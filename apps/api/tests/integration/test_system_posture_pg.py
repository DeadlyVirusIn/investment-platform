"""Research Safe Mode — persistence, signals, recovery, coupling (pg).

Pins (Wave 1B):
  * flag off: current_posture honors the override / NORMAL, reads no
    signals, writes no events;
  * signal triggers and warning/critical classification against real rows;
  * append-only event history; idempotent identical evaluation; changed
    signals append; concurrency-shaped double insert collapses on the
    NULLS NOT DISTINCT unique key;
  * recovery: SAFE cannot reach NORMAL directly; ack unlocks
    SAFE→RESTRICTED→NORMAL over clean cycles; ack refused while critical;
  * incidents: declare (restricted|safe), close re-evaluates (cannot
    manufacture NORMAL);
  * failure behavior: evaluator exception → RESTRICTED, repeated → SAFE;
    db failure never yields NORMAL;
  * payload bounds CHECKs; public projection redaction; preflight coupling
    (SAFE→HOLD, RESTRICTED caps at READY_WITH_LIMITATIONS, posture event
    id enters the preflight hash);
  * paper/portfolio isolation (module coupling introspection).
"""

from __future__ import annotations

import datetime
import inspect
import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.domain.publication import posture as ps
from apps.api.src.domain.publication import preflight as pf

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _posture_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "SYSTEM_POSTURE_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "SYSTEM_POSTURE_OVERRIDE", "", raising=False)
    ps.reset_cache_for_tests()
    yield
    ps.reset_cache_for_tests()


def _seed_healthy_world(db: Session) -> None:
    """Fresh ingest + fresh bar + outcome job + no overdue schedules."""
    for name in ("ingest_prices_daily", "score_recommendation_outcomes"):
        sid = str(uuid.uuid4())
        db.execute(text(
            "INSERT INTO job_schedule (id, name, cron_expr, enabled, "
            "next_run_at, created_at, updated_at) VALUES "
            "(:i, :n, '0 1 * * *', true, now() + interval '1 hour', now(), now()) "
            "ON CONFLICT DO NOTHING"
        ), {"i": sid, "n": name})
        real = db.execute(text(
            "SELECT id FROM job_schedule WHERE name=:n LIMIT 1"), {"n": name}
        ).scalar()
        db.execute(text(
            "INSERT INTO job_run (id, job_schedule_id, started_at, "
            "finished_at, status) VALUES (:i, :s, now() - interval '2 hours', "
            "now() - interval '1 hour', 'success')"
        ), {"i": str(uuid.uuid4()), "s": real})
    aid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO asset (id, symbol, asset_class, currency, is_active, "
        "created_at, updated_at) VALUES (:i, 'PSTX', 'equity', 'USD', true, "
        "now(), now())"), {"i": aid})
    db.execute(text(
        "INSERT INTO price_bar (id, asset_id, timeframe, ts, open, high, "
        "low, close, provider, created_at) VALUES (:i, :a, '1d', "
        "now() - interval '6 hours', 10, 11, 9, 10.5, 'test', now())"
    ), {"i": str(uuid.uuid4()), "a": aid})
    db.flush()


def _levels(db: Session) -> dict[str, str]:
    return {s.signal_id: s.level for s in ps.evaluate_signals(db)}


# ---------------------------------------------------------------------------
# flag off
# ---------------------------------------------------------------------------

def test_flag_off_reads_nothing_writes_nothing(
    pg_session: Session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SYSTEM_POSTURE_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "SYSTEM_POSTURE_OVERRIDE", "SAFE", raising=False)
    assert ps.current_posture(pg_session) == "SAFE"      # override honored
    monkeypatch.setattr(settings, "SYSTEM_POSTURE_OVERRIDE", "", raising=False)
    assert ps.current_posture(pg_session) == "NORMAL"
    n = pg_session.execute(
        text("SELECT count(*) FROM system_posture_event")).scalar()
    assert n == 0


# ---------------------------------------------------------------------------
# signal triggers + classification
# ---------------------------------------------------------------------------

def test_healthy_world_levels(pg_session: Session) -> None:
    _seed_healthy_world(pg_session)
    lv = _levels(pg_session)
    assert lv["ingest_health"] == "ok"
    assert lv["price_data"] == "ok"
    assert lv["scheduler"] == "ok"
    assert lv["outcome_pipeline"] == "ok"
    assert lv["owner_incident"] == "ok"
    # contracts flag off in tests → documented warning (RESTRICTED trigger)
    assert lv["ingest_contracts"] == "warning"


