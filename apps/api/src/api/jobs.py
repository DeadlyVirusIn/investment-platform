"""Jobs API: scheduler health + manual job trigger (synchronous)."""

from __future__ import annotations

import datetime as dt
import traceback
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger
from sqlalchemy import select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import JobRun, JobSchedule

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/health")
async def jobs_health() -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    jobs: list[dict[str, Any]] = []

    with SessionLocal() as session:
        schedules = list(session.scalars(select(JobSchedule)).all())
        for sched in schedules:
            last_run = session.scalars(
                select(JobRun)
                .where(JobRun.job_schedule_id == sched.id)
                .order_by(JobRun.started_at.desc())
                .limit(1)
            ).first()
            jobs.append(
                {
                    "name": sched.name,
                    "cron": sched.cron_expr,
                    "enabled": sched.enabled,
                    "last_run_at": sched.last_run_at.isoformat() if sched.last_run_at else None,
                    "next_run_at": sched.next_run_at.isoformat() if sched.next_run_at else None,
                    "last_status": last_run.status if last_run else None,
                    "last_error": last_run.error_message if last_run else None,
                }
            )

    return {
        "jobs": jobs,
        "scheduler_alive": True,
        "checked_at": now.isoformat(),
    }


@router.post("/{name}/run")
async def trigger_job(name: str) -> dict[str, Any]:
    """Synchronously execute a registered job and return its run summary."""
    from apps.worker.src.jobs.registry import REGISTRY

    job_fn = REGISTRY.get(name)
    if job_fn is None:
        raise HTTPException(status_code=404, detail=f"unknown job: {name}")

    started_at = dt.datetime.now(dt.timezone.utc)

    # Resolve or create a schedule row so run rows always have a parent.
    with SessionLocal() as session:
        sched = session.scalars(
            select(JobSchedule).where(JobSchedule.name == name)
        ).first()
        if sched is None:
            raise HTTPException(
                status_code=404,
                detail=f"no job_schedule row for '{name}' — seed it first",
            )
        run = JobRun(
            job_schedule_id=sched.id,
            started_at=started_at,
            status="running",
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id

    status = "success"
    error_msg: str | None = None
    try:
        await job_fn()
    except Exception:  # noqa: BLE001
        status = "error"
        error_msg = traceback.format_exc()
        logger.error("Manual trigger for '{}' failed:\n{}", name, error_msg)

    finished_at = dt.datetime.now(dt.timezone.utc)
    duration = Decimal(str((finished_at - started_at).total_seconds()))

    with SessionLocal() as session:
        run_row = session.get(JobRun, run_id)
        if run_row is not None:
            run_row.finished_at = finished_at
            run_row.status = status
            run_row.error_message = error_msg
            run_row.duration_seconds = duration
        sched_row = session.get(JobSchedule, run.job_schedule_id)
        if sched_row is not None:
            sched_row.last_run_at = finished_at
        session.commit()

    return {
        "run_id": run_id,
        "job": name,
        "status": status,
        "duration_seconds": str(duration),
        "error": error_msg,
    }
