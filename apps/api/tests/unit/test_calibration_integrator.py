"""Phase 4 unit tests — batch integrator + global limiter."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.src.config import settings
from apps.api.src.domain.confidence_calibration.integrator import (
    BatchResult,
    calibrate_batch,
)
from apps.api.src.domain.confidence_calibration.policy import (
    APPLIED,
    SKIP_DISABLED,
    BucketFactor,
    derive_factors,
)


def _cal(bucket: str, count: int, win_rate: float | None):
    return {"bucket": bucket, "count": count, "win_rate": win_rate, "avg_return": 0.01}


# ---------------------------------------------------------------------------
# Flag OFF path
# ---------------------------------------------------------------------------


class TestFlagOff:
    def test_identity_with_flag_off(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", False)
        signals = [
            {"signal_id": "a", "confidence": 0.3},
            {"signal_id": "b", "confidence": 0.7},
        ]
        factors = derive_factors([_cal("0.6-0.8", 100, 0.9)], None)
        r = calibrate_batch(signals, factors)

        assert r.signals_total == 2
        assert r.signals_adjusted == 0
        assert r.adjustments["a"].adjusted_confidence == 0.3
        assert r.adjustments["b"].adjusted_confidence == 0.7
        assert r.avg_shift_before_scaling == 0.0
        assert r.avg_shift_after_scaling == 0.0
        assert r.limiter_triggered is False
        assert all(a.status == SKIP_DISABLED for a in r.adjustments.values())

    def test_effective_confidence_returns_fallback_when_disabled(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", False)
        r = calibrate_batch([{"signal_id": "x", "confidence": 0.5}], None)
        assert r.effective_confidence("x", fallback=0.5) == 0.5
        assert r.effective_confidence("missing", fallback=0.42) == 0.42


# ---------------------------------------------------------------------------
# Flag ON path + shadow mode
# ---------------------------------------------------------------------------


class TestFlagOnShadow:
    def test_shadow_computes_but_effective_is_fallback(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", True)
        monkeypatch.setattr(settings, "CALIBRATION_SHADOW_MODE", True)
        factors = derive_factors([_cal("0.4-0.6", 100, 0.6)], None)
        # Bump max_avg_shift high enough to avoid limiter scaling this 1-signal test
        r = calibrate_batch(
            [{"signal_id": "a", "confidence": 0.5}], factors, max_avg_shift=1.0,
        )

        # Calibration ran — factor 1.2, adjusted 0.6
        assert r.adjustments["a"].adjusted_confidence == pytest.approx(0.6, abs=1e-9)
        assert r.adjustments["a"].factor_used == 1.2
        # But effective_confidence returns fallback
        assert r.effective_confidence("a", fallback=0.5) == 0.5
        assert r.shadow_mode is True


class TestFlagOnLive:
    def test_applies_adjustment_in_live_mode(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", True)
        monkeypatch.setattr(settings, "CALIBRATION_SHADOW_MODE", False)
        factors = derive_factors([_cal("0.4-0.6", 100, 0.6)], None)
        # High budget to prove live-mode application on pure raw factor
        r = calibrate_batch(
            [{"signal_id": "a", "confidence": 0.5}], factors, max_avg_shift=1.0,
        )

        assert r.adjustments["a"].adjusted_confidence == pytest.approx(0.6, abs=1e-9)
        assert r.effective_confidence("a", fallback=0.5) == pytest.approx(0.6, abs=1e-9)


# ---------------------------------------------------------------------------
# Global impact limiter
# ---------------------------------------------------------------------------


class TestGlobalLimiter:
    def test_limiter_triggers_when_avg_shift_exceeds_budget(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", True)
        monkeypatch.setattr(settings, "CALIBRATION_SHADOW_MODE", False)
        # Max shift 0.05 — force heavy calibration
        monkeypatch.setattr(settings, "CALIBRATION_MAX_AVG_SHIFT", 0.05)

        # Multiple signals all in 0.4-0.6 bucket, factor=1.2 (0.5*1.2=0.6, shift=0.1)
        factors = derive_factors([_cal("0.4-0.6", 100, 0.6)], None)
        signals = [
            {"signal_id": f"s{i}", "confidence": 0.5} for i in range(5)
        ]
        r = calibrate_batch(signals, factors)

        # Before limiter: each shift = 0.5 * (1.2-1) = 0.10 → avg 0.10 > 0.05
        assert r.avg_shift_before_scaling == pytest.approx(0.10, abs=1e-6)
        assert r.limiter_triggered is True
        # Scaled: ratio = 0.05 / 0.10 = 0.5 → factor 1 + 0.2*0.5 = 1.1
        # Adjusted confidence = 0.5 * 1.1 = 0.55 → shift 0.05
        assert r.avg_shift_after_scaling == pytest.approx(0.05, abs=1e-6)
        assert r.scale_down_ratio == pytest.approx(0.5, abs=1e-6)
        assert r.adjustments["s0"].factor_used == pytest.approx(1.1, abs=1e-6)
        assert r.adjustments["s0"].adjusted_confidence == pytest.approx(0.55, abs=1e-6)

    def test_limiter_not_triggered_when_shift_within_budget(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", True)
        monkeypatch.setattr(settings, "CALIBRATION_SHADOW_MODE", False)
        # Factor 1.1 (0.55/0.5), shift per signal 0.05 — exactly budget
        factors = derive_factors([_cal("0.4-0.6", 100, 0.55)], None)
        signals = [{"signal_id": "s", "confidence": 0.5}]
        r = calibrate_batch(signals, factors, max_avg_shift=0.05)
        # avg_shift = 0.05 → NOT > budget → no trigger (strict >)
        assert r.limiter_triggered is False
        assert r.avg_shift_before_scaling == pytest.approx(0.05, abs=1e-6)
        assert r.avg_shift_after_scaling == pytest.approx(0.05, abs=1e-6)

    def test_limiter_preserves_identity_when_factor_already_1(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", True)
        monkeypatch.setattr(settings, "CALIBRATION_SHADOW_MODE", False)
        # No data → all factors = 1.0 → zero shift → no limiter needed
        r = calibrate_batch(
            [{"signal_id": "x", "confidence": 0.5}], factors=None,
        )
        assert r.limiter_triggered is False
        assert r.avg_shift_before_scaling == 0.0
        assert r.adjustments["x"].adjusted_confidence == 0.5


# ---------------------------------------------------------------------------
# Determinism + invariants
# ---------------------------------------------------------------------------


class TestInvariants:
    def test_same_input_same_output(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", True)
        monkeypatch.setattr(settings, "CALIBRATION_SHADOW_MODE", False)
        factors = derive_factors([_cal("0.4-0.6", 100, 0.6)], None)
        signals = [{"signal_id": "a", "confidence": 0.5}, {"signal_id": "b", "confidence": 0.3}]
        r1 = calibrate_batch(signals, factors)
        r2 = calibrate_batch(signals, factors)
        assert r1.avg_shift_before_scaling == r2.avg_shift_before_scaling
        assert r1.avg_shift_after_scaling == r2.avg_shift_after_scaling
        assert {k: v.adjusted_confidence for k, v in r1.adjustments.items()} == \
               {k: v.adjusted_confidence for k, v in r2.adjustments.items()}

    def test_no_duplicate_signals(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", True)
        signals = [{"signal_id": f"s{i}", "confidence": 0.5} for i in range(10)]
        r = calibrate_batch(signals, None)
        assert len(r.adjustments) == 10
        assert set(r.adjustments.keys()) == {f"s{i}" for i in range(10)}

    def test_no_missing_signals(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", True)
        signals = [{"signal_id": "only_one", "confidence": 0.5}]
        r = calibrate_batch(signals, None)
        assert r.signals_total == 1
        assert "only_one" in r.adjustments

    def test_empty_input_no_crash(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", True)
        r = calibrate_batch([], None)
        assert r.signals_total == 0
        assert r.adjustments == {}
        assert r.avg_shift_before_scaling == 0.0
        assert r.limiter_triggered is False

    def test_flag_off_produces_zero_shift_even_with_factors(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_CALIBRATION", False)
        factors = derive_factors([_cal("0.4-0.6", 100, 0.99)], None)
        signals = [{"signal_id": f"s{i}", "confidence": 0.5} for i in range(10)]
        r = calibrate_batch(signals, factors)
        assert r.avg_shift_before_scaling == 0.0
        assert r.avg_shift_after_scaling == 0.0
        # All unchanged
        assert all(a.adjusted_confidence == 0.5 for a in r.adjustments.values())
