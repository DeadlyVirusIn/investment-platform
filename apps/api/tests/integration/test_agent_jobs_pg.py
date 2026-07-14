"""Agent Gateway B/D contracts — jobs, bounded SSE, drafts (real PostgreSQL).

Covers the P7 B/D verification matrix: frozen job-type dispatch (casing /
Unicode / traversal / type tricks all rejected), atomic idempotency under
races, advisory-locked queue cap under concurrent submissions, terminal
immutability, capped failure summaries, research_run registry rows, offline
runner isolation (no request-handler execution), SSE bounds (events cap,
time cap, heartbeat, eviction, auth expiry mid-stream, DB failure, audit
with emitted count), draft forced-pending + agent provenance, and
source-level bans on shell/eval/exec/dynamic-import/URL-fetch paths.

agent_job / agent_job_event / agent_idempotency are migration-116 tables —
ensured idempotently here (login_attempt precedent; migration itself is
ephemeral-validated separately).
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
from apps.api.src.config import settings
from apps.api.src.db import get_session
from apps.api.src.domain.agent_gateway import jobs as jobs_svc
from apps.api.src.domain.agent_gateway import tokens

from .test_agent_gateway_http_pg import _DDL, _DDL_AGENT  # app_user/session + 114 tables

pytestmark = pytest.mark.integration

OWNER_EMAIL = "owner@test.local"

# migration-116 shapes (+ ensure app_user.access_role exists — an earlier
# test file may have created app_user from a variant DDL without it)
_DDL_JOBS = """
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS access_role VARCHAR(16);
CREATE TABLE IF NOT EXISTS agent_job (
    id VARCHAR(36) PRIMARY KEY,
    job_uid VARCHAR(32) NOT NULL,
    job_type VARCHAR(32) NOT NULL,
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    seed BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'queued',
    token_prefix VARCHAR(8) NOT NULL,
    created_by VARCHAR(64) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    research_run_id VARCHAR(36),
    result_summary VARCHAR(2000),
    error_summary VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    research_task_id VARCHAR(36) REFERENCES research_task(id)
        ON DELETE RESTRICT,
    CONSTRAINT uq_agent_job_uid UNIQUE (job_uid),
    CONSTRAINT ck_agent_job_type CHECK (job_type IN
      ('calibration_study','walk_forward_baseline','drift_report','attribution_fixture')),
    CONSTRAINT ck_agent_job_status CHECK (status IN
      ('queued','running','succeeded','failed','cancelled')),
    CONSTRAINT ck_agent_job_finished CHECK
      (status IN ('queued','running') OR finished_at IS NOT NULL),
    CONSTRAINT ck_agent_job_error CHECK
      (status <> 'failed' OR error_summary IS NOT NULL),
    CONSTRAINT ck_agent_job_params_size CHECK (pg_column_size(params) <= 16384)
);
-- migration-121 column (idempotent for tables created by earlier files)
ALTER TABLE agent_job ADD COLUMN IF NOT EXISTS research_task_id VARCHAR(36)
  REFERENCES research_task(id) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS ix_agent_job_owner_status
  ON agent_job (created_by, status);
