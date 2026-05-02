"""Phase 11W (Phase E.3) — auto enforcement + cooldown integration."""

from __future__ import annotations

import datetime as dt
import importlib

import pytest
from sqlalchemy import text


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def e3_schema(pg_engine):
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
        "059_research_operator_cooldown_history",
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
def session(e3_schema, pg_session):
    pg_session.execute(text(
        "TRUNCATE research_ro.research_operator_control_history, "
        "         research_ro.research_alert, "
        "         research_ro.research_operator_control, "
        "         research_ro.research_manual_run_audit, "
        "         research_ro.research_run CASCADE"
    ))
    pg_session.commit()
    yield pg_session


def _set(monkeypatch, **kw):
    from apps.api.src.config import settings
    for k, v in kw.items():
        monkeypatch.setattr(settings, k, v, raising=False)


def _enable(monkeypatch, **extra):
    defaults = dict(
        RESEARCH_RO_ENABLED=True,
        RESEARCH_MANUAL_RUN_ENABLED=True,
        RESEARCH_AUTO_ENFORCEMENT_ENABLED=True,
        RESEARCH_ALLOWED_PROVIDERS="mock",
        RESEARCH_ALLOWED_OPERATORS="alice,bob",
        RESEARCH_LOCAL_TEST_MODE=False,
        RESEARCH_MAX_RUNS_PER_OPERATOR_DAILY=99,
        RESEARCH_MAX_RUNS_PER_SYMBOL_DAILY=99,
        RESEARCH_MAX_CONCURRENT_MANUAL_RUNS=99,
        RESEARCH_MAX_TICKER_DAILY_RUNS=99,
        RESEARCH_MAX_DAILY_COST_USD=100.0,
        RESEARCH_ANOMALY_REJECTED_THRESHOLD=2,
        RESEARCH_ANOMALY_TOKEN_VIOLATION_THRESHOLD=2,
        RESEARCH_ANOMALY_DUPLICATE_THRESHOLD=2,
        RESEARCH_ENFORCEMENT_LOOKBACK_HOURS=24,
        RESEARCH_WATCH_COOLDOWN_HOURS=24,
        RESEARCH_RESTRICTED_COOLDOWN_HOURS=24,
        RESEARCH_TOKEN_RESTRICTED_COOLDOWN_HOURS=72,
        RESEARCH_BLOCKED_COOLDOWN_HOURS=24,
        RESEARCH_ADMIN_OVERRIDE_WATCH_THRESHOLD=2,
        RESEARCH_ADMIN_OVERRIDE_RESTRICT_THRESHOLD=5,
        RESEARCH_ALERT_DEDUP_WINDOW_MIN=30,
        RESEARCH_ALERT_AUTO_RESOLVE_HOURS=24,
    )
    defaults.update(extra)
    _set(monkeypatch, **defaults)


def _seed_audit(s, *, op, status, reason=None):
    s.execute(text(
        """
        INSERT INTO research_ro.research_manual_run_audit
          (operator_id, symbol, as_of, provider, request_source,
           status, rejection_reason)
        VALUES (:op, 'UNH', '2026-04-29', 'mock', 'cli', :st, :r)
        """
    ), {"op": op, "st": status, "r": reason})
    s.commit()


def _seed_alert(s, *, op, alert_type, severity="warning"):
    s.execute(text(
        """
        INSERT INTO research_ro.research_alert
          (severity, alert_type, operator_id, message)
        VALUES (:sev, :at, :op, :m)
        """
    ), {"sev": severity, "at": alert_type, "op": op, "m": "test"})
    s.commit()


def _set_state(s, *, op, state, blocked_until=None, restricted_until=None):
    s.execute(text(
        """
        INSERT INTO research_ro.research_operator_control
          (operator_id, state, updated_by, blocked_until, restricted_until)
        VALUES (:op, :st, 'test', :bu, :ru)
        ON CONFLICT (operator_id) DO UPDATE
          SET state = EXCLUDED.state,
              blocked_until = EXCLUDED.blocked_until,
              restricted_until = EXCLUDED.restricted_until,
              updated_at = now()
        """
    ), {
        "op": op, "st": state, "bu": blocked_until, "ru": restricted_until,
    })
    s.commit()


# ===========================================================================
# Auto evaluation rules
# ===========================================================================


