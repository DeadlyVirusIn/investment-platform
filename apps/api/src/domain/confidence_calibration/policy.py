"""Pure policy — derives per-bucket adjustment factors from scorecard data.

All guardrails enforced here:
  1. Sample size floor (count < MIN_SAMPLES → factor = 1.0)
  2. Stability check (|win_rate_7d - win_rate_30d| > DRIFT_THRESHOLD → factor = 1.0)
  3. Clamp (MIN ≤ factor ≤ MAX)

Deterministic. No I/O. No ML.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.api.src.config import settings

# Calibration bucket edges must match computer.CALIBRATION_BUCKETS exactly.
BUCKET_EDGES: list[tuple[float, float, str]] = [
    (0.0, 0.2, "0.0-0.2"),
    (0.2, 0.4, "0.2-0.4"),
    (0.4, 0.6, "0.4-0.6"),
    (0.6, 0.8, "0.6-0.8"),
    (0.8, 1.0001, "0.8-1.0"),
]

SKIP_LOW_SAMPLES = "skipped_low_samples"
SKIP_DRIFT = "skipped_drift"
SKIP_DISABLED = "skipped_flag_disabled"
SKIP_NO_DATA = "skipped_no_data"
APPLIED = "applied"


@dataclass(frozen=True)
class BucketFactor:
    bucket: str
    factor: float
    win_rate: float | None
    sample_count: int
    status: str            # applied | skipped_*
    skip_reason: str | None


def bucket_for(confidence: float | None) -> str | None:
    if confidence is None:
        return None
    for lo, hi, label in BUCKET_EDGES:
        if lo <= confidence < hi:
            return label
    return None


def _clamp(f: float) -> float:
    return max(
        settings.CALIBRATION_FACTOR_MIN,
        min(settings.CALIBRATION_FACTOR_MAX, f),
    )


def _index_by_bucket(calibration_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["bucket"]: row for row in calibration_rows or []}


def derive_factors(
    calibration_30d: list[dict[str, Any]] | None,
    calibration_7d: list[dict[str, Any]] | None,
    *,
    min_samples: int | None = None,
    drift_threshold: float | None = None,
    baseline: float | None = None,
) -> dict[str, BucketFactor]:
    """Compute adjustment factor per bucket.

    calibration_*: list of {bucket, count, win_rate, avg_return}.
    Returns a dict keyed by bucket label. Buckets not present in 30d data
    still appear in output with factor=1.0 and skipped_no_data.
    """
    ms = min_samples if min_samples is not None else settings.CALIBRATION_MIN_SAMPLES
    dt_ = drift_threshold if drift_threshold is not None else settings.CALIBRATION_DRIFT_THRESHOLD
    base = baseline if baseline is not None else settings.CALIBRATION_EXPECTED_BASELINE

    by30 = _index_by_bucket(calibration_30d or [])
    by7 = _index_by_bucket(calibration_7d or [])

    out: dict[str, BucketFactor] = {}
    for _, _, label in BUCKET_EDGES:
        row30 = by30.get(label)
        # No 30d data → no adjustment
        if row30 is None:
            out[label] = BucketFactor(
                bucket=label, factor=1.0, win_rate=None, sample_count=0,
                status=SKIP_NO_DATA, skip_reason=SKIP_NO_DATA,
            )
            continue
        count = int(row30.get("count", 0) or 0)
        wr30 = row30.get("win_rate")
        wr30 = float(wr30) if wr30 is not None else None

        # Guardrail 1 — sample floor
        if count < ms:
            out[label] = BucketFactor(
                bucket=label, factor=1.0,
                win_rate=wr30, sample_count=count,
                status=SKIP_LOW_SAMPLES, skip_reason=SKIP_LOW_SAMPLES,
            )
            continue

        # Guardrail 2 — stability (only if 7d bucket exists + has data)
        row7 = by7.get(label)
        if row7 is not None:
            wr7 = row7.get("win_rate")
            wr7 = float(wr7) if wr7 is not None else None
            if wr30 is not None and wr7 is not None:
                if abs(wr7 - wr30) > dt_:
                    out[label] = BucketFactor(
                        bucket=label, factor=1.0,
                        win_rate=wr30, sample_count=count,
                        status=SKIP_DRIFT, skip_reason=SKIP_DRIFT,
                    )
                    continue

        # Apply: factor = win_rate / baseline, clamped
        if wr30 is None or base <= 0:
            out[label] = BucketFactor(
                bucket=label, factor=1.0, win_rate=wr30, sample_count=count,
                status=SKIP_NO_DATA, skip_reason=SKIP_NO_DATA,
            )
            continue
        raw = wr30 / base
        factor = round(_clamp(raw), 4)
        out[label] = BucketFactor(
            bucket=label, factor=factor,
            win_rate=wr30, sample_count=count,
            status=APPLIED, skip_reason=None,
        )

    return out
