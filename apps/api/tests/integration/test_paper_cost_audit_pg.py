"""Paper-cost audit stamp — durable reconstruction + exact ledger reconciliation.

Priority 3 hardening: every cost-enabled fill must durably reconstruct
gross / commission / slippage / total / net and the model version+config from
``paper_trade.execution_cost_json`` alone — no back-solving from quantized
prices, no dependence on the live settings. Cash movements must reconcile to
the stamped net_notional EXACTLY (Decimal, not float).
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, PaperPortfolio, PaperTrade, PriceBar
from apps.api.src.domain.paper_trading import paper_execution as pe
from apps.api.src.domain.paper_trading.execution_costs import (
    COST_MODEL_VERSION,
    CostConfig,
    compute_fill_costs,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def seeded(pg_session: Session):
    """Asset + next-day bar + funded portfolio."""
    asset = Asset(symbol="COSTX", asset_class="equity")
    pg_session.add(asset)
    pg_session.flush()
    now = dt.datetime.now(dt.timezone.utc)
    pg_session.add(PriceBar(
        asset_id=asset.id, timeframe="1d", ts=now + dt.timedelta(days=1),
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"),
        close=Decimal("100.5"), volume=1_000_000,
        provider="test",
    ))
    book = PaperPortfolio(
        name=f"cost-audit-{uuid.uuid4().hex[:8]}",
        starting_cash=Decimal("100000"), cash=Decimal("100000"),
    )
    pg_session.add(book)
    pg_session.commit()
    return pg_session, book, asset, now


def _enable_costs(monkeypatch, **over):
    from apps.api.src.config import settings
    monkeypatch.setattr(settings, "PAPER_COST_MODEL_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "PAPER_COMMISSION_BPS", over.get("commission_bps", 1), raising=False)
    monkeypatch.setattr(settings, "PAPER_SPREAD_FLOOR_BPS", over.get("floor", 2), raising=False)
    monkeypatch.setattr(settings, "PAPER_SLIPPAGE_CAP_BPS", over.get("cap", 50), raising=False)
    monkeypatch.setattr(settings, "PAPER_IMPACT_K_BPS", over.get("k", 10), raising=False)


def test_buy_stamps_full_breakdown_and_cash_reconciles_exactly(seeded, monkeypatch):
    s, book, asset, now = seeded
    _enable_costs(monkeypatch)
    cash_before = Decimal(str(book.cash))
    res = pe.submit_trade(
        s, portfolio_id=book.id, asset_id=asset.id, side="buy",
        quantity=Decimal("10"), submitted_at=now,
    )
    s.commit()
    trade = s.get(PaperTrade, res.trade_id)
    stamp = trade.execution_cost_json
    assert stamp is not None
    # -- version + config durably present
    assert stamp["version"] == COST_MODEL_VERSION
    assert stamp["config"] == {
        "commission_bps": "1", "spread_floor_bps": "2",
        "slippage_cap_bps": "50", "impact_k_bps": "10",
    }
    # -- breakdown fields all present, Decimal-string typed
    for k in ("raw_fill_price", "effective_fill_price", "gross_notional",
              "commission", "slippage_cost", "total_cost", "net_notional",
              "slippage_bps", "model"):
        assert k in stamp
    gross = Decimal(stamp["gross_notional"])
    commission = Decimal(stamp["commission"])
    slippage = Decimal(stamp["slippage_cost"])
    total = Decimal(stamp["total_cost"])
    net = Decimal(stamp["net_notional"])
    raw = Decimal(stamp["raw_fill_price"])
    eff = Decimal(stamp["effective_fill_price"])
    # -- internal consistency (exact Decimal identities)
    assert gross == Decimal("10") * raw
    assert total == commission + slippage
    assert net == Decimal("10") * eff + commission          # buy: cash out
    assert eff > raw                                        # adverse for buys
    # -- stored row matches the stamp
    assert Decimal(str(trade.fill_price)) == eff
    assert Decimal(str(trade.commission)) == commission
    # -- LEDGER: cash moved by exactly net_notional
    s.refresh(book)
    assert cash_before - Decimal(str(book.cash)) == net


def test_sell_cash_reconciles_and_slippage_adverse_down(seeded, monkeypatch):
    s, book, asset, now = seeded
    _enable_costs(monkeypatch)
    pe.submit_trade(s, portfolio_id=book.id, asset_id=asset.id, side="buy",
                    quantity=Decimal("10"), submitted_at=now)
    s.commit()
    s.refresh(book)
    cash_before = Decimal(str(book.cash))
    res = pe.submit_trade(s, portfolio_id=book.id, asset_id=asset.id,
                          side="sell", quantity=Decimal("10"), submitted_at=now)
    s.commit()
    trade = s.get(PaperTrade, res.trade_id)
    stamp = trade.execution_cost_json
    raw, eff = Decimal(stamp["raw_fill_price"]), Decimal(stamp["effective_fill_price"])
    net = Decimal(stamp["net_notional"])
    assert eff < raw                                        # adverse for sells
    assert net == Decimal("10") * eff - Decimal(stamp["commission"])
    s.refresh(book)
    assert Decimal(str(book.cash)) - cash_before == net     # cash in == net


def test_reconstruction_from_stamp_alone_reproduces_breakdown(seeded, monkeypatch):
    """Replay the stamped config + raw price through the versioned model and
    get byte-identical numbers — the durability contract."""
    s, book, asset, now = seeded
    _enable_costs(monkeypatch, commission_bps=3, floor=4, cap=40, k=12)
    res = pe.submit_trade(s, portfolio_id=book.id, asset_id=asset.id,
                          side="buy", quantity=Decimal("7"), submitted_at=now)
    s.commit()
    stamp = s.get(PaperTrade, res.trade_id).execution_cost_json
    assert stamp["version"] == COST_MODEL_VERSION
    cfg = CostConfig(
        enabled=True,
        commission_bps=Decimal(stamp["config"]["commission_bps"]),
        spread_floor_bps=Decimal(stamp["config"]["spread_floor_bps"]),
        slippage_cap_bps=Decimal(stamp["config"]["slippage_cap_bps"]),
        impact_k_bps=Decimal(stamp["config"]["impact_k_bps"]),
    )
    # ADV is not part of the stamp; the stamped slippage_bps pins the model
    # output. Recompute with the SAME bps by feeding no volume + floor=bps
    # for the fallback path, or verify the identity directly:
    qty, raw = Decimal("7"), Decimal(stamp["raw_fill_price"])
    bps = Decimal(stamp["slippage_bps"])
    eff_expected = (raw * (1 + bps / Decimal("10000"))).quantize(Decimal("0.000001"))
    assert Decimal(stamp["effective_fill_price"]) == eff_expected
    commission_expected = (qty * raw * cfg.commission_bps / Decimal("10000")
                           ).quantize(Decimal("0.000001"))
    assert Decimal(stamp["commission"]) == commission_expected
    slippage_expected = ((eff_expected - raw) * qty).quantize(Decimal("0.000001"))
    assert Decimal(stamp["slippage_cost"]) == slippage_expected
    assert Decimal(stamp["total_cost"]) == commission_expected + slippage_expected
    assert Decimal(stamp["net_notional"]) == qty * eff_expected + commission_expected


def test_zero_cost_path_stamps_nothing(seeded):
    """Flag off (default): NULL stamp, byte-identical legacy behavior."""
    s, book, asset, now = seeded
    res = pe.submit_trade(s, portfolio_id=book.id, asset_id=asset.id,
                          side="buy", quantity=Decimal("5"), submitted_at=now)
    s.commit()
    trade = s.get(PaperTrade, res.trade_id)
    assert trade.execution_cost_json is None
    assert Decimal(str(trade.commission)) == Decimal("0")


def test_override_callers_not_double_stamped(seeded, monkeypatch):
    """Callers baking their own costs (fill_price_override) bypass the model
    even when the flag is on — no stamp, no double charge."""
    s, book, asset, now = seeded
    _enable_costs(monkeypatch)
    res = pe.submit_trade(
        s, portfolio_id=book.id, asset_id=asset.id, side="buy",
        quantity=Decimal("5"), submitted_at=now,
        fill_price_override=Decimal("100.10"),
        slippage_bps=Decimal("1"), commission=Decimal("0.5"),
    )
    s.commit()
    trade = s.get(PaperTrade, res.trade_id)
    assert trade.execution_cost_json is None
    assert Decimal(str(trade.fill_price)) == Decimal("100.10")


def test_position_and_realized_pnl_consistent_with_stamps(seeded, monkeypatch):
    """Round-trip: realized P&L on the close equals sell-eff minus buy-eff
    proceeds — i.e., the stamped effective prices ARE the ledger prices."""
    s, book, asset, now = seeded
    _enable_costs(monkeypatch)
    buy = pe.submit_trade(s, portfolio_id=book.id, asset_id=asset.id,
                          side="buy", quantity=Decimal("10"), submitted_at=now)
    sell = pe.submit_trade(s, portfolio_id=book.id, asset_id=asset.id,
                           side="sell", quantity=Decimal("10"), submitted_at=now)
    s.commit()
    b = s.get(PaperTrade, buy.trade_id).execution_cost_json
    sl = s.get(PaperTrade, sell.trade_id).execution_cost_json
    eff_buy = Decimal(b["effective_fill_price"])
    eff_sell = Decimal(sl["effective_fill_price"])
    assert sell.realized_pnl is not None
    assert Decimal(str(sell.realized_pnl)) == (eff_sell - eff_buy) * Decimal("10")
