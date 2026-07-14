"""DB-backed tick-loop scheduler.  Polls job_schedule every 60 s, no Celery."""

from __future__ import annotations

import asyncio
import datetime
import os
import traceback
from decimal import Decimal
from pathlib import Path

from croniter import croniter
from loguru import logger
from sqlalchemy import select, text

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import JobRun, JobSchedule
from apps.api.src.options.data_provider._redact import (
    redact_error_for_storage as _redact_store,
)
from apps.worker.src.jobs.registry import REGISTRY

_TICK_INTERVAL: int = 60          # seconds between polls
_MAX_CONCURRENT: int = 3          # asyncio.Semaphore slots

# P6D.36A — liveness heartbeat for the compose healthcheck. Touched once
# per loop iteration (even when the tick itself errors: the loop being
# alive is what the healthcheck asserts; job failures are tracked in
# job_run). Healthcheck fails when mtime is older than ~3 intervals.
_HEARTBEAT_FILE: str = os.environ.get("WORKER_HEARTBEAT_FILE", "/tmp/worker_heartbeat")


def _result_reports_failure(result: object) -> bool:
    """P0-2A.4 — jobs may swallow their own exceptions and signal failure
    via a returned ``{"status": "error"|"failed"}`` dict (e.g.
    options_candidate_generation). The scheduler must honor that contract,
    not just raised exceptions — on 2026-06-12 a NoSuchColumnError outage
    was recorded as status=success because the return value was discarded."""
    return (
        isinstance(result, dict)
        and str(result.get("status", "")).lower() in ("error", "failed")
    )


def _claim_due_job(schedule: JobSchedule, now: datetime.datetime) -> bool:
    """P0-5A — atomically claim one due job for execution.

    Both worker containers run this same scheduler loop. To guarantee a
    job runs exactly once, advance `next_run_at` to the next cron slot
    inside a single guarded UPDATE: the scheduler whose UPDATE matches
    the row (RETURNING a row) wins; any sibling's identical UPDATE then
    matches 0 rows (next_run_at already in the future) and skips. No
    migration — reuses the existing next_run_at column.

    Returns True if THIS scheduler claimed the job. A malformed cron is
    surfaced loudly and NOT claimed (the job won't fire until fixed —
    safer than re-running every tick)."""
    try:
        next_run = croniter(schedule.cron_expr, now).get_next(datetime.datetime)
    except Exception as exc:  # noqa: BLE001 — malformed cron, don't claim
        logger.warning("croniter error claiming '{}': {}", schedule.name, exc)
        return False
    with SessionLocal() as session:
        row = session.execute(
            text(
                "UPDATE job_schedule SET next_run_at = :next "
                "WHERE id = :id AND enabled = true AND next_run_at <= :now "
                "RETURNING id"
            ),
            {"next": next_run, "id": schedule.id, "now": now},
        ).first()
        session.commit()
    return row is not None


def _heal_null_schedules(now: datetime.datetime) -> int:
    """P0-5B — bootstrap enabled schedules whose ``next_run_at`` is NULL.

    Migration-seeded rows (e.g. 069's options jobs, the exit-cycle row)
    were created with next_run_at NULL, and the claim predicate
    (``next_run_at <= now``) can never match NULL — such jobs are stuck
    forever and have 0 job_run rows. Repair = compute the next valid slot
    from the row's own cron_expr (NEVER "now": no immediate mass-fire).

    Safety:
      * disabled rows are never touched;
      * malformed cron_expr is left NULL and surfaced loudly as a
        structured ``schedule_stuck`` error (visible, not executed);
      * the guarded UPDATE (``AND next_run_at IS NULL``) is race-safe
        across both scheduler containers — the loser matches 0 rows;
      * exactly-once execution still flows through _claim_due_job.

    Returns the number of rows repaired by THIS instance."""
    repaired = 0
    with SessionLocal() as session:
        rows = list(session.scalars(
            select(JobSchedule).where(
                JobSchedule.enabled == True,  # noqa: E712
                JobSchedule.next_run_at.is_(None),
            )
        ))
        for sched in rows:
            try:
                nxt = croniter(sched.cron_expr, now).get_next(datetime.datetime)
            except Exception as exc:  # noqa: BLE001 — malformed cron: stuck, visible
                logger.error(
                    'schedule_stuck name="{}" reason=invalid_cron cron_expr={!r} error="{}"',
                    sched.name, sched.cron_expr, exc,
                )
                continue
            row = session.execute(
                text(
                    "UPDATE job_schedule SET next_run_at = :next "
                    "WHERE id = :id AND enabled = true AND next_run_at IS NULL "
                    "RETURNING id"
                ),
                {"next": nxt, "id": sched.id},
            ).first()
            if row is not None:
                repaired += 1
                logger.info(
                    'schedule_repaired name="{}" next_run_at="{}" reason=null_bootstrap',
                    sched.name, nxt.isoformat(),
                )
        session.commit()
    return repaired


