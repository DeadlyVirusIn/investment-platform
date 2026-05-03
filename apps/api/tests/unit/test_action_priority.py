"""Unit tests for action priority scoring."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.src.domain.actions.priority import (
    TIER_CRT_THRESHOLD,
    TIER_HIGH_THRESHOLD,
    compute_priority,
    priority_tier,
)


class TestComputePriority:
    def test_all_max_inputs_gives_100(self):
        p = compute_priority(
            confidence=100,
            regime_aligned=True,
            urgency="now",
            dependencies_resolved_frac=1.0,
            economic_impact_pct=1.0,
        )
        assert p == Decimal("100.00")

    def test_all_min_inputs_gives_0(self):
        p = compute_priority(
            confidence=0,
            regime_aligned=False,
            urgency="passive",
            dependencies_resolved_frac=0.0,
            economic_impact_pct=0.0,
        )
        # urgency=passive is still 0.2 weight → 0.25 * 0.2 = 0.05 of 100 = 5
        assert p == Decimal("5.00")

    def test_none_confidence_treated_as_zero(self):
        p = compute_priority(
            confidence=None,
            regime_aligned=False,
            urgency="passive",
            dependencies_resolved_frac=0.0,
            economic_impact_pct=0.0,
        )
        assert p == Decimal("5.00")

    def test_returns_decimal_with_2dp(self):
        p = compute_priority(
            confidence=73.5,
            regime_aligned=True,
            urgency="today",
            dependencies_resolved_frac=0.5,
            economic_impact_pct=0.3,
        )
        assert isinstance(p, Decimal)
        # Max 2dp — no more
        sign, digits, exponent = p.as_tuple()
        assert exponent >= -2

    def test_confidence_clipped_above_100(self):
        p_high = compute_priority(
            confidence=150,
            regime_aligned=False,
            urgency="passive",
            dependencies_resolved_frac=0.0,
            economic_impact_pct=0.0,
        )
        p_max = compute_priority(
            confidence=100,
            regime_aligned=False,
            urgency="passive",
            dependencies_resolved_frac=0.0,
            economic_impact_pct=0.0,
        )
        assert p_high == p_max

    def test_confidence_clipped_below_0(self):
        p_low = compute_priority(
            confidence=-25,
            regime_aligned=False,
            urgency="passive",
            dependencies_resolved_frac=0.0,
            economic_impact_pct=0.0,
        )
        p_zero = compute_priority(
            confidence=0,
            regime_aligned=False,
            urgency="passive",
            dependencies_resolved_frac=0.0,
            economic_impact_pct=0.0,
        )
        assert p_low == p_zero

    def test_deps_clipped_to_01(self):
        p_over = compute_priority(
            confidence=50, regime_aligned=False, urgency="passive",
            dependencies_resolved_frac=5.0, economic_impact_pct=0.0,
        )
        p_one = compute_priority(
            confidence=50, regime_aligned=False, urgency="passive",
            dependencies_resolved_frac=1.0, economic_impact_pct=0.0,
        )
        assert p_over == p_one

    def test_unknown_urgency_defaults_to_this_week(self):
        p_unknown = compute_priority(
            confidence=0, regime_aligned=False, urgency="bogus",
            dependencies_resolved_frac=0.0, economic_impact_pct=0.0,
        )
        p_week = compute_priority(
            confidence=0, regime_aligned=False, urgency="this_week",
            dependencies_resolved_frac=0.0, economic_impact_pct=0.0,
        )
        assert p_unknown == p_week

    def test_regime_aligned_adds_20_points(self):
        p_aligned = compute_priority(
            confidence=0, regime_aligned=True, urgency="passive",
            dependencies_resolved_frac=0.0, economic_impact_pct=0.0,
        )
        p_unaligned = compute_priority(
            confidence=0, regime_aligned=False, urgency="passive",
            dependencies_resolved_frac=0.0, economic_impact_pct=0.0,
        )
        assert p_aligned - p_unaligned == Decimal("20.00")

    def test_urgency_now_vs_passive_delta_is_20(self):
        kwargs = dict(
            confidence=0, regime_aligned=False,
            dependencies_resolved_frac=0.0, economic_impact_pct=0.0,
        )
        p_now = compute_priority(urgency="now", **kwargs)
        p_passive = compute_priority(urgency="passive", **kwargs)
        # 0.25 * (1.0 - 0.2) * 100 = 20
        assert p_now - p_passive == Decimal("20.00")

    def test_confidence_75_regime_aligned_today_yields_crt(self):
        p = compute_priority(
            confidence=75,
            regime_aligned=True,
            urgency="today",
            dependencies_resolved_frac=1.0,
            economic_impact_pct=0.5,
        )
        # 0.35*0.75 + 0.25*0.8 + 0.20 + 0.10 + 0.05 = 0.2625+0.20+0.20+0.10+0.05 = 0.8125 → 81.25
        assert p == Decimal("81.25")
        assert priority_tier(p) == "CRT"

    def test_deterministic_same_inputs_same_output(self):
        args = dict(
            confidence=55, regime_aligned=True, urgency="today",
            dependencies_resolved_frac=0.7, economic_impact_pct=0.33,
        )
        assert compute_priority(**args) == compute_priority(**args)


class TestPriorityTier:
    def test_75_is_crt(self):
        assert priority_tier(Decimal("75.00")) == "CRT"
        assert priority_tier(Decimal("99.99")) == "CRT"

    def test_50_to_under_75_is_high(self):
        assert priority_tier(Decimal("50.00")) == "HIGH"
        assert priority_tier(Decimal("74.99")) == "HIGH"

    def test_under_50_is_nrm(self):
        assert priority_tier(Decimal("49.99")) == "NRM"
        assert priority_tier(Decimal("0")) == "NRM"

    def test_accepts_float_input(self):
        assert priority_tier(80.0) == "CRT"
        assert priority_tier(55) == "HIGH"
        assert priority_tier(10.5) == "NRM"

    def test_thresholds_are_exposed(self):
        assert TIER_CRT_THRESHOLD == Decimal("75")
        assert TIER_HIGH_THRESHOLD == Decimal("50")
