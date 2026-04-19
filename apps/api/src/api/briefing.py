"""Daily briefing API – stub endpoint for Phase 0."""

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/briefing", tags=["briefing"])


@router.get("/today")
async def get_today_briefing() -> dict[str, Any]:
    return {"stub": True, "data": {"sections": [], "generated_at": None}}
