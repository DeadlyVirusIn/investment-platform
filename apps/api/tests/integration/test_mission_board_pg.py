"""Wave 2B — Mission Board pg integration tests.

Real task/report version chains + a real agent_job table (DDL mirrors
migration 115 — agent_job is not ORM-mapped). Pins: column derivations on
real rows, one card per task, retry-supersedes-failure, gateway-off zero
job queries, READ-ONLY (row counts byte-stable), bounded query count
(no N+1), payload redaction (no body/citations/emails/secrets), caps +
overflow, deterministic output, route wiring incl. filters.
"""

from __future__ import annotations

import datetime
import json

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from apps.api.src.api import research_inbox as api
from apps.api.src.domain.research_inbox import mission_board as mb
from apps.api.src.domain.research_inbox import service as svc

pytestmark = pytest.mark.integration

OWNER = {"email": "owner@example.com", "id": "owner-1", "role": "owner"}

_DDL_JOBS = """
CREATE TABLE IF NOT EXISTS agent_job (
    id VARCHAR(36) PRIMARY KEY,
    job_uid VARCHAR(32) NOT NULL UNIQUE,
    job_type VARCHAR(32) NOT NULL,
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    seed BIGINT,
    status VARCHAR(16) NOT NULL DEFAULT 'queued',
    token_prefix VARCHAR(8) NOT NULL,
    created_by VARCHAR(64) NOT NULL,
    request_hash VARCHAR(64),
    research_run_id VARCHAR(36),
    result_summary TEXT,
    error_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
"""


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _cite(days_ago: float = 1.0) -> list[dict]:
    ts = _now() - datetime.timedelta(days=days_ago)
    return [{"source": "s", "url": "https://example.com/e",
             "observed_at": ts.isoformat()}]


@pytest.fixture
def env(pg_session: Session, monkeypatch):
    pg_session.execute(text(_DDL_JOBS))
    pg_session.execute(text("DELETE FROM agent_job"))
    pg_session.commit()
    monkeypatch.setattr(
        "apps.api.src.domain.research_inbox.mission_board.settings.AGENT_GATEWAY_ENABLED",
        True, raising=False)
    return pg_session


def _task(db, title="T", schedule=None, follow_up=None):
    return svc.create_task(db, title=title, question=f"Q about {title}?",
                           scope=None, schedule_expr=schedule,
                           created_by="owner@example.com",
                           follow_up_of_task_id=follow_up)


def _job(db, uid, status, jt="drift_report", params=None, err=None,
         created_shift_s=0):
    db.execute(text(
        "INSERT INTO agent_job (id, job_uid, job_type, params, status, "
        "token_prefix, created_by, error_summary, created_at, started_at, "
        "finished_at) VALUES (gen_random_uuid()::varchar, :u, :jt, "
        "CAST(:p AS jsonb), :s, 'arthos_a', 'gw-owner', :e, "
        "now() + make_interval(secs => :shift), "
        "CASE WHEN CAST(:s AS varchar) IN ('running','failed','succeeded') "
        "THEN now() END, "
        "CASE WHEN CAST(:s AS varchar) IN ('failed','succeeded','cancelled') "
        "THEN now() END)"),
        {"u": uid, "jt": jt, "p": json.dumps(params or {}), "s": status,
         "e": err, "shift": created_shift_s})
    db.commit()


def _board(db, **kw):
    return mb.build_mission_board(db, **kw)


def _cards(board, column):
    for col in board["columns"]:
        if col["key"] == column:
            return col["cards"]
    return []


# ── column derivations on real rows ────────────────────────────────────────