def test_missing_ingest_history_is_critical(pg_session: Session) -> None:
    assert _levels(pg_session)["ingest_health"] == "critical"


def test_failed_ingest_run_is_critical(pg_session: Session) -> None:
    _seed_healthy_world(pg_session)
    real = pg_session.execute(text(
        "SELECT id FROM job_schedule WHERE name='ingest_prices_daily'")).scalar()
    pg_session.execute(text(
        "INSERT INTO job_run (id, job_schedule_id, started_at, finished_at, "
        "status) VALUES (:i, :s, now(), now(), 'failure')"
    ), {"i": str(uuid.uuid4()), "s": real})
    pg_session.flush()
    assert _levels(pg_session)["ingest_health"] == "critical"


def test_stale_ingest_warning_vs_critical(pg_session: Session) -> None:
    _seed_healthy_world(pg_session)
    pg_session.execute(text(
        "UPDATE job_run SET finished_at = now() - interval '40 hours' "
        "WHERE status='success'"))
    pg_session.flush()
    assert _levels(pg_session)["ingest_health"] == "warning"
    pg_session.execute(text(
        "UPDATE job_run SET finished_at = now() - interval '80 hours' "
        "WHERE status='success'"))
    pg_session.flush()
    assert _levels(pg_session)["ingest_health"] == "critical"


def test_stale_price_warning_and_critical(pg_session: Session) -> None:
    _seed_healthy_world(pg_session)
    pg_session.execute(text(
        "UPDATE price_bar SET ts = now() - interval '7 days'"))
    pg_session.flush()
    assert _levels(pg_session)["price_data"] == "warning"
    pg_session.execute(text(
        "UPDATE price_bar SET ts = now() - interval '12 days'"))
    pg_session.flush()
    assert _levels(pg_session)["price_data"] == "critical"


def test_scheduler_critical_only_for_publication_inputs(
    pg_session: Session,
) -> None:
    _seed_healthy_world(pg_session)
    # a stuck NON-critical schedule → warning
    pg_session.execute(text(
        "INSERT INTO job_schedule (id, name, cron_expr, enabled, next_run_at, "
        "created_at, updated_at) VALUES (:i, 'refresh_company_names', "
        "'0 2 * * *', true, NULL, now(), now())"), {"i": str(uuid.uuid4())})
    pg_session.flush()
    assert _levels(pg_session)["scheduler"] == "warning"
    # a stuck PUBLICATION-INPUT schedule → critical
    pg_session.execute(text(
        "UPDATE job_schedule SET next_run_at = NULL "
        "WHERE name = 'ingest_prices_daily'"))
    pg_session.flush()
    assert _levels(pg_session)["scheduler"] == "critical"


# ---------------------------------------------------------------------------
# events: idempotency, append-only, concurrency, bounds
# ---------------------------------------------------------------------------

def test_idempotent_identical_evaluation(pg_session: Session) -> None:
    _seed_healthy_world(pg_session)
    e1 = ps.evaluate_and_record(pg_session)
    e2 = ps.evaluate_and_record(pg_session)
    assert e1["id"] == e2["id"]
    n = pg_session.execute(
        text("SELECT count(*) FROM system_posture_event")).scalar()
    assert n == 1


def test_changed_signals_append_new_event(pg_session: Session) -> None:
    _seed_healthy_world(pg_session)
    e1 = ps.evaluate_and_record(pg_session)
    pg_session.execute(text(
        "UPDATE job_run SET finished_at = now() - interval '80 hours' "
        "WHERE status='success'"))
    pg_session.flush()
    e2 = ps.evaluate_and_record(pg_session)
    assert e2["id"] != e1["id"]
    assert e2["posture"] == "SAFE"
    assert e2["previous_event_id"] == e1["id"]
    rows = pg_session.execute(text(
        "SELECT id FROM system_posture_event ORDER BY created_at")).all()
    assert len(rows) == 2                       # append-only history


def test_concurrent_first_event_collapses_null_prev(
    pg_session: Session,
) -> None:
    _seed_healthy_world(pg_session)
    signals = ps.evaluate_signals(pg_session)
    proposed, clean = ps.propose(signals)
    snap = ps._snapshot_json(signals, clean)
    basis = ps._hash_basis(signals, clean)
    for _ in range(2):
        ps._insert_event(pg_session, posture=proposed,
                         reasons=[{"kind": "t"}], snapshot_json=snap,
                         hash_basis=basis,
                         triggered_by="auto", previous_event_id=None)
    n = pg_session.execute(
        text("SELECT count(*) FROM system_posture_event")).scalar()
    assert n == 1                                # NULLS NOT DISTINCT key


