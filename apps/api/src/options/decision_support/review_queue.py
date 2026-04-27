"""Review queue assembler (Phase 11I).

Pure read; consumes the Phase 11H evaluation service. NEVER persists.

Builds:
  * Filtered + ranked review queue
  * Per-bucket grouped views (4 buckets + neutral)
  * Detail-row enrichment with bucket label, ranking explanation,
    tie-breakers, exclusion/inclusion reason, severe-flag list

NEVER imports paper.engine mutation modules. NEVER opens trades.
NEVER recommends a strategy.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from apps.api.src.options.decision_support.buckets import (
    ALL_BUCKETS,
    BUCKET_DATA_QUALITY_REVIEW,
    BUCKET_EXCLUDED,
    BUCKET_HIGH_REVIEW_PRIORITY,
    BUCKET_LABELS,
    BUCKET_MODEL_LIMITATION_REVIEW,
    BUCKET_NEUTRAL,
    SEVERE_FLAGS,
    classify,
    has_data_quality_penalty,
    has_severe_flag,
)
from apps.api.src.options.decision_support.ranking import (
    TIE_BREAKERS,
    rank,
)
from apps.api.src.options.evaluation.score_service import list_scores


HUMAN_REVIEW_NOTE = (
    "Human review required — review queues and shortlists are "
    "observational. They are not trade recommendations or execution "
    "guidance."
)

DECISION_SUPPORT_DISCLAIMER = (
    "Review queues are for human inspection only. They are not trade "
    "recommendations or execution guidance."
)


def _attach_review_metadata(score: dict[str, Any]) -> dict[str, Any]:
    bucket_token, reason = classify(score)
    out = dict(score)
    out["bucket"] = bucket_token
    out["bucket_label"] = BUCKET_LABELS[bucket_token]
    out["inclusion_reason"] = reason
    out["severe_flags"] = [
        f for f in (score.get("flags") or []) if f in SEVERE_FLAGS
    ]
    out["has_data_quality_penalty"] = has_data_quality_penalty(score)
    out["has_severe_flag"] = has_severe_flag(score)
    return out


def _filter_and_rank(
    scores: list[dict[str, Any]],
    *,
    qualified_only: bool,
    min_score: int | None,
    exclude_severe_flags: bool,
    bucket: str | None,
) -> list[dict[str, Any]]:
    annotated = [_attach_review_metadata(s) for s in scores]

    def _keep(s: dict[str, Any]) -> bool:
        if qualified_only and not s.get("qualified"):
            return False
        if min_score is not None and int(s.get("total_score") or 0) < min_score:
            return False
        if exclude_severe_flags and s["has_severe_flag"]:
            return False
        if bucket is not None and s["bucket"] != bucket:
            return False
        return True

    kept = [s for s in annotated if _keep(s)]
    excluded_count = len(annotated) - len(kept)
    ranked = rank(kept)
    # surface excluded-count alongside via attribute on first row only would
    # be brittle; orchestrator below recomputes it from caller paths.
    return ranked, excluded_count, annotated  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Public service entry points
# ---------------------------------------------------------------------------

def get_review_queue(
    session: Session,
    *,
    strategy: str | None = None,
    underlying: str | None = None,
    min_score: int | None = None,
    qualified_only: bool = False,
    exclude_severe_flags: bool = False,
    bucket: str | None = None,
    lookback_days: int = 14,
    limit: int = 100,
) -> dict[str, Any]:
    raw = list_scores(
        session, strategy=strategy, underlying=underlying,
        lookback_days=lookback_days, limit=10_000,
    )
    ranked, excluded_count, _annotated = _filter_and_rank(
        raw["scores"],
        qualified_only=qualified_only,
        min_score=min_score,
        exclude_severe_flags=exclude_severe_flags,
        bucket=bucket,
    )
    if limit and len(ranked) > limit:
        ranked = ranked[:limit]
    return {
        "count": len(ranked),
        "excluded_count": int(excluded_count),
        "filters": {
            "strategy": strategy, "underlying": underlying,
            "min_score": min_score, "qualified_only": qualified_only,
            "exclude_severe_flags": exclude_severe_flags,
            "bucket": bucket, "lookback_days": lookback_days,
            "limit": limit,
        },
        "tie_breakers": list(TIE_BREAKERS),
        "review_queue": ranked,
        "human_review_note": HUMAN_REVIEW_NOTE,
        "decision_support_disclaimer": DECISION_SUPPORT_DISCLAIMER,
        "observation_only_notice":
            "Observation only — not investment advice or execution guidance",
    }


def get_review_detail(
    session: Session, *, observation_id: str,
) -> dict[str, Any] | None:
    queue = get_review_queue(
        session, lookback_days=120, limit=10_000,
    )
    for row in queue["review_queue"]:
        if row.get("id") == observation_id:
            row["human_review_note"] = HUMAN_REVIEW_NOTE
            row["decision_support_disclaimer"] = DECISION_SUPPORT_DISCLAIMER
            row["tie_breakers"] = list(TIE_BREAKERS)
            return row
    return None


def get_buckets(
    session: Session,
    *,
    lookback_days: int = 14,
) -> dict[str, Any]:
    """Group ALL scored rows by bucket label. Computed view only —
    NEVER persisted, NEVER mutated by user actions."""
    raw = list_scores(
        session, lookback_days=lookback_days, limit=10_000,
    )
    annotated = [_attach_review_metadata(s) for s in raw["scores"]]
    grouped: dict[str, list[dict[str, Any]]] = {b: [] for b in ALL_BUCKETS}
    for s in annotated:
        grouped[s["bucket"]].append(s)
    out_groups = []
    for token in ALL_BUCKETS:
        rows = rank(grouped[token]) if grouped[token] else []
        out_groups.append({
            "bucket": token,
            "label": BUCKET_LABELS[token],
            "count": len(rows),
            "rows": rows,
        })
    return {
        "groups": out_groups,
        "tie_breakers": list(TIE_BREAKERS),
        "human_review_note": HUMAN_REVIEW_NOTE,
        "decision_support_disclaimer": DECISION_SUPPORT_DISCLAIMER,
        "observation_only_notice":
            "Observation only — not investment advice or execution guidance",
    }


def get_summary(
    session: Session,
    *,
    lookback_days: int = 14,
) -> dict[str, Any]:
    raw = list_scores(
        session, lookback_days=lookback_days, limit=10_000,
    )
    annotated = [_attach_review_metadata(s) for s in raw["scores"]]
    by_bucket: dict[str, int] = {b: 0 for b in ALL_BUCKETS}
    for s in annotated:
        by_bucket[s["bucket"]] += 1
    scores = [int(s.get("total_score") or 0) for s in annotated]
    n = len(scores)
    sorted_s = sorted(scores)
    median = (
        sorted_s[n // 2] if n % 2 == 1
        else (sorted_s[n // 2 - 1] + sorted_s[n // 2]) / 2 if n
        else None
    )
    return {
        "n_total": n,
        "by_bucket": [
            {"bucket": b, "label": BUCKET_LABELS[b], "count": by_bucket[b]}
            for b in ALL_BUCKETS
        ],
        "n_high_review_priority": by_bucket[BUCKET_HIGH_REVIEW_PRIORITY],
        "n_data_quality_review":  by_bucket[BUCKET_DATA_QUALITY_REVIEW],
        "n_model_limitation_review":
            by_bucket[BUCKET_MODEL_LIMITATION_REVIEW],
        "n_neutral":  by_bucket[BUCKET_NEUTRAL],
        "n_excluded": by_bucket[BUCKET_EXCLUDED],
        "median_score": (
            str(round(median, 2)) if median is not None else None
        ),
        "tie_breakers": list(TIE_BREAKERS),
        "human_review_note": HUMAN_REVIEW_NOTE,
        "decision_support_disclaimer": DECISION_SUPPORT_DISCLAIMER,
        "observation_only_notice":
            "Observation only — not investment advice or execution guidance",
    }
