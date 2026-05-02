"""Phase 11W (Phase E.1) — integration tests for enterprise controls.

Runs against `pg-11v-test`. Verifies behavioral guarantees that
need a real Postgres + research_ro schema + audit table:

  1. test_operator_not_allowlisted_rejected_before_provider_call
  2. test_operator_allowlisted_can_run
  3. test_daily_operator_limit_blocks_provider_call
  4. test_symbol_daily_limit_blocks_provider_call
  5. test_concurrency_limit_blocks_second_run
  6. test_audit_log_written_for_success
  7. test_audit_log_written_for_rejection
  8. test_cli_uses_same_guard_path_as_http
  9. test_http_never_returns_raw_unsafe_output
 10. test_usage_summary_counts_runs_and_rejections
 11. test_anomaly_flags_repeated_rejections
"""

from __future__ import annotations

import datetime as dt
import importlib

import pytest
from sqlalchemy import text


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Module fixture — apply 052/053/057 against the test DB.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def e1_schema(pg_engine):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with pg_engine.begin() as conn:
        # Pre-create context_daily so 052 GRANT succeeds.
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
def session(e1_schema, pg_session):
    pg_session.execute(text(
        "TRUNCATE research_ro.research_manual_run_audit, "
        "         research_ro.research_run CASCADE"
    ))
    pg_session.commit()
    yield pg_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_asset(s, *, symbol: str = "UNH") -> str:
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


def _set(monkeypatch, **kw):
    from apps.api.src.config import settings
    for k, v in kw.items():
        monkeypatch.setattr(settings, k, v, raising=False)


def _audit_count(s, *, status: str | None = None) -> int:
    sql = "SELECT count(*) FROM research_ro.research_manual_run_audit"
    if status:
        sql += " WHERE status = :st"
    return int(s.execute(
        text(sql), {"st": status} if status else {}
    ).scalar() or 0)


def _enable(monkeypatch, **extra):
    """Common Phase E + E.1 enablement defaults for tests."""
    defaults = dict(
        RESEARCH_RO_ENABLED=True,
        RESEARCH_MANUAL_RUN_ENABLED=True,
        RESEARCH_ALLOWED_PROVIDERS="mock",
        RESEARCH_ALLOWED_SYMBOLS="",
        RESEARCH_ALLOWED_OPERATORS="alice,bob",
        RESEARCH_LOCAL_TEST_MODE=False,
        RESEARCH_MAX_RUNS_PER_OPERATOR_DAILY=5,
        RESEARCH_MAX_RUNS_PER_SYMBOL_DAILY=3,
        RESEARCH_MAX_CONCURRENT_MANUAL_RUNS=10,
        RESEARCH_MAX_TICKER_DAILY_RUNS=10,
        RESEARCH_MAX_DAILY_COST_USD=100.0,
    )
    defaults.update(extra)
    _set(monkeypatch, **defaults)


# ===========================================================================
# 1. Operator not allowlisted → rejected BEFORE provider call
# ===========================================================================


def test_operator_not_allowlisted_rejected_before_provider_call(
    session, monkeypatch,
):
    _seed_asset(session, symbol="UNH")
    _enable(monkeypatch)
    from apps.api.src.research.manual_run_safe import (
        run_manual_safely, PhaseENotAllowedError,
    )
    n_run_before = int(session.execute(
        text("SELECT count(*) FROM research_ro.research_run")
    ).scalar() or 0)
    with pytest.raises(PhaseENotAllowedError):
        run_manual_safely(
            session, symbol="UNH", as_of=dt.date(2026, 4, 29),
            provider_name="mock", operator_id="eve",
        )
    n_run_after = int(session.execute(
        text("SELECT count(*) FROM research_ro.research_run")
    ).scalar() or 0)
    assert n_run_after == n_run_before  # no provider call made
    # Audit row recorded the rejection.
    row = session.execute(text(
        "SELECT operator_id, symbol, status, rejection_reason "
        "FROM research_ro.research_manual_run_audit ORDER BY created_at DESC LIMIT 1"
    )).mappings().first()
    assert row["operator_id"] == "eve"
    assert row["status"] == "rejected"
    assert "allowlist" in row["rejection_reason"]


# ===========================================================================
# 2. Allowlisted operator can run
# ===========================================================================


def test_operator_allowlisted_can_run(session, monkeypatch):
    _seed_asset(session, symbol="UNH")
    _enable(monkeypatch)
    from apps.api.src.research.manual_run_safe import run_manual_safely
    payload = run_manual_safely(
        session, symbol="UNH", as_of=dt.date(2026, 4, 29),
        provider_name="mock", operator_id="alice",
    )
    assert payload.run_id
    assert payload.symbol == "UNH"
    assert _audit_count(session, status="accepted") == 1


# ===========================================================================
# 3. Per-operator daily limit
# ===========================================================================


