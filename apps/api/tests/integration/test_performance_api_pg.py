"""Integration: /api/performance returns correct metrics end-to-end."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    Recommendation,
    RecommendationOutcome,
)
from apps.api.src.domain.performance.metrics import compute_metrics

pytestmark = pytest.mark.integration


def _seed_rec_with_outcome(
    pg_session: Session,
    asset: Asset,
    offset_days: int,
    r30: Decimal,
    r90: Decimal,
    label: int,
    snap: str,
) -> str:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    rec = Recommendation(
        asset_id=asset.id, action="Buy", model_version="0.1.0",
        snapshot_hash=snap, rationale='{"snapshot_hash":"' + snap + '"}',
        conviction=Decimal("50"),
        generated_at=now - dt.timedelta(days=offset_days),
    )
    pg_session.add(rec)
    pg_session.flush()
    pg_session.add(RecommendationOutcome(
        recommendation_id=rec.id,
        price_at_recommendation=Decimal("100"),
        realized_30d_return=r30,
        realized_90d_return=r90,
        barrier_label=label,
    ))
    pg_session.commit()
    return rec.id


def test_compute_metrics_module_on_sample_data(pg_session: Session) -> None:
    returns = [Decimal("0.1"), Decimal("-0.05"), Decimal("0.03")]
    labels = [1, -1, 1]
    m = compute_metrics(returns, labels)
    assert m.total_trades == 3
    assert m.wins == 2
    assert m.losses == 1
    assert m.neutral == 0
    assert m.expectancy == (Decimal("0.08") / Decimal("3"))


def test_performance_api_aggregates_outcomes(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    asset = Asset(symbol="PERF", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()

    # Mix of wins, losses, neutral over different recs
    scenarios = [
        (100, Decimal("0.10"), Decimal("0.20"), 1, "s1"),
        (95, Decimal("-0.05"), Decimal("-0.02"), -1, "s2"),
        (90, Decimal("0.03"), Decimal("0.05"), 1, "s3"),
        (85, Decimal("0"), Decimal("0.01"), 0, "s4"),
        (80, Decimal("-0.02"), Decimal("-0.03"), -1, "s5"),
    ]
    for offset, r30, r90, label, snap in scenarios:
        _seed_rec_with_outcome(pg_session, asset, offset, r30, r90, label, snap)

    client = TestClient(app)
    resp = client.get("/api/performance?window=30d")
    assert resp.status_code == 200
    data = resp.json()

    core = data["recommendation_metrics"]["tier_1_core"]
    exp = data["experimental_metrics"]
    assert data["window"] == "30d"
    assert core["total_trades"] == 5
    assert core["wins"] == 2
    assert core["losses"] == 2
    assert core["neutral"] == 1
    # win_rate = 2/5 = 0.4
    assert Decimal(core["win_rate"]) == Decimal("2") / Decimal("5")
    # expectancy = (0.1 - 0.05 + 0.03 + 0 - 0.02) / 5 = 0.06 / 5 = 0.012
    assert Decimal(core["expectancy"]).quantize(Decimal("0.001")) == Decimal("0.012")
    # profit_factor = (0.10 + 0.03) / (0.05 + 0.02) = 0.13 / 0.07 ~ 1.857
    assert Decimal(core["profit_factor"]) > Decimal("1.8")
    assert Decimal(core["profit_factor"]) < Decimal("2.0")
    assert exp["max_drawdown"] is not None  # some drawdown in mixed path
    assert exp["sharpe_ratio"] is not None

    # Breakdown contains both windows
    assert "30d" in data["breakdown_by_window"]
    assert "90d" in data["breakdown_by_window"]
    assert (
        data["breakdown_by_window"]["90d"]
        ["recommendation_metrics"]["tier_1_core"]["total_trades"] == 5
    )


def test_performance_api_empty_when_no_outcomes(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    client = TestClient(app)
    resp = client.get("/api/performance?window=30d")
    assert resp.status_code == 200
    data = resp.json()
    core = data["recommendation_metrics"]["tier_1_core"]
    exp = data["experimental_metrics"]
    assert core["total_trades"] == 0
    assert core["win_rate"] is None
    assert core["hit_rate"] is None
    assert exp["sharpe_ratio"] is None
