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
from sqlalchemy import select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import JobRun, JobSchedule
from apps.worker.src.jobs.registry import REGISTRY

_TICK_INTERVAL: int = 60          # seconds between polls
_MAX_CONCURRENT: int = 3          # asyncio.Semaphore slots

# P6D.36A — liveness heartbeat for the compose healthcheck. Touched once
# per loop iteration (even when the tick itself errors: the loop being
# alive is what the healthcheck asserts; job failures are tracked in
# job_run). Healthcheck fails when mtime is older than ~3 intervals.
_HEARTBEAT_FILE: str = os.environ.get("WORKER_HEARTBEAT_FILE", "/tmp/worker_heartbeat")


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
            await job_fn()
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
                        cron = croniter(sched_row.cron_expr, finished_at)
                        sched_row.next_run_at = cron.get_next(datetime.datetime)
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
