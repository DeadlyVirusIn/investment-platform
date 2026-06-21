"""M1 auth endpoints — signup / login / logout (cookie-based sessions).

Mounted at /api -> POST /api/signup, /api/login, /api/logout. Real identity for
all per-user surfaces flows from the `arthos_session` HttpOnly cookie. Returns
only safe user fields (never the password hash). Login uses a generic error to
avoid user enumeration.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.auth import identity as ident
from apps.api.src.config import settings
from apps.api.src.db import get_session

router = APIRouter(tags=["auth"])

_COOKIE_MAX_AGE = 30 * 24 * 3600


class SignupBody(BaseModel):
    email: str
    password: str
    display_name: str | None = None


class LoginBody(BaseModel):
    email: str
    password: str


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=ident.SESSION_COOKIE,
        value=token,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=bool(settings.SESSION_COOKIE_SECURE),
        path="/",
    )


def _safe_user(db: Session, uid: str) -> dict[str, Any]:
    row = db.execute(
        text("SELECT id, email, display_name FROM app_user WHERE id = :i"),
        {"i": uid},
    ).mappings().first()
    if row is None:
        return {"id": uid}
    return {"id": row["id"], "email": row["email"], "display_name": row["display_name"]}


@router.post("/signup")
def signup(body: SignupBody, response: Response, db: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        uid = ident.create_user(
            db, email=body.email, password=body.password, display_name=body.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    token = ident.create_session(db, uid)
    db.commit()
    _set_session_cookie(response, token)
    return {"ok": True, "user": _safe_user(db, uid)}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, db: Session = Depends(get_session)) -> dict[str, Any]:
    ip = ident.client_ip(request)
    if ident.login_locked(
        db, email=body.email, ip=ip,
        max_attempts=settings.AUTH_LOGIN_MAX_ATTEMPTS,
        window_seconds=settings.AUTH_LOGIN_WINDOW_SECONDS,
        lockout_seconds=settings.AUTH_LOGIN_LOCKOUT_SECONDS,
    ):
        # Locked out → SAME generic error as a bad password (no lockout/enum disclosure).
        raise HTTPException(status_code=401, detail="invalid email or password")
    uid = ident.authenticate_user(db, email=body.email, password=body.password)
    if not uid:
        ident.record_login_attempt(db, email=body.email, ip=ip, succeeded=False)
        db.commit()
        raise HTTPException(status_code=401, detail="invalid email or password")
    ident.clear_login_failures(db, email=body.email)  # reset on success
    token = ident.create_session(db, uid)
    db.commit()
    _set_session_cookie(response, token)
    return {"ok": True, "user": _safe_user(db, uid)}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_session)) -> dict[str, Any]:
    ident.revoke_session(db, request.cookies.get(ident.SESSION_COOKIE))
    db.commit()
    response.delete_cookie(ident.SESSION_COOKIE, path="/")
    return {"ok": True}
