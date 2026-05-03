"""Unit tests: eligibility gates + scoring + (pure) decision composition."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace

from apps.api.src.domain.stock_engine.eligibility import (
    ALL_REJECTION_REASONS,
    ORDERED_GATES,
    REJ_ALREADY_AT_CAP,
    REJ_BELOW_LONG_TREND,
    REJ_EARNINGS_TOO_CLOSE,
    REJ_IDIOSYNCRATIC_VOL,
    REJ_INSUFFICIENT_HISTORY,
    REJ_LIQUIDITY_FAIL,
    REJ_NOT_IN_UNIVERSE,
    REJ_REGIME_OFF,
    REJ_STALE_DATA,
    DecisionContext,
    PortfolioView,
    first_rejection_reason,
)
from apps.api.src.domain.stock_engine.scoring import (
    ACTION_THRESHOLDS,
    MODEL_VERSION,
    composite_score,
    map_action,
)


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


@dataclass
class FakeRegime:
    as_of_date: dt.date = dt.date(2026, 4, 17)
    benchmark_symbol: str = "SPY"
    market_trend: str = "uptrend"
    vol_regime: str = "normal"
    breadth_regime: str | None = None
    sma50_over_sma200: bool = True
    realized_vol_20d: Decimal = Decimal("0.14")
    atr_pctile_1y: Decimal = Decimal("0.40")


def _row(
    *,
    asset_id: str = "a1",
    enough_data: bool = True,
    stale_data: bool = False,
    avg_dollar_volume_20d: Decimal | None = Decimal("60000000"),
    earnings_proximity_days: int | None = None,
    price_vs_200sma: Decimal | None = Decimal("0.05"),
    atr_percent_14: Decimal | None = Decimal("0.02"),
    residual_momentum_60d: Decimal | None = Decimal("1.0"),
    residual_momentum_20d: Decimal | None = Decimal("0.5"),
    sector_relative_rank: Decimal | None = Decimal("0.7"),
    trend_strength_20d: Decimal | None = Decimal("1.0"),
):
    """Build a fake FactorSnapshot-shaped object with the fields gates read."""
    return SimpleNamespace(
        asset_id=asset_id,
        enough_data=enough_data,
        stale_data=stale_data,
        avg_dollar_volume_20d=avg_dollar_volume_20d,
        earnings_proximity_days=earnings_proximity_days,
        price_vs_200sma=price_vs_200sma,
        atr_percent_14=atr_percent_14,
        residual_momentum_60d=residual_momentum_60d,
        residual_momentum_20d=residual_momentum_20d,
        sector_relative_rank=sector_relative_rank,
        trend_strength_20d=trend_strength_20d,
    )


_UNSET = object()


def _ctx(
    *, regime=_UNSET,
    universe: set[str] | None = None,
    atr_p90: Decimal | None = Decimal("0.05"),
    portfolio: PortfolioView | None = None,
) -> DecisionContext:
    return DecisionContext(
        regime=FakeRegime() if regime is _UNSET else regime,
        universe_asset_ids=universe or {"a1", "a2", "a3"},
        atr_p90=atr_p90,
        portfolio=portfolio or PortfolioView(),
    )


# ---------------------------------------------------------------------------
# Gate order + vocabulary
# ---------------------------------------------------------------------------


def test_gate_order_matches_spec() -> None:
    reasons = [r for r, _ in ORDERED_GATES]
    assert reasons == [
        "regime_off",
        "not_in_universe",
        "insufficient_history",
        "stale_data",
        "liquidity_fail",
        "earnings_too_close",
        "below_long_trend",
        "idiosyncratic_vol_high",
        "already_at_cap",
    ]


def test_all_rejection_reasons_contains_downstream_values() -> None:
    assert "topn_overflow" in ALL_REJECTION_REASONS
    assert "high_vol_topn_overflow" in ALL_REJECTION_REASONS
    assert "job_error" in ALL_REJECTION_REASONS


# ---------------------------------------------------------------------------
# Individual gate behavior
# ---------------------------------------------------------------------------


def test_pass_all_gates_accepts() -> None:
    assert first_rejection_reason(_ctx(), _row()) is None


def test_gate_regime_off_when_downtrend() -> None:
    ctx = _ctx(regime=FakeRegime(market_trend="downtrend"))
    assert first_rejection_reason(ctx, _row()) == REJ_REGIME_OFF


def test_gate_does_not_reject_on_high_vol_alone() -> None:
    """High-vol is now a SOFT constraint handled at selection stage;
    gate layer must not reject on vol_regime='high' by itself."""
    ctx = _ctx(regime=FakeRegime(vol_regime="high"))
    assert first_rejection_reason(ctx, _row()) is None


def test_gate_regime_off_when_regime_missing() -> None:
    ctx = _ctx(regime=None)
    assert first_rejection_reason(ctx, _row()) == REJ_REGIME_OFF


def test_gate_not_in_universe() -> None:
    ctx = _ctx(universe={"other"})
    assert first_rejection_reason(ctx, _row(asset_id="a1")) == REJ_NOT_IN_UNIVERSE


def test_gate_insufficient_history_before_everything_data_dependent() -> None:
    row = _row(enough_data=False, avg_dollar_volume_20d=Decimal("1"))
    assert first_rejection_reason(_ctx(), row) == REJ_INSUFFICIENT_HISTORY


def test_gate_stale_data() -> None:
    row = _row(stale_data=True)
    assert first_rejection_reason(_ctx(), row) == REJ_STALE_DATA


def test_gate_liquidity_fail_below_threshold() -> None:
    row = _row(avg_dollar_volume_20d=Decimal("1000000"))
    assert first_rejection_reason(_ctx(), row) == REJ_LIQUIDITY_FAIL


def test_gate_liquidity_fail_when_null_volume() -> None:
    row = _row(avg_dollar_volume_20d=None)
    assert first_rejection_reason(_ctx(), row) == REJ_LIQUIDITY_FAIL


def test_gate_earnings_too_close() -> None:
    row = _row(earnings_proximity_days=3)
    assert first_rejection_reason(_ctx(), row) == REJ_EARNINGS_TOO_CLOSE


def test_gate_earnings_ok_when_far() -> None:
    row = _row(earnings_proximity_days=30)
    assert first_rejection_reason(_ctx(), row) is None


def test_gate_earnings_ok_when_null() -> None:
    row = _row(earnings_proximity_days=None)
    assert first_rejection_reason(_ctx(), row) is None


def test_gate_below_long_trend() -> None:
    row = _row(price_vs_200sma=Decimal("-0.08"))
    assert first_rejection_reason(_ctx(), row) == REJ_BELOW_LONG_TREND


def test_gate_below_long_trend_when_null() -> None:
    row = _row(price_vs_200sma=None)
    assert first_rejection_reason(_ctx(), row) == REJ_BELOW_LONG_TREND


def test_gate_idiosyncratic_vol_high() -> None:
    ctx = _ctx(atr_p90=Decimal("0.03"))
    row = _row(atr_percent_14=Decimal("0.05"))
    assert first_rejection_reason(ctx, row) == REJ_IDIOSYNCRATIC_VOL


def test_gate_vol_passes_when_p90_unknown() -> None:
    ctx = _ctx(atr_p90=None)
    row = _row(atr_percent_14=Decimal("1.0"))
    assert first_rejection_reason(ctx, row) is None


def test_gate_already_at_cap() -> None:
    pf = PortfolioView(weights_by_asset={"a1": 0.09})
    ctx = _ctx(portfolio=pf)
    assert first_rejection_reason(ctx, _row(asset_id="a1")) == REJ_ALREADY_AT_CAP


# ---------------------------------------------------------------------------
# Composite score math
# ---------------------------------------------------------------------------


def test_composite_zero_on_neutral_inputs() -> None:
    row = _row(
        residual_momentum_60d=Decimal("0"),
        residual_momentum_20d=Decimal("0"),
        sector_relative_rank=Decimal("0.5"),
        trend_strength_20d=Decimal("0"),
        atr_percent_14=Decimal("0.02"),
    )
    s = composite_score(row, Decimal("0.02"))
    assert s.composite == Decimal("0")
    assert s.action == "Hold"
    # confidence = 50 + 50*0 = 50
    assert s.confidence == Decimal("50")
    assert s.confidence_label == "Medium"


def test_composite_bullish_triggers_buy() -> None:
    # All bullish inputs → composite well above 0.25
    row = _row(
        residual_momentum_60d=Decimal("3"),
        residual_momentum_20d=Decimal("3"),
        sector_relative_rank=Decimal("1"),
        trend_strength_20d=Decimal("2"),
        atr_percent_14=Decimal("0.01"),
    )
    s = composite_score(row, Decimal("0.02"))
    assert s.composite > Decimal("0.5")
    assert s.action == "Buy"
    assert s.confidence_label in ("Medium", "High")


def test_composite_bearish_triggers_sell() -> None:
    row = _row(
        residual_momentum_60d=Decimal("-3"),
        residual_momentum_20d=Decimal("-3"),
        sector_relative_rank=Decimal("0"),
        trend_strength_20d=Decimal("-2"),
        atr_percent_14=Decimal("1.0"),
    )
    s = composite_score(row, Decimal("0.02"))
    assert s.composite <= Decimal(str(ACTION_THRESHOLDS["REDUCE"]))
    assert s.action == "Sell"


def test_composite_handles_missing_components() -> None:
    row = _row(
        residual_momentum_60d=None,
        residual_momentum_20d=None,
        sector_relative_rank=None,
        trend_strength_20d=None,
        atr_percent_14=None,
    )
    s = composite_score(row, None)
    assert s.composite is None
    assert s.action is None


def test_composite_partial_missing_yields_valid_score() -> None:
    row = _row(
        residual_momentum_60d=Decimal("1"),
        residual_momentum_20d=None,          # missing
        sector_relative_rank=Decimal("0.6"),
        trend_strength_20d=None,             # missing
        atr_percent_14=Decimal("0.02"),
    )
    s = composite_score(row, Decimal("0.02"))
    assert s.composite is not None
    assert "residual_momentum_20d" in s.missing_components
    assert "trend_strength_20d" in s.missing_components


def test_map_action_boundaries() -> None:
    assert map_action(0.25) == "Buy"
    assert map_action(0.24999) == "Hold"
    assert map_action(-0.25) == "Hold"
    assert map_action(-0.25001) == "Trim"
    assert map_action(-0.65) == "Trim"
    assert map_action(-0.66) == "Sell"


# ---------------------------------------------------------------------------
# Model version
# ---------------------------------------------------------------------------


def test_model_version_format() -> None:
    assert MODEL_VERSION.startswith("stock_swing_v1:")
    assert len(MODEL_VERSION.split(":")[1]) == 16
