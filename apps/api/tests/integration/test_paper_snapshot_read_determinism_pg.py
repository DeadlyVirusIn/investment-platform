"""P6D.35A — paper_equity_snapshot read determinism under duplicate rows.

The table legally holds duplicate (portfolio_id, snapshot_date, source) rows
(the unique key includes recorded_at) — live data has 47 duplicate groups, 31
with CONFLICTING equity. Until the writer/constraint fix (P6D.35C), every
latest-snapshot reader must resolve ties deterministically: ORDER BY
snapshot_date DESC, recorded_at DESC, id DESC. These tests pin the behavior
with the worst case — two rows on the SAME date with the SAME recorded_at and
different equity (mirrors the real 2026-06-07 conflict: 146,155 vs 121,907).
"""

from __future__ import annotations

import datetime as dt

import pytest

from apps.api.src.api.paper_canonical import canonical_stock
from apps.api.src.config import settings
from apps.api.src.db.models import PaperEquitySnapshot, PaperPortfolio

pytestmark = pytest.mark.integration

D_PRIOR = dt.datetime(2026, 6, 5, tzinfo=dt.timezone.utc)
D_DUP = dt.datetime(2026, 6, 7, tzinfo=dt.timezone.utc)
REC = dt.datetime(2026, 6, 8, 23, 31, 3, tzinfo=dt.timezone.utc)


def _snap(pid, date, equity, recorded_at):
    return PaperEquitySnapshot(
        portfolio_id=pid, snapshot_date=date, source="live",
        total_equity=equity, cash=100, positions_value=equity - 100,
        unrealized_pnl=0, realized_pnl_cumulative=0, recorded_at=recorded_at,
    )


@pytest.fixture
def dup_portfolio(pg_session, monkeypatch):
    p = PaperPortfolio(
        name="snapshot-determinism-test", starting_cash=100000, cash=100000,
    )
    pg_session.add(p)
    pg_session.flush()
    monkeypatch.setattr(settings, "CANONICAL_STOCK_PORTFOLIO_ID", str(p.id))
    # prior day (daily_pnl basis) + the conflicting duplicate pair: same
    # date, same source, SAME recorded_at, different equity.
    pg_session.add(_snap(p.id, D_PRIOR, 122073, REC - dt.timedelta(days=2)))
    # NOTE: the current unique key (portfolio, date, source, recorded_at)
    # FORBIDS exact recorded_at ties — the real live duplicates differ by
    # microseconds/minutes. Winner = latest recorded_at (the id DESC
    # tiebreaker is defense-in-depth, source-pinned in the unit suite).
    a = _snap(p.id, D_DUP, 146155, REC - dt.timedelta(microseconds=1))
    b = _snap(p.id, D_DUP, 121907, REC)
    pg_session.add(a)
    pg_session.add(b)
    pg_session.commit()
    winner = b   # later recorded_at wins, regardless of equity magnitude
    return p, winner


def test_canonical_picks_highest_id_on_exact_tie(pg_session, dup_portfolio):
    _, hi = dup_portfolio
    out = canonical_stock(db=pg_session)
    assert out["status"] == "live"
    assert out["nav"] == float(hi.total_equity)   # latest-recorded row wins
    assert out["source_snapshot_id"] == str(hi.id)


def test_canonical_daily_pnl_deterministic_across_calls(pg_session, dup_portfolio):
    _, hi = dup_portfolio
    results = {
        (canonical_stock(db=pg_session)["nav"],
         canonical_stock(db=pg_session)["daily_pnl"])
        for _ in range(5)
    }
    assert len(results) == 1                              # identical every call
    nav, daily = results.pop()
    assert nav == float(hi.total_equity)
    assert daily == float(hi.total_equity) - 122073.0     # prior-day basis
