"""Recommendations API – stub endpoints for Phase 0."""

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("")
async def list_recommendations() -> dict[str, Any]:
    return {"stub": True, "data": []}


@router.get("/{rec_id}/evidence")
async def get_recommendation_evidence(rec_id: str) -> dict[str, Any]:
    return {"stub": True, "recommendation_id": rec_id, "data": []}
