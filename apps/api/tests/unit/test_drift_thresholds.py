"""Phase 11U.2 - frozen thresholds tests."""

from __future__ import annotations

from apps.api.src.ml import drift_thresholds as t


def test_min_recent_rows_frozen():
    assert t.MIN_RECENT_ROWS == 100


def test_auc_drop_review_frozen():
    assert t.AUC_DROP_REVIEW == 0.05


def test_brier_increase_review_frozen():
    assert t.BRIER_INCREASE_REVIEW == 0.03


def test_hit_ratio_drop_review_frozen():
    assert t.HIT_RATIO_DROP_REVIEW == 0.05


def test_psi_review_frozen():
    assert t.PSI_REVIEW == 0.20


def test_psi_high_review_frozen():
    assert t.PSI_HIGH_REVIEW == 0.35


def test_missingness_increase_review_frozen():
    assert t.MISSINGNESS_INCREASE_REVIEW == 0.10


def test_outlier_rate_increase_review_frozen():
    assert t.OUTLIER_RATE_INCREASE_REVIEW == 0.05


def test_bucket_lift_drop_review_frozen():
    assert t.BUCKET_LIFT_DROP_REVIEW == 0.25


def test_calibration_bin_delta_review_frozen():
    assert t.CALIBRATION_BIN_DELTA_REVIEW == 0.10


def test_coverage_drop_review_frozen():
    assert t.COVERAGE_DROP_REVIEW == 0.30


def test_provisional_rate_increase_review_frozen():
    assert t.PROVISIONAL_RATE_INCREASE_REVIEW == 0.20
