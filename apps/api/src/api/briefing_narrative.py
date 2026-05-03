"""Briefing narrative endpoint — GET /api/briefing/narrative."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.domain.briefing.narrative import compose_narrative

router = APIRouter(prefix="/briefing", tags=["briefing"])


def _dec(v: Decimal | None) -> str | None:
    return str(v) if v is not None else None


@router.get("/narrative")
def get_narrative(
    portfolio_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    p = compose_narrative(session, portfolio_id=portfolio_id)
    return {
        "as_of_date": p.as_of_date,
        "narrative": p.narrative,
        "regime": p.regime,
        "portfolio_flags": p.portfolio_flags,
        "tuning_top": p.tuning_top,
        "delta": {
            "nav": _dec(p.delta.nav),
            "nav_pct": _dec(p.delta.nav_pct),
            "positions": p.delta.positions,
            "candidates": p.delta.candidates,
            "accepted_buys": p.delta.accepted_buys,
            "regime_changed": p.delta.regime_changed,
            "prev_regime": p.delta.prev_regime,
        },
    }
