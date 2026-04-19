"""Daily briefing API — engine-backed."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.domain.briefing.briefing_service import build_briefing

router = APIRouter(prefix="/briefing", tags=["briefing"])


@router.get("/today")
def get_today_briefing(
    account_id: str = Query(..., description="account uuid"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return build_briefing(session, account_id)
