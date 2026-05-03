"""Integration tests for paper-trading backend."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    PaperPortfolio,
    PaperPosition,
    PaperTrade,
    PriceBar,
)
from apps.api.src.domain.paper_trading.paper_execution import (
    PaperTradeRejected,
    find_next_open,
    submit_trade,
)
from apps.api.src.domain.paper_trading.paper_service import (
    PortfolioCreate,
    compute_equity_breakdown,
    create_portfolio,
    snapshot_equity_now,
    trade_counts,
)

pytestmark = pytest.mark.integration

BASE_TS = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def _seed_asset_with_prices(
    pg_session: Session,
    symbol: str,
    closes: list[str],
    opens: list[str] | None = None,
    start_ts: dt.datetime = BASE_TS,
) -> str:
    asset = Asset(symbol=symbol, asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()
    opens = opens or closes
    for i, (c, o) in enumerate(zip(closes, opens)):
        pg_session.add(PriceBar(
            asset_id=asset.id, timeframe="1d",
            ts=start_ts + dt.timedelta(days=i),
            open=Decimal(o),
            high=Decimal(str(max(float(c), float(o)) + 0.5)),
            low=Decimal(str(min(float(c), float(o)) - 0.5)),
            close=Decimal(c),
            adjusted_close=Decimal(c),
            volume=1_000_000,
            provider="test",
        ))
    pg_session.commit()
    return asset.id


# ---------------------------------------------------------------------------
# find_next_open
# ---------------------------------------------------------------------------


def test_find_next_open_returns_next_bar(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "NXO",
        closes=["100", "101", "102"],
        opens=["99.5", "100.5", "101.5"],
    )
    fill = find_next_open(pg_session, asset_id, BASE_TS)
    assert fill is not None
    ts, price = fill
    # First bar IS at BASE_TS; we want strictly after → bar index 1
    assert ts == BASE_TS + dt.timedelta(days=1)
    assert price == Decimal("100.5")


def test_find_next_open_none_when_no_future_bar(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "END", closes=["100"], opens=["100"]
    )
    fill = find_next_open(pg_session, asset_id, BASE_TS + dt.timedelta(days=30))
    assert fill is None


# ---------------------------------------------------------------------------
# Portfolio + trade flow
# ---------------------------------------------------------------------------


def test_create_portfolio_with_defaults(pg_session: Session) -> None:
    p = create_portfolio(pg_session, PortfolioCreate(name="default"))
    pg_session.commit()
    assert p.id
    assert Decimal(str(p.starting_cash)) == Decimal("1000.00")
    assert Decimal(str(p.cash)) == Decimal("1000.00")
    assert p.is_active is True


def test_duplicate_portfolio_name_raises(pg_session: Session) -> None:
    create_portfolio(pg_session, PortfolioCreate(name="dup"))
    pg_session.commit()
    with pytest.raises(ValueError, match="already in use"):
        create_portfolio(pg_session, PortfolioCreate(name="dup"))


def test_buy_opens_position_next_open_fill(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "BUY",
        closes=["100", "101", "102"],
        opens=["100", "100", "103"],
    )
    p = create_portfolio(pg_session, PortfolioCreate(name="buy-test", starting_cash=Decimal("1000")))
    pg_session.commit()

    # Submit at BASE_TS → fill at next bar's open = 100 (day 1)
    result = submit_trade(
        pg_session, portfolio_id=p.id, asset_id=asset_id,
        side="buy", quantity=Decimal("2"), submitted_at=BASE_TS,
    )
    pg_session.commit()

    assert result.fill_price == Decimal("100")
    assert result.fill_ts == BASE_TS + dt.timedelta(days=1)
    assert result.cash_after == Decimal("800")
    assert result.realized_pnl is None

    pos = pg_session.scalar(
        select(PaperPosition).where(
            PaperPosition.portfolio_id == p.id,
            PaperPosition.asset_id == asset_id,
            PaperPosition.is_open.is_(True),
        )
    )
    assert pos is not None
    assert Decimal(str(pos.quantity)) == Decimal("2")
    assert Decimal(str(pos.avg_cost)) == Decimal("100")


def test_sell_closes_position_records_realized(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "SELL",
        closes=["100", "100", "120"],
        opens=["100", "100", "120"],
    )
    p = create_portfolio(pg_session, PortfolioCreate(name="sell-test"))
    pg_session.commit()

    submit_trade(
        pg_session, portfolio_id=p.id, asset_id=asset_id,
        side="buy", quantity=Decimal("5"), submitted_at=BASE_TS,
    )
    pg_session.commit()
    # After-buy cash: 1000 - 5*100 = 500

    sell = submit_trade(
        pg_session, portfolio_id=p.id, asset_id=asset_id,
        side="sell", quantity=Decimal("5"),
        submitted_at=BASE_TS + dt.timedelta(days=1),
    )
    pg_session.commit()
    # Sell fills at day-2 open = 120 → proceeds 5 × 120 = 600 → cash = 500 + 600 = 1100
    assert sell.fill_price == Decimal("120")
    assert sell.cash_after == Decimal("1100")
    assert sell.realized_pnl == Decimal("100")  # 5 × (120 - 100)

    pos = pg_session.scalar(
        select(PaperPosition).where(PaperPosition.portfolio_id == p.id)
    )
    assert pos.is_open is False
    assert pos.closed_at is not None


def test_partial_sell_keeps_remaining_open(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "PRT",
        closes=["100"] * 5, opens=["100"] * 5,
    )
    p = create_portfolio(pg_session, PortfolioCreate(name="partial"))
    pg_session.commit()
    submit_trade(pg_session, portfolio_id=p.id, asset_id=asset_id,
                 side="buy", quantity=Decimal("10"), submitted_at=BASE_TS)
    pg_session.commit()

    submit_trade(pg_session, portfolio_id=p.id, asset_id=asset_id,
                 side="sell", quantity=Decimal("4"),
                 submitted_at=BASE_TS + dt.timedelta(days=1))
    pg_session.commit()

    pos = pg_session.scalar(
        select(PaperPosition).where(
            PaperPosition.portfolio_id == p.id,
            PaperPosition.is_open.is_(True),
        )
    )
    assert Decimal(str(pos.quantity)) == Decimal("6")


def test_insufficient_cash_rejects(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "RICH", closes=["500", "500"], opens=["500", "500"]
    )
    p = create_portfolio(pg_session, PortfolioCreate(name="poor", starting_cash=Decimal("100")))
    pg_session.commit()
    with pytest.raises(PaperTradeRejected, match="insufficient cash"):
        submit_trade(
            pg_session, portfolio_id=p.id, asset_id=asset_id,
            side="buy", quantity=Decimal("1"), submitted_at=BASE_TS,
        )


def test_sell_without_position_rejects(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "NOPOS", closes=["100", "100"], opens=["100", "100"]
    )
    p = create_portfolio(pg_session, PortfolioCreate(name="empty"))
    pg_session.commit()
    with pytest.raises(PaperTradeRejected, match="no open position"):
        submit_trade(
            pg_session, portfolio_id=p.id, asset_id=asset_id,
            side="sell", quantity=Decimal("1"), submitted_at=BASE_TS,
        )


def test_sell_over_position_rejects(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "LOW", closes=["100"] * 5, opens=["100"] * 5
    )
    p = create_portfolio(pg_session, PortfolioCreate(name="low-qty"))
    pg_session.commit()
    submit_trade(pg_session, portfolio_id=p.id, asset_id=asset_id,
                 side="buy", quantity=Decimal("2"), submitted_at=BASE_TS)
    pg_session.commit()
    with pytest.raises(PaperTradeRejected, match="insufficient position"):
        submit_trade(
            pg_session, portfolio_id=p.id, asset_id=asset_id,
            side="sell", quantity=Decimal("5"),
            submitted_at=BASE_TS + dt.timedelta(days=1),
        )


def test_max_open_positions_blocks_new_asset(pg_session: Session) -> None:
    p = create_portfolio(
        pg_session,
        PortfolioCreate(name="capped", starting_cash=Decimal("10000"), max_open_positions=2),
    )
    pg_session.commit()
    for sym in ("X1", "X2"):
        aid = _seed_asset_with_prices(
            pg_session, sym, closes=["100"] * 5, opens=["100"] * 5
        )
        submit_trade(pg_session, portfolio_id=p.id, asset_id=aid,
                     side="buy", quantity=Decimal("1"), submitted_at=BASE_TS)
        pg_session.commit()
    # Third asset should reject
    aid3 = _seed_asset_with_prices(
        pg_session, "X3", closes=["100"] * 5, opens=["100"] * 5
    )
    with pytest.raises(PaperTradeRejected, match="max open positions"):
        submit_trade(
            pg_session, portfolio_id=p.id, asset_id=aid3,
            side="buy", quantity=Decimal("1"), submitted_at=BASE_TS,
        )


def test_adding_to_existing_position_blends_avg_cost(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "BLND",
        closes=["100", "100", "110", "110"],
        opens=["100", "100", "110", "110"],
    )
    p = create_portfolio(pg_session, PortfolioCreate(name="blend", starting_cash=Decimal("10000")))
    pg_session.commit()
    submit_trade(pg_session, portfolio_id=p.id, asset_id=asset_id,
                 side="buy", quantity=Decimal("5"), submitted_at=BASE_TS)
    pg_session.commit()  # 5 @ 100 → avg=100
    submit_trade(pg_session, portfolio_id=p.id, asset_id=asset_id,
                 side="buy", quantity=Decimal("5"),
                 submitted_at=BASE_TS + dt.timedelta(days=1))
    pg_session.commit()  # 5 @ 110 → total 10, avg = (500+550)/10 = 105
    pos = pg_session.scalar(
        select(PaperPosition).where(
            PaperPosition.portfolio_id == p.id, PaperPosition.is_open.is_(True)
        )
    )
    assert Decimal(str(pos.quantity)) == Decimal("10")
    assert Decimal(str(pos.avg_cost)) == Decimal("105")


def test_equity_breakdown_and_return(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "EQBR",
        closes=["100", "100", "120"],
        opens=["100", "100", "120"],
    )
    p = create_portfolio(pg_session, PortfolioCreate(name="eqbr", starting_cash=Decimal("1000")))
    pg_session.commit()
    submit_trade(pg_session, portfolio_id=p.id, asset_id=asset_id,
                 side="buy", quantity=Decimal("5"), submitted_at=BASE_TS)
    pg_session.commit()

    breakdown = compute_equity_breakdown(pg_session, p)
    # cash: 1000 - 500 = 500; positions latest close = 120; value 5*120 = 600
    assert Decimal(str(breakdown["cash"])) == Decimal("500")
    assert Decimal(str(breakdown["positions_value"])) == Decimal("600")
    assert Decimal(str(breakdown["total_equity"])) == Decimal("1100")
    assert Decimal(str(breakdown["unrealized_pnl"])) == Decimal("100")  # 5 * (120-100)


def test_snapshot_equity_upserts_same_day(pg_session: Session) -> None:
    p = create_portfolio(pg_session, PortfolioCreate(name="snap"))
    pg_session.commit()
    s1 = snapshot_equity_now(pg_session, p)
    pg_session.commit()
    s2 = snapshot_equity_now(pg_session, p)
    pg_session.commit()
    # Same calendar day → same row id
    assert s1.id == s2.id


def test_usd_amount_sizing_computes_quantity(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "USD", closes=["100", "100"], opens=["100", "100"]
    )
    p = create_portfolio(pg_session, PortfolioCreate(name="usd", starting_cash=Decimal("1000")))
    pg_session.commit()
    result = submit_trade(
        pg_session, portfolio_id=p.id, asset_id=asset_id,
        side="buy", usd_amount=Decimal("250"), submitted_at=BASE_TS,
    )
    pg_session.commit()
    # 250 / 100 = 2.5 qty
    assert result.quantity == Decimal("2.5")


def test_trade_counts_wins_losses(pg_session: Session) -> None:
    # Day 1 open 100 (buy fill), day 2 open 120 (first sell fill → win),
    # day 3 open 120 (second buy fill), day 4 open 80 (second sell fill → loss)
    asset_id = _seed_asset_with_prices(
        pg_session, "WL",
        closes=["100", "100", "120", "120", "80"],
        opens=["100", "100", "120", "120", "80"],
    )
    p = create_portfolio(pg_session, PortfolioCreate(name="wl", starting_cash=Decimal("10000")))
    pg_session.commit()
    # Win trade
    submit_trade(pg_session, portfolio_id=p.id, asset_id=asset_id,
                 side="buy", quantity=Decimal("1"), submitted_at=BASE_TS)
    pg_session.commit()
    submit_trade(pg_session, portfolio_id=p.id, asset_id=asset_id,
                 side="sell", quantity=Decimal("1"),
                 submitted_at=BASE_TS + dt.timedelta(days=1))
    pg_session.commit()
    # Loss trade
    submit_trade(pg_session, portfolio_id=p.id, asset_id=asset_id,
                 side="buy", quantity=Decimal("1"),
                 submitted_at=BASE_TS + dt.timedelta(days=2))
    pg_session.commit()
    submit_trade(pg_session, portfolio_id=p.id, asset_id=asset_id,
                 side="sell", quantity=Decimal("1"),
                 submitted_at=BASE_TS + dt.timedelta(days=3))
    pg_session.commit()

    counts = trade_counts(pg_session, p.id)
    assert counts["wins"] == 1
    assert counts["losses"] == 1
    assert counts["breakeven"] == 0


# ---------------------------------------------------------------------------
# API end-to-end
# ---------------------------------------------------------------------------


def test_api_portfolio_create_and_trade(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    asset_id = _seed_asset_with_prices(
        pg_session, "API",
        closes=["100", "100", "120"],
        opens=["100", "100", "120"],
    )

    client = TestClient(app)
    # Create portfolio
    r = client.post("/api/paper/portfolios", json={
        "name": "api-test", "starting_cash": "1000",
    })
    assert r.status_code == 201
    pid = r.json()["id"]

    # Submit buy via symbol
    r = client.post(f"/api/paper/portfolios/{pid}/trade", json={
        "symbol": "API", "side": "buy", "quantity": "5",
        "submitted_at": BASE_TS.isoformat(),
    })
    assert r.status_code == 201
    body = r.json()
    assert body["side"] == "buy"
    assert Decimal(body["fill_price"]) == Decimal("100")

    # Portfolio detail
    r = client.get(f"/api/paper/portfolios/{pid}")
    assert r.status_code == 200
    detail = r.json()
    assert Decimal(detail["cash"]) == Decimal("500")
    assert len(detail["open_positions"]) == 1

    # Sell
    r = client.post(f"/api/paper/portfolios/{pid}/trade", json={
        "symbol": "API", "side": "sell", "quantity": "5",
        "submitted_at": (BASE_TS + dt.timedelta(days=1)).isoformat(),
    })
    assert r.status_code == 201
    assert Decimal(r.json()["realized_pnl"]) == Decimal("100")

    # Trades listed
    r = client.get(f"/api/paper/portfolios/{pid}/trades")
    assert r.status_code == 200
    trades = r.json()
    assert trades["count"] == 2
    assert trades["counts"]["wins"] == 1


def test_api_snapshot_and_equity_curve(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    client = TestClient(app)
    r = client.post("/api/paper/portfolios", json={
        "name": "eq-curve-test", "starting_cash": "1000",
    })
    pid = r.json()["id"]
    r = client.post(f"/api/paper/portfolios/{pid}/snapshot")
    assert r.status_code == 201
    r = client.get(f"/api/paper/portfolios/{pid}/equity")
    assert r.status_code == 200
    body = r.json()
    assert "current" in body
    assert "curve" in body
    assert len(body["curve"]) == 1
