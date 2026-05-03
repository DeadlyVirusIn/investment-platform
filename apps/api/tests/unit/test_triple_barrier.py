"""Triple-barrier outcome labeling — pure-function unit tests."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.api.src.domain.recommendations.outcome_labeling import (
    HORIZON_DEFAULT,
    HORIZON_MEAN_REVERSION,
    HORIZON_TREND,
    classify_signal_type,
    compute_sigma_from_returns,
    compute_sigma_t0,
    horizon_for_signal,
    realized_return_at,
    triple_barrier_label,
)


BASE_TS = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def _series(prices: list[float]) -> list[tuple[dt.datetime, Decimal]]:
    return [
        (BASE_TS + dt.timedelta(days=i), Decimal(str(p)))
        for i, p in enumerate(prices)
    ]


# ---------------------------------------------------------------------------
# Sigma
# ---------------------------------------------------------------------------


def test_sigma_from_returns_basic() -> None:
    # Returns: [0.1, -0.1, 0.1, -0.1, 0.1]
    rets = [Decimal("0.1"), Decimal("-0.1"), Decimal("0.1"), Decimal("-0.1"), Decimal("0.1")]
    sigma = compute_sigma_from_returns(rets)
    assert sigma is not None
    assert sigma > Decimal("0.09")
    assert sigma < Decimal("0.12")


def test_sigma_from_returns_insufficient() -> None:
    assert compute_sigma_from_returns([Decimal("0.1")]) is None
    assert compute_sigma_from_returns([]) is None


def test_sigma_t0_requires_lookback_plus_one() -> None:
    prices = [Decimal("100")] * 20
    # 20 constant prices → 19 zero returns → needs lookback+1 = 21
    assert compute_sigma_t0(prices, lookback=20) is None
    # 21 prices → 20 returns, all zero → sigma = 0
    sigma = compute_sigma_t0([Decimal("100")] * 21, lookback=20)
    assert sigma == Decimal("0")


# ---------------------------------------------------------------------------
# Triple-barrier core
# ---------------------------------------------------------------------------


def test_profit_target_hit_returns_plus_one() -> None:
    # Entry at day 0 price 100; sigma = 1%; pt=2 → +2% barrier = ret >= 0.02
    # Day 4 reaches 102 → +2% exactly → triggers
    prices = [100.0, 100.5, 101.0, 101.5, 102.0, 103.0, 103.5]
    series = _series(prices)
    sigma = Decimal("0.01")
    result = triple_barrier_label(
        series, BASE_TS, sigma,
        pt=Decimal("2"), sl=Decimal("2"), n_bars=6,
    )
    assert result is not None
    assert result.label == 1
    assert result.reason == "profit"
    assert result.first_touch_at == series[4][0]


def test_stop_loss_hit_returns_minus_one() -> None:
    prices = [100.0, 99.5, 99.0, 98.5, 98.0, 97.0, 96.5]
    series = _series(prices)
    sigma = Decimal("0.01")
    result = triple_barrier_label(
        series, BASE_TS, sigma,
        pt=Decimal("2"), sl=Decimal("2"), n_bars=6,
    )
    assert result is not None
    assert result.label == -1
    assert result.reason == "stop"


def test_neither_hit_horizon_uses_sign_of_terminal() -> None:
    # 1.5% gain at horizon, no 2% barrier touched
    prices = [100.0, 100.2, 100.5, 100.7, 101.0, 101.2, 101.5]
    series = _series(prices)
    sigma = Decimal("0.01")
    result = triple_barrier_label(
        series, BASE_TS, sigma,
        pt=Decimal("2"), sl=Decimal("2"), n_bars=6,
    )
    assert result is not None
    assert result.reason == "horizon"
    # Terminal positive → sign = +1
    assert result.label == 1


def test_horizon_flat_returns_zero() -> None:
    prices = [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    series = _series(prices)
    sigma = Decimal("0.01")
    result = triple_barrier_label(
        series, BASE_TS, sigma,
        pt=Decimal("2"), sl=Decimal("2"), n_bars=6,
    )
    assert result is not None
    assert result.reason == "horizon"
    assert result.label == 0


def test_both_barriers_hit_earlier_wins() -> None:
    # +2% on day 1, -5% on day 4 → up_hit day 1 wins
    prices = [100.0, 102.0, 105.0, 101.0, 95.0, 94.0]
    series = _series(prices)
    sigma = Decimal("0.01")
    result = triple_barrier_label(
        series, BASE_TS, sigma,
        pt=Decimal("2"), sl=Decimal("2"), n_bars=5,
    )
    assert result is not None
    assert result.label == 1
    assert result.first_touch_at == series[1][0]


def test_stop_hit_before_profit_returns_minus_one() -> None:
    # Day 1 hits -2% first; day 3 hits +5% later → stop wins
    prices = [100.0, 98.0, 95.0, 105.0, 106.0]
    series = _series(prices)
    sigma = Decimal("0.01")
    result = triple_barrier_label(
        series, BASE_TS, sigma,
        pt=Decimal("2"), sl=Decimal("2"), n_bars=4,
    )
    assert result is not None
    assert result.label == -1
    assert result.first_touch_at == series[1][0]


def test_sigma_zero_returns_none() -> None:
    prices = [100.0, 100.0, 100.0]
    series = _series(prices)
    result = triple_barrier_label(
        series, BASE_TS, Decimal("0"),
        pt=Decimal("2"), sl=Decimal("2"), n_bars=2,
    )
    assert result is None


def test_insufficient_future_data_returns_none() -> None:
    series = _series([100.0])
    result = triple_barrier_label(
        series, BASE_TS, Decimal("0.01"), n_bars=10,
    )
    assert result is None


def test_no_lookahead_uses_only_forward_bars() -> None:
    # Pre-entry bars should not participate in decision
    # Day 0..4 = pre-entry; entry at day 5; horizon n_bars=3 → 6,7,8
    full_prices = [90.0, 95.0, 105.0, 110.0, 98.0, 100.0, 101.0, 105.0, 102.0]
    series = _series(full_prices)
    entry_ts = series[5][0]
    # Sigma small → +5% hit would trigger up
    result = triple_barrier_label(
        series, entry_ts, Decimal("0.01"),
        pt=Decimal("2"), sl=Decimal("2"), n_bars=3,
    )
    assert result is not None
    # Day 7 is 105 → +5% from 100 → up
    assert result.label == 1
    assert result.first_touch_at == series[7][0]


# ---------------------------------------------------------------------------
# Realized returns at offsets
# ---------------------------------------------------------------------------


def test_realized_return_at_offset() -> None:
    series = _series([100.0] * 40)  # flat
    series[30] = (series[30][0], Decimal("110"))  # day 30 price bump
    out = realized_return_at(series, BASE_TS, 30, entry_price=Decimal("100"))
    assert out is not None
    price_at, ret = out
    assert price_at == Decimal("110")
    assert ret == Decimal("0.1")


def test_realized_return_none_when_offset_beyond_series() -> None:
    series = _series([100.0] * 10)
    assert realized_return_at(series, BASE_TS, 30) is None


# ---------------------------------------------------------------------------
# Signal-type classifier + horizon mapping
# ---------------------------------------------------------------------------


def test_horizon_for_signal_values() -> None:
    assert horizon_for_signal("trend") == HORIZON_TREND == 63
    assert horizon_for_signal("mean_reversion") == HORIZON_MEAN_REVERSION == 10
    assert horizon_for_signal("default") == HORIZON_DEFAULT == 30
    assert horizon_for_signal(None) == HORIZON_DEFAULT
    assert horizon_for_signal("anything-else") == HORIZON_DEFAULT


def test_classify_empty_is_default() -> None:
    assert classify_signal_type(None) == "default"
    assert classify_signal_type([]) == "default"


def test_classify_trend_dominant() -> None:
    keys = ["price_vs_sma_long", "trend_strength", "rsi_14"]
    assert classify_signal_type(keys) == "trend"


def test_classify_mean_reversion_dominant() -> None:
    keys = ["rsi_14", "rsi_14", "trend_strength"]
    assert classify_signal_type(keys) == "mean_reversion"


def test_classify_tie_is_default() -> None:
    keys = ["trend_strength", "rsi_14"]
    assert classify_signal_type(keys) == "default"


def test_classify_ignores_unknown_keys() -> None:
    # Unknowns don't vote — all-unknown stays default
    assert classify_signal_type(["macd", "something_else"]) == "default"
