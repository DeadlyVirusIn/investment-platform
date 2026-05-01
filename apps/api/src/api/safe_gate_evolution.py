"""Phase 11X — safe gate-evolution shadow read-only API.

GET-only endpoints exposing the diagnostic. NEVER mutates any
table. NEVER returns execution-actionable language; rows are
labeled "Shadow note" and clearly state `would_trade` semantics.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db import get_session


router = APIRouter(
    prefix="/safe-gate-evolution", tags=["safe-gate-evolution"],
)


SHADOW_NOTICE = (
    "Shadow note — diagnostic only. Hypothetical pilot evaluation "
    "of partial macro alignment; never opens real or paper positions."
)


@router.get("/summary")
def summary(
    start: dt.date | None = Query(default=None),
    end: dt.date | None = Query(default=None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Aggregate counts + score distribution. Read-only.

    Defaults to lifetime if start/end omitted."""
    where_parts = []
    params: dict[str, Any] = {}
    if start is not None:
        where_parts.append("run_date >= :start")
        params["start"] = start
    if end is not None:
        where_parts.append("run_date <= :end")
        params["end"] = end
    where_sql = (
        ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    )

    rows = session.execute(text(
        f"""
        SELECT
          COUNT(*)                                            AS days_evaluated,
          COUNT(*) FILTER (WHERE would_trade = FALSE)         AS days_production_flat,
          COUNT(*) FILTER (WHERE would_trade = TRUE)          AS days_shadow_eligible,
          COUNT(*) FILTER (WHERE shadow_reason='macro_favorable_count_zero')
                                                              AS days_zero_favorable,
          COUNT(*) FILTER (WHERE shadow_reason='production_trade_opened')
                                                              AS days_production_traded,
          AVG(macro_favorable_count)::numeric(6,3)            AS avg_favorable,
          AVG(composite_score) FILTER (WHERE would_trade = TRUE)
                                                              AS avg_eligible_score,
          MIN(composite_score) FILTER (WHERE would_trade = TRUE)
                                                              AS min_eligible_score,
          MAX(composite_score) FILTER (WHERE would_trade = TRUE)
                                                              AS max_eligible_score
        FROM safe_gate_evolution_shadow
        {where_sql}
        """
    ), params).mappings().first()

    top_symbols = session.execute(text(
        f"""
        SELECT symbol, COUNT(*) AS n,
               AVG(composite_score)::numeric(20,6) AS avg_score
        FROM safe_gate_evolution_shadow
        {where_sql}
          {"AND" if where_sql else "WHERE"} would_trade = TRUE
          AND symbol IS NOT NULL
        GROUP BY symbol
        ORDER BY n DESC, avg_score DESC
        LIMIT 10
        """
    ), params).mappings().all()

    blocked = session.execute(text(
        f"""
        SELECT shadow_reason, COUNT(*) AS n
        FROM safe_gate_evolution_shadow
        {where_sql}
          {"AND" if where_sql else "WHERE"} would_trade = FALSE
        GROUP BY shadow_reason
        ORDER BY n DESC
        """
    ), params).mappings().all()

    favorable_dist = session.execute(text(
        f"""
        SELECT macro_favorable_count AS bucket, COUNT(*) AS n
        FROM safe_gate_evolution_shadow
        {where_sql}
        GROUP BY macro_favorable_count
        ORDER BY macro_favorable_count
        """
    ), params).mappings().all()

    base = dict(rows) if rows else {}
    return {
        "notice": SHADOW_NOTICE,
        "window": {
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
        },
        "counts": {
            "days_evaluated": int(base.get("days_evaluated") or 0),
            "days_production_flat": int(
                base.get("days_production_flat") or 0
            ),
            "days_shadow_eligible": int(
                base.get("days_shadow_eligible") or 0
            ),
            "days_zero_favorable": int(
                base.get("days_zero_favorable") or 0
            ),
            "days_production_traded": int(
                base.get("days_production_traded") or 0
            ),
        },
        "favorable_distribution": [
            {"favorable_count": int(r["bucket"]), "n": int(r["n"])}
            for r in favorable_dist
        ],
        "score_distribution_eligible": {
            "avg": (
                float(base["avg_eligible_score"])
                if base.get("avg_eligible_score") is not None else None
            ),
            "min": (
                float(base["min_eligible_score"])
                if base.get("min_eligible_score") is not None else None
            ),
            "max": (
                float(base["max_eligible_score"])
                if base.get("max_eligible_score") is not None else None
            ),
        },
        "top_symbols": [
            {
                "symbol": r["symbol"],
                "n": int(r["n"]),
                "avg_score": float(r["avg_score"]),
            }
            for r in top_symbols
        ],
        "blocked_reasons": [
            {"shadow_reason": r["shadow_reason"], "n": int(r["n"])}
            for r in blocked
        ],
    }


@router.get("/runs")
def list_runs(
    start: dt.date | None = Query(default=None),
    end: dt.date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    where_parts = []
    params: dict[str, Any] = {"lim": limit}
    if start is not None:
        where_parts.append("run_date >= :start")
        params["start"] = start
    if end is not None:
        where_parts.append("run_date <= :end")
        params["end"] = end
    where_sql = (
        ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    )
    rows = session.execute(text(
        f"""
        SELECT id, run_date, symbol, side, composite_score, confidence,
               macro_favorable_count, failed_macro_gates, price_regime,
               original_selector_reason, shadow_reason,
               hypothetical_size_multiplier, would_trade, created_at
        FROM safe_gate_evolution_shadow
        {where_sql}
        ORDER BY run_date DESC
        LIMIT :lim
        """
    ), params).mappings().all()
    return {
        "notice": SHADOW_NOTICE,
        "count": len(rows),
        "rows": [
            {
                "id": str(r["id"]),
                "run_date": r["run_date"].isoformat(),
                "symbol": r["symbol"],
                "side": r["side"],
                "composite_score": (
                    float(r["composite_score"])
                    if r["composite_score"] is not None else None
                ),
                "confidence": (
                    float(r["confidence"])
                    if r["confidence"] is not None else None
                ),
                "macro_favorable_count": int(r["macro_favorable_count"]),
                "failed_macro_gates": r["failed_macro_gates"],
                "price_regime": r["price_regime"],
                "original_selector_reason": r["original_selector_reason"],
                "shadow_reason": r["shadow_reason"],
                "hypothetical_size_multiplier": float(
                    r["hypothetical_size_multiplier"]
                ),
                "would_trade": bool(r["would_trade"]),
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ],
    }
