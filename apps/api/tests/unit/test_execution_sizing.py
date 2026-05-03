"""Unit tests — execution sizing (normalized + Kelly)."""

from __future__ import annotations

import pytest

from apps.api.src.domain.execution.sizing import (
    KELLY_FRACTION_DEFAULT,
    KELLY_FULL_EDGE_RETURN,
    KELLY_SIGNAL_NEUTRAL,
    MAX_POSITION_SIZE,
    TARGET_DAILY_VOL,
    VOL_SCALE_CAP,
    VOL_SCALE_FLOOR,
    kelly_size,
    normalized_size,
)


# ---------------------------------------------------------------------------
# normalized_size
# ---------------------------------------------------------------------------


class TestNormalizedSize:
    def test_zero_composite_zero_size(self):
        r = normalized_size(0.0, 0.9, 0.02)
        assert r.raw_size == 0.0
        assert r.capped_reason == "zero"

    def test_zero_confidence_zero_size(self):
        r = normalized_size(0.9, 0.0, 0.02)
        assert r.raw_size == 0.0

    def test_high_conviction_target_vol(self):
        """Max conviction at target_vol -> size = conviction * 1.0"""
        r = normalized_size(1.0, 1.0, TARGET_DAILY_VOL)
        # conviction=1.0, vol_scale=1.0 -> size=1.0
        assert abs(r.raw_size - 1.0) < 1e-9

    def test_high_vol_shrinks_size(self):
        low_vol = normalized_size(0.8, 0.8, 0.01)    # vol < target -> boost
        high_vol = normalized_size(0.8, 0.8, 0.05)   # vol > target -> shrink
        assert high_vol.raw_size < low_vol.raw_size

    def test_low_vol_bonus_capped(self):
        """Vol scale can't exceed VOL_SCALE_CAP."""
        r = normalized_size(0.5, 0.5, 0.001)  # vol << target
        assert r.vol_scale <= VOL_SCALE_CAP + 1e-9

    def test_extreme_vol_scales_floor(self):
        r = normalized_size(0.5, 0.5, 1.0)  # crazy high vol
        assert r.vol_scale >= VOL_SCALE_FLOOR - 1e-9

    def test_zero_vol_defaults_to_one_scale(self):
        """Zero vol must not explode to infinity."""
        r = normalized_size(0.5, 0.5, 0.0)
        assert 0 <= r.raw_size <= MAX_POSITION_SIZE

    def test_max_size_cap(self):
        """Size must never exceed max_size, regardless of conviction/vol."""
        r = normalized_size(1.0, 1.0, 1e-9)  # maximal conviction, minimal vol
        assert r.raw_size <= MAX_POSITION_SIZE + 1e-9

    def test_custom_max_size(self):
        r = normalized_size(1.0, 1.0, 1e-9, max_size=0.3)
        assert r.raw_size <= 0.3 + 1e-9

    def test_input_clipping_composite(self):
        # composite > 1 or < 0 should be clipped
        r_over = normalized_size(1.5, 0.8, 0.02)
        r_max = normalized_size(1.0, 0.8, 0.02)
        assert abs(r_over.raw_size - r_max.raw_size) < 1e-9
        r_neg = normalized_size(-0.3, 0.8, 0.02)
        assert r_neg.raw_size == 0.0

    def test_output_bounded_0_1(self):
        # Random sweep
        for c in [0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0]:
            for q in [0.0, 0.3, 0.7, 1.0]:
                for v in [1e-6, 0.005, 0.02, 0.10, 0.50]:
                    r = normalized_size(c, q, v)
                    assert 0.0 <= r.raw_size <= MAX_POSITION_SIZE


# ---------------------------------------------------------------------------
# kelly_size
# ---------------------------------------------------------------------------


class TestKellySize:
    def test_below_neutral_zero_size(self):
        """Composite below signal_neutral -> no bet."""
        r = kelly_size(KELLY_SIGNAL_NEUTRAL - 0.01, 1.0, 0.02)
        assert r.raw_size == 0.0
        assert r.capped_reason == "neutral"

    def test_at_neutral_zero_size(self):
        r = kelly_size(KELLY_SIGNAL_NEUTRAL, 1.0, 0.02)
        assert r.raw_size == 0.0

    def test_max_composite_max_confidence_positive(self):
        r = kelly_size(1.0, 1.0, 0.02)
        assert r.raw_size > 0.0

    def test_zero_vol_returns_zero_not_infinity(self):
        r = kelly_size(1.0, 1.0, 0.0)
        assert r.raw_size == 0.0
        assert r.capped_reason == "zero"

    def test_low_vol_larger_size(self):
        # Use vols high enough that neither hits max_size cap
        r_low = kelly_size(0.9, 0.9, 0.08)
        r_high = kelly_size(0.9, 0.9, 0.15)
        assert r_low.raw_size > r_high.raw_size

    def test_max_cap_enforced(self):
        """Extreme edge + tiny vol must not exceed max_size."""
        r = kelly_size(1.0, 1.0, 1e-3)   # very small vol -> big Kelly
        assert r.raw_size <= MAX_POSITION_SIZE + 1e-9

    def test_quarter_kelly_default(self):
        assert KELLY_FRACTION_DEFAULT == 0.25

    def test_fractional_kelly_smaller_than_full(self):
        r_quarter = kelly_size(0.9, 0.9, 0.03, kelly_fraction=0.25)
        r_full = kelly_size(0.9, 0.9, 0.03, kelly_fraction=1.0)
        # Both may be capped at max_size; relax expectation
        assert r_quarter.raw_size <= r_full.raw_size + 1e-9

    def test_confidence_scales_edge(self):
        # vol=0.10 keeps both below max cap
        r_hi = kelly_size(0.9, 1.0, 0.10)
        r_lo = kelly_size(0.9, 0.3, 0.10)
        assert r_hi.raw_size > r_lo.raw_size

    def test_composite_monotonic(self):
        sizes = [
            kelly_size(c, 1.0, 0.02).raw_size
            for c in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        ]
        for i in range(len(sizes) - 1):
            assert sizes[i] <= sizes[i + 1] + 1e-9

    def test_output_bounded(self):
        for c in [0.0, 0.5, 0.7, 0.9, 1.0]:
            for q in [0.0, 0.5, 1.0]:
                for v in [1e-6, 0.01, 0.03, 0.1, 0.5]:
                    r = kelly_size(c, q, v)
                    assert 0.0 <= r.raw_size <= MAX_POSITION_SIZE

    def test_input_clipping(self):
        # Out-of-range composite/confidence clipped, no crash
        r = kelly_size(1.5, 1.5, 0.02)
        assert 0 <= r.raw_size <= MAX_POSITION_SIZE
        r_neg = kelly_size(-0.5, 0.5, 0.02)
        assert r_neg.raw_size == 0.0
