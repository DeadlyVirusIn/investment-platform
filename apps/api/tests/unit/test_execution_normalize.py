"""Unit tests — execution boundary normalizers."""

from __future__ import annotations

import math

import pytest

from apps.api.src.domain.execution.normalize import (
    TRADING_DAYS_PER_YEAR,
    VOL_MAX,
    VOL_MIN,
    VolatilityScaleError,
    ensure_annualized_vol,
    normalize_confidence,
    validate_annualized_vol,
)


# ---------------------------------------------------------------------------
# normalize_confidence
# ---------------------------------------------------------------------------


class TestNormalizeConfidence:
    def test_percentage_71_2_becomes_0_712(self):
        assert normalize_confidence(71.2) == pytest.approx(0.712)

    def test_fractional_0_71_unchanged(self):
        assert normalize_confidence(0.71) == pytest.approx(0.71)

    def test_fractional_1_0_unchanged(self):
        assert normalize_confidence(1.0) == 1.0

    def test_150_clamped_to_1(self):
        assert normalize_confidence(150) == 1.0

    def test_negative_becomes_zero(self):
        assert normalize_confidence(-0.3) == 0.0

    def test_negative_percent_becomes_zero(self):
        assert normalize_confidence(-20) == 0.0

    def test_none_becomes_zero(self):
        assert normalize_confidence(None) == 0.0

    def test_zero_stays_zero(self):
        assert normalize_confidence(0) == 0.0
        assert normalize_confidence(0.0) == 0.0

    def test_non_numeric_returns_zero(self):
        assert normalize_confidence("abc") == 0.0
        assert normalize_confidence([]) == 0.0

    def test_int_accepted(self):
        assert normalize_confidence(75) == 0.75
        assert normalize_confidence(1) == 1.0

    def test_string_number_accepted(self):
        assert normalize_confidence("71.2") == pytest.approx(0.712)

    def test_exactly_1_0_not_divided(self):
        """Boundary: 1.0 must remain 1.0 (fractional), not become 0.01."""
        assert normalize_confidence(1.0) == 1.0


# ---------------------------------------------------------------------------
# ensure_annualized_vol
# ---------------------------------------------------------------------------


class TestEnsureAnnualizedVol:
    def test_daily_input_multiplied_by_sqrt_252(self):
        daily = 0.02
        result = ensure_annualized_vol(daily, is_daily=True)
        expected = 0.02 * math.sqrt(TRADING_DAYS_PER_YEAR)
        assert result == pytest.approx(expected)

    def test_annualized_input_unchanged(self):
        annualized = 0.30
        result = ensure_annualized_vol(annualized, is_daily=False)
        assert result == 0.30

    def test_zero_returns_zero(self):
        assert ensure_annualized_vol(0.0, is_daily=True) == 0.0
        assert ensure_annualized_vol(0.0, is_daily=False) == 0.0

    def test_none_returns_zero(self):
        assert ensure_annualized_vol(None, is_daily=True) == 0.0
        assert ensure_annualized_vol(None, is_daily=False) == 0.0

    def test_negative_returns_zero(self):
        assert ensure_annualized_vol(-0.02, is_daily=True) == 0.0

    def test_non_numeric_returns_zero(self):
        assert ensure_annualized_vol("xyz", is_daily=True) == 0.0
        assert ensure_annualized_vol([], is_daily=False) == 0.0

    def test_sqrt_factor_is_sqrt_252(self):
        assert ensure_annualized_vol(1.0, is_daily=True) == pytest.approx(
            math.sqrt(252)
        )


# ---------------------------------------------------------------------------
# validate_annualized_vol
# ---------------------------------------------------------------------------


class TestValidateAnnualizedVol:
    def test_normal_equity_vol_passes(self):
        validate_annualized_vol(0.30)  # 30% annualized, typical
        validate_annualized_vol(0.15)
        validate_annualized_vol(1.0)   # extreme but valid

    def test_below_min_raises(self):
        with pytest.raises(VolatilityScaleError):
            validate_annualized_vol(VOL_MIN / 2)
        with pytest.raises(VolatilityScaleError):
            validate_annualized_vol(0.0)
        with pytest.raises(VolatilityScaleError):
            validate_annualized_vol(-0.1)

    def test_above_max_raises(self):
        with pytest.raises(VolatilityScaleError):
            validate_annualized_vol(VOL_MAX + 0.1)
        with pytest.raises(VolatilityScaleError):
            validate_annualized_vol(5.0)

    def test_exact_bounds_are_excluded(self):
        """Strict inequality — VOL_MIN and VOL_MAX themselves raise."""
        with pytest.raises(VolatilityScaleError):
            validate_annualized_vol(VOL_MIN)
        with pytest.raises(VolatilityScaleError):
            validate_annualized_vol(VOL_MAX)
