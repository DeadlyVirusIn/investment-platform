"""Integration: paper-performance API + service against Postgres."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    PaperEquitySnapshot,
    PaperPortfolio,
    PaperTrade,
)
from apps.api.src.domain.performance.paper_performance import compute_paper_metrics

pytestmark = pytest.mark.integration


def _make_portfolio(pg_session: Session, cash: str = "1000") -> PaperPortfolio:
    p = PaperPortfolio(
        name=f"perf-{dt.datetime.now().timestamp()}",
        starting_cash=Decimal(cash),
        cash=Decimal(cash),
        is_active=True,
    )
    pg_session.add(p)
    pg_session.flush()
    pg_session.commit()
    return p


def _snapshot(pg_session: Session, pid: str, day_offset: int, equity: str) -> None:
    pg_session.add(PaperEquitySnapshot(
        portfolio_id=pid,
        snapshot_date=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(days=day_offset),
        cash=Decimal(equity),
        positions_value=Decimal("0"),
        total_equity=Decimal(equity),
        unrealized_pnl=Decimal("0"),
        realized_pnl_cumulative=Decimal("0"),
    ))
    pg_session.commit()


def _sell_trade(pg_session: Session, pid: str, asset_id: str, pnl: str) -> None:
    pg_session.add(PaperTrade(
        portfolio_id=pid,
        asset_id=asset_id,
        side="sell",
        quantity=Decimal("1"),
        fill_price=Decimal("100"),
        fill_ts=dt.datetime.now(dt.timezone.utc),
        realized_pnl=Decimal(pnl),
    ))
    pg_session.commit()


def _seed_asset(pg_session: Session, symbol: str) -> str:
    a = Asset(symbol=symbol, asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(a)
    pg_session.flush()
    pg_session.commit()
    return a.id


# ---------------------------------------------------------------------------
# Service layer
# ---------------------------------------------------------------------------


def test_compute_metrics_empty_portfolio(pg_session: Session) -> None:
    p = _make_portfolio(pg_session)
    m = compute_paper_metrics(pg_session, p.id)
    assert m.trades == 0
    assert m.wins == 0
    assert m.losses == 0
    assert m.hit_rate is None
    assert m.expectancy is None
    assert m.profit_factor is None
    assert m.max_drawdown is None
    assert m.sharpe is None
    # Total return derived from cash vs starting_cash = 0 on empty
    assert m.total_return == Decimal("0")


def test_compute_metrics_full_scenario(pg_session: Session) -> None:
    p = _make_portfolio(pg_session, cash="1000")
    a = _seed_asset(pg_session, "XYZ")

    _sell_trade(pg_session, p.id, a, "50")
    _sell_trade(pg_session, p.id, a, "-20")
    _sell_trade(pg_session, p.id, a, "30")

    # Equity 1000 -> 1100 -> 900 -> 1060
    for i, eq in enumerate(["1000", "1100", "900", "1060"]):
        _snapshot(pg_session, p.id, i, eq)

    m = compute_paper_metrics(pg_session, p.id)
    assert m.trades == 3
    assert m.wins == 2
    assert m.losses == 1
    assert m.hit_rate == Decimal("2") / Decimal("3")
    # expectancy = (50 - 20 + 30) / 3 = 20
    assert m.expectancy == Decimal("20")
    # profit_factor = 80 / 20 = 4
    assert m.profit_factor == Decimal("4")
    # max_drawdown: peak 1100 -> trough 900 -> -0.1818..
    assert m.max_drawdown is not None
    assert m.max_drawdown < Decimal("-0.18")
    assert m.max_drawdown > Decimal("-0.19")
    # total_return = (1060 - 1000) / 1000 = 0.06
    assert m.total_return == Decimal("0.06")


def test_summary_endpoint_empty_state(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    client = TestClient(app)
    resp = client.get("/api/performance/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["portfolio_id"] is None
    assert data["trades"] == 0
    assert data["total_return"] is None
    assert data["hit_rate"] is None
    assert data.get("empty_state")


def test_summary_endpoint_with_data(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    p = _make_portfolio(pg_session)
    a = _seed_asset(pg_session, "AAA")
    _sell_trade(pg_session, p.id, a, "100")
    _sell_trade(pg_session, p.id, a, "-40")
    for i, eq in enumerate(["1000", "1060"]):
        _snapshot(pg_session, p.id, i, eq)

    client = TestClient(app)
    resp = client.get(f"/api/performance/summary?portfolio_id={p.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["trades"] == 2
    assert data["wins"] == 1
    assert data["losses"] == 1
    assert Decimal(data["hit_rate"]) == Decimal("0.5")
    assert Decimal(data["expectancy"]) == Decimal("30")


def test_equity_curve_endpoint(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    p = _make_portfolio(pg_session)
    for i, eq in enumerate(["1000", "1010", "1020", "1005"]):
        _snapshot(pg_session, p.id, i, eq)

    client = TestClient(app)
    resp = client.get(f"/api/performance/equity-curve?portfolio_id={p.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["portfolio_id"] == p.id
    assert len(data["points"]) == 4
    assert data["points"][0]["date"] == "2026-01-01"
    assert Decimal(data["points"][0]["equity"]) == Decimal("1000")
    assert Decimal(data["points"][3]["equity"]) == Decimal("1005")


def test_equity_curve_empty_returns_empty_points(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    client = TestClient(app)
    resp = client.get("/api/performance/equity-curve")
    assert resp.status_code == 200
    data = resp.json()
    assert data["portfolio_id"] is None
    assert data["points"] == []
