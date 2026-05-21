"""Phase Opt-C2 Pre-Canary 0.1 — options feature engine wrapper.

Calls `apps.api.src.options.features.engine.compute_features_for` for
every underlying in `settings.OPTIONS_RUN_UNIVERSE`, populating
`options_feature_daily` once per trading day per underlying.

Why this job exists
-------------------
Audit (Phase Opt-C2 forensic) found `options_feature_daily` table at
0 rows EVER. The feature engine code at
`apps/api/src/options/features/engine.py` is full Phase 11D
implementation — it was never wired to a scheduler.

Consequence of the gap: shadow_evaluator's `iv_rank_pass` gate fails
open (always passes) because the IV-rank lookup returns None →
treated as no-rejection. Operating without IV-rank discipline is a
silent downgrade of the rejection logic.

This wrapper plugs the gap. Strict invariants:

  * Reads ONLY from options_chain_snapshot (via the engine).
  * Writes ONLY to options_feature_daily (via engine._upsert).
  * Never touches options_paper_trade or lifecycle tables.
  * Never calls a provider directly.
  * Per-underlying try/except — one failure does not abort batch.

Cron target: `35 21 * * 1-5` (UTC), between chain snapshot at 21:30
and shadow eval at 21:45. Snapshot must finish first; eval can then
read fresh feature rows.
"""

from __future__ import annotations

import datetime as dt

from loguru import logger

from apps.api.src.config import settings
from apps.api.src.options.features.engine import compute_features_for


async def run_options_features_compute(
    as_of: dt.date | None = None,
) -> dict:
    """Compute one feature row per underlying for the given date.

    When ``as_of`` is None, uses today's UTC date.
    Returns a summary dict for logging / test inspection.
    """
    target_date = as_of or dt.datetime.now(dt.timezone.utc).date()
    universe = tuple(getattr(settings, "OPTIONS_RUN_UNIVERSE",
                             ("SPY", "QQQ", "IWM", "GLD", "TLT")))

    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []

    for underlying in universe:
        try:
            summary = compute_features_for(
                underlying=underlying, as_of_date=target_date,
            )
            succeeded.append(underlying)
            logger.info(
                "[options_features] {} @ {} accepted={}/{} flags={}",
                underlying, target_date,
                summary.n_accepted, summary.n_chain_rows,
                list(summary.flags),
            )
        except Exception as exc:  # noqa: BLE001 — per-symbol isolation
            failed.append((underlying, str(exc)))
            logger.error(
                "[options_features] {} @ {} FAILED: {}",
                underlying, target_date, exc,
            )

    result = {
        "as_of_date": target_date.isoformat(),
        "universe_size": len(universe),
        "succeeded": succeeded,
        "failed": failed,
    }
    logger.info(
        "[options_features] complete: {} ok, {} failed",
        len(succeeded), len(failed),
    )
    return result