def test_full_board_scenarios(env: Session):
    db = env
    _task(db, "queued-plain")                                   # queued
    t_sched = _task(db, "queued-scheduled", schedule="0 6 * * MON")
    t_pending = _task(db, "needs-review")
    svc.create_report(db, t_pending.id, body="B", citations=_cite(),
                      provenance="generated", created_by="agent:researcher")
    t_done = _task(db, "delivered-fresh")
    svc.create_report(db, t_done.id, body="B", citations=_cite(1),
                      provenance="human", created_by="owner@example.com")
    t_corr = _task(db, "corrected-chain")
    r1 = svc.create_report(db, t_corr.id, body="v1", citations=_cite(1),
                           provenance="human", created_by="owner@example.com")
    r2 = svc.correct_report(db, r1.id, new_body="v2", citations=_cite(1),
                            created_by="owner@example.com")
    svc.correct_report(db, r2.id, new_body="v3", citations=_cite(1),
                       created_by="owner@example.com")
    t_stale = _task(db, "stale-evidence")
    svc.create_report(db, t_stale.id, body="B", citations=_cite(20),
                      provenance="human", created_by="owner@example.com")
    _job(db, "agj_run1", "running")                             # running
    _job(db, "agj_fail1", "failed", err="ValueError: boom",
         params={"reference_days": 30})                        # failed

    board = _board(db)
    by = {c["title"]: c["column"] for col in board["columns"]
          for c in col["cards"] if c["kind"] == "task"}
    assert by["queued-plain"] == "queued"
    assert by["queued-scheduled"] == "queued"
    assert by["needs-review"] == "review_needed"
    assert by["delivered-fresh"] == "delivered"
    assert by["corrected-chain"] == "corrected"
    assert by["stale-evidence"] == "stale"
    assert board["counts"]["running"] == 1
    assert board["counts"]["failed"] == 1
    assert board["rule_set_version"] == "mission-board-1"

    # scheduled card is explicit that nothing auto-runs
    sched = next(c for c in _cards(board, "queued")
                 if c["title"] == "queued-scheduled")
    assert sched["schedule"]["defined"] is True
    assert "nothing runs automatically" in sched["schedule"]["note"]

    # corrected chain summary
    corr = next(c for c in _cards(board, "corrected"))
    assert corr["chain"] == {
        "versions": 3, "prior_retained": 2, "corrections": 2,
        "current_version": 3, "current_status": "approved",
        "last_corrected_by_label": "owner",
    }

    # one card per task, globally
    ids = [c["card_id"] for col in board["columns"] for c in col["cards"]]
    assert len(ids) == len(set(ids))


def test_approved_v1_pending_v2_review_needed_not_delivered(env: Session):
    db = env
    t = _task(db, "v1-approved-v2-pending")
    r1 = svc.create_report(db, t.id, body="v1", citations=_cite(),
                           provenance="human", created_by="owner@example.com")
    svc.correct_report(db, r1.id, new_body="v2", provenance="generated",
                       created_by="agent:researcher")
    board = _board(db)
    assert [c["title"] for c in _cards(board, "review_needed")] == [
        "v1-approved-v2-pending"]
    assert _cards(board, "delivered") == []
    card = _cards(board, "review_needed")[0]
    assert card["chain"]["corrections"] == 1        # chain context retained
    assert card["latest_report"]["version"] == 2


def test_rejected_latest_after_approved_is_corrected(env: Session):
    db = env
    t = _task(db, "rejected-correction")
    r1 = svc.create_report(db, t.id, body="v1", citations=_cite(),
                           provenance="human", created_by="owner@example.com")
    r2 = svc.correct_report(db, r1.id, new_body="v2", provenance="generated",
                            created_by="agent:researcher")
    svc.reject_report(db, r2.id, reviewer="owner@example.com")
    card = _cards(_board(db), "corrected")[0]
    assert card["chain"]["current_status"] == "rejected"


def test_failed_job_with_active_retry_shows_running_only(env: Session):
    db = env
    _job(db, "agj_old", "failed", params={"reference_days": 90},
         err="boom", created_shift_s=-60)
    _job(db, "agj_new", "running", params={"reference_days": 90})
    board = _board(db)
    assert board["counts"]["failed"] == 0
    assert [c["job_uid"] for c in _cards(board, "running")] == ["agj_new"]


def test_follow_up_card_labels_parent(env: Session):
    db = env
    parent = _task(db, "root question")
    _task(db, "the follow-up", follow_up=parent.id)
    card = next(c for c in _cards(_board(db), "queued")
                if c["title"] == "the follow-up")
    assert card["is_follow_up"] is True
    assert card["follow_up"]["parent_task_id"] == parent.id
    assert card["follow_up"]["parent_title"] == "root question"
    assert card["follow_up"]["depth"] == 1


# ── gateway off / store missing ────────────────────────────────────────────

