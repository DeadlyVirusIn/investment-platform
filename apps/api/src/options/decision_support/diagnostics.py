"""Decision support diagnostics (Phase 11I).

Aggregates exclusion drivers + bucket counts from the review queue.
Compute-on-read; NEVER writes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from apps.api.src.options.decision_support.buckets import (
    ALL_BUCKETS,
    BUCKET_EXCLUDED,
    BUCKET_LABELS,
    DATA_QUALITY_PENALTY_CODES,
    SEVERE_FLAGS,
    classify,
)
from apps.api.src.options.decision_support.review_queue import (
    DECISION_SUPPORT_DISCLAIMER,
    HUMAN_REVIEW_NOTE,
)
from apps.api.src.options.evaluation.score_service import list_scores


def get_diagnostics(
    session: Session,
    *,
    lookback_days: int = 14,
) -> dict[str, Any]:
    raw = list_scores(
        session, lookback_days=lookback_days, limit=10_000,
    )
    by_bucket: dict[str, int] = {b: 0 for b in ALL_BUCKETS}
    severe_counter: dict[str, int] = {f: 0 for f in SEVERE_FLAGS}
    dq_counter: dict[str, int] = {f: 0 for f in DATA_QUALITY_PENALTY_CODES}
    n_excluded_low_score = 0
    n_excluded_unqualified = 0
    n_excluded_severe_combo = 0

    for s in raw["scores"]:
        bucket, _reason = classify(s)
        by_bucket[bucket] += 1
        for f in s.get("flags") or []:
            if f in severe_counter:
                severe_counter[f] += 1
        for p in s.get("penalties") or []:
            code = p.get("code")
            if code in dq_counter:
                dq_counter[code] += 1
        if bucket == BUCKET_EXCLUDED:
            score = int(s.get("total_score") or 0)
            qualified = bool(s.get("qualified"))
            severe = any(
                f in SEVERE_FLAGS for f in s.get("flags") or []
            )
            if severe and not qualified:
                n_excluded_severe_combo += 1
            elif not qualified:
                n_excluded_unqualified += 1
            else:
                n_excluded_low_score += 1

    return {
        "by_bucket": [
            {"bucket": b, "label": BUCKET_LABELS[b], "count": by_bucket[b]}
            for b in ALL_BUCKETS
        ],
        "exclusion_drivers": {
            "low_score": int(n_excluded_low_score),
            "unqualified_no_severe": int(n_excluded_unqualified),
            "severe_combined_with_unqualified_or_low_score":
                int(n_excluded_severe_combo),
        },
        "common_severe_flag_drivers": [
            {"code": f, "count": severe_counter[f]}
            for f in SEVERE_FLAGS if severe_counter[f] > 0
        ],
        "common_data_quality_penalty_drivers": [
            {"code": f, "count": dq_counter[f]}
            for f in DATA_QUALITY_PENALTY_CODES if dq_counter[f] > 0
        ],
        "human_review_note": HUMAN_REVIEW_NOTE,
        "decision_support_disclaimer": DECISION_SUPPORT_DISCLAIMER,
        "observation_only_notice":
            "Observation only — not investment advice or execution guidance",
    }
