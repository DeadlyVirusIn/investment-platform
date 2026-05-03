"""Watchlist API — lightweight v1.

Single-user system, no auth scoping. Symbols are uppercased and deduped.
Optionally decorates list with latest close from price_bar if available.
"""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.db.models import Asset, PriceBar, Watchlist

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,15}$")


class WatchlistAddRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=16)


def _normalize(sym: str) -> str:
    s = (sym or "").strip().upper()
    if not _SYMBOL_RE.match(s):
        raise HTTPException(status_code=400, detail=f"invalid symbol: {sym!r}")
    return s


def _latest_prices_for(
    session: Session, symbols: list[str],
) -> dict[str, tuple[Decimal | None, Decimal | None]]:
    """Return {symbol: (last_close, prev_close)} for each symbol that has bars."""
    out: dict[str, tuple[Decimal | None, Decimal | None]] = {}
    if not symbols:
        return out
    assets = session.execute(
        select(Asset.id, Asset.symbol).where(Asset.symbol.in_(symbols))
    ).all()
    for asset_id, sym in assets:
        bars = list(session.execute(
            select(PriceBar.close)
            .where(PriceBar.asset_id == asset_id, PriceBar.timeframe == "1d")
            .order_by(desc(PriceBar.ts))
            .limit(2)
        ).all())
        if not bars:
            continue
        last = bars[0][0]
        prev = bars[1][0] if len(bars) > 1 else None
        out[sym] = (
            last if last is None or isinstance(last, Decimal) else Decimal(str(last)),
            prev if prev is None or isinstance(prev, Decimal) else Decimal(str(prev)),
        )
    return out


def _item_payload(
    symbol: str,
    added_at: dt.datetime,
    prices: dict[str, tuple[Decimal | None, Decimal | None]],
) -> dict[str, Any]:
    last, prev = prices.get(symbol, (None, None))
    change_pct: str | None = None
    if last is not None and prev is not None and prev != 0:
        change_pct = str(((last - prev) / prev).quantize(Decimal("0.000001")))
    return {
        "symbol": symbol,
        "added_at": added_at.isoformat() if added_at else None,
        "last_close": str(last) if last is not None else None,
        "change_pct": change_pct,
    }


@router.get("")
def list_watchlist(session: Session = Depends(get_session)) -> dict[str, Any]:
    rows = list(session.scalars(
        select(Watchlist).order_by(Watchlist.added_at.desc())
    ))
    symbols = [r.symbol for r in rows]
    prices = _latest_prices_for(session, symbols)
    return {
        "count": len(rows),
        "items": [_item_payload(r.symbol, r.added_at, prices) for r in rows],
    }


@router.post("", status_code=201)
def add_to_watchlist(
    body: WatchlistAddRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    sym = _normalize(body.symbol)
    existing = session.get(Watchlist, sym)
    if existing is not None:
        return {"symbol": sym, "created": False}
    session.add(Watchlist(symbol=sym))
    session.commit()
    return {"symbol": sym, "created": True}


@router.delete("/{symbol}")
def remove_from_watchlist(
    symbol: str, session: Session = Depends(get_session),
) -> dict[str, Any]:
    sym = _normalize(symbol)
    row = session.get(Watchlist, sym)
    if row is None:
        raise HTTPException(status_code=404, detail=f"symbol not watched: {sym}")
    session.delete(row)
    session.commit()
    return {"symbol": sym, "removed": True}