def test_gateway_disabled_zero_job_queries_and_note(env: Session,
                                                    monkeypatch):
    db = env
    monkeypatch.setattr(
        "apps.api.src.domain.research_inbox.mission_board.settings.AGENT_GATEWAY_ENABLED",
        False, raising=False)
    _task(db, "still-works")
    _job(db, "agj_x", "failed", err="boom")   # present but must not be read
    statements: list[str] = []
    engine = db.get_bind()

    def _spy(conn, cursor, stmt, params, ctx, executemany):
        statements.append(stmt)

    event.listen(engine, "before_cursor_execute", _spy)
    try:
        board = _board(db)
    finally:
        event.remove(engine, "before_cursor_execute", _spy)
    assert not any("agent_job" in s for s in statements)   # zero job queries
    assert board["gateway_enabled"] is False
    assert board["counts"]["failed"] == 0                  # never mislabeled
    assert board["counts"]["queued"] == 1
    assert any("Gateway is off" in n for n in board["board_health"]["notes"])


# ── read-only + query bound ────────────────────────────────────────────────

def test_board_is_read_only(env: Session):
    db = env
    t = _task(db, "ro")
    svc.create_report(db, t.id, body="B", citations=_cite(),
                      provenance="generated", created_by="agent:a")
    _job(db, "agj_ro", "failed", err="x")
    before = {
        tbl: db.execute(text(f"SELECT count(*) FROM {tbl}")).scalar()
        for tbl in ("research_task", "research_report", "agent_job")
    }
    snap = db.execute(text(
        "SELECT md5(string_agg(row_to_json(r)::text, ',' "
        "ORDER BY r.id)) FROM research_report r")).scalar()
    _board(db)
    db.rollback()
    after = {
        tbl: db.execute(text(f"SELECT count(*) FROM {tbl}")).scalar()
        for tbl in ("research_task", "research_report", "agent_job")
    }
    snap2 = db.execute(text(
        "SELECT md5(string_agg(row_to_json(r)::text, ',' "
        "ORDER BY r.id)) FROM research_report r")).scalar()
    assert before == after and snap == snap2


def test_query_count_is_bounded_no_n_plus_1(env: Session):
    db = env
    for i in range(12):
        t = _task(db, f"bulk-{i}")
        svc.create_report(db, t.id, body="B", citations=_cite(),
                          provenance="generated", created_by="agent:a")
    statements: list[str] = []
    engine = db.get_bind()

    def _spy(conn, cursor, stmt, params, ctx, executemany):
        if stmt.strip().upper().startswith("SELECT"):
            statements.append(stmt)

    event.listen(engine, "before_cursor_execute", _spy)
    try:
        _board(db)
    finally:
        event.remove(engine, "before_cursor_execute", _spy)
    # tasks + reports + jobs (+ optional follow-up parents) — never per-card
    assert len(statements) <= 4


# ── redaction, caps, filters, route wiring ─────────────────────────────────

def test_payload_has_no_bodies_citations_emails_or_secrets(env: Session):
    db = env
    t = _task(db, "redaction")
    svc.create_report(db, t.id, body="SECRET-BODY-TEXT",
                      citations=_cite(), provenance="human",
                      created_by="owner@example.com")
    _job(db, "agj_red", "failed", err="Trace: secret-token abc")
    payload = json.dumps(_board(db))
    assert "SECRET-BODY-TEXT" not in payload
    assert "owner@example.com" not in payload
    assert "observed_at" not in payload         # raw citations never leave
    assert "request_hash" not in payload
    assert "gw-owner" not in payload            # job created_by stays server-side


def test_per_column_cap_and_overflow(env: Session):
    db = env
    for i in range(7):
        _task(db, f"q-{i}")
    board = _board(db, per_column=3)
    col = next(c for c in board["columns"] if c["key"] == "queued")
    assert col["total"] == 7 and col["shown"] == 3 and col["overflow"] == 4
    assert board["counts"]["queued"] == 7       # counts are pre-cap


def test_route_filters_and_shape(env: Session):
    db = env
    _task(db, "alpha idea")
    _task(db, "beta idea")
    out = api.get_mission_board(owner=OWNER, db=db, column="queued",
                                q="alpha", provenance=None, freshness=None,
                                per_column=30)
    assert [c["key"] for c in out["columns"]] == ["queued"]
    assert [c["title"] for c in out["columns"][0]["cards"]] == ["alpha idea"]
    assert set(out) == {"rule_set_version", "generated_at",
                        "gateway_enabled", "counts", "columns",
                        "board_health", "source_freshness"}


def test_deterministic_output_between_calls(env: Session):
    db = env
    _task(db, "d1")
    _task(db, "d2")
    _job(db, "agj_d", "running")
    b1, b2 = _board(db), _board(db)
    b1.pop("generated_at"), b2.pop("generated_at")
    assert json.dumps(b1, sort_keys=True) == json.dumps(b2, sort_keys=True)
