"""Owner/admin access guard — Admin-1.

Env-based owner allowlist (``ARTHOS_OWNER_EMAILS``, comma-separated, case-
insensitive). No DB role column, no migration. ``require_owner`` reads the
``arthos_session`` cookie -> user -> email and returns **404 (not 403)** for
anonymous AND non-owner callers, so the admin surface is never disclosed to
anyone who isn't the owner. Every owner access (and every denied attempt) is
logged for audit.

Enforcement is server-side: this dependency is attached to every /api/admin/*
router. The frontend gate is cosmetic only.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.auth import identity as ident
from apps.api.src.config import settings
from apps.api.src.db import get_session


def owner_emails() -> set[str]:
    """Parse the allowlist env into a lowercased set. Empty => no owner."""
    raw = getattr(settings, "ARTHOS_OWNER_EMAILS", "") or ""
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_owner(email: str | None) -> bool:
    """Case-insensitive membership. Empty allowlist denies everyone."""
    if not email:
        return False
    allow = owner_emails()
    return bool(allow) and email.strip().lower() in allow


def require_owner(request: Request, db: Session = Depends(get_session)) -> dict:
    """FastAPI dependency. Returns the owner identity, or raises 404.

    404 (not 403) for both anonymous and authenticated-non-owner callers:
    the admin surface must be undiscoverable to anyone but the owner.
    """
    uid = ident.session_user_id(db, request.cookies.get(ident.SESSION_COOKIE))
    if not uid:
        # Anonymous — do not reveal the admin surface exists.
        raise HTTPException(status_code=404)
    row = db.execute(
        text("SELECT id, email FROM app_user WHERE id = :i"), {"i": uid}
    ).mappings().first()
    email = row["email"] if row else None
    if not is_owner(email):
        logger.warning("admin_access_denied path={} uid={}", request.url.path, uid)
        raise HTTPException(status_code=404)
    logger.info("admin_access_ok owner={} path={}", email, request.url.path)
    return {"id": uid, "email": email}
