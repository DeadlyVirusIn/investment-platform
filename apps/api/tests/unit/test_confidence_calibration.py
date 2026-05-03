"""Phase 3 calibration unit tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.src.config import settings
from apps.api.src.domain.confidence_calibration.applier import (
    adjust_confidence,
)
from apps.api.src.domain.confidence_calibration.policy import (
    APPLIED,
    SKIP_DISABLED,
    SKIP_DRIFT,
    SKIP_LOW_SAMPLES,
    SKIP_NO_DATA,
    bucket_for,
    derive_factors,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _cal_row(bucket: str, count: int, win_rate: float | None, avg_return: float = 0.01):
    return {
        "bucket": bucket, "count": count, "win_rate": win_rate,
        "avg_return": avg_return,
    }


# ---------------------------------------------------------------------------
# derive_factors — calculation + clamps
# ---------------------------------------------------------------------------


class TestFactorCalculation:
    def test_win_rate_above_baseline_yields_factor_gt_1(self):
        cal30 = [_cal_row("0.4-0.6", count=100, win_rate=0.6)]
        out = derive_factors(cal30, None)
        # 0.6 / 0.5 = 1.2 → clamp cap 1.2
        assert out["0.4-0.6"].factor == 1.2
        assert out["0.4-0.6"].status == APPLIED

    def test_win_rate_below_baseline_yields_factor_lt_1(self):
        cal30 = [_cal_row("0.6-0.8", count=100, win_rate=0.3)]
        out = derive_factors(cal30, None)
        # 0.3 / 0.5 = 0.6 → clamp floor 0.8
        assert out["0.6-0.8"].factor == 0.8
        assert out["0.6-0.8"].status == APPLIED

    def test_baseline_exact_match_yields_1(self):
        cal30 = [_cal_row("0.0-0.2", count=100, win_rate=0.5)]
        out = derive_factors(cal30, None)
        assert out["0.0-0.2"].factor == 1.0
        assert out["0.0-0.2"].status == APPLIED

    def test_raw_factor_within_range_no_clamp(self):
        # 0.55 / 0.5 = 1.1  (between 0.8 and 1.2 — no clamp)
        cal30 = [_cal_row("0.2-0.4", count=100, win_rate=0.55)]
        out = derive_factors(cal30, None)
        assert out["0.2-0.4"].factor == 1.1


class TestClampBehavior:
    def test_extreme_high_win_rate_clamps_to_max(self):
        cal30 = [_cal_row("0.8-1.0", count=100, win_rate=0.99)]
        out = derive_factors(cal30, None)
        assert out["0.8-1.0"].factor == 1.2

    def test_extreme_low_win_rate_clamps_to_min(self):
        cal30 = [_cal_row("0.8-1.0", count=100, win_rate=0.05)]
        out = derive_factors(cal30, None)
        assert out["0.8-1.0"].factor == 0.8


class TestSampleSizeGuardrail:
    def test_below_min_samples_forces_factor_1(self):
        cal30 = [_cal_row("0.4-0.6", count=19, win_rate=0.9)]
        out = derive_factors(cal30, None)
        assert out["0.4-0.6"].factor == 1.0
        assert out["0.4-0.6"].status == SKIP_LOW_SAMPLES

    def test_at_exactly_min_samples_applies(self):
        # 20 is the floor — NOT skipped
        cal30 = [_cal_row("0.4-0.6", count=20, win_rate=0.55)]
        out = derive_factors(cal30, None, min_samples=20)
        assert out["0.4-0.6"].status == APPLIED

    def test_missing_bucket_in_30d_no_data(self):
        out = derive_factors([], None)
        for label, bf in out.items():
            assert bf.factor == 1.0
            assert bf.status == SKIP_NO_DATA


class TestStabilityGuardrail:
    def test_drift_above_threshold_skips(self):
        cal30 = [_cal_row("0.4-0.6", count=100, win_rate=0.6)]
        cal7 = [_cal_row("0.4-0.6", count=30, win_rate=0.9)]
        # |0.9 - 0.6| = 0.30 > 0.15
        out = derive_factors(cal30, cal7)
        assert out["0.4-0.6"].factor == 1.0
        assert out["0.4-0.6"].status == SKIP_DRIFT

    def test_drift_at_threshold_still_applies(self):
        # |0.15 - 0.0| = 0.15 → NOT > threshold → applied
        cal30 = [_cal_row("0.4-0.6", count=100, win_rate=0.45)]
        cal7 = [_cal_row("0.4-0.6", count=30, win_rate=0.60)]
        out = derive_factors(cal30, cal7)
        # diff = 0.15 → allowed. 0.45 / 0.5 = 0.9, clamped (within band)
        assert out["0.4-0.6"].status == APPLIED
        assert out["0.4-0.6"].factor == 0.9

    def test_drift_just_above_threshold_skips(self):
        cal30 = [_cal_row("0.4-0.6", count=100, win_rate=0.45)]
        cal7 = [_cal_row("0.4-0.6", count=30, win_rate=0.61)]
        # diff 0.16 > 0.15
        out = derive_factors(cal30, cal7)
        assert out["0.4-0.6"].status == SKIP_DRIFT

    def test_no_7d_data_still_applies(self):
        cal30 = [_cal_row("0.4-0.6", count=100, win_rate=0.55)]
        out = derive_factors(cal30, None)
        assert out["0.4-0.6"].status == APPLIED


# ---------------------------------------------------------------------------
# adjust_confidence — end-to-end with flag
# ---------------------------------------------------------------------------


class TestApplierFlagOff:
    def test_flag_off_is_identity(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", False)
        cal30 = [_cal_row("0.4-0.6", count=100, win_rate=0.9)]
        factors = derive_factors(cal30, None)
        r = adjust_confidence(0.55, factors)
        assert r.original_confidence == 0.55
        assert r.adjusted_confidence == 0.55
        assert r.applied_factor == 1.0
        assert r.status == SKIP_DISABLED

    def test_flag_off_ignores_all_factors(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", False)
        # Force impossible factor
        from apps.api.src.domain.confidence_calibration.policy import BucketFactor
        factors = {
            "0.4-0.6": BucketFactor(
                bucket="0.4-0.6", factor=1.2, win_rate=0.9,
                sample_count=1000, status=APPLIED, skip_reason=None,
            ),
        }
        r = adjust_confidence(0.5, factors)
        assert r.adjusted_confidence == 0.5   # unchanged


class TestApplierFlagOn:
    def test_flag_on_applies_bucket_factor(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", True)
        cal30 = [_cal_row("0.4-0.6", count=100, win_rate=0.6)]
        factors = derive_factors(cal30, None)
        r = adjust_confidence(Decimal("0.50"), factors)
        # factor 1.2 × 0.50 = 0.60
        assert r.applied_factor == 1.2
        assert r.adjusted_confidence == pytest.approx(0.60, abs=1e-9)
        assert r.status == APPLIED

    def test_flag_on_low_samples_is_identity(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", True)
        cal30 = [_cal_row("0.4-0.6", count=5, win_rate=0.9)]
        factors = derive_factors(cal30, None)
        r = adjust_confidence(0.5, factors)
        assert r.applied_factor == 1.0
        assert r.adjusted_confidence == 0.5
        assert r.status == SKIP_LOW_SAMPLES

    def test_flag_on_drift_is_identity(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", True)
        cal30 = [_cal_row("0.4-0.6", count=100, win_rate=0.6)]
        cal7 = [_cal_row("0.4-0.6", count=30, win_rate=0.95)]
        factors = derive_factors(cal30, cal7)
        r = adjust_confidence(0.5, factors)
        assert r.applied_factor == 1.0
        assert r.adjusted_confidence == 0.5
        assert r.status == SKIP_DRIFT

    def test_unknown_bucket_is_identity(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", True)
        r = adjust_confidence(0.5, factors={})
        assert r.adjusted_confidence == 0.5
        assert r.status == SKIP_NO_DATA

    def test_none_confidence_treated_as_zero(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", True)
        r = adjust_confidence(None, factors={})
        assert r.original_confidence == 0.0
        assert r.adjusted_confidence == 0.0


class TestDeterminism:
    def test_same_inputs_same_output(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", True)
        cal30 = [_cal_row("0.4-0.6", count=50, win_rate=0.55)]
        f1 = derive_factors(cal30, None)
        f2 = derive_factors(cal30, None)
        assert f1 == f2
        r1 = adjust_confidence(0.5, f1)
        r2 = adjust_confidence(0.5, f2)
        assert r1 == r2


class TestBucketHelper:
    def test_bucket_for_boundaries(self):
        assert bucket_for(0.0) == "0.0-0.2"
        assert bucket_for(0.2) == "0.2-0.4"
        assert bucket_for(0.5) == "0.4-0.6"
        assert bucket_for(0.79) == "0.6-0.8"
        assert bucket_for(0.8) == "0.8-1.0"
        assert bucket_for(1.0) == "0.8-1.0"
        assert bucket_for(None) is None
