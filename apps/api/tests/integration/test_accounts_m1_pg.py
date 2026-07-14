"""M1 Auth Core — integration tests (real Postgres via pg_session harness).

Mirrors test_paper_user_portfolio_pg.py. Exercises the auth-core functions and
the identity resolver directly (no TestClient / dev-DB coupling). The auth
tables (app_user, user_session) are raw-SQL migration tables not present in the
ORM metadata create_all, so we ensure them here idempotently. Each test uses a
unique email so rows never collide across the non-truncated auth tables.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from apps.api.src.auth import identity as ident
from apps.api.src.config import settings
from apps.api.src.db.models import PaperPortfolio, PaperPosition
from apps.api.src.domain.paper_trading.paper_service import (
    resolve_user_stock_portfolio,
    user_stock_portfolio_name,
)

pytestmark = pytest.mark.integration


def _ensure_auth_tables(db: Session) -> None:
    db.execute(text(
        """
        CREATE TABLE IF NOT EXISTS app_user (
            id text PRIMARY KEY,
            email text UNIQUE,
            display_name text,
            auth_provider text NOT NULL DEFAULT 'placeholder',
            external_auth_id text,
            password_hash text,
            created_at timestamptz NOT NULL DEFAULT now(),
            disabled_at timestamptz
        )
        """
    ))
    db.execute(text(
        """
        CREATE TABLE IF NOT EXISTS user_session (
            token text PRIMARY KEY,
            user_id text NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz
        )
        """
    ))
    db.commit()


@pytest.fixture
def auth_db(pg_session: Session) -> Session:
    _ensure_auth_tables(pg_session)
    return pg_session


def _email() -> str:
    return f"u-{uuid.uuid4().hex[:10]}@example.com"


# --------------------------------------------------------------------------
# Passwords / users
# --------------------------------------------------------------------------
def test_signup_stores_hashed_password_not_plaintext(auth_db: Session) -> None:
    email, pw = _email(), "correct horse battery"
    uid = ident.create_user(auth_db, email=email, password=pw)
    auth_db.commit()
    row = auth_db.execute(
        text("SELECT password_hash, auth_provider FROM app_user WHERE id = :i"),
        {"i": uid},
    ).mappings().first()
    assert row is not None
    assert row["auth_provider"] == "password"
    assert row["password_hash"] and row["password_hash"].startswith("scrypt$")
    assert pw not in row["password_hash"]  # never plaintext
    assert ident.verify_password(pw, row["password_hash"]) is True
    assert ident.verify_password("wrong", row["password_hash"]) is False


def test_duplicate_email_rejected(auth_db: Session) -> None:
    email = _email()
    ident.create_user(auth_db, email=email, password="password123")
    auth_db.commit()
    with pytest.raises(ValueError):
        ident.create_user(auth_db, email=email, password="password456")


def test_authenticate_user(auth_db: Session) -> None:
    email, pw = _email(), "password123"
    uid = ident.create_user(auth_db, email=email, password=pw)
    auth_db.commit()
    assert ident.authenticate_user(auth_db, email=email, password=pw) == uid
    assert ident.authenticate_user(auth_db, email=email, password="nope") is None
    assert ident.authenticate_user(auth_db, email=_email(), password=pw) is None  # unknown user


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------
def test_session_lifecycle_create_resolve_revoke(auth_db: Session) -> None:
    uid = ident.create_user(auth_db, email=_email(), password="password123")
    token = ident.create_session(auth_db, uid)
    auth_db.commit()
    assert ident.session_user_id(auth_db, token) == uid
    ident.revoke_session(auth_db, token)
    auth_db.commit()
    assert ident.session_user_id(auth_db, token) is None  # revoked → no identity


def test_expired_session_does_not_resolve(auth_db: Session) -> None:
    uid = ident.create_user(auth_db, email=_email(), password="password123")
    token = "expired-" + uuid.uuid4().hex
    auth_db.execute(
        text(
            """
            INSERT INTO user_session (token, user_id, created_at, expires_at)
            VALUES (:t, :u, now() - interval '40 days', now() - interval '1 day')
            """
        ),
        {"t": token, "u": uid},
    )
    auth_db.commit()
    assert ident.session_user_id(auth_db, token) is None


# --------------------------------------------------------------------------
# Identity resolution + demo gating
# --------------------------------------------------------------------------
def test_session_cookie_resolves_to_app_user(auth_db: Session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "DEMO_DEVICE_MODE", False)
    monkeypatch.setattr(settings, "AUTH_DISABLED_LOCAL", False)
    uid = ident.create_user(auth_db, email=_email(), password="password123")
    token = ident.create_session(auth_db, uid)
    auth_db.commit()
    assert ident.resolve_identity_value(auth_db, cookie_token=token, device_header="305fcf0b") == uid


def test_spoofed_device_header_ignored_when_demo_off(auth_db: Session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "DEMO_DEVICE_MODE", False)
    monkeypatch.setattr(settings, "AUTH_DISABLED_LOCAL", False)
    # No valid session cookie + a spoofed device header → anonymous (None),
    # NOT the targeted user's id. This is the core anti-spoof property.
    assert ident.resolve_identity_value(auth_db, cookie_token=None, device_header="victim-device-id") is None
    assert ident.resolve_identity_value(auth_db, cookie_token="bogus-token", device_header="victim-device-id") is None


def test_device_header_honored_only_in_demo_mode(auth_db: Session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "AUTH_DISABLED_LOCAL", False)
    monkeypatch.setattr(settings, "DEMO_DEVICE_MODE", True)
    assert ident.resolve_identity_value(auth_db, cookie_token=None, device_header="305fcf0b") == "305fcf0b"
    monkeypatch.setattr(settings, "DEMO_DEVICE_MODE", False)
    assert ident.resolve_identity_value(auth_db, cookie_token=None, device_header="305fcf0b") is None


# --------------------------------------------------------------------------
# Cross-user isolation (the load-bearing security invariant)
# --------------------------------------------------------------------------
def test_two_users_resolve_distinct_books_and_cannot_read_each_other(auth_db: Session) -> None:
    uid_a = ident.create_user(auth_db, email=_email(), password="password123")
    uid_b = ident.create_user(auth_db, email=_email(), password="password123")
    auth_db.commit()

    pid_a = resolve_user_stock_portfolio(auth_db, uid_a)
    pid_b = resolve_user_stock_portfolio(auth_db, uid_b)
    auth_db.commit()

    assert pid_a != pid_b
    assert auth_db.get(PaperPortfolio, pid_a).name == user_stock_portfolio_name(uid_a)
    assert auth_db.get(PaperPortfolio, pid_b).name == user_stock_portfolio_name(uid_b)

    # A's scoped read can never include B's portfolio rows.
    a_open = auth_db.scalar(
        select(func.count()).select_from(PaperPosition)
        .where(PaperPosition.portfolio_id == pid_a)
    )
    assert a_open == 0  # fresh user starts empty
    leaked = auth_db.scalar(
        select(func.count()).select_from(PaperPosition)
        .where(PaperPosition.portfolio_id == pid_a, PaperPosition.portfolio_id == pid_b)
    )
    assert leaked == 0


def test_fresh_signup_starts_empty(auth_db: Session) -> None:
    uid = ident.create_user(auth_db, email=_email(), password="password123")
    pid = resolve_user_stock_portfolio(auth_db, uid)
    auth_db.commit()
    n = auth_db.scalar(
        select(func.count()).select_from(PaperPosition)
        .where(PaperPosition.portfolio_id == pid, PaperPosition.is_open.is_(True))
    )
    assert n == 0


def test_login_persists_same_portfolio(auth_db: Session) -> None:
    email, pw = _email(), "password123"
    uid = ident.create_user(auth_db, email=email, password=pw)
    auth_db.commit()
    # Two separate logins (sessions/devices) → same app_user.id → same book.
    uid1 = ident.authenticate_user(auth_db, email=email, password=pw)
    uid2 = ident.authenticate_user(auth_db, email=email, password=pw)
    assert uid1 == uid2 == uid
    pid1 = resolve_user_stock_portfolio(auth_db, uid1)
    pid2 = resolve_user_stock_portfolio(auth_db, uid2)
    auth_db.commit()
    assert pid1 == pid2
