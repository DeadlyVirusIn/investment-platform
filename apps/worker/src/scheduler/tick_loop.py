"""DB-backed tick-loop scheduler.  Polls job_schedule every 60 s, no Celery.

Timezone semantics: cron expressions in `job_schedule.cron_expr` are
evaluated in SCHEDULER_TZ (default America/New_York) so operators can
specify wall-clock times like `0 22 * * 1-5` meaning 22:00 ET, not
22:00 UTC. `next_run_at` and `last_run_at` are stored in UTC.

Override via env `SCHEDULER_TZ`.
"""

from __future__ import annotations

import asyncio
import datetime
import os
import traceback
from decimal import Decimal

from croniter import croniter
from loguru import logger
from sqlalchemy import select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import JobRun, JobSchedule
from apps.worker.src.jobs.registry import REGISTRY

_TICK_INTERVAL: int = 60          # seconds between polls
_MAX_CONCURRENT: int = 3          # asyncio.Semaphore slots
_SCHEDULER_TZ = os.environ.get("SCHEDULER_TZ", "America/New_York")


def _tz():
    """Return the configured scheduler timezone."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(_SCHEDULER_TZ)
    except Exception:
        # Final fallback: UTC (preserves legacy behavior on exotic hosts)
        return datetime.timezone.utc


def _next_cron_utc(cron_expr: str, base_utc: datetime.datetime) -> datetime.datetime:
    """Compute next fire-time in UTC from a cron_expr interpreted in
    SCHEDULER_TZ. Input `base_utc` must be tz-aware UTC."""
    local_base = base_utc.astimezone(_tz())
    nxt_local = croniter(cron_expr, local_base).get_next(datetime.datetime)
    # croniter returns naive datetime; attach the scheduler tz, then to UTC
    if nxt_local.tzinfo is None:
        nxt_local = nxt_local.replace(tzinfo=_tz())
    return nxt_local.astimezone(datetime.timezone.utc)


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
            # Phase L wrapper-RC honesty: a job returning {"skipped": True}
            # has done no substantive work. Classify it accordingly so
            # dashboards stop conflating "ran" with "succeeded at work".
            if isinstance(result, dict) and result.get("skipped") is True:
                status = "skipped"
                reason = result.get("reason")
                if reason:
                    error_msg = f"skipped: {reason}"
                logger.info(
                    "Job '{}' skipped (reason={})",
                    schedule.name, reason,
                )
            # A non-zero return_code from a wrapper that has explicitly
            # surfaced one (without raising) is an error.
            elif isinstance(result, dict) and isinstance(
                result.get("return_code"), int,
            ) and result["return_code"] != 0:
                status = "error"
                error_msg = (
                    f"non-zero return_code={result['return_code']} from "
                    f"wrapper {schedule.name}"
                )
                logger.error(
                    "Job '{}' returned non-zero rc={}",
                    schedule.name, result["return_code"],
                )
        except Exception:
            status = "error"
            error_msg = traceback.format_exc()
            logger.error("Job '{}' failed:\n{}", schedule.name, error_msg)
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
                    sched_row.last_run_at = finished_at
                    try:
                        # Interpret cron in configured tz (ET by default)
                        sched_row.next_run_at = _next_cron_utc(
                            sched_row.cron_expr, finished_at,
                        )
                    except Exception as cron_exc:
                        logger.warning("croniter error for '{}': {}", sched_row.name, cron_exc)

                session.commit()

        logger.info("Job '{}' finished – status={} duration={}s", schedule.name, status, duration)


async def _tick() -> None:
    """Single scheduler tick: find due jobs and launch them."""
    now = datetime.datetime.now(datetime.timezone.utc)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

    with SessionLocal() as session:
        stmt = select(JobSchedule).where(
            JobSchedule.enabled == True,  # noqa: E712
            JobSchedule.next_run_at <= now,
        )
        due: list[JobSchedule] = list(session.scalars(stmt).all())

    if not due:
        return

    logger.debug("Scheduler tick: {} job(s) due", len(due))
    tasks = [asyncio.create_task(_execute_job(sched, semaphore)) for sched in due]
    await asyncio.gather(*tasks, return_exceptions=True)


async def _reconcile_schedule_tz() -> None:
    """Rewrite next_run_at for every enabled schedule using the current
    SCHEDULER_TZ. Run once at startup so cron_expr like `0 22 * * 1-5`
    stops firing at 22:00 UTC (18:00 ET) and starts firing at 22:00 ET.

    Jobs that were already overdue keep their overdue state — they will
    fire on the next tick and self-correct afterwards.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    with SessionLocal() as session:
        rows = list(session.scalars(
            select(JobSchedule).where(JobSchedule.enabled == True),  # noqa: E712
        ).all())
        for r in rows:
            try:
                new_next = _next_cron_utc(r.cron_expr, now)
            except Exception as e:
                logger.warning(
                    "reconcile_tz: cron parse failed for '{}': {}",
                    r.name, e,
                )
                continue
            # Only advance next_run_at — never pull it backwards into the
            # past if croniter+tz happens to produce a nearer time, since
            # that could cause an immediate fire of a job the operator
            # doesn't expect.
            if r.next_run_at is None or new_next > r.next_run_at:
                r.next_run_at = new_next
        session.commit()
    logger.info(
        "Scheduler tz reconciled ({} jobs, tz={})",
        len(rows), _SCHEDULER_TZ,
    )


async def run() -> None:
    """Run the scheduler loop indefinitely."""
    logger.info(
        "Scheduler tick-loop started (interval={}s, tz={})",
        _TICK_INTERVAL, _SCHEDULER_TZ,
    )
    try:
        await _reconcile_schedule_tz()
    except Exception:
        logger.error("tz reconcile failed:\n{}", traceback.format_exc())
    while True:
        try:
            await _tick()
        except Exception:
            logger.error("Unhandled error in tick:\n{}", traceback.format_exc())
        await asyncio.sleep(_TICK_INTERVAL)
