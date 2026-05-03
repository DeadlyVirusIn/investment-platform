"""Options chain snapshot worker job (Phase 11C — function only;
NOT yet registered in registry / cron).

Cron target (per docs/research/OPTIONS_SYSTEM_DESIGN.md): every 15 min
during market hours (e.g. cron `*/15 13-21 * * 1-5` in UTC).

Phase 11C ships only the no-arg async wrapper. Scheduler registration
+ market-hours gating + cron seeding are deferred to a later phase
(Phase 11C.x or Phase 11E scheduler-wiring) to keep this commit
strictly to the data-ingest layer per operator scope.

Hard-isolated from V2 / equity / governance / execution.
"""

from __future__ import annotations

import datetime as dt

from loguru import logger

from apps.api.src.config import settings
from apps.api.src.options.data.chain_ingest import (
    DEFAULT_UNIVERSE,
    ingest_universe,
)


async def run_options_chain_snapshot_job() -> None:
    """No-arg async wrapper for scheduler integration (when wired).

    Idempotency: ingest_universe uses INSERT ... ON CONFLICT DO NOTHING
    on the natural key (snapshot_at_utc, underlying, expiry, strike,
    option_type). Multiple invocations within the same second are safe.

    Skips silently when OPTIONS_ENABLED is False — no work, no error.
    """
    if not getattr(settings, "OPTIONS_ENABLED", False):
        logger.info(
            "options_chain_snapshot job skipped — OPTIONS_ENABLED=False",
        )
        return

    snapshot_at = dt.datetime.now(dt.timezone.utc)
    summaries = ingest_universe(
        universe=DEFAULT_UNIVERSE,
        snapshot_at_utc=snapshot_at,
    )
    n_ok = sum(1 for s in summaries if s.status == "ok")
    n_partial = sum(1 for s in summaries if s.status == "partial")
    n_skipped = sum(1 for s in summaries if s.status == "skipped_unavailable")
    n_error = sum(1 for s in summaries if s.status == "error")
    total_inserted = sum(s.n_inserted for s in summaries)
    logger.info(
        "options_chain_snapshot job done snapshot_at={} ok={} partial={} "
        "skipped={} error={} total_inserted={}",
        snapshot_at, n_ok, n_partial, n_skipped, n_error, total_inserted,
    )
