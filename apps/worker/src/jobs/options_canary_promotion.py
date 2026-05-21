"""Phase Opt-C2 Pre-Canary 0 — promoter STUB.

Registered + cron-scheduled in migration 069. Body is intentionally
inert until Phase 1A activates promotion logic.

Activation gate: settings.OPTIONS_CANARY_ENABLED. Default False →
job logs noop and returns. Once Phase 1A lands, body is replaced
with:

  1. Read today's would_trade=true rows from
     options_shadow_decision_log filtered by
     (underlying_symbol = OPTIONS_CANARY_UNIVERSE,
      strategy implies OPTIONS_CANARY_STRATEGY)
  2. Apply DTE window (OPTIONS_CANARY_MIN_DTE / MAX_DTE)
  3. Check canary-spy-v1 portfolio open-trade count vs
     OPTIONS_CANARY_MAX_OPEN
  4. Check capital cap vs OPTIONS_CANARY_MAX_CAPITAL_USD
  5. Build OptionLegSpec list from Tradier sandbox quotes
  6. Call apps.api.src.options.persist_option.persist_option
     once per allowed promotion (max 1/day in Phase 1A)
  7. Write options_execution_funnel row with rollup counts

Discipline locks (will be enforced when body lands):
  * Never bypass persist_option (proposal_hash idempotency).
  * Never write paper_only=false.
  * Never call lifecycle.transition_to_fill from this job
    (lifecycle is a separate scheduled job).
  * Per-portfolio try/except — one error never aborts batch.
"""

from __future__ import annotations

from loguru import logger

from apps.api.src.config import settings


async def run_options_canary_promotion() -> dict:
    enabled = bool(getattr(settings, "OPTIONS_CANARY_ENABLED", False))
    if not enabled:
        logger.info(
            "[options_canary_promotion] OPTIONS_CANARY_ENABLED=false — noop"
        )
        return {"skipped": True, "reason": "canary_disabled"}

    # Phase 1A landing target: real promotion logic. Pre-Canary 0
    # only confirms the wrapper is wired and that the cron + flag
    # interactions are correct. Returning a sentinel so the
    # job_run row is success+0 rather than running real writes.
    logger.info(
        "[options_canary_promotion] gate ON but body not yet "
        "shipped (Phase 1A pending) — noop"
    )
    return {"skipped": True, "reason": "phase1a_not_shipped"}
