"""Deterministic ranking of scored observations (Phase 11I).

Sort key (frozen, documented for audit):
  1. evaluation_score DESCENDING
  2. severe_flag_count ASCENDING (fewer is better)
  3. liquidity component score DESCENDING
  4. as_of_date DESCENDING (newer first)
  5. observation id ASCENDING (final tie-break, stable)

NEVER uses ML, learned weights, or hidden ranking signals.
"""

from __future__ import annotations

from typing import Any, Sequence

from apps.api.src.options.decision_support.buckets import (
    severe_flag_count,
)


# Frozen list — UI consumes verbatim
TIE_BREAKERS: tuple[str, ...] = (
    "evaluation_score DESC",
    "severe_flag_count ASC",
    "liquidity_component_score DESC",
    "as_of_date DESC",
    "observation_id ASC",
)


def _liquidity_score(score: dict[str, Any]) -> int:
    for c in score.get("components") or []:
        if c.get("component") == "liquidity":
            return int(c.get("score") or 0)
    return 0


def _sort_key(score: dict[str, Any]) -> tuple:
    return (
        -int(score.get("total_score") or 0),
        int(severe_flag_count(score)),
        -_liquidity_score(score),
        # Reverse-lex by date; newer date string sorts later in lex order,
        # so use a negative ordinal of (year, month, day) for proper desc.
        _date_reverse_key(score.get("as_of_date") or ""),
        str(score.get("id") or ""),
    )


def _date_reverse_key(iso: str) -> str:
    """Lex-reverse a YYYY-MM-DD string so newer dates sort first.
    We invert each digit (9 -> 0, 0 -> 9) to flip the natural order."""
    if not iso:
        return ""
    table = str.maketrans("0123456789", "9876543210")
    return iso.translate(table)


def rank(scores: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return scores sorted deterministically. Each row is annotated
    with `rank_position` and a `ranking_explanation` block."""
    sorted_scores = sorted(scores, key=_sort_key)
    out: list[dict[str, Any]] = []
    for pos, s in enumerate(sorted_scores, start=1):
        explanation = (
            f"Rank {pos} via deterministic sort: "
            f"score={s.get('total_score')} (desc), "
            f"severe_flag_count={severe_flag_count(s)} (asc), "
            f"liquidity_component={_liquidity_score(s)} (desc), "
            f"as_of_date={s.get('as_of_date')} (desc), "
            f"id={s.get('id')} (asc)."
        )
        annotated = dict(s)
        annotated["rank_position"] = pos
        annotated["ranking_explanation"] = explanation
        annotated["tie_breakers"] = list(TIE_BREAKERS)
        out.append(annotated)
    return out
