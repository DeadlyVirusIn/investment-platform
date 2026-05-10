"""Market events route.

Exposes:
    GET /api/market/events?symbols=AAPL,MSFT,NVDA
    GET /api/asset/{symbol}/events

Both routes are read-only. SEC EDGAR works without any key. Polygon
and Benzinga are wired through env vars; absent keys mean the
relevant arrays come back empty (frontend handles gracefully).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from apps.api.src.domain.market_events.service import (
    MAX_SYMBOLS,
    get_events_for_symbol,
    get_events_for_symbols,
)


router = APIRouter(tags=["market-events"])


@router.get("/market/events")
def market_events(
    symbols: str = Query(
        default="",
        description=f"Comma-separated tickers (max {MAX_SYMBOLS}).",
        max_length=512,
    ),
) -> dict[str, Any]:
    sym_list = [s for s in (symbols or "").split(",") if s.strip()]
    return get_events_for_symbols(sym_list)


@router.get("/asset/{symbol}/events")
def asset_events(symbol: str) -> dict[str, Any]:
    return get_events_for_symbol(symbol)
