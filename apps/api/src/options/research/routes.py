"""Phase D — AI conviction (Research) HTTP routes.

GET-only. Read-only. No execution.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.options.research.service import (
    underlying_research,
    universe_summary,
)


router = APIRouter(prefix="/options/research", tags=["options-research"])


@router.get("/universe")
def get_universe(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """One-line summary per underlying for the universe overview."""
    return universe_summary(session)


@router.get("/underlying/{symbol}")
def get_underlying(
    symbol: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Per-underlying AI conviction view."""
    return underlying_research(session, symbol.upper())
