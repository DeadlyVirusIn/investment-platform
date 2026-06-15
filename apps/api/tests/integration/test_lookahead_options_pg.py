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
