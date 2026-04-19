# FEATURE FLAG: performance analytics endpoints are DISABLED until Phase 1 P&L engine is complete.
# Remove this comment and the stub body once PerformanceService is implemented.

"""Performance API – stub endpoint for Phase 0."""

from typing import Any, Literal

from fastapi import APIRouter, Query

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("")
async def get_performance(
    window: Literal["30d", "90d", "1y"] = Query(default="30d"),
) -> dict[str, Any]:
    return {"stub": True, "window": window, "data": {}}
