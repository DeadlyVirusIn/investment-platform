"""Wave 2C (migration 121) — research execution & origin provenance (pg).

Pins: task-linked job submission (validation, closed-task refusal,
idempotent replay preserving the link, same-key-different-task 409),
transition whitelist preserving research_task_id, DB-trigger immutability
(the exact SQL from migration 121, imported — no drift), RESTRICT proofs,
follow-up server-stamped source_report_id with composite-FK correctness,
any-retained-version follow-up policy, execution-history route (isolation,
ordering, caps, redaction, zero writes, owner-shaped), and no historical
backfill.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.api import research_inbox as inbox_api
from apps.api.src.domain.agent_gateway import jobs as jobs_svc
from apps.api.src.domain.research_inbox import service as svc

from .test_agent_gateway_http_pg import _DDL, _DDL_AGENT
from .test_agent_jobs_pg import _DDL_JOBS

pytestmark = pytest.mark.integration

OWNER = {"email": "owner@example.com", "id": "owner-1", "role": "owner"}


def _migration_121_sql() -> tuple[str, str]:
    """Import the trigger DDL from the migration itself — tests and
    migration can never drift."""
    path = (pathlib.Path(__file__).resolve().parents[4]
            / "infra" / "alembic" / "versions"
            / "121_research_exec_provenance.py")
    spec = importlib.util.spec_from_file_location("mig121", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.PROVENANCE_TRIGGER_SQL, mod.PROVENANCE_TRIGGER_DROP_SQL


@pytest.fixture
def env(pg_session: Session):
    pg_session.execute(text(_DDL))
    pg_session.execute(text(_DDL_AGENT))
    pg_session.execute(text(_DDL_JOBS))
    trig, drop = _migration_121_sql()
    pg_session.execute(text(drop))
    pg_session.execute(text(trig))
    pg_session.execute(text(
        "TRUNCATE agent_idempotency, agent_job_event, agent_job CASCADE"))
    pg_session.commit()
    yield pg_session
    pg_session.rollback()
    pg_session.execute(text(drop))
    pg_session.commit()


def _ident() -> dict:
    return {"token_prefix": "arthospx", "created_by": "gw-owner",
            "agent_name": "researcher", "scopes": {"B"},
            "rate_limit_per_min": 60}


def _task(db, title="T", status="open"):
    t = svc.create_task(db, title=title, question="Q?",
                        created_by="owner@example.com")
    if status != "open":
        db.execute(text("UPDATE research_task SET status=:s WHERE id=:i"),
                   {"s": status, "i": t.id})
        db.commit()
    return t


def _submit(db, key, task_id=None, seed=1, params=None):
    job, replayed = jobs_svc.submit_job(
        db, ident=_ident(), job_type="attribution_fixture",
        params=params or {}, idempotency_key=key, seed=seed,
        research_task_id=task_id)
    db.commit()
    return job, replayed


# ── submission ─────────────────────────────────────────────────────────────

def test_job_without_task_stays_null(env: Session):
    job, _ = _submit(env, "k-null")
    assert job["research_task_id"] is None


def test_valid_task_linked_job(env: Session):
    t = _task(env)
    job, replayed = _submit(env, "k-link", task_id=t.id)
    assert job["research_task_id"] == t.id and replayed is False
    # bounded provenance in the event stream — prefix only, no task body
    ev = env.execute(text(
        "SELECT payload FROM agent_job_event WHERE job_id = "
        "(SELECT id FROM agent_job WHERE job_uid=:u) AND event_type='queued'"
    ), {"u": job["job_uid"]}).scalar()
    assert t.id[:8] in ev and "Q?" not in ev


def test_paused_task_allowed_closed_rejected_missing_rejected(env: Session):
    paused = _task(env, "p", status="paused")
    job, _ = _submit(env, "k-paused", task_id=paused.id)
    assert job["research_task_id"] == paused.id

    closed = _task(env, "c", status="closed")
    with pytest.raises(jobs_svc.InvalidJob, match="closed"):
        _submit(env, "k-closed", task_id=closed.id)
    env.rollback()
    with pytest.raises(jobs_svc.InvalidJob, match="unknown research_task"):
        _submit(env, "k-missing", task_id="00000000-0000-0000-0000-000000000000")
    env.rollback()


def test_idempotent_replay_preserves_original_task_link(env: Session):
    t = _task(env)
    first, _ = _submit(env, "k-replay", task_id=t.id)
    again, replayed = _submit(env, "k-replay", task_id=t.id)
    assert replayed is True
    assert again["job_uid"] == first["job_uid"]
    assert again["research_task_id"] == t.id


def test_same_key_different_task_conflicts(env: Session):
    t1, t2 = _task(env, "a"), _task(env, "b")
    _submit(env, "k-conf", task_id=t1.id)
    with pytest.raises(jobs_svc.IdempotencyConflict):
        _submit(env, "k-conf", task_id=t2.id)
    env.rollback()
    # ...and task-less vs task-linked with the same key also conflicts
    with pytest.raises(jobs_svc.IdempotencyConflict):
        _submit(env, "k-conf")
    env.rollback()
    # original job untouched
    orig = env.execute(text(
        "SELECT research_task_id FROM agent_job WHERE request_hash IN "
        "(SELECT request_hash FROM agent_idempotency WHERE idem_key='k-conf')"
    )).scalar()
    assert orig == t1.id


# ── transition whitelist + DB immutability ────────────────────────────────

def test_transitions_preserve_task_link(env: Session):
    t = _task(env)
    job, _ = _submit(env, "k-trans", task_id=t.id)
    uid = jobs_svc.run_next_queued(env)   # queued → running → succeeded
    env.commit()
    assert uid == job["job_uid"]
    row = env.execute(text(
        "SELECT status, research_task_id FROM agent_job WHERE job_uid=:u"),
        {"u": uid}).mappings().one()
    assert row["status"] == "succeeded"
    assert row["research_task_id"] == t.id


def test_cancellation_preserves_task_link(env: Session):
    t = _task(env)
    job, _ = _submit(env, "k-cancel", task_id=t.id)
    out = jobs_svc.cancel_job(env, _ident(), job["job_uid"])
    env.commit()
    assert out["status"] == "cancelled"
    assert out["research_task_id"] == t.id


def test_direct_sql_mutation_of_job_link_rejected_by_trigger(env: Session):
    t1, t2 = _task(env, "a"), _task(env, "b")
    job, _ = _submit(env, "k-mut", task_id=t1.id)
    for sql, params in [
        ("UPDATE agent_job SET research_task_id=:x WHERE job_uid=:u",
         {"x": t2.id, "u": job["job_uid"]}),
        ("UPDATE agent_job SET research_task_id=NULL WHERE job_uid=:u",
         {"u": job["job_uid"]}),
    ]:
        with pytest.raises(Exception, match="immutable"):
            env.execute(text(sql), params)
        env.rollback()


def test_null_to_set_via_update_rejected(env: Session):
    t = _task(env)
    job, _ = _submit(env, "k-late")
    with pytest.raises(Exception, match="immutable"):
        env.execute(text(
            "UPDATE agent_job SET research_task_id=:x WHERE job_uid=:u"),
            {"x": t.id, "u": job["job_uid"]})
    env.rollback()


def test_task_with_execution_history_cannot_be_deleted(env: Session):
    t = _task(env)
    _submit(env, "k-restrict", task_id=t.id)
    with pytest.raises(Exception):
        env.execute(text("DELETE FROM research_task WHERE id=:i"),
                    {"i": t.id})
        env.flush()
    env.rollback()


def test_retry_is_a_new_job_never_a_mutation(env: Session):
    t = _task(env)
    j1, _ = _submit(env, "k-r1", task_id=t.id)
    j2, _ = _submit(env, "k-r2", task_id=t.id)   # retry = new key, new job
    assert j1["job_uid"] != j2["job_uid"]
    n = env.execute(text(
        "SELECT count(*) FROM agent_job WHERE research_task_id=:t"),
        {"t": t.id}).scalar()
    assert n == 2


# ── follow-up source-report stamping ───────────────────────────────────────

def _cite():
    return [{"source": "s", "url": "https://example.com/x",
             "observed_at": "2026-07-13T00:00:00+00:00"}]


def test_follow_up_stamps_exact_source_version_server_side(env: Session):
    parent = _task(env, "origin")
    r1 = svc.create_report(env, parent.id, body="v1", citations=_cite(),
                           provenance="human",
                           created_by="owner@example.com")
    out = inbox_api.create_follow_up(
        report_id=r1.id,
        body=inbox_api.FollowUpBody(title="fu", question="q?"),
        owner=OWNER, db=env)
    assert out["source_report_id"] == r1.id
    assert out["source_report_version"] == 1
    row = env.execute(text(
        "SELECT source_report_id, follow_up_of_task_id FROM research_task "
        "WHERE id=:i"), {"i": out["id"]}).mappings().one()
    assert row["source_report_id"] == r1.id
    assert row["follow_up_of_task_id"] == parent.id


def test_follow_up_allowed_from_any_retained_version(env: Session):
    # pinned policy: pending, rejected, and superseded versions are all
    # legitimate follow-up sources; the link names that exact version.
    parent = _task(env, "origin")
    r1 = svc.create_report(env, parent.id, body="v1", citations=_cite(),
                           provenance="generated", created_by="agent:a")
    svc.reject_report(env, r1.id, reviewer="owner@example.com")
    r2 = svc.correct_report(env, r1.id, new_body="v2",
                            created_by="owner@example.com")
    for src in (r1, r2):   # rejected+superseded v1 AND current v2
        out = inbox_api.create_follow_up(
            report_id=src.id,
            body=inbox_api.FollowUpBody(title=f"fu-{src.version}",
                                        question="q?"),
            owner=OWNER, db=env)
        assert out["source_report_version"] == src.version


def test_cross_task_source_report_rejected(env: Session):
    a, b = _task(env, "a"), _task(env, "b")
    rb = svc.create_report(env, b.id, body="v1", citations=_cite(),
                           provenance="human",
                           created_by="owner@example.com")
    with pytest.raises(svc.ResearchInboxError):
        svc.create_task(env, title="bad", question="q?",
                        created_by="o", follow_up_of_task_id=a.id,
                        source_report_id=rb.id)
    env.rollback()
    # and the composite FK backstops a direct insert
    with pytest.raises(Exception):
        env.execute(text(
            "INSERT INTO research_task (id, title, question, status, "
            "created_by, follow_up_of_task_id, source_report_id, created_at)"
            " VALUES (gen_random_uuid()::varchar, 'bad', 'q', 'open', 'o', "
            ":p, :r, now())"), {"p": a.id, "r": rb.id})
        env.flush()
    env.rollback()


def test_source_provenance_immutable_after_creation(env: Session):
    parent = _task(env, "origin")
    r1 = svc.create_report(env, parent.id, body="v1", citations=_cite(),
                           provenance="human",
                           created_by="owner@example.com")
    out = inbox_api.create_follow_up(
        report_id=r1.id,
        body=inbox_api.FollowUpBody(title="fu", question="q?"),
        owner=OWNER, db=env)
    with pytest.raises(Exception, match="immutable"):
        env.execute(text(
            "UPDATE research_task SET source_report_id=NULL WHERE id=:i"),
            {"i": out["id"]})
    env.rollback()


def test_follow_up_mutates_nothing_and_launches_nothing(env: Session):
    parent = _task(env, "origin")
    r1 = svc.create_report(env, parent.id, body="v1", citations=_cite(),
                           provenance="human",
                           created_by="owner@example.com")
    snap = env.execute(text(
        "SELECT row_to_json(r)::text FROM research_report r WHERE id=:i"),
        {"i": r1.id}).scalar()
    inbox_api.create_follow_up(
        report_id=r1.id,
        body=inbox_api.FollowUpBody(title="fu", question="q?"),
        owner=OWNER, db=env)
    assert env.execute(text(
        "SELECT row_to_json(r)::text FROM research_report r WHERE id=:i"),
        {"i": r1.id}).scalar() == snap
    assert (env.execute(text("SELECT count(*) FROM agent_job")).scalar()
            == 0)


def test_historical_tasks_stay_unlinked(env: Session):
    _task(env, "old")
    n = env.execute(text(
        "SELECT count(*) FROM research_task "
        "WHERE source_report_id IS NOT NULL")).scalar()
    assert n == 0   # nothing invents links for pre-121 rows


# ── execution-history route ────────────────────────────────────────────────

def test_execution_history_isolation_ordering_and_redaction(env: Session):
    t1, t2 = _task(env, "mine"), _task(env, "other")
    _submit(env, "eh-1", task_id=t1.id, params={"symbols": ["AAA"]})
    _submit(env, "eh-2", task_id=t1.id)
    _submit(env, "eh-3", task_id=t2.id)
    out = inbox_api.execution_history(task_id=t1.id, owner=OWNER, db=env,
                                      limit=50)
    assert out["total"] == 2 and out["overflow"] == 0
    uids = [a["job_uid"] for a in out["attempts"]]
    assert len(uids) == 2                      # t2's job never leaks in
    # newest-first; attempt numbers oldest=1
    assert out["attempts"][0]["attempt"] == 2
    assert out["attempts"][0]["is_retry"] is True
    assert out["attempts"][1]["attempt"] == 1
    import json as _json
    payload = _json.dumps(out)
    assert "request_hash" not in payload
    assert "gw-owner" not in payload           # created_by never leaves
    assert "symbols" not in payload            # params payload not exposed
    assert "AAA" not in payload


def test_execution_history_unknown_task_404_and_no_writes(env: Session):
    with pytest.raises(HTTPException) as e:
        inbox_api.execution_history(task_id="nope", owner=OWNER, db=env,
                                    limit=50)
    assert e.value.status_code == 404
    t = _task(env)
    before = env.execute(text("SELECT count(*) FROM agent_job")).scalar()
    inbox_api.execution_history(task_id=t.id, owner=OWNER, db=env, limit=50)
    assert env.execute(
        text("SELECT count(*) FROM agent_job")).scalar() == before


def test_execution_history_cap_and_overflow(env: Session):
    t = _task(env)
    # queue cap is 5/owner; use direct inserts to exceed the page size
    for i in range(7):
        env.execute(text(
            "INSERT INTO agent_job (id, job_uid, job_type, params, seed, "
            "status, token_prefix, created_by, request_hash, "
            "research_task_id, finished_at, result_summary) VALUES "
            "(gen_random_uuid()::varchar, :u, 'drift_report', '{}'::jsonb, "
            "1, 'succeeded', 'p', 'o', :h, :t, now(), 'ok')"),
            {"u": f"agjeh{i}", "h": f"h{i}", "t": t.id})
    env.commit()
    out = inbox_api.execution_history(task_id=t.id, owner=OWNER, db=env,
                                      limit=5)
    assert out["total"] == 7
    assert len(out["attempts"]) == 5
    assert out["overflow"] == 2