def test_module_has_no_update_or_delete_of_events() -> None:
    src = inspect.getsource(ps)
    assert "UPDATE system_posture_event" not in src
    assert "DELETE FROM system_posture_event" not in src


def test_payload_bounds_enforced(pg_session: Session) -> None:
    with pytest.raises(Exception, match="ck_posture_event_reasons_bound|Check"):
        pg_session.execute(text(
            "INSERT INTO system_posture_event (id, posture, reasons_json, "
            "signal_snapshot_json, triggered_by, evaluator_version, "
            "evaluator_git_sha, input_hash, created_at) VALUES "
            "(:i, 'NORMAL', :big, '{}', 'auto', 'v', 's', 'h', now())"
        ), {"i": str(uuid.uuid4()), "big": "x" * 5000})
        pg_session.flush()
    pg_session.rollback()


def test_trigger_vocabulary_check(pg_session: Session) -> None:
    with pytest.raises(Exception, match="ck_posture_event_trigger|Check"):
        pg_session.execute(text(
            "INSERT INTO system_posture_event (id, posture, reasons_json, "
            "signal_snapshot_json, triggered_by, evaluator_version, "
            "evaluator_git_sha, input_hash, created_at) VALUES "
            "(:i, 'NORMAL', '[]', '{}', 'llm', 'v', 's', 'h2', now())"
        ), {"i": str(uuid.uuid4())})
        pg_session.flush()
    pg_session.rollback()


# ---------------------------------------------------------------------------
# recovery flow
# ---------------------------------------------------------------------------

def _force_safe(db: Session) -> dict:
    """Healthy world, then break ingest critically and record SAFE."""
    _seed_healthy_world(db)
    db.execute(text(
        "UPDATE job_run SET finished_at = now() - interval '80 hours' "
        "WHERE status='success'"))
    db.flush()
    e = ps.evaluate_and_record(db)
    assert e["posture"] == "SAFE"
    return e


def _heal(db: Session) -> None:
    db.execute(text(
        "UPDATE job_run SET finished_at = now() - interval '1 hour' "
        "WHERE status='success'"))
    db.flush()


