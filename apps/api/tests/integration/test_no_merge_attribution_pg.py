"""BP9a — submit_trade no-merge seam + targeted SELL by position_id.

Proves decision-level 1:1 attribution: merge_positions=False opens a new
position per Buy (each with its own opened_by_recommendation_id), and a SELL
with position_id closes exactly that lot. Default (merge_positions=True,
position_id=None) is byte-identical legacy behaviour.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    PaperPosition,
    PriceBar,
    Recommendation,
)
from apps.api.src.domain.paper_trading.paper_execution import (
    PaperTradeRejected,
    submit_trade,
)
from apps.api.src.domain.paper_trading.paper_service import (
    PortfolioCreate,
    create_portfolio,
)

pytestmark = pytest.mark.integration

BUY_AT = dt.datetime(2026, 5, 1, 0, 0, tzinfo=dt.timezone.utc)
SELL_AT = dt.datetime(2026, 5, 1, 15, 0, tzinfo=dt.timezone.utc)


def _bar(asset_id: str, d: dt.datetime, px: str) -> PriceBar:
    p = Decimal(px)
    return PriceBar(asset_id=asset_id, timeframe="1d", ts=d, open=p, high=p,
                    low=p, close=p, adjusted_close=p, volume=1_000_000,
                    provider="bp9a")


def _setup(pg_session: Session, symbol: str = "NM1") -> tuple[str, str, str, str]:
    a = Asset(symbol=symbol, asset_class="equity", exchange="TEST", currency="USD")
    pg_session.add(a)
    pg_session.flush()
    # fill bars: buy fills at 5/1 14:00; sell fills at 5/2 14:00.
    pg_session.add(_bar(a.id, dt.datetime(2026, 5, 1, 14, 0, tzinfo=dt.timezone.utc), "100"))
    pg_session.add(_bar(a.id, dt.datetime(2026, 5, 2, 14, 0, tzinfo=dt.timezone.utc), "110"))
    pf = create_portfolio(pg_session, PortfolioCreate(
        name=f"nm-{symbol}", starting_cash=Decimal("1000000"),
        max_open_positions=100))
    r1 = Recommendation(asset_id=a.id, action="Buy", conviction=Decimal("60"),
                        model_version="v", snapshot_hash="s1")
    r2 = Recommendation(asset_id=a.id, action="Buy", conviction=Decimal("66.7"),
                        model_version="v", snapshot_hash="s2")
    pg_session.add_all([r1, r2])
    pg_session.flush()
    return a.id, pf.id, r1.id, r2.id


def _open_positions(pg_session: Session, portfolio_id: str) -> list[PaperPosition]:
    return list(pg_session.scalars(select(PaperPosition).where(
        PaperPosition.portfolio_id == portfolio_id,
        PaperPosition.is_open.is_(True))))


def test_default_merges_same_asset(pg_session: Session) -> None:
    aid, pid, r1, r2 = _setup(pg_session)
    submit_trade(pg_session, portfolio_id=pid, asset_id=aid, side="buy",
                 quantity=Decimal("10"), submitted_at=BUY_AT, recommendation_id=r1)
    submit_trade(pg_session, portfolio_id=pid, asset_id=aid, side="buy",
                 quantity=Decimal("5"), submitted_at=BUY_AT, recommendation_id=r2)
    pg_session.flush()
    pos = _open_positions(pg_session, pid)
    assert len(pos) == 1                          # merged
    assert pos[0].quantity == Decimal("15")       # qty summed
    assert pos[0].opened_by_recommendation_id == r1   # first rec retained


def test_no_merge_opens_separate_positions(pg_session: Session) -> None:
    aid, pid, r1, r2 = _setup(pg_session)
    submit_trade(pg_session, portfolio_id=pid, asset_id=aid, side="buy",
                 quantity=Decimal("10"), submitted_at=BUY_AT, recommendation_id=r1,
                 merge_positions=False)
    submit_trade(pg_session, portfolio_id=pid, asset_id=aid, side="buy",
                 quantity=Decimal("5"), submitted_at=BUY_AT, recommendation_id=r2,
                 merge_positions=False)
    pg_session.flush()
    pos = _open_positions(pg_session, pid)
    assert len(pos) == 2                          # one per Buy
    assert {p.opened_by_recommendation_id for p in pos} == {r1, r2}   # 1:1


def test_targeted_sell_closes_only_that_lot(pg_session: Session) -> None:
    aid, pid, r1, r2 = _setup(pg_session)
    submit_trade(pg_session, portfolio_id=pid, asset_id=aid, side="buy",
                 quantity=Decimal("10"), submitted_at=BUY_AT, recommendation_id=r1,
                 merge_positions=False)
    submit_trade(pg_session, portfolio_id=pid, asset_id=aid, side="buy",
                 quantity=Decimal("5"), submitted_at=BUY_AT, recommendation_id=r2,
                 merge_positions=False)
    pg_session.flush()
    by_rec = {p.opened_by_recommendation_id: p for p in _open_positions(pg_session, pid)}
    target = by_rec[r1]

    submit_trade(pg_session, portfolio_id=pid, asset_id=aid, side="sell",
                 quantity=Decimal("10"), submitted_at=SELL_AT, position_id=target.id)
    pg_session.flush()
    pg_session.expire_all()

    closed = pg_session.get(PaperPosition, target.id)
    other = pg_session.get(PaperPosition, by_rec[r2].id)
    assert closed.is_open is False and closed.realized_pnl is not None
    assert closed.closed_by_trade_id is not None
    assert other.is_open is True                  # the other lot untouched


def test_invalid_position_id_raises(pg_session: Session) -> None:
    aid, pid, r1, r2 = _setup(pg_session)
    submit_trade(pg_session, portfolio_id=pid, asset_id=aid, side="buy",
                 quantity=Decimal("10"), submitted_at=BUY_AT, recommendation_id=r1,
                 merge_positions=False)
    pg_session.flush()

    # non-existent position
    with pytest.raises(PaperTradeRejected):
        submit_trade(pg_session, portfolio_id=pid, asset_id=aid, side="sell",
                     quantity=Decimal("1"), submitted_at=SELL_AT,
                     position_id="does-not-exist")

    # foreign asset/portfolio position
    aid2, pid2, r3, _ = _setup(pg_session, symbol="NM2")
    submit_trade(pg_session, portfolio_id=pid2, asset_id=aid2, side="buy",
                 quantity=Decimal("10"), submitted_at=BUY_AT, recommendation_id=r3,
                 merge_positions=False)
    pg_session.flush()
    foreign = _open_positions(pg_session, pid2)[0]
    with pytest.raises(PaperTradeRejected):
        submit_trade(pg_session, portfolio_id=pid, asset_id=aid, side="sell",
                     quantity=Decimal("1"), submitted_at=SELL_AT,
                     position_id=foreign.id)
