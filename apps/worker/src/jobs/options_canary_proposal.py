"""Canary-1 proposal scheduler entrypoint.

Gate 4 deliverable — operational shell only. Master flag gate at top
ensures no engine logic runs while OPTIONS_ENABLED + OPTIONS_CANARY_ENABLED
remain false. Telemetry is written on every invocation regardless of
outcome.

Direction:
  tick_loop  --►  this job  --►  apps.api.src.options.canary.engine

This module MUST NOT:
  - import other worker job modules
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


async def run_options_canary_proposal_job() -> dict[str, Any]:
    """Scheduler entrypoint. Wraps engine.run_proposal_cycle(now).

    Returns wrapper-RC dict per D2.3:
      {skipped: True, reason: <enum>}        — paused / no-op paths
      {return_code: !=0, reason: <enum>}     — error paths
      {return_code: 0, ...}                  — success paths

    tick_loop maps these to job_run.status correctly.
    """
    started_at = dt.datetime.now(dt.timezone.utc)

    # ---- Master flag gate (first executable line) -----------------------
    if not (settings.OPTIONS_ENABLED or settings.OPTIONS_CANARY_ENABLED):
        logger.info(
            "options_canary_proposal skipped — both OPTIONS_ENABLED and "
            "OPTIONS_CANARY_ENABLED are False",
        )
        finished_at = dt.datetime.now(dt.timezone.utc)
        _canary_engine._write_canary_telemetry(
            started_at=started_at,
            finished_at=finished_at,
            job_name="canary_proposal",
            classification="paused",
            counts={},
            error_summary={"flag_off": True},
        )
        return {"skipped": True, "reason": "master_flags_off"}

    # ---- Delegate to engine (Gate 4: engine cycle is itself a stub) -----
    try:
        return await _canary_engine.run_proposal_cycle(now=started_at)
    except Exception as exc:  # noqa: BLE001
        finished_at = dt.datetime.now(dt.timezone.utc)
        err = {"type": type(exc).__name__, "message": str(exc)[:512]}
        logger.error(
            "options_canary_proposal exception: {}: {}",
            type(exc).__name__, str(exc)[:512],
        )
        _canary_engine._write_canary_telemetry(
            started_at=started_at,
            finished_at=finished_at,
            job_name="canary_proposal",
            classification="error",
            failure_code="F6_deployment_drift",
            counts={},
            error_summary=err,
        )
        return {
            "return_code": 1,
            "reason": f"exception:{type(exc).__name__}",
        }
