"""Phase 2 stock fix Phase 4 — paper-trading execution funnel HTTP routes.

GET-only. Backed by paper_trading.funnel SELECT helpers. Zero mutation.

Endpoints (mounted under /api/paper/funnel):
  GET /paper/funnel/recent             — daily totals across all portfolios
  GET /paper/funnel/by-portfolio       — per-portfolio time series
  GET /paper/funnel/reasons            — skip-reason distribution
  GET /paper/funnel/saturation         — latest saturation per portfolio
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.domain.paper_trading import funnel as F


router = APIRouter(prefix="/paper/funnel", tags=["paper-funnel"])


@router.get("/recent")
def funnel_recent(
    days: int = Query(default=14, ge=1, le=90),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = F.recent_rows(session, days=days)
    return {"count": len(rows), "days": days, "rows": rows}


@router.get("/by-portfolio")
def funnel_by_portfolio(
    portfolio_id: str = Query(...),
    days: int = Query(default=14, ge=1, le=90),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = F.by_portfolio(session, portfolio_id=portfolio_id, days=days)
    return {
        "portfolio_id": portfolio_id, "days": days,
        "count": len(rows), "rows": rows,
    }


@router.get("/reasons")
def funnel_reasons(
    days: int = Query(default=14, ge=1, le=90),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return {"days": days, "reasons": F.reason_distribution(session, days=days)}


@router.get("/saturation")
def funnel_saturation(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = F.saturation_snapshot(session)
    return {"count": len(rows), "rows": rows}
