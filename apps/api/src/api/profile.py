"""M3 profile endpoints — collect-only investing profile.

Session-authenticated (arthos_session cookie). A user can only read/write their
OWN row (scoped by the session-resolved app_user.id). Enum values validated.
NO recommendation/personalization behavior is wired here — collection only.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.auth import identity as ident
from apps.api.src.db import get_session

router = APIRouter(tags=["profile"])

ENUMS: dict[str, set[str]] = {
    "investing_experience": {"none", "beginner", "intermediate", "experienced"},
    "investing_goal": {"learn", "grow_wealth", "income", "preserve", "retirement"},
    "risk_comfort": {"low", "medium", "high"},
    "time_horizon": {"short", "medium", "long"},
    "preferred_style": {"steady", "balanced", "growth"},
    "liquidity_need": {"low", "medium", "high"},
    "options_experience": {"none", "learning", "experienced"},
}
FIELDS = list(ENUMS.keys())
# Fields that must be set for the profile to count as "complete".
REQUIRED = ["investing_experience", "investing_goal", "risk_comfort", "time_horizon", "preferred_style"]


class ProfileBody(BaseModel):
    investing_experience: str | None = None
    investing_goal: str | None = None
    risk_comfort: str | None = None
    time_horizon: str | None = None
    preferred_style: str | None = None
    liquidity_need: str | None = None
    options_experience: str | None = None


def _require_user(request: Request, db: Session) -> str:
    uid = ident.session_user_id(db, request.cookies.get(ident.SESSION_COOKIE))
    if not uid:
        raise HTTPException(status_code=401, detail="authentication required")
    return uid


def _read(db: Session, uid: str) -> dict[str, Any] | None:
    cols = ", ".join(FIELDS)
    row = db.execute(
        text(f"SELECT {cols} FROM user_profile WHERE user_id = :u"),
        {"u": uid},
    ).mappings().first()
    return dict(row) if row else None


def _payload(profile: dict[str, Any] | None) -> dict[str, Any]:
    data = {f: (profile.get(f) if profile else None) for f in FIELDS}
    complete = bool(profile) and all(profile.get(f) for f in REQUIRED)
    return {"profile": data, "complete": complete}


@router.get("/profile")
def get_profile(request: Request, db: Session = Depends(get_session)) -> dict[str, Any]:
    uid = _require_user(request, db)
    return _payload(_read(db, uid))


@router.put("/profile")
def put_profile(body: ProfileBody, request: Request, db: Session = Depends(get_session)) -> dict[str, Any]:
    uid = _require_user(request, db)
    values = body.model_dump(exclude_unset=True)
    for k, v in values.items():
        if v is not None and v not in ENUMS[k]:
            raise HTTPException(status_code=422, detail=f"invalid value for {k}")
    if values:
        cols = list(values.keys())
        insert_cols = ", ".join(["user_id", *cols])
        insert_ph = ", ".join([":user_id", *[f":{c}" for c in cols]])
        set_clause = ", ".join(f"{c} = :{c}" for c in cols)
        db.execute(
            text(
                f"INSERT INTO user_profile ({insert_cols}, updated_at) "
                f"VALUES ({insert_ph}, now()) "
                f"ON CONFLICT (user_id) DO UPDATE SET {set_clause}, updated_at = now()"
            ),
            {"user_id": uid, **values},
        )
        db.commit()
    return _payload(_read(db, uid))
