"""M1 auth core — password hashing, revocable DB sessions, identity resolution.

Design: the core functions take a SQLAlchemy Session so they are unit-testable
without a TestClient or the dev DB. Passwords use stdlib `hashlib.scrypt`
(memory-hard, no new dependency). Identity priority:

  1. valid session cookie  -> authenticated app_user.id
  2. (demo/dev mode only)  -> X-Auth-User-Id device header
  3. else                  -> None (anonymous)

Public auth NEVER trusts the device header — it is honored only when
DEMO_DEVICE_MODE or AUTH_DISABLED_LOCAL is set.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings

SESSION_COOKIE = "arthos_session"
_SESSION_TTL_DAYS = 30
_N, _R, _P = 2 ** 14, 8, 1  # scrypt cost params


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------
def hash_password(password: str) -> str:
    if not password or len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded or not password:
        return False
    try:
        scheme, n, r, p, salt_hex, hash_hex = encoded.split("$")
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(expected),
        )
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------
def create_user(db: Session, *, email: str, password: str, display_name: str | None = None) -> str:
    em = _norm_email(email)
    if not em or "@" not in em:
        raise ValueError("invalid email")
    exists = db.execute(text("SELECT 1 FROM app_user WHERE lower(email) = :e"), {"e": em}).first()
    if exists is not None:
        raise ValueError("email already registered")
    uid = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO app_user
              (id, email, display_name, auth_provider, password_hash, created_at)
            VALUES (:id, :email, :dn, 'password', :ph, now())
            """
        ),
        {"id": uid, "email": em, "dn": display_name or em.split("@")[0], "ph": hash_password(password)},
    )
    return uid


def authenticate_user(db: Session, *, email: str, password: str) -> str | None:
    em = _norm_email(email)
    row = db.execute(
        text("SELECT id, password_hash, disabled_at FROM app_user WHERE lower(email) = :e"),
        {"e": em},
    ).mappings().first()
    if row is None or row["disabled_at"] is not None:
        # dummy verify to flatten the timing difference between miss and bad-password
        verify_password(password, "scrypt$16384$8$1$00$00")
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return row["id"]


# --------------------------------------------------------------------------
# Sessions (revocable, DB-backed)
# --------------------------------------------------------------------------
def create_session(db: Session, user_id: str, *, ttl_days: int = _SESSION_TTL_DAYS) -> str:
    token = secrets.token_urlsafe(32)
    db.execute(
        text(
            """
            INSERT INTO user_session (token, user_id, created_at, expires_at)
            VALUES (:t, :u, now(), now() + (:d || ' days')::interval)
            """
        ),
        {"t": token, "u": user_id, "d": str(int(ttl_days))},
    )
    return token


def session_user_id(db: Session, token: str | None) -> str | None:
    """Return the app_user.id for a valid (not revoked, not expired, user not
    disabled) session token; else None."""
    if not token:
        return None
    row = db.execute(
        text(
            """
            SELECT us.user_id
            FROM user_session us
            JOIN app_user u ON u.id = us.user_id
            WHERE us.token = :t
              AND us.revoked_at IS NULL
              AND us.expires_at > now()
              AND u.disabled_at IS NULL
            """
        ),
        {"t": token},
    ).mappings().first()
    return row["user_id"] if row else None


def revoke_session(db: Session, token: str | None) -> None:
    if not token:
        return
    db.execute(
        text("UPDATE user_session SET revoked_at = now() WHERE token = :t AND revoked_at IS NULL"),
        {"t": token},
    )


# --------------------------------------------------------------------------
# Login rate-limit / lockout (M1B brute-force protection)
# --------------------------------------------------------------------------
def record_login_attempt(db: Session, *, email: str, ip: str | None, succeeded: bool) -> None:
    db.execute(
        text("INSERT INTO login_attempt (email, ip, succeeded) VALUES (:e, :ip, :s)"),
        {"e": _norm_email(email), "ip": ip or "", "s": succeeded},
    )


def login_locked(
    db: Session, *, email: str, ip: str | None,
    max_attempts: int, window_seconds: int, lockout_seconds: int,
) -> bool:
    """True if (email OR non-empty ip) accumulated >= max_attempts FAILED logins
    within window_seconds AND the most recent failure is within lockout_seconds.
    Caller treats locked the same as a bad password (generic error)."""
    em = _norm_email(email)
    ipv = ip or ""
    row = db.execute(
        text(
            """
            SELECT count(*) AS n, max(created_at) AS last
            FROM login_attempt
            WHERE succeeded = false
              AND created_at > now() - make_interval(secs => :win)
              AND (email = :e OR (ip = :ip AND :ip <> ''))
            """
        ),
        {"win": float(window_seconds), "e": em, "ip": ipv},
    ).mappings().first()
    if not row or (row["n"] or 0) < max_attempts or row["last"] is None:
        return False
    locked = db.execute(
        text("SELECT (:last > now() - make_interval(secs => :lock)) AS locked"),
        {"last": row["last"], "lock": float(lockout_seconds)},
    ).scalar()
    return bool(locked)


def clear_login_failures(db: Session, *, email: str) -> None:
    """Reset the email's failed-attempt counter after a successful login."""
    db.execute(
        text("DELETE FROM login_attempt WHERE email = :e AND succeeded = false"),
        {"e": _norm_email(email)},
    )


# --------------------------------------------------------------------------
# Identity resolution
# --------------------------------------------------------------------------
def _demo_mode() -> bool:
    return bool(settings.DEMO_DEVICE_MODE) or bool(settings.AUTH_DISABLED_LOCAL)


def resolve_identity_value(db: Session, *, cookie_token: str | None, device_header: str | None) -> str | None:
    """Pure resolver (no HTTP). Session cookie wins; the device header is a
    fallback ONLY in demo/dev mode; otherwise anonymous (None)."""
    uid = session_user_id(db, cookie_token)
    if uid:
        return uid
    if _demo_mode():
        dev = (device_header or "").strip()
        if dev:
            return dev[:64]
    return None


def resolve_identity(request: Request, db: Session) -> str | None:
    return resolve_identity_value(
        db,
        cookie_token=request.cookies.get(SESSION_COOKIE),
        device_header=request.headers.get("X-Auth-User-Id"),
    )