CREATE TABLE IF NOT EXISTS agent_job_event (
    id VARCHAR(36) PRIMARY KEY,
    job_id VARCHAR(36) NOT NULL REFERENCES agent_job(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    event_type VARCHAR(24) NOT NULL,
    payload VARCHAR(500) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_agent_job_event_seq UNIQUE (job_id, seq),
    CONSTRAINT ck_agent_job_event_seq CHECK (seq >= 1)
);
CREATE TABLE IF NOT EXISTS agent_idempotency (
    id VARCHAR(36) PRIMARY KEY,
    token_prefix VARCHAR(8) NOT NULL,
    idem_key VARCHAR(64) NOT NULL,
    kind VARCHAR(8) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    ref_id VARCHAR(36) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_agent_idem_token_key UNIQUE (token_prefix, idem_key),
    CONSTRAINT ck_agent_idem_kind CHECK (kind IN ('job','draft'))
);
"""

_TABLES = ("agent_idempotency", "agent_job_event", "agent_job",
           "agent_token", "agent_audit", "app_user", "user_session")


@pytest.fixture
def jb_env(pg_engine, pg_session: Session, monkeypatch):
    pg_session.execute(text(_DDL))
    pg_session.execute(text(_DDL_AGENT))
    pg_session.execute(text(_DDL_JOBS))
    pg_session.execute(text(f"TRUNCATE {', '.join(_TABLES)} CASCADE"))
    pg_session.commit()

    test_sm = sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)
    monkeypatch.setattr(db_mod, "SessionLocal", test_sm)
    monkeypatch.setattr(settings, "ARTHOS_OWNER_EMAILS", OWNER_EMAIL)
    gw._limiter.reset()
    gw._sse_generation.clear()

    app = FastAPI()
    app.add_middleware(AgentAuditMiddleware)
    app.include_router(gw_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")
    app.dependency_overrides[get_session] = lambda: pg_session
    client = TestClient(app, raise_server_exceptions=False)
    yield app, client, pg_session, test_sm
    pg_session.rollback()
    pg_session.execute(text(f"TRUNCATE {', '.join(_TABLES)} CASCADE"))
    pg_session.commit()


def _ident(db: Session, scopes="B,D", created_by="owner-1") -> tuple[dict, str]:
    """Mint directly at the service layer; return (resolved ident, token)."""
    full, meta = tokens.create_token(
        db, agent_name="jobs-agent", scopes=scopes, created_by=created_by,
        ttl_days=30, max_ttl_days=90, rate_limit_per_min=240,
    )
    db.commit()
    ident = tokens.resolve_token(db, full)
    db.commit()
    return ident, full


def _params():
    return {"start": "2026-01-01", "end": "2026-03-01", "bins": 10}


# ---------------------------------------------------------------------------
# Submission + registry + idempotency
# ---------------------------------------------------------------------------
def test_submit_creates_job_and_research_run_row(jb_env):
    app, client, s, sm = jb_env
    ident, _ = _ident(s)
    job, replayed = jobs_svc.submit_job(
        s, ident=ident, job_type="calibration_study", params=_params(),
        idempotency_key="k1", seed=42)
    s.commit()
    assert not replayed and job["status"] == "queued" and job["seed"] == 42
    rr = s.execute(text(
        "SELECT run_type, status, random_seed, parameters, config_hash "
        "FROM research_run WHERE id = (SELECT research_run_id FROM agent_job "
        "WHERE job_uid = :u)"), {"u": job["job_uid"]}).mappings().one()
    assert rr["run_type"] == "agent_job" and rr["random_seed"] == 42
    assert rr["parameters"]["bins"] == 10 and len(rr["config_hash"]) == 64


def test_idempotent_replay_and_conflict(jb_env):
    app, client, s, sm = jb_env
    ident, _ = _ident(s)
    j1, r1 = jobs_svc.submit_job(s, ident=ident, job_type="calibration_study",
                                 params=_params(), idempotency_key="kX", seed=7)
    s.commit()
    j2, r2 = jobs_svc.submit_job(s, ident=ident, job_type="calibration_study",
                                 params=_params(), idempotency_key="kX", seed=7)
    s.commit()
    assert (r1, r2) == (False, True) and j2["job_uid"] == j1["job_uid"]
    with pytest.raises(jobs_svc.IdempotencyConflict):
        jobs_svc.submit_job(s, ident=ident, job_type="drift_report",
                            params={"reference_days": 30, "current_days": 7},
                            idempotency_key="kX", seed=7)
    s.rollback()


def test_idempotency_atomic_under_race(jb_env):
    """N threads, same key, same request → exactly ONE job row; every
    thread gets the same job_uid back."""
    app, client, s, sm = jb_env
    ident, _ = _ident(s)
    results, errs = [], []

    def submit():
        db = sm()
        try:
            job, _rep = jobs_svc.submit_job(
                db, ident=ident, job_type="attribution_fixture", params={},
                idempotency_key="race-key", seed=1)
            db.commit()
            results.append(job["job_uid"])
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            errs.append(exc)
        finally:
            db.close()

    threads = [threading.Thread(target=submit) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errs and len(set(results)) == 1
    n = s.execute(text("SELECT count(*) FROM agent_job")).scalar()
    assert n == 1


def test_queue_cap_five_and_concurrent_submissions(jb_env):
    app, client, s, sm = jb_env
    ident, _ = _ident(s)
    for i in range(5):
        jobs_svc.submit_job(s, ident=ident, job_type="attribution_fixture",
                            params={}, idempotency_key=f"cap-{i}", seed=i)
    s.commit()
    with pytest.raises(jobs_svc.QueueFull):
        jobs_svc.submit_job(s, ident=ident, job_type="attribution_fixture",
                            params={}, idempotency_key="cap-6", seed=6)
    s.rollback()
    # concurrent distinct keys from a fresh owner never overshoot the cap
    ident2, _ = _ident(s, created_by="owner-2")
    errs, oks = [], []

    def submit(i):
        db = sm()
        try:
            jobs_svc.submit_job(db, ident=ident2,
                                job_type="attribution_fixture", params={},
                                idempotency_key=f"cc-{i}", seed=i)
            db.commit()
            oks.append(i)
        except jobs_svc.QueueFull:
            db.rollback()
            errs.append(i)
        finally:
            db.close()

    threads = [threading.Thread(target=submit, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    n = s.execute(text(
        "SELECT count(*) FROM agent_job WHERE created_by='owner-2' "
        "AND status IN ('queued','running')")).scalar()
    assert n == 5 and len(oks) == 5 and len(errs) == 3


# ---------------------------------------------------------------------------
# Dispatch hardening — exact-match only
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad_type", [
    "Calibration_Study",              # casing
    "CALIBRATION_STUDY",
    " calibration_study",             # whitespace
    "calibration_study\x00",          # NUL
    "calibration_ѕtudy",              # Cyrillic 's' confusable
    "../drift_report",                # traversal
    "drift_report; rm -rf /",         # shell fragment
    "os.system",                      # module path
    "http://evil/x",                  # URL
    "SELECT 1",                       # SQL
    123, None, ["drift_report"], {"j": 1},   # type tricks
])
def test_job_type_dispatch_cannot_be_bypassed(jb_env, bad_type):
    app, client, s, sm = jb_env
    ident, _ = _ident(s)
    with pytest.raises(jobs_svc.InvalidJob):
        jobs_svc.submit_job(s, ident=ident, job_type=bad_type, params={},
                            idempotency_key="bt", seed=1)
    s.rollback()


@pytest.mark.parametrize("bad_params", [
    {"start": "2026-01-01", "end": "2026-03-01", "bins": 10, "extra": 1},
    {"start": "2026-01-01", "end": "2036-03-01", "bins": 10},   # window too big
    {"start": "2026-03-01", "end": "2026-01-01", "bins": 10},   # reversed
    {"start": "1999-01-01", "end": "2026-01-01", "bins": 10},   # too old
    {"start": "2026-01-01", "end": "2026-03-01", "bins": 999},  # bins range
    {"start": "2026-01-01", "end": "2026-03-01", "bins": "10"},  # type
])
def test_param_schemas_bounded(jb_env, bad_params):
    app, client, s, sm = jb_env
    ident, _ = _ident(s)
    with pytest.raises(jobs_svc.InvalidJob):
        jobs_svc.submit_job(s, ident=ident, job_type="calibration_study",
                            params=bad_params, idempotency_key="bp", seed=1)
    s.rollback()


def test_symbol_and_seed_bounds(jb_env):
    app, client, s, sm = jb_env
    ident, _ = _ident(s)
    with pytest.raises(jobs_svc.InvalidJob):
        jobs_svc.submit_job(s, ident=ident, job_type="attribution_fixture",
                            params={"symbols": ["A" * 13]},
                            idempotency_key="sy1", seed=1)
    s.rollback()
    with pytest.raises(jobs_svc.InvalidJob):
        jobs_svc.submit_job(s, ident=ident, job_type="attribution_fixture",
                            params={"symbols": [f"S{i}" for i in range(21)]},
                            idempotency_key="sy2", seed=1)
    s.rollback()
    with pytest.raises(jobs_svc.InvalidJob):
        jobs_svc.submit_job(s, ident=ident, job_type="attribution_fixture",
                            params={}, idempotency_key="sd", seed=2**31)
    s.rollback()
    # server-generated seed recorded when omitted
    job, _ = jobs_svc.submit_job(s, ident=ident,
                                 job_type="attribution_fixture", params={},
                                 idempotency_key="sd2")
    s.commit()
    assert isinstance(job["seed"], int) and 0 <= job["seed"] < 2**31


# ---------------------------------------------------------------------------
# Runner: success, capped failure, terminal immutability, no side effects
# ---------------------------------------------------------------------------
def test_runner_success_events_and_registry(jb_env):
    app, client, s, sm = jb_env
    ident, _ = _ident(s)
    job, _ = jobs_svc.submit_job(s, ident=ident,
                                 job_type="attribution_fixture",
                                 params={"symbols": ["AAPL"]},
                                 idempotency_key="run1", seed=99)
    s.commit()
    uid = jobs_svc.run_next_queued(s)
    s.commit()
    assert uid == job["job_uid"]
    done = jobs_svc.get_job(s, ident, job_id_or_uid=uid)
    assert done["status"] == "succeeded"
    assert "seed=99" in done["result_summary"]          # deterministic seed recorded
    evs = jobs_svc.fetch_events(s, done["_id"])
    assert [e["event"] for e in evs] == ["queued", "started", "completed"]
    assert [e["seq"] for e in evs] == [1, 2, 3]
    rr_status = s.execute(text(
        "SELECT status FROM research_run WHERE id = "
        "(SELECT research_run_id FROM agent_job WHERE job_uid = :u)"),
        {"u": uid}).scalar()
    assert rr_status == "completed"
    # terminal immutable
    with pytest.raises(jobs_svc.TerminalStateError):
        jobs_svc._transition(s, done["_id"], "running")
    s.rollback()


def test_runner_failure_capped_no_stack_no_secret(jb_env, monkeypatch):
    app, client, s, sm = jb_env
    ident, _ = _ident(s)
    jobs_svc.submit_job(s, ident=ident, job_type="attribution_fixture",
                        params={}, idempotency_key="fail1", seed=1)
    s.commit()

    def boom(db, params, seed):
        raise ValueError("boom " + "x" * 1000)  # oversized message

    monkeypatch.setitem(jobs_svc._HANDLERS, "attribution_fixture", boom)
    uid = jobs_svc.run_next_queued(s)
    s.commit()
    job = jobs_svc.get_job(s, ident, job_id_or_uid=uid)
    assert job["status"] == "failed"
    assert job["error_summary"].startswith("ValueError: boom")
    assert len(job["error_summary"]) <= 500          # capped
    assert "Traceback" not in job["error_summary"]   # never a stack trace


def test_jobs_do_not_mutate_product_state(jb_env):
    app, client, s, sm = jb_env
    ident, _ = _ident(s)
    before = {
        t: s.execute(text(f"SELECT count(*) FROM {t}")).scalar()
        for t in ("recommendation", "paper_trade", "paper_portfolio")
    }
    jobs_svc.submit_job(s, ident=ident, job_type="calibration_study",
                        params=_params(), idempotency_key="mut", seed=3)
    s.commit()
    jobs_svc.run_next_queued(s)
    s.commit()
    after = {
        t: s.execute(text(f"SELECT count(*) FROM {t}")).scalar()
        for t in ("recommendation", "paper_trade", "paper_portfolio")
    }
    assert before == after


def test_cancel_only_queued(jb_env):
    app, client, s, sm = jb_env
    ident, _ = _ident(s)
    job, _ = jobs_svc.submit_job(s, ident=ident,
                                 job_type="attribution_fixture", params={},
                                 idempotency_key="cx", seed=1)
    s.commit()
    out = jobs_svc.cancel_job(s, ident, job["job_uid"])
    s.commit()
    assert out["status"] == "cancelled"
    with pytest.raises(jobs_svc.TerminalStateError):
        jobs_svc.cancel_job(s, ident, job["job_uid"])
    s.rollback()


def test_cross_owner_job_access_404(jb_env):
    app, client, s, sm = jb_env
    ident_a, _ = _ident(s, created_by="owner-A")
    ident_b, _ = _ident(s, created_by="owner-B")
    job, _ = jobs_svc.submit_job(s, ident=ident_a,
                                 job_type="attribution_fixture", params={},
                                 idempotency_key="xo", seed=1)
    s.commit()
    with pytest.raises(jobs_svc.JobNotFound):
        jobs_svc.get_job(s, ident_b, job_id_or_uid=job["job_uid"])
    s.rollback()


# ---------------------------------------------------------------------------
# HTTP surface — B scope end-to-end
# ---------------------------------------------------------------------------
def _mk_owner_and_token(client, s, scopes: list[str]) -> str:
    uid = str(uuid.uuid4())
    cookie = "sess-" + uuid.uuid4().hex
    # unique email per owner row; ARTHOS_OWNER_EMAILS only checks membership
    # of the single OWNER_EMAIL, so make every real owner that email and
    # give throwaway owners a distinct one when several coexist in one test
    email = OWNER_EMAIL if not s.execute(
        text("SELECT 1 FROM app_user WHERE email = :e"), {"e": OWNER_EMAIL}
    ).first() else f"owner-{uuid.uuid4().hex[:8]}@test.local"
    s.execute(text("INSERT INTO app_user (id, email, access_role) "
                   "VALUES (:i, :e, 'owner')"),
              {"i": uid, "e": email})
    s.execute(text("INSERT INTO user_session (token, user_id, expires_at) "
                   "VALUES (:t, :u, now() + interval '1 day')"),
              {"t": cookie, "u": uid})
    s.commit()
    r = client.post("/api/admin/agent-tokens",
                    json={"agent_name": "http-agent", "scopes": scopes,
                          "rate_limit_per_min": 240},
                    cookies={"arthos_session": cookie})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_http_submit_replay_conflict_and_cap(jb_env):
    app, client, s, sm = jb_env
    tok = _mk_owner_and_token(client, s, ["B"])
    h = {"Authorization": f"Bearer {tok}"}
    body = {"job_type": "attribution_fixture", "params": {},
            "idempotency_key": "h1", "seed": 5}
    r1 = client.post("/api/agent/jobs", json=body, headers=h)
    assert r1.status_code == 202 and r1.json()["replayed"] is False
    r2 = client.post("/api/agent/jobs", json=body, headers=h)
    assert r2.status_code == 202 and r2.json()["replayed"] is True
    assert r2.json()["job_uid"] == r1.json()["job_uid"]
    r3 = client.post("/api/agent/jobs", json={**body, "seed": 6}, headers=h)
    assert r3.status_code == 409
    for i in range(4):
        assert client.post("/api/agent/jobs", json={
            **body, "idempotency_key": f"h-cap-{i}"}, headers=h,
        ).status_code == 202
    r6 = client.post("/api/agent/jobs",
                     json={**body, "idempotency_key": "h-cap-full"},
                     headers=h)
    assert r6.status_code == 429
    # status read + missing job 404 + internal id never serialized
    uid = r1.json()["job_uid"]
    g = client.get(f"/api/agent/jobs/{uid}", headers=h)
    assert g.status_code == 200 and "_id" not in g.json()
    assert client.get("/api/agent/jobs/agj_nope", headers=h).status_code == 404


# ---------------------------------------------------------------------------
# SSE — bounds, eviction, auth expiry, DB failure, audit count
# ---------------------------------------------------------------------------
@pytest.fixture
def fast_sse(monkeypatch):
    monkeypatch.setattr(gw, "SSE_MAX_SECONDS", 1.0)
    monkeypatch.setattr(gw, "SSE_HEARTBEAT_SECONDS", 0.2)
    monkeypatch.setattr(gw, "SSE_POLL_SECONDS", 0.02)


def _stream_lines(gen, cap=200):
    out = []
    for line in gen:
        out.append(line)
        if len(out) >= cap:
            gen.close()
            break
    return out


def test_sse_terminal_event_closes(jb_env, fast_sse):
    app, client, s, sm = jb_env
    ident, _ = _ident(s)
    job, _ = jobs_svc.submit_job(s, ident=ident,
                                 job_type="attribution_fixture", params={},
                                 idempotency_key="sse1", seed=1)
    s.commit()
    jobs_svc.run_next_queued(s)
    s.commit()
    lines = _stream_lines(gw.job_event_stream(
        ident, job["_id"], after=0, max_events=500, route_tmpl="/t"))
    joined = "".join(lines)
    assert "event: queued" in joined and "event: completed" in joined
    assert "event: terminal" in joined and joined.rstrip().endswith("data: succeeded")


def test_sse_event_cap_yields_cursor(jb_env, fast_sse):
    app, client, s, sm = jb_env
    ident, _ = _ident(s)
    job, _ = jobs_svc.submit_job(s, ident=ident,
                                 job_type="attribution_fixture", params={},
                                 idempotency_key="sse2", seed=1)
    s.commit()
    for i in range(5):
        jobs_svc._append_event(s, job["_id"], "progress", f"step {i}")
    s.commit()
    lines = _stream_lines(gw.job_event_stream(
        ident, job["_id"], after=0, max_events=3, route_tmpl="/t"))
    joined = "".join(lines)
    assert joined.count("event: ") == 4      # 3 data events + cursor
    assert "event: cursor" in joined
    # resume from cursor gets the rest
    cursor = int(lines[-1].split("data: ")[1].strip())
    more = _stream_lines(gw.job_event_stream(
        ident, job["_id"], after=cursor, max_events=500, route_tmpl="/t"))
    assert "step 4" in "".join(more)


def test_sse_time_cap_and_heartbeat(jb_env, fast_sse):
    app, client, s, sm = jb_env
    ident, _ = _ident(s)
    job, _ = jobs_svc.submit_job(s, ident=ident,
                                 job_type="attribution_fixture", params={},
                                 idempotency_key="sse3", seed=1)
    s.commit()  # queued only — never runs → stream must time-cap out
    lines = _stream_lines(gw.job_event_stream(
        ident, job["_id"], after=1, max_events=500, route_tmpl="/t"))
    joined = "".join(lines)
    assert ": heartbeat" in joined            # heartbeats while idle
    assert "event: cursor" in joined          # closed by time cap w/ cursor


def test_sse_second_stream_evicts_first(jb_env, fast_sse):
    app, client, s, sm = jb_env
    ident, _ = _ident(s)
    job, _ = jobs_svc.submit_job(s, ident=ident,
                                 job_type="attribution_fixture", params={},
                                 idempotency_key="sse4", seed=1)
    s.commit()
    g1 = gw.job_event_stream(ident, job["_id"], after=0, max_events=500,
                             route_tmpl="/t")
    next(g1)  # start g1 (consumes 'queued')
    g2 = gw.job_event_stream(ident, job["_id"], after=0, max_events=500,
                             route_tmpl="/t")
    next(g2)  # registering g2 bumps the generation
    rest = _stream_lines(g1)
    assert "event: evicted" in "".join(rest)
    g2.close()


def test_sse_revoked_token_terminates_stream(jb_env, fast_sse):
    app, client, s, sm = jb_env
    ident, full = _ident(s)
    job, _ = jobs_svc.submit_job(s, ident=ident,
                                 job_type="attribution_fixture", params={},
                                 idempotency_key="sse5", seed=1)
    s.commit()
    s.execute(text("UPDATE agent_token SET status='revoked', revoked_at=now() "
                   "WHERE token_prefix = :p"), {"p": ident["token_prefix"]})
    s.commit()
    lines = _stream_lines(gw.job_event_stream(
        ident, job["_id"], after=1, max_events=500, route_tmpl="/t"))
    assert "event: auth_expired" in "".join(lines)


def test_sse_db_failure_bounded_error(jb_env, fast_sse, monkeypatch):
    app, client, s, sm = jb_env
    ident, _ = _ident(s)
    job, _ = jobs_svc.submit_job(s, ident=ident,
                                 job_type="attribution_fixture", params={},
                                 idempotency_key="sse6", seed=1)
    s.commit()

    class Boom:
        def __call__(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(db_mod, "SessionLocal", Boom())
    lines = _stream_lines(gw.job_event_stream(
        ident, job["_id"], after=0, max_events=500, route_tmpl="/t"))
    assert "event: error" in "".join(lines) and len(lines) <= 2


def test_sse_disconnect_writes_audit_with_count(jb_env, fast_sse):
    app, client, s, sm = jb_env
    ident, _ = _ident(s)
    job, _ = jobs_svc.submit_job(s, ident=ident,
                                 job_type="attribution_fixture", params={},
                                 idempotency_key="sse7", seed=1)
    s.commit()
    g = gw.job_event_stream(ident, job["_id"], after=0, max_events=500,
                            route_tmpl="/agent/jobs/{job_uid}/events")
    next(g)          # one event delivered
    g.close()        # client disconnect → GeneratorExit → finally audit
    row = s.execute(text(
        "SELECT idempotency_key, scope_used FROM agent_audit "
        "WHERE route = '/agent/jobs/{job_uid}/events'")).mappings().first()
    assert row is not None and row["idempotency_key"] == "sse_events=1"
    assert row["scope_used"] == "B"


def test_sse_http_cross_owner_404_and_scope(jb_env):
    app, client, s, sm = jb_env
    tok_b = _mk_owner_and_token(client, s, ["B"])
    h = {"Authorization": f"Bearer {tok_b}"}
    r = client.post("/api/agent/jobs", json={
        "job_type": "attribution_fixture", "params": {},
        "idempotency_key": "sse-h1"}, headers=h)
    uid = r.json()["job_uid"]
    # foreign owner (rewrite created_by on a second token) → 404
    ident_x, full_x = _ident(s, created_by="stranger")
    hx = {"Authorization": f"Bearer {full_x}"}
    assert client.get(f"/api/agent/jobs/{uid}/events", headers=hx).status_code == 404
    # R-only token → 403 before any stream work
    tok_r = _mk_owner_and_token(client, s, ["R"])
    assert client.get(f"/api/agent/jobs/{uid}/events",
                      headers={"Authorization": f"Bearer {tok_r}"}).status_code == 403


# ---------------------------------------------------------------------------
# D scope — drafts
# ---------------------------------------------------------------------------
def _mk_task(s: Session) -> str:
    from apps.api.src.domain.research_inbox import service as inbox_svc
    t = inbox_svc.create_task(s, title="watch", question="anything new?")
    s.commit()
    return t.id


def test_draft_forced_pending_agent_provenance(jb_env):
    app, client, s, sm = jb_env
    task_id = _mk_task(s)
    tok = _mk_owner_and_token(client, s, ["D"])
    h = {"Authorization": f"Bearer {tok}"}
    body = {"task_uid": task_id, "body_md": "# finding\nnothing material",
            "citations": [], "idempotency_key": "d1"}
    r = client.post("/api/agent/drafts", json=body, headers=h)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["review_status"] == "pending" and out["replayed"] is False
    row = s.execute(text(
        "SELECT generated_by, provenance, review_status FROM research_report "
        "WHERE id = :i"), {"i": out["report_id"]}).mappings().one()
    assert row["generated_by"] == "agent:http-agent"    # server-set, never body
    assert row["provenance"] == "generated"
    assert row["review_status"] == "pending"
    # replay + conflict
    r2 = client.post("/api/agent/drafts", json=body, headers=h)
    assert r2.status_code == 201 and r2.json()["replayed"] is True
    assert r2.json()["report_id"] == out["report_id"]
    r3 = client.post("/api/agent/drafts",
                     json={**body, "body_md": "different"}, headers=h)
    assert r3.status_code == 409
    # unknown task 404; bad type 422; bad citation 422
    assert client.post("/api/agent/drafts", json={
        **body, "idempotency_key": "d2", "task_uid": str(uuid.uuid4()),
    }, headers=h).status_code == 404
    assert client.post("/api/agent/drafts", json={
        **body, "idempotency_key": "d3", "report_type": "shell",
    }, headers=h).status_code == 422
    assert client.post("/api/agent/drafts", json={
        **body, "idempotency_key": "d4",
        "citations": [{"note": "no url"}],
    }, headers=h).status_code == 422


def test_gateway_has_no_report_review_surface(jb_env):
    """The gateway can NEVER approve/publish/correct/delete a report."""
    app, client, s, sm = jb_env
    from .test_agent_gateway_http_pg import _flatten_routes
    for r in _flatten_routes(app.routes):
        if r.path.startswith("/agent"):
            for banned in ("approve", "reject", "publish", "correct",
                           "review", "delete"):
                assert banned not in r.path.lower(), r.path


# ---------------------------------------------------------------------------
# Source-level security scans
# ---------------------------------------------------------------------------
def test_no_dangerous_capabilities_in_gateway_sources():
    import apps.api.src.api.agent_gateway as g
    import apps.api.src.domain.agent_gateway.jobs as j
    banned = ("subprocess", "os.system", "eval(", "exec(", "__import__",
              "importlib", "pickle", "requests.", "urllib", "httpx",
              "socket.", "nbformat", "papermill")
    for mod in (g, j):
        src = open(mod.__file__, encoding="utf-8").read()
        for b in banned:
            assert b not in src, (mod.__name__, b)


def test_handler_dispatch_table_frozen_and_complete():
    assert set(jobs_svc._HANDLERS) == set(jobs_svc.JOB_TYPES)
    assert set(jobs_svc._PARAM_VALIDATORS) == set(jobs_svc.JOB_TYPES)
    assert isinstance(jobs_svc.JOB_TYPES, frozenset)
    assert jobs_svc.JOB_TYPES == frozenset({
        "calibration_study", "walk_forward_baseline", "drift_report",
        "attribution_fixture"})


def test_jobs_module_writes_only_agent_and_registry_tables():
    """Every INSERT/UPDATE in jobs.py targets only agent_* or research_run."""
    import re

    import apps.api.src.domain.agent_gateway.jobs as j
    src = open(j.__file__, encoding="utf-8").read()
    # INSERT INTO <t>  and  UPDATE <t> SET  — excludes 'UPDATE .. FOR UPDATE
    # SKIP LOCKED' locking clauses (no SET, not a write target)
    writes = re.findall(r"INSERT INTO\s+(\w+)", src)
    writes += re.findall(r"UPDATE\s+(\w+)\s+SET", src)
    assert writes, "expected write statements"
    for stmt in writes:
        assert stmt in ("agent_job", "agent_job_event", "agent_idempotency",
                        "research_run"), stmt
