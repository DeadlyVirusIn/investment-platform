"""Unit tests: cost_model + portfolio_sizer + exit_rules (pure functions)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from apps.api.src.domain.stock_engine.portfolio.cost_model import (
    MIN_SLIPPAGE_BPS,
    apply_cost,
    compute_slippage_bps,
    cost_for_trade,
)
from apps.api.src.domain.stock_engine.portfolio.exit_rules import (
    MAX_HOLDING_DAYS,
    STOP_LOSS_PCT,
    PositionView,
    RegimeView,
    evaluate_exits,
)
from apps.api.src.domain.stock_engine.portfolio.portfolio_sizer import (
    MAX_POSITIONS,
    MAX_POSITION_PCT,
    MAX_SECTOR_PCT,
    SizingInput,
    size_positions,
)


# ---------------------------------------------------------------------------
# cost_model
# ---------------------------------------------------------------------------


def test_compute_slippage_min_floor() -> None:
    slip, spread, impact = compute_slippage_bps(
        close=Decimal("100"), high=Decimal("100"), low=Decimal("100"),
        trade_notional=Decimal("100"), avg_dollar_volume=Decimal("1000000000"),
    )
    # Flat bar + deep ADV → formula ≈ 0; floor kicks in
    assert slip == MIN_SLIPPAGE_BPS
    assert spread == Decimal("0")


def test_compute_slippage_scales_with_spread() -> None:
    slip, spread, _ = compute_slippage_bps(
        close=Decimal("100"), high=Decimal("104"), low=Decimal("96"),
        trade_notional=Decimal("1000"),
        avg_dollar_volume=Decimal("10000000000"),
    )
    # spread_bps_proxy = 10000 * 8 / 100 / 4 = 200; slip ≈ max(2, 0.5*200) ≈ 100
    assert spread == Decimal("200")
    assert abs(slip - Decimal("100")) < Decimal("0.01")


def test_compute_slippage_impact_component() -> None:
    slip, _, impact = compute_slippage_bps(
        close=Decimal("100"), high=Decimal("100.5"), low=Decimal("99.5"),
        trade_notional=Decimal("1000000"),
        avg_dollar_volume=Decimal("1000000"),
    )
    # impact_bps = 10000 * 1e6 / (1e6 * 10) = 1000
    assert impact == Decimal("1000")
    assert slip > Decimal("500")


def test_compute_slippage_unknown_adv_skips_impact() -> None:
    slip, _, impact = compute_slippage_bps(
        close=Decimal("100"), high=Decimal("101"), low=Decimal("99"),
        trade_notional=Decimal("10000"),
        avg_dollar_volume=None,
    )
    assert impact == Decimal("0")
    assert slip >= MIN_SLIPPAGE_BPS


def test_apply_cost_buy_vs_sell_sign() -> None:
    buy = apply_cost(quote_price=Decimal("100"), side="buy",
                     slippage_bps=Decimal("50"))
    sell = apply_cost(quote_price=Decimal("100"), side="sell",
                      slippage_bps=Decimal("50"))
    assert buy > Decimal("100")
    assert sell < Decimal("100")
    assert buy - Decimal("100") == Decimal("100") - sell


def test_cost_for_trade_builds_result() -> None:
    r = cost_for_trade(
        side="buy",
        quote_price=Decimal("100"),
        high=Decimal("101"), low=Decimal("99"),
        trade_notional=Decimal("10000"),
        avg_dollar_volume=Decimal("1000000000"),
    )
    assert r.slippage_bps >= MIN_SLIPPAGE_BPS
    assert r.fill_price > Decimal("100")
    assert r.commission == Decimal("0")


# ---------------------------------------------------------------------------
# portfolio_sizer
# ---------------------------------------------------------------------------


def _cand(aid: str, composite: str, confidence: str, sector: str = "tech") -> SizingInput:
    return SizingInput(
        asset_id=aid,
        composite_score=Decimal(composite),
        confidence=Decimal(confidence),
        sector=sector,
    )


def test_sizer_empty_returns_empty() -> None:
    r = size_positions([])
    assert r.target_weights == {}
    assert r.sector_totals == {}


def test_sizer_base_weight_times_confidence() -> None:
    r = size_positions([_cand("a", "0.5", "70")])
    # base = 0.1; conf 70/100 → 0.07
    assert r.target_weights["a"] == Decimal("0.07")


def test_sizer_clamps_to_max_position_pct() -> None:
    # With base_weight=0.10 the formula alone can't exceed 0.10 at conf=100,
    # so use a smaller max_positions to force above cap.
    r = size_positions(
        [_cand("a", "0.9", "100")],
        max_positions=2,                  # base_weight = 0.50
        max_position_pct=Decimal("0.30"),
    )
    assert r.target_weights["a"] == MAX_POSITION_PCT


def test_sizer_drops_beyond_max_positions() -> None:
    cands = [_cand(f"a{i}", "0.5", "70") for i in range(15)]
    r = size_positions(cands, max_positions=10)
    assert len(r.target_weights) == 10
    dropped_ids = {aid for aid, _ in r.dropped}
    assert len(dropped_ids) == 5


def test_sizer_sector_cap_rescales() -> None:
    # 8 tech candidates at conf=100 → tech weight = 0.80; cap=0.50 → rescale
    cands = [_cand(f"t{i}", "0.5", "100", sector="tech") for i in range(8)]
    r = size_positions(cands, max_sector_pct=Decimal("0.50"))
    assert abs(r.sector_totals["tech"] - Decimal("0.50")) < Decimal("0.000001")


def test_sizer_respects_composite_order_for_tiebreak() -> None:
    cands = [
        _cand("low", "0.1", "70"),
        _cand("high", "0.9", "70"),
        _cand("mid", "0.5", "70"),
    ]
    r = size_positions(cands, max_positions=2)
    assert "high" in r.target_weights
    assert "mid" in r.target_weights
    assert "low" not in r.target_weights


def test_sizer_zero_confidence_dropped() -> None:
    r = size_positions([_cand("z", "0.5", "0")])
    assert "z" not in r.target_weights
    assert ("z", "zero_weight") in r.dropped


# ---------------------------------------------------------------------------
# exit_rules
# ---------------------------------------------------------------------------


NOW = dt.datetime(2026, 4, 20, 13, 30, tzinfo=dt.timezone.utc)


def _pos(
    aid: str, avg_cost: str, opened_days_ago: int, qty: str = "10",
) -> PositionView:
    return PositionView(
        asset_id=aid,
        quantity=Decimal(qty),
        avg_cost=Decimal(avg_cost),
        opened_at=NOW - dt.timedelta(days=opened_days_ago),
    )


def test_exit_stop_loss_triggers() -> None:
    # avg 100, current 89 → pnl -11% ≤ -10%
    pos = _pos("a", "100", opened_days_ago=2)
    out = evaluate_exits(
        positions=[pos], prices_by_asset={"a": Decimal("89")},
        regime=RegimeView(market_trend="uptrend"),
        universe_asset_ids={"a"}, now=NOW,
    )
    assert len(out) == 1
    assert out[0].reason == "stop_loss"


def test_exit_horizon_triggers_after_max_days() -> None:
    pos = _pos("a", "100", opened_days_ago=MAX_HOLDING_DAYS)
    out = evaluate_exits(
        positions=[pos], prices_by_asset={"a": Decimal("100")},
        regime=RegimeView(market_trend="uptrend"),
        universe_asset_ids={"a"}, now=NOW,
    )
    assert out[0].reason == "horizon_exit"


def test_exit_downtrend_triggers_before_horizon() -> None:
    pos = _pos("a", "100", opened_days_ago=3)
    out = evaluate_exits(
        positions=[pos], prices_by_asset={"a": Decimal("100")},
        regime=RegimeView(market_trend="downtrend"),
        universe_asset_ids={"a"}, now=NOW,
    )
    assert out[0].reason == "regime_exit"


def test_exit_universe_leaves_last() -> None:
    pos = _pos("a", "100", opened_days_ago=3)
    out = evaluate_exits(
        positions=[pos], prices_by_asset={"a": Decimal("100")},
        regime=RegimeView(market_trend="uptrend"),
        universe_asset_ids=set(), now=NOW,
    )
    assert out[0].reason == "universe_exit"


def test_exit_no_reason_returns_empty() -> None:
    pos = _pos("a", "100", opened_days_ago=3)
    out = evaluate_exits(
        positions=[pos], prices_by_asset={"a": Decimal("101")},
        regime=RegimeView(market_trend="uptrend"),
        universe_asset_ids={"a"}, now=NOW,
    )
    assert out == []


def test_exit_stop_loss_wins_over_downtrend() -> None:
    pos = _pos("a", "100", opened_days_ago=3)
    out = evaluate_exits(
        positions=[pos], prices_by_asset={"a": Decimal("85")},
        regime=RegimeView(market_trend="downtrend"),
        universe_asset_ids={"a"}, now=NOW,
    )
    # stop_loss has priority
    assert out[0].reason == "stop_loss"
