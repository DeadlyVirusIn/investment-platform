"""Integration: confidence × regime matrix + insights exposed via API."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, Recommendation, RecommendationOutcome

pytestmark = pytest.mark.integration


def _seed_outcome(
    pg_session, asset, offset_days, r30, r90, label, conviction, trend, vol, dd, snap,
):
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    rec = Recommendation(
        asset_id=asset.id, action="Buy", model_version="0.1.0",
        snapshot_hash=snap, rationale='{"snapshot_hash":"' + snap + '"}',
        conviction=conviction, generated_at=now - dt.timedelta(days=offset_days),
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


def test_api_exposes_matrix_and_insights(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    asset = Asset(symbol="MX", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()

    # Build a scenario: 5 high-conf uptrend wins; 5 high-conf downtrend losses;
    # 5 low-conf mixed.
    base_offset = 100
    snap_i = 0

    def _snap() -> str:
        nonlocal snap_i
        snap_i += 1
        return f"m{snap_i}"

    for i in range(5):
        _seed_outcome(
            pg_session, asset, base_offset - i, Decimal("0.08"), Decimal("0.12"),
            1, Decimal("75"), "uptrend", "low", "none", _snap(),
        )
    for i in range(5):
        _seed_outcome(
            pg_session, asset, base_offset - 10 - i, Decimal("-0.06"), Decimal("-0.08"),
            -1, Decimal("75"), "downtrend", "high", "severe", _snap(),
        )
    for i in range(5):
        label = 1 if i % 2 == 0 else -1
        r = Decimal("0.03") if label == 1 else Decimal("-0.02")
        _seed_outcome(
            pg_session, asset, base_offset - 20 - i, r, r,
            label, Decimal("20"), "sideways", "medium", "mild", _snap(),
        )

    client = TestClient(app)
    resp = client.get("/api/performance?window=30d")
    assert resp.status_code == 200
    data = resp.json()
    t2 = data["recommendation_metrics"]["tier_2_conditional"]

    assert "confidence_regime_matrix" in t2
    matrix = t2["confidence_regime_matrix"]
    # All three dimensions present
    assert set(matrix.keys()) == {"trend", "volatility", "drawdown"}
    # 16 rows per dimension
    assert len(matrix["trend"]) == 16

    # Check specific cross-tab cell: High × uptrend → 5 wins
    high_up = next(
        r for r in matrix["trend"]
        if r["confidence_bucket"] == "High (60-100)" and r["regime"] == "uptrend"
    )
    assert high_up["count"] == 5
    assert Decimal(high_up["hit_rate"]) == Decimal("1")

    # High × downtrend → 5 losses → hit_rate 0
    high_down = next(
        r for r in matrix["trend"]
        if r["confidence_bucket"] == "High (60-100)" and r["regime"] == "downtrend"
    )
    assert high_down["count"] == 5
    assert Decimal(high_down["hit_rate"]) == Decimal("0")

    # Insights present
    assert "insights" in t2
    insights = t2["insights"]
    assert "confidence_inversion" in insights
    assert "regime_sensitivity" in insights
    assert "low_sample_warnings" in insights

    # Regime sensitivity should fire: uptrend hit=1.0 vs downtrend hit=0.0 → spread=1.0
    rs = insights["regime_sensitivity"]
    trend_sens = [s for s in rs if s["dimension"] == "trend"]
    assert len(trend_sens) == 1
    assert trend_sens[0]["best_regime"] == "uptrend"
    assert trend_sens[0]["worst_regime"] == "downtrend"
    assert Decimal(trend_sens[0]["spread"]) == Decimal("1")

    # Low bucket has 5 samples, not a warning. Nothing here should create
    # < 5 conf bucket warnings since each populated bucket has exactly 5.
    conf_warnings = [w for w in insights["low_sample_warnings"]
                     if w["dimension"] == "confidence"]
    assert conf_warnings == []
