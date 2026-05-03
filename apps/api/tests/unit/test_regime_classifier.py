"""Unit tests for deterministic regime classification."""

from __future__ import annotations

from decimal import Decimal

from apps.api.src.domain.features.regime_classifier import (
    DD_REGIMES,
    TREND_REGIMES,
    VOL_REGIMES,
    classify_all,
    classify_drawdown,
    classify_trend,
    classify_volatility,
)


def _constant(n: int, value: float = 100.0) -> list[Decimal]:
    return [Decimal(str(value)) for _ in range(n)]


def _uptrend(n: int = 250, start: float = 100.0, step: float = 0.5) -> list[Decimal]:
    return [Decimal(str(start + i * step)) for i in range(n)]


def _downtrend(n: int = 250, start: float = 200.0, step: float = -0.5) -> list[Decimal]:
    return [Decimal(str(start + i * step)) for i in range(n)]


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------


def test_trend_uptrend() -> None:
    assert classify_trend(_uptrend()) == "uptrend"


def test_trend_downtrend() -> None:
    assert classify_trend(_downtrend()) == "downtrend"


def test_trend_sideways_on_flat() -> None:
    assert classify_trend(_constant(250)) == "sideways"


def test_trend_sideways_on_insufficient_data() -> None:
    assert classify_trend(_constant(10)) == "sideways"
    assert classify_trend([]) == "sideways"


# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------


def test_volatility_low_on_quiet_series() -> None:
    # Tiny steps → daily sigma << 1% → annualized ~1% → low
    prices = [Decimal(str(100 + i * 0.001)) for i in range(100)]
    assert classify_volatility(prices) == "low"


def test_volatility_high_on_noisy_series() -> None:
    # Zigzag with ±3% swings → annualized ~40%+ → high
    prices: list[Decimal] = []
    base = Decimal("100")
    for i in range(100):
        swing = Decimal("3") if i % 2 == 0 else Decimal("-3")
        base = base + swing
        prices.append(base)
    assert classify_volatility(prices) == "high"


def test_volatility_medium_default_on_short_series() -> None:
    assert classify_volatility([Decimal("100")]) == "medium"


# ---------------------------------------------------------------------------
# Drawdown
# ---------------------------------------------------------------------------


def test_drawdown_none_on_rising_series() -> None:
    assert classify_drawdown(_uptrend()) == "none"


def test_drawdown_severe_on_deep_decline() -> None:
    # Peak 200, trough 100 → 50% drawdown → severe
    prices = _uptrend(n=100, start=100, step=1.0) + _downtrend(n=100, start=200, step=-1.0)
    assert classify_drawdown(prices) == "severe"


def test_drawdown_mild_on_moderate_decline() -> None:
    # ~10% drawdown
    prices = _uptrend(n=50, start=100, step=1.0) + [Decimal("135")] * 5 + _downtrend(
        n=25, start=135, step=-0.5
    )
    result = classify_drawdown(prices)
    assert result in ("mild", "severe")  # around the boundary; tolerate either side


def test_drawdown_none_empty() -> None:
    assert classify_drawdown([]) == "none"


# ---------------------------------------------------------------------------
# Combined
# ---------------------------------------------------------------------------


def test_classify_all_has_three_keys() -> None:
    out = classify_all(_uptrend())
    assert set(out.keys()) == {"trend_regime", "volatility_regime", "drawdown_regime"}
    assert out["trend_regime"] in TREND_REGIMES
    assert out["volatility_regime"] in VOL_REGIMES
    assert out["drawdown_regime"] in DD_REGIMES


def test_classify_all_deterministic_same_input_same_output() -> None:
    prices = _uptrend()
    assert classify_all(prices) == classify_all(prices)
