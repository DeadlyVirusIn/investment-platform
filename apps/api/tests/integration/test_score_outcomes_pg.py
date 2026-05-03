"""Integration tests: score_recommendation_outcomes job end-to-end."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    PriceBar,
    Recommendation,
    RecommendationEvidence,
    RecommendationOutcome,
)
from apps.worker.src.jobs.score_outcomes import score_recommendation_outcomes

pytestmark = pytest.mark.integration


def _seed_asset_with_prices(
    pg_session: Session,
    symbol: str,
    entry_ts: dt.datetime,
    pre_bars: int = 30,
    post_bars: int = 90,
    pre_trend: Decimal = Decimal("0.2"),
    post_trend: Decimal = Decimal("0.5"),
    noise_amp: Decimal = Decimal("0.5"),
) -> tuple[str, Decimal]:
    """Seed a series of price bars around `entry_ts`.

    Returns (asset_id, entry_price).
    """
    asset = Asset(symbol=symbol, asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()

    base = Decimal("100")
    # Pre-entry: mild upward drift with oscillation so sigma > 0
    for i in range(pre_bars):
        ts = entry_ts - dt.timedelta(days=pre_bars - i)
        drift = pre_trend * Decimal(i)
        noise = noise_amp if i % 2 == 0 else -noise_amp
        price = base + drift + noise
        pg_session.add(PriceBar(
            asset_id=asset.id, timeframe="1d", ts=ts,
            open=price, high=price + Decimal("0.5"), low=price - Decimal("0.5"),
            close=price, adjusted_close=price, volume=1_000_000, provider="test",
        ))

    entry_price = base + pre_trend * Decimal(pre_bars)
    # Entry bar exactly at entry_ts
    pg_session.add(PriceBar(
        asset_id=asset.id, timeframe="1d", ts=entry_ts,
        open=entry_price, high=entry_price + Decimal("0.5"),
        low=entry_price - Decimal("0.5"), close=entry_price,
        adjusted_close=entry_price, volume=1_000_000, provider="test",
    ))

    # Post-entry: steady uptrend pushes above profit barrier
    for i in range(1, post_bars + 1):
        ts = entry_ts + dt.timedelta(days=i)
        price = entry_price + post_trend * Decimal(i)
        pg_session.add(PriceBar(
            asset_id=asset.id, timeframe="1d", ts=ts,
            open=price, high=price + Decimal("0.5"), low=price - Decimal("0.5"),
            close=price, adjusted_close=price, volume=1_000_000, provider="test",
        ))

    pg_session.commit()
    return asset.id, entry_price


def _create_rec_with_outcome(
    pg_session: Session,
    asset_id: str,
    generated_at: dt.datetime,
    price_at: Decimal,
    snapshot: str = "snap-A",
) -> str:
    rec = Recommendation(
        asset_id=asset_id, action="Buy", model_version="0.1.0",
        snapshot_hash=snapshot, rationale='{"snapshot_hash":"' + snapshot + '"}',
        conviction=Decimal("70"), generated_at=generated_at,
    )
    pg_session.add(rec)
    pg_session.flush()
    pg_session.add(RecommendationOutcome(
        recommendation_id=rec.id,
        price_at_recommendation=price_at,
    ))
    pg_session.commit()
    return rec.id


async def test_job_labels_uptrend_as_profit(pg_session: Session) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    entry = now - dt.timedelta(days=60)
    asset_id, entry_price = _seed_asset_with_prices(
        pg_session, symbol="LBL1",
        entry_ts=entry,
        post_trend=Decimal("0.8"),  # strong uptrend; triggers profit barrier quickly
    )
    rec_id = _create_rec_with_outcome(pg_session, asset_id, entry, entry_price)

    await score_recommendation_outcomes()

    pg_session.expire_all()
    outcome = pg_session.scalar(
        select(RecommendationOutcome).where(
            RecommendationOutcome.recommendation_id == rec_id
        )
    )
    assert outcome is not None
    assert outcome.barrier_label == 1
    assert outcome.barrier_first_touch_at is not None
    assert outcome.realized_30d_return is not None
    assert outcome.price_after_30d is not None


async def test_job_labels_downtrend_as_stop(pg_session: Session) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    entry = now - dt.timedelta(days=60)
    asset_id, entry_price = _seed_asset_with_prices(
        pg_session, symbol="LBL2",
        entry_ts=entry,
        post_trend=Decimal("-0.8"),  # strong downtrend; triggers stop-loss
    )
    rec_id = _create_rec_with_outcome(pg_session, asset_id, entry, entry_price)

    await score_recommendation_outcomes()

    pg_session.expire_all()
    outcome = pg_session.scalar(
        select(RecommendationOutcome).where(
            RecommendationOutcome.recommendation_id == rec_id
        )
    )
    assert outcome.barrier_label == -1


async def test_job_skips_recent_recommendations(pg_session: Session) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    # Entry too recent (5 days ago) — below MIN_AGE_DAYS=30
    entry = now - dt.timedelta(days=5)
    asset_id, entry_price = _seed_asset_with_prices(
        pg_session, symbol="SKIP", entry_ts=entry, post_bars=10,
    )
    rec_id = _create_rec_with_outcome(pg_session, asset_id, entry, entry_price)

    await score_recommendation_outcomes()

    pg_session.expire_all()
    outcome = pg_session.scalar(
        select(RecommendationOutcome).where(
            RecommendationOutcome.recommendation_id == rec_id
        )
    )
    assert outcome.barrier_label is None  # still unlabeled


async def test_job_idempotent_skips_already_labeled(pg_session: Session) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    entry = now - dt.timedelta(days=60)
    asset_id, entry_price = _seed_asset_with_prices(
        pg_session, symbol="IDEM", entry_ts=entry,
    )
    rec_id = _create_rec_with_outcome(pg_session, asset_id, entry, entry_price)

    await score_recommendation_outcomes()
    pg_session.expire_all()
    first = pg_session.scalar(
        select(RecommendationOutcome).where(
            RecommendationOutcome.recommendation_id == rec_id
        )
    )
    first_touch = first.barrier_first_touch_at
    first_label = first.barrier_label

    # Re-run: existing label stays (WHERE barrier_label IS NULL excludes it)
    await score_recommendation_outcomes()
    pg_session.expire_all()
    second = pg_session.scalar(
        select(RecommendationOutcome).where(
            RecommendationOutcome.recommendation_id == rec_id
        )
    )
    assert second.barrier_label == first_label
    assert second.barrier_first_touch_at == first_touch


def _add_evidence(pg_session: Session, rec_id: str, factor_keys: list[str]) -> None:
    for k in factor_keys:
        pg_session.add(RecommendationEvidence(
            recommendation_id=rec_id, evidence_type=k, source="test", summary="{}",
        ))
    pg_session.commit()


async def test_job_stores_barrier_n_bars_for_trend_signal(pg_session: Session) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    entry = now - dt.timedelta(days=80)
    asset_id, entry_price = _seed_asset_with_prices(
        pg_session, symbol="TRND", entry_ts=entry, post_bars=70,
        post_trend=Decimal("0.8"),
    )
    rec_id = _create_rec_with_outcome(pg_session, asset_id, entry, entry_price, snapshot="t1")
    _add_evidence(pg_session, rec_id, ["trend_strength", "price_vs_sma_long"])

    await score_recommendation_outcomes()

    pg_session.expire_all()
    outcome = pg_session.scalar(
        select(RecommendationOutcome).where(
            RecommendationOutcome.recommendation_id == rec_id
        )
    )
    assert outcome.barrier_n_bars == 63
    assert outcome.barrier_label in (-1, 0, 1)


async def test_job_stores_barrier_n_bars_for_mean_reversion_signal(pg_session: Session) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    entry = now - dt.timedelta(days=40)
    asset_id, entry_price = _seed_asset_with_prices(
        pg_session, symbol="MRV", entry_ts=entry, post_bars=25,
        post_trend=Decimal("0.6"),
    )
    rec_id = _create_rec_with_outcome(pg_session, asset_id, entry, entry_price, snapshot="m1")
    _add_evidence(pg_session, rec_id, ["rsi_14"])

    await score_recommendation_outcomes()

    pg_session.expire_all()
    outcome = pg_session.scalar(
        select(RecommendationOutcome).where(
            RecommendationOutcome.recommendation_id == rec_id
        )
    )
    assert outcome.barrier_n_bars == 10


async def test_job_stores_barrier_n_bars_default_without_evidence(
    pg_session: Session,
) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    entry = now - dt.timedelta(days=60)
    asset_id, entry_price = _seed_asset_with_prices(
        pg_session, symbol="DEF", entry_ts=entry, post_bars=40,
    )
    rec_id = _create_rec_with_outcome(pg_session, asset_id, entry, entry_price, snapshot="d1")
    # No evidence rows → default horizon

    await score_recommendation_outcomes()

    pg_session.expire_all()
    outcome = pg_session.scalar(
        select(RecommendationOutcome).where(
            RecommendationOutcome.recommendation_id == rec_id
        )
    )
    assert outcome.barrier_n_bars == 30


async def test_job_handles_missing_price_data(pg_session: Session) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    entry = now - dt.timedelta(days=60)
    # Seed asset but NO price bars
    asset = Asset(symbol="NOPX", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()
    rec_id = _create_rec_with_outcome(pg_session, asset.id, entry, Decimal("100"))

    await score_recommendation_outcomes()

    pg_session.expire_all()
    outcome = pg_session.scalar(
        select(RecommendationOutcome).where(
            RecommendationOutcome.recommendation_id == rec_id
        )
    )
    # No data → still unlabeled, no crash
    assert outcome.barrier_label is None
