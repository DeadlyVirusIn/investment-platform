"""Scheduled job: regenerate options_strategy_candidate from shadow
decisions + features for the target run_date.

Wraps ``options.strategy_candidates.service.generate_for_observations``.
Idempotent: INSERT ... ON CONFLICT (shadow_observation_id, rule_id)
DO NOTHING, plus skip_existing pre-filter — repeated runs add no
duplicates.

Reads:  options_shadow_decision_log, options_chain_snapshot,
        options_feature_daily
Writes: options_strategy_candidate  (ONLY)
NEVER touches paper / recommendation / canary / lifecycle tables.

Gated: no-ops when BOTH OPTIONS_ENABLED and OPTIONS_SHADOW_EVAL_ENABLED
are False (mirrors run_options_chain_snapshot_job).
"""

from __future__ import annotations

import datetime as dt

from loguru import logger

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.options.strategy_candidates.service import (
    generate_for_observations,
)


async def run_options_candidate_generation_job() -> dict:
    """No-arg async wrapper for the scheduler. Returns a status summary.

    status: "skipped" (flags off) | "ok" (>=1 inserted) |
            "no_data" (nothing new inserted) | "error".
    """
    if not (getattr(settings, "OPTIONS_ENABLED", False)
            or getattr(settings, "OPTIONS_SHADOW_EVAL_ENABLED", False)):
        logger.info(
            "options_candidate_generation skipped — OPTIONS_ENABLED and "
            "OPTIONS_SHADOW_EVAL_ENABLED both False",
        )
        return {"status": "skipped", "reason": "flags_off"}

    run_date = dt.datetime.now(dt.timezone.utc).date()
    try:
        with SessionLocal() as session:
            result = generate_for_observations(
                session, run_date=run_date, skip_existing=True,
            )
    except Exception:  # noqa: BLE001
        logger.exception("options_candidate_generation failed run_date={}", run_date)
        return {"status": "error", "run_date": run_date.isoformat()}

    status = "ok" if int(result.get("inserted", 0)) > 0 else "no_data"
    logger.info(
        "options_candidate_generation job done run_date={} status={} {}",
        run_date, status, result,
    )
    return {"status": status, "run_date": run_date.isoformat(), **result}
