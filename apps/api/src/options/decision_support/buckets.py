"""Frozen bucket-classification rules (Phase 11I).

Each scored row is assigned one BUCKET via a deterministic precedence
cascade. Buckets are LABELS — they never imply action, never say
"recommended", never say "best".

Pure-fn module. Stdlib only.
"""

from __future__ import annotations

from typing import Any

from apps.api.src.options.paper.expiration import (
    FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
    FLAG_MISSING_SETTLEMENT,
    FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
)


# ---------------------------------------------------------------------------
# Frozen bucket tokens — UI consumes verbatim
# ---------------------------------------------------------------------------

BUCKET_HIGH_REVIEW_PRIORITY  = "HIGH_REVIEW_PRIORITY"
BUCKET_DATA_QUALITY_REVIEW   = "NEEDS_REVIEW_DATA_QUALITY"
BUCKET_MODEL_LIMITATION_REVIEW = "NEEDS_REVIEW_MODEL_LIMITATION"
BUCKET_EXCLUDED              = "EXCLUDED_BY_REVIEW_RULES"
BUCKET_NEUTRAL               = "NEUTRAL_NEEDS_REVIEW"

ALL_BUCKETS: tuple[str, ...] = (
    BUCKET_HIGH_REVIEW_PRIORITY,
    BUCKET_DATA_QUALITY_REVIEW,
    BUCKET_MODEL_LIMITATION_REVIEW,
    BUCKET_NEUTRAL,
    BUCKET_EXCLUDED,
)

BUCKET_LABELS: dict[str, str] = {
    BUCKET_HIGH_REVIEW_PRIORITY:    "High review priority",
    BUCKET_DATA_QUALITY_REVIEW:     "Needs review — data quality",
    BUCKET_MODEL_LIMITATION_REVIEW: "Needs review — model limitation",
    BUCKET_NEUTRAL:                 "Neutral — needs human review",
    BUCKET_EXCLUDED:                "Excluded by review rules",
}

# Frozen thresholds — operator-locked
HIGH_PRIORITY_MIN_SCORE = 75
EXCLUDED_MAX_SCORE      = 49

SEVERE_FLAGS: tuple[str, ...] = (
    FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
    FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
    FLAG_MISSING_SETTLEMENT,
)

DATA_QUALITY_PENALTY_CODES: tuple[str, ...] = (
    "MISSING_GREEKS",
    "MISSING_IV",
    "NO_PRICE_HISTORY",
    "INSUFFICIENT_IV_HISTORY",
    "INSUFFICIENT_VOLUME_HISTORY",
    "NO_OPEN_INTEREST",
)


def has_severe_flag(score: dict[str, Any]) -> bool:
    return any(f in SEVERE_FLAGS for f in (score.get("flags") or []))


def severe_flag_count(score: dict[str, Any]) -> int:
    return sum(1 for f in (score.get("flags") or []) if f in SEVERE_FLAGS)


def has_data_quality_penalty(score: dict[str, Any]) -> bool:
    return any(
        p.get("code") in DATA_QUALITY_PENALTY_CODES
        for p in (score.get("penalties") or [])
    )


# ---------------------------------------------------------------------------
# Classification cascade — single bucket per row
# ---------------------------------------------------------------------------

def classify(score: dict[str, Any]) -> tuple[str, str]:
    """Return (bucket_token, plain-English inclusion/exclusion reason).

    Precedence (frozen):
      1. EXCLUDED if (score <= EXCLUDED_MAX_SCORE) OR (qualified is False
         AND severe flag present) OR (qualified is False AND severe flag
         absent but score < HIGH_PRIORITY_MIN_SCORE)
      2. MODEL_LIMITATION_REVIEW if any severe flag present
      3. DATA_QUALITY_REVIEW if any data-quality penalty present
      4. HIGH_REVIEW_PRIORITY if score >= HIGH_PRIORITY_MIN_SCORE AND
         qualified AND no severe flag AND no data-quality penalty
      5. NEUTRAL otherwise (mid-range, qualified, clean — operator
         judgment needed)
    """
    total = int(score.get("total_score") or 0)
    qualified = bool(score.get("qualified"))
    severe = has_severe_flag(score)
    dq_pen = has_data_quality_penalty(score)

    # 1. Excluded
    if total <= EXCLUDED_MAX_SCORE:
        return (
            BUCKET_EXCLUDED,
            f"Excluded: total_score={total} <= {EXCLUDED_MAX_SCORE}.",
        )
    if not qualified and not severe:
        return (
            BUCKET_EXCLUDED,
            "Excluded: rejected by rule (qualified=false, no severe flag).",
        )

    # 2. Model limitation
    if severe:
        if not qualified or total <= EXCLUDED_MAX_SCORE:
            return (
                BUCKET_EXCLUDED,
                "Excluded: severe model-limitation flag combined with "
                "rule rejection or below-threshold score.",
            )
        return (
            BUCKET_MODEL_LIMITATION_REVIEW,
            "Surfaced for human review because at least one severe "
            "model-limitation flag (pin risk / assignment simplified "
            "exit / missing settlement) is present.",
        )

    # 3. Data quality
    if dq_pen:
        return (
            BUCKET_DATA_QUALITY_REVIEW,
            "Surfaced for human review because at least one data-quality "
            "penalty (missing IV / Greeks / realized vol / OI / IV "
            "history) reduced the evaluation score.",
        )

    # 4. High review priority
    if (qualified and total >= HIGH_PRIORITY_MIN_SCORE
            and not severe and not dq_pen):
        return (
            BUCKET_HIGH_REVIEW_PRIORITY,
            f"High review priority: total_score={total} >= "
            f"{HIGH_PRIORITY_MIN_SCORE}, qualified=true, no severe flags, "
            f"no data-quality penalties.",
        )

    # 5. Neutral
    return (
        BUCKET_NEUTRAL,
        "Neutral score range — requires human judgment; no severe "
        "model-limitation flags or data-quality penalties present.",
    )
