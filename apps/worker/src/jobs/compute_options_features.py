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

from decimal import Decimal

from sqlalchemy import text

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.options.data.chain_ingest import DEFAULT_UNIVERSE
from apps.api.src.options.features.engine import compute_features_for


def _latest_price_bar_close(symbol: str) -> Decimal | None:
    """Latest daily close from price_bar (reuses the stock pipeline's
    bars) as the moneyness spot. Returns None when the symbol has no
    price_bar coverage (e.g. GLD/TLT) — caller falls back to spot=None.
    """
    with SessionLocal() as session:
        row = session.execute(text(
            """
            SELECT coalesce(adjusted_close, close)
            FROM price_bar
            WHERE asset_id IN (
                SELECT id FROM asset WHERE symbol = :s LIMIT 1
            ) AND timeframe = '1d'
            ORDER BY ts DESC LIMIT 1
            """
        ), {"s": symbol}).first()
    if row is None or row[0] is None:
        return None
    return Decimal(str(row[0]))


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
    spot_missing = 0

    for sym in DEFAULT_UNIVERSE:
        # Layer 2B — source moneyness spot from price_bar (stock pipeline).
        # GLD/TLT have no price_bar coverage → spot=None (moneyness NULL).
        spot = _latest_price_bar_close(sym)
        if spot is None:
            spot_missing += 1
            logger.info(
                "compute_options_features spot_missing — no price_bar for "
                "{} (moneyness/ATM/strike-distance will be NULL)", sym,
            )
        try:
            summary = compute_features_for(
                underlying=sym, as_of_date=as_of, spot=spot,
            )
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
        "no_quotes={} spot_missing={} errors={} status={}",
        as_of, upserted, no_quotes, spot_missing, errors, status,
    )
    return {
        "status": status,
        "as_of": as_of.isoformat(),
        "upserted": upserted,
        "no_quotes": no_quotes,
        "spot_missing": spot_missing,
        "errors": errors,
    }
