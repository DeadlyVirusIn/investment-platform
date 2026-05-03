"""SYSTEM-ALPHA analytics + system-health + trade-replay endpoints.

All read-only. No execution impact.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db import SessionLocal
from apps.api.src.alpha import (
    analyze_signals, build_catalyst_analytics, classify_failure,
    compute_entry_quality, compute_system_health,
    compute_portfolio_risk,
)
from apps.api.src.alpha.coverage_report import build_coverage_report
from apps.api.src.ml.dataset import build_dataset

router = APIRouter(prefix="/analytics", tags=["analytics"])
health_router = APIRouter(prefix="/system", tags=["system"])
replay_router = APIRouter(prefix="/trades", tags=["trade-replay"])


def _s() -> Session:
    return SessionLocal()


# ---------------------------------------------------------------------------
# analytics
# ---------------------------------------------------------------------------

@router.get("/performance/by-symbol")
async def by_symbol(limit: int = 50) -> dict[str, Any]:
    with _s() as s:
        rows = s.execute(text("""
            SELECT instrument AS symbol,
                   COUNT(*) AS n,
                   AVG(net_ret_pct) AS mean_ret,
                   SUM(CASE WHEN net_ret_pct > 0 THEN 1 ELSE 0 END) AS wins
            FROM paper_trade_log
            WHERE status='closed' AND net_ret_pct IS NOT NULL
            GROUP BY instrument
            ORDER BY n DESC
            LIMIT :l
        """), {"l": int(limit)}).mappings().all()
    return {"count": len(rows), "rows": [dict(r) for r in rows]}


@router.get("/performance/by-regime")
async def by_regime() -> dict[str, Any]:
    with _s() as s:
        rows = s.execute(text("""
            SELECT regime_at_entry AS regime,
                   COUNT(*) AS n,
                   AVG(net_ret_pct) AS mean_ret,
                   SUM(CASE WHEN net_ret_pct > 0 THEN 1 ELSE 0 END) AS wins
            FROM paper_trade_log
            WHERE status='closed' AND net_ret_pct IS NOT NULL
            GROUP BY regime_at_entry
            ORDER BY n DESC
        """)).mappings().all()
    return {"count": len(rows), "rows": [dict(r) for r in rows]}


@router.get("/performance/by-catalyst")
async def by_catalyst() -> dict[str, Any]:
    with _s() as s:
        ds = build_dataset(s)
    ca = build_catalyst_analytics(ds.df)
    return ca.to_dict()


@router.get("/performance/by-confidence")
async def by_confidence() -> dict[str, Any]:
    with _s() as s:
        ds = build_dataset(s)
    if ds.empty():
        return {"rows": [], "reason": "no data"}
    df = ds.df
    bins = [(-0.01, 0.3), (0.3, 0.6), (0.6, 0.85), (0.85, 1.01)]
    labels = ["low", "mid_low", "mid_high", "high"]
    rows = []
    for (lo, hi), lab in zip(bins, labels):
        mask = df["feature_confidence"].between(lo, hi, inclusive="left")
        sub = df.loc[mask, "fwd_ret_5d"].dropna()
        rows.append({
            "bucket": lab, "n": int(len(sub)),
            "mean_ret": float(sub.mean()) if not sub.empty else 0.0,
            "hit_rate": float((sub > 0).mean()) if not sub.empty else 0.0,
        })
    return {"rows": rows}


@router.get("/trades/distribution")
async def trade_distribution() -> dict[str, Any]:
    with _s() as s:
        winners = s.execute(text("""
            SELECT id::text AS id, instrument, entry_date, net_ret_pct
            FROM paper_trade_log
            WHERE status='closed' AND net_ret_pct > 0
            ORDER BY net_ret_pct DESC LIMIT 10
        """)).mappings().all()
        losers = s.execute(text("""
            SELECT id::text AS id, instrument, entry_date, net_ret_pct
            FROM paper_trade_log
            WHERE status='closed' AND net_ret_pct < 0
            ORDER BY net_ret_pct ASC LIMIT 10
        """)).mappings().all()
    return {
        "top_winners": [dict(r) for r in winners],
        "top_losers":  [dict(r) for r in losers],
    }


@router.get("/failures")
async def failures(limit: int = 50) -> dict[str, Any]:
    with _s() as s:
        rows = s.execute(text("""
            SELECT id::text AS id, instrument, entry_date,
                   net_ret_pct, failure_analysis
            FROM paper_trade_log
            WHERE status='closed' AND net_ret_pct < 0
              AND failure_analysis IS NOT NULL
            ORDER BY entry_date DESC
            LIMIT :l
        """), {"l": int(limit)}).mappings().all()
    return {"count": len(rows), "rows": [dict(r) for r in rows]}


@router.get("/execution-quality")
async def execution_quality(limit: int = 50) -> dict[str, Any]:
    with _s() as s:
        rows = s.execute(text("""
            SELECT id::text AS id, instrument, entry_date,
                   execution_quality
            FROM paper_trade_log
            WHERE execution_quality IS NOT NULL
            ORDER BY entry_date DESC
            LIMIT :l
        """), {"l": int(limit)}).mappings().all()
    return {"count": len(rows), "rows": [dict(r) for r in rows]}


@router.get("/exits/research")
async def exits_research() -> dict[str, Any]:
    # Wiring note: heavy — invokes simulate_exits across closed trades with
    # forward bars. Gated behind dataset readiness; returns placeholder
    # until a nightly job persists the result.
    return {
        "status": "not_precomputed",
        "hint": ("run `python -m apps.api.src.jobs.alpha_nightly` to "
                 "persist exit research; API currently read-only"),
    }


@router.get("/signal-insights")
async def signal_insights() -> dict[str, Any]:
    with _s() as s:
        ds = build_dataset(s)
    if ds.empty():
        return {"n_rows": 0, "reason": "no data"}
    return analyze_signals(ds.df).to_dict()


# ---------------------------------------------------------------------------
# System health
# ---------------------------------------------------------------------------

@health_router.get("/alpha-coverage")
async def alpha_coverage() -> dict[str, Any]:
    """Validation — how much intelligence data is populated."""
    with _s() as s:
        return build_coverage_report(s).to_dict()


@health_router.get("/health-score")
async def system_health_score() -> dict[str, Any]:
    with _s() as s:
        # Try persisted value first
        row = s.execute(text("""
            SELECT overall, components, recommendation, warnings, created_at
            FROM system_health_score
            ORDER BY created_at DESC
            LIMIT 1
        """)).mappings().first()
    if row:
        return {"present": True, **dict(row)}
    # Compute on-the-fly with neutral inputs
    score = compute_system_health()
    return {"present": False, "computed": score.to_dict()}


# ---------------------------------------------------------------------------
# Trade replay
# ---------------------------------------------------------------------------

@replay_router.get("/{trade_id}/replay")
async def trade_replay(trade_id: str) -> dict[str, Any]:
    with _s() as s:
        trade = s.execute(text("""
            SELECT id::text AS id, instrument, engine, entry_date,
                   exit_date, entry_price, exit_price, status,
                   net_ret_pct, gross_ret_pct, regime_at_entry,
                   (COALESCE(exit_date, CURRENT_DATE) - entry_date)
                       AS days_held,
                   reason, catalyst_snapshot,
                   data_confidence, near_earnings,
                   failure_analysis, execution_quality
            FROM paper_trade_log
            WHERE id = :id
        """), {"id": trade_id}).mappings().first()
        if trade is None:
            raise HTTPException(status_code=404, detail="trade not found")
        decision = s.execute(text("""
            SELECT id::text AS id, as_of_date, engine, action, reason,
                   inputs_used, context_values, feature_confidence,
                   factor_attribution, catalyst, data_quality,
                   missing_features, ml_advisory
            FROM decision_log
            WHERE instrument = :sym AND as_of_date = :asof
            LIMIT 1
        """), {
            "sym": trade["instrument"], "asof": trade["entry_date"],
        }).mappings().first()
        shadow = s.execute(text("""
            SELECT id::text AS id, ml_score, ml_confidence, ml_action,
                   ml_reason_codes, evaluation
            FROM ml_shadow_prediction
            WHERE symbol = :sym AND as_of_date = :asof
            ORDER BY created_at DESC LIMIT 1
        """), {
            "sym": trade["instrument"], "asof": trade["entry_date"],
        }).mappings().first()
    return {
        "trade": dict(trade),
        "decision": dict(decision) if decision else None,
        "ml_shadow": dict(shadow) if shadow else None,
    }
