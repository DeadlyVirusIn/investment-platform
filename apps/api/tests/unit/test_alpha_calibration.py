"""SYSTEM-ALPHA-6 — calibration rule correctness + safety gates."""

from __future__ import annotations

from apps.api.src.alpha.calibration import (
    AUTO_MIN_CONFIDENCE, AUTO_MIN_SAMPLE, CalibrationRec, PARAM_BOUNDS,
    _rule_engine_underperf, _rule_raise_data_confidence,
    _rule_reduce_exploratory,
)


def _rets(values):
    return [{"net_ret_pct": v, "engine": "B",
             "exploratory_paper": False} for v in values]


# ---------------------------------------------------------------------------
# auto-apply gates
# ---------------------------------------------------------------------------

def test_auto_applicable_requires_confidence_and_sample():
    r = CalibrationRec(
        parameter_key="paper_exploratory_size_multiplier",
        old_value=0.25, new_value=0.15,
        reason="x", confidence=0.95, sample_size=100,
    )
    assert r.auto_applicable is True
    r2 = CalibrationRec(**{**r.__dict__, "confidence": 0.80})
    assert r2.auto_applicable is False
    r3 = CalibrationRec(**{**r.__dict__, "sample_size": 30})
    assert r3.auto_applicable is False


def test_auto_applicable_rejects_size_increase():
    r = CalibrationRec(
        parameter_key="paper_exploratory_size_multiplier",
        old_value=0.10, new_value=0.25,     # attacker tries to scale up
        reason="x", confidence=0.99, sample_size=500,
    )
    assert r.auto_applicable is False


def test_auto_min_constants_are_strict():
    assert AUTO_MIN_CONFIDENCE >= 0.85
    assert AUTO_MIN_SAMPLE >= 50


# ---------------------------------------------------------------------------
# rules
# ---------------------------------------------------------------------------

def test_rule_reduce_exploratory_small_sample_noop():
    rows = [{"net_ret_pct": -1.0} for _ in range(15)]
    assert _rule_reduce_exploratory(rows, {}) is None


def test_rule_reduce_exploratory_triggers_when_losing():
    rows = [{"net_ret_pct": -0.5} for _ in range(25)]
    r = _rule_reduce_exploratory(rows, {})
    assert r is not None
    assert r.parameter_key == "paper_exploratory_size_multiplier"
    assert r.new_value < r.old_value   # reduction only
    assert r.risk_reducing is True


def test_rule_reduce_exploratory_no_change_when_positive():
    rows = [{"net_ret_pct": 0.5} for _ in range(25)]
    assert _rule_reduce_exploratory(rows, {}) is None


def test_rule_engine_underperf_requires_sharpe_and_avg_negative():
    # Negative avg but positive sharpe trick can't happen; test standard case
    rows = _rets([-1, -2, -1, -3, -1, -2] * 6)    # 36 rows
    r = _rule_engine_underperf("B", rows, {})
    assert r is not None
    assert r.parameter_key == "engine_size_multiplier_B"
    assert r.new_value <= 0.5
    assert r.risk_reducing


def test_rule_engine_underperf_small_sample_noop():
    rows = _rets([-1, -2, -1])
    assert _rule_engine_underperf("B", rows, {}) is None


def test_rule_engine_underperf_positive_avg_noop():
    rows = _rets([1, 2, 1, 2] * 10)
    assert _rule_engine_underperf("B", rows, {}) is None


def test_rule_raise_data_confidence_low_winrate():
    # 50 rows, 15 wins → 30% win rate
    rows = [{"net_ret_pct": 1.0 if i < 15 else -1.0} for i in range(50)]
    r = _rule_raise_data_confidence(rows, {})
    assert r is not None
    assert r.parameter_key == "min_data_confidence"
    assert r.new_value > r.old_value          # tightens upward
    # But marked risk_reducing: tightening filter reduces trade count/risk
    assert r.risk_reducing is True


def test_rule_raise_data_confidence_ok_winrate_noop():
    rows = [{"net_ret_pct": 1.0 if i < 30 else -1.0} for i in range(50)]
    assert _rule_raise_data_confidence(rows, {}) is None


# ---------------------------------------------------------------------------
# bounds
# ---------------------------------------------------------------------------

def test_param_bounds_fixed():
    assert PARAM_BOUNDS["paper_exploratory_size_multiplier"]["max"] <= 0.25
    assert PARAM_BOUNDS["engine_size_multiplier_A"]["max"] <= 1.0
    assert PARAM_BOUNDS["engine_size_multiplier_B"]["max"] <= 1.0
    assert PARAM_BOUNDS["min_data_confidence"]["min"] >= 0.3
