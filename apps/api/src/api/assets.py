"""Assets API: create + list. Item-detail lives under /asset/{symbol}."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.domain.assets.asset_service import (
    AssetCreate,
    create_asset,
    list_assets,
)

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("")
def get_assets(
    limit: int = 500,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    # Phase 2 — frontend name map needs the full universe (>500). Cap at 5000.
    limit = max(1, min(limit, 5000))
    assets = [a.model_dump(mode="json") for a in list_assets(session, limit=limit)]
    return {"assets": assets, "count": len(assets)}


@router.post("", status_code=201)
def post_asset(
    payload: AssetCreate,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        out = create_asset(session, payload)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return out.model_dump(mode="json")
