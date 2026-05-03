"""Daily briefing API — engine-backed.

``account_id`` is optional in personal-use single-account mode: when omitted,
falls back to the oldest Account. Multi-account callers pass explicit id.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.db.models import Account
from apps.api.src.domain.briefing.briefing_service import build_briefing

router = APIRouter(prefix="/briefing", tags=["briefing"])


DEFAULT_ACCOUNT_NAME = "Primary"


def _resolve_account_id(session: Session, account_id: str | None) -> str:
    """Optional account_id; bootstrap ``Primary`` when none exist."""
    if account_id:
        return account_id
    stmt = select(Account.id).order_by(Account.created_at.asc(), Account.id.asc()).limit(1)
    found = session.execute(stmt).scalars().first()
    if found:
        return found
    new_account = Account(
        name=DEFAULT_ACCOUNT_NAME,
        account_type="broker",
        currency="USD",
        is_active=True,
    )
    session.add(new_account)
    session.flush()
    session.commit()
    return new_account.id


@router.get("/today")
def get_today_briefing(
    account_id: str | None = Query(default=None, description="optional account uuid"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    resolved = _resolve_account_id(session, account_id)
    return build_briefing(session, resolved)