def test_repeated_rejections_auto_watch_24h(session, monkeypatch):
    _enable(monkeypatch)
    for _ in range(3):
        _seed_audit(session, op="alice", status="rejected", reason="cap")
    from apps.api.src.research.manual_run_auto_enforcement import (
        evaluate_operator_state,
    )
    ev = evaluate_operator_state(session, operator_id="alice", dry_run=True)
    assert ev.desired_state == "watch"
    assert ev.reason == "repeated_rejections"
    assert ev.cooldown_until is not None


def test_duplicate_spam_auto_restricts_24h(session, monkeypatch):
    _enable(monkeypatch)
    for _ in range(3):
        _seed_audit(session, op="alice", status="duplicate")
    from apps.api.src.research.manual_run_auto_enforcement import (
        evaluate_operator_state,
    )
    ev = evaluate_operator_state(session, operator_id="alice", dry_run=True)
    assert ev.desired_state == "restricted"
    assert ev.reason == "duplicate_spam"


def test_forbidden_tokens_auto_restricts_72h(session, monkeypatch):
    _enable(monkeypatch)
    for _ in range(3):
        _seed_audit(session, op="alice",
                    status="rejected", reason="token_violation")
    from apps.api.src.research.manual_run_auto_enforcement import (
        evaluate_operator_state,
    )
    ev = evaluate_operator_state(session, operator_id="alice", dry_run=True)
    assert ev.desired_state == "restricted"
    assert ev.reason == "repeated_token_violations"
    expected_h = 72
    assert ev.cooldown_until is not None
    delta_h = (
        ev.cooldown_until - dt.datetime.now(dt.timezone.utc)
    ).total_seconds() / 3600
    assert abs(delta_h - expected_h) < 1.0


def test_blocked_attempt_while_restricted_auto_blocks_24h(
    session, monkeypatch,
):
    _enable(monkeypatch)
    _set_state(session, op="alice", state="restricted")
    _seed_audit(session, op="alice",
                status="rejected", reason="blocked_attempt")
    from apps.api.src.research.manual_run_auto_enforcement import (
        evaluate_operator_state,
    )
    ev = evaluate_operator_state(session, operator_id="alice", dry_run=True)
    assert ev.desired_state == "blocked"
    assert ev.reason == "blocked_attempt_while_restricted"


def test_repeated_admin_override_usage_watch(session, monkeypatch):
    _enable(monkeypatch, RESEARCH_ADMIN_OVERRIDE_WATCH_THRESHOLD=2,
            RESEARCH_ADMIN_OVERRIDE_RESTRICT_THRESHOLD=5)
    for _ in range(2):
        _seed_alert(session, op="alice",
                    alert_type="admin_override_used", severity="warning")
    from apps.api.src.research.manual_run_auto_enforcement import (
        evaluate_operator_state,
    )
    ev = evaluate_operator_state(session, operator_id="alice", dry_run=True)
    assert ev.desired_state in ("watch", "restricted")
    assert ev.reason == "repeated_admin_override_usage"


def test_repeated_admin_override_usage_restrict(session, monkeypatch):
    _enable(monkeypatch, RESEARCH_ADMIN_OVERRIDE_WATCH_THRESHOLD=2,
            RESEARCH_ADMIN_OVERRIDE_RESTRICT_THRESHOLD=3)
    for _ in range(5):
        _seed_alert(session, op="alice",
                    alert_type="admin_override_used", severity="high")
    from apps.api.src.research.manual_run_auto_enforcement import (
        evaluate_operator_state,
    )
    ev = evaluate_operator_state(session, operator_id="alice", dry_run=True)
    assert ev.desired_state == "restricted"


# ===========================================================================
# Cooldown / demotion
# ===========================================================================


def test_watch_expiry_returns_clear_without_recent_violations(
    session, monkeypatch,
):
    _enable(monkeypatch)
    _set_state(session, op="alice", state="watch")
    from apps.api.src.research.manual_run_auto_enforcement import (
        evaluate_operator_state,
    )
    ev = evaluate_operator_state(session, operator_id="alice", dry_run=True)
    assert ev.desired_state == "clear"


def test_restricted_expiry_returns_watch_with_recent_warning(
    session, monkeypatch,
):
    _enable(monkeypatch)
    _set_state(session, op="alice", state="restricted",
               restricted_until=dt.datetime.now(dt.timezone.utc)
                                - dt.timedelta(minutes=1))
    _seed_audit(session, op="alice", status="rejected", reason="cap")
    from apps.api.src.research.manual_run_auto_enforcement import (
        evaluate_operator_state,
    )
    ev = evaluate_operator_state(session, operator_id="alice", dry_run=True)
    assert ev.desired_state == "watch"


