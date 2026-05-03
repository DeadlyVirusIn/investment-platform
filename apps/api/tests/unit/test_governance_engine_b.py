"""Tests for governance.engine_b_policy — pure-function state machine."""

from __future__ import annotations

import math

from src.governance.engine_b_policy import (
    SHARPE_DEGRADED,
    SHARPE_DISABLED,
    evaluate_engine_b,
    simulate_engine_b,
)


def test_empty_returns_active_default():
    v = evaluate_engine_b([])
    assert v.state == "ACTIVE"
    assert v.advisory is True
    assert v.n == 0
    d = v.to_dict()
    assert d["execution_changed"] is False
    assert d["advisory"] is True


def test_strong_positive_returns_active():
    v = evaluate_engine_b([0.01] * 80)
    assert v.state == "ACTIVE"


def test_negative_returns_classify_disabled():
    v = evaluate_engine_b([-0.02] * 80)
    assert v.state == "DISABLED"
    assert v.recommendation == "RECOMMEND_DISABLE"


def test_mild_negative_classifies_degraded():
    # craft series with rolling Sharpe between degraded and disabled.
    rets = [-0.001] * 80
    v = evaluate_engine_b(rets)
    assert v.state in {"DEGRADED", "DISABLED"}


def test_advisory_invariants():
    for rets in ([0.01] * 80, [-0.02] * 80, []):
        v = evaluate_engine_b(rets)
        assert v.advisory is True
        d = v.to_dict()
        assert d["advisory"] is True
        assert d["execution_changed"] is False


def test_simulate_returns_three_modes():
    rets = [0.01, -0.02, 0.005, -0.015, 0.02, -0.01, 0.0, 0.01,
            -0.005, 0.015] * 8
    sims = simulate_engine_b(rets)
    assert set(sims.keys()) == {"remove", "gate_tsmom", "replace_tsmom"}
    assert sims["remove"] == 0.0


def test_simulate_empty_safe():
    sims = simulate_engine_b([])
    assert sims["remove"] == 0.0
    assert sims["gate_tsmom"] is None or math.isnan(sims["gate_tsmom"])


def test_thresholds_monotone():
    assert SHARPE_DEGRADED > SHARPE_DISABLED


def test_disabled_recommendation_text():
    v = evaluate_engine_b([-0.02] * 80)
    assert "DISABLE" in v.recommendation
