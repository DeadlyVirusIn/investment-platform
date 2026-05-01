"""Market-data readiness probe for the daily loop.

Exit codes:
  0 — ready (prior trading day bar exists for primary instrument)
  3 — NOT ready (no bar within the tolerance window)
  1 — unexpected error (DB down etc.) — treated as NOT ready by loop

The loop uses this before calling run_paper_daily. When NOT ready, the
loop marks paper_daily as SKIPPED_MARKET_DATA_NOT_READY and continues
with downstream jobs that are safe to run without a fresh bar
(ml_hybrid_monitor, alpha_calibration …). Never creates trades on its
own; never writes to paper_trade_log.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from loguru import logger
from sqlalchemy import text

from apps.api.src.db import SessionLocal

# Default instrument and tolerance (trading-day-aware via weekday skip).
# Phase 11W incident fix: changed from "ES" (E-mini futures, never
# present in this stock-only universe) to "SPY", which IS in the
# universe. The original "ES" default caused the precheck to silently
# fall through to context_daily, which then pinned target_date to a
# stale macro-backfill date.
DEFAULT_INSTRUMENT = "SPY"
MAX_BAR_AGE_CAL_DAYS = 4   # covers Friday → Monday gap + 1 holiday


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Check whether prior-day market bar exists.",
    )
    p.add_argument("--instrument", default=DEFAULT_INSTRUMENT)
    p.add_argument(
        "--as-of", default=None,
        help="YYYY-MM-DD (default: today local UTC)",
    )
    p.add_argument(
        "--max-age-days", type=int, default=MAX_BAR_AGE_CAL_DAYS,
    )
    return p.parse_args()


def _stage_max_dates(s) -> dict:
    """Pull max(as_of_date) from each pipeline stage for diagnostic
    logging. Read-only."""
    row = s.execute(text(
        """
        SELECT
          (SELECT max(ts)::date FROM price_bar) AS price_bar,
          (SELECT max(as_of_date) FROM context_daily) AS context_daily,
          (SELECT max(as_of_date) FROM regime_snapshot) AS regime,
          (SELECT max(as_of_date) FROM factor_snapshot) AS factor,
          (SELECT max(as_of_date) FROM candidate_idea) AS candidate
        """
    )).mappings().first()
    return {k: (v.isoformat() if v else None) for k, v in (row or {}).items()}


def check_ready(
    *, instrument: str, as_of: dt.date, max_age_days: int,
) -> tuple[bool, dict]:
    """Return (ready, info_dict).

    Phase 11W (incident fix): the precheck now reports per-stage
    max-dates and FAILS if context_daily lags price_bar by more than
    max_age_days. Previously it silently used a stale context_daily
    as latest_bar_date, which caused paper_run_log to upsert the
    same row indefinitely.
    """
    earliest_acceptable = as_of - dt.timedelta(days=int(max_age_days))
    try:
        with SessionLocal() as s:
            stage_dates = _stage_max_dates(s)
            # Latest available bar (price-side) — drives the eligible
            # target trading date.
            price_row = s.execute(text(
                """
                SELECT p.ts::date AS bar_date
                FROM price_bar p
                JOIN asset a ON a.id = p.asset_id
                WHERE a.symbol = :sym
                  AND p.timeframe = '1d'
                  AND p.ts::date <= :asof
                ORDER BY p.ts DESC
                LIMIT 1
                """
            ), {"sym": instrument, "asof": as_of}).mappings().first()
            ctx_row = s.execute(text(
                """
                SELECT MAX(as_of_date) AS bar_date
                FROM context_daily
                WHERE as_of_date <= :asof
                """
            ), {"asof": as_of}).mappings().first()
    except Exception as e:
        return False, {"error": f"db_error:{type(e).__name__}:{e}"}

    info = {
        "instrument": instrument,
        "as_of": as_of.isoformat(),
        "max_age_days": int(max_age_days),
        "latest_price_bar_date": stage_dates.get("price_bar"),
        "latest_context_daily_date": stage_dates.get("context_daily"),
        "latest_regime_date": stage_dates.get("regime"),
        "latest_factor_date": stage_dates.get("factor"),
        "latest_candidate_date": stage_dates.get("candidate"),
    }

    price_date = price_row.get("bar_date") if price_row else None
    ctx_date = ctx_row.get("bar_date") if ctx_row else None

    if price_date is None:
        return False, {**info, "reason": "no_price_bar_found"}

    info["bar_date"] = price_date.isoformat()
    info["age_days"] = int((as_of - price_date).days)

    if price_date < earliest_acceptable:
        return False, {**info, "reason": "bar_too_stale"}

    # Phase 11W — explicit stale-context detection. If price_bar has
    # advanced past the engine pipeline, refuse to mark ready and
    # log which stage is lagging. Caller (run_daily_loop.sh) will
    # report SKIPPED with reason; engine_pipeline runs upstream so
    # this case is rare in practice.
    if ctx_date is None or ctx_date < price_date:
        return False, {
            **info,
            "reason": "macro_context_stale",
            "context_daily_lag_days": (
                int((price_date - ctx_date).days)
                if ctx_date else None
            ),
            "context_daily_max": (
                ctx_date.isoformat() if ctx_date else None
            ),
        }

    return True, info


def main() -> int:
    args = _parse()
    as_of = (
        dt.date.fromisoformat(args.as_of)
        if args.as_of else dt.date.today()
    )
    ready, info = check_ready(
        instrument=args.instrument, as_of=as_of,
        max_age_days=args.max_age_days,
    )
    # Always emit the latest price-bar date into /tmp so the loop can
    # target_date = latest_bar when running paper_daily. Phase 11W
    # incident fix: this now reflects price_bar (the source of truth)
    # rather than context_daily, so a stale macro pipeline can no
    # longer pin target_date to an old day.
    bd = info.get("bar_date")
    if bd:
        try:
            with open("/tmp/latest_bar_date", "w", encoding="utf-8") as f:
                f.write(bd)
        except Exception:
            pass
    # Phase 11W — write a parallel diagnostic file with the per-stage
    # max-dates so operators can debug stale-context issues without
    # opening the database.
    try:
        diag_lines = [
            f"price_bar={info.get('latest_price_bar_date')}",
            f"context_daily={info.get('latest_context_daily_date')}",
            f"regime={info.get('latest_regime_date')}",
            f"factor={info.get('latest_factor_date')}",
            f"candidate={info.get('latest_candidate_date')}",
            f"selected_target_date={info.get('bar_date')}",
            f"reason={info.get('reason') or 'ready'}",
        ]
        with open(
            "/tmp/market_data_diagnostics", "w", encoding="utf-8",
        ) as f:
            f.write("\n".join(diag_lines) + "\n")
    except Exception:
        pass
    if ready:
        logger.info("market data READY {}", info)
        return 0
    if info.get("error"):
        logger.warning("market data check ERROR {}", info)
        return 1
    logger.info("market data NOT READY {}", info)
    return 3


if __name__ == "__main__":
    sys.exit(main())
