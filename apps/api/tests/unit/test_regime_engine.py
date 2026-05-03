"""Unit tests: regime engine pure functions."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.api.src.domain.regime.regime_engine import (
    BarView,
    MIN_PCTILE_SAMPLES,
    atr_percent,
    classify_market_trend,
    classify_vol_regime,
    compute_regime,
    log_returns,
    percentile_rank,
    realized_vol_annualized,
    simple_moving_average,
)


BASE = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)


def _bars(closes: list[float]) -> list[BarView]:
    out: list[BarView] = []
    for i, c in enumerate(closes):
        out.append(BarView(
            ts=BASE + dt.timedelta(days=i),
            high=Decimal(str(c * 1.01)),
            low=Decimal(str(c * 0.99)),
            close=Decimal(str(c)),
        ))
    return out


# ---------------------------------------------------------------------------
# simple_moving_average
# ---------------------------------------------------------------------------


def test_sma_basic() -> None:
    vals = [Decimal(str(v)) for v in [1, 2, 3, 4, 5]]
    assert simple_moving_average(vals, 5) == 3.0
    assert simple_moving_average(vals, 3) == 4.0


def test_sma_returns_none_when_short() -> None:
    assert simple_moving_average([Decimal("1"), Decimal("2")], 5) is None


# ---------------------------------------------------------------------------
# log_returns
# ---------------------------------------------------------------------------


def test_log_returns_length_and_sign() -> None:
    closes = [Decimal("100"), Decimal("105"), Decimal("100"), Decimal("110")]
    rs = log_returns(closes)
    assert len(rs) == 3
    assert rs[0] > 0  # 100 -> 105
    assert rs[1] < 0  # 105 -> 100


def test_log_returns_skip_nonpositive() -> None:
    rs = log_returns([Decimal("0"), Decimal("100")])
    assert rs == []


# ---------------------------------------------------------------------------
# realized_vol_annualized
# ---------------------------------------------------------------------------


def test_realized_vol_requires_window_plus_one() -> None:
    closes = [Decimal("100")] * 20
    assert realized_vol_annualized(closes, window=20) is None


def test_realized_vol_zero_for_flat_series() -> None:
    closes = [Decimal("100")] * 21
    rv = realized_vol_annualized(closes, window=20)
    assert rv == 0.0


def test_realized_vol_positive_on_oscillation() -> None:
    closes = []
    price = 100.0
    for i in range(25):
        price *= 1.01 if i % 2 == 0 else 0.99
        closes.append(Decimal(str(price)))
    rv = realized_vol_annualized(closes, window=20)
    assert rv is not None
    assert rv > 0.05  # annualized daily ±1% → ~16% vol


# ---------------------------------------------------------------------------
# atr_percent
# ---------------------------------------------------------------------------


def test_atr_percent_requires_period_plus_one() -> None:
    assert atr_percent(_bars([100.0] * 14), period=14) is None


def test_atr_percent_positive() -> None:
    a = atr_percent(_bars([100.0] * 20), period=14)
    assert a is not None
    assert a > 0


# ---------------------------------------------------------------------------
# percentile_rank
# ---------------------------------------------------------------------------


def test_percentile_rank_none_on_small_sample() -> None:
    history = [0.1] * (MIN_PCTILE_SAMPLES - 1)
    assert percentile_rank(history, 0.5) is None


def test_percentile_rank_boundaries() -> None:
    history = list(range(MIN_PCTILE_SAMPLES))  # 0..29
    assert percentile_rank(history, -1) == 0.0
    assert percentile_rank(history, 100) == 1.0


def test_percentile_rank_mid() -> None:
    history = list(range(MIN_PCTILE_SAMPLES))
    p = percentile_rank(history, 15)
    assert p is not None
    assert 0.45 < p < 0.55


# ---------------------------------------------------------------------------
# classify_market_trend
# ---------------------------------------------------------------------------


def test_trend_uptrend_when_sma50_above_sma200_and_price_above() -> None:
    assert classify_market_trend(close=110, sma50=105, sma200=100) == "uptrend"


def test_trend_downtrend_when_sma50_below_sma200_and_price_well_below() -> None:
    # pct_above_200 = (94-100)/100 = -0.06 < -0.05
    assert classify_market_trend(close=94, sma50=95, sma200=100) == "downtrend"


def test_trend_sideways_when_near_sma200() -> None:
    # pct_above_200 = -0.02, not < -0.05 → sideways
    assert classify_market_trend(close=98, sma50=99, sma200=100) == "sideways"


def test_trend_sideways_when_sma50_above_but_price_at_sma200() -> None:
    # price == sma200 → pct_above_200 = 0, not > 0 → not uptrend → sideways
    assert classify_market_trend(close=100, sma50=105, sma200=100) == "sideways"


# ---------------------------------------------------------------------------
# classify_vol_regime
# ---------------------------------------------------------------------------


def test_vol_regime_low() -> None:
    assert classify_vol_regime(0.10) == "low"
    assert classify_vol_regime(0.3299) == "low"


def test_vol_regime_normal() -> None:
    assert classify_vol_regime(0.33) == "normal"
    assert classify_vol_regime(0.79) == "normal"


def test_vol_regime_high() -> None:
    assert classify_vol_regime(0.80) == "high"
    assert classify_vol_regime(0.99) == "high"


# ---------------------------------------------------------------------------
# compute_regime — end-to-end on synthetic SPY series
# ---------------------------------------------------------------------------


def _long_series(n: int, start: float = 100.0, drift: float = 0.001) -> list[BarView]:
    closes = []
    price = start
    for i in range(n):
        # Small alternating move so stdev > 0
        shock = 0.005 if i % 2 == 0 else -0.003
        price *= 1 + drift + shock
        closes.append(price)
    return _bars(closes)


def test_compute_regime_insufficient_bars_returns_none() -> None:
    bars = _long_series(150)  # < MIN_SMA_LONG (200)
    assert compute_regime(bars, dt.date(2026, 4, 19)) is None


def test_compute_regime_happy_path_on_drifting_series() -> None:
    # 280 bars: enough for SMA200 + percentile windows (>= MIN_PCTILE_SAMPLES)
    bars = _long_series(280, drift=0.0008)
    result = compute_regime(bars, dt.date(2026, 4, 19))
    assert result is not None
    assert result.benchmark_symbol == "SPY"
    assert result.as_of_date == dt.date(2026, 4, 19)
    assert result.market_trend in ("uptrend", "downtrend", "sideways")
    assert result.vol_regime in ("low", "normal", "high")
    assert result.breadth_regime is None
    assert result.realized_vol_20d > 0
    assert 0 <= result.atr_pctile_1y <= 1
    assert isinstance(result.sma50_over_sma200, bool)


def test_compute_regime_uptrend_on_strong_drift() -> None:
    bars = _long_series(280, drift=0.003)  # strong upward drift
    result = compute_regime(bars, dt.date(2026, 4, 19))
    assert result is not None
    assert result.market_trend == "uptrend"
    assert result.sma50_over_sma200 is True
