"""Tests for governance.drift_monitor."""

from __future__ import annotations

import random

from src.governance.drift_monitor import (
    aggregate,
    feature_drift,
    performance_drift,
    regime_drift,
)


def test_feature_drift_no_shift_ok():
    rng = random.Random(42)
    base = [rng.gauss(0, 1) for _ in range(500)]
    curr = [rng.gauss(0, 1) for _ in range(500)]
    r = feature_drift(base, curr, name="x")
    assert r.severity == "OK"
    assert r.statistic is not None


def test_feature_drift_large_shift_detected():
    rng = random.Random(42)
    base = [rng.gauss(0, 1) for _ in range(500)]
    curr = [rng.gauss(3, 1) for _ in range(500)]
    r = feature_drift(base, curr, name="x")
    assert r.severity in {"WARN", "CRITICAL"}


def test_feature_drift_insufficient_samples():
    r = feature_drift([1.0, 2.0], [3.0, 4.0])
    assert r.severity == "INSUFFICIENT"


def test_performance_drift_collapse_detected():
    rng = random.Random(0)
    base = [rng.gauss(0.001, 0.01) for _ in range(120)]
    curr = [rng.gauss(-0.005, 0.01) for _ in range(120)]
    r = performance_drift(base, curr)
    assert r.severity in {"WARN", "CRITICAL"}


def test_performance_drift_no_change_ok():
    rng = random.Random(0)
    base = [rng.gauss(0, 0.01) for _ in range(120)]
    curr = [rng.gauss(0, 0.01) for _ in range(120)]
    r = performance_drift(base, curr)
    assert r.severity == "OK"


def test_performance_drift_insufficient():
    r = performance_drift([0.01] * 5, [0.02] * 5)
    assert r.severity == "INSUFFICIENT"


def test_regime_drift_detected():
    base = ["TREND"] * 80 + ["CHOP"] * 20
    curr = ["TREND"] * 30 + ["CHOP"] * 70
    r = regime_drift(base, curr)
    assert r.severity in {"WARN", "CRITICAL"}


def test_regime_drift_stable_ok():
    base = ["TREND"] * 50 + ["CHOP"] * 50
    curr = ["TREND"] * 48 + ["CHOP"] * 52
    r = regime_drift(base, curr)
    assert r.severity == "OK"


def test_regime_drift_insufficient():
    r = regime_drift(["A"], ["A"])
    assert r.severity == "INSUFFICIENT"


def test_aggregate_picks_worst_severity():
    a = feature_drift([0.0] * 500, [3.0] * 500)
    b = performance_drift([0.0] * 120, [0.0] * 120)
    out = aggregate([a, b])
    assert out["overall_severity"] in {"WARN", "CRITICAL"}
    assert any(r["severity"] in {"WARN", "CRITICAL"} for r in out["results"])
    assert isinstance(out["any_critical"], bool)
    assert isinstance(out["any_warn"], bool)
