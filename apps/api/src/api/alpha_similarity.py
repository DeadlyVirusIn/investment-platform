"""SYSTEM-ALPHA-8 similarity API — preview + recent + coverage."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.alpha.similarity import (
    LOOKBACK_DAYS, MIN_NEIGHBORS, TOP_K,
    build_current_vector, compute_similarity_multiplier,
    evaluate_similarity, invalidate_cache, load_historical,
)
from apps.api.src.db import SessionLocal

router = APIRouter(prefix="/alpha/similarity", tags=["alpha-similarity"])


def _s() -> Session:
    return SessionLocal()


@router.get("/coverage")
async def coverage(lookback_days: int = LOOKBACK_DAYS) -> dict[str, Any]:
    """Historical labeled sample size + regime/engine breakdown."""
    with _s() as s:
        pts = load_historical(s, lookback_days=lookback_days, force=True)
    by_engine: dict[str, int] = {}
    by_exploratory = {"true": 0, "false": 0}
    for p in pts:
        by_engine[p.engine] = by_engine.get(p.engine, 0) + 1
        by_exploratory["true" if p.exploratory else "false"] += 1
    return {
        "lookback_days": int(lookback_days),
        "total": len(pts),
        "min_neighbors_required": MIN_NEIGHBORS,
        "ready": len(pts) >= MIN_NEIGHBORS,
        "by_engine": by_engine,
        "by_exploratory": by_exploratory,
    }


@router.post("/preview")
async def preview(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Preview similarity lookup for an ad-hoc context."""
    regime = str(body.get("regime") or "neutral").lower()
    engine = str(body.get("engine") or "NONE").upper()
    exploratory = bool(body.get("exploratory") or False)
    gates_passed = body.get("gates_passed")
    try:
        gates_passed_i = (
            int(gates_passed) if gates_passed is not None else None
        )
    except (TypeError, ValueError):
        gates_passed_i = None
    ctx_vals = body.get("context_values") or {}
    catalyst = body.get("catalyst") or {}
    data_quality = body.get("data_quality") or {}
    with _s() as s:
        res = compute_similarity_multiplier(
            s,
            regime=regime, engine=engine, exploratory=exploratory,
            gates_passed=gates_passed_i, context_values=ctx_vals,
            catalyst=catalyst, data_quality=data_quality,
        )
    vec = build_current_vector(
        regime=regime, engine=engine, exploratory=exploratory,
        gates_passed=gates_passed_i, context_values=ctx_vals,
        catalyst=catalyst, data_quality=data_quality,
    )
    return {"input_vector": vec, **res.to_dict()}


@router.get("/recent")
async def recent(limit: int = 50) -> dict[str, Any]:
    """Last N paper entries where similarity was evaluated."""
    with _s() as s:
        rows = s.execute(text("""
            SELECT id::text AS trade_id, entry_date, instrument, engine,
                   regime_at_entry, status, net_ret_pct,
                   alpha_rule_snapshot->'similarity'           AS similarity,
                   alpha_rule_snapshot->>'similarity_matched'  AS matched_s,
                   alpha_rule_snapshot->>'similarity_multiplier' AS mult_s,
                   alpha_rule_snapshot->>'paper_size_multiplier' AS psize_s
            FROM paper_trade_log
            WHERE alpha_rule_snapshot ? 'similarity'
            ORDER BY entry_date DESC, id DESC
            LIMIT :l
        """), {"l": int(limit)}).mappings().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        sim = r.get("similarity") or {}
        if not isinstance(sim, dict):
            sim = {}
        try:
            mult = float(r.get("mult_s") or sim.get("multiplier") or 1.0)
        except (TypeError, ValueError):
            mult = 1.0
        try:
            psize = float(r.get("psize_s") or 0.0)
        except (TypeError, ValueError):
            psize = 0.0
        out.append({
            "trade_id": r["trade_id"],
            "entry_date": str(r.get("entry_date")),
            "instrument": r.get("instrument"),
            "engine": r.get("engine"),
            "regime_at_entry": r.get("regime_at_entry"),
            "status": r.get("status"),
            "net_ret_pct": (
                float(r["net_ret_pct"])
                if r.get("net_ret_pct") is not None else None
            ),
            "matched": str(r.get("matched_s") or "").lower() == "true"
                        or bool(sim.get("matched")),
            "multiplier": mult,
            "paper_size_multiplier": psize,
            "n_neighbors": int(sim.get("n_neighbors") or 0),
            "avg_return_pct": float(sim.get("avg_return_pct") or 0.0),
            "win_rate": float(sim.get("win_rate") or 0.0),
            "reason": sim.get("reason") or "",
        })
    return {"count": len(out), "rows": out,
            "top_k": TOP_K, "min_neighbors": MIN_NEIGHBORS}


@router.post("/refresh")
async def refresh() -> dict[str, Any]:
    """Invalidate in-process historical cache; next call rebuilds."""
    invalidate_cache()
    return {"ok": True}
