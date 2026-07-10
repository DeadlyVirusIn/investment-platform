"""Integration tests — Priority 3 honest paper execution costs (pg).

Proves:
  * flag OFF (default) → fills byte-identical to legacy zero-cost path
    (fill price, cash, commission=0, slippage_bps NULL);
  * flag ON → non-negative costs, slippage always adverse (buys fill at or
    above bar open, sells at or below), floor/cap behaviour, deterministic
    fallback when dollar-volume data is missing, reproducibility, and full
    ledger reconciliation (cash delta == net notional; avg_cost == net fill).

Mirrors the seeding conventions of test_paper_trading_pg.py.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db.models import Asset, PaperPosition, PaperTrade, PriceBar
from apps.api.src.domain.paper_trading.execution_costs import (
    CostConfig,
    avg_dollar_volume_for_asset,
    compute_fill_costs,
)
from apps.api.src.domain.paper_trading.paper_execution import submit_trade
from apps.api.src.domain.paper_trading.paper_service import (
    PortfolioCreate,
    create_portfolio,
)

pytestmark = pytest.mark.integration

BASE_TS = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def _seed_asset_with_prices(
    pg_session: Session,
    symbol: str,
    closes: list[str],
    opens: list[str] | None = None,
    volume: int | None = 1_000_000,
    start_ts: dt.datetime = BASE_TS,
) -> str:
    """Same shape as test_paper_trading_pg._seed_asset_with_prices, plus a
    ``volume`` knob (None → no dollar-volume data → cost-model fallback)."""
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
            volume=volume,
            provider="test",
        ))
    pg_session.commit()
    return asset.id


@pytest.fixture
def costs_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PAPER_COST_MODEL_ENABLED", True)


@pytest.fixture
def costs_on_with_commission(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PAPER_COST_MODEL_ENABLED", True)
    monkeypatch.setattr(settings, "PAPER_COMMISSION_BPS", 5.0)


def _trade_row(pg_session: Session, trade_id: str) -> PaperTrade:
    row = pg_session.get(PaperTrade, trade_id)
    assert row is not None
    return row


# ---------------------------------------------------------------------------
# Zero-cost parity: flag OFF (default) must be byte-identical to legacy
# ---------------------------------------------------------------------------


def test_flag_off_buy_sell_byte_identical_to_legacy(pg_session: Session) -> None:
    assert settings.PAPER_COST_MODEL_ENABLED is False  # default-off contract
    asset_id = _seed_asset_with_prices(
        pg_session, "OFF1",
        closes=["100", "100", "120"],
        opens=["100", "100", "120"],
    )
    p = create_portfolio(pg_session, PortfolioCreate(name="off-parity", starting_cash=Decimal("1000")))
    pg_session.commit()

    buy = submit_trade(
        pg_session, portfolio_id=p.id, asset_id=asset_id,
        side="buy", quantity=Decimal("5"), submitted_at=BASE_TS,
    )
    pg_session.commit()
    # Legacy expected values (mirrors test_paper_trading_pg exactly)
    assert buy.fill_price == Decimal("100")
    assert buy.fill_ts == BASE_TS + dt.timedelta(days=1)
    assert buy.cash_after == Decimal("500")
    assert buy.costs is None
    row = _trade_row(pg_session, buy.trade_id)
    assert Decimal(str(row.commission)) == Decimal("0")
    assert row.slippage_bps is None

    sell = submit_trade(
        pg_session, portfolio_id=p.id, asset_id=asset_id,
        side="sell", quantity=Decimal("5"),
        submitted_at=BASE_TS + dt.timedelta(days=1),
    )
    pg_session.commit()
    assert sell.fill_price == Decimal("120")
    assert sell.cash_after == Decimal("1100")
    assert sell.realized_pnl == Decimal("100")
    assert sell.costs is None
    row = _trade_row(pg_session, sell.trade_id)
    assert Decimal(str(row.commission)) == Decimal("0")
    assert row.slippage_bps is None

    pos = pg_session.scalar(select(PaperPosition).where(PaperPosition.portfolio_id == p.id))
    assert Decimal(str(pos.avg_cost)) == Decimal("100")


def test_flag_off_explicit_false_matches_default(
    pg_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "PAPER_COST_MODEL_ENABLED", False)
    asset_id = _seed_asset_with_prices(pg_session, "OFF2", closes=["50", "50"], opens=["50", "50"])
    p = create_portfolio(pg_session, PortfolioCreate(name="off-explicit", starting_cash=Decimal("1000")))
    pg_session.commit()
    res = submit_trade(
        pg_session, portfolio_id=p.id, asset_id=asset_id,
        side="buy", quantity=Decimal("2"), submitted_at=BASE_TS,
    )
    pg_session.commit()
    assert res.fill_price == Decimal("50")
    assert res.cash_after == Decimal("900")
    assert res.costs is None


# ---------------------------------------------------------------------------
# Flag ON: direction correctness + non-negative costs
# ---------------------------------------------------------------------------


def test_flag_on_buy_fills_above_open_sell_below(
    pg_session: Session, costs_on: None
) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "ADV1",
        closes=["100", "100", "100"],
        opens=["100", "100", "100"],
    )
    p = create_portfolio(pg_session, PortfolioCreate(name="adverse", starting_cash=Decimal("1000")))
    pg_session.commit()

    buy = submit_trade(
        pg_session, portfolio_id=p.id, asset_id=asset_id,
        side="buy", quantity=Decimal("2"), submitted_at=BASE_TS,
    )
    pg_session.commit()
    assert buy.costs is not None
    assert buy.fill_price >= Decimal("100")          # buys fill higher (adverse)
    assert buy.fill_price > Decimal("100")           # floor bps > 0 → strictly
    assert buy.costs.commission >= 0
    assert buy.costs.slippage >= 0
    assert buy.costs.total == buy.costs.commission + buy.costs.slippage
    assert buy.costs.gross_notional == Decimal("2") * Decimal("100")

    sell = submit_trade(
        pg_session, portfolio_id=p.id, asset_id=asset_id,
        side="sell", quantity=Decimal("2"),
        submitted_at=BASE_TS + dt.timedelta(days=1),
    )
    pg_session.commit()
    assert sell.costs is not None
    assert sell.fill_price <= Decimal("100")         # sells fill lower (adverse)
    assert sell.fill_price < Decimal("100")
    assert sell.costs.commission >= 0
    assert sell.costs.slippage >= 0

    # Round trip at a flat price must lose money (honest costs).
    assert sell.cash_after < Decimal("1000")


# ---------------------------------------------------------------------------
# Floor vs cap
# ---------------------------------------------------------------------------


def test_tiny_order_slippage_floor_applies(pg_session: Session, costs_on: None) -> None:
    # ADV = 1_000_000 vol × 100 close = 1e8; order 200 USD →
    # raw = 10 × sqrt(200/1e8) ≈ 0.0141 bps → floored at 2 bps.
    asset_id = _seed_asset_with_prices(
        pg_session, "TINY", closes=["100", "100"], opens=["100", "100"],
    )
    p = create_portfolio(pg_session, PortfolioCreate(name="tiny", starting_cash=Decimal("1000")))
    pg_session.commit()
    res = submit_trade(
        pg_session, portfolio_id=p.id, asset_id=asset_id,
        side="buy", quantity=Decimal("2"), submitted_at=BASE_TS,
    )
    pg_session.commit()
    assert res.costs is not None
    assert res.costs.model == "liquidity"
    assert res.costs.slippage_bps == Decimal("2")    # floor
    assert res.fill_price == Decimal("100.02")       # 100 × (1 + 2/10000)
    row = _trade_row(pg_session, res.trade_id)
    assert Decimal(str(row.slippage_bps)) == Decimal("2")


def test_large_order_slippage_cap_applies(pg_session: Session, costs_on: None) -> None:
    # ADV = 1 share × 100 = 100 USD; order 3000 USD →
    # raw = 10 × sqrt(3000/100) ≈ 54.77 bps → capped at 50 bps.
    asset_id = _seed_asset_with_prices(
        pg_session, "BIG", closes=["100", "100"], opens=["100", "100"], volume=1,
    )
    p = create_portfolio(pg_session, PortfolioCreate(name="big", starting_cash=Decimal("10000")))
    pg_session.commit()
    res = submit_trade(
        pg_session, portfolio_id=p.id, asset_id=asset_id,
        side="buy", quantity=Decimal("30"), submitted_at=BASE_TS,
    )
    pg_session.commit()
    assert res.costs is not None
    assert res.costs.model == "liquidity"
    assert res.costs.slippage_bps == Decimal("50")   # cap
    assert res.fill_price == Decimal("100.5")        # 100 × (1 + 50/10000)


# ---------------------------------------------------------------------------
# Missing dollar-volume data → deterministic fallback
# ---------------------------------------------------------------------------


def test_missing_avg_dollar_volume_uses_flat_fallback(
    pg_session: Session, costs_on: None
) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "NOVOL", closes=["100", "100"], opens=["100", "100"], volume=None,
    )
    assert avg_dollar_volume_for_asset(pg_session, asset_id, BASE_TS) is None
    p = create_portfolio(pg_session, PortfolioCreate(name="novol", starting_cash=Decimal("1000")))
    pg_session.commit()
    res = submit_trade(
        pg_session, portfolio_id=p.id, asset_id=asset_id,
        side="buy", quantity=Decimal("2"), submitted_at=BASE_TS,
    )
    pg_session.commit()
    assert res.costs is not None
    assert res.costs.model == "fallback"
    assert res.costs.slippage_bps == Decimal("2")    # flat PAPER_SPREAD_FLOOR_BPS
    assert res.fill_price == Decimal("100.02")       # deterministic value


# ---------------------------------------------------------------------------
# Reproducibility — same inputs twice → identical fills
# ---------------------------------------------------------------------------


def test_same_inputs_twice_identical_fills(pg_session: Session, costs_on_with_commission: None) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "REPRO", closes=["100", "100"], opens=["100", "100"],
    )
    results = []
    for name in ("repro-a", "repro-b"):
        p = create_portfolio(pg_session, PortfolioCreate(name=name, starting_cash=Decimal("1000")))
        pg_session.commit()
        res = submit_trade(
            pg_session, portfolio_id=p.id, asset_id=asset_id,
            side="buy", quantity=Decimal("3"), submitted_at=BASE_TS,
        )
        pg_session.commit()
        results.append(res)
    a, b = results
    assert a.fill_price == b.fill_price
    assert a.cash_after == b.cash_after
    assert a.costs == b.costs


# ---------------------------------------------------------------------------
# Ledger reconciliation — cash delta == net notional; avg_cost == net fill
# ---------------------------------------------------------------------------


def test_buy_ledger_cash_delta_equals_net_notional(
    pg_session: Session, costs_on_with_commission: None
) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "LEDG1", closes=["100", "100"], opens=["100", "100"],
    )
    p = create_portfolio(pg_session, PortfolioCreate(name="ledger-buy", starting_cash=Decimal("1000")))
    pg_session.commit()
    qty = Decimal("4")
    res = submit_trade(
        pg_session, portfolio_id=p.id, asset_id=asset_id,
        side="buy", quantity=qty, submitted_at=BASE_TS,
    )
    pg_session.commit()
    assert res.costs is not None
    assert res.costs.commission > 0                  # 5 bps of gross notional

    # Net price + commission from the persisted trade row (existing columns).
    row = _trade_row(pg_session, res.trade_id)
    net_price = Decimal(str(row.fill_price))
    commission = Decimal(str(row.commission))
    cash_delta = Decimal("1000") - res.cash_after
    assert cash_delta == qty * net_price + commission
    assert cash_delta == res.costs.net_notional

    # Position basis reflects the net (cost-adjusted) fill price.
    pos = pg_session.scalar(select(PaperPosition).where(PaperPosition.portfolio_id == p.id))
    assert Decimal(str(pos.avg_cost)) == net_price
    assert net_price == res.costs.effective_fill_price


def test_sell_ledger_cash_delta_equals_net_notional(
    pg_session: Session, costs_on_with_commission: None
) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "LEDG2", closes=["100", "100", "110"], opens=["100", "100", "110"],
    )
    p = create_portfolio(pg_session, PortfolioCreate(name="ledger-sell", starting_cash=Decimal("1000")))
    pg_session.commit()
    qty = Decimal("4")
    buy = submit_trade(
        pg_session, portfolio_id=p.id, asset_id=asset_id,
        side="buy", quantity=qty, submitted_at=BASE_TS,
    )
    pg_session.commit()
    sell = submit_trade(
        pg_session, portfolio_id=p.id, asset_id=asset_id,
        side="sell", quantity=qty, submitted_at=BASE_TS + dt.timedelta(days=1),
    )
    pg_session.commit()
    assert sell.costs is not None

    row = _trade_row(pg_session, sell.trade_id)
    net_price = Decimal(str(row.fill_price))
    commission = Decimal(str(row.commission))
    cash_delta = sell.cash_after - buy.cash_after
    assert cash_delta == qty * net_price - commission
    assert cash_delta == sell.costs.net_notional
    # Realized P&L is price-based (net fill vs net basis); commission is
    # carried on the trade row and in cash, keeping attribution separable.
    basis = Decimal(str(_trade_row(pg_session, buy.trade_id).fill_price))
    assert sell.realized_pnl == qty * (net_price - basis)


# ---------------------------------------------------------------------------
# Callers with their own cost model (fill_price_override) are untouched
# ---------------------------------------------------------------------------


def test_fill_price_override_bypasses_cost_model(
    pg_session: Session, costs_on_with_commission: None
) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "OVRD", closes=["100", "100"], opens=["100", "100"],
    )
    p = create_portfolio(pg_session, PortfolioCreate(name="override", starting_cash=Decimal("1000")))
    pg_session.commit()
    res = submit_trade(
        pg_session, portfolio_id=p.id, asset_id=asset_id,
        side="buy", quantity=Decimal("2"), submitted_at=BASE_TS,
        fill_price_override=Decimal("101.5"),
        slippage_bps=Decimal("15"), commission=Decimal("1.25"),
    )
    pg_session.commit()
    # Rebalance-style call keeps its own numbers; no double charge.
    assert res.costs is None
    assert res.fill_price == Decimal("101.5")
    assert res.cash_after == Decimal("1000") - Decimal("2") * Decimal("101.5")
    row = _trade_row(pg_session, res.trade_id)
    assert Decimal(str(row.commission)) == Decimal("1.25")
    assert Decimal(str(row.slippage_bps)) == Decimal("15")


# ---------------------------------------------------------------------------
# Pure-function checks (no DB): validation + non-negativity invariants
# ---------------------------------------------------------------------------


def test_compute_fill_costs_pure_invariants() -> None:
    cfg = CostConfig(
        enabled=True,
        commission_bps=Decimal("5"),
        spread_floor_bps=Decimal("2"),
        slippage_cap_bps=Decimal("50"),
        impact_k_bps=Decimal("10"),
    )
    buy = compute_fill_costs(
        "buy", Decimal("10"), Decimal("100"),
        avg_dollar_volume=Decimal("1000000"), config=cfg,
    )
    sell = compute_fill_costs(
        "sell", Decimal("10"), Decimal("100"),
        avg_dollar_volume=Decimal("1000000"), config=cfg,
    )
    assert buy.effective_fill_price > Decimal("100")
    assert sell.effective_fill_price < Decimal("100")
    # Symmetric adverse move for the same slippage bps.
    assert buy.slippage_bps == sell.slippage_bps
    assert buy.slippage == sell.slippage
    for b in (buy, sell):
        assert b.commission >= 0
        assert b.slippage >= 0
        assert b.total == b.commission + b.slippage
        assert b.net_notional >= 0
    # Buy pays more than gross; sell receives less than gross.
    assert buy.net_notional > buy.gross_notional
    assert sell.net_notional < sell.gross_notional

    with pytest.raises(ValueError, match="unknown side"):
        compute_fill_costs("short", Decimal("1"), Decimal("100"),
                           avg_dollar_volume=None, config=cfg)
    with pytest.raises(ValueError, match="quantity"):
        compute_fill_costs("buy", Decimal("0"), Decimal("100"),
                           avg_dollar_volume=None, config=cfg)
    with pytest.raises(ValueError, match="fill_price"):
        compute_fill_costs("buy", Decimal("1"), Decimal("0"),
                           avg_dollar_volume=None, config=cfg)


def test_compute_fill_costs_negative_config_clamped() -> None:
    cfg = CostConfig(
        enabled=True,
        commission_bps=Decimal("-5"),       # hostile config → clamped to 0
        spread_floor_bps=Decimal("-2"),
        slippage_cap_bps=Decimal("50"),
        impact_k_bps=Decimal("10"),
    )
    b = compute_fill_costs(
        "buy", Decimal("1"), Decimal("100"),
        avg_dollar_volume=None, config=cfg,
    )
    assert b.commission == 0
    assert b.slippage == 0
    assert b.slippage_bps == 0
    assert b.effective_fill_price == Decimal("100")
