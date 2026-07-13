"""Scheduled Research Safe Mode posture evaluation (Wave 1B).

Runs the SAME deterministic evaluator the lazy read path and owner console
use (``domain.publication.posture.evaluate_and_record``) through the
claim/lease-safe scheduler, so posture is refreshed on cadence instead of
only on reads. Flag-guarded: with SYSTEM_POSTURE_ENABLED off the job no-ops
with a log line (no signals read, no event rows written).

No schedule row is inserted by any migration — scheduling this job is part
of the flag-enablement runbook (see docs/architecture/RESEARCH_SAFE_MODE.md).
Suggested cadence: every 15 minutes.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.domain.publication import posture as ps


async def evaluate_system_posture() -> dict[str, Any]:
    if not settings.SYSTEM_POSTURE_ENABLED:
        logger.info("evaluate_system_posture: flag off — no-op")
        return {"status": "skipped", "reason": "SYSTEM_POSTURE_ENABLED=false"}
    with SessionLocal() as session:
        row = ps.evaluate_and_record(session, triggered_by="system")
    logger.info(
        "evaluate_system_posture: posture={} event={}",
        row.get("posture"), row.get("id"),
    )
    return {"status": "ok", "posture": row.get("posture"),
            "event_id": row.get("id")}
