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


def _email_and_role(db: Session, uid: str) -> tuple[str | None, str | None]:
    """Return (email, access_role) for a user id. Defensive: if the
    access_role column does not exist yet (pre-migration), fall back to
    email-only so the env allowlist still works."""
    try:
        row = db.execute(
            text("SELECT email, access_role FROM app_user WHERE id = :i"), {"i": uid}
        ).mappings().first()
        if row:
            return row["email"], row.get("access_role")
    except Exception:
        db.rollback()
        row = db.execute(
            text("SELECT email FROM app_user WHERE id = :i"), {"i": uid}
        ).mappings().first()
        if row:
            return row["email"], None
    return None, None


def require_owner(request: Request, db: Session = Depends(get_session)) -> dict:
    """FastAPI dependency. Returns the owner identity, or raises 404.

    Owner access is granted by EITHER the durable DB role (access_role =
    'owner') OR the env allowlist (ARTHOS_OWNER_EMAILS) — DB role is the
    durable source, env is the bootstrap/failsafe. 404 (not 403) for both
    anonymous and authenticated-non-owner callers: the admin surface must be
    undiscoverable to anyone but the owner.
    """
    uid = ident.session_user_id(db, request.cookies.get(ident.SESSION_COOKIE))
    if not uid:
        raise HTTPException(status_code=404)
    email, role = _email_and_role(db, uid)
    via = "db_role" if role == "owner" else ("env" if is_owner(email) else None)
    if via is None:
        logger.warning("admin_access_denied path={} uid={}", request.url.path, uid)
        raise HTTPException(status_code=404)
    logger.info("admin_access_ok owner={} via={} path={}", email, via, request.url.path)
    return {"id": uid, "email": email, "role": role, "via": via}
