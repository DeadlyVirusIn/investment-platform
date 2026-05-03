"""Alpha context-calibration API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.alpha.context_calibration import (
    MIN_MULTIPLIER, apply_context_rec, build_context_performance,
    evaluate_context_calibration, load_active_context_multipliers,
    persist_recommendations, revert_context, ContextKey, ContextRec,
    ContextStats,
)
from apps.api.src.db import SessionLocal

router = APIRouter(prefix="/alpha/context", tags=["alpha-context"])


def _s() -> Session:
    return SessionLocal()


@router.get("/performance")
async def performance(lookback_days: int = 60) -> dict[str, Any]:
    with _s() as s:
        stats = build_context_performance(s, lookback_days=lookback_days)
    return {
        "count": len(stats),
        "buckets": [r.to_dict() for r in stats],
    }


@router.get("/recommendations")
async def recommendations(lookback_days: int = 60) -> dict[str, Any]:
    with _s() as s:
        recs = evaluate_context_calibration(s, lookback_days=lookback_days)
    return {"count": len(recs),
            "recommendations": [r.to_dict() for r in recs]}


@router.get("/active")
async def active() -> dict[str, Any]:
    with _s() as s:
        mp = load_active_context_multipliers(s)
        rows = s.execute(text("""
            SELECT context_key, context, multiplier, reason,
                   confidence, sample_size, applied_at, status
            FROM alpha_context_multiplier
            WHERE status = 'active'
            ORDER BY applied_at DESC
        """)).mappings().all()
    return {"count": len(mp), "rows": [dict(r) for r in rows]}


@router.post("/refresh")
async def refresh(
    auto_apply: bool = False, lookback_days: int = 60,
) -> dict[str, Any]:
    with _s() as s:
        recs = evaluate_context_calibration(s, lookback_days=lookback_days)
        if not recs:
            return {"count": 0, "recommended": 0, "auto_applied": 0}
        out = persist_recommendations(s, recs, auto_apply=auto_apply)
    return {"count": len(recs), **out,
            "items": [r.to_dict() for r in recs]}


@router.post("/apply")
async def apply_endpoint(
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    ctx = body.get("context") or {}
    new_mult = body.get("proposed_multiplier")
    old_mult = body.get("current_multiplier", 1.0)
    if new_mult is None:
        raise HTTPException(400, "proposed_multiplier required")
    if float(new_mult) > float(old_mult):
        raise HTTPException(400,
                              "context multipliers may only decrease")
    if float(new_mult) < MIN_MULTIPLIER:
        raise HTTPException(400,
                              f"multiplier below floor {MIN_MULTIPLIER}")
    try:
        ck = ContextKey(
            engine=str(ctx.get("engine") or "none").upper(),
            regime=str(ctx.get("regime") or "neutral"),
            mode=str(ctx.get("mode") or "strict"),
        )
    except Exception as e:
        raise HTTPException(400, f"bad context: {e}") from e
    rec = ContextRec(
        context=ck,
        current_multiplier=float(old_mult),
        proposed_multiplier=float(new_mult),
        stats=ContextStats(
            context=ck, sample_size=int(body.get("sample_size") or 0),
            win_rate=0.0, avg_return=0.0, median_return=0.0,
            sharpe=0.0, total_return=0.0,
        ),
        reason=str(body.get("reason") or "manual apply"),
        confidence=float(body.get("confidence") or 0.0),
    )
    with _s() as s:
        apply_context_rec(s, rec, applied_by="operator")
        s.commit()
    return {"ok": True, **rec.to_dict()}


@router.post("/revert")
async def revert_endpoint(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    key = str(body.get("context_key") or "")
    reason = str(body.get("reason") or "manual revert")
    if not key:
        raise HTTPException(400, "context_key required")
    with _s() as s:
        ok = revert_context(s, key, reason=reason)
    if not ok:
        raise HTTPException(404, "context not active")
    return {"ok": True, "context_key": key}
