"""Dashboard API — one-shot summary endpoint."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.domain.dashboard.summary import build_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def get_dashboard_summary(
    portfolio_id: str | None = Query(None),
    as_of: dt.date | None = Query(None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return build_summary(session, portfolio_id=portfolio_id, as_of=as_of)