def test_restricted_expiry_returns_clear_without_recent_violations(
    session, monkeypatch,
):
    _enable(monkeypatch)
    _set_state(session, op="alice", state="restricted",
               restricted_until=dt.datetime.now(dt.timezone.utc)
                                - dt.timedelta(minutes=1))
    from apps.api.src.research.manual_run_auto_enforcement import (
        evaluate_operator_state,
    )
    ev = evaluate_operator_state(session, operator_id="alice", dry_run=True)
    assert ev.desired_state == "clear"


def test_blocked_expiry_returns_restricted_with_recent_high(
    session, monkeypatch,
):
    _enable(monkeypatch)
    _set_state(session, op="alice", state="blocked",
               blocked_until=dt.datetime.now(dt.timezone.utc)
                             - dt.timedelta(minutes=1))
    _seed_audit(session, op="alice",
                status="rejected", reason="token_violation")
    from apps.api.src.research.manual_run_auto_enforcement import (
        evaluate_operator_state,
    )
    ev = evaluate_operator_state(session, operator_id="alice", dry_run=True)
    # Token-violation rule may escalate to restricted directly OR
    # demotion may produce restricted via "blocked_expired_high_signals".
    assert ev.desired_state == "restricted"


def test_blocked_expiry_returns_clear_without_recent_violations(
    session, monkeypatch,
):
    _enable(monkeypatch)
    _set_state(session, op="alice", state="blocked",
               blocked_until=dt.datetime.now(dt.timezone.utc)
                             - dt.timedelta(minutes=1))
    from apps.api.src.research.manual_run_auto_enforcement import (
        evaluate_operator_state,
    )
    ev = evaluate_operator_state(session, operator_id="alice", dry_run=True)
    assert ev.desired_state == "clear"


def test_no_demotion_when_cooldown_not_expired(session, monkeypatch):
    _enable(monkeypatch)
    _set_state(session, op="alice", state="blocked",
               blocked_until=dt.datetime.now(dt.timezone.utc)
                             + dt.timedelta(hours=4))
    from apps.api.src.research.manual_run_auto_enforcement import (
        evaluate_operator_state,
    )
    ev = evaluate_operator_state(session, operator_id="alice", dry_run=True)
    assert ev.would_change is False
    assert ev.desired_state == "blocked"


# ===========================================================================
# Alert lifecycle
# ===========================================================================


def test_alert_deduplication_window(session, monkeypatch):
    _enable(monkeypatch)
    from apps.api.src.research.manual_run_auto_enforcement import (
        dedupe_or_create_alert,
    )
    a1 = dedupe_or_create_alert(
        session, operator_id="alice", alert_type="cost_spike",
        severity="warning", message="first one",
    )
    a2 = dedupe_or_create_alert(
        session, operator_id="alice", alert_type="cost_spike",
        severity="warning", message="duplicate one",
    )
    assert a1.deduped is False
    assert a2.deduped is True
    assert a1.alert_id == a2.alert_id


def test_alert_auto_resolves_when_operator_clear(session, monkeypatch):
    _enable(monkeypatch, RESEARCH_ALERT_AUTO_RESOLVE_HOURS=0)
    _set_state(session, op="alice", state="clear")
    session.execute(text(
        """
        INSERT INTO research_ro.research_alert
          (severity, alert_type, operator_id, message, created_at)
        VALUES ('warning','test','alice','old',
                now() - interval '5 hours')
        """
    ))
    session.commit()
    from apps.api.src.research.manual_run_auto_enforcement import (
        auto_resolve_stale_alerts,
    )
    n = auto_resolve_stale_alerts(session, operator_id="alice")
    assert n == 1


def test_alert_metadata_sanitizes_raw_output_keys(session):
    from apps.api.src.research.manual_run_auto_enforcement import (
        sanitize_metadata,
    )
    md = sanitize_metadata({
        "body": "x", "raw_body": "x", "structured_output": {"y": 1},
        "evidence_refs": [{"a": 1}], "reflection": "x", "prompt": "x",
        "ok": "kept",
    })
    for bad in (
        "body", "raw_body", "structured_output",
        "evidence_refs", "reflection", "prompt",
    ):
        assert bad not in md
    assert md["ok"] == "kept"


def test_alert_message_forbidden_tokens_blocked(session):
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        session.execute(text(
            """
            INSERT INTO research_ro.research_alert
              (severity, alert_type, message)
            VALUES ('warning','test','we recommend buy AAPL')
            """
        ))
        session.flush()
    session.rollback()


# ===========================================================================
# Manual flow integration
# ===========================================================================


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


