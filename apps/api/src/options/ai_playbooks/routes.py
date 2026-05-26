"""Phase G — AI Approach HTTP routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.options.ai_playbooks.service import (
    get_approach, get_approach_live, list_approaches,
)


router = APIRouter(
    prefix="/options/approaches", tags=["options-ai-playbooks"],
)


@router.get("")
def list_all(session: Session = Depends(get_session)) -> dict[str, Any]:
    rows = list_approaches(session)
    return {"count": len(rows), "items": rows}


@router.get("/{slug}")
def get_one(
    slug: str, session: Session = Depends(get_session),
) -> dict[str, Any]:
    item = get_approach(session, slug)
    if item is None:
        raise HTTPException(status_code=404, detail="approach not found")
    return item


@router.get("/{slug}/live")
def get_one_live(
    slug: str, session: Session = Depends(get_session),
) -> dict[str, Any]:
    item = get_approach_live(session, slug)
    if item is None:
        raise HTTPException(status_code=404, detail="approach not found")
    return item
