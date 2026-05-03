"""Integration: /api/recommendations/diagnostics against Postgres."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, Recommendation, RecommendationEvidence

pytestmark = pytest.mark.integration


def _seed_rec(
    pg_session: Session,
    symbol: str,
    action: str,
    composite: str,
    evidence: list[dict],
    dampers: list[dict] | None = None,
    adjusted: str | None = None,
) -> str:
    asset = Asset(symbol=symbol, asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    rationale: dict = {
        "composite_score": composite,
        "enough_data": True,
        "stale_data": False,
        "confidence_label": "Medium",
        "family_scores": {"trend_momentum": composite},
    }
    if dampers is not None or adjusted is not None:
        rationale["policy"] = {
            "adjusted_composite_score": adjusted or composite,
            "adjustments": dampers or [],
        }
    rec = Recommendation(
        asset_id=asset.id, action=action, model_version="0.1.0",
        snapshot_hash=f"snap-{symbol}",
        rationale=json.dumps(rationale),
        conviction=Decimal("70"),
        generated_at=dt.datetime.now(dt.timezone.utc),
    )
    pg_session.add(rec)
    pg_session.flush()
    for ev in evidence:
        pg_session.add(RecommendationEvidence(
            recommendation_id=rec.id,
            evidence_type=ev["factor_key"], source=ev["family"],
            summary=json.dumps({
                "score": ev["score"], "direction": ev.get("direction", "bullish"),
                "narrative": ev.get("narrative", ""),
            }),
            weight=Decimal(str(ev.get("weight", "0.3"))),
        ))
    pg_session.commit()
    return rec.id


def test_diagnostics_endpoint_empty(pg_session: Session) -> None:
    from apps.api.src.main import app
    client = TestClient(app)
    resp = client.get("/api/recommendations/diagnostics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["summary"]["total"] == 0
    assert data["summary"]["buys"] == 0
    assert data["summary"]["near_buy_tight_count"] == 0


def test_diagnostics_orders_closest_to_buy(pg_session: Session) -> None:
    from apps.api.src.main import app

    _seed_rec(pg_session, "FAR", "Hold", "-0.10", evidence=[])
    _seed_rec(pg_session, "NEAR", "Hold", "0.22", evidence=[])
    _seed_rec(pg_session, "BUY", "Buy", "0.50", evidence=[])

    client = TestClient(app)
    resp = client.get("/api/recommendations/diagnostics")
    assert resp.status_code == 200
    data = resp.json()
    symbols = [d["symbol"] for d in data["diagnostics"]]
    assert symbols == ["BUY", "NEAR", "FAR"]
    # Summary
    assert data["summary"]["buys"] == 1
    # Near-buy tight (≤5%): BUY (0) + NEAR (0.03) = 2
    assert data["summary"]["near_buy_tight_count"] == 2


def test_diagnostics_surfaces_top_contributors_and_dampers(pg_session: Session) -> None:
    from apps.api.src.main import app

    evidence = [
        {"factor_key": "trend_strength", "family": "trend_momentum",
         "score": "0.18", "narrative": "strong uptrend"},
        {"factor_key": "rsi_14", "family": "volatility_risk",
         "score": "-0.12", "narrative": "RSI elevated"},
        {"factor_key": "sma_20_vs_50", "family": "trend_momentum",
         "score": "0.04"},
    ]
    dampers = [{
        "rule": "high_volatility_damping",
        "score_before": "0.30", "score_after": "0.21",
        "reason": "High volatility regime",
    }]
    _seed_rec(pg_session, "DAMP", "Hold", "0.30",
              evidence=evidence, dampers=dampers, adjusted="0.21")

    client = TestClient(app)
    resp = client.get("/api/recommendations/diagnostics")
    data = resp.json()
    d = data["diagnostics"][0]
    assert d["symbol"] == "DAMP"
    # composite_score is the policy-adjusted one
    assert Decimal(d["composite_score"]) == Decimal("0.21")
    assert Decimal(d["original_composite_score"]) == Decimal("0.30")
    assert Decimal(d["distance_to_buy"]) == Decimal("0.04")
    # Contributors sorted
    pos_keys = [c["factor_key"] for c in d["top_positive"]]
    assert pos_keys[0] == "trend_strength"
    neg_keys = [c["factor_key"] for c in d["top_negative"]]
    assert neg_keys == ["rsi_14"]
    # Damper surfaced
    assert len(d["dampers"]) == 1
    assert d["dampers"][0]["rule"] == "high_volatility_damping"
    # Batch summary counts damper
    assert data["summary"]["dampers_applied"] == 1


def test_diagnostics_respects_custom_buy_threshold(pg_session: Session) -> None:
    from apps.api.src.main import app
    _seed_rec(pg_session, "Q", "Hold", "0.10", evidence=[])
    client = TestClient(app)
    # Default threshold 0.25 → distance 0.15, no near-buy
    r1 = client.get("/api/recommendations/diagnostics").json()
    assert r1["summary"]["near_buy_tight_count"] == 0
    # Lower threshold 0.12 → distance 0.02, within tight band
    r2 = client.get("/api/recommendations/diagnostics?buy_threshold=0.12").json()
    assert r2["summary"]["near_buy_tight_count"] == 1
    assert Decimal(r2["summary"]["buy_threshold"]) == Decimal("0.12")