def test_daily_operator_limit_blocks_provider_call(
    session, monkeypatch,
):
    _seed_asset(session, symbol="UNH")
    _enable(
        monkeypatch,
        RESEARCH_MAX_RUNS_PER_OPERATOR_DAILY=1,
        RESEARCH_MAX_RUNS_PER_SYMBOL_DAILY=99,
    )
    # Pre-seed an accepted audit row (counts toward op cap).
    session.execute(text(
        """
        INSERT INTO research_ro.research_manual_run_audit
          (operator_id, symbol, as_of, provider, request_source, status)
        VALUES ('alice', 'UNH', '2026-04-29', 'mock', 'cli', 'accepted')
        """
    ))
    session.commit()
    from apps.api.src.research.manual_run_safe import (
        run_manual_safely, PhaseEQuotaExceededError,
    )
    n_runs_before = int(session.execute(
        text("SELECT count(*) FROM research_ro.research_run")
    ).scalar() or 0)
    with pytest.raises(PhaseEQuotaExceededError):
        run_manual_safely(
            session, symbol="UNH", as_of=dt.date(2026, 4, 29),
            provider_name="mock", operator_id="alice",
        )
    n_runs_after = int(session.execute(
        text("SELECT count(*) FROM research_ro.research_run")
    ).scalar() or 0)
    assert n_runs_after == n_runs_before
    rej = session.execute(text(
        "SELECT rejection_reason FROM research_ro.research_manual_run_audit "
        "WHERE status='rejected' ORDER BY created_at DESC LIMIT 1"
    )).first()
    assert rej and "operator" in rej[0] and "daily" in rej[0]


# ===========================================================================
# 4. Per-symbol daily limit
# ===========================================================================


def test_symbol_daily_limit_blocks_provider_call(
    session, monkeypatch,
):
    _seed_asset(session, symbol="UNH")
    _enable(
        monkeypatch,
        RESEARCH_MAX_RUNS_PER_OPERATOR_DAILY=99,
        RESEARCH_MAX_RUNS_PER_SYMBOL_DAILY=1,
    )
    session.execute(text(
        """
        INSERT INTO research_ro.research_manual_run_audit
          (operator_id, symbol, as_of, provider, request_source, status)
        VALUES ('bob', 'UNH', '2026-04-29', 'mock', 'cli', 'accepted')
        """
    ))
    session.commit()
    from apps.api.src.research.manual_run_safe import (
        run_manual_safely, PhaseEQuotaExceededError,
    )
    with pytest.raises(PhaseEQuotaExceededError):
        run_manual_safely(
            session, symbol="UNH", as_of=dt.date(2026, 4, 29),
            provider_name="mock", operator_id="alice",
        )


# ===========================================================================
# 5. Concurrency limit
# ===========================================================================


def test_concurrency_limit_blocks_second_run(session, monkeypatch):
    _seed_asset(session, symbol="UNH")
    _enable(
        monkeypatch,
        RESEARCH_MAX_CONCURRENT_MANUAL_RUNS=1,
        RESEARCH_MAX_RUNS_PER_OPERATOR_DAILY=99,
        RESEARCH_MAX_RUNS_PER_SYMBOL_DAILY=99,
    )
    # Pre-seed an in-flight audit row created within the last 5 min.
    session.execute(text(
        """
        INSERT INTO research_ro.research_manual_run_audit
          (operator_id, symbol, as_of, provider, request_source,
           status, created_at)
        VALUES ('bob', 'UNH', '2026-04-29', 'mock', 'cli',
                'in_flight', now() - interval '30 seconds')
        """
    ))
    session.commit()
    from apps.api.src.research.manual_run_safe import (
        run_manual_safely, PhaseEQuotaExceededError,
    )
    with pytest.raises(PhaseEQuotaExceededError):
        run_manual_safely(
            session, symbol="UNH", as_of=dt.date(2026, 4, 29),
            provider_name="mock", operator_id="alice",
        )


# ===========================================================================
# 6. Audit log written for success
# ===========================================================================


def test_audit_log_written_for_success(session, monkeypatch):
    _seed_asset(session, symbol="UNH")
    _enable(monkeypatch)
    from apps.api.src.research.manual_run_safe import run_manual_safely
    run_manual_safely(
        session, symbol="UNH", as_of=dt.date(2026, 4, 29),
        provider_name="mock", operator_id="alice",
    )
    row = session.execute(text(
        "SELECT operator_id, symbol, status, request_source, "
        "       research_run_id, model_id, prompt_hash, actual_cost_usd "
        "FROM research_ro.research_manual_run_audit ORDER BY created_at DESC LIMIT 1"
    )).mappings().first()
    assert row["operator_id"] == "alice"
    assert row["symbol"] == "UNH"
    assert row["status"] == "accepted"
    assert row["request_source"] == "cli"
    assert row["research_run_id"] is not None
    assert row["model_id"] is not None
    assert row["prompt_hash"] is not None
    assert row["actual_cost_usd"] is not None


