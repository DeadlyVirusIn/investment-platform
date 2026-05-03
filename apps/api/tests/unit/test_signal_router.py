"""Unit tests — regime-based signal router."""

from __future__ import annotations

import pytest

from apps.api.src.domain.routing.signal_router import (
    DEFAULT_EXPOSURE_MULTIPLIER,
    RULE_FALLBACK_MODEL_ONLY,
    RULE_LOW_VOL_BOTH,
    RULE_SIDEWAYS_REDUCE,
    RULE_TREND_UP_MODEL_ONLY,
    SIDEWAYS_EXPOSURE_MULTIPLIER,
    RoutedOutput,
    route_signals,
)


MODEL = [f"M{i}" for i in range(5)]
BEHAV = [f"B{i}" for i in range(3)]


class TestRouteSignals:
    def test_low_vol_uses_both_full_exposure(self):
        out = route_signals("low_vol", MODEL, BEHAV)
        assert out.model_signals == MODEL
        assert out.behavioral_signals == BEHAV
        assert out.exposure_multiplier == 1.0
        assert out.rule_applied == RULE_LOW_VOL_BOTH

    def test_trend_up_model_only_full_exposure(self):
        out = route_signals("trend_up", MODEL, BEHAV)
        assert out.model_signals == MODEL
        assert out.behavioral_signals == []
        assert out.exposure_multiplier == 1.0
        assert out.rule_applied == RULE_TREND_UP_MODEL_ONLY

    def test_sideways_uses_both_half_exposure(self):
        out = route_signals("sideways", MODEL, BEHAV)
        assert out.model_signals == MODEL
        assert out.behavioral_signals == BEHAV
        assert out.exposure_multiplier == 0.5
        assert out.rule_applied == RULE_SIDEWAYS_REDUCE

    def test_high_vol_fallback_model_only(self):
        out = route_signals("high_vol", MODEL, BEHAV)
        assert out.model_signals == MODEL
        assert out.behavioral_signals == []
        assert out.exposure_multiplier == 1.0
        assert out.rule_applied == RULE_FALLBACK_MODEL_ONLY

    def test_unknown_regime_fallback_model_only(self):
        out = route_signals("definitely_not_a_regime", MODEL, BEHAV)
        assert out.model_signals == MODEL
        assert out.behavioral_signals == []
        assert out.rule_applied == RULE_FALLBACK_MODEL_ONLY

    def test_empty_inputs_no_crash(self):
        out = route_signals("low_vol", [], [])
        assert out.model_signals == []
        assert out.behavioral_signals == []

    def test_copies_lists_not_mutates(self):
        """Returned lists should be independent from inputs."""
        m = list(MODEL)
        b = list(BEHAV)
        out = route_signals("sideways", m, b)
        out.model_signals.append("M_new")
        out.behavioral_signals.append("B_new")
        assert m == MODEL
        assert b == BEHAV

    def test_routed_output_is_frozen(self):
        out = route_signals("low_vol", MODEL, BEHAV)
        with pytest.raises(Exception):
            out.exposure_multiplier = 0.25  # type: ignore

    def test_exposure_multiplier_always_positive(self):
        for regime in ("low_vol", "trend_up", "sideways", "high_vol", "xyz"):
            out = route_signals(regime, MODEL, BEHAV)
            assert 0.0 < out.exposure_multiplier <= 1.0

    def test_rules_from_constants(self):
        """All 4 rules are represented in constants."""
        rules = {
            RULE_LOW_VOL_BOTH,
            RULE_TREND_UP_MODEL_ONLY,
            RULE_SIDEWAYS_REDUCE,
            RULE_FALLBACK_MODEL_ONLY,
        }
        assert len(rules) == 4

    def test_sideways_multiplier_is_half(self):
        assert SIDEWAYS_EXPOSURE_MULTIPLIER == 0.5

    def test_default_multiplier_is_one(self):
        assert DEFAULT_EXPOSURE_MULTIPLIER == 1.0
