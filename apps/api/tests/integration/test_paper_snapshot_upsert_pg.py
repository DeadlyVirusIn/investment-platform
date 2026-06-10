"""P6D.35C — paper_equity_snapshot writer UPSERT semantics.

After migration 094 the unique key is (portfolio_id, snapshot_date, source)
and `snapshot_equity_now` is a PostgreSQL INSERT ... ON CONFLICT DO UPDATE:
  * a second same-day same-source call updates the SAME row in place —
    value columns and recorded_at take the latest write, id/created_at are
    preserved (last writer wins);
  * different snapshot_date or different source → separate rows (cells are
    isolated; replay can never rewrite live history);
  * a raw duplicate INSERT on (portfolio_id, snapshot_date, source) raises
    IntegrityError — the structural uniqueness pin.
"""

from __future__ import annotations

import datetime as dt
import time
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.src.db.models import PaperEquitySnapshot
from apps.api.src.domain.paper_trading.paper_service import (
    PortfolioCreate,
    create_portfolio,
    snapshot_equity_now,
)

pytestmark = pytest.mark.integration

AS_OF = dt.datetime(2026, 6, 1, 14, 30, tzinfo=dt.timezone.utc)


def _row_count(session: Session, portfolio_id: str) -> int:
    return session.scalar(
        select(func.count())
        .select_from(PaperEquitySnapshot)
        .where(PaperEquitySnapshot.portfolio_id == portfolio_id)
    )


def test_same_day_second_call_updates_in_place(pg_session: Session) -> None:
    p = create_portfolio(
        pg_session, PortfolioCreate(name="upsert-same-day",
                                    starting_cash=Decimal("1000"))
    )
    pg_session.commit()

    s1 = snapshot_equity_now(pg_session, p, as_of=AS_OF, source="live")
    pg_session.commit()
    first_id, first_created = s1.id, s1.created_at
    first_recorded = s1.recorded_at
    assert Decimal(str(s1.total_equity)) == Decimal("1000")

    # Change equity between calls so "second values win" is observable.
    p.cash = Decimal("900")
    pg_session.commit()
    time.sleep(0.01)  # guarantee a strictly later recorded_at

    s2 = snapshot_equity_now(
        pg_session, p, as_of=AS_OF + dt.timedelta(hours=3), source="live"
    )
    pg_session.commit()

    assert s2.id == first_id                       # same row, updated in place
    assert _row_count(pg_session, p.id) == 1       # ONE row per (pid,date,src)
    assert Decimal(str(s2.total_equity)) == Decimal("900")   # second wins
    assert Decimal(str(s2.cash)) == Decimal("900")
    assert s2.recorded_at > first_recorded         # write timestamp advanced
    assert s2.created_at == first_created          # creation time preserved


def test_different_snapshot_date_creates_separate_rows(
    pg_session: Session,
) -> None:
    p = create_portfolio(
        pg_session, PortfolioCreate(name="upsert-diff-date")
    )
    pg_session.commit()
    s1 = snapshot_equity_now(pg_session, p, as_of=AS_OF, source="live")
    pg_session.commit()
    s2 = snapshot_equity_now(
        pg_session, p, as_of=AS_OF + dt.timedelta(days=1), source="live"
    )
    pg_session.commit()
    assert s1.id != s2.id
    assert _row_count(pg_session, p.id) == 2


def test_different_source_creates_separate_rows(pg_session: Session) -> None:
    p = create_portfolio(
        pg_session, PortfolioCreate(name="upsert-diff-source")
    )
    pg_session.commit()
    s_live = snapshot_equity_now(pg_session, p, as_of=AS_OF, source="live")
    pg_session.commit()
    s_replay = snapshot_equity_now(
        pg_session, p, as_of=AS_OF, source="replay"
    )
    pg_session.commit()
    assert s_live.id != s_replay.id                # replay never touches live
    assert _row_count(pg_session, p.id) == 2


def test_raw_duplicate_insert_raises_integrity_error(
    pg_session: Session,
) -> None:
    """Structural pin: (portfolio_id, snapshot_date, source) is UNIQUE even
    when recorded_at differs — the exact row shape that was legal pre-094."""
    p = create_portfolio(pg_session, PortfolioCreate(name="upsert-pin"))
    pg_session.commit()
    d = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    rec = dt.datetime(2026, 6, 1, 23, 30, tzinfo=dt.timezone.utc)

    def _snap(equity: int, recorded_at: dt.datetime) -> PaperEquitySnapshot:
        return PaperEquitySnapshot(
            portfolio_id=p.id, snapshot_date=d, source="live",
            total_equity=equity, cash=100, positions_value=equity - 100,
            unrealized_pnl=0, realized_pnl_cumulative=0,
            recorded_at=recorded_at,
        )

    pg_session.add(_snap(1000, rec))
    pg_session.commit()

    pg_session.add(_snap(2000, rec + dt.timedelta(minutes=5)))
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()
