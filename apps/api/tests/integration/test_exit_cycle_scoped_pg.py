"""BACKTEST-PAPER-6a — portfolio-scoped run_exit_cycle callable.

Proves the extracted callable:
  * portfolio_id=<target> closes ONLY that portfolio's eligible positions.
  * portfolio_id=None (default) scans every portfolio (legacy behaviour).
  * closes stamp realized_pnl + closed_by_trade_id (MP1S exit attribution).
  * no CONFIRM_ENV required (operator gate is CLI-only).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, PaperPortfolio, PaperPosition, PriceBar
from scripts.run_paper_exit_cycle import run_exit_cycle

pytestmark = pytest.mark.integration

TODAY = dt.date.today()


def _seed_portfolio_with_tp_position(
    pg_session: Session, *, name: str, symbol: str,
    entry: float = 100.0, latest: float = 120.0, held_days: int = 2,
) -> tuple[str, str]:
    a = Asset(symbol=symbol, asset_class="equity", currency="USD")
    p = PaperPortfolio(
        name=name, starting_cash=Decimal("10000"),
        cash=Decimal("9000"), is_active=True,
    )
    pg_session.add_all([a, p])
    pg_session.flush()
    pg_session.add(PaperPosition(
        portfolio_id=p.id, asset_id=a.id, quantity=Decimal("10"),
        avg_cost=Decimal(str(entry)), is_open=True,
        opened_at=dt.datetime.now(dt.timezone.utc).replace(
            hour=15, minute=0, second=0, microsecond=0,
        ) - dt.timedelta(days=held_days),
    ))
    # mark bar (today) + next-bar fill (tomorrow)
    for d, t in ((TODAY, 13), (TODAY + dt.timedelta(days=1), 13)):
        pg_session.add(PriceBar(
            asset_id=a.id, timeframe="1d",
            ts=dt.datetime.combine(d, dt.time(t, 0), tzinfo=dt.timezone.utc),
            open=latest, high=latest, low=latest, close=latest,
            adjusted_close=latest, provider="bp6a",
        ))
    pg_session.flush()
    return p.id, a.id


def _is_open(pg_session: Session, asset_id: str) -> bool:
    pg_session.expire_all()
    return pg_session.execute(text(
        "SELECT is_open FROM paper_position WHERE asset_id = :a"
    ), {"a": asset_id}).scalar()


def test_run_exit_cycle_scoped_to_one_portfolio(pg_session: Session) -> None:
    tgt_pf, tgt_asset = _seed_portfolio_with_tp_position(
        pg_session, name="replay:tgt", symbol="TGT")
    other_pf, other_asset = _seed_portfolio_with_tp_position(
        pg_session, name="replay:other", symbol="OTH")
    pg_session.commit()

    # scope to the target portfolio only
    res = run_exit_cycle(
        pg_session, as_of=TODAY, portfolio_id=tgt_pf,
        take_profit_pct=Decimal("0.05"), commit=True,
    )

    assert res.scanned == 1                 # only the target's position seen
    assert len(res.closed) == 1
    assert _is_open(pg_session, tgt_asset) is False     # target closed
    assert _is_open(pg_session, other_asset) is True    # other untouched

    # closed position carries MP1S exit attribution
    row = pg_session.execute(text(
        "SELECT is_open, realized_pnl, closed_by_trade_id "
        "FROM paper_position WHERE asset_id = :a"
    ), {"a": tgt_asset}).first()
    assert row.is_open is False
    assert row.realized_pnl is not None and float(row.realized_pnl) > 0
    assert row.closed_by_trade_id is not None


def test_run_exit_cycle_default_scans_all_portfolios(pg_session: Session) -> None:
    pf_a, asset_a = _seed_portfolio_with_tp_position(
        pg_session, name="replay:a", symbol="AAA")
    pf_b, asset_b = _seed_portfolio_with_tp_position(
        pg_session, name="replay:b", symbol="BBB")
    pg_session.commit()

    res = run_exit_cycle(
        pg_session, as_of=TODAY, portfolio_id=None,
        take_profit_pct=Decimal("0.05"), commit=True,
    )

    assert res.scanned >= 2
    assert _is_open(pg_session, asset_a) is False
    assert _is_open(pg_session, asset_b) is False


def test_run_exit_cycle_never_touches_user_books(pg_session: Session) -> None:
    """P1 incident 2026-07-08: engine exit rules (TP/SL/max-hold) must never
    force-sell positions inside a per-user practice book (``user:<id>:stock``)."""
    user_pf, user_asset = _seed_portfolio_with_tp_position(
        pg_session, name="user:exit-guard-user:stock", symbol="USR")
    engine_pf, engine_asset = _seed_portfolio_with_tp_position(
        pg_session, name="replay:engine-guard", symbol="ENG")
    pg_session.commit()

    res = run_exit_cycle(
        pg_session, as_of=TODAY, portfolio_id=None,
        take_profit_pct=Decimal("0.05"), commit=True,
    )

    assert _is_open(pg_session, engine_asset) is False   # engine book exits fire
    assert _is_open(pg_session, user_asset) is True      # user book untouched
    assert all(c.get("portfolio_id") != user_pf for c in res.closed)