def test_auto_enforcement_runs_before_provider_call(
    session, monkeypatch,
):
    """auto-enforce escalates state from rejected history. Then the
    enforcement check raises before the provider is imported."""
    _enable(monkeypatch)
    _seed_asset(session, symbol="UNH")
    # Pre-seed 3 token-violation rejections so the auto rule
    # escalates alice to restricted.
    for _ in range(3):
        _seed_audit(session, op="alice",
                    status="rejected", reason="token_violation")
    from apps.api.src.research.manual_run_safe import (
        run_manual_safely, PhaseENotAllowedError,
    )
    n_runs_before = int(session.execute(
        text("SELECT count(*) FROM research_ro.research_run")
    ).scalar() or 0)
    with pytest.raises(PhaseENotAllowedError):
        run_manual_safely(
            session, symbol="UNH", as_of=dt.date(2026, 4, 29),
            provider_name="mock", operator_id="alice",
        )
    n_runs_after = int(session.execute(
        text("SELECT count(*) FROM research_ro.research_run")
    ).scalar() or 0)
    assert n_runs_after == n_runs_before
    # Operator was escalated.
    state = session.execute(text(
        "SELECT state FROM research_ro.research_operator_control "
        "WHERE operator_id='alice'"
    )).scalar()
    assert state in ("restricted", "blocked")


def test_blocked_operator_provider_call_count_zero(
    session, monkeypatch,
):
    _enable(monkeypatch)
    _seed_asset(session, symbol="UNH")
    _set_state(session, op="alice", state="blocked",
               blocked_until=dt.datetime.now(dt.timezone.utc)
                             + dt.timedelta(hours=24))
    from apps.api.src.research.manual_run_safe import (
        run_manual_safely, PhaseENotAllowedError,
    )
    n_before = int(session.execute(
        text("SELECT count(*) FROM research_ro.research_run")
    ).scalar() or 0)
    with pytest.raises(PhaseENotAllowedError):
        run_manual_safely(
            session, symbol="UNH", as_of=dt.date(2026, 4, 29),
            provider_name="mock", operator_id="alice",
        )
    n_after = int(session.execute(
        text("SELECT count(*) FROM research_ro.research_run")
    ).scalar() or 0)
    assert n_after == n_before


def test_restricted_operator_provider_call_count_zero(
    session, monkeypatch,
):
    _enable(monkeypatch)
    _seed_asset(session, symbol="UNH")
    _set_state(session, op="alice", state="restricted",
               restricted_until=dt.datetime.now(dt.timezone.utc)
                                + dt.timedelta(hours=24))
    from apps.api.src.research.manual_run_safe import (
        run_manual_safely, PhaseENotAllowedError,
    )
    n_before = int(session.execute(
        text("SELECT count(*) FROM research_ro.research_run")
    ).scalar() or 0)
    with pytest.raises(PhaseENotAllowedError):
        run_manual_safely(
            session, symbol="UNH", as_of=dt.date(2026, 4, 29),
            provider_name="mock", operator_id="alice",
            admin_override=False,
        )
    n_after = int(session.execute(
        text("SELECT count(*) FROM research_ro.research_run")
    ).scalar() or 0)
    assert n_after == n_before


def test_watch_operator_allowed_and_audited(session, monkeypatch):
    _enable(monkeypatch)
    _seed_asset(session, symbol="UNH")
    _set_state(session, op="alice", state="watch")
    from apps.api.src.research.manual_run_safe import run_manual_safely
    payload = run_manual_safely(
        session, symbol="UNH", as_of=dt.date(2026, 4, 29),
        provider_name="mock", operator_id="alice",
    )
    assert payload.run_id


def test_auto_enforcement_disabled_dry_run_only(session, monkeypatch):
    """With RESEARCH_AUTO_ENFORCEMENT_ENABLED=false, no Phase E.3
    history rows are written by the manual run path (Phase E.1
    anomaly transitions remain independently active and may still
    update state)."""
    _enable(monkeypatch, RESEARCH_AUTO_ENFORCEMENT_ENABLED=False)
    _seed_asset(session, symbol="UNH")
    for _ in range(3):
        _seed_audit(session, op="alice",
                    status="rejected", reason="token_violation")
    n_hist_before = int(session.execute(text(
        "SELECT count(*) FROM research_ro.research_operator_control_history "
        "WHERE source='auto'"
    )).scalar() or 0)
    from apps.api.src.research.manual_run_safe import run_manual_safely
    run_manual_safely(
        session, symbol="UNH", as_of=dt.date(2026, 4, 29),
        provider_name="mock", operator_id="alice",
    )
    n_hist_after = int(session.execute(text(
        "SELECT count(*) FROM research_ro.research_operator_control_history "
        "WHERE source='auto'"
    )).scalar() or 0)
    # Phase E.3 auto-enforcement is OFF → no auto history entries
    # were written. (Phase E.1 anomaly path may still mutate state
    # via a different code path; that's expected and not gated by
    # the E.3 flag.)
    assert n_hist_after == n_hist_before


