"""Frozen guardrail text templates (Phase 11K).

Plain-English module constants. NEVER calls LLMs. NEVER includes
recommendation/action wording outside explicit safety negation.

Wording rules:
  * Ranking text uses "appears earlier under deterministic ordering
    rules" — NEVER "ranked above", "better", "worse", "prefer",
    "choose".
  * "Recommendation" / "advice" / "signal" / "instruction" appear
    ONLY in negation phrases ("does not constitute X", "is not Y").
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# What this does NOT mean (canonical block surfaced everywhere)
# ---------------------------------------------------------------------------

WTDN_EXPECTED_PROFITABILITY = (
    "Outputs from this layer do not represent expected profitability. "
    "Scores and rankings are not forecasts of P&L."
)

WTDN_PROBABILITY_OF_SUCCESS = (
    "Outputs do not represent probability of trade success. "
    "No probabilistic model produces these values."
)

WTDN_SUITABILITY_FOR_TRADING = (
    "Outputs do not assess suitability of any position for any "
    "individual operator, account, or risk tolerance."
)

WTDN_INSTRUCTION_TO_ACT = (
    "Outputs do not constitute instruction to act, recommendation "
    "to enter or exit a position, or guidance to place an order."
)

WTDN_LIVE_MARKET_SIGNAL = (
    "Outputs are not live-market signals. They reflect deterministic "
    "evaluation over historical paper observations only."
)


# ---------------------------------------------------------------------------
# Score interpretation
# ---------------------------------------------------------------------------

SCORE_HEADLINE = (
    "An evaluation score is a deterministic rule-based review value."
)

SCORE_IS_WHAT = (
    "The score is computed from frozen v1 component weights "
    "(liquidity 25 + risk/reward 25 + volatility context 20 + "
    "structure 20) minus capped data/model penalties (max −20). "
    "It exists only to focus human review attention. The number is "
    "the same every time the same inputs are passed in."
)

SCORE_IS_NOT_WHAT: tuple[str, ...] = (
    "The score is not a forecast of future P&L.",
    "The score is not a probability of success.",
    "The score is not an expected return value.",
    "The score is not a suitability measure for any operator.",
    "The score is not a recommendation, signal, or instruction.",
    "The score is not adaptive — no learning weights, no ML.",
)

SCORE_REVIEW_ONLY_FOOTER = (
    "Use the score to decide which observations to inspect first. "
    "It is review context only."
)


# ---------------------------------------------------------------------------
# Bucket interpretation
# ---------------------------------------------------------------------------

BUCKET_HEADLINES: dict[str, str] = {
    "HIGH_REVIEW_PRIORITY": (
        "A 'High review priority' bucket is a human-review category, "
        "not a selection for trading."
    ),
    "NEEDS_REVIEW_DATA_QUALITY": (
        "A 'Needs review — data quality' bucket flags rows whose "
        "score was reduced by upstream data gaps."
    ),
    "NEEDS_REVIEW_MODEL_LIMITATION": (
        "A 'Needs review — model limitation' bucket flags rows where "
        "the engine's model approximations require extra scrutiny."
    ),
    "NEUTRAL_NEEDS_REVIEW": (
        "A 'Neutral — needs human review' bucket is the mid-range "
        "default — it does not imply favourable or unfavourable."
    ),
    "EXCLUDED_BY_REVIEW_RULES": (
        "An 'Excluded by review rules' bucket means the row failed "
        "the inclusion cascade. It is not a rejection of any market "
        "candidate."
    ),
}

BUCKET_IS_WHAT = (
    "Bucket assignment is a deterministic classification cascade — "
    "score threshold + rule qualification + flag presence + data "
    "quality. It is computed identically for every row given the "
    "same inputs."
)

BUCKET_IS_NOT_WHAT: tuple[str, ...] = (
    "A bucket label does not imply favourable or unfavourable.",
    "A bucket label does not imply actionable or non-actionable.",
    "A bucket label does not imply selected or rejected for trading.",
    "A bucket label does not constitute advice or recommendation.",
)

BUCKET_REVIEW_ONLY_FOOTER = (
    "Buckets sort observations into human-review categories. "
    "Human inspection is required before any further interpretation."
)


# ---------------------------------------------------------------------------
# Ranking interpretation
# ---------------------------------------------------------------------------

RANKING_HEADLINE = (
    "A rank position reflects deterministic ordering rules only."
)

RANKING_IS_WHAT = (
    "Rank position is computed by a frozen 5-level lexicographic "
    "sort: evaluation_score, severe_flag_count, liquidity_component_"
    "score, as_of_date, observation_id. A row appears earlier under "
    "the deterministic ordering rules when its sort key is "
    "lexicographically smaller — never because the system 'prefers' "
    "or 'chooses' it."
)

RANKING_IS_NOT_WHAT: tuple[str, ...] = (
    "Rank position is not a quality ranking.",
    "Rank position is not a recommendation order.",
    "Rank position is not a probability ordering.",
    "Rank position is not an expected-return ordering.",
    "Rank position is not 'ranked above' or 'ranked below' another "
    "row in any preference sense.",
)

RANKING_DETERMINISTIC_ORDERING_PHRASE = (
    "appears earlier under deterministic ordering rules"
)

RANKING_REVIEW_ONLY_FOOTER = (
    "Use rank position to control how many rows you examine — "
    "never to infer suitability or preference."
)


# ---------------------------------------------------------------------------
# Selection bias banner
# ---------------------------------------------------------------------------

SELECTION_BIAS_BANNER = (
    "Viewing only a subset of observations may create selection "
    "bias. Review context is observational only and does not "
    "indicate suitability, preference, or an action."
)


# ---------------------------------------------------------------------------
# Page-level notices (mirror banners surfaced on every options page)
# ---------------------------------------------------------------------------

NOTICE_PAPER_ONLY = (
    "Options are paper-trading only — simulated lifecycle. No live "
    "orders. No execution. No ML signals."
)

NOTICE_OBSERVATION_ONLY = (
    "Observation only — not investment advice or execution guidance."
)

NOTICE_EVALUATION = (
    "Evaluation scores are fixed rule-based paper analytics. They "
    "are not trade recommendations."
)

NOTICE_DECISION_SUPPORT = (
    "Review queues are for human inspection only. They are not "
    "trade recommendations or execution guidance."
)

NOTICE_DECISION_FRAMING = (
    "Decision framing provides deterministic review context only. "
    "It is not advice, recommendation, or execution guidance."
)

NOTICE_INTERPRETATION_GUARDRAILS = (
    "Interpretation guardrails describe what scores, buckets, and "
    "rankings DO and DO NOT mean. They are interpretation context "
    "only — not advice, recommendation, or instruction."
)
