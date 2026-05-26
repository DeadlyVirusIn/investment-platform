"""Phase Opt-C2 Pre-Canary 0.2 — read-only canary HTTP endpoints.

GET-only routes under `/api/options/canary`. All handlers delegate
to `funnel.py` SELECT helpers. Zero mutation paths. No POST / PUT /
PATCH / DELETE.

Endpoints:
  GET /options/canary/portfolios              — list canary portfolios
  GET /options/canary/funnel/recent           — daily funnel totals
  GET /options/canary/funnel/by-portfolio     — per-portfolio time series
  GET /options/canary/funnel/reasons          — skip-reason distribution
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.options.canary import funnel as F


router = APIRouter(prefix="/options/canary", tags=["options-canary"])


@router.get("/portfolios")
def list_portfolios(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = F.list_portfolios(session)
    # Decimal → str for JSON safety. Counts already int.
    out = []
    for r in rows:
        out.append({
            **{k: (str(v) if hasattr(v, "as_tuple") else v)
               for k, v in r.items()},
        })
    return {"count": len(out), "rows": out}


@router.get("/funnel/recent")
def funnel_recent(
    days: int = Query(default=14, ge=1, le=90),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = F.recent_rows(session, days=days)
    return {"count": len(rows), "days": days, "rows": rows}


@router.get("/funnel/by-portfolio")
def funnel_by_portfolio(
    portfolio_id: str = Query(...),
    days: int = Query(default=14, ge=1, le=90),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = F.by_portfolio(session, portfolio_id=portfolio_id, days=days)
    return {
        "portfolio_id": portfolio_id,
        "days": days,
        "count": len(rows),
        "rows": rows,
    }


@router.get("/funnel/reasons")
def funnel_reasons(
    days: int = Query(default=14, ge=1, le=90),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return {"days": days, "reasons": F.reason_distribution(session, days=days)}
