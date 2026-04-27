"""Neutral A vs B factual comparison (Phase 11J).

NEVER says "better" / "worse" / "choose" / "avoid". Output is purely
factual deltas + side-by-side fact lists.

Pure-fn module. Stdlib only.
"""

from __future__ import annotations

from typing import Any

from apps.api.src.options.decision_support.buckets import (
    BUCKET_LABELS,
    SEVERE_FLAGS,
)


def _liquidity_score(row: dict[str, Any]) -> int:
    for c in row.get("components") or []:
        if c.get("component") == "liquidity":
            return int(c.get("score") or 0)
    return 0


def _severe_flag_count(row: dict[str, Any]) -> int:
    return sum(1 for f in (row.get("flags") or []) if f in SEVERE_FLAGS)


def _diff_phrase(label: str, a: int, b: int, *, fewer_better: bool = False) -> str:
    """Render a neutral comparison sentence. NEVER labels one side
    as better / preferred — only states the factual delta."""
    if a == b:
        return f"Observation A and Observation B have equal {label} ({a})."
    if a > b:
        if fewer_better:
            return (
                f"Observation A has more {label} ({a}) than Observation B ({b})."
            )
        return (
            f"Observation A has higher {label} ({a}) than Observation B ({b})."
        )
    if fewer_better:
        return (
            f"Observation A has fewer {label} ({a}) than Observation B ({b})."
        )
    return (
        f"Observation A has lower {label} ({a}) than Observation B ({b})."
    )


def compare(
    row_a: dict[str, Any], row_b: dict[str, Any],
) -> dict[str, Any]:
    """Build a structured comparison report. Wording is constrained to
    factual delta phrases — never preference or prescription."""
    score_a = int(row_a.get("total_score") or 0)
    score_b = int(row_b.get("total_score") or 0)
    sev_a = _severe_flag_count(row_a)
    sev_b = _severe_flag_count(row_b)
    liq_a = _liquidity_score(row_a)
    liq_b = _liquidity_score(row_b)

    deltas = [
        _diff_phrase("evaluation score", score_a, score_b),
        _diff_phrase("severe flag count", sev_a, sev_b, fewer_better=True),
        _diff_phrase("liquidity component score", liq_a, liq_b),
        _diff_phrase("penalty count",
                     len(row_a.get("penalties") or []),
                     len(row_b.get("penalties") or []),
                     fewer_better=True),
    ]

    bucket_a = str(row_a.get("bucket") or "")
    bucket_b = str(row_b.get("bucket") or "")
    if bucket_a == bucket_b:
        bucket_phrase = (
            f"Observation A and Observation B share the same review "
            f"bucket ({BUCKET_LABELS.get(bucket_a, bucket_a)})."
        )
    else:
        bucket_phrase = (
            f"Observation A is in bucket "
            f"{BUCKET_LABELS.get(bucket_a, bucket_a)!r}; "
            f"Observation B is in bucket "
            f"{BUCKET_LABELS.get(bucket_b, bucket_b)!r}."
        )

    rank_a = row_a.get("rank_position")
    rank_b = row_b.get("rank_position")
    if rank_a is not None and rank_b is not None:
        if rank_a == rank_b:
            ranking_phrase = (
                f"Observation A and Observation B share rank position {rank_a}."
            )
        elif rank_a < rank_b:
            ranking_phrase = (
                f"Observation A is ranked above Observation B "
                f"(rank {rank_a} vs {rank_b}) under the deterministic "
                f"sort: evaluation_score DESC, severe_flag_count ASC, "
                f"liquidity_component_score DESC, as_of_date DESC, id ASC."
            )
        else:
            ranking_phrase = (
                f"Observation B is ranked above Observation A "
                f"(rank {rank_b} vs {rank_a}) under the deterministic "
                f"sort: evaluation_score DESC, severe_flag_count ASC, "
                f"liquidity_component_score DESC, as_of_date DESC, id ASC."
            )
    else:
        ranking_phrase = (
            "Ranking position not available for one or both rows."
        )

    flags_only_a = [
        f for f in (row_a.get("flags") or []) if f not in (row_b.get("flags") or [])
    ]
    flags_only_b = [
        f for f in (row_b.get("flags") or []) if f not in (row_a.get("flags") or [])
    ]

    return {
        "a": _summary_facts(row_a),
        "b": _summary_facts(row_b),
        "factual_deltas": deltas,
        "bucket_phrase": bucket_phrase,
        "ranking_phrase": ranking_phrase,
        "flags_only_in_a": flags_only_a,
        "flags_only_in_b": flags_only_b,
        "non_preference_notice": (
            "This comparison reports factual deltas only. It does not "
            "express a preference, recommendation, or selection between "
            "observations. Human review is required."
        ),
    }


def _summary_facts(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "underlying": row.get("underlying"),
        "rule_id": row.get("rule_id"),
        "as_of_date": row.get("as_of_date"),
        "total_score": row.get("total_score"),
        "qualified": row.get("qualified"),
        "bucket": row.get("bucket"),
        "bucket_label": row.get("bucket_label"),
        "rank_position": row.get("rank_position"),
        "flags": list(row.get("flags") or []),
        "n_penalties": len(row.get("penalties") or []),
        "liquidity_component_score": _liquidity_score(row),
    }
