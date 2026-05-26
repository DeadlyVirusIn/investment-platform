"""Phase E — Options Journal HTTP routes.

GET-only. Read-only. Composed views on top of existing tables.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.options.journal.service import (
    ENTRY_TYPES,
    fetch_timeline,
    timeline_entry_to_dict,
    trade_evolution,
)


router = APIRouter(prefix="/options/journal", tags=["options-journal"])


@router.get("/timeline")
def get_timeline(
    lookback_days: int = Query(default=14, ge=1, le=90),
    underlying: str | None = Query(default=None),
    entry_type: list[str] | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Unified DESC timeline across shadow / candidate / trade /
    lifecycle sources. Filters by underlying + entry_type."""
    items = fetch_timeline(
        session,
        lookback_days=lookback_days,
        underlying=underlying,
        entry_types=entry_type,
        limit=limit,
    )
    return {
        "count":           len(items),
        "lookback_days":   lookback_days,
        "filter": {
            "underlying":  underlying,
            "entry_type":  entry_type,
        },
        "known_entry_types": list(ENTRY_TYPES),
        "items": [timeline_entry_to_dict(e) for e in items],
    }


@router.get("/trade/{trade_id}/evolution")
def get_trade_evolution(
    trade_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Per-trade thesis evolution narrative."""
    payload = trade_evolution(session, trade_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="trade not found")
    return payload
