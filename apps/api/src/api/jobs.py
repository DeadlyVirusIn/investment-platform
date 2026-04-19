"""Jobs API – scheduler health and manual trigger endpoints."""

import datetime
from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/health")
async def jobs_health() -> dict[str, Any]:
    return {
        "jobs": [],
        "scheduler_alive": True,
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@router.post("/{name}/run")
async def trigger_job(name: str) -> dict[str, Any]:
    return {"queued": True, "job": name}
