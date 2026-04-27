"""Phase 11K unit tests — interpretation guardrails pure-fns.

Covers:
  * Selection-bias detector — every trigger code fires under the
    correct filter state
  * `is_recommendation_language` — flags assertion form, ignores
    negation form
  * Required guardrail copy present (deterministic ordering phrase,
    What This Does Not Mean block)
  * Forbidden ranking wording absent ("ranked above" / "better" /
    "worse" / "prefer" / "choose")
  * Recommendation/action wording absent outside safety negation
  * Boundary import scan — no V2/equity/ML/LLM/paper.engine.mutation
  * No mutating SQL or session calls
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

from apps.api.src.options.decision_support.buckets import (
    BUCKET_DATA_QUALITY_REVIEW,
    BUCKET_HIGH_REVIEW_PRIORITY,
)
from apps.api.src.options.interpretation_guardrails import (
    guardrail_templates as T,
)
from apps.api.src.options.interpretation_guardrails.guardrail_models import (
    BucketInterpretation,
    PageContextGuardrails,
    RankingInterpretation,
    ScoreInterpretation,
    SelectionBiasNotice,
    WhatThisDoesNotMean,
)
from apps.api.src.options.interpretation_guardrails.safety import (
    TRIGGER_ONLY_HIGH_PRIORITY,
    TRIGGER_ONLY_ONE_BUCKET,
    TRIGGER_SCORE_DESC_SORT_ACTIVE,
    detect_selection_bias,
    is_recommendation_language,
)


# ===========================================================================
# Selection-bias detector
# ===========================================================================

def test_only_high_review_priority_bucket_filter_triggers():
    triggers = detect_selection_bias({
        "bucket_filter": BUCKET_HIGH_REVIEW_PRIORITY,
        "sort_mode": "SCORE_DESC",
    })
    assert TRIGGER_ONLY_HIGH_PRIORITY in triggers
    assert TRIGGER_SCORE_DESC_SORT_ACTIVE in triggers


def test_only_high_priority_via_selected_buckets_list():
    triggers = detect_selection_bias({
        "selected_buckets": [BUCKET_HIGH_REVIEW_PRIORITY],
        "sort_mode": "SCORE_DESC",
    })
    assert TRIGGER_ONLY_HIGH_PRIORITY in triggers


def test_score_desc_sort_default_triggers_when_no_filter():
    triggers = detect_selection_bias({
        "bucket_filter": None,
        "selected_buckets": [],
    })
    assert TRIGGER_SCORE_DESC_SORT_ACTIVE in triggers
    assert TRIGGER_ONLY_HIGH_PRIORITY not in triggers
    assert TRIGGER_ONLY_ONE_BUCKET not in triggers


def test_only_one_bucket_selected_other_than_high_priority():
    triggers = detect_selection_bias({
        "bucket_filter": BUCKET_DATA_QUALITY_REVIEW,
        "sort_mode": "OTHER",
    })
    assert TRIGGER_ONLY_ONE_BUCKET in triggers
    assert TRIGGER_ONLY_HIGH_PRIORITY not in triggers


def test_no_triggers_when_all_buckets_selected_and_no_score_desc():
    triggers = detect_selection_bias({
        "bucket_filter": "ALL",
        "selected_buckets": [],
        "sort_mode": "OTHER",
    })
    assert triggers == []


# ===========================================================================
# Recommendation-language helper
# ===========================================================================

def test_is_recommendation_language_flags_assertion_form():
    assert is_recommendation_language("This is a recommended trade")
    assert is_recommendation_language("place order at the bid")
    assert is_recommendation_language("Top pick for the day")


def test_is_recommendation_language_ignores_negated_form():
    assert not is_recommendation_language(
        "This is not a recommendation"
    )
    assert not is_recommendation_language(
        "Outputs are not signals"
    )
    assert not is_recommendation_language(
        "Does not constitute instruction to act"
    )


def test_is_recommendation_language_handles_empty():
    assert not is_recommendation_language("")
    assert not is_recommendation_language(None)   # type: ignore[arg-type]


# ===========================================================================
# Required guardrail copy
# ===========================================================================

def test_ranking_uses_deterministic_ordering_phrase():
    assert "appears earlier under deterministic ordering rules" in (
        T.RANKING_DETERMINISTIC_ORDERING_PHRASE
    )
    assert (
        "appears earlier under the deterministic ordering rules"
        in T.RANKING_IS_WHAT
    )


def test_ranking_text_avoids_preference_wording():
    blob = " ".join([
        T.RANKING_HEADLINE,
        T.RANKING_IS_WHAT,
        *T.RANKING_IS_NOT_WHAT,
        T.RANKING_REVIEW_ONLY_FOOTER,
    ]).lower()
    # Ranking copy explicitly says "is not 'ranked above'..." in
    # NEGATION form. We allow the phrase only inside quoted-negation
    # patterns; reject any UNQUOTED preference wording.
    for forbidden in (r"\bbetter\b", r"\bworse\b",
                      r"\bprefer\b", r"\bchoose\b"):
        assert not re.search(forbidden, blob), (
            f"ranking copy contains forbidden preference word "
            f"{forbidden!r}"
        )


def test_what_this_does_not_mean_required_phrases():
    """All five spec-mandated negations are present."""
    text = " ".join([
        T.WTDN_EXPECTED_PROFITABILITY,
        T.WTDN_PROBABILITY_OF_SUCCESS,
        T.WTDN_SUITABILITY_FOR_TRADING,
        T.WTDN_INSTRUCTION_TO_ACT,
        T.WTDN_LIVE_MARKET_SIGNAL,
    ]).lower()
    assert "expected profitability" in text
    assert "probability of trade success" in text
    assert "suitability" in text
    assert "instruction to act" in text
    assert "live-market signal" in text


def test_score_text_explains_what_score_is_and_is_not():
    blob = " ".join([
        T.SCORE_HEADLINE,
        T.SCORE_IS_WHAT,
        *T.SCORE_IS_NOT_WHAT,
        T.SCORE_REVIEW_ONLY_FOOTER,
    ]).lower()
    assert "deterministic" in blob
    assert "is not a forecast" in blob
    assert "is not a probability" in blob
    assert "is not a recommendation" in blob


def test_bucket_headlines_cover_all_five_buckets():
    expected = {
        "HIGH_REVIEW_PRIORITY",
        "NEEDS_REVIEW_DATA_QUALITY",
        "NEEDS_REVIEW_MODEL_LIMITATION",
        "NEUTRAL_NEEDS_REVIEW",
        "EXCLUDED_BY_REVIEW_RULES",
    }
    assert expected <= set(T.BUCKET_HEADLINES.keys())


def test_bucket_text_avoids_preference_wording():
    blob = " ".join([
        *T.BUCKET_HEADLINES.values(),
        T.BUCKET_IS_WHAT,
        *T.BUCKET_IS_NOT_WHAT,
        T.BUCKET_REVIEW_ONLY_FOOTER,
    ]).lower()
    for forbidden in (r"\bbetter\b", r"\bworse\b",
                      r"\bprefer\b", r"\bchoose\b"):
        assert not re.search(forbidden, blob), (
            f"bucket copy contains forbidden preference word "
            f"{forbidden!r}"
        )


def test_selection_bias_banner_text_matches_spec():
    expected = (
        "Viewing only a subset of observations may create selection "
        "bias. Review context is observational only and does not "
        "indicate suitability, preference, or an action."
    )
    assert T.SELECTION_BIAS_BANNER == expected


# ===========================================================================
# Source-static — no mutation, no V2/ML/LLM, no paper-engine-mutation
# ===========================================================================

_IG_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "src" / "options" / "interpretation_guardrails"
)


def _ig_files() -> list[Path]:
    return list(_IG_DIR.rglob("*.py"))


_FORBIDDEN_DECORATORS = (
    r"@router\.post\b", r"@router\.put\b",
    r"@router\.patch\b", r"@router\.delete\b",
)


def test_no_router_decorators_in_guardrail_modules():
    for p in _ig_files():
        src = p.read_text(encoding="utf-8")
        for pat in _FORBIDDEN_DECORATORS:
            assert not re.search(pat, src), (
                f"forbidden decorator {pat!r} in {p.name}"
            )


_MUTATING_SQL = (
    r"\bINSERT\s+INTO\b",
    r"\bUPDATE\s+\w+\s+SET\b",
    r"\bDELETE\s+FROM\b",
    r"session\.add\b",
    r"session\.commit\b",
    r"session\.delete\b",
    r"session\.flush\b",
    r"session\.merge\b",
)


def test_no_mutating_sql_in_guardrail_modules():
    for p in _ig_files():
        src = p.read_text(encoding="utf-8")
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith(("#", '"', "'")):
                continue
            for pat in _MUTATING_SQL:
                assert not re.search(pat, line), (
                    f"forbidden mutating SQL/session call {pat!r} "
                    f"in {p.name}: {stripped}"
                )


_FORBIDDEN_IMPORTS = (
    r"\bv2_promotion(?!_snapshot)\b",
    r"\bv2_promotion_snapshot\b",
    r"\bv2_oos_monitoring\b",
    r"\bv2_stat_validation\b",
    r"\bb2_v2_comparison\b",
    r"\bengine_b\w*",
    r"\bshadow_strategy\w*",
    r"\bml_hybrid\b", r"\bml_research\b", r"\bml_replay\b",
    r"\bopenai\b", r"\banthropic\b", r"\bcohere\b",
    r"\btransformers\b", r"\btorch\b", r"\bsklearn\b",
    r"\bxgboost\b", r"\blightgbm\b",
    r"options\.paper\.engine\b",
)


def test_no_forbidden_imports_in_guardrails():
    for p in _ig_files():
        src = p.read_text(encoding="utf-8")
        import_lines = [
            ln for ln in src.splitlines()
            if ln.strip().startswith(("import ", "from "))
        ]
        joined = "\n".join(import_lines)
        for pat in _FORBIDDEN_IMPORTS:
            assert not re.search(pat, joined, re.IGNORECASE), (
                f"forbidden import pattern {pat!r} in {p.name}"
            )


def test_guardrail_modules_import_in_isolation():
    import sys
    before = set(sys.modules)
    importlib.import_module("apps.api.src.options.interpretation_guardrails.guardrail_models")
    importlib.import_module("apps.api.src.options.interpretation_guardrails.guardrail_templates")
    importlib.import_module("apps.api.src.options.interpretation_guardrails.safety")
    importlib.import_module("apps.api.src.options.interpretation_guardrails.guardrail_service")
    after = set(sys.modules)
    new_modules = after - before
    forbidden = (
        "v2_promotion_gates", "v2_promotion_state", "v2_promotion_snapshot",
        "v2_oos_monitoring", "v2_stat_validation", "b2_v2_comparison",
        "engine_b", "shadow_strategy",
        "ml_hybrid", "ml_research", "ml_replay",
        "openai", "anthropic", "cohere", "transformers", "torch",
        "options.paper.engine",
    )
    for f in forbidden:
        assert not any(f in m for m in new_modules), (
            f"guardrails indirectly pulled in {f}"
        )


def test_no_llm_or_prompt_generation_code_in_guardrails():
    forbidden_text = (
        r"\bChatCompletion\b",
        r"\bcompletions?\.create\b",
        r"\bopenai\.\w+",
        r"\banthropic\.\w+",
        r"\bsystem_prompt\b",
        r"\bllm\.\w+",
    )
    for p in _ig_files():
        src = p.read_text(encoding="utf-8")
        for pat in forbidden_text:
            assert not re.search(pat, src, re.IGNORECASE), (
                f"LLM/prompt pattern {pat!r} in {p.name}"
            )


# ===========================================================================
# Recommendation/action wording outside safety negation
# ===========================================================================

def test_guardrail_text_passes_recommendation_language_scan():
    """Walk every guardrail-template string constant and verify
    is_recommendation_language() returns False (i.e. only
    negated-form mentions exist)."""
    blob_strings = [
        T.SCORE_HEADLINE,
        T.SCORE_IS_WHAT,
        *T.SCORE_IS_NOT_WHAT,
        T.SCORE_REVIEW_ONLY_FOOTER,
        *T.BUCKET_HEADLINES.values(),
        T.BUCKET_IS_WHAT,
        *T.BUCKET_IS_NOT_WHAT,
        T.BUCKET_REVIEW_ONLY_FOOTER,
        T.RANKING_HEADLINE,
        T.RANKING_IS_WHAT,
        *T.RANKING_IS_NOT_WHAT,
        T.RANKING_DETERMINISTIC_ORDERING_PHRASE,
        T.RANKING_REVIEW_ONLY_FOOTER,
        T.SELECTION_BIAS_BANNER,
        T.WTDN_EXPECTED_PROFITABILITY,
        T.WTDN_PROBABILITY_OF_SUCCESS,
        T.WTDN_SUITABILITY_FOR_TRADING,
        T.WTDN_INSTRUCTION_TO_ACT,
        T.WTDN_LIVE_MARKET_SIGNAL,
    ]
    for s in blob_strings:
        assert not is_recommendation_language(s), (
            f"un-negated recommendation/action wording in: {s!r}"
        )


# ===========================================================================
# Dataclass shapes
# ===========================================================================

def test_dataclasses_are_frozen():
    """Guardrail dataclasses must be immutable."""
    for cls in (WhatThisDoesNotMean, ScoreInterpretation,
                BucketInterpretation, RankingInterpretation,
                SelectionBiasNotice, PageContextGuardrails):
        # All defined with @dataclass(frozen=True)
        assert getattr(cls, "__dataclass_params__").frozen
