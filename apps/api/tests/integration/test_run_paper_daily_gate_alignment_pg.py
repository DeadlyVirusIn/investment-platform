"""Phase 11U.fix - integration test against Postgres.

Confirms the daily run reads the four production gate booleans from
`context_daily` (Phase 11P backfill source-of-truth) so its
`gates_favorable` count matches the macro backfill exactly.

Read-only against context_daily; never writes.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from scripts.run_paper_daily import (
    PRODUCTION_GATE_NAMES,
    _read_gates_from_context_daily,
)


pytestmark = pytest.mark.integration


@pytest.fixture
def session_factory(pg_engine):
    return sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )


@pytest.fixture(autouse=True)
def _ensure_context_daily(pg_engine):
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
                UNIQUE (as_of_date, context_name, logic_version)
            )
            """
        ))
    yield
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE TABLE context_daily RESTART IDENTITY CASCADE"
        ))


def _seed_gate(
    pg_session: Session, *, day: dt.date, name: str, value: bool,
) -> None:
    pg_session.execute(text(
        """
        INSERT INTO context_daily
          (as_of_date, context_name, status, value_bool,
           source_features, logic_version, logic_hash)
        VALUES
          (:d, :n, 'production', :v,
           ARRAY['test'], 'v1.0.0', 'test_hash')
        ON CONFLICT (as_of_date, context_name, logic_version)
          DO UPDATE SET value_bool = EXCLUDED.value_bool
        """
    ), {"d": day, "n": name, "v": value})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_returns_all_four_when_present_for_target_date(
    pg_session, session_factory,
):
    target = dt.date(2026, 4, 28)
    _seed_gate(pg_session, day=target, name="rates_calm", value=False)
    _seed_gate(pg_session, day=target, name="vrp_supportive", value=True)
    _seed_gate(pg_session, day=target, name="credit_stable", value=True)
    _seed_gate(pg_session, day=target,
               name="liquidity_expanding", value=False)
    pg_session.commit()
    out = _read_gates_from_context_daily(pg_session, target)
    assert out == {
        "rates_calm": False,
        "vrp_supportive": True,
        "credit_stable": True,
        "liquidity_expanding": False,
    }


def test_matches_macro_backfill_two_of_four_on_2026_04_28(
    pg_session, session_factory,
):
    """Mirrors the production state observed in the diagnosis: 4/27
    and 4/28 both at 2/4 (vrp + credit)."""
    target = dt.date(2026, 4, 28)
    _seed_gate(pg_session, day=target, name="rates_calm", value=False)
    _seed_gate(pg_session, day=target, name="vrp_supportive", value=True)
    _seed_gate(pg_session, day=target, name="credit_stable", value=True)
    _seed_gate(pg_session, day=target,
               name="liquidity_expanding", value=False)
    pg_session.commit()
    gates = _read_gates_from_context_daily(pg_session, target)
    assert gates is not None
    n_pass = sum(int(v) for v in gates.values())
    assert n_pass == 2


def test_falls_back_when_gate_row_missing_for_target_date(
    pg_session, session_factory,
):
    target = dt.date(2026, 4, 28)
    # Only 3 of 4 seeded
    _seed_gate(pg_session, day=target, name="rates_calm", value=False)
    _seed_gate(pg_session, day=target, name="vrp_supportive", value=True)
    _seed_gate(pg_session, day=target, name="credit_stable", value=True)
    pg_session.commit()
    out = _read_gates_from_context_daily(pg_session, target)
    assert out is None


def test_uses_latest_le_run_date_when_target_has_gap(
    pg_session, session_factory,
):
    """Weekend / holiday shape: target_date has no row but earlier
    business days do. Function must pick up the latest <= target."""
    earlier = dt.date(2026, 4, 24)        # Friday
    target = dt.date(2026, 4, 27)         # Monday — no row at this date
    for name, val in (
        ("rates_calm", True),
        ("vrp_supportive", False),
        ("credit_stable", True),
        ("liquidity_expanding", True),
    ):
        _seed_gate(pg_session, day=earlier, name=name, value=val)
    pg_session.commit()
    out = _read_gates_from_context_daily(pg_session, target)
    assert out == {
        "rates_calm": True,
        "vrp_supportive": False,
        "credit_stable": True,
        "liquidity_expanding": True,
    }


def test_does_not_use_future_rows(
    pg_session, session_factory,
):
    """A row dated AFTER target_date must not be returned."""
    target = dt.date(2026, 4, 24)
    later = dt.date(2026, 4, 28)
    for name, val in (
        ("rates_calm", True),
        ("vrp_supportive", True),
        ("credit_stable", True),
        ("liquidity_expanding", True),
    ):
        # Future-dated rows
        _seed_gate(pg_session, day=later, name=name, value=val)
    pg_session.commit()
    out = _read_gates_from_context_daily(pg_session, target)
    assert out is None


def test_picks_most_recent_when_multiple_le_target(
    pg_session, session_factory,
):
    target = dt.date(2026, 4, 28)
    older = dt.date(2026, 4, 21)
    newer = dt.date(2026, 4, 27)
    for name, val_old, val_new in (
        ("rates_calm",          True,  False),
        ("vrp_supportive",      False, True),
        ("credit_stable",       False, True),
        ("liquidity_expanding", True,  False),
    ):
        _seed_gate(pg_session, day=older, name=name, value=val_old)
        _seed_gate(pg_session, day=newer, name=name, value=val_new)
    pg_session.commit()
    out = _read_gates_from_context_daily(pg_session, target)
    # Must use values from the newer row only
    assert out == {
        "rates_calm": False,
        "vrp_supportive": True,
        "credit_stable": True,
        "liquidity_expanding": False,
    }


def test_lookup_does_not_write_to_context_daily(
    pg_session, session_factory,
):
    """Sanity: row count + checksum unchanged after a read."""
    target = dt.date(2026, 4, 28)
    for name, val in (
        ("rates_calm", False),
        ("vrp_supportive", True),
        ("credit_stable", True),
        ("liquidity_expanding", False),
    ):
        _seed_gate(pg_session, day=target, name=name, value=val)
    pg_session.commit()
    n_before = pg_session.execute(text(
        "SELECT COUNT(*) FROM context_daily"
    )).scalar_one()
    _read_gates_from_context_daily(pg_session, target)
    n_after = pg_session.execute(text(
        "SELECT COUNT(*) FROM context_daily"
    )).scalar_one()
    assert n_before == n_after


def test_lookup_handles_only_one_logic_version_per_name(
    pg_session, session_factory,
):
    """If a single name has multiple logic_versions on the same day,
    DISTINCT ON (context_name) must still return exactly one row per
    name — the most recent."""
    target = dt.date(2026, 4, 28)
    for name in PRODUCTION_GATE_NAMES:
        pg_session.execute(text(
            """
            INSERT INTO context_daily
              (as_of_date, context_name, status, value_bool,
               source_features, logic_version, logic_hash)
            VALUES (:d, :n, 'production', TRUE,
                    ARRAY['test'], 'v0.9.0', 'h0')
            """
        ), {"d": target, "n": name})
        pg_session.execute(text(
            """
            INSERT INTO context_daily
              (as_of_date, context_name, status, value_bool,
               source_features, logic_version, logic_hash)
            VALUES (:d, :n, 'production', FALSE,
                    ARRAY['test'], 'v1.0.0', 'h1')
            """
        ), {"d": target, "n": name})
    pg_session.commit()
    out = _read_gates_from_context_daily(pg_session, target)
    assert out is not None
    assert len(out) == 4
