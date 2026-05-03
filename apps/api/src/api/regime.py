"""Regime API — current snapshot + history range."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.db.models import RegimeSnapshot

router = APIRouter(prefix="/regime", tags=["regime"])

MAX_HISTORY_DAYS = 3650  # ~10 years


def _dec(v: Decimal | None) -> str | None:
    return str(v) if v is not None else None


def _row_payload(row: RegimeSnapshot) -> dict[str, Any]:
    return {
        "as_of_date": row.as_of_date.isoformat(),
        "benchmark_symbol": row.benchmark_symbol,
        "market_trend": row.market_trend,
        "vol_regime": row.vol_regime,
        "breadth_regime": row.breadth_regime,
        "sma50_over_sma200": row.sma50_over_sma200,
        "realized_vol_20d": _dec(row.realized_vol_20d),
        "atr_pctile_1y": _dec(row.atr_pctile_1y),
    }


@router.get("/current")
def get_regime_current(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = session.scalars(
        select(RegimeSnapshot).order_by(RegimeSnapshot.as_of_date.desc()).limit(1)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="no regime snapshots yet")
    return _row_payload(row)


@router.get("/history")
def get_regime_history(
    from_date: dt.date | None = Query(
        None, alias="from", description="YYYY-MM-DD inclusive; defaults to 1y ago",
    ),
    to_date: dt.date | None = Query(
        None, alias="to", description="YYYY-MM-DD inclusive; defaults to today",
    ),
    limit: int = Query(400, ge=1, le=5000),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    end = to_date or dt.date.today()
    start = from_date or (end - dt.timedelta(days=365))
    if (end - start).days > MAX_HISTORY_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"range too wide (>{MAX_HISTORY_DAYS} days)",
        )
    if start > end:
        raise HTTPException(
            status_code=400, detail="from must be <= to",
        )

    stmt = (
        select(RegimeSnapshot)
        .where(
            RegimeSnapshot.as_of_date >= start,
            RegimeSnapshot.as_of_date <= end,
        )
        .order_by(RegimeSnapshot.as_of_date.asc())
        .limit(limit)
    )
    rows = list(session.scalars(stmt))
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "count": len(rows),
        "snapshots": [_row_payload(r) for r in rows],
    }
