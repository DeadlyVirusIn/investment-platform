"""Scheduled job: refresh options_feature_daily for the v1 ETF universe.

Wraps ``options.features.engine.compute_features_for`` — one call per
underlying. Idempotent: the engine upserts on (as_of_date, underlying),
so repeated runs overwrite rather than duplicate.

Reads:  options_chain_snapshot
Writes: options_feature_daily  (ONLY)
NEVER touches paper / recommendation / canary / lifecycle tables.

Gated: no-ops when BOTH OPTIONS_ENABLED and OPTIONS_SHADOW_EVAL_ENABLED
are False (mirrors run_options_chain_snapshot_job).
"""

from __future__ import annotations

import datetime as dt

from loguru import logger

from apps.api.src.config import settings
from apps.api.src.options.data.chain_ingest import DEFAULT_UNIVERSE
from apps.api.src.options.features.engine import compute_features_for


async def compute_options_features_job() -> dict:
    """No-arg async wrapper for the scheduler. Returns a status summary.

    status: "skipped" (flags off) | "ok" (>=1 real upsert) |
            "no_data" (all underlyings flagged NO_QUOTES) | "error".
    """
    if not (getattr(settings, "OPTIONS_ENABLED", False)
            or getattr(settings, "OPTIONS_SHADOW_EVAL_ENABLED", False)):
        logger.info(
            "compute_options_features skipped — OPTIONS_ENABLED and "
            "OPTIONS_SHADOW_EVAL_ENABLED both False",
        )
        return {"status": "skipped", "reason": "flags_off"}

    as_of = dt.datetime.now(dt.timezone.utc).date()
    upserted = 0
    no_quotes = 0
    errors = 0

    for sym in DEFAULT_UNIVERSE:
        try:
            summary = compute_features_for(underlying=sym, as_of_date=as_of)
            if summary.upserted:
                upserted += 1
            if any(str(f) == "NO_QUOTES" for f in summary.flags):
                no_quotes += 1
        except Exception:  # noqa: BLE001 — log + continue; one symbol must not abort the batch
            errors += 1
            logger.exception("compute_options_features failed for {}", sym)

    if errors:
        status = "error"
    elif no_quotes == len(DEFAULT_UNIVERSE):
        status = "no_data"
    else:
        status = "ok"

    logger.info(
        "compute_options_features job done as_of={} upserted={} "
        "no_quotes={} errors={} status={}",
        as_of, upserted, no_quotes, errors, status,
    )
    return {
        "status": status,
        "as_of": as_of.isoformat(),
        "upserted": upserted,
        "no_quotes": no_quotes,
        "errors": errors,
    }