def _touch_heartbeat() -> None:
    try:
        Path(_HEARTBEAT_FILE).touch()
    except OSError as exc:  # never let liveness plumbing kill the loop
        logger.warning("heartbeat touch failed ({}): {}", _HEARTBEAT_FILE, exc)


async def _execute_job(schedule: JobSchedule, semaphore: asyncio.Semaphore) -> None:
    """Run a single scheduled job inside the semaphore, updating job_run rows."""
    async with semaphore:
        job_fn = REGISTRY.get(schedule.name)
        if job_fn is None:
            logger.warning("No handler registered for job '{}'", schedule.name)
            return

        started_at = datetime.datetime.now(datetime.timezone.utc)
        run_id: str | None = None

        # -- open run row ------------------------------------------------
        with SessionLocal() as session:
            run = JobRun(
                job_schedule_id=schedule.id,
                started_at=started_at,
                status="running",
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            run_id = run.id

        logger.info("Job '{}' started (run_id={})", schedule.name, run_id)

        status = "success"
        error_msg: str | None = None
        try:
            result = await job_fn()
        except Exception:
            status = "error"
            # Redact before BOTH logging and DB storage: a traceback can carry
            # a provider URL with `…apiKey=…`. The loguru patcher scrubs the
            # log line; job_run.error_message bypasses loguru so scrub here.
            error_msg = _redact_store(traceback.format_exc())
            logger.error("Job '{}' failed:\n{}", schedule.name, error_msg)
        else:
            # P0-2A.4 — honor job-reported failure (swallowed exceptions
            # returned as {"status": "error"}). Same recording path as a
            # raise; scheduling/retry semantics unchanged.
            if _result_reports_failure(result):
                status = "error"
                error_msg = _redact_store(f"job returned failure status: {result!r}")[:2000]
                logger.error(
                    "Job '{}' reported failure via return value: {}",
                    schedule.name, error_msg,
                )
        finally:
            finished_at = datetime.datetime.now(datetime.timezone.utc)
            duration = Decimal(str((finished_at - started_at).total_seconds()))

            # -- close run row + update schedule -------------------------
            with SessionLocal() as session:
                run_row = session.get(JobRun, run_id)
                if run_row is not None:
                    run_row.finished_at = finished_at
                    run_row.status = status
                    run_row.error_message = error_msg
                    run_row.duration_seconds = duration

                sched_row = session.get(JobSchedule, schedule.id)
                if sched_row is not None:
                    # P0-5A — next_run_at is advanced atomically at CLAIM
                    # time in _claim_due_job; no longer recomputed here
                    # (recomputing post-execution was the non-atomic step
                    # that let both schedulers run the same job).
                    sched_row.last_run_at = finished_at

                session.commit()

        logger.info("Job '{}' finished – status={} duration={}s", schedule.name, status, duration)


async def _tick() -> None:
    """Single scheduler tick: find due jobs and launch them."""
    now = datetime.datetime.now(datetime.timezone.utc)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

    # P0-5B — repair NULL next_run_at rows BEFORE the due query so newly
    # seeded / stuck schedules join the normal claim flow at their NEXT
    # cron slot (never immediately).
    _heal_null_schedules(now)

    with SessionLocal() as session:
        stmt = select(JobSchedule).where(
            JobSchedule.enabled == True,  # noqa: E712
            JobSchedule.next_run_at <= now,
        )
        due: list[JobSchedule] = list(session.scalars(stmt).all())

    if not due:
        return

    # P0-5A — atomically claim each due job before executing. A racing
    # scheduler claims the rest; no job runs twice. Skipped (lost-race)
    # rows return False and are not executed by this instance.
    claimed = [sched for sched in due if _claim_due_job(sched, now)]
    if not claimed:
        return

    logger.debug(
        "Scheduler tick: {} due, {} claimed by this instance",
        len(due), len(claimed),
    )
    tasks = [asyncio.create_task(_execute_job(sched, semaphore)) for sched in claimed]
    await asyncio.gather(*tasks, return_exceptions=True)


async def run() -> None:
    """Run the scheduler loop indefinitely."""
    logger.info("Scheduler tick-loop started (interval={}s)", _TICK_INTERVAL)
    while True:
        _touch_heartbeat()
        try:
            await _tick()
        except Exception:
            logger.error("Unhandled error in tick:\n{}", traceback.format_exc())
        await asyncio.sleep(_TICK_INTERVAL)
