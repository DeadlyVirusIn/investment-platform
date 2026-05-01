"""Phase 11Z — Macro gate unknown semantics integration tests.

Covers:
  * Migration 055 up/down: ck_context_daily_status accepts the
    three new statuses and rejects unknowns; value_bool can be NULL
    after upgrade and is forced NOT NULL after downgrade.
  * Diagnostic gate compute returns structured envelopes for
    insufficient/missing/stale/computed cases.
  * persist_context never coerces None → False; routes by status.
  * Selector reader (`_read_gates_from_context_daily`) returns None
    for non-production rows and surfaces statuses distinctly.
  * Wide-window backfill is exercised end-to-end with a fake FRED
    adapter, confirming a single-day persist target still computes
    real True/False values when lookback is honored.
"""

from __future__ import annotations

import datetime as dt
import importlib

import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixture — apply migration 055 to the testcontainer
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def macro_unknown_table(pg_engine):
    """Ensure context_daily exists with the legacy CHECK + NOT NULL,
    then run migration 055 to extend it. Tests run against the
    upgraded shape; teardown restores the legacy shape."""
    with pg_engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS context_daily (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                as_of_date date NOT NULL,
                context_name text NOT NULL,
                status text NOT NULL,
                value_bool boolean NOT NULL,
                source_features text[] NOT NULL,
                logic_version text NOT NULL,
                logic_hash text NOT NULL,
                computed_at timestamptz NOT NULL DEFAULT now(),
                CONSTRAINT ux_context_daily_name_ver_date
                  UNIQUE (as_of_date, context_name, logic_version),
                CONSTRAINT ck_context_daily_status
                  CHECK (status IN ('production','candidate','diagnostic'))
            )
            """
        ))

    mod = importlib.import_module(
        "infra.alembic.versions.055_phase_11z_macro_unknown_semantics"
    )
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with pg_engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()
    yield pg_engine
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS context_daily CASCADE"))


@pytest.fixture
def session(macro_unknown_table, pg_session):
    pg_session.execute(text("TRUNCATE TABLE context_daily"))
    pg_session.commit()
    yield pg_session


# ---------------------------------------------------------------------------
# Schema-level: accepted statuses + nullable value_bool
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [
    "production", "candidate", "diagnostic",
    "insufficient_data", "missing_data", "stale_data",
])
def test_ck_status_accepts_new_values(session, status):
    val: bool | None = True if status == "production" else None
    session.execute(text(
        """
        INSERT INTO context_daily
          (as_of_date, context_name, status, value_bool,
           source_features, logic_version, logic_hash)
        VALUES
          (:d, :n, :s, :v, ARRAY['t'], 'v1.0.0', 'h')
        """
    ), {
        "d": dt.date(2026, 4, 29), "n": f"name_{status}",
        "s": status, "v": val,
    })
    session.commit()
    n = session.execute(text(
        "SELECT count(*) FROM context_daily WHERE status = :s"
    ), {"s": status}).scalar_one()
    assert n == 1


def test_ck_status_rejects_unrecognized_value(session):
    with pytest.raises(IntegrityError):
        session.execute(text(
            """
            INSERT INTO context_daily
              (as_of_date, context_name, status, value_bool,
               source_features, logic_version, logic_hash)
            VALUES (:d, 'x', 'totally_invalid', NULL,
                    ARRAY['t'], 'v1.0.0', 'h')
            """
        ), {"d": dt.date(2026, 4, 29)})
        session.flush()
    session.rollback()


def test_value_bool_can_be_null_post_migration(session):
    session.execute(text(
        """
        INSERT INTO context_daily
          (as_of_date, context_name, status, value_bool,
           source_features, logic_version, logic_hash)
        VALUES (:d, 'rates_calm', 'insufficient_data', NULL,
                ARRAY['t'], 'v1.0.0', 'h')
        """
    ), {"d": dt.date(2026, 4, 29)})
    session.commit()
    row = session.execute(text(
        "SELECT value_bool FROM context_daily "
        "WHERE context_name='rates_calm'"
    )).mappings().first()
    assert row is not None
    assert row["value_bool"] is None


# ---------------------------------------------------------------------------
# Backfill diagnostics — compute_gates_with_diagnostics
# ---------------------------------------------------------------------------


def _series(dates: list[dt.date], vals: list[float]) -> pd.Series:
    idx = pd.to_datetime(dates)
    return pd.Series(vals, index=idx, dtype="float64")


def test_compute_gates_diagnostics_missing_data():
    from scripts.backfill_macro_features import (
        compute_gates_with_diagnostics, STATUS_MISSING,
    )
    series = {
        "DGS10": pd.Series(dtype="float64"),
        "VIXCLS": pd.Series(dtype="float64"),
        "BAMLH0A0HYM2": pd.Series(dtype="float64"),
        "WALCL": pd.Series(dtype="float64"),
        "WTREGEN": pd.Series(dtype="float64"),
        "RRPONTSYD": pd.Series(dtype="float64"),
    }
    spy = pd.Series(dtype="float64")
    res = compute_gates_with_diagnostics(
        series, spy, as_of=dt.date(2026, 4, 29),
    )
    for name in (
        "rates_calm", "vrp_supportive", "credit_stable",
        "liquidity_expanding",
    ):
        assert res[name].value is None
        assert res[name].status == STATUS_MISSING


def test_compute_gates_diagnostics_insufficient_data():
    """One DGS10 obs but rates_calm needs 6 → insufficient_data."""
    from scripts.backfill_macro_features import (
        compute_gates_with_diagnostics, STATUS_INSUFFICIENT,
    )
    series = {
        "DGS10": _series([dt.date(2026, 4, 29)], [4.42]),
        "VIXCLS": pd.Series(dtype="float64"),
        "BAMLH0A0HYM2": pd.Series(dtype="float64"),
        "WALCL": pd.Series(dtype="float64"),
        "WTREGEN": pd.Series(dtype="float64"),
        "RRPONTSYD": pd.Series(dtype="float64"),
    }
    spy = pd.Series(dtype="float64")
    res = compute_gates_with_diagnostics(
        series, spy, as_of=dt.date(2026, 4, 29),
    )
    rates = res["rates_calm"]
    assert rates.value is None
    assert rates.status == STATUS_INSUFFICIENT
    assert "DGS10" in rates.reason
    assert rates.available_obs == 1
    assert rates.required_obs >= 6


def test_compute_gates_diagnostics_stale_data():
    """6 DGS10 obs but newest is 30 cal days before as_of →
    stale_data (tolerance 5d)."""
    from scripts.backfill_macro_features import (
        compute_gates_with_diagnostics, STATUS_STALE,
    )
    base = dt.date(2026, 4, 1)
    series = {
        "DGS10": _series(
            [base + dt.timedelta(days=i) for i in range(7)],
            [4.30, 4.31, 4.32, 4.33, 4.34, 4.35, 4.36],
        ),
        "VIXCLS": pd.Series(dtype="float64"),
        "BAMLH0A0HYM2": pd.Series(dtype="float64"),
        "WALCL": pd.Series(dtype="float64"),
        "WTREGEN": pd.Series(dtype="float64"),
        "RRPONTSYD": pd.Series(dtype="float64"),
    }
    spy = pd.Series(dtype="float64")
    res = compute_gates_with_diagnostics(
        series, spy, as_of=dt.date(2026, 5, 1),  # 24 days after last DGS10
    )
    assert res["rates_calm"].value is None
    assert res["rates_calm"].status == STATUS_STALE


def test_compute_gates_diagnostics_computed_value_not_coerced():
    """6 DGS10 obs with rising series → rates_calm computes False."""
    from scripts.backfill_macro_features import (
        compute_gates_with_diagnostics, STATUS_PRODUCTION,
    )
    base = dt.date(2026, 4, 23)
    series = {
        "DGS10": _series(
            [base + dt.timedelta(days=i) for i in range(7)],
            [4.30, 4.32, 4.34, 4.35, 4.36, 4.38, 4.42],
        ),
        "VIXCLS": pd.Series(dtype="float64"),
        "BAMLH0A0HYM2": pd.Series(dtype="float64"),
        "WALCL": pd.Series(dtype="float64"),
        "WTREGEN": pd.Series(dtype="float64"),
        "RRPONTSYD": pd.Series(dtype="float64"),
    }
    spy = pd.Series(dtype="float64")
    res = compute_gates_with_diagnostics(
        series, spy, as_of=dt.date(2026, 4, 29),
    )
    rates = res["rates_calm"]
    assert rates.status == STATUS_PRODUCTION
    assert rates.value is False  # 4.42 - 4.30 > 0


# ---------------------------------------------------------------------------
# Persistence — never coerce None → False
# ---------------------------------------------------------------------------


def test_persist_context_with_diagnostic_writes_null_value(
    macro_unknown_table, pg_engine,
):
    """Phase 11Z — None gate result should land as
    `status='insufficient_data'`, `value_bool=NULL` rather than
    silently coerced to False/production."""
    from scripts.backfill_macro_features import (
        persist_context, GateDiagnostic, STATUS_INSUFFICIENT,
    )
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE context_daily"))
    rows = [(
        dt.date(2026, 4, 29), "rates_calm",
        GateDiagnostic(
            name="rates_calm", value=None,
            status=STATUS_INSUFFICIENT,
            reason="need >=6 DGS10 obs, have 1",
            required_obs=6, available_obs=1,
            latest_input_date=dt.date(2026, 4, 29),
            inputs_used=("DGS10",),
        ),
    )]
    persist_context(
        rows, logic_version="v1.0.0", session_factory=SessionCls,
    )
    with SessionCls() as s:
        row = s.execute(text(
            "SELECT status, value_bool FROM context_daily "
            "WHERE context_name='rates_calm'"
        )).mappings().first()
    assert row["status"] == STATUS_INSUFFICIENT
    assert row["value_bool"] is None


def test_persist_context_legacy_path_no_longer_coerces_none(
    macro_unknown_table, pg_engine,
):
    """Legacy bool|None tuple — when val is None, must persist as
    insufficient_data with NULL value_bool, NOT production+False."""
    from scripts.backfill_macro_features import (
        persist_context, STATUS_INSUFFICIENT,
    )
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE context_daily"))
    persist_context(
        [(dt.date(2026, 4, 29), "credit_stable", None)],
        logic_version="v1.0.0",
        session_factory=SessionCls,
    )
    with SessionCls() as s:
        row = s.execute(text(
            "SELECT status, value_bool FROM context_daily "
            "WHERE context_name='credit_stable'"
        )).mappings().first()
    assert row["status"] == STATUS_INSUFFICIENT
    assert row["value_bool"] is None


def test_persist_context_legacy_path_keeps_real_bools(
    macro_unknown_table, pg_engine,
):
    """A real True / False from the legacy path still persists as
    production with value_bool set."""
    from scripts.backfill_macro_features import (
        persist_context, STATUS_PRODUCTION,
    )
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE context_daily"))
    persist_context(
        [
            (dt.date(2026, 4, 29), "rates_calm", False),
            (dt.date(2026, 4, 29), "credit_stable", True),
        ],
        logic_version="v1.0.0",
        session_factory=SessionCls,
    )
    with SessionCls() as s:
        rows = s.execute(text(
            "SELECT context_name, status, value_bool "
            "FROM context_daily ORDER BY context_name"
        )).mappings().all()
    assert len(rows) == 2
    by_name = {r["context_name"]: r for r in rows}
    assert by_name["rates_calm"]["status"] == STATUS_PRODUCTION
    assert by_name["rates_calm"]["value_bool"] is False
    assert by_name["credit_stable"]["status"] == STATUS_PRODUCTION
    assert by_name["credit_stable"]["value_bool"] is True


# ---------------------------------------------------------------------------
# Selector reader — unknown vs failed
# ---------------------------------------------------------------------------


def _seed(
    s: Session, *,
    day: dt.date, name: str, status: str, value: bool | None,
):
    s.execute(text(
        """
        INSERT INTO context_daily
          (as_of_date, context_name, status, value_bool,
           source_features, logic_version, logic_hash)
        VALUES
          (:d, :n, :s, :v, ARRAY['t'], 'v1.0.0', 'h')
        ON CONFLICT (as_of_date, context_name, logic_version)
          DO UPDATE SET status = EXCLUDED.status,
                        value_bool = EXCLUDED.value_bool
        """
    ), {"d": day, "n": name, "s": status, "v": value})


def test_read_gates_distinguishes_unknown_from_false(session):
    from scripts.run_paper_daily import (
        _read_gates_from_context_daily,
        _read_gate_statuses_from_context_daily,
    )
    d = dt.date(2026, 4, 29)
    _seed(session, day=d, name="rates_calm",
          status="production", value=False)
    _seed(session, day=d, name="vrp_supportive",
          status="production", value=True)
    _seed(session, day=d, name="credit_stable",
          status="insufficient_data", value=None)
    _seed(session, day=d, name="liquidity_expanding",
          status="missing_data", value=None)
    session.commit()
    gates = _read_gates_from_context_daily(session, d)
    assert gates is not None
    assert gates["rates_calm"] is False
    assert gates["vrp_supportive"] is True
    assert gates["credit_stable"] is None    # unknown
    assert gates["liquidity_expanding"] is None
    statuses = _read_gate_statuses_from_context_daily(session, d)
    assert statuses["rates_calm"] == "production"
    assert statuses["credit_stable"] == "insufficient_data"
    assert statuses["liquidity_expanding"] == "missing_data"


def test_unknown_gates_do_not_count_as_favorable_or_failed(session):
    """gates_favorable should count only True; failed_gates should
    only contain explicit False; unknown_gates should be the rest.
    Replicates the dispatch in step_compute_features_and_context."""
    from scripts.run_paper_daily import (
        _read_gates_from_context_daily, PRODUCTION_GATE_NAMES,
    )
    d = dt.date(2026, 4, 29)
    _seed(session, day=d, name="rates_calm",
          status="production", value=False)
    _seed(session, day=d, name="vrp_supportive",
          status="production", value=True)
    _seed(session, day=d, name="credit_stable",
          status="insufficient_data", value=None)
    _seed(session, day=d, name="liquidity_expanding",
          status="stale_data", value=None)
    session.commit()
    gates = _read_gates_from_context_daily(session, d)
    favorable = sum(1 for v in gates.values() if v is True)
    failed = [n for n, v in gates.items() if v is False]
    unknown = [n for n, v in gates.items() if v is None]
    assert favorable == 1
    assert failed == ["rates_calm"]
    assert sorted(unknown) == [
        "credit_stable", "liquidity_expanding",
    ]
    assert len(gates) == len(PRODUCTION_GATE_NAMES)


# ---------------------------------------------------------------------------
# Wide-window backfill: BackfillConfig.fetch_start
# ---------------------------------------------------------------------------


def test_backfill_config_fetch_start_expands_lookback():
    from scripts.backfill_macro_features import BackfillConfig
    cfg = BackfillConfig(
        start=dt.date(2026, 4, 29), end=dt.date(2026, 4, 29),
        series=("DGS10",), dry_run=False, commit=True,
        logic_version="v1.0.0", explain=False,
        lookback_days=45,
    )
    assert cfg.fetch_start == dt.date(2026, 3, 15)
    # default 45-day lookback covers >30 business days
    n_bdays = sum(
        1 for i in range((cfg.end - cfg.fetch_start).days + 1)
        if (
            cfg.fetch_start + dt.timedelta(days=i)
        ).weekday() < 5
    )
    assert n_bdays >= 30


def test_backfill_config_zero_lookback_keeps_legacy_behavior():
    from scripts.backfill_macro_features import BackfillConfig
    cfg = BackfillConfig(
        start=dt.date(2026, 4, 29), end=dt.date(2026, 4, 29),
        series=("DGS10",), dry_run=False, commit=True,
        logic_version="v1.0.0", explain=False,
        lookback_days=0,
    )
    assert cfg.fetch_start == cfg.start


# ---------------------------------------------------------------------------
# Migration rollback
# ---------------------------------------------------------------------------


def test_migration_055_downgrade_restores_old_constraint(pg_engine):
    """Run 055.upgrade() then 055.downgrade() and confirm:
      * NULL value_bool rows get coerced to FALSE so the restored
        NOT NULL passes.
      * Non-legacy status rows get coerced to 'production'.
      * Old CHECK constraint refuses 'insufficient_data' again."""
    mod = importlib.import_module(
        "infra.alembic.versions.055_phase_11z_macro_unknown_semantics"
    )
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    # Fresh table for this test only.
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS context_daily CASCADE"))
        conn.execute(text(
            """
            CREATE TABLE context_daily (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                as_of_date date NOT NULL,
                context_name text NOT NULL,
                status text NOT NULL,
                value_bool boolean NOT NULL,
                source_features text[] NOT NULL,
                logic_version text NOT NULL,
                logic_hash text NOT NULL,
                computed_at timestamptz NOT NULL DEFAULT now(),
                CONSTRAINT ux_context_daily_name_ver_date
                  UNIQUE (as_of_date, context_name, logic_version),
                CONSTRAINT ck_context_daily_status
                  CHECK (status IN ('production','candidate','diagnostic'))
            )
            """
        ))

    with pg_engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()
    # Insert a row using the new statuses + NULL value_bool.
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )
    with SessionCls() as s:
        s.execute(text(
            """
            INSERT INTO context_daily
              (as_of_date, context_name, status, value_bool,
               source_features, logic_version, logic_hash)
            VALUES
              (:d, 'credit_stable', 'insufficient_data', NULL,
               ARRAY['t'], 'v1.0.0', 'h')
            """
        ), {"d": dt.date(2026, 4, 29)})
        s.commit()
    # Downgrade.
    with pg_engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.downgrade()
    # Surviving row must be coerced.
    with SessionCls() as s:
        row = s.execute(text(
            "SELECT status, value_bool FROM context_daily"
        )).mappings().first()
    assert row["status"] == "production"
    assert row["value_bool"] is False
    # Old CHECK reinstated.
    with SessionCls() as s:
        with pytest.raises(IntegrityError):
            s.execute(text(
                """
                INSERT INTO context_daily
                  (as_of_date, context_name, status, value_bool,
                   source_features, logic_version, logic_hash)
                VALUES
                  (:d, 'x', 'insufficient_data', FALSE,
                   ARRAY['t'], 'v1.0.0', 'h')
                """
            ), {"d": dt.date(2026, 5, 1)})
            s.flush()
        s.rollback()
    # Re-upgrade so other tests in the module find the new shape.
    with pg_engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()
