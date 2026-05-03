"""Nightly Hybrid Performance Monitor.

Usage:
    python -m apps.api.src.jobs.ml_hybrid_monitor_nightly

Computes 7/14/30-day hybrid performance metrics, runs promotion guard,
persists one snapshot per window. Never changes trading mode.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from loguru import logger

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.ml.shadow.hybrid_monitor import (
    compute_window_performance, persist_snapshot,
)
from apps.api.src.ml.shadow.promotion_guard import (
    PromotionThresholds, evaluate_promotion,
)
from sqlalchemy import text


DEFAULT_WINDOWS = (7, 14, 30)


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Nightly hybrid monitor.")
    p.add_argument("--no-persist", action="store_true")
    p.add_argument("--as-of", default=None,
                    help="YYYY-MM-DD (default: today UTC)")
    p.add_argument("--windows", default="7,14,30")
    return p.parse_args()


def _load_recent_snapshots_for_state(
    session, *, window_days: int, limit: int = 14,
) -> list[dict]:
    rows = session.execute(text("""
        SELECT as_of_date, window_days, calibration_ece,
               delta_sharpe_vs_deterministic, false_avoid_rate,
               missed_winner_rate, ml_advice_count,
               deterministic_trades, model_status
        FROM ml_hybrid_performance_snapshot
        WHERE window_days = :w
        ORDER BY as_of_date DESC
        LIMIT :l
    """), {"w": int(window_days), "l": int(limit)}).mappings().all()
    return [dict(r) for r in rows]


def main() -> int:
    args = _parse()
    windows = tuple(
        int(x.strip()) for x in args.windows.split(",") if x.strip()
    ) or DEFAULT_WINDOWS
    as_of = (
        dt.date.fromisoformat(args.as_of)
        if args.as_of else dt.date.today()
    )
    mode = str(getattr(settings, "ML_HYBRID_MODE", "advisory"))
    th = PromotionThresholds.from_settings(settings)

    results: dict[int, dict] = {}
    with SessionLocal() as s:
        for w in windows:
            r = compute_window_performance(
                s, as_of=as_of, window_days=w, mode=mode,
            )
            results[w] = r.to_dict()
            # Need predictions to evaluate
            has_preds = r.ml_advice_count > 0
            # Recent 7d snapshot history → consecutive-healthy-days count
            recent = _load_recent_snapshots_for_state(
                s, window_days=7, limit=th.required_healthy_days * 2,
            )
            decision = evaluate_promotion(
                current_mode=mode,
                window_results=results,
                recent_snapshots=recent,
                thresholds=th,
                has_ml_predictions=has_preds,
            )
            if not args.no_persist:
                try:
                    persist_snapshot(
                        s, result=r, promotion_status=decision.state,
                    )
                except Exception as e:
                    logger.warning("persist_snapshot {}d failed: {}", w, e)
            logger.info(
                "hybrid monitor {}d: advice={} outcomes={} state={} "
                "rec={}", w, r.ml_advice_count, r.deterministic_trades,
                decision.state, decision.recommendation,
            )

    logger.info("hybrid monitor done; mode stays '{}'. No auto flip.", mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
