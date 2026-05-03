"""Asset API — detail endpoints. Upgraded in UI-2A to serve real price data
for benchmark overlays and future asset-detail pages. Fundamentals and
technicals remain stubs for later phases.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.db.models import Asset, PriceBar

router = APIRouter(prefix="/asset", tags=["asset"])


def _d(v: object) -> str | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return str(v)
    return str(v)


@router.get("/{symbol}")
def get_asset(
    symbol: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(Asset).where(Asset.symbol == symbol)
    asset = session.scalars(stmt).first()
    if asset is None:
        raise HTTPException(status_code=404, detail=f"unknown symbol: {symbol}")
    return {
        "id": asset.id,
        "symbol": asset.symbol,
        "name": asset.name,
        "asset_class": asset.asset_class,
        "exchange": asset.exchange,
        "currency": asset.currency,
        "is_active": asset.is_active,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }


@router.get("/{symbol}/prices")
def get_asset_prices(
    symbol: str,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    timeframe: str = "1d",
    limit: int = Query(default=5000, ge=1, le=50000),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Return daily price history for a symbol. Used for benchmark overlays."""
    stmt = select(Asset).where(Asset.symbol == symbol)
    asset = session.scalars(stmt).first()
    if asset is None:
        raise HTTPException(status_code=404, detail=f"unknown symbol: {symbol}")

    where = [
        PriceBar.asset_id == asset.id,
        PriceBar.timeframe == timeframe,
    ]
    if from_:
        try:
            dt_from = dt.datetime.fromisoformat(from_.replace("Z", "+00:00"))
            where.append(PriceBar.ts >= dt_from)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"invalid 'from' date: {from_}")
    if to:
        try:
            dt_to = dt.datetime.fromisoformat(to.replace("Z", "+00:00"))
            where.append(PriceBar.ts <= dt_to)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"invalid 'to' date: {to}")

    bars = session.scalars(
        select(PriceBar).where(*where).order_by(PriceBar.ts.asc()).limit(limit)
    ).all()

    prices = [
        {
            "ts": b.ts.isoformat() if b.ts else None,
            "close": _d(b.close),
            "adjusted_close": _d(b.adjusted_close) if b.adjusted_close is not None else None,
        }
        for b in bars
    ]
    return {
        "symbol": asset.symbol,
        "timeframe": timeframe,
        "count": len(prices),
        "prices": prices,
    }


@router.get("/{symbol}/fundamentals")
def get_fundamentals(symbol: str) -> dict[str, Any]:
    return {"stub": True, "symbol": symbol, "data": {}}


@router.get("/{symbol}/technicals")
def get_technicals(symbol: str) -> dict[str, Any]:
    return {"stub": True, "symbol": symbol, "data": {}}
