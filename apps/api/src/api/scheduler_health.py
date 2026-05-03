"""Daily Loop Health endpoint.

Reads persisted health markers + DB job_schedule so Ops can show:
  • last successful loop timestamp
  • last failed loop timestamp
  • last scheduled tickloop run per job
  • next scheduled tickloop run per job
  • current lock file presence (best-effort)

Markers live in /tmp inside worker-cron container, bind-mounted to a
docker-volume `worker_cron_tmp`. The API container does NOT mount that
volume by default, so we fall back to reading via the DB-backed
job_schedule for tickloop data and expose marker endpoints primarily
for the worker-cron container to write.
"""

from __future__ import annotations

import datetime as dt
import os
import pathlib
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db import SessionLocal

router = APIRouter(prefix="/scheduler", tags=["scheduler"])

# Optional bind-mount location — overridable via env.
# When unset, marker-based fields return null.
MARKER_DIR = os.environ.get("SCHEDULER_MARKER_DIR", "")


def _s() -> Session:
    return SessionLocal()


def _read_marker(name: str) -> str | None:
    if not MARKER_DIR:
        return None
    p = pathlib.Path(MARKER_DIR) / name
    try:
        return p.read_text().strip() if p.exists() else None
    except Exception:
        return None


def _lock_held() -> bool | None:
    """Probe the worker-cron lock file via the marker volume, not the
    API container's own /tmp. Presence alone is not proof of flock —
    supercronic may leave the file after release — so this is a best-
    effort indicator only."""
    if not MARKER_DIR:
        return None
    # worker-cron writes lock to /tmp/quant_daily_loop.lock; the volume
    # worker_cron_tmp mounts that same /tmp tree into the API container
    # at MARKER_DIR (read-only).
    lock = pathlib.Path(MARKER_DIR) / "quant_daily_loop.lock"
    try:
        return lock.exists()
    except Exception:
        return None


@router.get("/health")
async def scheduler_health() -> dict[str, Any]:
    """Return daily-loop + tickloop scheduler snapshot."""
    # --- tickloop schedule + last runs (DB-backed) ---
    with _s() as s:
        jobs = s.execute(text("""
            SELECT js.name, js.cron_expr, js.enabled,
                   js.last_run_at, js.next_run_at,
                   (
                     SELECT jr.status FROM job_run jr
                     WHERE jr.job_schedule_id = js.id
                     ORDER BY jr.started_at DESC LIMIT 1
                   ) AS last_status,
                   (
                     SELECT jr.error_message FROM job_run jr
                     WHERE jr.job_schedule_id = js.id
                     ORDER BY jr.started_at DESC LIMIT 1
                   ) AS last_error
            FROM job_schedule js
            ORDER BY js.name
        """)).mappings().all()
        last_runs = s.execute(text("""
            SELECT jr.started_at, jr.finished_at, jr.status, js.name
            FROM job_run jr
            JOIN job_schedule js ON js.id = jr.job_schedule_id
            ORDER BY jr.started_at DESC
            LIMIT 10
        """)).mappings().all()

    # --- daily loop markers (cron container) ---
    last_success = _read_marker("last_daily_loop_success")
    last_failure = _read_marker("last_daily_loop_failure")
    lock = _lock_held()

    # Next cron — static schedule from crontab file (Tue-Sat 03:30 ET).
    next_cron = _next_cron_fire()

    return {
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "daily_loop": {
            "last_success_at":  last_success,
            "last_failure_at":  last_failure,
            "lock_present":     lock,
            "next_scheduled":   next_cron.isoformat() if next_cron else None,
            "marker_dir":       MARKER_DIR or None,
        },
        "tickloop": {
            "jobs": [dict(j) for j in jobs],
            "recent_runs": [dict(r) for r in last_runs],
        },
    }


def _next_cron_fire() -> dt.datetime | None:
    """Compute the next 03:30 ET Tue–Sat fire time.

    Runs in whatever TZ the API container has. Assumes the cron lives in
    America/New_York; we express the result in UTC. This is best-effort
    (DST boundaries may drift by 1 hour until the next scheduled run
    recalibrates).
    """
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/New_York")
        now = dt.datetime.now(tz)
        # Start from today 03:30 local
        candidate = now.replace(hour=3, minute=30, second=0, microsecond=0)
        if candidate <= now:
            candidate = candidate + dt.timedelta(days=1)
        # Advance until weekday in {Tue..Sat} = 1..5
        while candidate.weekday() not in (1, 2, 3, 4, 5):
            candidate = candidate + dt.timedelta(days=1)
        return candidate.astimezone(dt.timezone.utc)
    except Exception:
        return None
