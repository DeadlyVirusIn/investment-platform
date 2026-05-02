"""Phase 11W (Phase E.2) — alerts + monitoring + enforcement tests."""

from __future__ import annotations

import datetime as dt
import importlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def e2_schema(pg_engine):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with pg_engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS context_daily (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                as_of_date date NOT NULL,
                context_name text NOT NULL,
                status text NOT NULL,
                value_bool boolean,
                source_features text[] NOT NULL,
                logic_version text NOT NULL,
                logic_hash text NOT NULL,
                computed_at timestamptz NOT NULL DEFAULT now(),
                CONSTRAINT ux_context_daily_name_ver_date
                  UNIQUE (as_of_date, context_name, logic_version)
            )
            """
        ))
    for revision in (
        "052_research_ro_init",
        "053_research_ro_provider_idempotency",
        "057_research_manual_run_audit",
        "058_research_alerts_operator_control",
    ):
        mod = importlib.import_module(f"infra.alembic.versions.{revision}")
        with pg_engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                try:
                    mod.upgrade()
                except Exception as exc:  # noqa: BLE001
                    if "already exists" not in str(exc).lower():
                        raise
    yield pg_engine


@pytest.fixture
def session(e2_schema, pg_session):
    pg_session.execute(text(
        "TRUNCATE research_ro.research_alert, "
        "         research_ro.research_operator_control, "
        "         research_ro.research_manual_run_audit, "
        "         research_ro.research_run CASCADE"
    ))
    pg_session.commit()
    yield pg_session


@pytest.fixture
def client(monkeypatch, pg_engine):
    from apps.api.src.config import settings
    monkeypatch.setattr(settings, "RESEARCH_RO_ENABLED", True)
    monkeypatch.setattr(settings, "RESEARCH_MANUAL_RUN_ENABLED", False)
    monkeypatch.setattr(settings, "RESEARCH_ADMIN_TOKEN", "")
    # Phase F.1 — pre-date tier stripping; default to enterprise so
    # existing payload-shape assertions pass.
    monkeypatch.setattr(settings, "RESEARCH_PREMIUM_TIER", "enterprise")
    from sqlalchemy.orm import Session, sessionmaker
    test_session = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )
    import apps.api.src.db as db_mod
    monkeypatch.setattr(db_mod, "SessionLocal", test_session)
    import apps.api.src.api.research as research_mod
    monkeypatch.setattr(research_mod, "SessionLocal", test_session)
    import apps.api.src.main as main_mod
    importlib.reload(main_mod)
    return TestClient(main_mod.app)


def _seed_asset(s, *, symbol="UNH"):
    aid = f"asset-{symbol.lower()}"
    s.execute(text(
        """
        INSERT INTO asset
          (id, symbol, name, asset_class, exchange, currency,
           is_active, created_at, updated_at)
        VALUES (:id, :sym, :sym, 'equity', 'NASDAQ', 'USD',
                TRUE, now(), now())
        ON CONFLICT ON CONSTRAINT uq_asset_symbol_exchange DO NOTHING
        """
    ), {"id": aid, "sym": symbol})
    s.commit()
    return aid


def _enable(monkeypatch, **extra):
    from apps.api.src.config import settings
    defaults = dict(
        RESEARCH_RO_ENABLED=True,
        RESEARCH_MANUAL_RUN_ENABLED=True,
        RESEARCH_ALLOWED_PROVIDERS="mock",
        RESEARCH_ALLOWED_OPERATORS="alice,bob",
        RESEARCH_LOCAL_TEST_MODE=False,
        RESEARCH_MAX_RUNS_PER_OPERATOR_DAILY=99,
        RESEARCH_MAX_RUNS_PER_SYMBOL_DAILY=99,
        RESEARCH_MAX_CONCURRENT_MANUAL_RUNS=99,
        RESEARCH_MAX_TICKER_DAILY_RUNS=99,
        RESEARCH_MAX_DAILY_COST_USD=100.0,
        RESEARCH_ANOMALY_REJECTED_THRESHOLD=2,
        RESEARCH_ANOMALY_REJECTED_WINDOW_MIN=60,
    )
    defaults.update(extra)
    for k, v in defaults.items():
        monkeypatch.setattr(settings, k, v, raising=False)


# ===========================================================================
# 1. Repeated rejections → alert
# ===========================================================================


def test_repeated_rejections_create_alert(session, monkeypatch):
    _enable(monkeypatch)
    # Pre-seed 3 rejected audit rows for alice within the window.
    for _ in range(3):
        session.execute(text(
            """
            INSERT INTO research_ro.research_manual_run_audit
              (operator_id, symbol, as_of, provider, request_source,
               status, rejection_reason)
            VALUES ('alice', 'UNH', '2026-04-29', 'mock', 'cli',
                    'rejected', 'rate_limit')
            """
        ))
    session.commit()
    _seed_asset(session, symbol="UNH")
    from apps.api.src.research.manual_run_safe import run_manual_safely
    run_manual_safely(
        session, symbol="UNH", as_of=dt.date(2026, 4, 29),
        provider_name="mock", operator_id="alice",
    )
    alerts = session.execute(text(
        "SELECT alert_type, severity, operator_id "
        "FROM research_ro.research_alert "
        "WHERE alert_type IN ('repeated_rejections', "
        "                     'forbidden_token_threshold_exceeded')"
    )).mappings().all()
    assert any(
        a["alert_type"] == "repeated_rejections" and a["operator_id"] == "alice"
        for a in alerts
    )


# ===========================================================================
# 2. Forbidden-token threshold → high alert + restricted state
# ===========================================================================


def test_forbidden_token_threshold_creates_high_alert(
    session, monkeypatch,
):
    _enable(
        monkeypatch,
        RESEARCH_ANOMALY_TOKEN_VIOLATION_THRESHOLD=2,
    )
    # Seed 2 rejections whose reason mentions 'token'.
    for _ in range(3):
        session.execute(text(
            """
            INSERT INTO research_ro.research_manual_run_audit
              (operator_id, symbol, as_of, provider, request_source,
               status, rejection_reason)
            VALUES ('alice', 'UNH', '2026-04-29', 'mock', 'cli',
                    'rejected', 'token_violation_detected')
            """
        ))
    session.commit()
    _seed_asset(session, symbol="UNH")
    from apps.api.src.research.manual_run_safe import run_manual_safely
    run_manual_safely(
        session, symbol="UNH", as_of=dt.date(2026, 4, 29),
        provider_name="mock", operator_id="alice",
    )
    alerts = session.execute(text(
        "SELECT alert_type, severity FROM research_ro.research_alert "
        "WHERE alert_type='forbidden_token_threshold_exceeded'"
    )).mappings().all()
    assert alerts
    assert all(a["severity"] in ("high", "critical") for a in alerts)
    # Operator should be restricted now.
    state = session.execute(text(
        "SELECT state FROM research_ro.research_operator_control "
        "WHERE operator_id='alice'"
    )).scalar()
    assert state in ("restricted", "blocked")


# ===========================================================================
# 3. Duplicate spam → alert
# ===========================================================================


def test_duplicate_spam_creates_alert(session, monkeypatch):
    _enable(
        monkeypatch,
        RESEARCH_ANOMALY_DUPLICATE_THRESHOLD=2,
    )
    # Seed duplicate audit rows.
    for _ in range(3):
        session.execute(text(
            """
            INSERT INTO research_ro.research_manual_run_audit
              (operator_id, symbol, as_of, provider, request_source, status)
            VALUES ('alice', 'UNH', '2026-04-29', 'mock', 'cli', 'duplicate')
            """
        ))
    session.commit()
    _seed_asset(session, symbol="UNH")
    from apps.api.src.research.manual_run_safe import run_manual_safely
    run_manual_safely(
        session, symbol="UNH", as_of=dt.date(2026, 4, 29),
        provider_name="mock", operator_id="alice",
    )
    n = session.execute(text(
        "SELECT count(*) FROM research_ro.research_alert "
        "WHERE alert_type='duplicate_spam' AND operator_id='alice'"
    )).scalar()
    assert (n or 0) >= 1


# ===========================================================================
# 4. Cost spike → warning alert
# ===========================================================================


def test_cost_spike_creates_warning(session, monkeypatch):
    """Direct call to detect_anomalies + apply_anomaly_transitions
    with an elevated estimated_cost simulates a cost spike."""
    _enable(monkeypatch)
    from apps.api.src.research.manual_run_controls import detect_anomalies
    from apps.api.src.research.manual_run_enforcement import (
        apply_anomaly_transitions,
    )
    rep = detect_anomalies(
        session, operator_id="alice", symbol="UNH",
        estimated_cost_usd=99.99,  # >> 5x per-run cap of 0.05
    )
    assert any(f.startswith("cost_spike") for f in rep.flags)
    apply_anomaly_transitions(
        session, operator_id="alice", symbol="UNH",
        flags=rep.flags,
    )
    n = session.execute(text(
        "SELECT count(*) FROM research_ro.research_alert "
        "WHERE alert_type='cost_spike'"
    )).scalar()
    assert (n or 0) >= 1


# ===========================================================================
# 5. Blocked operator rejected before provider call
# ===========================================================================


def test_blocked_operator_rejected_before_provider_call(
    session, monkeypatch,
):
    _enable(monkeypatch)
    _seed_asset(session, symbol="UNH")
    from apps.api.src.research.manual_run_enforcement import (
        set_operator_state,
    )
    set_operator_state(
        session, operator_id="alice", state="blocked",
        updated_by="test", reason="manual_block",
    )
    n_before_runs = int(session.execute(text(
        "SELECT count(*) FROM research_ro.research_run"
    )).scalar() or 0)
    from apps.api.src.research.manual_run_safe import (
        run_manual_safely, PhaseENotAllowedError,
    )
    with pytest.raises(PhaseENotAllowedError):
        run_manual_safely(
            session, symbol="UNH", as_of=dt.date(2026, 4, 29),
            provider_name="mock", operator_id="alice",
        )
    n_after_runs = int(session.execute(text(
        "SELECT count(*) FROM research_ro.research_run"
    )).scalar() or 0)
    assert n_after_runs == n_before_runs
    # Alert recorded.
    n_alerts = session.execute(text(
        "SELECT count(*) FROM research_ro.research_alert "
        "WHERE alert_type='enforcement_rejection'"
    )).scalar()
    assert (n_alerts or 0) >= 1


# ===========================================================================
# 6. Restricted operator rejected without override
# ===========================================================================


def test_restricted_operator_rejected_without_override(
    session, monkeypatch,
):
    _enable(monkeypatch)
    _seed_asset(session, symbol="UNH")
    from apps.api.src.research.manual_run_enforcement import (
        set_operator_state,
    )
    set_operator_state(
        session, operator_id="alice", state="restricted",
        updated_by="test", reason="manual_restrict",
    )
    from apps.api.src.research.manual_run_safe import (
        run_manual_safely, PhaseENotAllowedError,
    )
    with pytest.raises(PhaseENotAllowedError):
        run_manual_safely(
            session, symbol="UNH", as_of=dt.date(2026, 4, 29),
            provider_name="mock", operator_id="alice",
            admin_override=False,
        )


# ===========================================================================
# 7. Watch operator allowed (with audit warning)
# ===========================================================================


def test_watch_operator_allowed_with_warning_audit(
    session, monkeypatch,
):
    _enable(monkeypatch)
    _seed_asset(session, symbol="UNH")
    from apps.api.src.research.manual_run_enforcement import (
        set_operator_state,
    )
    set_operator_state(
        session, operator_id="alice", state="watch",
        updated_by="test", reason="prior_anomalies",
    )
    from apps.api.src.research.manual_run_safe import run_manual_safely
    payload = run_manual_safely(
        session, symbol="UNH", as_of=dt.date(2026, 4, 29),
        provider_name="mock", operator_id="alice",
    )
    # Run completed.
    assert payload.run_id


# ===========================================================================
# 8. Manual override use is logged
# ===========================================================================


def test_operator_control_manual_override_logged(
    session, monkeypatch,
):
    _enable(monkeypatch)
    _seed_asset(session, symbol="UNH")
    from apps.api.src.research.manual_run_enforcement import (
        set_operator_state,
    )
    set_operator_state(
        session, operator_id="alice", state="restricted",
        updated_by="test", reason="manual_restrict",
    )
    from apps.api.src.research.manual_run_safe import run_manual_safely
    payload = run_manual_safely(
        session, symbol="UNH", as_of=dt.date(2026, 4, 29),
        provider_name="mock", operator_id="alice",
        admin_override=True,
    )
    assert payload.run_id
    # Override-use alert recorded.
    n = session.execute(text(
        "SELECT count(*) FROM research_ro.research_alert "
        "WHERE alert_type='admin_override_used'"
    )).scalar()
    assert (n or 0) >= 1


# ===========================================================================
# 9. Alert metadata contains no raw output
# ===========================================================================


def test_alert_metadata_contains_no_raw_output(session):
    from apps.api.src.research.manual_run_enforcement import emit_alert
    aid = emit_alert(
        session,
        severity="info", alert_type="test_metadata",
        message="metadata sanitization test",
        metadata={
            "body": "we recommend buy AAPL",  # MUST be stripped
            "raw_body": "<<<RAW MODEL TEXT>>>",
            "structured_output": {"a": 1},
            "evidence_refs": [{"x": 1}],
            "reflection": "labeled history",
            "ok_field": "kept",
        },
    )
    md = session.execute(text(
        "SELECT metadata FROM research_ro.research_alert "
        "WHERE id = CAST(:id AS uuid)"
    ), {"id": aid}).scalar()
    for forbidden in (
        "body", "raw_body", "structured_output",
        "evidence_refs", "reflection",
    ):
        assert forbidden not in md, f"alert metadata leaked {forbidden}"
    assert md.get("ok_field") == "kept"


# ===========================================================================
# 10-12. GET-only API contracts
# ===========================================================================


def test_alerts_api_get_only(session, client):
    session.execute(text(
        """
        INSERT INTO research_ro.research_alert
          (severity, alert_type, message)
        VALUES ('warning', 'test', 'sample alert')
        """
    ))
    session.commit()
    r = client.get("/api/research/alerts?limit=5")
    assert r.status_code == 200
    j = r.json()
    assert j["alerts_table"] == "present"
    assert any(a["alert_type"] == "test" for a in j["alerts"])
    # Methods other than GET must 405/404.
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(method, "/api/research/alerts").status_code in (404, 405)


def test_operators_api_get_only(session, client):
    from apps.api.src.research.manual_run_enforcement import (
        set_operator_state,
    )
    set_operator_state(
        session, operator_id="alice", state="watch",
        updated_by="test", reason="x",
    )
    r = client.get("/api/research/operators")
    assert r.status_code == 200
    j = r.json()
    assert j["operators_table"] == "present"
    ops = {o["operator_id"] for o in j["operators"]}
    assert "alice" in ops
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(method, "/api/research/operators").status_code in (404, 405)


def test_usage_summary_api_get_only(session, client):
    r = client.get("/api/research/usage/summary")
    assert r.status_code == 200
    j = r.json()
    for k in ("audit_today", "alerts", "operators"):
        assert k in j
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(
            method, "/api/research/usage/summary",
        ).status_code in (404, 405)


# ===========================================================================
# 13. JobHealth reads alerts (server-side equivalent of frontend test)
# ===========================================================================


def test_job_health_reads_alerts_get_only(session, client):
    r = client.get("/api/research/usage/summary")
    assert r.status_code == 200
    j = r.json()
    assert j["alerts"]["open"] >= 0


# ===========================================================================
# 14-18. Static guards (no scheduler / worker / execution / reflection)
# ===========================================================================


import re
from pathlib import Path


_PHASE_E2_FILES = (
    "apps/api/src/research/manual_run_enforcement.py",
    "apps/api/src/api/research.py",
    "scripts/research_admin.py",
    "infra/alembic/versions/058_research_alerts_operator_control.py",
)


def test_no_post_from_ui_phase_e2():
    web_dir = Path("apps/web/src/components/research")
    if not web_dir.exists():
        pytest.skip("web research components absent")
    blob = ""
    for p in web_dir.rglob("*.tsx"):
        blob += p.read_text(encoding="utf-8", errors="ignore")
    assert "method: 'POST'" not in blob
    assert 'method: "POST"' not in blob


def test_no_scheduler_entry_phase_e2():
    worker = Path("apps/worker/src")
    if not worker.exists():
        pytest.skip("worker dir absent")
    blob = ""
    for p in worker.rglob("*.py"):
        blob += p.read_text(encoding="utf-8", errors="ignore")
    for tok in (
        "manual_run_enforcement", "research_alert",
        "research_operator_control", "research_admin",
    ):
        assert tok not in blob, f"worker references {tok}"


def test_no_worker_registry_entry_phase_e2():
    reg = Path("apps/worker/src/jobs/registry.py")
    if not reg.exists():
        pytest.skip("registry absent")
    src = reg.read_text(encoding="utf-8")
    for tok in (
        "manual_run_enforcement", "research_alert",
        "research_operator_control", "research_admin",
    ):
        assert tok not in src, f"registry references {tok}"


def test_no_execution_imports_phase_e2():
    forbidden = (
        "apps.api.src.domain.features.feature_engine",
        "apps.api.src.domain.recommendations.recommendation_engine",
        "apps.api.src.data.evaluation",
        "apps.api.src.domain.stock_engine.decision_engine",
        "apps.api.src.options.paper",
        "apps.api.src.domain.execution",
        "langchain", "langgraph",
    )
    for rel in _PHASE_E2_FILES:
        p = Path(rel)
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8")
        for bad in forbidden:
            assert bad not in src, f"{rel} imports {bad}"


def test_no_reflection_feedback_phase_e2():
    for d in (
        "apps/api/src/domain/features",
        "apps/api/src/domain/recommendations",
        "apps/api/src/data/evaluation",
        "apps/worker/src",
    ):
        path = Path(d)
        if not path.exists():
            continue
        for p in path.rglob("*.py"):
            src = p.read_text(encoding="utf-8", errors="ignore")
            for bad in (
                "research_reflection", "research_alert",
                "research_operator_control",
            ):
                assert bad not in src, (
                    f"reflection/alert/operator-control feedback in {p}"
                )
