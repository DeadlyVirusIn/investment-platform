"""BACKTEST-PAPER-6b — multi-day replay_range integration test.

A pre-seeded open position (low cost basis + a linked Recommendation) in the
replay portfolio guarantees a deterministic take-profit close on day T0,
independent of organic engine-Buy timing; organic opens across T0..T4 prove
the multi-day loop + reuse + idempotency.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from apps.api.src.backtest.replay_driver import replay_range
from apps.api.src.db.models import (
    Account,
    Asset,
    PaperPortfolio,
    PaperPosition,
    PriceBar,
    Recommendation,
    UniverseMembership,
)

pytestmark = pytest.mark.integration

UNI = "stock_swing_v1"
RUN = "r1"
NAME = f"replay:{RUN}"
T0 = dt.date(2026, 6, 1)
WINDOW = {
    T0 + dt.timedelta(days=1): Decimal("155"),   # T1 — fill bar
    T0 + dt.timedelta(days=2): Decimal("164"),   # T2
    T0 + dt.timedelta(days=3): Decimal("165"),   # T3
    T0 + dt.timedelta(days=4): Decimal("166"),   # T4
}
N_HIST = 210


def _bar(asset_id: str, d: dt.date, close: Decimal) -> PriceBar:
    return PriceBar(
        asset_id=asset_id, timeframe="1d",
        ts=dt.datetime(d.year, d.month, d.day, 14, 0, tzinfo=dt.timezone.utc),
        open=close, high=close + Decimal("0.5"), low=close - Decimal("0.5"),
        close=close, adjusted_close=close, volume=1_000_000, provider="bp6b",
    )


def _seed(pg_session: Session) -> tuple[str, str]:
    a = Asset(symbol="RNG1", asset_class="equity", exchange="TEST", currency="USD")
    pg_session.add(a)
    pg_session.flush()
    for i in range(N_HIST):
        d = T0 - dt.timedelta(days=N_HIST - 1 - i)
        pg_session.add(_bar(a.id, d, Decimal(str(50 + 0.5 * i))))
    for d, px in WINDOW.items():
        pg_session.add(_bar(a.id, d, px))
    pg_session.add(UniverseMembership(
        universe_name=UNI, asset_id=a.id,
        start_date=T0 - dt.timedelta(days=N_HIST), end_date=None,
    ))

    # Pre-create the replay account + portfolio (replay_range reuses by name).
    acct = Account(name=NAME, account_type="manual", currency="USD",
                   is_active=True)
    pf = PaperPortfolio(name=NAME, starting_cash=Decimal("100000"),
                        cash=Decimal("100000"), is_active=True)
    pg_session.add_all([acct, pf])
    pg_session.flush()

    # A linked recommendation + an open position with a low cost basis →
    # guaranteed take-profit on day T0 (mark ~154.5 vs basis 100).
    rec = Recommendation(
        asset_id=a.id, action="Buy", conviction=Decimal("60"),
        model_version="seed", snapshot_hash="seed1",
    )
    pg_session.add(rec)
    pg_session.flush()
    pg_session.add(PaperPosition(
        portfolio_id=pf.id, asset_id=a.id, quantity=Decimal("10"),
        avg_cost=Decimal("100"), is_open=True,
        opened_at=dt.datetime(2026, 5, 20, 14, 0, tzinfo=dt.timezone.utc),
        opened_by_recommendation_id=rec.id,
    ))
    pg_session.commit()
    return a.id, pf.id


def test_replay_range_multi_day(pg_session: Session) -> None:
    _seed(pg_session)
    T4 = T0 + dt.timedelta(days=4)

    res = replay_range(
        pg_session, start=T0, end=T4, run_label=RUN,
        take_profit_pct=Decimal("0.05"),
    )

    assert res.trading_days == 5
    assert res.days[0] == T0 and res.days[-1] == T4

    # one replay account + portfolio reused (the pre-seeded ones)
    assert pg_session.scalar(select(func.count()).select_from(Account).where(
        Account.name == NAME)) == 1
    assert pg_session.scalar(
        select(func.count()).select_from(PaperPortfolio).where(
            PaperPortfolio.name == NAME)) == 1

    assert res.recommendations >= res.trading_days
    assert res.buys >= 1
    assert res.trades_submitted >= 1
    assert res.exits_closed >= 1                      # pre-seeded TP fired

    closed = pg_session.execute(text(
        "SELECT realized_pnl, closed_by_trade_id FROM paper_position "
        "WHERE portfolio_id = :pf AND is_open = FALSE "
        "AND realized_pnl IS NOT NULL"
    ), {"pf": res.portfolio_id}).first()
    assert closed is not None
    assert closed.closed_by_trade_id is not None
    assert float(closed.realized_pnl) > 0             # TP from low basis

    assert res.closed_pairs                            # non-empty preview

    # Idempotency is at the RECOMMENDATION layer: persist dedups on
    # (asset, version, snapshot_hash), so a rerun creates NO new
    # recommendations. Trade/position state is intentionally NOT a no-op on
    # rerun — submit_trade merges same-asset buys (only the first buy's rec
    # is recorded as opened_by_recommendation_id) and exits change holdings
    # between runs. Replay runs meant to be repeatable should use a fresh
    # run_label (own portfolio); reruns into the same label accumulate.
    def _rec_count() -> int:
        return pg_session.scalar(
            select(func.count()).select_from(Recommendation).where(
                Recommendation.model_version == res.model_version)
        )

    recs_before = _rec_count()
    res2 = replay_range(
        pg_session, start=T0, end=T4, run_label=RUN,
        take_profit_pct=Decimal("0.05"),
    )
    assert res2.recommendations == res.recommendations   # same attempts
    assert _rec_count() == recs_before                   # no duplicate recs
