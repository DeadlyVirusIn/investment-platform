"""Integration: /api/asset/{symbol}/prices endpoint for benchmark overlays."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, PriceBar

pytestmark = pytest.mark.integration


def _seed_series(
    pg_session: Session,
    symbol: str,
    n: int = 10,
    start: Decimal = Decimal("100"),
    step: Decimal = Decimal("0.5"),
) -> tuple[str, dt.datetime]:
    base = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    asset = Asset(symbol=symbol, asset_class="etf", exchange="NYSE", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()
    for i in range(n):
        price = start + step * Decimal(i)
        pg_session.add(PriceBar(
            asset_id=asset.id, timeframe="1d",
            ts=base + dt.timedelta(days=i),
            open=price, high=price + Decimal("0.5"), low=price - Decimal("0.5"),
            close=price, adjusted_close=price,
            volume=1_000_000, provider="test",
        ))
    pg_session.commit()
    return asset.id, base


def test_asset_prices_returns_full_series(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    _seed_series(pg_session, "SPY", n=5)
    client = TestClient(app)
    resp = client.get("/api/asset/SPY/prices")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "SPY"
    assert data["timeframe"] == "1d"
    assert data["count"] == 5
    assert len(data["prices"]) == 5
    # Sorted ascending by ts
    for i in range(1, len(data["prices"])):
        assert data["prices"][i]["ts"] > data["prices"][i - 1]["ts"]


def test_asset_prices_respects_from_and_to(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    _seed_series(pg_session, "BND", n=10)
    client = TestClient(app)
    # Day 3..7 inclusive. Use params= so TestClient URL-encodes "+" properly.
    from_iso = dt.datetime(2026, 1, 4, tzinfo=dt.timezone.utc).isoformat()
    to_iso = dt.datetime(2026, 1, 8, tzinfo=dt.timezone.utc).isoformat()
    resp = client.get(
        "/api/asset/BND/prices",
        params={"from": from_iso, "to": to_iso},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 5


def test_asset_prices_unknown_symbol_404(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    client = TestClient(app)
    resp = client.get("/api/asset/UNKNOWN/prices")
    assert resp.status_code == 404


def test_asset_detail_returns_fields(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    _seed_series(pg_session, "MSFT", n=1)
    client = TestClient(app)
    resp = client.get("/api/asset/MSFT")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "MSFT"
    assert data["asset_class"] == "etf"
    assert data["is_active"] is True
