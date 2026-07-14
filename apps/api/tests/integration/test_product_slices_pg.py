"""Product-slice mounting — Thesis Ledger / Research Inbox / Learning Loop.

Locks the mounting contract: three INDEPENDENT default-off flags (disabled →
routes absent → 404), owner-session authorization on every mutation (404
posture for anonymous/non-owner), generated content always pending/draft
review, one-way state machines (409 on re-resolve/re-review), and no
trading/recommendation mutation coupling in any slice router.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.api.learning import router as learning_router
from apps.api.src.api.research_inbox import router as inbox_router
from apps.api.src.api.thesis import router as thesis_router
from apps.api.src.config import settings
from apps.api.src.db import get_session
from apps.api.src.db.models import Asset, Recommendation

pytestmark = pytest.mark.integration

OWNER_EMAIL = "owner@test.local"

_DDL = """
CREATE TABLE IF NOT EXISTS app_user (
    id VARCHAR(64) PRIMARY KEY,
    email VARCHAR(256) NOT NULL,
    display_name VARCHAR(128),
    auth_provider VARCHAR(32) NOT NULL DEFAULT 'password',
    password_hash TEXT,
    access_role VARCHAR(16),
    disabled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS user_session (
    token VARCHAR(128) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);
"""


@pytest.fixture
def slice_env(pg_session: Session, monkeypatch):
    pg_session.execute(text(_DDL))
    pg_session.execute(text("TRUNCATE app_user, user_session CASCADE"))
    pg_session.commit()
    monkeypatch.setattr(settings, "ARTHOS_OWNER_EMAILS", OWNER_EMAIL)

    app = FastAPI()
    app.include_router(thesis_router, prefix="/api")
    app.include_router(inbox_router, prefix="/api")
    app.include_router(learning_router, prefix="/api")
    app.dependency_overrides[get_session] = lambda: pg_session
    client = TestClient(app, raise_server_exceptions=False)

    uid = str(uuid.uuid4())
    cookie = "sess-" + uuid.uuid4().hex
    pg_session.execute(text("INSERT INTO app_user (id, email) VALUES (:i, :e)"),
                       {"i": uid, "e": OWNER_EMAIL})
    pg_session.execute(text(
        "INSERT INTO user_session (token, user_id, expires_at) "
        "VALUES (:t, :u, now() + interval '1 day')"), {"t": cookie, "u": uid})
    pg_session.commit()
    yield client, pg_session, {"arthos_session": cookie}
    pg_session.execute(text("TRUNCATE app_user, user_session CASCADE"))
    pg_session.commit()


# ---------------------------------------------------------------------------
# Flags: independent, default OFF, real app mounts nothing
# ---------------------------------------------------------------------------
def test_flags_default_off_and_independent():
    assert settings.THESIS_LEDGER_ENABLED is False
    assert settings.RESEARCH_INBOX_ENABLED is False
    assert settings.LEARNING_LOOP_ENABLED is False


def _flatten(routes) -> list:
    out = []
    for r in routes:
        inner = getattr(r, "original_router", None)
        sub = getattr(inner, "routes", None) or getattr(r, "routes", None)
        if sub:
            out.extend(_flatten(sub))
        elif getattr(r, "path", None) is not None:
            out.append(r)
    return out


def test_flags_off_real_app_has_no_slice_routes():
    import apps.api.src.main as m
    paths = [r.path for r in _flatten(m.app.routes)]
    assert paths
    assert not any(p.startswith("/theses") for p in paths)
    assert not any("/admin/inbox" in p for p in paths)
    assert not any("/admin/lessons" in p for p in paths)


# ---------------------------------------------------------------------------
# Authorization: every mutation owner-gated, 404 posture
# ---------------------------------------------------------------------------
ADMIN_CALLS = [
    ("POST", "/api/admin/theses", {"title": "t", "statement": "s",
                                   "wrong_if": "w", "scope": "company"}),
    ("POST", "/api/admin/inbox/tasks", {"title": "t", "question": "q"}),
    ("POST", "/api/admin/lessons", {"recommendation_id": "x", "thesis_id": "y",
                                    "what_happened": "w",
                                    "original_thesis_quote": "q"}),
]


@pytest.mark.parametrize("method,path,body", ADMIN_CALLS)
def test_anonymous_admin_mutations_404(slice_env, method, path, body):
    client, s, _cookies = slice_env
    r = client.request(method, path, json=body)
    assert r.status_code == 404  # undiscoverable without owner session


# ---------------------------------------------------------------------------
# Thesis: catalyst/risk CRUD one-way state machine
# ---------------------------------------------------------------------------
def _mk_thesis(client, cookies) -> str:
    r = client.post("/api/admin/theses", json={
        "title": "Test thesis", "statement": "Margins will expand because X.",
        "wrong_if": "Margins compress two quarters straight.",
        "scope": "theme", "horizon": "quarters",
    }, cookies=cookies)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_catalyst_risk_crud_and_one_way_resolution(slice_env):
    client, s, cookies = slice_env
    tid = _mk_thesis(client, cookies)
    # catalyst create → resolve → re-resolve 409
    c = client.post(f"/api/admin/theses/{tid}/catalysts",
                    json={"title": "Earnings call", "direction": "helps"},
                    cookies=cookies)
    assert c.status_code == 201, c.text
    cid = c.json()["id"]
    r1 = client.post(f"/api/admin/catalysts/{cid}/resolve",
                     json={"resolution": "beat"}, cookies=cookies)
    assert r1.status_code == 200 and r1.json()["resolved_at"]
    r2 = client.post(f"/api/admin/catalysts/{cid}/resolve",
                     json={"resolution": "again"}, cookies=cookies)
    assert r2.status_code == 409                      # no re-resolution
    # invalid direction rejected at the edge
    bad = client.post(f"/api/admin/theses/{tid}/catalysts",
                      json={"title": "x", "direction": "sideways"},
                      cookies=cookies)
    assert bad.status_code == 422
    # risk create → materialize → 409 on second materialization
    rk = client.post(f"/api/admin/theses/{tid}/risks",
                     json={"title": "Rate shock", "severity": "high"},
                     cookies=cookies)
    assert rk.status_code == 201
    rid = rk.json()["id"]
    m1 = client.post(f"/api/admin/risks/{rid}/materialize", cookies=cookies)
    assert m1.status_code == 200 and m1.json()["materialized_at"]
    m2 = client.post(f"/api/admin/risks/{rid}/materialize", cookies=cookies)
    assert m2.status_code == 409
    # unknown ids → 404
    assert client.post(f"/api/admin/catalysts/{uuid.uuid4()}/resolve",
                       json={"resolution": "x"},
                       cookies=cookies).status_code == 404
    assert client.post(f"/api/admin/risks/{uuid.uuid4()}/materialize",
                       cookies=cookies).status_code == 404


# ---------------------------------------------------------------------------
# Inbox: generated reports always pending; review carries identity; one-way
# ---------------------------------------------------------------------------
def test_inbox_generated_pending_review_workflow(slice_env):
    client, s, cookies = slice_env
    t = client.post("/api/admin/inbox/tasks",
                    json={"title": "Watch NVDA supply",
                          "question": "Any datacenter demand cracks?"},
                    cookies=cookies)
    assert t.status_code == 201, t.text
    task_id = t.json()["id"]
    rep = client.post(f"/api/admin/inbox/tasks/{task_id}/reports", json={
        "body": "Nothing material found.",
        "provenance": "generated",
        "citations": [{"url": "https://example.com/a",
                       "observed_at": dt.datetime.now(dt.timezone.utc).isoformat()}],
    }, cookies=cookies)
    assert rep.status_code == 201, rep.text
    r = rep.json()
    assert r["review_status"] == "pending"        # generated → forced pending
    assert r["reviewed_by"] is None
    # approve carries reviewer identity from the SESSION, not the body
    ap = client.post(f"/api/admin/inbox/reports/{r['id']}/approve",
                     cookies=cookies)
    assert ap.status_code == 200
    assert ap.json()["review_status"] == "approved"
    assert ap.json()["reviewed_by"] == OWNER_EMAIL
    # one-way: second review 409
    ag = client.post(f"/api/admin/inbox/reports/{r['id']}/reject",
                     cookies=cookies)
    assert ag.status_code == 409
    # pending filter now empty
    lst = client.get("/api/admin/inbox/reports?review_status=pending",
                     cookies=cookies)
    assert lst.json()["reports"] == []


# ---------------------------------------------------------------------------
# Learning: forced draft, hindsight guard, approve never flips thesis status
# ---------------------------------------------------------------------------
def test_lesson_forced_draft_hindsight_guard_and_review(slice_env):
    client, s, cookies = slice_env
    tid = _mk_thesis(client, cookies)
    # publish the thesis so revisions exist pre-recommendation
    st = client.patch(f"/api/admin/theses/{tid}/status",
                      json={"status": "active", "status_reason": "publishing"},
                      cookies=cookies)
    assert st.status_code == 200, st.text
    # a recommendation AFTER publication (hindsight guard anchor)
    asset = Asset(symbol=f"LS{uuid.uuid4().hex[:4].upper()}", asset_class="equity")
    s.add(asset)
    s.flush()
    rec = Recommendation(asset_id=asset.id, action="buy",
                         generated_at=dt.datetime.now(dt.timezone.utc)
                         + dt.timedelta(seconds=5))
    s.add(rec)
    s.commit()

    # hindsight guard: quote NOT in as-of-decision-time text → 422
    bad = client.post("/api/admin/lessons", json={
        "recommendation_id": rec.id, "thesis_id": tid,
        "what_happened": "It went up.",
        "original_thesis_quote": "text that was never in the thesis",
    }, cookies=cookies)
    assert bad.status_code == 422

    # verbatim quote from the statement → draft lesson
    ok = client.post("/api/admin/lessons", json={
        "recommendation_id": rec.id, "thesis_id": tid,
        "what_happened": "Margins expanded as expected.",
        "original_thesis_quote": "Margins will expand",
        "thesis_effect": "strengthened",
        "allow_unresolved_context": True,
    }, cookies=cookies)
    assert ok.status_code == 201, ok.text
    lesson = ok.json()
    assert lesson["review_state"] == "draft"      # ALWAYS drafts first
    assert lesson["reviewed_by"] is None

    ap = client.post(f"/api/admin/lessons/{lesson['id']}/approve",
                     cookies=cookies)
    assert ap.status_code == 200
    assert ap.json()["review_state"] == "approved"
    assert ap.json()["reviewed_by"] == OWNER_EMAIL
    # approving NEVER mutates thesis status
    detail = client.get(f"/api/theses/{tid}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "active"
    # one-way: re-review 409
    assert client.post(f"/api/admin/lessons/{lesson['id']}/reject",
                       cookies=cookies).status_code == 409


# ---------------------------------------------------------------------------
# No trading coupling: slice routers import no execution machinery
# ---------------------------------------------------------------------------
def test_slice_routers_import_no_execution_paths():
    import apps.api.src.api.learning as l
    import apps.api.src.api.research_inbox as ri
    import apps.api.src.api.thesis as th
    for mod in (th, ri, l):
        src = open(mod.__file__, encoding="utf-8").read()
        for banned in ("paper_execution", "submit_trade", "auto_trader",
                       "apps.api.src.options"):
            assert banned not in src, (mod.__name__, banned)
