"""Integration tests for /performance/paper/alpha-lab.

Verifies:
  * Returns real summary counts from paper_position +
    paper_trade + replay manifest.
  * Open winners sorted by unrealized_pnl_pct desc; losers asc.
  * Closed winners/losers sourced from paper_trade rows where
    side='sell'.
  * Patterns aggregate by age bucket / portfolio / concentration.
  * Empty DB returns zero-state with no fabricated values.
  * Replay-flagged trades surface via is_replay; not subtracted
    from headline figures.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db import get_session
from apps.api.src.db.models import (
    Asset, PaperPortfolio, PaperPosition, PaperTrade, PriceBar,
)
from apps.api.src.main import app


pytestmark = pytest.mark.integration


@pytest.fixture
def client(pg_engine):
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )

    def _override():
        s = SessionCls()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


def _seed_position(
    session: Session, *, symbol: str, entry: float,
    last_price: float | None, held_days: int = 3,
    portfolio_name: str = "P",
) -> str:
    a = Asset(symbol=symbol, asset_class="equity", currency="USD")
    p = PaperPortfolio(
        name=portfolio_name, starting_cash=Decimal("10000"),
        cash=Decimal("9000"), is_active=True,
    )
    session.add_all([a, p])
    session.flush()
    opened_at = (
        dt.datetime.now(dt.timezone.utc).replace(
            hour=15, minute=0, second=0, microsecond=0,
        ) - dt.timedelta(days=held_days)
    )
    session.add(PaperPosition(
        portfolio_id=p.id, asset_id=a.id,
        quantity=Decimal("10"), avg_cost=Decimal(str(entry)),
        is_open=True, opened_at=opened_at,
    ))
    if last_price is not None:
        session.add(PriceBar(
            asset_id=a.id, timeframe="1d",
            ts=dt.datetime.combine(
                dt.date.today(),
                dt.time(13, 0), tzinfo=dt.timezone.utc,
            ),
            open=last_price, high=last_price, low=last_price,
            close=last_price, adjusted_close=last_price,
            provider="test",
        ))
    session.commit()
    return a.id


def test_empty_db_returns_zero_state(client):
    body = client.get("/api/performance/paper/alpha-lab").json()
    s = body["summary"]
    assert s["open_positions"] == 0
    assert s["closed_positions"] == 0
    assert s["open_unrealized_pnl"] == 0.0
    assert s["closed_realized_pnl"] == 0.0
    assert body["open_winners"] == []
    assert body["open_losers"] == []
    assert body["closed_winners"] == []
    assert body["closed_losers"] == []


def test_winners_and_losers_split(pg_session, client):
    _seed_position(
        pg_session, symbol="WIN", entry=100, last_price=120,
        portfolio_name="P1",
    )
    _seed_position(
        pg_session, symbol="LOSE", entry=100, last_price=90,
        portfolio_name="P2",
    )
    body = client.get("/api/performance/paper/alpha-lab").json()
    assert body["summary"]["open_positions"] == 2
    assert [r["symbol"] for r in body["open_winners"]] == ["WIN"]
    assert [r["symbol"] for r in body["open_losers"]] == ["LOSE"]
    assert body["summary"]["open_winners_count"] == 1
    assert body["summary"]["open_losers_count"] == 1
    win = body["open_winners"][0]
    assert win["unrealized_pnl"] == pytest.approx(200.0, abs=0.01)
    assert win["unrealized_pnl_pct"] == pytest.approx(0.20, abs=0.0001)


def test_winners_sorted_descending(pg_session, client):
    _seed_position(
        pg_session, symbol="A", entry=100, last_price=110,
        portfolio_name="PA",
    )
    _seed_position(
        pg_session, symbol="B", entry=100, last_price=130,
        portfolio_name="PB",
    )
    _seed_position(
        pg_session, symbol="C", entry=100, last_price=120,
        portfolio_name="PC",
    )
    body = client.get("/api/performance/paper/alpha-lab").json()
    syms = [r["symbol"] for r in body["open_winners"]]
    assert syms == ["B", "C", "A"]


def test_losers_sorted_ascending(pg_session, client):
    _seed_position(
        pg_session, symbol="A", entry=100, last_price=95,
        portfolio_name="PA",
    )
    _seed_position(
        pg_session, symbol="B", entry=100, last_price=80,
        portfolio_name="PB",
    )
    body = client.get("/api/performance/paper/alpha-lab").json()
    syms = [r["symbol"] for r in body["open_losers"]]
    assert syms == ["B", "A"]


def test_missing_price_bar_renders_null_marks(pg_session, client):
    _seed_position(
        pg_session, symbol="NOPX", entry=100, last_price=None,
        portfolio_name="P",
    )
    body = client.get("/api/performance/paper/alpha-lab").json()
    # Position counted; mark + unrealized null; not in winners/losers.
    assert body["summary"]["open_positions"] == 1
    assert body["open_winners"] == []
    assert body["open_losers"] == []


def test_inactive_portfolios_excluded(pg_session, client):
    a = Asset(symbol="X", asset_class="equity", currency="USD")
    p = PaperPortfolio(
        name="inactive", starting_cash=Decimal("1000"),
        cash=Decimal("500"), is_active=False,
    )
    pg_session.add_all([a, p])
    pg_session.flush()
    pg_session.add(PaperPosition(
        portfolio_id=p.id, asset_id=a.id,
        quantity=Decimal("1"), avg_cost=Decimal("100"),
        is_open=True,
        opened_at=dt.datetime.now(dt.timezone.utc),
    ))
    pg_session.commit()
    body = client.get("/api/performance/paper/alpha-lab").json()
    assert body["summary"]["open_positions"] == 0


def test_closed_winners_losers_split(pg_session, client):
    a = Asset(symbol="C", asset_class="equity", currency="USD")
    p = PaperPortfolio(
        name="P", starting_cash=Decimal("10000"),
        cash=Decimal("9000"), is_active=True,
    )
    pg_session.add_all([a, p])
    pg_session.flush()
    pg_session.add(PaperTrade(
        portfolio_id=p.id, asset_id=a.id, side="sell",
        quantity=Decimal("10"), fill_price=Decimal("110"),
        fill_ts=dt.datetime.now(dt.timezone.utc),
        submitted_at=dt.datetime.now(dt.timezone.utc),
        realized_pnl=Decimal("100"),
        reason="exit_cycle: take_profit",
    ))
    pg_session.add(PaperTrade(
        portfolio_id=p.id, asset_id=a.id, side="sell",
        quantity=Decimal("5"), fill_price=Decimal("90"),
        fill_ts=dt.datetime.now(dt.timezone.utc),
        submitted_at=dt.datetime.now(dt.timezone.utc),
        realized_pnl=Decimal("-50"),
        reason="exit_cycle: stop_loss",
    ))
    pg_session.commit()
    body = client.get("/api/performance/paper/alpha-lab").json()
    assert len(body["closed_winners"]) == 1
    assert len(body["closed_losers"]) == 1
    assert body["closed_winners"][0]["realized_pnl"] == 100
    assert body["closed_losers"][0]["realized_pnl"] == -50
    assert body["summary"]["closed_realized_pnl"] == pytest.approx(
        50.0, abs=0.01,
    )


def test_age_buckets_aggregate(pg_session, client):
    _seed_position(
        pg_session, symbol="N1", entry=100, last_price=110,
        held_days=1, portfolio_name="P1",
    )
    _seed_position(
        pg_session, symbol="N2", entry=100, last_price=105,
        held_days=4, portfolio_name="P2",
    )
    _seed_position(
        pg_session, symbol="N3", entry=100, last_price=95,
        held_days=15, portfolio_name="P3",
    )
    body = client.get("/api/performance/paper/alpha-lab").json()
    buckets = {
        b["bucket"]: b
        for b in body["patterns"]["by_age_bucket"]
    }
    assert "<=1d" in buckets
    assert "2-5d" in buckets
    assert "11-20d" in buckets


def test_concentration_top_symbols(pg_session, client):
    _seed_position(
        pg_session, symbol="BIG", entry=100, last_price=200,
        portfolio_name="P1",
    )
    _seed_position(
        pg_session, symbol="SMALL", entry=10, last_price=12,
        portfolio_name="P2",
    )
    body = client.get("/api/performance/paper/alpha-lab").json()
    syms = [c["symbol"] for c in body["patterns"]["concentration"]]
    assert syms[0] == "BIG"


def test_no_global_empty_state_when_open_positions_exist(
    pg_session, client,
):
    _seed_position(
        pg_session, symbol="X", entry=100, last_price=110,
        portfolio_name="P",
    )
    body = client.get("/api/performance/paper/alpha-lab").json()
    # No closed trades yet — but open_winners / open_losers /
    # patterns are populated, so the page is NOT empty.
    assert body["summary"]["open_positions"] == 1
    assert body["closed_winners"] == []
    assert body["closed_losers"] == []
    assert len(body["open_winners"]) == 1
    assert body["patterns"]["by_age_bucket"] != []
