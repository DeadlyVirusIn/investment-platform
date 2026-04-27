"""Guardrail service (Phase 11K).

Compute-on-read. Looks up an observation row through the existing
read-only Phase 11I review-queue path, then renders a frozen-template
guardrail bundle. NEVER persists.

This service NEVER changes scoring (11H), bucket assignment (11I),
ranking (11I), or narrative wording (11J). It only adds a
side-channel interpretation layer.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from sqlalchemy.orm import Session

from apps.api.src.options.decision_support.buckets import (
    BUCKET_LABELS,
)
from apps.api.src.options.decision_support.review_queue import (
    get_review_queue,
)
from apps.api.src.options.interpretation_guardrails import guardrail_templates as T
from apps.api.src.options.interpretation_guardrails.guardrail_models import (
    BucketInterpretation,
    PageContextGuardrails,
    RankingInterpretation,
    ScoreInterpretation,
    SelectionBiasNotice,
    WhatThisDoesNotMean,
)
from apps.api.src.options.interpretation_guardrails.safety import (
    detect_selection_bias,
)


def _wtdn() -> WhatThisDoesNotMean:
    return WhatThisDoesNotMean(
        not_expected_profitability=T.WTDN_EXPECTED_PROFITABILITY,
        not_probability_of_success=T.WTDN_PROBABILITY_OF_SUCCESS,
        not_suitability_for_trading=T.WTDN_SUITABILITY_FOR_TRADING,
        not_instruction_to_act=T.WTDN_INSTRUCTION_TO_ACT,
        not_live_market_signal=T.WTDN_LIVE_MARKET_SIGNAL,
    )


def _envelope() -> dict[str, str]:
    return {
        "notice": T.NOTICE_PAPER_ONLY,
        "observation_only_notice": T.NOTICE_OBSERVATION_ONLY,
        "interpretation_guardrails_notice": T.NOTICE_INTERPRETATION_GUARDRAILS,
    }


def _row_for(
    session: Session, *, observation_id: str, lookback_days: int = 120,
) -> dict[str, Any] | None:
    """Look up a single review-queue row through Phase 11I (read-only).
    Returns None if missing."""
    queue = get_review_queue(
        session, lookback_days=lookback_days, limit=10_000,
    )
    for row in queue["review_queue"]:
        if row.get("id") == observation_id:
            return row
    return None


# ---------------------------------------------------------------------------
# Public service entry points
# ---------------------------------------------------------------------------

def get_score_interpretation(
    session: Session, *, observation_id: str,
) -> dict[str, Any] | None:
    row = _row_for(session, observation_id=observation_id)
    if row is None:
        return None
    block = ScoreInterpretation(
        headline=T.SCORE_HEADLINE,
        is_what=T.SCORE_IS_WHAT,
        is_not_what=T.SCORE_IS_NOT_WHAT,
        review_only_footer=T.SCORE_REVIEW_ONLY_FOOTER,
        what_this_does_not_mean=_wtdn(),
    )
    return {
        **_envelope(),
        "id": observation_id,
        "total_score": row.get("total_score"),
        "score_interpretation": asdict(block),
    }


def get_bucket_interpretation(
    session: Session, *, observation_id: str,
) -> dict[str, Any] | None:
    row = _row_for(session, observation_id=observation_id)
    if row is None:
        return None
    bucket = str(row.get("bucket") or "")
    headline = T.BUCKET_HEADLINES.get(
        bucket,
        "Bucket label is a human-review category only.",
    )
    block = BucketInterpretation(
        bucket=bucket,
        headline=headline,
        is_what=T.BUCKET_IS_WHAT,
        is_not_what=T.BUCKET_IS_NOT_WHAT,
        review_only_footer=T.BUCKET_REVIEW_ONLY_FOOTER,
        what_this_does_not_mean=_wtdn(),
    )
    return {
        **_envelope(),
        "id": observation_id,
        "bucket": bucket,
        "bucket_label": BUCKET_LABELS.get(bucket, bucket),
        "bucket_interpretation": asdict(block),
    }


def get_ranking_interpretation(
    session: Session, *, observation_id: str,
) -> dict[str, Any] | None:
    row = _row_for(session, observation_id=observation_id)
    if row is None:
        return None
    block = RankingInterpretation(
        headline=T.RANKING_HEADLINE,
        is_what=T.RANKING_IS_WHAT,
        is_not_what=T.RANKING_IS_NOT_WHAT,
        deterministic_ordering_phrase=T.RANKING_DETERMINISTIC_ORDERING_PHRASE,
        review_only_footer=T.RANKING_REVIEW_ONLY_FOOTER,
        what_this_does_not_mean=_wtdn(),
    )
    return {
        **_envelope(),
        "id": observation_id,
        "rank_position": row.get("rank_position"),
        "tie_breakers": row.get("tie_breakers") or [],
        "ranking_interpretation": asdict(block),
    }


def get_page_context() -> dict[str, Any]:
    """Bundle of standard banners + the universal "does not mean"
    block. The frontend uses this to render the WhatThisDoesNotMean
    panel without per-row context."""
    block = PageContextGuardrails(
        notice_paper_only=T.NOTICE_PAPER_ONLY,
        notice_observation_only=T.NOTICE_OBSERVATION_ONLY,
        notice_evaluation=T.NOTICE_EVALUATION,
        notice_decision_support=T.NOTICE_DECISION_SUPPORT,
        notice_decision_framing=T.NOTICE_DECISION_FRAMING,
        notice_interpretation_guardrails=T.NOTICE_INTERPRETATION_GUARDRAILS,
        what_this_does_not_mean=_wtdn(),
        selection_bias_banner_default_text=T.SELECTION_BIAS_BANNER,
    )
    return {
        **_envelope(),
        "page_context": asdict(block),
    }


def get_selection_bias_notice(
    *, filter_state: dict[str, Any],
) -> dict[str, Any]:
    triggers = detect_selection_bias(filter_state)
    notice = SelectionBiasNotice(
        triggered=bool(triggers),
        triggers=tuple(triggers),
        banner_text=T.SELECTION_BIAS_BANNER,
    )
    return {
        **_envelope(),
        "selection_bias_notice": asdict(notice),
    }
