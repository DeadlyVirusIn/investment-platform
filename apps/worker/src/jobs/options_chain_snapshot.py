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
    build_ingest_run_record,
    ingest_universe,
    persist_ingest_run,
)


async def run_options_chain_snapshot_job() -> None:
    """No-arg async wrapper for scheduler integration (when wired).

    Idempotency: ingest_universe uses INSERT ... ON CONFLICT DO NOTHING
    on the natural key (snapshot_at_utc, underlying, expiry, strike,
    option_type). Multiple invocations within the same second are safe.

    Skips silently when OPTIONS_ENABLED is False — no work, no error.
    """
    # Phase Opt-B3a Step 6a — gate decoupled. Chain ingest fires when
    # EITHER OPTIONS_ENABLED (paper-exec master) OR
    # OPTIONS_SHADOW_EVAL_ENABLED (research persistence) is True,
    # because shadow eval needs fresh chain rows to evaluate against.
    if not (getattr(settings, "OPTIONS_ENABLED", False)
            or getattr(settings, "OPTIONS_SHADOW_EVAL_ENABLED", False)):
        logger.info(
            "options_chain_snapshot skipped — both OPTIONS_ENABLED and "
            "OPTIONS_SHADOW_EVAL_ENABLED are False",
        )
        return

    started_at = dt.datetime.now(dt.timezone.utc)
    snapshot_at = started_at
    summaries = ingest_universe(
        universe=DEFAULT_UNIVERSE,
        snapshot_at_utc=snapshot_at,
    )
    finished_at = dt.datetime.now(dt.timezone.utc)
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

    # Opt-Obs-Fix1 — write run-summary telemetry the admin-observability
    # `options_chains` freshness card reads. Defensive: a telemetry-write
    # failure must never fail the ingest itself.
    try:
        record = build_ingest_run_record(
            summaries,
            started_at=started_at,
            finished_at=finished_at,
            universe=DEFAULT_UNIVERSE,
            provider_default=getattr(
                settings, "OPTIONS_DATA_PROVIDER", "unknown"),
        )
        persist_ingest_run(record)
        logger.info(
            "options_chain_ingest_run written classification={} "
            "rows_inserted={} rows_dedup={} rows_filtered_out={}",
            record["classification"], record["rows_inserted"],
            record["rows_dedup"], record["rows_filtered_out"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "failed to write options_chain_ingest_run telemetry: {}", exc,
        )
