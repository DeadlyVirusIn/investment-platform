"""QW1.2 — options chain-selection lookahead detector (integration).

Mirrors the chain-quote subquery in
options/strategy_candidates/service.py (~line 300-303):

    SELECT ... FROM options_chain_snapshot
     WHERE <natural key minus snapshot_at>
     ORDER BY snapshot_at_utc DESC LIMIT 1

That ordering picks the LATEST snapshot with NO `snapshot_at_utc <= run_date`
bound. For a past run_date (replay/backtest) it selects a snapshot stamped
AFTER the decision date -> lookahead bias.

Two tests:
  * one documents the CURRENT (leaky) behaviour: future snapshot is selected.
  * one asserts the DESIRED invariant (selected <= run_date) and is marked
    xfail(strict) — it fails today (leak), and will XPASS (forcing removal of
    the marker) once QW1-FIX bounds the query.

Detector only — no query fix here.
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


def _selected_snapshot_at(pg_session: Session) -> dt.datetime:
    """Run the exact DESC LIMIT 1 selection the generator uses (unbounded)."""
    return pg_session.execute(text(
        """
        SELECT snapshot_at_utc
          FROM options_chain_snapshot
         WHERE underlying = 'SPY' AND expiry = DATE '2026-07-18'
           AND strike = 440 AND option_type = 'PUT'
         ORDER BY snapshot_at_utc DESC
         LIMIT 1
        """
    )).scalar()


def test_current_behavior_selects_future_snapshot(pg_session: Session) -> None:
    """Documents the leak: DESC LIMIT 1 picks the post-run_date snapshot.
    Green = leak reproduced."""
    _seed(pg_session, BEFORE)
    _seed(pg_session, AFTER)
    pg_session.commit()
    sel = _selected_snapshot_at(pg_session)
    assert sel.date() == dt.date(2026, 6, 16)  # future snapshot chosen -> leak
    # invariant helper agrees this is a lookahead violation
    run_decision = dt.datetime(2026, 6, 15, 23, 59, 59, tzinfo=dt.timezone.utc)
    res = max_input_ts_le_decision(run_decision, [sel])
    assert res["ok"] is False


@pytest.mark.xfail(
    strict=True,
    reason="QW1 lookahead: chain selection uses ORDER BY snapshot_at_utc DESC "
           "LIMIT 1 with no snapshot_at_utc<=run_date bound; future snapshot "
           "is selected. Remove this marker once QW1-FIX bounds the query.",
)
def test_chain_selection_respects_decision_boundary(pg_session: Session) -> None:
    """DESIRED invariant: the selected snapshot must not be after run_date.
    Fails today (leak); XPASS after QW1-FIX -> strict xfail flags removal."""
    _seed(pg_session, BEFORE)
    _seed(pg_session, AFTER)
    pg_session.commit()
    sel = _selected_snapshot_at(pg_session)
    assert sel.date() <= RUN_DATE
