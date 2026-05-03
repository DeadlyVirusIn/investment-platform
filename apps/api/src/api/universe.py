"""Universe membership API — point-in-time list by universe name."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.domain.universe.membership import list_members

router = APIRouter(prefix="/universe", tags=["universe"])


@router.get("/{name}")
def get_universe(
    name: str,
    as_of: dt.date | None = Query(
        None, description="YYYY-MM-DD; defaults to today when omitted"
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    effective = as_of or dt.date.today()
    rows = list_members(session, name, effective)
    return {
        "universe_name": name,
        "as_of": effective.isoformat(),
        "count": len(rows),
        "members": [
            {
                "membership_id": m.id,
                "asset_id": m.asset_id,
                "symbol": a.symbol,
                "asset_class": a.asset_class,
                "start_date": m.start_date.isoformat(),
                "end_date": m.end_date.isoformat() if m.end_date else None,
                "reason": m.reason,
            }
            for (m, a) in rows
        ],
    }
