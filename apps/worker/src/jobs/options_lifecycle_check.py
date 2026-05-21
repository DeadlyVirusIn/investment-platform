"""Phase Opt-C2 Pre-Canary 0 — lifecycle check STUB.

Registered + cron-scheduled in migration 069. Body is intentionally
inert until Phase 1B activates fill + close logic.

Activation gate: settings.OPTIONS_CANARY_ENABLED. Default False →
job logs noop and returns.

Phase 1B target body (when it lands):

  Morning fill pass (PROPOSED → OPEN):
    1. SELECT * FROM options_paper_trade WHERE status='PROPOSED'
       AND opened_at::date < today
    2. For each: query latest options_chain_snapshot for the legs
    3. If snapshot.snapshot_at_utc::date > opened_at::date
       (next-bar discipline): call lifecycle.transition_to_fill
       with new mid prices
    4. Reserve capital in options_paper_position
    5. Decrement options_paper_portfolio.cash_current

  Afternoon evaluation pass (OPEN → CLOSED/EXPIRED/ASSIGNED):
    For each OPEN trade:
      a. Compute current spread mid from latest chain
      b. If target_pct hit → transition_to_close (target_hit)
      c. If stop_pct hit → transition_to_close (stop_hit)
      d. If DTE <= time_stop_dte → transition_to_close (time_stop)
      e. If at expiry: route via assignment-precedence rule
         (ITM short legs → transition_to_assigned; else _expired)

Discipline locks (will be enforced when body lands):
  * All transitions go through apps.api.src.options.lifecycle.
    Never UPDATE status directly.
  * Next-bar fill rule: snapshot date > opened_at date.
  * Capital release on every terminal transition.
  * Per-trade try/except — one failure never aborts batch.
"""

from __future__ import annotations

from loguru import logger

from apps.api.src.config import settings


async def run_options_lifecycle_check() -> dict:
    enabled = bool(getattr(settings, "OPTIONS_CANARY_ENABLED", False))
    if not enabled:
        logger.info(
            "[options_lifecycle_check] OPTIONS_CANARY_ENABLED=false — noop"
        )
        return {"skipped": True, "reason": "canary_disabled"}

    logger.info(
        "[options_lifecycle_check] gate ON but body not yet shipped "
        "(Phase 1B pending) — noop"
    )
    return {"skipped": True, "reason": "phase1b_not_shipped"}
