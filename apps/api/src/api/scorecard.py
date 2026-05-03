"""Read-only scorecard API — Phase 2."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.db.models import ModelScorecard

router = APIRouter(prefix="/scorecard", tags=["scorecard"])


def _dec(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return str(v)
    return str(v)


def _serialize(row: ModelScorecard) -> dict[str, Any]:
    return {
        "model_name": row.model_name,
        "window_start": row.window_start.isoformat(),
        "window_end": row.window_end.isoformat(),
        "total_signals": row.total_signals,
        "win_rate": _dec(row.win_rate),
        "avg_return": _dec(row.avg_return),
        "avg_drawdown": _dec(row.avg_drawdown),
        "sharpe_like_metric": _dec(row.sharpe_like_metric),
        "evaluation_lag": {
            "avg_days": _dec(row.avg_days_to_evaluation),
            "max_days": row.max_days_to_evaluation,
            "pct_within_horizon": _dec(row.pct_within_horizon),
        },
        "calibration": row.calibration or [],
        "factors": row.factor_effectiveness or [],
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("")
def get_scorecard(
    model: str | None = Query(
        None, description="Filter by model_name. Default: latest window for every model.",
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Return latest scorecard row(s).

    Response shape:
      {
        "overall": <latest scorecard for default model, or first>,
        "models": [ <scorecard per model> ],
        "calibration": [...],
        "factors": [...],
        "evaluation_lag": {...}
      }
    """
    stmt = select(ModelScorecard)
    if model:
        stmt = stmt.where(ModelScorecard.model_name == model)
    # Latest per model: order by window_end desc; Python-side dedup
    stmt = stmt.order_by(
        ModelScorecard.model_name.asc(),
        ModelScorecard.window_end.desc(),
    )
    rows = list(session.scalars(stmt))
    if not rows:
        raise HTTPException(404, detail="no scorecard rows yet")

    by_model: dict[str, ModelScorecard] = {}
    for r in rows:
        if r.model_name not in by_model:
            by_model[r.model_name] = r

    latest_list = list(by_model.values())
    if model:
        if model not in by_model:
            raise HTTPException(404, detail=f"no scorecard for model={model}")
        overall = by_model[model]
    else:
        # Pick lexicographically-first model's latest as "overall" convenience
        overall = latest_list[0]

    serialized = _serialize(overall)
    return {
        "overall": serialized,
        "models": [_serialize(r) for r in latest_list],
        "calibration": serialized["calibration"],
        "factors": serialized["factors"],
        "evaluation_lag": serialized["evaluation_lag"],
    }
