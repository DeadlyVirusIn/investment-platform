"""Alpha calibration API — recommendations + apply + revert."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.alpha.calibration import (
    CalibrationRec, apply_recommendation, evaluate_calibration,
    load_active_params, persist_recommendations, revert_parameter,
)
from apps.api.src.db import SessionLocal

router = APIRouter(prefix="/alpha/calibration",
                     tags=["alpha-calibration"])


def _s() -> Session:
    return SessionLocal()


@router.get("/recommendations")
async def recommendations() -> dict[str, Any]:
    with _s() as s:
        recs = evaluate_calibration(s)
    return {
        "count": len(recs),
        "recommendations": [r.to_dict() for r in recs],
    }


@router.get("/active")
async def active() -> dict[str, Any]:
    with _s() as s:
        return {"parameters": load_active_params(s)}


@router.get("/log")
async def log(limit: int = 100) -> dict[str, Any]:
    with _s() as s:
        rows = s.execute(text("""
            SELECT id::text AS id, parameter_key, action, old_value,
                   new_value, reason, confidence, sample_size,
                   applied_by, auto_applied, status, metrics,
                   created_at
            FROM alpha_calibration_log
            ORDER BY created_at DESC
            LIMIT :l
        """), {"l": int(limit)}).mappings().all()
    return {"count": len(rows), "rows": [dict(r) for r in rows]}


@router.post("/refresh")
async def refresh(auto_apply: bool = False) -> dict[str, Any]:
    """Recompute + persist recommendations. Auto-apply gated."""
    with _s() as s:
        recs = evaluate_calibration(s)
        if not recs:
            return {"count": 0, "recommended": 0, "auto_applied": 0}
        r = persist_recommendations(s, recs, auto_apply=auto_apply)
    return {"count": len(recs), **r,
            "items": [rec.to_dict() for rec in recs]}


@router.post("/apply")
async def apply(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    param = str(body.get("parameter_key") or "")
    new_value = body.get("new_value")
    old_value = body.get("old_value")
    reason = str(body.get("reason") or "manual apply")
    confidence = float(body.get("confidence") or 0.0)
    sample_size = int(body.get("sample_size") or 0)
    if not param or new_value is None:
        raise HTTPException(400,
                              "parameter_key and new_value required")
    # Safety: never allow increasing value when param is a multiplier
    if (old_value is not None
            and "size_multiplier" in param
            and float(new_value) > float(old_value)):
        raise HTTPException(400,
                              "size multipliers may only decrease")
    rec = CalibrationRec(
        parameter_key=param,
        old_value=float(old_value or 0.0),
        new_value=float(new_value),
        reason=reason,
        confidence=confidence,
        sample_size=sample_size,
    )
    with _s() as s:
        apply_recommendation(s, rec, applied_by="operator",
                                mark_auto=False)
        s.commit()
    return {"ok": True, **rec.to_dict()}


@router.post("/revert")
async def revert(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    param = str(body.get("parameter_key") or "")
    reason = str(body.get("reason") or "manual revert")
    if not param:
        raise HTTPException(400, "parameter_key required")
    with _s() as s:
        ok = revert_parameter(s, param, reason=reason)
    if not ok:
        raise HTTPException(404, "parameter not active")
    return {"ok": True, "parameter_key": param}
