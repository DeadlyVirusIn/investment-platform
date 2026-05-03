"""Integration: tiered /api/performance response structure + numbers."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, Recommendation, RecommendationOutcome

pytestmark = pytest.mark.integration


def _seed_outcome(
    pg_session: Session,
    asset: Asset,
    offset_days: int,
    r30: Decimal,
    r90: Decimal,
    label: int,
    conviction: Decimal,
    snap: str,
) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    rec = Recommendation(
        asset_id=asset.id, action="Buy", model_version="0.1.0",
        snapshot_hash=snap, rationale='{"snapshot_hash":"' + snap + '"}',
        conviction=conviction,
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


def test_tiered_response_contains_all_three_tiers(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    a = Asset(symbol="AAA", asset_class="equity", exchange="NASDAQ", currency="USD")
    b = Asset(symbol="BBB", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add_all([a, b])
    pg_session.flush()
    pg_session.commit()

    _seed_outcome(pg_session, a, 100, Decimal("0.10"), Decimal("0.20"), 1, Decimal("75"), "s1")
    _seed_outcome(pg_session, a, 95, Decimal("-0.03"), Decimal("-0.01"), -1, Decimal("75"), "s2")
    _seed_outcome(pg_session, b, 90, Decimal("0.05"), Decimal("0.08"), 1, Decimal("45"), "s3")
    _seed_outcome(pg_session, b, 85, Decimal("-0.02"), Decimal("-0.04"), -1, Decimal("20"), "s4")

    client = TestClient(app)
    resp = client.get("/api/performance?window=30d")
    assert resp.status_code == 200
    data = resp.json()

    assert data["window"] == "30d"
    assert "recommendation_metrics" in data
    assert "experimental_metrics" in data
    assert "breakdown_by_window" in data
    assert "30d" in data["breakdown_by_window"]
    assert "90d" in data["breakdown_by_window"]

    core = data["recommendation_metrics"]["tier_1_core"]
    assert core["total_trades"] == 4
    assert core["wins"] == 2
    assert core["losses"] == 2
    # hit_rate = 2 / 4 = 0.5
    assert Decimal(core["hit_rate"]) == Decimal("0.5")
    # Tier-1 has both hit_rate and win_rate present
    assert core["win_rate"] is not None

    exp = data["experimental_metrics"]
    assert "__warning__" in exp
    assert "EXPERIMENTAL" in exp["__warning__"]


def test_confidence_calibration_in_api(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    a = Asset(symbol="CAL", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(a)
    pg_session.flush()
    pg_session.commit()

    # High-confidence winners; low-confidence losers → calibration should show
    # higher hit_rate on High bucket.
    _seed_outcome(pg_session, a, 100, Decimal("0.10"), Decimal("0.15"), 1, Decimal("80"), "c1")
    _seed_outcome(pg_session, a, 95,  Decimal("0.08"), Decimal("0.12"), 1, Decimal("75"), "c2")
    _seed_outcome(pg_session, a, 90,  Decimal("-0.05"), Decimal("-0.03"), -1, Decimal("15"), "c3")
    _seed_outcome(pg_session, a, 85,  Decimal("-0.04"), Decimal("-0.02"), -1, Decimal("10"), "c4")

    client = TestClient(app)
    resp = client.get("/api/performance?window=30d")
    assert resp.status_code == 200
    buckets = resp.json()["recommendation_metrics"]["tier_2_conditional"]["confidence_buckets"]
    by_name = {b["bucket"]: b for b in buckets}
    assert by_name["High (60-100)"]["count"] == 2
    assert Decimal(by_name["High (60-100)"]["hit_rate"]) == Decimal("1")
    assert by_name["Low (0-30)"]["count"] == 2
    assert Decimal(by_name["Low (0-30)"]["hit_rate"]) == Decimal("0")


def test_per_asset_breakdown_in_api(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    a = Asset(symbol="SYMA", asset_class="equity", exchange="NASDAQ", currency="USD")
    b = Asset(symbol="SYMB", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add_all([a, b])
    pg_session.flush()
    pg_session.commit()

    _seed_outcome(pg_session, a, 100, Decimal("0.05"), Decimal("0.10"), 1, Decimal("50"), "p1")
    _seed_outcome(pg_session, a, 95,  Decimal("-0.02"), Decimal("-0.01"), -1, Decimal("50"), "p2")
    _seed_outcome(pg_session, b, 90,  Decimal("0.03"), Decimal("0.04"), 1, Decimal("50"), "p3")

    client = TestClient(app)
    data = client.get("/api/performance?window=30d").json()
    per_asset = data["recommendation_metrics"]["tier_2_conditional"]["per_asset"]
    by_sym = {p["symbol"]: p for p in per_asset}
    assert by_sym["SYMA"]["count"] == 2
    assert Decimal(by_sym["SYMA"]["hit_rate"]) == Decimal("0.5")
    assert by_sym["SYMB"]["count"] == 1
    assert Decimal(by_sym["SYMB"]["hit_rate"]) == Decimal("1")
    assert [p["symbol"] for p in per_asset] == ["SYMA", "SYMB"]
