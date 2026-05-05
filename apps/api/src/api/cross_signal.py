"""Cross-signal stock<->options analytics endpoints (read-only)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.src.db import get_session


router = APIRouter(
    prefix="/performance/cross-signal",
    tags=["performance", "cross-signal"],
)


@router.get("/strategy-map")
def strategy_map(
    db: Session = Depends(get_session),
    as_of_from: str | None = Query(
        None, description="ISO date inclusive. Default: 90 days back.",
    ),
    as_of_to: str | None = Query(
        None, description="ISO date inclusive. Default: today UTC.",
    ),
    horizon: str = Query(
        "5D",
        description="One of 1D / 3D / 5D / 10D / 20D.",
    ),
) -> dict[str, Any]:
    from apps.api.src.domain.cross_signal import build_strategy_map
    today = dt.datetime.now(dt.timezone.utc).date()
    a = (
        dt.date.fromisoformat(as_of_from) if as_of_from
        else today - dt.timedelta(days=90)
    )
    b = (
        dt.date.fromisoformat(as_of_to) if as_of_to else today
    )
    if horizon not in ("1D", "3D", "5D", "10D", "20D"):
        return {
            "error":
                "horizon must be one of 1D/3D/5D/10D/20D",
        }
    if a > b:
        return {"error": "as_of_from must be <= as_of_to"}

    items = build_strategy_map(
        db, as_of_from=a, as_of_to=b, horizon=horizon,
    )
    return {
        "horizon": horizon,
        "date_range": {"from": a.isoformat(), "to": b.isoformat()},
        "count": len(items),
        "items": items,
        "vocab": {
            "score_buckets": [
                "strong_buy", "moderate_buy", "neutral",
                "moderate_sell", "strong_sell",
            ],
            "gate_buckets": [
                "strict_pass", "soft_gate_relaxed",
                "hard_blocked", "data_blocked",
            ],
            "trend_buckets": ["uptrend", "sideways", "downtrend"],
            "iv_buckets": [
                "low_iv", "medium_iv", "high_iv", "unknown_iv",
            ],
            "strategy_buckets": [
                "stock_only", "long_call", "bull_call_spread",
                "long_put", "bear_put_spread", "credit_spread",
                "iron_condor",
            ],
        },
        "thresholds": {
            "edge_prefer_pct": 0.005,
            "stock_good_pct": 0.02,
            "stock_bad_pct": -0.02,
            "confidence_medium_min_n": 20,
            "confidence_high_min_n": 50,
        },
        "notice": (
            "Read-only analytics. NEVER affects execution. ML cannot "
            "act on this surface — `ML_CAN_AFFECT_TRADES=false` is "
            "preserved. Promotion + dynamic-sizing flags remain "
            "default off. Forward returns are computed from "
            "`price_bar` for stocks and `options_strategy_outcome` "
            "for options — no fabricated values."
        ),
    }


@router.get("/today")
def today_assistant(
    db: Session = Depends(get_session),
    as_of: str | None = Query(
        None, description="ISO date. Defaults to today UTC.",
    ),
    lookback_days: int = Query(90, ge=14, le=365),
    limit: int = Query(25, ge=1, le=100),
) -> dict[str, Any]:
    from apps.api.src.domain.cross_signal import build_today_assistant
    today = dt.datetime.now(dt.timezone.utc).date()
    target = dt.date.fromisoformat(as_of) if as_of else today
    items = build_today_assistant(
        db, as_of=target, lookback_days=lookback_days, limit=limit,
    )
    return {
        "as_of_date": target.isoformat(),
        "lookback_days": lookback_days,
        "count": len(items),
        "items": items,
        "notice": (
            "Decision hints only. Stock + options execution paths are "
            "untouched. To act on a hint, the operator runs the "
            "existing exec scripts; no auto-routing."
        ),
    }
