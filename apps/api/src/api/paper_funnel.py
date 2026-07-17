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

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from sqlalchemy import text

from apps.api.src.auth import identity as ident
from apps.api.src.api.admin_guard import _email_and_role, is_owner
from apps.api.src.auth.identity import resolve_identity
from apps.api.src.db import get_session
from apps.api.src.domain.paper_trading.paper_service import public_book_label
from apps.api.src.domain.paper_trading import funnel as F


router = APIRouter(prefix="/paper/funnel", tags=["paper-funnel"])


def _request_is_owner(request: Request, session: Session) -> bool:
    uid = ident.session_user_id(session, request.cookies.get(ident.SESSION_COOKIE))
    if not uid:
        return False
    email, role = _email_and_role(session, uid)
    return role == "owner" or is_owner(email)


def _require_readable_portfolio(request: Request, session: Session, portfolio_id: str) -> None:
    name = session.execute(
        text("SELECT name FROM paper_portfolio WHERE id = :pid"), {"pid": portfolio_id}
    ).scalar()
    if name is None:
        raise HTTPException(status_code=404, detail="Not Found")
    if name.strip().lower().startswith("user:") and not _request_is_owner(request, session):
        uid = resolve_identity(request, session)
        own_book = f"user:{uid[:64]}:stock" if uid else None
        if name != own_book:
            raise HTTPException(status_code=404, detail="Not Found")


@router.get("/recent")
def funnel_recent(
    request: Request,
    days: int = Query(default=14, ge=1, le=90),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = F.recent_rows(
        session, days=days, include_user_books=_request_is_owner(request, session)
    )
    return {"count": len(rows), "days": days, "rows": rows}


@router.get("/by-portfolio")
def funnel_by_portfolio(
    request: Request,
    portfolio_id: str = Query(...),
    days: int = Query(default=14, ge=1, le=90),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_readable_portfolio(request, session, portfolio_id)
    rows = F.by_portfolio(session, portfolio_id=portfolio_id, days=days)
    return {
        "portfolio_id": portfolio_id, "days": days,
        "count": len(rows), "rows": rows,
    }


@router.get("/reasons")
def funnel_reasons(
    request: Request,
    days: int = Query(default=14, ge=1, le=90),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return {"days": days, "reasons": F.reason_distribution(
        session, days=days, include_user_books=_request_is_owner(request, session)
    )}


@router.get("/saturation")
def funnel_saturation(
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    request_is_owner = _request_is_owner(request, session)
    rows = F.saturation_snapshot(session, include_user_books=request_is_owner)
    for row in rows:
        row["name"] = public_book_label(
            row["name"], is_owner=request_is_owner
        )
    return {"count": len(rows), "rows": rows}
