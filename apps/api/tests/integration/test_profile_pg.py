"""M3 profile endpoints — integration tests (real Postgres + TestClient).

Drives the real FastAPI app with get_session overridden to the test session,
so the /api/profile endpoints run against the isolated test DB. Auth is the
arthos_session cookie (created via the identity helpers).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.auth import identity as ident
from apps.api.src.db import get_session
from apps.api.src.main import app

pytestmark = pytest.mark.integration


def _ensure(db: Session) -> None:
    db.execute(text(
        """
        CREATE TABLE IF NOT EXISTS app_user (
            id text PRIMARY KEY, email text UNIQUE, display_name text,
            auth_provider text NOT NULL DEFAULT 'placeholder',
            external_auth_id text, password_hash text,
            created_at timestamptz NOT NULL DEFAULT now(), disabled_at timestamptz
        )
        """
    ))
    db.execute(text(
        """
        CREATE TABLE IF NOT EXISTS user_session (
            token text PRIMARY KEY,
            user_id text NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL, revoked_at timestamptz
        )
        """
    ))
    db.execute(text(
        """
        CREATE TABLE IF NOT EXISTS user_profile (
            user_id text PRIMARY KEY REFERENCES app_user(id) ON DELETE CASCADE,
            investing_experience text, investing_goal text, risk_comfort text,
            time_horizon text, preferred_style text, liquidity_need text,
            options_experience text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    ))
    db.commit()


@pytest.fixture
def client(pg_session: Session):
    _ensure(pg_session)

    def _override():
        yield pg_session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


def _make_user(db: Session) -> tuple[str, str]:
    uid = ident.create_user(db, email=f"p-{uuid.uuid4().hex[:10]}@example.com", password="password123")
    token = ident.create_session(db, uid)
    db.commit()
    return uid, token


VALID = {
    "investing_experience": "beginner",
    "investing_goal": "grow_wealth",
    "risk_comfort": "medium",
    "time_horizon": "long",
    "preferred_style": "balanced",
}


def test_unauthenticated_get_and_put_401(client) -> None:
    assert client.get("/api/profile").status_code == 401
    assert client.put("/api/profile", json=VALID).status_code == 401


def test_authenticated_create_and_update_profile(client, pg_session) -> None:
    _, token = _make_user(pg_session)
    c = {"arthos_session": token}
    r0 = client.get("/api/profile", cookies=c).json()
    assert r0["complete"] is False
    assert r0["profile"]["risk_comfort"] is None
    r1 = client.put("/api/profile", json=VALID, cookies=c)
    assert r1.status_code == 200
    assert r1.json()["complete"] is True
    assert r1.json()["profile"]["preferred_style"] == "balanced"
    r2 = client.put("/api/profile", json={"risk_comfort": "high"}, cookies=c).json()
    assert r2["profile"]["risk_comfort"] == "high"
    assert r2["profile"]["investing_goal"] == "grow_wealth"  # partial update preserves others
    assert r2["complete"] is True
    assert "password_hash" not in r2["profile"] and "token" not in r2["profile"]


def test_invalid_enum_rejected(client, pg_session) -> None:
    _, token = _make_user(pg_session)
    r = client.put("/api/profile", json={"risk_comfort": "extreme"}, cookies={"arthos_session": token})
    assert r.status_code == 422


def test_user_a_cannot_read_or_write_user_b(client, pg_session) -> None:
    _, ta = _make_user(pg_session)
    uid_b, tb = _make_user(pg_session)
    client.put("/api/profile", json=VALID, cookies={"arthos_session": ta})
    rb = client.get("/api/profile", cookies={"arthos_session": tb}).json()
    assert rb["complete"] is False
    assert rb["profile"]["investing_goal"] is None  # B never sees A's data
    client.put("/api/profile", json={"risk_comfort": "low"}, cookies={"arthos_session": tb})
    row_b = pg_session.execute(
        text("SELECT risk_comfort FROM user_profile WHERE user_id = :u"), {"u": uid_b}
    ).scalar()
    assert row_b == "low"


def test_completion_status(client, pg_session) -> None:
    _, token = _make_user(pg_session)
    c = {"arthos_session": token}
    partial = dict(VALID); partial.pop("preferred_style")
    assert client.put("/api/profile", json=partial, cookies=c).json()["complete"] is False
    assert client.put("/api/profile", json={"preferred_style": "steady"}, cookies=c).json()["complete"] is True
