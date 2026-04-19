"""Asset creation + listing. Enforces (symbol, exchange) uniqueness."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset

AssetClass = Literal["equity", "etf", "crypto", "index"]


class AssetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=32)
    name: str | None = Field(default=None, max_length=256)
    asset_class: AssetClass
    exchange: str | None = Field(default=None, max_length=32)
    currency: str = Field(default="USD", min_length=3, max_length=8)


class AssetOut(BaseModel):
    id: str
    symbol: str
    name: str | None
    asset_class: str
    exchange: str | None
    currency: str
    is_active: bool
    created_at: dt.datetime


def _to_out(row: Asset) -> AssetOut:
    return AssetOut(
        id=row.id,
        symbol=row.symbol,
        name=row.name,
        asset_class=row.asset_class,
        exchange=row.exchange,
        currency=row.currency,
        is_active=row.is_active,
        created_at=row.created_at,
    )


def create_asset(session: Session, payload: AssetCreate) -> AssetOut:
    stmt = select(Asset).where(
        Asset.symbol == payload.symbol,
        Asset.exchange == payload.exchange,
    )
    existing = session.execute(stmt).scalars().first()
    if existing is not None:
        raise ValueError(
            f"asset already exists for symbol={payload.symbol!r} "
            f"exchange={payload.exchange!r}"
        )

    row = Asset(
        symbol=payload.symbol,
        name=payload.name,
        asset_class=payload.asset_class,
        exchange=payload.exchange,
        currency=payload.currency,
        is_active=True,
    )
    session.add(row)
    session.flush()
    return _to_out(row)


def list_assets(session: Session, limit: int = 500) -> list[AssetOut]:
    stmt = (
        select(Asset)
        .order_by(Asset.symbol.asc(), Asset.exchange.asc().nulls_last())
        .limit(limit)
    )
    rows = list(session.execute(stmt).scalars())
    return [_to_out(r) for r in rows]
