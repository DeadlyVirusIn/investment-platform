"""Asset API – stub endpoints for Phase 0."""

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/asset", tags=["asset"])


@router.get("/{symbol}")
async def get_asset(symbol: str) -> dict[str, Any]:
    return {"stub": True, "symbol": symbol, "data": {}}


@router.get("/{symbol}/prices")
async def get_asset_prices(symbol: str) -> dict[str, Any]:
    return {"stub": True, "symbol": symbol, "data": []}


@router.get("/{symbol}/fundamentals")
async def get_fundamentals(symbol: str) -> dict[str, Any]:
    return {"stub": True, "symbol": symbol, "data": {}}


@router.get("/{symbol}/technicals")
async def get_technicals(symbol: str) -> dict[str, Any]:
    return {"stub": True, "symbol": symbol, "data": {}}
