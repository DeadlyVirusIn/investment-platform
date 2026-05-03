"""Alpha rules API — suggestions + apply + rollback + threshold recs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.alpha.adaptive_thresholds import recommend_thresholds
from apps.api.src.alpha.rule_analyzer import analyze_rules
from apps.api.src.alpha.rule_executor import (
    apply_rule, ignore_suggestion, persist_suggestions, rollback_rule,
)
from apps.api.src.alpha.rule_impact import compute_rule_impact
from apps.api.src.alpha.rule_refresh import (
    dedupe_existing_rule_ids, refresh_allowed,
)
from apps.api.src.alpha.rule_runtime import load_active_rules
from apps.api.src.alpha.rule_suggestions import generate_suggestions
from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.ml.dataset import build_dataset

router = APIRouter(prefix="/alpha/rules", tags=["alpha-rules"])
thresholds_router = APIRouter(prefix="/alpha/thresholds",
                                tags=["alpha-thresholds"])


def _s() -> Session:
    return SessionLocal()


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

@router.get("/suggestions")
async def list_suggestions(
    status: str = "pending", limit: int = 50,
) -> dict[str, Any]:
    with _s() as s:
        rows = s.execute(text("""
            SELECT id::text AS id, rule_id, rule_type, target, description,
                   confidence, sample_size, expected_impact, risk_level,
                   auto_applicable, parameters, status, created_at
            FROM alpha_rule_suggestion
            WHERE status = :st
            ORDER BY created_at DESC
            LIMIT :l
        """), {"st": status, "l": int(limit)}).mappings().all()
    return {"count": len(rows), "suggestions": [dict(r) for r in rows]}


@router.get("/active")
async def list_active() -> dict[str, Any]:
    with _s() as s:
        rows = s.execute(text("""
            SELECT rule_id, rule_type, parameters, previous_parameters,
                   applied_at, applied_by, status
            FROM alpha_rule_active
            WHERE status = 'active'
            ORDER BY applied_at DESC
        """)).mappings().all()
    return {"count": len(rows), "rules": [dict(r) for r in rows]}


@router.post("/apply")
async def apply_endpoint(
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    suggestion_id = str(body.get("suggestion_id") or "")
    if not suggestion_id:
        raise HTTPException(400, "suggestion_id required")
    applied_by = str(body.get("applied_by") or "operator")
    force = bool(body.get("force_manual", False))
    with _s() as s:
        r = apply_rule(s, suggestion_id,
                        applied_by=applied_by, force_manual=force)
    if not r.ok:
        raise HTTPException(400, r.reason)
    return r.to_dict()


@router.post("/ignore")
async def ignore_endpoint(
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    suggestion_id = str(body.get("suggestion_id") or "")
    reason = str(body.get("reason") or "")
    with _s() as s:
        r = ignore_suggestion(s, suggestion_id, reason=reason)
    return r.to_dict()


@router.post("/rollback")
async def rollback_endpoint(
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    rule_id = str(body.get("rule_id") or "")
    reason = str(body.get("reason") or "")
    if not rule_id:
        raise HTTPException(400, "rule_id required")
    with _s() as s:
        r = rollback_rule(s, rule_id, reason=reason)
    if not r.ok:
        raise HTTPException(400, r.reason)
    return r.to_dict()


@router.post("/refresh")
async def refresh_suggestions(force: bool = False) -> dict[str, Any]:
    """Rerun analyzer → generator → persist. Rate-limited + deduped."""
    cooldown = int(
        getattr(settings, "ALPHA_RULE_REFRESH_COOLDOWN_HOURS", 24),
    )
    dedupe_days = int(
        getattr(settings, "ALPHA_RULE_DEDUPE_DAYS", 7),
    )
    with _s() as s:
        ok, reason = refresh_allowed(s, cooldown_hours=cooldown, force=force)
        if not ok:
            raise HTTPException(429, detail=reason)
        ds = build_dataset(s)
        findings = analyze_rules(ds.df)
        sugs = generate_suggestions(findings)
        dup = dedupe_existing_rule_ids(
            s, [sg.rule_id for sg in sugs], within_days=dedupe_days,
        )
        sugs_new = [sg for sg in sugs if sg.rule_id not in dup]
        n = persist_suggestions(s, sugs_new, dry_run=False)
    return {
        "findings": len(findings),
        "suggestions_persisted": n,
        "skipped_duplicates": len(sugs) - len(sugs_new),
        "force": force,
        "cooldown_status": reason,
        "suggestion_ids": [x.id for x in sugs_new],
    }


@router.get("/runtime")
async def runtime_rules() -> dict[str, Any]:
    """Current rules as seen by the paper policy engine (post-validation)."""
    with _s() as s:
        rules = load_active_rules(s, force_refresh=True)
    return {
        "mode": getattr(settings, "ALPHA_RULES_MODE", "advisory"),
        "enabled": bool(getattr(settings, "ALPHA_RULES_ENABLED", True)),
        "allow_block": bool(
            getattr(settings, "ALPHA_RULE_ALLOW_BLOCK", False),
        ),
        "min_size_multiplier": float(
            getattr(settings, "ALPHA_RULE_MIN_SIZE_MULTIPLIER", 0.5),
        ),
        "count": len(rules),
        "rules": [r.to_dict() for r in rules],
    }


@router.get("/audit")
async def audit(
    rule_id: str | None = None,
    symbol: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    sql = """
        SELECT id::text AS decision_id, as_of_date, instrument AS symbol,
               engine, action, alpha_rules_mode,
               alpha_rule_size_multiplier, alpha_rule_blocked,
               alpha_rule_block_reason, alpha_rule_adjustment
        FROM decision_log
        WHERE alpha_rule_adjustment IS NOT NULL
    """
    params: dict[str, Any] = {"lim": int(limit)}
    if rule_id:
        sql += (" AND alpha_rule_adjustment ->> 'applied_rules' "
                "LIKE :pat")
        params["pat"] = f"%{rule_id}%"
    if symbol:
        sql += " AND instrument = :sym"
        params["sym"] = symbol.upper()
    sql += " ORDER BY decision_ts DESC LIMIT :lim"
    with _s() as s:
        rows = s.execute(text(sql), params).mappings().all()
    return {"count": len(rows), "rows": [dict(r) for r in rows]}


@router.get("/performance")
async def performance(rule_id: str | None = None,
                        limit: int = 30) -> dict[str, Any]:
    params: dict[str, Any] = {"lim": int(limit)}
    where = ""
    if rule_id:
        where = "WHERE rule_id = :r"
        params["r"] = rule_id
    with _s() as s:
        rows = s.execute(text(f"""
            SELECT id::text AS id, rule_id, window_start, window_end,
                   before, after, delta, created_at
            FROM rule_performance_log
            {where}
            ORDER BY created_at DESC
            LIMIT :lim
        """), params).mappings().all()
    return {"count": len(rows), "rows": [dict(r) for r in rows]}


@router.post("/impact/compute")
async def impact_compute() -> dict[str, Any]:
    with _s() as s:
        metrics = compute_rule_impact(s, persist=True)
    return {"count": len(metrics),
            "metrics": [m.to_dict() for m in metrics]}


@router.post("/pause")
async def pause_rule(
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    rule_id = str(body.get("rule_id") or "")
    if not rule_id:
        raise HTTPException(400, "rule_id required")
    reason = str(body.get("reason") or "manual pause")
    with _s() as s:
        res = s.execute(text("""
            UPDATE alpha_rule_active
               SET status = 'paused', applied_at = NOW()
             WHERE rule_id = :r AND status = 'active'
            RETURNING rule_id
        """), {"r": rule_id}).fetchone()
        if res is None:
            raise HTTPException(404, "rule not active")
        s.execute(text("""
            INSERT INTO alpha_rule_history
              (rule_id, action, applied_by, reason, status)
            VALUES (:r, 'pause', 'operator', :rea, 'paused')
        """), {"r": rule_id, "rea": reason})
        s.commit()
    return {"ok": True, "rule_id": rule_id, "status": "paused"}


@router.post("/resume")
async def resume_rule(
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    rule_id = str(body.get("rule_id") or "")
    if not rule_id:
        raise HTTPException(400, "rule_id required")
    with _s() as s:
        res = s.execute(text("""
            UPDATE alpha_rule_active
               SET status = 'active', applied_at = NOW()
             WHERE rule_id = :r AND status = 'paused'
            RETURNING rule_id
        """), {"r": rule_id}).fetchone()
        if res is None:
            raise HTTPException(404, "rule not paused")
        s.execute(text("""
            INSERT INTO alpha_rule_history
              (rule_id, action, applied_by, reason, status)
            VALUES (:r, 'resume', 'operator', 'manual resume', 'active')
        """), {"r": rule_id})
        s.commit()
    return {"ok": True, "rule_id": rule_id, "status": "active"}


@router.get("/history")
async def list_history(limit: int = 100) -> dict[str, Any]:
    with _s() as s:
        rows = s.execute(text("""
            SELECT id::text AS id, rule_id, action, parameters,
                   previous_parameters, applied_by, reason,
                   status, applied_at
            FROM alpha_rule_history
            ORDER BY applied_at DESC
            LIMIT :l
        """), {"l": int(limit)}).mappings().all()
    return {"count": len(rows), "history": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

@thresholds_router.get("")
async def list_thresholds() -> dict[str, Any]:
    """Return current threshold state (read from config/defaults)."""
    from apps.api.src.config import settings
    return {
        "min_data_confidence": 0.6,
        "max_event_risk":      0.7,
        "min_gates_favorable": 1,
        "paper_slippage_bps":
            float(getattr(settings, "PAPER_SLIPPAGE_BPS", 5.0)),
    }


@thresholds_router.get("/recommendations")
async def threshold_recommendations() -> dict[str, Any]:
    with _s() as s:
        ds = build_dataset(s)
    recs = recommend_thresholds(ds.df)
    return {
        "count": len(recs),
        "recommendations": [r.to_dict() for r in recs],
    }