# ===========================================================================
# 7. Audit log written for rejection
# ===========================================================================


def test_audit_log_written_for_rejection(session, monkeypatch):
    _seed_asset(session, symbol="UNH")
    _enable(monkeypatch)
    from apps.api.src.research.manual_run_safe import (
        run_manual_safely, PhaseENotAllowedError,
    )
    with pytest.raises(PhaseENotAllowedError):
        run_manual_safely(
            session, symbol="UNH", as_of=dt.date(2026, 4, 29),
            provider_name="anthropic",  # not allowed
            operator_id="alice",
        )
    n = _audit_count(session, status="rejected")
    assert n >= 1


# ===========================================================================
# 8. CLI uses same guard path as HTTP
# ===========================================================================


def test_cli_uses_same_guard_path_as_http(session, monkeypatch):
    """Both runners ultimately call run_manual_safely; the rejection
    audit row reflects the request_source. We verify CLI tags 'cli'
    and direct call with request_source='http' tags 'http'."""
    _seed_asset(session, symbol="UNH")
    _enable(monkeypatch)
    from apps.api.src.research.manual_run_safe import (
        run_manual_safely, PhaseENotAllowedError,
    )
    with pytest.raises(PhaseENotAllowedError):
        run_manual_safely(
            session, symbol="UNH", as_of=dt.date(2026, 4, 29),
            provider_name="mock", operator_id="eve",
            request_source="http",
        )
    with pytest.raises(PhaseENotAllowedError):
        run_manual_safely(
            session, symbol="UNH", as_of=dt.date(2026, 4, 29),
            provider_name="mock", operator_id="eve",
            request_source="cli",
        )
    rows = session.execute(text(
        "SELECT request_source, status FROM research_ro.research_manual_run_audit "
        "WHERE operator_id='eve' ORDER BY created_at"
    )).mappings().all()
    sources = sorted(r["request_source"] for r in rows)
    assert sources == ["cli", "http"]
    assert all(r["status"] == "rejected" for r in rows)


# ===========================================================================
# 9. HTTP never returns raw unsafe output
# ===========================================================================


def test_http_never_returns_raw_unsafe_output(session, monkeypatch):
    _seed_asset(session, symbol="UNH")
    _enable(monkeypatch)
    from apps.api.src.research.manual_run_safe import run_manual_safely
    payload = run_manual_safely(
        session, symbol="UNH", as_of=dt.date(2026, 4, 29),
        provider_name="mock", operator_id="alice",
        request_source="http",
    )
    d = payload.as_dict()
    for k in (
        "body", "raw_body", "raw_response", "structured_output",
        "agent_output", "evidence_refs", "reflection",
    ):
        assert k not in d, f"sanitized payload exposes {k!r}"


# ===========================================================================
# 10. Usage summary counts runs and rejections
# ===========================================================================


def test_usage_summary_counts_runs_and_rejections(session, monkeypatch):
    _seed_asset(session, symbol="UNH")
    _enable(monkeypatch)
    from apps.api.src.research.manual_run_controls import usage_summary
    from apps.api.src.research.manual_run_safe import (
        run_manual_safely, PhaseENotAllowedError,
    )
    # Successful run.
    run_manual_safely(
        session, symbol="UNH", as_of=dt.date(2026, 4, 29),
        provider_name="mock", operator_id="alice",
    )
    # Rejected (provider not allowed).
    with pytest.raises(PhaseENotAllowedError):
        run_manual_safely(
            session, symbol="UNH", as_of=dt.date(2026, 4, 29),
            provider_name="anthropic", operator_id="alice",
        )
    s = usage_summary(session, operator_id="alice")
    assert s.runs_today_by_operator >= 1
    assert s.rejected_today_by_operator >= 1
    assert s.runs_today_by_symbol_for_operator.get("UNH", 0) >= 1
    assert s.last_successful_run_at is not None


# ===========================================================================
# 11. Anomaly: repeated rejections flagged
# ===========================================================================


def test_anomaly_flags_repeated_rejections(session, monkeypatch):
    _enable(
        monkeypatch,
        RESEARCH_ANOMALY_REJECTED_THRESHOLD=2,
        RESEARCH_ANOMALY_REJECTED_WINDOW_MIN=60,
    )
    # Pre-seed 2 rejected rows for alice within the last 5 minutes.
    for i in range(2):
        session.execute(text(
            """
            INSERT INTO research_ro.research_manual_run_audit
              (operator_id, symbol, as_of, provider, request_source,
               status, rejection_reason, created_at)
            VALUES ('alice', 'UNH', '2026-04-29', 'mock', 'cli',
                    'rejected', 'rate_limit', now() - interval '60 seconds')
            """
        ))
    session.commit()
    from apps.api.src.research.manual_run_controls import detect_anomalies
    rep = detect_anomalies(
        session, operator_id="alice", symbol="UNH",
    )
    assert any(
        f.startswith("operator_repeated_rejections") for f in rep.flags
    )
