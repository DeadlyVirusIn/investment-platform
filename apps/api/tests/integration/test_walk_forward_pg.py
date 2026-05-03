"""Integration: walk-forward endpoint against Postgres."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    Recommendation,
    RecommendationOutcome,
)

pytestmark = pytest.mark.integration


def _seed_asset(pg_session: Session, symbol: str) -> str:
    a = Asset(symbol=symbol, asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(a)
    pg_session.flush()
    pg_session.commit()
    return a.id


def _add_rec(
    pg_session: Session,
    asset_id: str,
    generated_at: dt.datetime,
    barrier_label: int,
    realized_return: str,
    snapshot: str,
    signal_type: str | None = "default",
) -> None:
    rec = Recommendation(
        asset_id=asset_id,
        action="Buy",
        model_version="0.1.0",
        snapshot_hash=snapshot,
        rationale="{}",
        conviction=Decimal("70"),
        generated_at=generated_at,
    )
    pg_session.add(rec)
    pg_session.flush()
    pg_session.add(RecommendationOutcome(
        recommendation_id=rec.id,
        price_at_recommendation=Decimal("100"),
        barrier_label=barrier_label,
        barrier_n_bars=30,
        signal_type=signal_type,
        realized_30d_return=Decimal(realized_return),
    ))
    pg_session.commit()


def test_walk_forward_endpoint_empty_returns_no_splits(pg_session: Session) -> None:
    from apps.api.src.main import app

    client = TestClient(app)
    resp = client.get("/api/backtest/walk-forward/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["split_count"] == 0
    assert data["aggregate_stability"] == "UNKNOWN"
    assert data["config"]["train_days"] == 252


def test_walk_forward_endpoint_with_data(pg_session: Session) -> None:
    from apps.api.src.main import app

    asset_id = _seed_asset(pg_session, "WF1")
    base = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    # IS window (252d): strong positive edge
    for i in range(0, 252, 10):
        _add_rec(pg_session, asset_id, base + dt.timedelta(days=i),
                 barrier_label=1, realized_return="0.03", snapshot=f"is-{i}")
    # OOS window (63d): same edge → WFE ~ 1.0 → ROBUST
    for i in range(252, 315, 10):
        _add_rec(pg_session, asset_id, base + dt.timedelta(days=i),
                 barrier_label=1, realized_return="0.03", snapshot=f"oos-{i}")

    client = TestClient(app)
    resp = client.get("/api/backtest/walk-forward/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["split_count"] == 1
    split = data["splits"][0]
    assert split["stability"] == "ROBUST"
    assert Decimal(split["wfe"]) == Decimal("1")
    assert split["is_metrics"]["count"] > 0
    assert split["oos_metrics"]["count"] > 0
    assert data["aggregate_stability"] == "ROBUST"


def test_walk_forward_endpoint_custom_params(pg_session: Session) -> None:
    from apps.api.src.main import app

    asset_id = _seed_asset(pg_session, "WF2")
    base = dt.datetime(2024, 6, 1, tzinfo=dt.timezone.utc)
    for i in range(0, 150, 5):
        _add_rec(pg_session, asset_id, base + dt.timedelta(days=i),
                 barrier_label=1, realized_return="0.02", snapshot=f"p-{i}")

    client = TestClient(app)
    resp = client.get(
        "/api/backtest/walk-forward/summary"
        "?train_days=60&test_days=30&step_days=30"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["config"]["train_days"] == 60
    assert data["config"]["test_days"] == 30
    assert data["split_count"] >= 2


def test_walk_forward_endpoint_stratified_by_signal_type(pg_session: Session) -> None:
    from apps.api.src.main import app

    asset_id = _seed_asset(pg_session, "WF3")
    base = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    for i in range(0, 315, 10):
        _add_rec(pg_session, asset_id, base + dt.timedelta(days=i),
                 barrier_label=1, realized_return="0.02", snapshot=f"t-{i}",
                 signal_type="trend")
        _add_rec(pg_session, asset_id, base + dt.timedelta(days=i),
                 barrier_label=-1, realized_return="-0.02", snapshot=f"m-{i}",
                 signal_type="mean_reversion")

    client = TestClient(app)
    resp = client.get("/api/backtest/walk-forward/summary?signal_type=trend")
    assert resp.status_code == 200
    data = resp.json()
    assert data["stratified_by"] == "trend"
    assert data["aggregate_stability"] == "ROBUST"

    resp2 = client.get("/api/backtest/walk-forward/summary?signal_type=mean_reversion")
    data2 = resp2.json()
    # Negative IS expectancy → WFE undefined → UNKNOWN
    assert data2["splits"][0]["stability"] == "UNKNOWN"
