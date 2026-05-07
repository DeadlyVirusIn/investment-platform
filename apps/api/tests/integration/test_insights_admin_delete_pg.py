"""Phase F5 integration: admin-only DELETE /api/insights/cache.

Mounted ONLY when AGENT_INSIGHTS_ADMIN_MAINTENANCE_ENABLED=true AND
RESEARCH_ADMIN_TOKEN is non-empty. Requires the same `X-Admin-Token`
header as research_manual. Wipes only `agent_insight`, never
touches any other table.
"""

from __future__ import annotations

from importlib import reload

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.config import settings
from apps.api.src.db import get_session
from apps.api.src.db.models import AgentInsight
from apps.api.src.domain.agents.registry import BANNER


pytestmark = pytest.mark.integration


_ADMIN_TOKEN = "f5-test-admin-token"


def _seed_one_row(SessionCls) -> None:
    with SessionCls() as s:
        s.add(AgentInsight(
            kind="trade_quality",
            payload_hash="h" * 64,
            payload_redacted={"score": 72},
            content_markdown=f"{BANNER}\nseed",
            model="claude-test",
            source_endpoint="/api/x",
            banner=BANNER,
            safety_version="v1",
        ))
        s.commit()


def _row_count(SessionCls) -> int:
    with SessionCls() as s:
        return len(s.execute(select(AgentInsight)).scalars().all())


@pytest.fixture
def pg_app_client_admin_on(pg_engine, monkeypatch):
    """Re-import main with the admin gate ON so the DELETE route
    is mounted. Tears the app overrides down on exit."""
    monkeypatch.setattr(
        settings, "AGENT_INSIGHTS_ADMIN_MAINTENANCE_ENABLED", True,
    )
    monkeypatch.setattr(settings, "RESEARCH_ADMIN_TOKEN", _ADMIN_TOKEN)

    # Re-import main so the conditional `app.include_router(...)`
    # runs against the patched flag.
    import apps.api.src.main as main_mod
    reload(main_mod)
    app = main_mod.app

    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )

    def _override():
        s = SessionCls()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app), SessionCls
    finally:
        app.dependency_overrides.pop(get_session, None)
        # Restore main without the admin route for downstream tests.
        monkeypatch.setattr(
            settings,
            "AGENT_INSIGHTS_ADMIN_MAINTENANCE_ENABLED", False,
        )
        reload(main_mod)


@pytest.fixture(autouse=True)
def _truncate_cache(pg_engine):
    from sqlalchemy import text as _text
    with pg_engine.begin() as conn:
        conn.execute(_text(
            "TRUNCATE TABLE agent_insight RESTART IDENTITY CASCADE",
        ))
    yield


# ---------------------------------------------------------------------
# Default: admin route is NOT mounted
# ---------------------------------------------------------------------

def test_admin_route_unmounted_by_default():
    """With the admin maintenance flag at its default false, the
    DELETE route MUST NOT be registered."""
    from apps.api.src.main import app

    paths = {
        getattr(r, "path", "") for r in app.routes
    }
    assert "/api/insights/cache" not in paths


# ---------------------------------------------------------------------
# Admin route mounted: delete behavior + auth
# ---------------------------------------------------------------------

def test_admin_delete_requires_token(pg_app_client_admin_on):
    client, SessionCls = pg_app_client_admin_on
    _seed_one_row(SessionCls)

    # No header at all → FastAPI rejects with 422 (missing required
    # header). Either way, NOT a 200 and the row remains.
    r = client.delete("/api/insights/cache")
    assert r.status_code in (401, 403, 422)
    assert _row_count(SessionCls) == 1


def test_admin_delete_rejects_wrong_token(pg_app_client_admin_on):
    client, SessionCls = pg_app_client_admin_on
    _seed_one_row(SessionCls)

    r = client.delete(
        "/api/insights/cache",
        headers={"X-Admin-Token": "wrong"},
    )
    assert r.status_code == 403
    assert _row_count(SessionCls) == 1


def test_admin_delete_clears_only_agent_insight(
    pg_app_client_admin_on, pg_engine,
):
    client, SessionCls = pg_app_client_admin_on
    _seed_one_row(SessionCls)
    # Add a second row with a different natural key so we delete
    # more than one and confirm bulk truncation works.
    with SessionCls() as s:
        s.add(AgentInsight(
            kind="risk_commentary",
            payload_hash="g" * 64,
            payload_redacted={"nav": 100000},
            content_markdown=f"{BANNER}\nseed-2",
            model="claude-test",
            source_endpoint="/api/y",
            banner=BANNER,
            safety_version="v1",
        ))
        s.commit()

    # Snapshot a sample of execution tables that should not change.
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy import text as _text

    insp = sa_inspect(pg_engine)
    existing = set(insp.get_table_names())
    candidates = (
        "paper_trade", "paper_position", "paper_equity_snapshot",
        "decision_log", "recommendation",
    )
    sampled = [t for t in candidates if t in existing]
    assert sampled, "no execution tables in testcontainer schema"

    def _counts() -> dict[str, int]:
        with pg_engine.begin() as conn:
            return {
                t: int(conn.execute(_text(
                    f'SELECT count(*) FROM "{t}"'
                )).scalar() or 0)
                for t in sampled
            }

    before = _counts()
    assert _row_count(SessionCls) == 2

    r = client.delete(
        "/api/insights/cache",
        headers={"X-Admin-Token": _ADMIN_TOKEN},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted_rows"] == 2
    assert body["table"] == "agent_insight"

    # Cache cleared.
    assert _row_count(SessionCls) == 0
    # Execution tables untouched.
    after = _counts()
    assert before == after


def test_admin_delete_idempotent_on_empty_cache(pg_app_client_admin_on):
    client, SessionCls = pg_app_client_admin_on
    assert _row_count(SessionCls) == 0

    r = client.delete(
        "/api/insights/cache",
        headers={"X-Admin-Token": _ADMIN_TOKEN},
    )
    assert r.status_code == 200
    assert r.json()["deleted_rows"] == 0
