"""Factor snapshot API — single snapshot + latest-per-asset."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.db.models import Asset, FactorSnapshot

router = APIRouter(prefix="/factors", tags=["factors"])


def _dec(v: Decimal | None) -> str | None:
    return str(v) if v is not None else None


def _row_payload(row: FactorSnapshot, symbol: str | None = None) -> dict[str, Any]:
    return {
        "as_of_date": row.as_of_date.isoformat(),
        "asset_id": row.asset_id,
        "symbol": symbol,
        "residual_momentum_20d": _dec(row.residual_momentum_20d),
        "residual_momentum_60d": _dec(row.residual_momentum_60d),
        "sector_relative_rank": _dec(row.sector_relative_rank),
        "trend_strength_20d": _dec(row.trend_strength_20d),
        "price_vs_200sma": _dec(row.price_vs_200sma),
        "atr_percent_14": _dec(row.atr_percent_14),
        "earnings_proximity_days": row.earnings_proximity_days,
        "avg_dollar_volume_20d": _dec(row.avg_dollar_volume_20d),
        "enough_data": row.enough_data,
        "stale_data": row.stale_data,
        "feature_set_hash": row.feature_set_hash,
    }


@router.get("/snapshot")
def get_factor_snapshot(
    symbol: str = Query(..., description="Asset symbol (case-insensitive)"),
    as_of: dt.date | None = Query(
        None, description="YYYY-MM-DD; defaults to most recent for the symbol",
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    asset = session.scalars(
        select(Asset).where(func.upper(Asset.symbol) == symbol.upper()).limit(1)
    ).first()
    if asset is None:
        raise HTTPException(status_code=404, detail=f"unknown symbol: {symbol}")

    stmt = select(FactorSnapshot).where(FactorSnapshot.asset_id == asset.id)
    if as_of is not None:
        stmt = stmt.where(FactorSnapshot.as_of_date == as_of)
    else:
        stmt = stmt.order_by(FactorSnapshot.as_of_date.desc())
    stmt = stmt.limit(1)

    row = session.scalars(stmt).first()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"no factor_snapshot for {symbol} (as_of={as_of})",
        )
    return _row_payload(row, symbol=asset.symbol)


@router.get("/latest")
def get_factor_latest(
    limit: int = Query(50, ge=1, le=500),
    universe_only: bool = Query(
        False, description="If true, restrict to stock_swing_v1 members as of today",
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    # latest as_of_date per asset_id
    latest_sub = (
        select(
            FactorSnapshot.asset_id.label("asset_id"),
            func.max(FactorSnapshot.as_of_date).label("max_as_of"),
        )
        .group_by(FactorSnapshot.asset_id)
        .subquery()
    )
    stmt = (
        select(FactorSnapshot, Asset.symbol)
        .join(
            latest_sub,
            (FactorSnapshot.asset_id == latest_sub.c.asset_id)
            & (FactorSnapshot.as_of_date == latest_sub.c.max_as_of),
        )
        .join(Asset, Asset.id == FactorSnapshot.asset_id)
        .order_by(Asset.symbol.asc())
        .limit(limit)
    )

    if universe_only:
        from apps.api.src.db.models import UniverseMembership
        from sqlalchemy import or_

        today = dt.date.today()
        stmt = stmt.join(
            UniverseMembership,
            UniverseMembership.asset_id == FactorSnapshot.asset_id,
        ).where(
            UniverseMembership.universe_name == "stock_swing_v1",
            UniverseMembership.start_date <= today,
            or_(
                UniverseMembership.end_date.is_(None),
                UniverseMembership.end_date >= today,
            ),
        )

    rows = list(session.execute(stmt).all())
    return {
        "count": len(rows),
        "snapshots": [_row_payload(fs, sym) for fs, sym in rows],
    }
