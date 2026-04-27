"""Decision-framing service (Phase 11J).

Compute-on-read orchestrator. Consumes Phase 11I review-queue rows
and produces deterministic narratives + comparisons + checklists +
context caveats.

NEVER persists. NEVER calls LLMs. NEVER imports paper.engine
mutation modules.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from apps.api.src.options.decision_framing.checklist import build_checklist
from apps.api.src.options.decision_framing.comparison import compare
from apps.api.src.options.decision_framing.narrative_templates import (
    PAPER_ONLY_REMINDER,
    REVIEW_CONTEXT_ONLY_FOOTER,
    render_caveats,
    render_narrative,
)
from apps.api.src.options.decision_support.review_queue import (
    get_review_queue,
)


DECISION_FRAMING_DISCLAIMER = (
    "Decision framing provides deterministic review context only. "
    "It is not advice, recommendation, or execution guidance."
)


def _common_envelope() -> dict[str, str]:
    return {
        "decision_framing_disclaimer": DECISION_FRAMING_DISCLAIMER,
        "review_context_only_footer": REVIEW_CONTEXT_ONLY_FOOTER,
        "paper_only_reminder": PAPER_ONLY_REMINDER,
        "observation_only_notice":
            "Observation only — not investment advice or execution guidance",
    }


def _all_rows(
    session: Session, *, lookback_days: int,
) -> list[dict[str, Any]]:
    """Fetch the unfiltered Phase 11I queue once; downstream filters
    operate on the result in memory."""
    queue = get_review_queue(
        session, lookback_days=lookback_days, limit=10_000,
    )
    return list(queue["review_queue"])


def list_narratives(
    session: Session,
    *,
    bucket: str | None = None,
    strategy: str | None = None,
    underlying: str | None = None,
    lookback_days: int = 14,
    limit: int = 50,
) -> dict[str, Any]:
    rows = _all_rows(session, lookback_days=lookback_days)

    def _keep(r: dict[str, Any]) -> bool:
        if bucket is not None and r.get("bucket") != bucket:
            return False
        if strategy is not None and r.get("rule_id") != strategy:
            return False
        if underlying is not None and r.get("underlying") != underlying:
            return False
        return True

    kept = [r for r in rows if _keep(r)][:limit]
    narratives = [render_narrative(r) for r in kept]
    return {
        **_common_envelope(),
        "count": len(narratives),
        "narratives": narratives,
    }


def get_narrative_detail(
    session: Session,
    *,
    observation_id: str,
    lookback_days: int = 120,
) -> dict[str, Any] | None:
    rows = _all_rows(session, lookback_days=lookback_days)
    target = next((r for r in rows if r.get("id") == observation_id), None)
    if target is None:
        return None
    narrative = render_narrative(target)
    return {
        **_common_envelope(),
        "id": observation_id,
        "narrative": narrative,
        "ranking_explanation": target.get("ranking_explanation"),
        "tie_breakers": target.get("tie_breakers") or [],
        "inclusion_reason": target.get("inclusion_reason"),
        "components": target.get("components"),
        "penalties": target.get("penalties"),
    }


def compare_two(
    session: Session,
    *,
    observation_id_a: str,
    observation_id_b: str,
    lookback_days: int = 120,
) -> dict[str, Any] | None:
    rows = _all_rows(session, lookback_days=lookback_days)
    by_id = {r.get("id"): r for r in rows}
    a = by_id.get(observation_id_a)
    b = by_id.get(observation_id_b)
    if a is None or b is None:
        return None
    return {
        **_common_envelope(),
        "comparison": compare(a, b),
        "caveats_a": render_caveats(a),
        "caveats_b": render_caveats(b),
    }


def get_checklist(
    session: Session,
    *,
    observation_id: str,
    lookback_days: int = 120,
) -> dict[str, Any] | None:
    rows = _all_rows(session, lookback_days=lookback_days)
    target = next((r for r in rows if r.get("id") == observation_id), None)
    if target is None:
        return None
    return {
        **_common_envelope(),
        "id": observation_id,
        "checklist": build_checklist(target),
    }


def get_context(
    session: Session,
    *,
    observation_id: str,
    lookback_days: int = 120,
) -> dict[str, Any] | None:
    """Bundle: narrative + caveats + flags + checklist + non-action
    reminders. The page surfaces this as the structured "review
    context" payload."""
    rows = _all_rows(session, lookback_days=lookback_days)
    target = next((r for r in rows if r.get("id") == observation_id), None)
    if target is None:
        return None
    return {
        **_common_envelope(),
        "id": observation_id,
        "narrative": render_narrative(target),
        "checklist": build_checklist(target),
        "context_caveats": [
            "Sample size caution: scores are computed over a single "
            "(symbol, day) snapshot — not a peer cohort.",
            "Stale data caution: chain snapshots may be older than "
            "the current market session; verify timestamps before "
            "any further inspection.",
            "Missing data caution: feature flags surface upstream "
            "data gaps. Treat affected components as partial.",
            "Model limitation caution: pin-risk, simplified-exit, "
            "and missing-settlement flags impose recorded-payoff "
            "uncertainty.",
            "Score is not a recommendation: high scores are not "
            "endorsements; low scores are not refusals.",
            "Ranking is not selection: rank position reflects only "
            "the deterministic sort cascade — never operator intent.",
        ],
    }


def get_summary(
    session: Session,
    *,
    lookback_days: int = 14,
) -> dict[str, Any]:
    rows = _all_rows(session, lookback_days=lookback_days)
    n = len(rows)
    by_bucket: dict[str, int] = {}
    for r in rows:
        b = r.get("bucket") or ""
        by_bucket[b] = by_bucket.get(b, 0) + 1
    return {
        **_common_envelope(),
        "n_total_observations": n,
        "by_bucket": [
            {"bucket": k, "count": v}
            for k, v in sorted(by_bucket.items())
        ],
    }
