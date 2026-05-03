"""Integration: regime features populated + exposed via /api/performance."""

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
    RecommendationOutcome,
)
from apps.worker.src.jobs.score_outcomes import score_recommendation_outcomes

pytestmark = pytest.mark.integration


def _seed_asset_with_series(
    pg_session: Session,
    symbol: str,
    entry_ts: dt.datetime,
    pre_bars: int = 60,
    post_bars: int = 90,
    pre_step: Decimal = Decimal("0.5"),   # pre-entry trend direction
    post_step: Decimal = Decimal("0.8"),
    noise_amp: Decimal = Decimal("0.5"),
) -> tuple[str, Decimal]:
    asset = Asset(symbol=symbol, asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()

    base = Decimal("100")
    for i in range(pre_bars):
        ts = entry_ts - dt.timedelta(days=pre_bars - i)
        drift = pre_step * Decimal(i)
        noise = noise_amp if i % 2 == 0 else -noise_amp
        price = base + drift + noise
        pg_session.add(PriceBar(
            asset_id=asset.id, timeframe="1d", ts=ts,
            open=price, high=price + Decimal("0.5"), low=price - Decimal("0.5"),
            close=price, adjusted_close=price, volume=1_000_000, provider="test",
        ))
    entry_price = base + pre_step * Decimal(pre_bars)
    pg_session.add(PriceBar(
        asset_id=asset.id, timeframe="1d", ts=entry_ts,
        open=entry_price, high=entry_price + Decimal("0.5"),
        low=entry_price - Decimal("0.5"), close=entry_price,
        adjusted_close=entry_price, volume=1_000_000, provider="test",
    ))
    for i in range(1, post_bars + 1):
        price = entry_price + post_step * Decimal(i)
        pg_session.add(PriceBar(
            asset_id=asset.id, timeframe="1d",
            ts=entry_ts + dt.timedelta(days=i),
            open=price, high=price + Decimal("0.5"), low=price - Decimal("0.5"),
            close=price, adjusted_close=price, volume=1_000_000, provider="test",
        ))
    pg_session.commit()
    return asset.id, entry_price


def _seed_rec_with_outcome(
    pg_session: Session, asset_id: str, entry_ts: dt.datetime,
    price_at: Decimal, snap: str,
) -> str:
    rec = Recommendation(
        asset_id=asset_id, action="Buy", model_version="0.1.0",
        snapshot_hash=snap, rationale='{"snapshot_hash":"' + snap + '"}',
        conviction=Decimal("60"), generated_at=entry_ts,
    )
    pg_session.add(rec)
    pg_session.flush()
    pg_session.add(RecommendationOutcome(
        recommendation_id=rec.id, price_at_recommendation=price_at,
    ))
    pg_session.commit()
    return rec.id


async def test_score_outcomes_populates_regime_fields(pg_session: Session) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    entry = now - dt.timedelta(days=60)
    asset_id, entry_price = _seed_asset_with_series(pg_session, "RGM", entry)
    rec_id = _seed_rec_with_outcome(pg_session, asset_id, entry, entry_price, "r1")

    await score_recommendation_outcomes()

    pg_session.expire_all()
    outcome = pg_session.scalar(
        select(RecommendationOutcome).where(
            RecommendationOutcome.recommendation_id == rec_id
        )
    )
    assert outcome is not None
    assert outcome.trend_regime in ("uptrend", "downtrend", "sideways")
    assert outcome.volatility_regime in ("low", "medium", "high")
    assert outcome.drawdown_regime in ("none", "mild", "severe")
    # Pre-entry was a drifting-up sawtooth → expect uptrend or sideways
    assert outcome.trend_regime in ("uptrend", "sideways")


def test_performance_api_includes_regime_breakdowns(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    asset = Asset(symbol="RGB", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    scenarios = [
        # (days_offset, r30, r90, label, conviction, trend, vol, dd, snap)
        (100, Decimal("0.10"), Decimal("0.20"), 1, Decimal("70"), "uptrend", "low", "none", "s1"),
        (95, Decimal("-0.05"), Decimal("-0.02"), -1, Decimal("50"), "downtrend", "high", "severe", "s2"),
        (90, Decimal("0.03"), Decimal("0.05"), 1, Decimal("40"), "uptrend", "medium", "mild", "s3"),
        (85, Decimal("0.02"), Decimal("0.04"), 1, Decimal("35"), "sideways", "low", "none", "s4"),
    ]
    for offset, r30, r90, label, conv, trend, vol, dd, snap in scenarios:
        rec = Recommendation(
            asset_id=asset.id, action="Buy", model_version="0.1.0",
            snapshot_hash=snap, rationale='{"snapshot_hash":"' + snap + '"}',
            conviction=conv, generated_at=now - dt.timedelta(days=offset),
        )
        pg_session.add(rec)
        pg_session.flush()
        pg_session.add(RecommendationOutcome(
            recommendation_id=rec.id,
            price_at_recommendation=Decimal("100"),
            realized_30d_return=r30, realized_90d_return=r90,
            barrier_label=label,
            trend_regime=trend, volatility_regime=vol, drawdown_regime=dd,
        ))
    pg_session.commit()

    client = TestClient(app)
    resp = client.get("/api/performance?window=30d")
    assert resp.status_code == 200
    data = resp.json()
    t2 = data["recommendation_metrics"]["tier_2_conditional"]

    assert "by_trend_regime" in t2
    assert "by_volatility_regime" in t2
    assert "by_drawdown_regime" in t2

    # Trend buckets always emit all three + unknown
    trend_regimes = [b["regime"] for b in t2["by_trend_regime"]]
    assert trend_regimes == ["uptrend", "downtrend", "sideways", "unknown"]

    by_trend = {b["regime"]: b for b in t2["by_trend_regime"]}
    # 2 uptrend wins (labels 1, 1) → hit_rate 1.0
    assert by_trend["uptrend"]["count"] == 2
    assert Decimal(by_trend["uptrend"]["hit_rate"]) == Decimal("1")
    # downtrend: 1 loss → hit_rate 0
    assert by_trend["downtrend"]["count"] == 1
    assert Decimal(by_trend["downtrend"]["hit_rate"]) == Decimal("0")

    by_vol = {b["regime"]: b for b in t2["by_volatility_regime"]}
    assert by_vol["low"]["count"] == 2
    assert by_vol["high"]["count"] == 1

    by_dd = {b["regime"]: b for b in t2["by_drawdown_regime"]}
    assert by_dd["none"]["count"] == 2
    assert by_dd["severe"]["count"] == 1

    # Outcomes payload exposes regime fields
    oc0 = data["outcomes"][0]
    assert "trend_regime" in oc0
    assert "volatility_regime" in oc0
    assert "drawdown_regime" in oc0
