"""Phase 4 — batch calibration integrator.

Single entry-point for wiring calibration into a daily run. Enforces:
  - global impact limiter (rescales factors toward 1.0 if avg shift too large)
  - aggregate logging (before/after shift, counts)
  - shadow-mode override (produces adjustments but caller ignores them)

Deterministic. Pure. No DB. No ML.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from loguru import logger

from apps.api.src.config import settings
from apps.api.src.domain.confidence_calibration.applier import (
    AdjustmentResult,
    adjust_confidence,
)
from apps.api.src.domain.confidence_calibration.policy import (
    APPLIED,
    BucketFactor,
    bucket_for,
)


@dataclass
class BatchAdjustment:
    signal_id: str
    original_confidence: float
    adjusted_confidence: float        # post-limiter
    factor_used: float                # post-limiter
    raw_factor: float                 # pre-limiter (from policy)
    bucket: str | None
    status: str
    skip_reason: str | None


@dataclass
class BatchResult:
    adjustments: dict[str, BatchAdjustment] = field(default_factory=dict)
    avg_shift_before_scaling: float = 0.0
    avg_shift_after_scaling: float = 0.0
    signals_total: int = 0
    signals_adjusted: int = 0
    signals_skipped: int = 0
    limiter_triggered: bool = False
    scale_down_ratio: float = 1.0
    shadow_mode: bool = True
    flag_enabled: bool = False

    def effective_confidence(self, signal_id: str, fallback: float) -> float:
        """Return the confidence to use downstream.

        - If flag disabled or shadow_mode on → return fallback (original).
        - Else → return adjusted.
        """
        if not self.flag_enabled or self.shadow_mode:
            return fallback
        adj = self.adjustments.get(signal_id)
        return adj.adjusted_confidence if adj is not None else fallback


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_float(v: Decimal | float | int | None) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _scale_factor(raw_factor: float, ratio: float) -> float:
    """Move factor toward 1.0 by (1 - ratio). ratio in (0, 1]."""
    if ratio >= 1.0:
        return raw_factor
    return 1.0 + (raw_factor - 1.0) * ratio


# ---------------------------------------------------------------------------
# Batch entrypoint
# ---------------------------------------------------------------------------


def calibrate_batch(
    signals_input: list[dict[str, Any]],
    factors: dict[str, BucketFactor] | None,
    *,
    enabled: bool | None = None,
    shadow_mode: bool | None = None,
    max_avg_shift: float | None = None,
) -> BatchResult:
    """Compute per-signal adjustments + apply the global limiter.

    signals_input: list of {signal_id, confidence}. Order irrelevant.
    factors: output of derive_factors() — may be None to force identity.

    Returns a BatchResult. NEVER raises.
    """
    flag = settings.ENABLE_CONFIDENCE_CALIBRATION if enabled is None else enabled
    shadow = settings.CALIBRATION_SHADOW_MODE if shadow_mode is None else shadow_mode
    max_shift = (
        max_avg_shift if max_avg_shift is not None
        else settings.CALIBRATION_MAX_AVG_SHIFT
    )

    result = BatchResult(
        shadow_mode=shadow, flag_enabled=flag,
        signals_total=len(signals_input),
    )

    # Fast path when disabled: all identity, no math.
    if not flag:
        logger.info(
            "[calibration.batch] DISABLED signals={} shadow={} — identity pass",
            len(signals_input), shadow,
        )
        for s in signals_input:
            sid = s.get("signal_id", "")
            c = _to_float(s.get("confidence")) or 0.0
            result.adjustments[sid] = BatchAdjustment(
                signal_id=sid, original_confidence=c, adjusted_confidence=c,
                factor_used=1.0, raw_factor=1.0, bucket=bucket_for(c),
                status="skipped_flag_disabled", skip_reason="skipped_flag_disabled",
            )
        return result

    # --- Phase 1: compute raw adjustments via policy ------------------------
    raw_adjustments: list[AdjustmentResult] = []
    sids: list[str] = []
    for s in signals_input:
        sid = s.get("signal_id", "")
        sids.append(sid)
        adj = adjust_confidence(
            s.get("confidence"), factors, enabled=True, signal_id=sid,
        )
        raw_adjustments.append(adj)

    # --- Phase 2: compute batch avg_shift before limiter --------------------
    shifts_before = [
        abs(a.adjusted_confidence - a.original_confidence) for a in raw_adjustments
    ]
    avg_shift_before = statistics.fmean(shifts_before) if shifts_before else 0.0
    result.avg_shift_before_scaling = round(avg_shift_before, 6)

    # --- Phase 3: limiter — scale all factors toward 1.0 if over budget -----
    # Use small epsilon so FP noise at exact budget doesn't falsely trigger.
    LIMITER_EPSILON = 1e-9
    scale_ratio = 1.0
    if max_shift > 0 and (avg_shift_before - max_shift) > LIMITER_EPSILON:
        scale_ratio = max_shift / avg_shift_before
        result.limiter_triggered = True
    result.scale_down_ratio = round(scale_ratio, 6)

    # --- Phase 4: recompute adjustments with scaled factor -----------------
    shifts_after: list[float] = []
    for sid, raw in zip(sids, raw_adjustments):
        scaled_factor = _scale_factor(raw.applied_factor, scale_ratio)
        final_conf = raw.original_confidence * scaled_factor
        shift = abs(final_conf - raw.original_confidence)
        shifts_after.append(shift)
        result.adjustments[sid] = BatchAdjustment(
            signal_id=sid,
            original_confidence=raw.original_confidence,
            adjusted_confidence=final_conf,
            factor_used=scaled_factor,
            raw_factor=raw.applied_factor,
            bucket=raw.bucket,
            status=raw.status,
            skip_reason=raw.skip_reason,
        )
        if raw.status == APPLIED:
            result.signals_adjusted += 1
        else:
            result.signals_skipped += 1

    result.avg_shift_after_scaling = round(
        statistics.fmean(shifts_after) if shifts_after else 0.0, 6,
    )

    logger.info(
        "[calibration.batch] signals={} adjusted={} skipped={} "
        "avg_shift_before={:.6f} avg_shift_after={:.6f} "
        "limiter_triggered={} scale_ratio={:.4f} shadow={}",
        result.signals_total, result.signals_adjusted, result.signals_skipped,
        result.avg_shift_before_scaling, result.avg_shift_after_scaling,
        result.limiter_triggered, result.scale_down_ratio, result.shadow_mode,
    )
    return result
