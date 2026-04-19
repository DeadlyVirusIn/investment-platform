"""Alerts API – stub endpoints for Phase 0."""

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
async def list_alerts() -> dict[str, Any]:
    return {"stub": True, "data": []}


@router.post("")
async def create_alert(payload: dict[str, Any]) -> dict[str, Any]:
    return {"stub": True, "data": payload}
