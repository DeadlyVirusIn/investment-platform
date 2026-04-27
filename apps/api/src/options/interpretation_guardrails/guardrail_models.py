"""Frozen response shapes for guardrail endpoints (Phase 11K).

Pure dataclasses. Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WhatThisDoesNotMean:
    """Standard "this does NOT mean" block surfaced everywhere."""
    not_expected_profitability: str
    not_probability_of_success: str
    not_suitability_for_trading: str
    not_instruction_to_act: str
    not_live_market_signal: str


@dataclass(frozen=True)
class ScoreInterpretation:
    """How to read an evaluation score."""
    headline: str
    is_what: str
    is_not_what: tuple[str, ...]
    review_only_footer: str
    what_this_does_not_mean: WhatThisDoesNotMean


@dataclass(frozen=True)
class BucketInterpretation:
    """How to read a review bucket label."""
    bucket: str
    headline: str
    is_what: str
    is_not_what: tuple[str, ...]
    review_only_footer: str
    what_this_does_not_mean: WhatThisDoesNotMean


@dataclass(frozen=True)
class RankingInterpretation:
    """How to read a rank position."""
    headline: str
    is_what: str
    is_not_what: tuple[str, ...]
    deterministic_ordering_phrase: str
    review_only_footer: str
    what_this_does_not_mean: WhatThisDoesNotMean


@dataclass(frozen=True)
class SelectionBiasNotice:
    triggered: bool
    triggers: tuple[str, ...]
    banner_text: str


@dataclass(frozen=True)
class PageContextGuardrails:
    """Page-level disclaimers + standard "does not mean" block.
    Frontend uses this to render the WhatThisDoesNotMean panel."""
    notice_paper_only: str
    notice_observation_only: str
    notice_evaluation: str
    notice_decision_support: str
    notice_decision_framing: str
    notice_interpretation_guardrails: str
    what_this_does_not_mean: WhatThisDoesNotMean
    selection_bias_banner_default_text: str
