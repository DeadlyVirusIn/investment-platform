"""Watchlist API – stub endpoints for Phase 0."""

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("")
async def list_watchlist() -> dict[str, Any]:
    return {"stub": True, "data": []}


@router.post("")
async def add_to_watchlist(payload: dict[str, Any]) -> dict[str, Any]:
    return {"stub": True, "data": payload}
