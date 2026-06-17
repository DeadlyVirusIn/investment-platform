"""BP9b — replay produces decision-level 1:1 recommendation->position outcomes.

With merge_positions=False wired into replay, each Buy opens its own
PaperPosition (own opened_by_recommendation_id), so closed positions map 1:1
to recommendations. As a bonus the same-run_label rerun is now trade-
idempotent (the opened_by skip-check matches every rec, not just the first).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.src.backtest.replay_driver import replay_range
from apps.api.src.db.models import Asset, PaperPosition, PriceBar, UniverseMembership

pytestmark = pytest.mark.integration

UNI = "stock_swing_v1"
RUN = "nm1"
T0 = dt.date(2026, 6, 1)
WINDOW = {
    T0 + dt.timedelta(days=1): Decimal("155"),
    T0 + dt.timedelta(days=2): Decimal("164"),
    T0 + dt.timedelta(days=3): Decimal("165"),
    T0 + dt.timedelta(days=4): Decimal("166"),
}
N_HIST = 215


def _bar(asset_id: str, d: dt.date, close: Decimal) -> PriceBar:
    return PriceBar(
        asset_id=asset_id, timeframe="1d",
        ts=dt.datetime(d.year, d.month, d.day, 14, 0, tzinfo=dt.timezone.utc),
        open=close, high=close + Decimal("0.5"), low=close - Decimal("0.5"),
        close=close, adjusted_close=close, volume=1_000_000, provider="bp9b",
    )


def _seed(pg_session: Session) -> None:
    a = Asset(symbol="RNG1", asset_class="equity", exchange="TEST", currency="USD")
    pg_session.add(a)
    pg_session.flush()
    for i in range(N_HIST):  # uptrend ending T0 -> Buys
        d = T0 - dt.timedelta(days=N_HIST - 1 - i)
        pg_session.add(_bar(a.id, d, Decimal(str(50 + 0.5 * i))))
    for d, px in WINDOW.items():
        pg_session.add(_bar(a.id, d, px))
    pg_session.add(UniverseMembership(
        universe_name=UNI, asset_id=a.id,
        start_date=T0 - dt.timedelta(days=N_HIST), end_date=None))
    pg_session.commit()


def _positions(pg_session: Session, pf_id: str) -> list[PaperPosition]:
    return list(pg_session.scalars(select(PaperPosition).where(
        PaperPosition.portfolio_id == pf_id)))


def test_replay_no_merge_one_position_per_recommendation(
    pg_session: Session,
) -> None:
    _seed(pg_session)
    T4 = T0 + dt.timedelta(days=4)
    res = replay_range(pg_session, start=T0, end=T4, run_label=RUN,
                       take_profit_pct=Decimal("0.05"))

    positions = _positions(pg_session, res.portfolio_id)
    assert len(positions) >= 2                       # same asset, multiple days
    # every position attributed to a recommendation, all DISTINCT (1:1)
    rec_ids = [p.opened_by_recommendation_id for p in positions]
    assert all(rid is not None for rid in rec_ids)
    assert len(rec_ids) == len(set(rec_ids))         # no merge -> 1:1

    # closed positions also 1:1
    closed = [p for p in positions if not p.is_open]
    closed_recs = [p.opened_by_recommendation_id for p in closed]
    assert len(closed_recs) == len(set(closed_recs))


def test_no_merge_rerun_is_trade_idempotent(pg_session: Session) -> None:
    _seed(pg_session)
    T4 = T0 + dt.timedelta(days=4)
    res = replay_range(pg_session, start=T0, end=T4, run_label=RUN,
                       take_profit_pct=Decimal("0.05"))
    assert res.trades_submitted >= 1

    n_before = pg_session.scalar(select(func.count()).select_from(
        PaperPosition).where(PaperPosition.portfolio_id == res.portfolio_id))

    res2 = replay_range(pg_session, start=T0, end=T4, run_label=RUN,
                        take_profit_pct=Decimal("0.05"))
    # 1:1 attribution makes the opened_by skip-check exact -> no new buys
    assert res2.trades_submitted == 0
    assert res2.trades_skipped_existing >= 1
    n_after = pg_session.scalar(select(func.count()).select_from(
        PaperPosition).where(PaperPosition.portfolio_id == res.portfolio_id))
    assert n_after == n_before                        # no duplicate positions
