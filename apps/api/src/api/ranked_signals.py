"""Phase 1.5 ranked_signals API — read-only with hardened inputs."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.db.models import RankedSignalRow

router = APIRouter(prefix="/ranked-signals", tags=["ranked-signals"])

DEFAULT_LIMIT = 10
MAX_LIMIT = 50


@router.get("")
def list_ranked_signals(
    as_of: str | None = Query(
        None,
        description="ISO date (YYYY-MM-DD); default: latest available day.",
    ),
    limit: int = Query(
        DEFAULT_LIMIT, ge=1, le=MAX_LIMIT,
        description=f"Max rows (1..{MAX_LIMIT}).",
    ),
    strategy_id: str = Query(
        "deterministic_v1",
        min_length=1, max_length=64,
        description="strategy_id to filter on (default deterministic_v1).",
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    # as_of validation
    if as_of is None:
        latest = session.execute(
            select(RankedSignalRow.as_of_date)
            .where(RankedSignalRow.strategy_id == strategy_id)
            .order_by(RankedSignalRow.as_of_date.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest is None:
            raise HTTPException(404, detail="no ranked_signal rows for strategy")
        target = latest
    else:
        try:
            target = dt.date.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(
                400, detail=f"invalid as_of (expect YYYY-MM-DD): {as_of!r}",
            )

    stmt = (
        select(RankedSignalRow)
        .where(
            RankedSignalRow.as_of_date == target,
            RankedSignalRow.strategy_id == strategy_id,
        )
        .order_by(RankedSignalRow.rank_position.asc())
        .limit(limit)
    )
    rows = list(session.scalars(stmt))

    items = []
    for r in rows:
        payload = dict(r.payload or {})
        items.append({
            "symbol": r.symbol,
            "asset_id": r.asset_id,
            "score": float(r.score),
            "rank": int(r.rank_position),
            "strategy_id": r.strategy_id,
            "direction": payload.get("direction"),
            "confidence": payload.get("confidence"),
            "contributing_count": int(r.contributing_count),
        })
    return {
        "as_of_date": target.isoformat(),
        "strategy_id": strategy_id,
        "limit": limit,
        "count": len(items),
        "items": items,
    }
