"""Phase B — Options Opportunities HTTP routes.

GET-only surface. All endpoints respect the read-only architectural
lock; nothing mutates engine state. Sourced exclusively from existing
DB tables — no execution calls.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.options.opportunities.service import (
    CONVICTION_FLOOR,
    fetch_opportunities,
    opportunity_to_dict,
)


router = APIRouter(prefix="/options", tags=["options-opportunities"])


LANE_OPTIONS = ("bullish", "bearish", "neutral", "event",
                "developing", "conviction")


@router.get("/opportunities")
def list_opportunities(
    lane: str | None = Query(default=None, description="Filter by lane name."),
    limit: int = Query(default=24, ge=1, le=200),
    lookback_days: int = Query(default=7, ge=1, le=60),
    min_score: float | None = Query(default=None, ge=0.0, le=1.0),
    family: str | None = Query(
        default=None,
        description="Filter by family: engine_executable | research. "
                    "Omitted → both.",
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Ranked opportunity cards.

    Lane filter:
      * `bullish` / `bearish` / `neutral` / `event` / `developing`
      * `conviction` — cross-lane top-N with composite_score >= 0.78
      * omitted — every lane, top-N by composite_score
    """
    if lane is not None and lane.lower() not in LANE_OPTIONS:
        return {
            "lane": lane,
            "count": 0,
            "items": [],
            "error": f"unknown lane '{lane}'. "
                     f"valid: {', '.join(LANE_OPTIONS)}",
        }
    items = fetch_opportunities(
        session,
        lane=lane.lower() if lane else None,
        limit=limit,
        lookback_days=lookback_days,
        min_score=min_score,
        family=family.lower() if family else None,
    )
    dicts = [opportunity_to_dict(i) for i in items]
    return {
        "lane": lane,
        "family": family,
        "count": len(items),
        # Hybrid (Phase 1) — per-family counts for the dual-lane UI.
        "engine_executable_count":
            sum(1 for d in dicts if d["family"] == "engine_executable"),
        "research_count":
            sum(1 for d in dicts if d["family"] == "research"),
        "lookback_days": lookback_days,
        "conviction_floor": CONVICTION_FLOOR,
        "weights": {
            "score": 0.40, "freshness": 0.20,
            "liquidity": 0.15, "iv_fit": 0.15, "event": 0.10,
        },
        "items": dicts,
    }


@router.get("/opportunities/lanes")
def list_lanes(
    limit_per_lane: int = Query(default=6, ge=1, le=24),
    lookback_days: int = Query(default=7, ge=1, le=60),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """One-call composition for the Opportunities page.

    Returns each lane pre-bucketed so the frontend issues one HTTP
    request instead of six. Conviction lane is computed across all
    biases (top composite_score with qualified=true).
    """
    out: dict[str, Any] = {
        "lookback_days": lookback_days,
        "conviction_floor": CONVICTION_FLOOR,
        "lanes": {},
    }
    for lane in LANE_OPTIONS:
        items = fetch_opportunities(
            session, lane=lane, limit=limit_per_lane,
            lookback_days=lookback_days,
        )
        out["lanes"][lane] = {
            "count": len(items),
            "items": [opportunity_to_dict(i) for i in items],
        }
    return out


@router.get("/opportunities/regime")
def opportunity_regime_context(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Top-level regime context displayed above the lanes.

    Reads aggregated IV-rank across the universe + the today shadow
    snapshot for a single-line market read. Honest empty state when
    the feature engine has not yet populated iv_rank values.
    """
    from sqlalchemy import text
    iv_row = session.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE iv_rank_252d IS NOT NULL) AS n,
          AVG(iv_rank_252d) FILTER (WHERE iv_rank_252d IS NOT NULL) AS mean,
          MIN(iv_rank_252d) AS min, MAX(iv_rank_252d) AS max
        FROM options_feature_daily
        WHERE as_of_date >= (CURRENT_DATE - 3)
    """)).mappings().one()
    shadow_row = session.execute(text("""
        SELECT
          MAX(run_date) AS latest_run,
          COUNT(*) FILTER (WHERE would_trade=TRUE
                           AND run_date = (SELECT MAX(run_date) FROM options_shadow_decision_log))
            AS would_trade_today,
          COUNT(*) FILTER (WHERE run_date = (SELECT MAX(run_date) FROM options_shadow_decision_log))
            AS evaluated_today
        FROM options_shadow_decision_log
    """)).mappings().one()
    return {
        "iv_rank": {
            "underlyings_with_data": int(iv_row["n"] or 0),
            "mean": float(iv_row["mean"]) if iv_row["mean"] is not None else None,
            "min":  float(iv_row["min"])  if iv_row["min"]  is not None else None,
            "max":  float(iv_row["max"])  if iv_row["max"]  is not None else None,
        },
        "shadow": {
            "latest_run":         shadow_row["latest_run"].isoformat()
                                   if shadow_row["latest_run"] else None,
            "would_trade_today":  int(shadow_row["would_trade_today"] or 0),
            "evaluated_today":    int(shadow_row["evaluated_today"] or 0),
        },
    }
