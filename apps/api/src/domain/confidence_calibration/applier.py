"""Per-signal confidence adjustment. Flag-gated, fully logged.

When ENABLE_CONFIDENCE_CALIBRATION=False → returns original confidence verbatim
with status=skipped_flag_disabled. No math happens.

When enabled → looks up bucket, applies guardrail-enforced factor.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from loguru import logger

from apps.api.src.config import settings
from apps.api.src.domain.confidence_calibration.policy import (
    APPLIED,
    SKIP_DISABLED,
    SKIP_NO_DATA,
    BucketFactor,
    bucket_for,
)


@dataclass(frozen=True)
class AdjustmentResult:
    original_confidence: float
    adjusted_confidence: float
    applied_factor: float
    bucket: str | None
    sample_count: int
    status: str          # applied | skipped_* (see policy)
    skip_reason: str | None

    def to_dict(self) -> dict:
        return {
            "original_confidence": round(self.original_confidence, 6),
            "adjusted_confidence": round(self.adjusted_confidence, 6),
            "applied_factor": round(self.applied_factor, 6),
            "bucket": self.bucket,
            "sample_count": self.sample_count,
            "status": self.status,
            "skip_reason": self.skip_reason,
        }


def _to_float(v: Decimal | float | int | None) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def adjust_confidence(
    confidence: Decimal | float | None,
    factors: dict[str, BucketFactor] | None,
    *,
    enabled: bool | None = None,
    signal_id: str | None = None,
) -> AdjustmentResult:
    """Apply bucket-level calibration factor to a single confidence value.

    Returns AdjustmentResult. NEVER raises. Always logs.
    """
    flag = settings.ENABLE_CONFIDENCE_CALIBRATION if enabled is None else enabled
    c = _to_float(confidence)
    if c is None:
        c = 0.0

    # Identity when disabled — no calibration math at all.
    if not flag:
        result = AdjustmentResult(
            original_confidence=c, adjusted_confidence=c,
            applied_factor=1.0, bucket=None, sample_count=0,
            status=SKIP_DISABLED, skip_reason=SKIP_DISABLED,
        )
        logger.debug(
            "[calibration] signal={} {}",
            signal_id or "?", result.to_dict(),
        )
        return result

    label = bucket_for(c)
    if label is None or factors is None or label not in factors:
        result = AdjustmentResult(
            original_confidence=c, adjusted_confidence=c,
            applied_factor=1.0, bucket=label, sample_count=0,
            status=SKIP_NO_DATA, skip_reason=SKIP_NO_DATA,
        )
        logger.info(
            "[calibration] signal={} {}",
            signal_id or "?", result.to_dict(),
        )
        return result

    bf: BucketFactor = factors[label]
    factor = bf.factor
    adjusted = c * factor

    result = AdjustmentResult(
        original_confidence=c, adjusted_confidence=adjusted,
        applied_factor=factor, bucket=label,
        sample_count=bf.sample_count,
        status=bf.status,
        skip_reason=bf.skip_reason,
    )
    logger.info(
        "[calibration] signal={} {}",
        signal_id or "?", result.to_dict(),
    )
    return result