def test_safe_never_normal_without_ack_then_full_recovery_path(
    pg_session: Session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_safe(pg_session)
    _heal(pg_session)
    e2 = ps.evaluate_and_record(pg_session)
    assert e2["posture"] == "SAFE"               # improved but unacknowledged
    ack = ps.acknowledge_recovery(pg_session, "owner@example.com")
    assert ack["acknowledged_by"] == "owner@example.com"
    e3 = ps.evaluate_and_record(pg_session)
    assert e3["posture"] == "RESTRICTED"         # recovering
    # Steady-state warnings (contracts flag off, unknown local git sha) keep
    # it RESTRICTED — silence both to prove the final clean-cycle steps.
    monkeypatch.setattr(settings, "INGEST_CONTRACTS_ENABLED", True,
                        raising=False)
    monkeypatch.setattr(ps, "get_build_provenance",
                        lambda: {"git_sha": "abc123def4567890"})
    e5 = ps.evaluate_and_record(pg_session)
    assert e5["posture"] == "RESTRICTED"         # clean cooldown cycle
    e6 = ps.evaluate_and_record(pg_session)
    assert e6["posture"] == "NORMAL"             # full recovery


def test_ack_refused_while_critical(pg_session: Session) -> None:
    _force_safe(pg_session)
    with pytest.raises(ps.PostureActionError, match="critical"):
        ps.acknowledge_recovery(pg_session, "owner@example.com")


def test_ack_refused_when_not_safe(pg_session: Session) -> None:
    _seed_healthy_world(pg_session)
    ps.evaluate_and_record(pg_session)
    with pytest.raises(ps.PostureActionError, match="not SAFE"):
        ps.acknowledge_recovery(pg_session, "owner@example.com")


# ---------------------------------------------------------------------------
# incidents
# ---------------------------------------------------------------------------

def test_incident_declare_and_close_cannot_manufacture_normal(
    pg_session: Session,
) -> None:
    _seed_healthy_world(pg_session)
    ps.evaluate_and_record(pg_session)
    inc = ps.declare_incident(pg_session, "owner@example.com", "safe", "drill")
    assert inc["posture"] == "SAFE"
    assert _levels(pg_session)["owner_incident"] == "critical"
    after = ps.close_incident(pg_session, "owner@example.com")
    # close re-evaluates: contracts warning still active → RESTRICTED,
    # and SAFE-recovery hysteresis applies — never a straight NORMAL.
    assert after["posture"] != "NORMAL"


def test_restricted_incident_is_warning(pg_session: Session) -> None:
    _seed_healthy_world(pg_session)
    ps.declare_incident(pg_session, "owner@example.com", "restricted", "note")
    assert _levels(pg_session)["owner_incident"] == "warning"


def test_close_without_open_incident_refused(pg_session: Session) -> None:
    _seed_healthy_world(pg_session)
    with pytest.raises(ps.PostureActionError, match="no open incident"):
        ps.close_incident(pg_session, "owner@example.com")


# ---------------------------------------------------------------------------
# failure behavior
# ---------------------------------------------------------------------------

def test_evaluator_failure_restricted_then_safe(
    pg_session: Session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*a, **k):  # noqa: ANN002, ANN003
        raise RuntimeError("synthetic")
    monkeypatch.setattr(ps, "evaluate_and_record", boom)
    ps.reset_cache_for_tests()
    assert ps.current_posture(pg_session) == "RESTRICTED"
    assert ps.current_posture(pg_session) == "RESTRICTED"
    assert ps.current_posture(pg_session) == "SAFE"       # 3rd consecutive
    assert ps.current_posture(pg_session) == "SAFE"


def test_db_failure_never_normal(monkeypatch: pytest.MonkeyPatch) -> None:
    class DeadSession:
        def execute(self, *a, **k):  # noqa: ANN002, ANN003
            raise RuntimeError("db down")
        def rollback(self):
            pass
    ps.reset_cache_for_tests()
    assert ps.current_posture(DeadSession()) in ("RESTRICTED", "SAFE")


def test_no_session_fails_closed() -> None:
    ps.reset_cache_for_tests()
    assert ps.current_posture(None) == "RESTRICTED"


# ---------------------------------------------------------------------------
# preflight coupling + isolation
# ---------------------------------------------------------------------------

def test_preflight_hash_includes_posture_event_identity(
    pg_session: Session,
) -> None:
    from apps.api.tests.integration.test_publication_preflight_pg import (
        _healthy_candidate,
    )
    rec = _healthy_candidate(pg_session)
    _seed_healthy_world(pg_session)
    i1 = pf.load_inputs(pg_session, rec)
    assert i1.posture_event_id is not None
    # posture transition (owner incident) → different event → different hash
    ps.reset_cache_for_tests()
    ps.declare_incident(pg_session, "owner@example.com", "restricted", "x")
    i2 = pf.load_inputs(pg_session, rec)
    assert i2.posture_event_id != i1.posture_event_id
    assert i1.input_hash() != i2.input_hash()
    assert pf.evaluate(i2).verdict == "READY_WITH_LIMITATIONS"


def test_safe_posture_holds_via_preflight(pg_session: Session) -> None:
    from apps.api.tests.integration.test_publication_preflight_pg import (
        _healthy_candidate,
    )
    rec = _healthy_candidate(pg_session)
    _seed_healthy_world(pg_session)
    ps.declare_incident(pg_session, "owner@example.com", "safe", "drill")
    ps.reset_cache_for_tests()
    inp = pf.load_inputs(pg_session, rec)
    assert inp.posture == "SAFE"
    assert pf.evaluate(inp).verdict == "HOLD"


def test_posture_module_never_touches_paper_or_portfolio() -> None:
    src = inspect.getsource(ps)
    for token in ("paper_trading", "paper_service", "paper_execution",
                  "exit_cycle", "submit_trade", "PaperTrade",
                  "paper_portfolio", "recommendation "):
        assert token not in src, f"posture must not couple to {token}"


def test_public_projection_redaction(pg_session: Session) -> None:
    from apps.api.src.api.system_posture import public_posture
    _seed_healthy_world(pg_session)
    out = public_posture(db=pg_session)
    assert set(out.keys()) == {
        "posture", "message", "evaluated_at", "new_ideas_paused",
        "existing_ideas_available", "portfolio_available",
    }
    blob = json.dumps(out)
    for leak in ("run_id", "job", "input_hash", "git_sha", "signal",
                 "owner:", "example.com"):
        assert leak not in blob
    assert out["existing_ideas_available"] is True
    assert out["portfolio_available"] is True
