"""Phase 11U.1 - drift_metrics unit tests (pure-fn)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from apps.api.src.ml import drift_metrics as dm
from apps.api.src.ml.drift_metrics import (
    DriftMetricsError,
    bucket_lift,
    calibration_delta,
    coverage_deltas,
    ks,
    performance_deltas,
    psi,
    psi_boolean,
    psi_categorical,
    psi_numeric,
)


# ---------------------------------------------------------------------------
# PSI
# ---------------------------------------------------------------------------

def test_psi_returns_zero_for_identical_distributions():
    base = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0,
            1.0, 2.0, 3.0, 4.0, 5.0]
    res = psi_numeric(base, base)
    assert res.psi == 0.0


def test_psi_increases_for_shifted_distributions():
    base = list(range(1, 101))
    recent = [v + 50 for v in base]
    res = psi_numeric(base, recent)
    assert res.psi > 0.5


def test_psi_handles_zero_count_bin_via_eps_smoothing():
    # All recent values fall into one bin → other bins have zero count
    base = list(range(1, 101))
    recent = [50] * 30
    res = psi_numeric(base, recent)
    # PSI must be finite (no division by zero, no log(0))
    assert math.isfinite(res.psi)
    assert res.psi > 0


def test_psi_pure_function_deterministic():
    base = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    a = psi_numeric(base, [2, 3, 4, 5, 6, 7, 8, 9])
    b = psi_numeric(base, [2, 3, 4, 5, 6, 7, 8, 9])
    assert a.psi == b.psi


def test_psi_numeric_quantile_bins_locked_to_baseline():
    base = list(range(1, 101))
    res = psi_numeric(base, base)
    assert res.n_baseline == 100
    assert res.n_recent == 100
    # 10 bins by default
    assert len(res.bins) == 10


def test_psi_boolean_two_bins():
    res = psi_boolean(
        [True, True, False, False, False],
        [True, True, True, False, False],
    )
    assert len(res.bins) == 2
    assert math.isfinite(res.psi)


def test_psi_categorical_uses_other_bin_for_unseen():
    base = ["a", "b", "a", "c", "a", "b"]
    recent = ["a", "b", "z", "z"]
    res = psi_categorical(base, recent)
    labels = [b["bin_label"] for b in res.bins]
    assert "OTHER" in labels


def test_psi_returns_finite_when_recent_smaller():
    base = list(range(1, 101))
    recent = [1, 2, 3]
    res = psi_numeric(base, recent)
    assert math.isfinite(res.psi)


def test_psi_dispatcher_detects_numeric():
    base = [1.0, 2.0, 3.0]
    recent = [4.0, 5.0, 6.0]
    res = psi(base, recent)
    assert res.bins  # numeric bins present


def test_psi_dispatcher_detects_boolean():
    res = psi([True, False, True], [True, True, False])
    assert any(b.get("bin_label") in ("True", "False") for b in res.bins)


def test_psi_dispatcher_detects_categorical():
    res = psi(["a", "b", "a"], ["a", "c"])
    assert any("OTHER" == b.get("bin_label") for b in res.bins)


def test_psi_rejects_empty_baseline():
    with pytest.raises(DriftMetricsError):
        psi_numeric([], [1.0, 2.0])


# ---------------------------------------------------------------------------
# KS
# ---------------------------------------------------------------------------

def test_ks_returns_zero_for_identical():
    a = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert ks(a, a) == 0.0


def test_ks_increases_for_shifted_distributions():
    base = list(range(1, 101))
    recent = [v + 50 for v in base]
    assert ks(base, recent) > 0.4


def test_ks_handles_empty_recent_returns_none():
    assert ks([1, 2, 3], []) is None
    assert ks([], [1, 2, 3]) is None


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

def test_calibration_delta_per_bin_correct():
    base = [
        {"bin": "0.0-0.1", "actual_positive_rate": 0.05},
        {"bin": "0.1-0.2", "actual_positive_rate": 0.15},
    ]
    rec = [
        {"bin": "0.0-0.1", "actual_positive_rate": 0.10},
        {"bin": "0.1-0.2", "actual_positive_rate": 0.20},
    ]
    out = calibration_delta(base, rec)
    deltas = {r["bin"]: r["delta"] for r in out.bins}
    assert deltas["0.0-0.1"] == 0.05
    assert deltas["0.1-0.2"] == 0.05


def test_calibration_max_abs_delta():
    base = [
        {"bin": "a", "actual_positive_rate": 0.10},
        {"bin": "b", "actual_positive_rate": 0.50},
    ]
    rec = [
        {"bin": "a", "actual_positive_rate": 0.30},
        {"bin": "b", "actual_positive_rate": 0.40},
    ]
    out = calibration_delta(base, rec)
    assert out.max_abs_bin_delta == 0.20


def test_calibration_handles_missing_bin():
    base = [{"bin": "a", "actual_positive_rate": 0.10}]
    rec = [{"bin": "b", "actual_positive_rate": 0.20}]
    out = calibration_delta(base, rec)
    deltas = {r["bin"]: r["delta"] for r in out.bins}
    # Missing-pair bins → delta is None
    assert deltas["a"] is None
    assert deltas["b"] is None


# ---------------------------------------------------------------------------
# Performance deltas
# ---------------------------------------------------------------------------

def test_performance_auc_delta():
    p = performance_deltas(
        {"auc_macro": 0.6}, {"auc_macro": 0.55},
    )
    assert p.auc_delta == -0.05


def test_performance_brier_delta():
    p = performance_deltas(
        {"brier_score": 0.20}, {"brier_score": 0.24},
    )
    assert p.brier_delta == 0.04


def test_performance_hit_ratio_delta():
    p = performance_deltas(
        {"hit_ratio": 0.50}, {"hit_ratio": 0.42},
    )
    assert p.hit_ratio_delta == -0.08


def test_metrics_reject_negative_brier():
    with pytest.raises(DriftMetricsError):
        performance_deltas({"brier_score": -0.1}, {"brier_score": 0.2})


# ---------------------------------------------------------------------------
# Bucket lift
# ---------------------------------------------------------------------------

def test_bucket_lift_baseline_only():
    base = {
        "SHADOW_LOW":  {"n": 100, "actual_positive_rate": 0.10},
        "SHADOW_HIGH": {"n": 50,  "actual_positive_rate": 0.50},
    }
    out = bucket_lift(base, {})
    assert out.baseline_lift == 5.0
    assert out.recent_lift is None


def test_bucket_lift_recent_only():
    rec = {
        "SHADOW_LOW":  {"n": 50, "actual_positive_rate": 0.20},
        "SHADOW_HIGH": {"n": 30, "actual_positive_rate": 0.40},
    }
    out = bucket_lift({}, rec)
    assert out.recent_lift == 2.0
    assert out.baseline_lift is None


def test_bucket_lift_drop_relative():
    base = {
        "SHADOW_LOW":  {"n": 100, "actual_positive_rate": 0.10},
        "SHADOW_HIGH": {"n": 50,  "actual_positive_rate": 0.50},
    }
    rec = {
        "SHADOW_LOW":  {"n": 100, "actual_positive_rate": 0.20},
        "SHADOW_HIGH": {"n": 50,  "actual_positive_rate": 0.50},
    }
    out = bucket_lift(base, rec)
    # baseline_lift=5; recent_lift=2.5 → drop_rel=0.5
    assert out.baseline_lift == 5.0
    assert out.recent_lift == 2.5
    assert out.lift_drop_rel == 0.5


def test_bucket_lift_zero_baseline_returns_none():
    base = {
        "SHADOW_LOW":  {"n": 100, "actual_positive_rate": 0.0},
        "SHADOW_HIGH": {"n": 50,  "actual_positive_rate": 0.50},
    }
    out = bucket_lift(base, {})
    # Division by zero protected
    assert out.baseline_lift is None


# ---------------------------------------------------------------------------
# Coverage deltas
# ---------------------------------------------------------------------------

def test_coverage_rows_scored_delta_pct():
    out = coverage_deltas(
        {"rows_scored": 1000, "rows_excluded": {}},
        {"rows_scored": 700, "rows_excluded": {}},
    )
    assert out.rows_scored_delta_pct == -0.3


def test_coverage_missingness_delta():
    out = coverage_deltas(
        {"rows_scored": 1000, "rows_excluded": {"missing_features": 30}},
        {"rows_scored": 700,  "rows_excluded": {"missing_features": 70}},
    )
    assert out.missingness_baseline is not None
    assert out.missingness_recent is not None
    assert out.missingness_delta is not None


def test_coverage_provisional_delta():
    out = coverage_deltas(
        {"rows_scored": 1000, "rows_excluded": {"is_provisional": 100}},
        {"rows_scored": 700,  "rows_excluded": {"is_provisional": 200}},
    )
    assert out.provisional_baseline is not None
    assert out.provisional_recent is not None
    assert out.provisional_delta is not None


def test_outlier_rate_delta():
    out = coverage_deltas(
        {"rows_scored": 1000, "rows_excluded": {"outlier": 10}},
        {"rows_scored": 700,  "rows_excluded": {"outlier": 80}},
    )
    assert out.outlier_rate_delta is not None
    assert out.outlier_rate_delta > 0


def test_metrics_no_floating_point_overflow_on_extreme_inputs():
    base = [1e-10] * 100
    recent = [1e10] * 100
    res = psi_numeric(base, recent)
    assert math.isfinite(res.psi)


def test_metrics_pure_no_side_effects():
    base = [1.0, 2.0, 3.0]
    recent = [4.0, 5.0, 6.0]
    a = psi_numeric(base, recent)
    b = psi_numeric(base, recent)
    assert a.psi == b.psi
    assert a.bins == b.bins


# ---------------------------------------------------------------------------
# Boundary scans
# ---------------------------------------------------------------------------

def test_metrics_no_db_imports():
    src = Path(dm.__file__).read_text(encoding="utf-8")
    for tok in (
        "from apps.api.src.db", "INSERT INTO",
        "session.execute", "sqlalchemy",
    ):
        assert tok not in src, (
            f"drift_metrics must not touch DB: {tok!r}"
        )


def test_metrics_no_pickle_load():
    src = Path(dm.__file__).read_text(encoding="utf-8")
    assert "joblib" not in src
    assert "pickle.load" not in src


def test_metrics_no_file_writes():
    src = Path(dm.__file__).read_text(encoding="utf-8")
    for tok in (
        ".write_text(", ".write(", "json.dump(",
    ):
        assert tok not in src, (
            f"drift_metrics must be pure: {tok!r}"
        )
