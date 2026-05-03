"""Integration tests for the auto_trader + run_paper_trading job."""

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
    Recommendation,
)
from apps.api.src.domain.paper_trading.auto_trader import (
    AutoTradeConfig,
    auto_trade_portfolio,
    generate_decisions,
)
from apps.api.src.domain.paper_trading.paper_service import (
    PortfolioCreate,
    create_portfolio,
)
from apps.worker.src.jobs.run_paper_trading import run_paper_trading

pytestmark = pytest.mark.integration

BASE_TS = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _seed_asset_with_prices(
    pg_session: Session,
    symbol: str,
    n_bars: int = 40,
    open_price: Decimal = Decimal("100"),
    step: Decimal = Decimal("0"),
) -> str:
    asset = Asset(symbol=symbol, asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()
    for i in range(n_bars):
        p = open_price + step * Decimal(i)
        pg_session.add(PriceBar(
            asset_id=asset.id, timeframe="1d",
            ts=BASE_TS + dt.timedelta(days=i),
            open=p, high=p + Decimal("0.5"), low=p - Decimal("0.5"),
            close=p, adjusted_close=p, volume=1_000_000, provider="test",
        ))
    pg_session.commit()
    return asset.id


def _seed_recommendation(
    pg_session: Session,
    asset_id: str,
    action: str,
    conviction: Decimal,
    snap: str,
    offset_days_ago: int = 0,
) -> str:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    rec = Recommendation(
        asset_id=asset_id, action=action, conviction=conviction,
        model_version="0.1.0", snapshot_hash=snap,
        rationale='{"snapshot_hash":"' + snap + '"}',
        generated_at=now - dt.timedelta(days=offset_days_ago),
    )
    pg_session.add(rec)
    pg_session.flush()
    pg_session.commit()
    return rec.id


def _active_portfolio(pg_session: Session, name: str, cash: str = "10000") -> PaperPortfolio:
    p = create_portfolio(pg_session, PortfolioCreate(name=name, starting_cash=Decimal(cash)))
    pg_session.commit()
    return p


# ---------------------------------------------------------------------------
# Decision rules
# ---------------------------------------------------------------------------


def test_high_confidence_buy_produces_open_buy(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(pg_session, "BUY1")
    _seed_recommendation(pg_session, asset_id, "Buy", Decimal("70"), "s1")
    p = _active_portfolio(pg_session, "ct-buy")

    decisions = generate_decisions(
        pg_session, p, AutoTradeConfig(buy_confidence_threshold=Decimal("60")),
        now=BASE_TS,
    )
    assert len(decisions) == 1
    d = decisions[0]
    assert d.kind == "open_buy"
    assert d.asset_id == asset_id
    assert d.usd_amount == Decimal("1000.00")  # 10% of 10000


def test_low_confidence_buy_is_skipped(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(pg_session, "LOWC")
    _seed_recommendation(pg_session, asset_id, "Buy", Decimal("40"), "s2")
    p = _active_portfolio(pg_session, "ct-low")

    decisions = generate_decisions(
        pg_session, p, AutoTradeConfig(buy_confidence_threshold=Decimal("60")),
        now=BASE_TS,
    )
    assert decisions == []


def test_already_held_asset_skipped(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(pg_session, "HELD")
    _seed_recommendation(pg_session, asset_id, "Buy", Decimal("80"), "s3")
    p = _active_portfolio(pg_session, "ct-held")
    pg_session.add(PaperPosition(
        portfolio_id=p.id, asset_id=asset_id,
        quantity=Decimal("1"), avg_cost=Decimal("100"),
        is_open=True, opened_at=BASE_TS,
    ))
    pg_session.commit()

    decisions = generate_decisions(pg_session, p, AutoTradeConfig(), now=BASE_TS)
    assert all(d.asset_id != asset_id or d.kind == "close_sell" for d in decisions)
    # Only valid close condition: sell rec or max hold; neither applies → empty.
    assert decisions == []


def test_max_open_positions_caps_buys(pg_session: Session) -> None:
    p = create_portfolio(
        pg_session,
        PortfolioCreate(name="ct-cap", starting_cash=Decimal("100000"), max_open_positions=2),
    )
    pg_session.commit()
    # 3 buy recs
    for i, sym in enumerate(["M1", "M2", "M3"]):
        aid = _seed_asset_with_prices(pg_session, sym)
        _seed_recommendation(pg_session, aid, "Buy", Decimal("80"), f"cap{i}")

    decisions = generate_decisions(pg_session, p, AutoTradeConfig(), now=BASE_TS)
    buys = [d for d in decisions if d.kind == "open_buy"]
    assert len(buys) == 2


def test_max_holding_days_forces_sell(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(pg_session, "OLD")
    p = _active_portfolio(pg_session, "ct-old")
    # Position opened 35 days before "now"
    now = BASE_TS + dt.timedelta(days=35)
    pg_session.add(PaperPosition(
        portfolio_id=p.id, asset_id=asset_id,
        quantity=Decimal("2"), avg_cost=Decimal("100"),
        is_open=True, opened_at=BASE_TS,
    ))
    pg_session.commit()

    decisions = generate_decisions(
        pg_session, p, AutoTradeConfig(max_holding_days=30), now=now,
    )
    sells = [d for d in decisions if d.kind == "close_sell"]
    assert len(sells) == 1
    assert "max_holding_days" in sells[0].reason
    assert sells[0].quantity == Decimal("2")


def test_rec_flip_to_sell_triggers_exit(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(pg_session, "FLP")
    p = _active_portfolio(pg_session, "ct-flip")
    pg_session.add(PaperPosition(
        portfolio_id=p.id, asset_id=asset_id,
        quantity=Decimal("3"), avg_cost=Decimal("100"),
        is_open=True, opened_at=BASE_TS + dt.timedelta(days=5),
    ))
    pg_session.commit()
    _seed_recommendation(pg_session, asset_id, "Sell", Decimal("50"), "flip1")

    decisions = generate_decisions(
        pg_session, p, AutoTradeConfig(),
        now=BASE_TS + dt.timedelta(days=10),
    )
    sells = [d for d in decisions if d.kind == "close_sell"]
    assert len(sells) == 1
    assert "flipped to Sell" in sells[0].reason


def test_rec_trim_also_triggers_exit(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(pg_session, "TRM")
    p = _active_portfolio(pg_session, "ct-trim")
    pg_session.add(PaperPosition(
        portfolio_id=p.id, asset_id=asset_id,
        quantity=Decimal("2"), avg_cost=Decimal("100"),
        is_open=True, opened_at=BASE_TS + dt.timedelta(days=5),
    ))
    pg_session.commit()
    _seed_recommendation(pg_session, asset_id, "Trim", Decimal("50"), "trim1")

    decisions = generate_decisions(
        pg_session, p, AutoTradeConfig(),
        now=BASE_TS + dt.timedelta(days=10),
    )
    assert any(d.kind == "close_sell" for d in decisions)


# ---------------------------------------------------------------------------
# Execution path
# ---------------------------------------------------------------------------


def test_auto_trade_portfolio_executes_buy_end_to_end(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(pg_session, "EXE")
    _seed_recommendation(pg_session, asset_id, "Buy", Decimal("75"), "exe1")
    p = _active_portfolio(pg_session, "ct-exe")

    result = auto_trade_portfolio(pg_session, p, AutoTradeConfig(), now=BASE_TS)
    pg_session.commit()

    assert len(result.executed) == 1
    trades = list(pg_session.scalars(
        select(PaperTrade).where(PaperTrade.portfolio_id == p.id)
    ))
    assert len(trades) == 1
    assert trades[0].side == "buy"
    assert trades[0].recommendation_id is not None
    assert "auto_trader" in (trades[0].reason or "")


def test_buy_and_sell_full_round_trip(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "RND", n_bars=40, open_price=Decimal("100"), step=Decimal("1"),
    )
    # Buy rec is "older"; Sell rec placed AFTER with explicit later timestamp.
    _seed_recommendation(
        pg_session, asset_id, "Buy", Decimal("80"), "rnd1", offset_days_ago=10,
    )
    p = _active_portfolio(pg_session, "ct-rt")

    res_buy = auto_trade_portfolio(pg_session, p, AutoTradeConfig(), now=BASE_TS)
    pg_session.commit()
    assert len(res_buy.executed) == 1

    # Flip recommendation to Sell (offset=0 → clearly newer than Buy@10d ago)
    _seed_recommendation(
        pg_session, asset_id, "Sell", Decimal("50"), "rnd2", offset_days_ago=0,
    )
    res_sell = auto_trade_portfolio(
        pg_session, p, AutoTradeConfig(),
        now=BASE_TS + dt.timedelta(days=5),
    )
    pg_session.commit()
    assert len(res_sell.executed) == 1

    open_pos = list(pg_session.scalars(
        select(PaperPosition).where(
            PaperPosition.portfolio_id == p.id,
            PaperPosition.is_open.is_(True),
        )
    ))
    assert open_pos == []


def _seed_asset_with_future_prices(
    pg_session: Session,
    symbol: str,
    n_bars: int = 10,
    open_price: Decimal = Decimal("100"),
) -> str:
    """Seed a price series starting from `now - 1 day` so real-time jobs can fill."""
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    start = now - dt.timedelta(days=1)
    asset = Asset(symbol=symbol, asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()
    for i in range(n_bars):
        p = open_price
        pg_session.add(PriceBar(
            asset_id=asset.id, timeframe="1d",
            ts=start + dt.timedelta(days=i),
            open=p, high=p + Decimal("0.5"), low=p - Decimal("0.5"),
            close=p, adjusted_close=p, volume=1_000_000, provider="test",
        ))
    pg_session.commit()
    return asset.id


def test_run_paper_trading_job_snapshots_equity(pg_session: Session) -> None:
    asset_id = _seed_asset_with_future_prices(pg_session, "JOB")
    _seed_recommendation(pg_session, asset_id, "Buy", Decimal("70"), "job1")
    _active_portfolio(pg_session, "ct-job")

    import asyncio
    asyncio.run(run_paper_trading())

    from apps.api.src.db.models import PaperEquitySnapshot
    pg_session.expire_all()
    snaps = list(pg_session.scalars(select(PaperEquitySnapshot)))
    assert len(snaps) == 1


def test_run_paper_trading_job_idempotent(pg_session: Session) -> None:
    asset_id = _seed_asset_with_future_prices(pg_session, "IDEM")
    _seed_recommendation(pg_session, asset_id, "Buy", Decimal("75"), "idem1")
    _active_portfolio(pg_session, "ct-idem")

    import asyncio
    asyncio.run(run_paper_trading())
    asyncio.run(run_paper_trading())
    pg_session.expire_all()

    # Same-day equity snapshot upserts → still one row
    from apps.api.src.db.models import PaperEquitySnapshot
    snaps = list(pg_session.scalars(select(PaperEquitySnapshot)))
    assert len(snaps) == 1
    # Second run should skip the buy (already holding → no new rec → no new trade)
    trades = list(pg_session.scalars(select(PaperTrade)))
    assert len(trades) == 1


# ---------------------------------------------------------------------------
# Validation fields on API
# ---------------------------------------------------------------------------


def test_portfolio_detail_includes_validation(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    asset_id = _seed_asset_with_prices(
        pg_session, "VAL", n_bars=10,
        open_price=Decimal("100"), step=Decimal("1"),
    )
    p = _active_portfolio(pg_session, "ct-val")

    client = TestClient(app)
    # Snapshot twice at different dates to build a curve → drawdown math
    # runs. First snapshot now, second after manually shifted date.
    from apps.api.src.db.models import PaperEquitySnapshot
    pg_session.add(PaperEquitySnapshot(
        portfolio_id=p.id,
        snapshot_date=BASE_TS,
        cash=Decimal("1200"),
        positions_value=Decimal("0"),
        total_equity=Decimal("1200"),
        unrealized_pnl=Decimal("0"),
        realized_pnl_cumulative=Decimal("0"),
    ))
    pg_session.add(PaperEquitySnapshot(
        portfolio_id=p.id,
        snapshot_date=BASE_TS + dt.timedelta(days=3),
        cash=Decimal("1000"),
        positions_value=Decimal("0"),
        total_equity=Decimal("1000"),
        unrealized_pnl=Decimal("0"),
        realized_pnl_cumulative=Decimal("0"),
    ))
    pg_session.commit()

    resp = client.get(f"/api/paper/portfolios/{p.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "validation" in data
    dd = data["validation"]["drawdown"]
    assert dd["max_drawdown_pct"] is not None
    # (1000 - 1200) / 1200 = -0.1666...
    assert Decimal(dd["max_drawdown_pct"]) < Decimal("0")
    assert dd["max_drawdown_duration_days"] == 3

    # Confidence validation block always present
    assert "confidence_validation" in data["validation"]
    labels = [b["bucket"] for b in data["validation"]["confidence_validation"]]
    assert labels == ["Low (0-30)", "Medium (30-60)", "High (60-100)", "Unknown"]
