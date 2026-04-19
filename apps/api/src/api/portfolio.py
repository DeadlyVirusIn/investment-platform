"""Portfolio API – stub endpoints for Phase 0."""

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/summary")
async def get_portfolio_summary() -> dict[str, Any]:
    return {"stub": True, "data": {}}


@router.get("/positions")
async def get_positions() -> dict[str, Any]:
    return {"stub": True, "data": []}


@router.get("/transactions")
async def list_transactions() -> dict[str, Any]:
    return {"stub": True, "data": []}


@router.post("/transactions")
async def create_transaction(payload: dict[str, Any]) -> dict[str, Any]:
    return {"stub": True, "data": payload}


@router.get("/pnl")
async def get_pnl() -> dict[str, Any]:
    return {"stub": True, "data": {"realized": 0, "unrealized": 0}}
