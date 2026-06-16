"""QW1.2 + QW1-FIX.A — options chain-selection lookahead detector + fix proof.

Mirrors the chain-quote subquery in
options/strategy_candidates/service.py (~line 300-308):

    SELECT ... FROM options_chain_snapshot
     WHERE option_symbol = s.option_symbol
       AND (snapshot_at_utc AT TIME ZONE 'UTC')::date <= s.run_date   -- QW1-FIX.A
     ORDER BY snapshot_at_utc DESC LIMIT 1

Without the bound (old behaviour) a past run_date selects a snapshot stamped
AFTER the decision date -> lookahead. With the bound the on-or-before
snapshot is chosen.

Two tests:
  * unbounded regression guard — proves the OLD query would still leak (the
    bound is load-bearing).
  * bounded invariant — QW1-FIX.A: selected snapshot <= run_date.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db.options_models import OptionsChainSnapshot
from apps.api.src.analytics.lookahead import max_input_ts_le_decision
# QW1-FIX.B — exercise the real bounded strike-ladder selector.
from apps.api.src.options.strategy_candidates.legs import _fetch_ladder

pytestmark = pytest.mark.integration

RUN_DATE = dt.date(2026, 6, 15)
BEFORE = dt.datetime(2026, 6, 14, 14, 0, tzinfo=dt.timezone.utc)   # <= run_date
AFTER = dt.datetime(2026, 6, 16, 14, 0, tzinfo=dt.timezone.utc)    # AFTER run_date

_NAT = dict(
    underlying="SPY", expiry=dt.date(2026, 7, 18),
    strike=Decimal("440"), option_type="PUT",
    option_symbol="SPY260718P00440000",
)


def _seed(pg_session: Session, snap_at: dt.datetime) -> None:
    pg_session.add(OptionsChainSnapshot(
        snapshot_at_utc=snap_at, mid=Decimal("1.20"),
        quote_age_seconds=2, provider="qw1-test", **_NAT,
    ))


def _selected_snapshot_at(pg_session: Session, *, bounded: bool) -> dt.datetime:
    """Run the generator's chain selection. `bounded=True` mirrors QW1-FIX.A
    (snapshot_at_utc::date <= run_date); `bounded=False` is the old unbounded
    DESC LIMIT 1 that leaked."""
    clause = (
        "AND (snapshot_at_utc AT TIME ZONE 'UTC')::date <= :rd" if bounded else ""
    )
    return pg_session.execute(text(
        f"""
        SELECT snapshot_at_utc
          FROM options_chain_snapshot
         WHERE underlying = 'SPY' AND expiry = DATE '2026-07-18'
           AND strike = 440 AND option_type = 'PUT'
           {clause}
         ORDER BY snapshot_at_utc DESC
         LIMIT 1
        """
    ), {"rd": RUN_DATE}).scalar()


def test_unbounded_selection_would_leak(pg_session: Session) -> None:
    """Regression guard: the OLD unbounded DESC LIMIT 1 picks the
    post-run_date snapshot. Proves the QW1-FIX.A bound is load-bearing."""
    _seed(pg_session, BEFORE)
    _seed(pg_session, AFTER)
    pg_session.commit()
    sel = _selected_snapshot_at(pg_session, bounded=False)
    assert sel.date() == dt.date(2026, 6, 16)  # future snapshot chosen -> leak
    run_decision = dt.datetime(2026, 6, 15, 23, 59, 59, tzinfo=dt.timezone.utc)
    assert max_input_ts_le_decision(run_decision, [sel])["ok"] is False


def test_chain_selection_respects_decision_boundary(pg_session: Session) -> None:
    """QW1-FIX.A: with the snapshot_at_utc::date <= run_date bound, the
    selected snapshot is the on-or-before one, never the future snapshot."""
    _seed(pg_session, BEFORE)
    _seed(pg_session, AFTER)
    pg_session.commit()
    sel = _selected_snapshot_at(pg_session, bounded=True)
    assert sel.date() <= RUN_DATE
    assert sel.date() == dt.date(2026, 6, 14)  # the pre-run_date snapshot
    run_decision = dt.datetime(2026, 6, 15, 23, 59, 59, tzinfo=dt.timezone.utc)
    assert max_input_ts_le_decision(run_decision, [sel])["ok"] is True


# --- QW1-FIX.B: strike-ladder (_fetch_ladder) lookahead ---

def _seed_ladder(pg_session: Session, snap_at: dt.datetime, strikes) -> None:
    for k in strikes:
        pg_session.add(OptionsChainSnapshot(
            snapshot_at_utc=snap_at, underlying="SPY",
            expiry=dt.date(2026, 7, 18), strike=Decimal(str(k)),
            option_type="PUT",
            option_symbol=f"SPY260718P{int(k * 1000):08d}",
            bid=Decimal("0.95"), ask=Decimal("1.05"), mid=Decimal("1.00"),
            delta=Decimal("-0.30"), quote_age_seconds=2, provider="qw1b-test",
        ))


def test_strike_ladder_bounded_by_run_date(pg_session: Session) -> None:
    """QW1-FIX.B: _fetch_ladder(as_of=run_date) returns the on-or-before
    ladder, never the post-run_date one."""
    _seed_ladder(pg_session, BEFORE, [435, 440])
    _seed_ladder(pg_session, AFTER, [435, 440])
    pg_session.commit()
    ladder = _fetch_ladder(
        pg_session, "SPY", dt.date(2026, 7, 18), "PUT", as_of=RUN_DATE,
    )
    assert ladder  # non-empty
    for row in ladder:
        assert row.priced_as_of.date() <= RUN_DATE
        assert row.priced_as_of.date() == dt.date(2026, 6, 14)  # before ladder


def test_unbounded_ladder_would_leak(pg_session: Session) -> None:
    """Regression guard: the OLD unbounded MAX(snapshot_at_utc) picks the
    post-run_date ladder. Proves the QW1-FIX.B bound is load-bearing."""
    _seed_ladder(pg_session, BEFORE, [435, 440])
    _seed_ladder(pg_session, AFTER, [435, 440])
    pg_session.commit()
    sel = pg_session.execute(text(
        """
        SELECT MAX(snapshot_at_utc) FROM options_chain_snapshot
         WHERE underlying = 'SPY' AND expiry = DATE '2026-07-18'
           AND option_type = 'PUT'
        """
    )).scalar()
    assert sel.date() == dt.date(2026, 6, 16)  # unbounded MAX -> future -> leak
