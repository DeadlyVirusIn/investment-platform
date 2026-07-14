"""Wave 1D — Decision Replay Timeline API.

Mounted ONLY when settings.DECISION_REPLAY_ENABLED.

Public route: GET /recommendations/{symbol}/timeline — anonymous callers
receive only public lifecycle events; an authenticated session adds THAT
USER'S OWN practice activity (resolved server-side from the session cookie;
the caller cannot name a principal). The payload never contains UUIDs,
asset/database ids, snapshot hashes, git SHAs, raw family-score maps, raw
preflight checks, raw posture signals, emails, or internal trade ids.

Owner route: GET /admin/replay/{recommendation_id} — owner-gated 404
posture; adds exact recommendation identity, rule-set versions, and full
preflight checks. It still never exposes secrets, provider errors, or
OTHER users' paper activity (owner deep view is not a cross-user
impersonation path — support workflows would be a separate audited design).
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from apps.api.src.api.admin_guard import require_owner
from apps.api.src.auth import identity as ident
from apps.api.src.db import get_session
from apps.api.src.domain.recommendations.replay import get_timeline

public_router = APIRouter(prefix="/recommendations", tags=["decision-replay"])
owner_router = APIRouter(
    prefix="/admin/replay",
    tags=["decision-replay-admin"],
    dependencies=[Depends(require_owner)],
)

_SYMBOL = re.compile(r"^[A-Za-z][A-Za-z0-9.\-]{0,9}$")


@public_router.get("/{symbol}/timeline")
def public_timeline(
    symbol: str, request: Request, db: Session = Depends(get_session)
) -> dict[str, Any]:
    if not _SYMBOL.fullmatch(symbol):
        raise HTTPException(status_code=404, detail="unknown symbol")
    # Principal resolved server-side only — anonymous → None → zero paper
    # events; no parameter can select another user's activity.
    user_id = ident.session_user_id(
        db, request.cookies.get(ident.SESSION_COOKIE))
    result = get_timeline(db, symbol=symbol, user_id=user_id, owner=False)
    if result is None:
        raise HTTPException(status_code=404, detail="unknown symbol")
    return result


@owner_router.get("/{recommendation_id}")
def owner_timeline(
    recommendation_id: str, db: Session = Depends(get_session)
) -> dict[str, Any]:
    result = get_timeline(db, rec_id=recommendation_id, owner=True)
    if result is None:
        raise HTTPException(status_code=404, detail="unknown recommendation")
    result["recommendation_id"] = recommendation_id   # owner-only identity
    return result
