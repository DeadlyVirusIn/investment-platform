"""Canary-1 lifecycle scheduler entrypoint.

Gate 4 deliverable — operational shell only. Master flag gate at top
ensures no engine logic runs while OPTIONS_ENABLED + OPTIONS_CANARY_ENABLED
remain false. Telemetry is written on every invocation regardless of
outcome.

Owns: fill / monitor / exit for the single canary trade. NOT proposals.

Direction:
  tick_loop  --►  this job  --►  apps.api.src.options.canary.engine

This module MUST NOT:
  - import options_canary_proposal
  - import apps.api.src.options.canary.operator_event
  - write directly to options_trade_lifecycle_event
  - write directly to options_canary_lifecycle_run

CI lint (infra/ci/constitutional_checklist/canary_gateway_lint.py)
enforces all of the above.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from loguru import logger

from apps.api.src.config import settings
from apps.api.src.options.canary import engine as _canary_engine


async def run_options_canary_lifecycle_job() -> dict[str, Any]:
    """Scheduler entrypoint. Wraps engine.run_lifecycle_cycle(now).

    Rate-limited internally per MONITOR_MIN_INTERVAL_SECONDS; re-invocations
    inside the window still write telemetry but skip lifecycle-event writes.
    """
    started_at = dt.datetime.now(dt.timezone.utc)

    # ---- Master flag gate (first executable line) -----------------------
    # Per Gate 5 Blast-Radius D1: lifecycle stays dormant during Gate 5
    # (proposal-only phase). Lifecycle gates on OPTIONS_ENABLED ALONE; the
    # canary-only flag does NOT un-skip this job. Activates at Gate 6+
    # when fill logic ships.
    if not settings.OPTIONS_ENABLED:
        logger.info(
            "options_canary_lifecycle skipped — OPTIONS_ENABLED is False "
            "(Gate 5 lifecycle dormancy; canary flag alone does not "
            "activate fill/monitor/exit paths)",
        )
        finished_at = dt.datetime.now(dt.timezone.utc)
        _canary_engine._write_canary_telemetry(
            started_at=started_at,
            finished_at=finished_at,
            job_name="canary_lifecycle",
            classification="paused",
            counts={},
            error_summary={"flag_off": True},
        )
        return {"skipped": True, "reason": "master_flags_off"}

    # ---- Delegate to engine (Gate 4: engine cycle is itself a stub) -----
    try:
        return await _canary_engine.run_lifecycle_cycle(now=started_at)
    except Exception as exc:  # noqa: BLE001
        finished_at = dt.datetime.now(dt.timezone.utc)
        err = {"type": type(exc).__name__, "message": str(exc)[:512]}
        logger.error(
            "options_canary_lifecycle exception: {}: {}",
            type(exc).__name__, str(exc)[:512],
        )
        _canary_engine._write_canary_telemetry(
            started_at=started_at,
            finished_at=finished_at,
            job_name="canary_lifecycle",
            classification="error",
            failure_code="F6_deployment_drift",
            counts={},
            error_summary=err,
        )
        return {
            "return_code": 1,
            "reason": f"exception:{type(exc).__name__}",
        }
