"""Agent Gateway v0 — HTTP-level authz matrix + abuse tests (Priority 7).

Builds a minimal FastAPI app with the REAL gateway router, owner console
router, and audit middleware (the same objects main.py mounts when
AGENT_GATEWAY_ENABLED=True), pointed at the isolated test DB:
  * `db.SessionLocal` is monkeypatched to the test engine (the gateway
    dependency + middleware late-import it), and
  * `get_session` is dependency-overridden for the owner console.

agent_token / agent_audit / app_user / user_session are migration-only
tables — ensured idempotently here (M1C login_attempt precedent).

Covers the P7 verification matrix: owner-session-only minting, cookie/Bearer
non-interchangeability, full R/P/B/D cross-scope denials, revoked-token
replay, audit completeness + leak-freedom, rate-limit boundary/reset, size
caps, pagination abuse, DB-outage fail-closed, audit-write failure isolation,
concurrent token use, serialization leakage, and a route scan proving no
mutating trade endpoint exists.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

import apps.api.src.db as db_mod
from apps.api.src.api import agent_gateway as gw
from apps.api.src.api.agent_admin import router as admin_router
from apps.api.src.api.agent_gateway import AgentAuditMiddleware, router as gw_router
from apps.api.src.api.admin_guard import require_owner  # noqa: F401 (route dep)
from apps.api.src.config import settings
from apps.api.src.db import get_session
from apps.api.src.domain.agent_gateway import tokens

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

# same DDL as test_agent_gateway_pg.py (114 migration shape)
_DDL_AGENT = """
CREATE TABLE IF NOT EXISTS agent_token (
    id VARCHAR(36) PRIMARY KEY,
    agent_name VARCHAR(64) NOT NULL,
    token_prefix VARCHAR(8) NOT NULL,
    token_hash VARCHAR(64) NOT NULL,
    scopes VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    expires_at TIMESTAMPTZ NOT NULL,
    rate_limit_per_min INTEGER NOT NULL DEFAULT 60,
    max_request_bytes INTEGER NOT NULL DEFAULT 65536,
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    revoked_reason TEXT,
    CONSTRAINT uq_agent_token_prefix UNIQUE (token_prefix),
    CONSTRAINT uq_agent_token_hash UNIQUE (token_hash),
    CONSTRAINT ck_agent_token_status CHECK (status IN ('active','revoked')),
    CONSTRAINT ck_agent_token_scopes CHECK (scopes ~ '^[RPBD](,[RPBD]){0,3}$'),
    CONSTRAINT ck_agent_token_rate CHECK (rate_limit_per_min BETWEEN 1 AND 240),
    CONSTRAINT ck_agent_token_revoked CHECK
        (status <> 'revoked' OR revoked_at IS NOT NULL)
);
CREATE TABLE IF NOT EXISTS agent_audit (
    id VARCHAR(36) PRIMARY KEY,
    agent_name VARCHAR(64),
    token_prefix VARCHAR(8),
    route VARCHAR(128) NOT NULL,
    method VARCHAR(8) NOT NULL,
    scope_used VARCHAR(4),
    status_code INTEGER NOT NULL,
    idempotency_key VARCHAR(64),
    duration_ms INTEGER NOT NULL,
    request_hash VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def gw_env(pg_engine, pg_session: Session, monkeypatch):
    """App + client + db session, fully wired to the test DB."""
    pg_session.execute(text(_DDL))
    pg_session.execute(text(_DDL_AGENT))
    pg_session.execute(
        text("TRUNCATE agent_token, agent_audit, app_user, user_session CASCADE")
    )
    pg_session.commit()

    test_sessionmaker = sessionmaker(bind=pg_engine, class_=Session,
                                     expire_on_commit=False)
    monkeypatch.setattr(db_mod, "SessionLocal", test_sessionmaker)
    monkeypatch.setattr(settings, "ARTHOS_OWNER_EMAILS", OWNER_EMAIL)
    gw._limiter.reset()

    app = FastAPI()
    app.add_middleware(AgentAuditMiddleware)
    app.include_router(gw_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")
    app.dependency_overrides[get_session] = lambda: pg_session

    client = TestClient(app, raise_server_exceptions=False)
    yield app, client, pg_session
    pg_session.execute(
        text("TRUNCATE agent_token, agent_audit, app_user, user_session CASCADE")
    )
    pg_session.commit()


def _mk_owner(s: Session, email: str = OWNER_EMAIL) -> tuple[str, str]:
    """Insert an owner app_user + a live session; return (uid, cookie_token)."""
    uid = str(uuid.uuid4())
    cookie = "sess-" + uuid.uuid4().hex
    s.execute(
        text("INSERT INTO app_user (id, email) VALUES (:i, :e)"),
        {"i": uid, "e": email},
    )
    s.execute(
        text(
            "INSERT INTO user_session (token, user_id, expires_at) "
            "VALUES (:t, :u, now() + interval '1 day')"
        ),
        {"t": cookie, "u": uid},
    )
    s.commit()
    return uid, cookie


def _mint_http(client, cookie: str, scopes: list[str], **kw) -> dict:
    r = client.post(
        "/api/admin/agent-tokens",
        json={"agent_name": kw.pop("agent_name", "t-" + uuid.uuid4().hex[:6]),
              "scopes": scopes, **kw},
        cookies={"arthos_session": cookie},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _bearer(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def _audit_rows(s: Session) -> list[dict]:
    return [dict(r) for r in s.execute(
        text("SELECT * FROM agent_audit ORDER BY created_at")
    ).mappings().all()]


# ---------------------------------------------------------------------------
# Owner console authz
# ---------------------------------------------------------------------------
def test_mint_requires_owner_session(gw_env):
    app, client, s = gw_env
    # no cookie → 404 (undiscoverable)
    r = client.post("/api/admin/agent-tokens",
                    json={"agent_name": "x", "scopes": ["R"]})
    assert r.status_code == 404
    # non-owner session → 404
    _uid, cookie = _mk_owner(s, email="notowner@test.local")
    r = client.post("/api/admin/agent-tokens",
                    json={"agent_name": "x", "scopes": ["R"]},
                    cookies={"arthos_session": cookie})
    assert r.status_code == 404
    # owner session → 200, secret returned exactly once
    _uid, cookie = _mk_owner(s)
    out = _mint_http(client, cookie, ["R"])
    assert out["token"].startswith("arthos_at_")
    # list never returns the token or hash
    r = client.get("/api/admin/agent-tokens", cookies={"arthos_session": cookie})
    body = r.text
    assert out["token"] not in body and "token_hash" not in body
    assert out["token_prefix"] in body


def test_gateway_token_cannot_access_owner_console(gw_env):
    app, client, s = gw_env
    _uid, cookie = _mk_owner(s)
    out = _mint_http(client, cookie, ["R", "P", "B", "D"])
    # Bearer on the console (no cookie) → 404: agent auth is invalid there
    r = client.post("/api/admin/agent-tokens",
                    json={"agent_name": "x", "scopes": ["R"]},
                    headers=_bearer(out["token"]))
    assert r.status_code == 404
    r = client.get("/api/admin/agent-tokens", headers=_bearer(out["token"]))
    assert r.status_code == 404


def test_revoke_requires_owner_and_kills_replay(gw_env):
    app, client, s = gw_env
    _uid, cookie = _mk_owner(s)
    out = _mint_http(client, cookie, ["R"])
    assert client.get("/api/agent/whoami", headers=_bearer(out["token"])).status_code == 200
    # non-owner cannot revoke
    r = client.post(f"/api/admin/agent-tokens/{out['id']}/revoke", json={})
    assert r.status_code == 404
    # owner revokes → replay of the same bearer fails closed
    r = client.post(f"/api/admin/agent-tokens/{out['id']}/revoke",
                    json={"reason": "test"}, cookies={"arthos_session": cookie})
    assert r.status_code == 200
    assert client.get("/api/agent/whoami", headers=_bearer(out["token"])).status_code == 401


# ---------------------------------------------------------------------------
# Cookie/Bearer non-interchangeability
# ---------------------------------------------------------------------------
def test_no_cookie_fallback_on_gateway(gw_env):
    app, client, s = gw_env
    _uid, cookie = _mk_owner(s)
    # a perfectly valid OWNER session cookie is anonymous on /agent
    r = client.get("/api/agent/whoami", cookies={"arthos_session": cookie})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Cross-scope matrix — every scope × every route
# ---------------------------------------------------------------------------
ROUTES = [
    ("GET", "/api/agent/whoami", "R"),
    ("GET", "/api/agent/recommendations", "R"),
    ("GET", "/api/agent/portfolio", "P"),
    ("GET", "/api/agent/portfolio/trades", "P"),
    ("POST", "/api/agent/jobs", "B"),
    ("POST", "/api/agent/drafts", "D"),
]


def test_cross_scope_denial_matrix(gw_env):
    app, client, s = gw_env
    _uid, cookie = _mk_owner(s)
    toks = {sc: _mint_http(client, cookie, [sc])["token"] for sc in "RPBD"}
    for held in "RPBD":
        for method, path, needed in ROUTES:
            r = client.request(method, path, headers=_bearer(toks[held]))
            if held == needed:
                # scope admits the call; body-less POSTs then fail Pydantic
                # validation (422) — never an authz outcome
                assert r.status_code in (200, 202, 422, 501), (held, path, r.status_code)
            else:
                assert r.status_code == 403, (held, path, r.status_code)


# ---------------------------------------------------------------------------
# Audit completeness + leak freedom
# ---------------------------------------------------------------------------
def test_audit_rows_for_success_and_failures_no_secrets(gw_env):
    app, client, s = gw_env
    _uid, cookie = _mk_owner(s)
    out = _mint_http(client, cookie, ["R"])
    tok = out["token"]
    client.get("/api/agent/whoami", headers=_bearer(tok))            # 200
    client.get("/api/agent/whoami")                                   # 401
    client.get("/api/agent/portfolio", headers=_bearer(tok))          # 403
    rows = _audit_rows(s)
    codes = sorted(r["status_code"] for r in rows)
    assert codes == [200, 401, 403], codes
    # exactly one row per request; templated route (normalized, no /api
    # prefix — uniform regardless of router nesting); no secret anywhere
    assert all(r["route"].startswith("/agent") for r in rows)
    blob = " ".join(str(v) for r in rows for v in r.values())
    assert tok not in blob
    assert out["token_prefix"] in blob  # prefix IS the audit key
    # 401 row still carries no identity but is present
    anon = [r for r in rows if r["status_code"] == 401][0]
    assert anon["agent_name"] is None


def test_denied_requests_keep_creating_bounded_audit_rows(gw_env):
    app, client, s = gw_env
    for _ in range(5):
        client.get("/api/agent/whoami", headers=_bearer("Bearer garbage"))
    rows = _audit_rows(s)
    assert len(rows) == 5 and all(r["status_code"] == 401 for r in rows)


# ---------------------------------------------------------------------------
# Malformed auth + size abuse
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("hdr", [
    None,
    "",
    "Bearer",
    "Bearer ",
    "Basic dXNlcjpwYXNz",
    "Bearer arthos_session_cookievalue",
    "Bearer arthos_at_tooShort",
    "Bearer " + "arthos_at_" + "f" * 400,   # oversized token body
    "NotAScheme arthos_at_" + "a" * 40,
])
def test_malformed_authorization_headers_401(gw_env, hdr):
    app, client, s = gw_env
    headers = {"Authorization": hdr} if hdr is not None else {}
    r = client.get("/api/agent/whoami", headers=headers)
    assert r.status_code == 401


def test_oversized_body_413_pre_auth(gw_env):
    app, client, s = gw_env
    r = client.post("/api/agent/jobs",
                    headers={"Content-Length": str(2_000_000)})
    assert r.status_code == 413


def test_oversized_query_string_414(gw_env):
    app, client, s = gw_env
    r = client.get("/api/agent/recommendations?junk=" + "x" * 3000)
    assert r.status_code == 414


def test_pagination_abuse_rejected(gw_env):
    app, client, s = gw_env
    _uid, cookie = _mk_owner(s)
    tok = _mint_http(client, cookie, ["R"])["token"]
    assert client.get("/api/agent/recommendations?limit=500",
                      headers=_bearer(tok)).status_code == 422
    assert client.get("/api/agent/recommendations?limit=0",
                      headers=_bearer(tok)).status_code == 422
    assert client.get("/api/agent/recommendations?offset=999999999",
                      headers=_bearer(tok)).status_code == 422


# ---------------------------------------------------------------------------
# Rate limit boundary + reset + concurrency
# ---------------------------------------------------------------------------
def test_rate_limit_boundary_and_reset(gw_env):
    app, client, s = gw_env
    _uid, cookie = _mk_owner(s)
    tok = _mint_http(client, cookie, ["R"], rate_limit_per_min=3)["token"]
    codes = [client.get("/api/agent/whoami", headers=_bearer(tok)).status_code
             for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    # 429 is audited
    assert any(r["status_code"] == 429 for r in _audit_rows(s))
    # window reset → allowed again
    gw._limiter.reset()
    assert client.get("/api/agent/whoami", headers=_bearer(tok)).status_code == 200


def test_concurrent_use_of_one_token(gw_env):
    app, client, s = gw_env
    _uid, cookie = _mk_owner(s)
    tok = _mint_http(client, cookie, ["R"], rate_limit_per_min=240)["token"]
    results: list[int] = []
    lock = threading.Lock()

    def call():
        code = client.get("/api/agent/whoami", headers=_bearer(tok)).status_code
        with lock:
            results.append(code)

    threads = [threading.Thread(target=call) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 10 and all(c == 200 for c in results)


# ---------------------------------------------------------------------------
# Failure isolation — audit write failure + DB outage
# ---------------------------------------------------------------------------
def test_audit_write_failure_does_not_break_response(gw_env, monkeypatch):
    app, client, s = gw_env
    _uid, cookie = _mk_owner(s)
    tok = _mint_http(client, cookie, ["R"])["token"]
    from apps.api.src.domain.agent_gateway import audit as audit_mod

    def boom(*a, **k):
        raise RuntimeError("audit db down")

    monkeypatch.setattr(audit_mod, "record", boom)
    r = client.get("/api/agent/whoami", headers=_bearer(tok))
    assert r.status_code == 200  # request outcome unchanged


def test_db_outage_fails_closed_503(gw_env, monkeypatch):
    app, client, s = gw_env

    class Boom:
        def __call__(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(db_mod, "SessionLocal", Boom())
    r = client.get("/api/agent/whoami",
                   headers=_bearer("arthos_at_" + "a" * 40))
    assert r.status_code == 503  # never 200, never fail-open


# ---------------------------------------------------------------------------
# R/P route behavior + cross-user isolation
# ---------------------------------------------------------------------------
def _seed_rec(s: Session, symbol: str = "TSTA") -> str:
    aid, rid = str(uuid.uuid4()), str(uuid.uuid4())
    s.execute(text(
        "INSERT INTO asset (id, symbol, asset_class, currency, is_active,"
        " created_at, updated_at) VALUES (:a, :sym, 'equity', 'USD', true,"
        " now(), now())"), {"a": aid, "sym": symbol})
    s.execute(text(
        "INSERT INTO recommendation (id, asset_id, generated_at, action,"
        " conviction, rationale, model_version, created_at) VALUES"
        " (:r, :a, now(), 'buy', 72.5, :rat, 'secret-model-v9', now())"),
        {"r": rid, "a": aid, "rat": "test rationale"})
    s.execute(text(
        "INSERT INTO recommendation_evidence (id, recommendation_id,"
        " evidence_type, source, summary, weight, created_at) VALUES"
        " (:i, :r, 'factor', 'unit-test', 'momentum positive', 0.4, now())"),
        {"i": str(uuid.uuid4()), "r": rid})
    s.commit()
    return rid


def test_r_routes_list_and_detail_public_safe(gw_env):
    app, client, s = gw_env
    rid = _seed_rec(s)
    _uid, cookie = _mk_owner(s)
    tok = _mint_http(client, cookie, ["R"])["token"]
    r = client.get("/api/agent/recommendations", headers=_bearer(tok))
    assert r.status_code == 200
    body = r.json()
    assert body["recommendations"] and body["recommendations"][0]["symbol"] == "TSTA"
    # model internals never serialized
    assert "secret-model-v9" not in r.text
    assert "model_version" not in r.text and "snapshot_hash" not in r.text
    d = client.get(f"/api/agent/recommendations/{rid}", headers=_bearer(tok))
    assert d.status_code == 200
    assert d.json()["evidence"][0]["type"] == "factor"
    # unknown id → 404
    assert client.get(f"/api/agent/recommendations/{uuid.uuid4()}",
                      headers=_bearer(tok)).status_code == 404


def _seed_book(s: Session, user_id: str, symbol: str, cash: str) -> None:
    from apps.api.src.domain.paper_trading.paper_service import (
        user_stock_portfolio_name,
    )
    aid, pid = str(uuid.uuid4()), str(uuid.uuid4())
    s.execute(text(
        "INSERT INTO asset (id, symbol, asset_class, currency, is_active,"
        " created_at, updated_at) VALUES (:a, :sym, 'equity', 'USD', true,"
        " now(), now())"), {"a": aid, "sym": symbol})
    s.execute(text(
        "INSERT INTO paper_portfolio (id, name, starting_cash, cash,"
        " is_active, created_at, updated_at) VALUES (:p, :n, 100000, :c,"
        " true, now(), now())"),
        {"p": pid, "n": user_stock_portfolio_name(user_id), "c": cash})
    s.execute(text(
        "INSERT INTO paper_position (id, portfolio_id, asset_id, quantity,"
        " avg_cost, is_open, opened_at, updated_at) VALUES (:i, :p, :a, 10,"
        " 50.5, true, now(), now())"),
        {"i": str(uuid.uuid4()), "p": pid, "a": aid})
    s.execute(text(
        "INSERT INTO paper_trade (id, portfolio_id, asset_id, side, quantity,"
        " fill_price, fill_ts, submitted_at, commission, created_at) VALUES"
        " (:i, :p, :a, 'buy', 10, 50.5, now(), now(), 1.0, now())"),
        {"i": str(uuid.uuid4()), "p": pid, "a": aid})
    s.commit()


def test_p_routes_own_book_only_cross_user_isolated(gw_env):
    app, client, s = gw_env
    _uid, cookie = _mk_owner(s)
    tok_a = _mint_http(client, cookie, ["P"])
    tok_b = _mint_http(client, cookie, ["P"])
    # NB: created_by is the OWNER uid for both in v0 — simulate two distinct
    # principals by rewriting created_by (multi-user future, T6 posture)
    s.execute(text("UPDATE agent_token SET created_by = 'userA' WHERE id = :i"),
              {"i": tok_a["id"]})
    s.execute(text("UPDATE agent_token SET created_by = 'userB' WHERE id = :i"),
              {"i": tok_b["id"]})
    s.commit()
    _seed_book(s, "userA", "AAPA", "90000")
    _seed_book(s, "userB", "BBBB", "80000")

    ra = client.get("/api/agent/portfolio", headers=_bearer(tok_a["token"])).json()
    rb = client.get("/api/agent/portfolio", headers=_bearer(tok_b["token"])).json()
    assert ra["cash"] == 90000.0 and rb["cash"] == 80000.0
    assert [p["symbol"] for p in ra["positions"]] == ["AAPA"]
    assert [p["symbol"] for p in rb["positions"]] == ["BBBB"]
    # A's payload contains nothing of B's
    ta = client.get("/api/agent/portfolio/trades", headers=_bearer(tok_a["token"]))
    assert "BBBB" not in ta.text and "AAPA" in ta.text
    # no portfolio id ever crosses the boundary
    assert "portfolio_id" not in ta.text
    for payload in (ra, rb):
        assert "id" not in payload and "portfolio_id" not in payload


def test_p_route_no_book_yet_is_empty_not_error(gw_env):
    app, client, s = gw_env
    _uid, cookie = _mk_owner(s)
    tok = _mint_http(client, cookie, ["P"])["token"]
    r = client.get("/api/agent/portfolio", headers=_bearer(tok))
    assert r.status_code == 200 and r.json()["exists"] is False


# ---------------------------------------------------------------------------
# Route scan — no mutating trade surface exists (spec §3/§7, NON-GOALS)
# ---------------------------------------------------------------------------
def _flatten_routes(routes) -> list:
    """Recursively flatten nested-router route objects (this FastAPI keeps
    included routers as a single nested entry in app.routes)."""
    out = []
    for r in routes:
        inner = getattr(r, "original_router", None)  # fastapi _IncludedRouter
        sub = getattr(inner, "routes", None) or getattr(r, "routes", None)
        if sub:
            out.extend(_flatten_routes(sub))
        elif getattr(r, "path", None) is not None:
            out.append(r)
    return out


def test_route_scan_no_trade_mutation_endpoints(gw_env):
    app, client, s = gw_env
    agent_routes = [r for r in _flatten_routes(app.routes)
                    if r.path.startswith("/agent")]
    assert agent_routes, "gateway routes must be mounted in this app"
    for r in agent_routes:
        methods = getattr(r, "methods", set()) or set()
        assert not ({"PUT", "PATCH", "DELETE"} & methods), r.path
        if "POST" in methods:
            assert r.path in ("/agent/jobs", "/agent/drafts",
                              "/agent/jobs/{job_uid}/cancel"), r.path
            # no write-capable route may carry trade vocabulary at all
            for bad in ("trade", "order", "buy", "sell", "position"):
                assert bad not in r.path.lower(), r.path
        # trade-EXECUTION vocabulary banned on EVERY route (job cancel is a
        # queued-job control, not order cancellation; portfolio/trades is a
        # read-only history view — both legitimate)
        for bad in ("execute", "submit_trade", "/order", "broker"):
            assert bad not in r.path.lower(), r.path


def test_gateway_module_imports_no_execution_paths():
    """The gateway module must never import trade-execution machinery."""
    banned = (
        "paper_execution",          # submit_trade path
        "apps.api.src.options",     # options engine
        "auto_trader",
    )
    src = open(gw.__file__, encoding="utf-8").read()
    for b in banned:
        assert b not in src, f"forbidden import surface: {b}"


# ---------------------------------------------------------------------------
# Flag off → the REAL app has no /agent routes and no console
# ---------------------------------------------------------------------------
def test_flag_off_real_app_has_no_agent_routes():
    assert settings.AGENT_GATEWAY_ENABLED is False  # default must stay off
    import apps.api.src.main as m

    paths = [r.path for r in _flatten_routes(m.app.routes)]
    assert paths, "main app must have routes"
    assert not any("/agent/" in p or p.endswith("/agent") for p in paths)
    assert not any("agent-tokens" in p for p in paths)
