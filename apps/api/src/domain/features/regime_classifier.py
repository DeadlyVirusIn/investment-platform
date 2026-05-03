"""Deterministic regime classification from a price series.

No ML. No lookahead — callers pass only pre-entry prices.
All math in Decimal.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from apps.api.src.domain.recommendations.outcome_labeling import (
    _decimal_sqrt,
    compute_sigma_from_returns,
)

TrendRegime = Literal["uptrend", "downtrend", "sideways"]
VolRegime = Literal["low", "medium", "high"]
DdRegime = Literal["none", "mild", "severe"]

TREND_REGIMES: tuple[str, ...] = ("uptrend", "downtrend", "sideways")
VOL_REGIMES: tuple[str, ...] = ("low", "medium", "high")
DD_REGIMES: tuple[str, ...] = ("none", "mild", "severe")


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _sma(prices: list[Decimal], period: int) -> Decimal | None:
    if len(prices) < period:
        return None
    return sum(prices[-period:], Decimal("0")) / Decimal(period)


def _daily_returns(prices: list[Decimal], lookback: int) -> list[Decimal]:
    start = max(1, len(prices) - lookback)
    return [
        (prices[i] - prices[i - 1]) / prices[i - 1]
        for i in range(start, len(prices))
        if prices[i - 1] != 0
    ]


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------


def classify_trend(prices: list[Decimal]) -> TrendRegime:
    """uptrend when SMA20 > SMA50 AND price > long SMA.

    downtrend when SMA20 < SMA50 AND price < long SMA.
    sideways otherwise. Defaults to ``sideways`` on insufficient data.
    """
    if len(prices) < 21:
        return "sideways"
    current = prices[-1]
    sma20 = _sma(prices, 20)
    sma50 = _sma(prices, min(50, len(prices)))
    long_sma = _sma(prices, min(200, len(prices)))
    if sma20 is None or sma50 is None or long_sma is None:
        return "sideways"
    if sma20 > sma50 and current > long_sma:
        return "uptrend"
    if sma20 < sma50 and current < long_sma:
        return "downtrend"
    return "sideways"


# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------


def classify_volatility(
    prices: list[Decimal],
    lookback: int = 20,
    low_thresh: Decimal = Decimal("0.15"),
    high_thresh: Decimal = Decimal("0.30"),
) -> VolRegime:
    """Bucket annualized realized vol of the trailing ``lookback`` daily returns.

    Thresholds default to <15% low / 15-30% medium / >30% high.
    Annualization = ``sqrt(252)``. Defaults to ``medium`` on insufficient data.
    """
    if len(prices) < lookback + 1:
        return "medium"
    returns = _daily_returns(prices, lookback)
    daily_sigma = compute_sigma_from_returns(returns)
    if daily_sigma is None:
        return "medium"
    annualized = daily_sigma * _decimal_sqrt(Decimal("252"))
    if annualized < low_thresh:
        return "low"
    if annualized > high_thresh:
        return "high"
    return "medium"


# ---------------------------------------------------------------------------
# Drawdown
# ---------------------------------------------------------------------------


def classify_drawdown(
    prices: list[Decimal],
    lookback: int = 252,
    mild_thresh: Decimal = Decimal("0.05"),
    severe_thresh: Decimal = Decimal("0.20"),
) -> DdRegime:
    """Bucket max peak-to-trough drawdown over the trailing window.

    Thresholds default to <5% none / 5-20% mild / >=20% severe.
    """
    window = prices[-lookback:] if len(prices) >= lookback else prices
    if len(window) < 2:
        return "none"
    peak = window[0]
    max_dd = Decimal("0")
    for v in window:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
    if max_dd < mild_thresh:
        return "none"
    if max_dd < severe_thresh:
        return "mild"
    return "severe"


# ---------------------------------------------------------------------------
# Combined
# ---------------------------------------------------------------------------


def classify_all(prices: list[Decimal]) -> dict[str, str]:
    return {
        "trend_regime": classify_trend(prices),
        "volatility_regime": classify_volatility(prices),
        "drawdown_regime": classify_drawdown(prices),
    }
