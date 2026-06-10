"""P6D.35A → P6D.35C — paper_equity_snapshot read determinism.

HISTORY: 35A pinned reader tie-breaking (ORDER BY snapshot_date DESC,
recorded_at DESC, id DESC) while the table could legally hold duplicate
(portfolio_id, snapshot_date, source) rows — the unique key included
recorded_at, and live data had 47 duplicate groups, 31 with CONFLICTING
equity (e.g. the real 2026-06-07 conflict: 146,155 vs 121,907).

P6D.35C (migration 094) archived + deleted the non-keepers (keeper = the
exact row the 35A readers already selected) and narrowed the unique key to
(portfolio_id, snapshot_date, source); the writer is now an UPSERT. The
duplicate row shape this suite originally exercised is therefore
structurally IMPOSSIBLE — adaptation:

  * the old fixture's duplicate pair (same date/source, different
    recorded_at) now raises IntegrityError — pinned below as the NEW
    structural guarantee that replaces reader tie-breaking;
  * canonical nav/daily_pnl determinism is re-pinned over single rows
    (the only legal state). The readers keep their recorded_at/id DESC
    tiebreakers as defense-in-depth, but they can no longer choose
    between competing rows.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.exc import IntegrityError

from apps.api.src.api.paper_canonical import canonical_stock
from apps.api.src.config import settings
from apps.api.src.db.models import PaperEquitySnapshot, PaperPortfolio

pytestmark = pytest.mark.integration

D_PRIOR = dt.datetime(2026, 6, 5, tzinfo=dt.timezone.utc)
D_LATEST = dt.datetime(2026, 6, 7, tzinfo=dt.timezone.utc)
REC = dt.datetime(2026, 6, 8, 23, 31, 3, tzinfo=dt.timezone.utc)


def _snap(pid, date, equity, recorded_at):
    return PaperEquitySnapshot(
        portfolio_id=pid, snapshot_date=date, source="live",
        total_equity=equity, cash=100, positions_value=equity - 100,
        unrealized_pnl=0, realized_pnl_cumulative=0, recorded_at=recorded_at,
    )


@pytest.fixture
def snap_portfolio(pg_session, monkeypatch):
    """Canonical portfolio with ONE live row per snapshot_date (the only
    state the post-094 schema permits)."""
    p = PaperPortfolio(
        name="snapshot-determinism-test", starting_cash=100000, cash=100000,
    )
    pg_session.add(p)
    pg_session.flush()
    monkeypatch.setattr(settings, "CANONICAL_STOCK_PORTFOLIO_ID", str(p.id))
    pg_session.add(_snap(p.id, D_PRIOR, 122073, REC - dt.timedelta(days=2)))
    latest = _snap(p.id, D_LATEST, 121907, REC)
    pg_session.add(latest)
    pg_session.commit()
    return p, latest


def test_duplicate_date_source_row_is_structurally_impossible(
    pg_session, snap_portfolio
):
    """The exact shape 35A had to tie-break (same portfolio/date/source,
    DIFFERENT recorded_at, conflicting equity) is now an IntegrityError on
    uq_paper_equity_snapshot — uniqueness moved from the reader into the
    schema."""
    p, _ = snap_portfolio
    pg_session.add(
        _snap(p.id, D_LATEST, 146155, REC - dt.timedelta(microseconds=1))
    )
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


def test_canonical_reads_single_row_per_date(pg_session, snap_portfolio):
    _, latest = snap_portfolio
    out = canonical_stock(db=pg_session)
    assert out["status"] == "live"
    assert out["nav"] == float(latest.total_equity)
    assert out["source_snapshot_id"] == str(latest.id)


def test_canonical_daily_pnl_deterministic_across_calls(
    pg_session, snap_portfolio
):
    _, latest = snap_portfolio
    results = {
        (canonical_stock(db=pg_session)["nav"],
         canonical_stock(db=pg_session)["daily_pnl"])
        for _ in range(5)
    }
    assert len(results) == 1                              # identical every call
    nav, daily = results.pop()
    assert nav == float(latest.total_equity)
    assert daily == float(latest.total_equity) - 122073.0  # prior-day basis
