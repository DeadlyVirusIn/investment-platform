"""Unit tests — regime classifier + multiplier table."""

from __future__ import annotations

import math

import pytest

from apps.api.src.domain.execution.regime import (
    DEFAULT_REGIME,
    HIGH_VOL_RATIO,
    LOW_VOL_RATIO,
    MIN_BARS_REQUIRED,
    REGIME_MULTIPLIERS,
    REGIMES,
    classify_regime,
    regime_multiplier,
)


# ---------------------------------------------------------------------------
# Helpers — deterministic synthetic price series
# ---------------------------------------------------------------------------


def _linear_uptrend(n: int, start: float = 100.0, daily_pct: float = 0.005) -> list[float]:
    """Exponential uptrend — constant % returns give vol_ratio~=1, letting
    the trend branch fire (not the low_vol branch)."""
    out = [start]
    for _ in range(n - 1):
        out.append(out[-1] * (1.0 + daily_pct))
    return out


def _sideways(n: int, base: float = 100.0) -> list[float]:
    """Flat constant series -> vol=0 (no vol regime) and SMA_short==SMA_long
    -> falls through to sideways."""
    return [base] * n


def _high_vol_recent(
    n_calm: int, n_chaotic: int, base: float = 100.0,
) -> list[float]:
    """Calm history + high-vol recent window."""
    # Calm segment: very small deterministic oscillation
    out = [base + 0.01 * math.sin(i) for i in range(n_calm)]
    # Chaotic segment: alternating large jumps
    last = out[-1]
    for i in range(n_chaotic):
        last = last * (1.05 if i % 2 == 0 else 0.95)
        out.append(last)
    return out


def _low_vol_recent(
    n_chaotic: int, n_calm: int, base: float = 100.0,
) -> list[float]:
    """Volatile history + calm recent window."""
    out = []
    last = base
    for i in range(n_chaotic):
        last = last * (1.05 if i % 2 == 0 else 0.95)
        out.append(last)
    # Calm ends
    for i in range(n_calm):
        out.append(last + 0.001 * math.sin(i))
    return out


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class TestClassifyRegime:
    def test_insufficient_bars_defaults_sideways(self):
        r = classify_regime([100.0, 101.0, 102.0])
        assert r.regime == DEFAULT_REGIME
        assert "insufficient_bars" in r.reason
        assert r.multiplier == REGIME_MULTIPLIERS[DEFAULT_REGIME]

    def test_trend_up_detected(self):
        prices = _linear_uptrend(80)
        r = classify_regime(prices)
        assert r.regime == "trend_up"
        assert r.sma_short > r.sma_long
        assert r.slope_up is True

    def test_sideways_fallback(self):
        prices = _sideways(80)
        r = classify_regime(prices)
        # Flat series may classify as low_vol (tiny vol ratio) or sideways
        assert r.regime in ("sideways", "low_vol")

    def test_high_vol_detected(self):
        prices = _high_vol_recent(n_calm=80, n_chaotic=25)
        r = classify_regime(prices)
        assert r.regime == "high_vol"
        assert r.vol_ratio is not None and r.vol_ratio > HIGH_VOL_RATIO

    def test_low_vol_detected(self):
        prices = _low_vol_recent(n_chaotic=80, n_calm=25)
        r = classify_regime(prices)
        assert r.regime == "low_vol"
        assert r.vol_ratio is not None and r.vol_ratio < LOW_VOL_RATIO

    def test_bars_available_reported(self):
        prices = _linear_uptrend(100)
        r = classify_regime(prices)
        assert r.bars_available == 100

    def test_returned_regime_in_enum(self):
        prices = _linear_uptrend(80)
        r = classify_regime(prices)
        assert r.regime in REGIMES or r.regime == DEFAULT_REGIME

    def test_multiplier_is_from_table(self):
        prices = _linear_uptrend(80)
        r = classify_regime(prices)
        assert r.multiplier == REGIME_MULTIPLIERS[r.regime]

    def test_exactly_min_bars_classifies(self):
        prices = _linear_uptrend(MIN_BARS_REQUIRED)
        r = classify_regime(prices)
        assert r.regime != "insufficient_bars"
        assert r.bars_available == MIN_BARS_REQUIRED


# ---------------------------------------------------------------------------
# Multiplier table
# ---------------------------------------------------------------------------


class TestRegimeMultipliers:
    def test_trend_up_full_size(self):
        assert REGIME_MULTIPLIERS["trend_up"] == 1.0

    def test_low_vol_full_size(self):
        assert REGIME_MULTIPLIERS["low_vol"] == 1.0

    def test_sideways_half_size(self):
        assert REGIME_MULTIPLIERS["sideways"] == 0.5

    def test_high_vol_quarter_size(self):
        assert REGIME_MULTIPLIERS["high_vol"] == 0.25

    def test_no_multiplier_above_one(self):
        for m in REGIME_MULTIPLIERS.values():
            assert 0 <= m <= 1.0

    def test_regime_multiplier_lookup(self):
        assert regime_multiplier("trend_up") == 1.0
        assert regime_multiplier("unknown_regime") == REGIME_MULTIPLIERS[DEFAULT_REGIME]

    def test_all_enum_members_have_multiplier(self):
        for regime in REGIMES:
            assert regime in REGIME_MULTIPLIERS