# ===========================================================================
# CLI / static guards
# ===========================================================================


def test_cli_evaluate_all_no_provider_call(session, monkeypatch):
    _enable(monkeypatch)
    for _ in range(3):
        _seed_audit(session, op="alice",
                    status="rejected", reason="token_violation")
    n_before = int(session.execute(
        text("SELECT count(*) FROM research_ro.research_run")
    ).scalar() or 0)
    from apps.api.src.research.manual_run_auto_enforcement import (
        evaluate_all_operators,
    )
    evals = evaluate_all_operators(session, dry_run=False)
    n_after = int(session.execute(
        text("SELECT count(*) FROM research_ro.research_run")
    ).scalar() or 0)
    assert n_after == n_before  # bulk eval never invokes provider
    assert any(
        e.operator_id == "alice" and e.would_change
        for e in evals
    )


def test_cli_manual_state_change_writes_history(session, monkeypatch):
    _enable(monkeypatch)
    from apps.api.src.research.manual_run_auto_enforcement import (
        EnforcementEvaluation, apply_operator_state_transition,
    )
    ev = EnforcementEvaluation(
        operator_id="alice", current_state="clear",
        desired_state="watch", reason="manual",
        severity="info", cooldown_until=None,
        source="manual", would_change=True, dry_run=False,
        sanitized_metadata={"by": "test"},
    )
    apply_operator_state_transition(
        session, evaluation=ev, source="manual",
    )
    n = session.execute(text(
        "SELECT count(*) FROM research_ro.research_operator_control_history "
        "WHERE operator_id='alice'"
    )).scalar()
    assert (n or 0) >= 1


# Static guards.
import re
from pathlib import Path


_PHASE_E3_FILES = (
    "apps/api/src/research/manual_run_auto_enforcement.py",
    "apps/api/src/research/manual_run_safe.py",
    "scripts/research_admin.py",
    "infra/alembic/versions/059_research_operator_cooldown_history.py",
)


def test_no_scheduler_entry_phase_e3():
    worker = Path("apps/worker/src")
    if not worker.exists():
        pytest.skip("worker dir absent")
    blob = ""
    for p in worker.rglob("*.py"):
        blob += p.read_text(encoding="utf-8", errors="ignore")
    for tok in (
        "manual_run_auto_enforcement",
        "research_operator_control_history",
    ):
        assert tok not in blob


def test_no_worker_registry_entry_phase_e3():
    reg = Path("apps/worker/src/jobs/registry.py")
    if not reg.exists():
        pytest.skip("registry absent")
    src = reg.read_text(encoding="utf-8")
    for tok in (
        "manual_run_auto_enforcement",
        "research_operator_control_history",
    ):
        assert tok not in src


def test_no_execution_imports_phase_e3():
    forbidden = (
        "apps.api.src.domain.features.feature_engine",
        "apps.api.src.domain.recommendations.recommendation_engine",
        "apps.api.src.data.evaluation",
        "apps.api.src.domain.stock_engine.decision_engine",
        "apps.api.src.options.paper",
        "apps.api.src.domain.execution",
        "langchain", "langgraph",
    )
    for rel in _PHASE_E3_FILES:
        p = Path(rel)
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8")
        for bad in forbidden:
            assert bad not in src, f"{rel} imports {bad}"


def test_no_reflection_feedback_phase_e3():
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
                "research_reflection",
                "research_operator_control_history",
                "manual_run_auto_enforcement",
            ):
                assert bad not in src


def test_no_post_routes_added_phase_e3():
    src = Path("apps/api/src/api/research.py").read_text(encoding="utf-8")
    posts = re.findall(r"@router\.(post|put|patch|delete)\b", src)
    assert posts == []


def test_no_post_from_ui_phase_e3():
    web = Path("apps/web/src/components/research")
    if not web.exists():
        pytest.skip("web research absent")
    blob = ""
    for p in web.rglob("*.tsx"):
        blob += p.read_text(encoding="utf-8", errors="ignore")
    assert "method: 'POST'" not in blob
    assert 'method: "POST"' not in blob
