"""BACKTEST-PAPER-5 — single-day replay driver integration test."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.src.backtest.replay_driver import replay_one_day
from apps.api.src.db.models import (
    Asset,
    PaperPosition,
    Recommendation,
    RecommendationOutcome,
    UniverseMembership,
)
from apps.api.src.domain.recommendations.recommendation_engine import (
    load_engine_config,
)

pytestmark = pytest.mark.integration

UNI = "stock_swing_v1"
T = dt.date(2026, 6, 15)
N = 215
T_CLOSE = Decimal(str(50 + 0.5 * (N - 1)))   # last in-window bar close (157.0)
FUTURE_CLOSE = Decimal("999")


def _bar(asset_id: str, d: dt.date, close: Decimal):
    from apps.api.src.db.models import PriceBar
    return PriceBar(
        asset_id=asset_id, timeframe="1d",
        ts=dt.datetime(d.year, d.month, d.day, 14, 0, tzinfo=dt.timezone.utc),
        open=close, high=close + Decimal("0.5"), low=close - Decimal("0.5"),
        close=close, adjusted_close=close, volume=1_000_000, provider="bp5",
    )


def _seed(pg_session: Session) -> str:
    a = Asset(symbol="RPLY1", asset_class="equity", exchange="TEST", currency="USD")
    pg_session.add(a)
    pg_session.flush()
    # Strong steady uptrend ending at T (bias engine toward Buy).
    for i in range(N):
        d = T - dt.timedelta(days=N - 1 - i)
        price = Decimal(str(50 + 0.5 * i))
        pg_session.add(_bar(a.id, d, price))
    # Fill bar (T+1) + a future bar (T+5) that must be excluded from the T decision.
    pg_session.add(_bar(a.id, T + dt.timedelta(days=1), Decimal("200")))
    pg_session.add(_bar(a.id, T + dt.timedelta(days=5), FUTURE_CLOSE))
    pg_session.add(UniverseMembership(
        universe_name=UNI, asset_id=a.id,
        start_date=T - dt.timedelta(days=N), end_date=None,
    ))
    pg_session.commit()
    return a.id


def _pos_count(pg_session: Session, portfolio_id: str) -> int:
    return pg_session.scalar(
        select(func.count()).select_from(PaperPosition).where(
            PaperPosition.portfolio_id == portfolio_id)
    )


def test_replay_one_day_end_to_end(pg_session: Session) -> None:
    asset_id = _seed(pg_session)
    version = f"{load_engine_config().version}+replay:t1"

    res = replay_one_day(pg_session, as_of=T, run_label="t1")
    pg_session.flush()

    assert res.assets_evaluated >= 1
    assert res.recommendations == res.assets_evaluated
    assert res.model_version == version

    rec = pg_session.scalars(
        select(Recommendation).where(
            Recommendation.asset_id == asset_id,
            Recommendation.model_version == version,
        )
    ).first()
    assert rec is not None
    gen = rec.generated_at
    if gen.tzinfo is None:
        gen = gen.replace(tzinfo=dt.timezone.utc)
    assert gen == dt.datetime(T.year, T.month, T.day, tzinfo=dt.timezone.utc)
    assert rec.model_version.endswith("+replay:t1")

    # decision used T close, NOT the T+5 future bar
    outcome = pg_session.scalars(
        select(RecommendationOutcome).where(
            RecommendationOutcome.recommendation_id == rec.id)
    ).first()
    assert outcome is not None
    assert outcome.price_at_recommendation == T_CLOSE
    assert outcome.price_at_recommendation != FUTURE_CLOSE

    # trade path: at least one Buy exercised, fill at next bar (T+1)
    assert res.buys >= 1
    assert res.trades_submitted == res.buys
    assert res.trades_skipped_existing == 0

    pos = pg_session.scalars(
        select(PaperPosition).where(
            PaperPosition.portfolio_id == res.portfolio_id,
            PaperPosition.opened_by_recommendation_id == rec.id,
        )
    ).first()
    assert pos is not None
    opened = pos.opened_at
    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=dt.timezone.utc)
    assert opened.date() == T + dt.timedelta(days=1)   # next-bar fill

    pos_count_1 = _pos_count(pg_session, res.portfolio_id)

    # rerun is idempotent: no new recs/positions, all buys skipped
    res2 = replay_one_day(pg_session, as_of=T, run_label="t1")
    pg_session.flush()
    assert res2.recommendations == res.recommendations
    assert res2.trades_submitted == 0
    assert res2.trades_skipped_existing == res.buys
    assert _pos_count(pg_session, res.portfolio_id) == pos_count_1
