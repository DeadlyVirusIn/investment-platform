"""Stock-engine analytics API — tuning visibility over candidate_idea.

All endpoints are read-only. No writes. No state changes.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.domain.diagnostics.csv_tools import rows_to_csv
from apps.api.src.domain.stock_engine.analytics import (
    DEFAULT_BLOCKED_ALPHA_MIN_SCORE,
    DEFAULT_REGIME_PRESSURE_MIN_SCORE,
    DEFAULT_THRESHOLD_GRID,
    blocked_alpha,
    regime_pressure,
    rejection_analytics,
    score_distribution,
    sector_preview,
    threshold_sensitivity,
)

router = APIRouter(
    prefix="/stock-engine/analytics", tags=["stock-engine-analytics"],
)


@router.get("/rejections")
def get_rejections(
    from_date: dt.date | None = Query(None, alias="from"),
    to_date: dt.date | None = Query(None, alias="to"),
    symbol: str | None = Query(None),
    sector: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return rejection_analytics(
        session, from_date=from_date, to_date=to_date,
        symbol=symbol, sector=sector,
    )


_BLOCKED_CSV_COLUMNS = (
    "as_of_date", "symbol", "sector", "asset_id",
    "composite_score", "confidence", "rejection_reason",
)


@router.get("/blocked-alpha")
def get_blocked_alpha(
    from_date: dt.date | None = Query(None, alias="from"),
    to_date: dt.date | None = Query(None, alias="to"),
    min_score: float = Query(float(DEFAULT_BLOCKED_ALPHA_MIN_SCORE),
                             ge=-1.0, le=1.0),
    rejection_reason: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    format: str = Query("json", pattern="^(json|csv)$"),
    session: Session = Depends(get_session),
) -> Any:
    payload = blocked_alpha(
        session, from_date=from_date, to_date=to_date,
        min_score=Decimal(str(min_score)),
        rejection_reason=rejection_reason, limit=limit,
    )
    if format == "csv":
        body = rows_to_csv(payload.get("items", []), _BLOCKED_CSV_COLUMNS)
        return Response(content=body, media_type="text/csv")
    return payload


@router.get("/score-distribution")
def get_score_distribution(
    from_date: dt.date | None = Query(None, alias="from"),
    to_date: dt.date | None = Query(None, alias="to"),
    sector: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return score_distribution(
        session, from_date=from_date, to_date=to_date, sector=sector,
    )


@router.get("/threshold-sensitivity")
def get_threshold_sensitivity(
    from_date: dt.date | None = Query(None, alias="from"),
    to_date: dt.date | None = Query(None, alias="to"),
    thresholds: list[float] | None = Query(
        None, description="Optional custom grid; repeat param for multiple values",
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    grid: tuple[Decimal, ...]
    if thresholds:
        grid = tuple(Decimal(str(t)) for t in thresholds)
    else:
        grid = DEFAULT_THRESHOLD_GRID
    return threshold_sensitivity(
        session, from_date=from_date, to_date=to_date, thresholds=grid,
    )


@router.get("/regime-pressure")
def get_regime_pressure(
    from_date: dt.date | None = Query(None, alias="from"),
    to_date: dt.date | None = Query(None, alias="to"),
    min_top_score: float = Query(
        float(DEFAULT_REGIME_PRESSURE_MIN_SCORE), ge=-1.0, le=1.0,
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return regime_pressure(
        session, from_date=from_date, to_date=to_date,
        min_top_score=Decimal(str(min_top_score)),
    )


@router.get("/sector-preview")
def get_sector_preview(
    as_of: dt.date | None = Query(None),
    min_blocked_score: float = Query(
        float(DEFAULT_BLOCKED_ALPHA_MIN_SCORE), ge=-1.0, le=1.0,
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return sector_preview(
        session, as_of=as_of,
        min_blocked_score=Decimal(str(min_blocked_score)),
    )
