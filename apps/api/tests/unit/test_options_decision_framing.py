"""Phase 11J unit tests — pure-fn decision framing modules.

Covers:
  * Narrative determinism (same input → same output)
  * Narrative required safety language (paper-only / human review /
    not recommendation / not execution guidance)
  * Narrative forbidden language absent
  * Comparison neutrality (factual deltas only; no better/worse/
    choose/avoid wording)
  * Checklist contains no action verbs
  * Boundary import scan — no V2/equity/ML/LLM/paper-engine-mutation
  * No mutating SQL or session calls
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

from apps.api.src.options.decision_framing.checklist import (
    CHECKLIST_ALWAYS,
    build_checklist,
)
from apps.api.src.options.decision_framing.comparison import compare
from apps.api.src.options.decision_framing.narrative_templates import (
    CAUTION_PARAGRAPH,
    PAPER_ONLY_REMINDER,
    REVIEW_CONTEXT_ONLY_FOOTER,
    caveat_for_flag,
    render_caveats,
    render_narrative,
    render_why,
)
from apps.api.src.options.decision_support.buckets import (
    BUCKET_DATA_QUALITY_REVIEW,
    BUCKET_EXCLUDED,
    BUCKET_HIGH_REVIEW_PRIORITY,
    BUCKET_MODEL_LIMITATION_REVIEW,
    BUCKET_NEUTRAL,
)
from apps.api.src.options.paper.expiration import (
    FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
    FLAG_MISSING_SETTLEMENT,
    FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
)


def _row(
    *,
    id="SPY:2026-04-27:SHORT_PUT_CREDIT_SPREAD",
    bucket=BUCKET_HIGH_REVIEW_PRIORITY,
    bucket_label="High review priority",
    score=82,
    qualified=True,
    flags=(),
    penalties=(),
    components=None,
    rank_position=1,
    inclusion_reason="example",
):
    return {
        "id": id,
        "bucket": bucket,
        "bucket_label": bucket_label,
        "underlying": "SPY",
        "rule_id": "SHORT_PUT_CREDIT_SPREAD",
        "as_of_date": "2026-04-27",
        "total_score": score,
        "qualified": qualified,
        "flags": list(flags),
        "penalties": list(penalties),
        "components": components or [
            {"component": "liquidity",   "weight_max": 25, "score": 22, "explanation": ""},
            {"component": "risk_reward", "weight_max": 25, "score": 18, "explanation": ""},
            {"component": "vol_context", "weight_max": 20, "score": 14, "explanation": ""},
            {"component": "structure",   "weight_max": 20, "score": 18, "explanation": ""},
        ],
        "rank_position": rank_position,
        "inclusion_reason": inclusion_reason,
    }


# ===========================================================================
# Narrative determinism
# ===========================================================================

def test_render_narrative_is_deterministic():
    a = render_narrative(_row())
    b = render_narrative(_row())
    assert a == b


def test_render_why_uses_high_review_priority_template():
    out = render_why(_row(bucket=BUCKET_HIGH_REVIEW_PRIORITY, score=82))
    assert "High Review Priority" in out
    assert "82" in out
    assert "qualified" in out


def test_render_why_uses_model_limitation_template_when_severe_flag():
    out = render_why(_row(
        bucket=BUCKET_MODEL_LIMITATION_REVIEW,
        flags=(FLAG_PIN_RISK_UNCERTAIN_OUTCOME,),
    ))
    assert "Model Limitation" in out
    assert "PIN_RISK_UNCERTAIN_OUTCOME" in out


def test_render_why_uses_data_quality_template_when_dq_penalty():
    out = render_why(_row(
        bucket=BUCKET_DATA_QUALITY_REVIEW,
        penalties=[{"code": "MISSING_GREEKS", "points": -3,
                    "label": "x", "reason": "x"}],
    ))
    assert "Data Quality" in out
    assert "MISSING_GREEKS" in out


def test_render_why_uses_neutral_template_when_neutral():
    out = render_why(_row(bucket=BUCKET_NEUTRAL, score=64))
    assert "Neutral" in out


def test_render_why_uses_excluded_template_when_excluded():
    out = render_why(_row(
        bucket=BUCKET_EXCLUDED, score=40,
        inclusion_reason="Excluded: total_score=40 <= 49.",
    ))
    assert "Excluded by Review Rules" in out
    assert "total_score=40" in out


# ===========================================================================
# Required safety language
# ===========================================================================

def test_narrative_includes_paper_only_reminder():
    n = render_narrative(_row())
    assert "paper-only" in n["paper_only_reminder"].lower()


def test_narrative_includes_human_review_caution():
    n = render_narrative(_row())
    assert "Human review is still required" in n["caution_paragraph"]


def test_narrative_includes_review_context_only_footer():
    n = render_narrative(_row())
    assert "review context only" in n["non_action_footer"].lower()
    assert "not a trade recommendation" in n["non_action_footer"].lower()
    assert "not execution guidance" in n["non_action_footer"].lower()


def test_pin_risk_caveat_present_when_flag_present():
    n = render_narrative(_row(flags=(FLAG_PIN_RISK_UNCERTAIN_OUTCOME,)))
    joined = " ".join(n["caveats"])
    assert "Pin risk" in joined


def test_assignment_caveat_present_when_flag_present():
    n = render_narrative(_row(flags=(FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,)))
    joined = " ".join(n["caveats"])
    assert "Assignment" in joined or "assignment" in joined


def test_missing_settlement_caveat_present_when_flag_present():
    n = render_narrative(_row(flags=(FLAG_MISSING_SETTLEMENT,)))
    joined = " ".join(n["caveats"])
    assert "Missing settlement" in joined


# ===========================================================================
# Forbidden language
# ===========================================================================

_FORBIDDEN_NARRATIVE_WORDS = (
    r"\brecommended\b", r"\brecommendation\b",
    r"\bbest\b", r"\bsignal\b",
    r"\bconfidence\b",
    r"\bexecute\b", r"\bplace order\b",
    r"\bauto-?trade\b",
    # "enter trade" / "exit trade" forbidden as action verbs. Bare
    # "exit" appears in the canonical flag name "simplified-exit" and
    # in benign noun phrases like "exit model"; only the action-noun
    # form is forbidden.
    r"\benter (?:a |the )?trade\b",
    r"\bexit (?:a |the )?trade\b",
    r"\btrade now\b", r"\btop pick\b",
    r"\bstrong setup\b", r"\bthesis\b",
    r"\bconviction\b",
    # Forbidden alpha-claim wording (recommendation-style).
    # The bare word "alpha" can appear in legitimate technical names.
    r"\bgenerate alpha\b", r"\bcapture alpha\b",
)


def _scannable_narrative_blob(n: dict) -> str:
    """Concat the AUTHORED narrative text — excluding the safety
    footers that legitimately contain negations like 'not a trade
    recommendation'. We scan only the bucket explanation + caveats."""
    parts = [n.get("why_it_appears") or ""]
    parts.extend(n.get("caveats") or [])
    return " ".join(parts).lower()


def test_narrative_avoids_forbidden_language_for_high_priority_row():
    n = render_narrative(_row())
    blob = _scannable_narrative_blob(n)
    for pat in _FORBIDDEN_NARRATIVE_WORDS:
        assert not re.search(pat, blob, re.IGNORECASE), (
            f"narrative contains forbidden token {pat!r}"
        )


def test_narrative_avoids_forbidden_language_with_severe_flag():
    n = render_narrative(_row(
        bucket=BUCKET_MODEL_LIMITATION_REVIEW,
        flags=(FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
               FLAG_ASSIGNMENT_SIMPLIFIED_EXIT),
    ))
    blob = _scannable_narrative_blob(n)
    for pat in _FORBIDDEN_NARRATIVE_WORDS:
        assert not re.search(pat, blob, re.IGNORECASE), (
            f"narrative contains forbidden token {pat!r}"
        )


# ===========================================================================
# Comparison neutrality
# ===========================================================================

def test_compare_emits_factual_deltas_only():
    a = _row(id="A", score=80, flags=())
    b = _row(id="B", score=60, flags=(FLAG_PIN_RISK_UNCERTAIN_OUTCOME,))
    out = compare(a, b)
    deltas = " ".join(out["factual_deltas"])
    assert "Observation A has higher evaluation score" in deltas
    assert "Observation A has fewer severe flag count" in deltas


def test_compare_avoids_preference_wording():
    a = _row(id="A", score=80)
    b = _row(id="B", score=60)
    out = compare(a, b)
    blob = " ".join([
        out["bucket_phrase"],
        out["ranking_phrase"],
        out["non_preference_notice"],
        *out["factual_deltas"],
    ]).lower()
    for forbidden in (
        r"\bbetter\b", r"\bworse\b",
        r"\bchoose\b", r"\bprefer\b",
        r"\bavoid\b", r"\bbest\b",
        r"\brecommended\b", r"\bsignal\b",
    ):
        assert not re.search(forbidden, blob), (
            f"comparison emitted forbidden word {forbidden!r}"
        )


def test_compare_includes_non_preference_notice():
    a = _row(id="A", score=80)
    b = _row(id="B", score=60)
    out = compare(a, b)
    assert "factual deltas" in out["non_preference_notice"].lower()
    assert "human review" in out["non_preference_notice"].lower()


def test_compare_ranking_phrase_uses_ranked_above_below_only():
    a = _row(id="A", score=80, rank_position=1)
    b = _row(id="B", score=60, rank_position=2)
    out = compare(a, b)
    assert "ranked above" in out["ranking_phrase"]


def test_compare_equal_scores_produces_equal_phrase():
    a = _row(id="A", score=70, rank_position=3)
    b = _row(id="B", score=70, rank_position=3)
    out = compare(a, b)
    assert "equal" in " ".join(out["factual_deltas"]).lower()


# ===========================================================================
# Checklist
# ===========================================================================

_FORBIDDEN_CHECKLIST_VERBS = (
    r"\benter (?:a |the )?trade\b",
    r"\bexit (?:a |the )?trade\b",
    r"\bplace order\b",
    r"\bexecute\b",
    r"\bbuy\b", r"\bsell\b",
)


def test_checklist_always_items_count():
    rows = build_checklist(_row())
    # Always-present items + 0 conditional (no flags) = always count
    assert len(rows) == len(CHECKLIST_ALWAYS)


def test_checklist_pin_risk_adds_extra_item():
    rows = build_checklist(_row(flags=(FLAG_PIN_RISK_UNCERTAIN_OUTCOME,)))
    codes = {r["code"] for r in rows}
    assert "EXTRA_VERIFY_PIN_RISK_BAND" in codes


def test_checklist_assignment_adds_extra_item():
    rows = build_checklist(_row(flags=(FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,)))
    codes = {r["code"] for r in rows}
    assert "EXTRA_VERIFY_ASSIGNMENT_HANDLING" in codes


def test_checklist_missing_settlement_adds_extra_item():
    rows = build_checklist(_row(flags=(FLAG_MISSING_SETTLEMENT,)))
    codes = {r["code"] for r in rows}
    assert "EXTRA_VERIFY_MISSING_SETTLEMENT" in codes


def test_checklist_avoids_action_verbs():
    rows = build_checklist(_row(flags=(
        FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
        FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
        FLAG_MISSING_SETTLEMENT,
    )))
    blob = " ".join(
        f"{r['label']} {r['description']}" for r in rows
    ).lower()
    for pat in _FORBIDDEN_CHECKLIST_VERBS:
        assert not re.search(pat, blob, re.IGNORECASE), (
            f"checklist contains action verb {pat!r}"
        )


def test_checklist_label_set_is_safe():
    """Spec mandates these labels exist verbatim."""
    rows = build_checklist(_row())
    labels = {r["label"] for r in rows}
    expected = {
        "Verify data freshness",
        "Verify option chain liquidity",
        "Verify spread / OI / volume",
        "Review model limitation flags",
        "Review pin risk / assignment / settlement flags",
        "Review current market context manually",
        "Confirm this is paper-only analysis",
    }
    assert expected <= labels


# ===========================================================================
# Source-static — no mutation, no V2/ML/LLM, no paper-engine-mutation
# ===========================================================================

_DF_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "src" / "options" / "decision_framing"
)


def _df_files() -> list[Path]:
    return list(_DF_DIR.rglob("*.py"))


_FORBIDDEN_DECORATORS = (
    r"@router\.post\b", r"@router\.put\b",
    r"@router\.patch\b", r"@router\.delete\b",
)


def test_no_router_decorators_in_decision_framing_modules():
    for p in _df_files():
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


def test_no_mutating_sql_in_decision_framing_modules():
    for p in _df_files():
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
    # No LLM/API client imports of any kind
    r"\bopenai\b", r"\banthropic\b", r"\bcohere\b",
    r"\btransformers\b", r"\btorch\b", r"\bsklearn\b",
    r"\bxgboost\b", r"\blightgbm\b",
    # Paper engine mutation surface forbidden
    r"options\.paper\.engine\b",
)


def test_no_forbidden_imports_in_decision_framing():
    for p in _df_files():
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


def test_decision_framing_modules_import_in_isolation():
    import sys
    before = set(sys.modules)
    importlib.import_module("apps.api.src.options.decision_framing.narrative_templates")
    importlib.import_module("apps.api.src.options.decision_framing.comparison")
    importlib.import_module("apps.api.src.options.decision_framing.checklist")
    importlib.import_module("apps.api.src.options.decision_framing.framing_service")
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
            f"decision framing indirectly pulled in {f}"
        )


def test_no_llm_or_prompt_generation_code_in_decision_framing():
    """Source must not contain prompt-generation patterns."""
    forbidden_text = (
        r"\bChatCompletion\b",
        r"\bcompletions?\.create\b",
        r"\bopenai\.\w+",
        r"\banthropic\.\w+",
        r"\bsystem_prompt\b",
        r"\bllm\.\w+",
    )
    for p in _df_files():
        src = p.read_text(encoding="utf-8")
        for pat in forbidden_text:
            assert not re.search(pat, src, re.IGNORECASE), (
                f"LLM/prompt pattern {pat!r} in {p.name}"
            )


_FORBIDDEN_USER_FACING = (
    r"\bRecommended\b", r"\bRecommendation\b",
    r"\bBest Trade\b", r"\bTop pick\b", r"\bTrade now\b",
    r"\bAuto-?trade\b",
    r"\bExecute Trade\b", r"\bPlace Order\b",
    r"\bConfidence Score\b", r"\bML Signal\b",
    r"\bPromote\b",
    r"\bStrong setup\b", r"\bThesis\b",
    r"\bConviction\b", r"\bAlpha\b",
)


def test_no_recommendation_language_in_decision_framing():
    for p in _df_files():
        src = p.read_text(encoding="utf-8")
        for pat in _FORBIDDEN_USER_FACING:
            assert not re.search(pat, src), (
                f"forbidden user-facing wording {pat!r} in {p.name}"
            )


def test_decision_framing_disclaimer_defined():
    src = (_DF_DIR / "framing_service.py").read_text(encoding="utf-8")
    flat = re.sub(r"[\s\"]+", " ", src)
    assert "Decision framing provides deterministic review context only" in flat
    assert "not advice, recommendation, or execution guidance" in flat


# Re-exported helpers exist
def test_caveat_for_flag_returns_text_for_known_flag():
    out = caveat_for_flag(FLAG_PIN_RISK_UNCERTAIN_OUTCOME)
    assert out and "Pin risk" in out


def test_render_caveats_returns_unique_lines():
    n = _row(flags=(FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
                    FLAG_PIN_RISK_UNCERTAIN_OUTCOME),
             penalties=[{"code": "MISSING_GREEKS", "points": -3,
                          "label": "x", "reason": "x"}])
    out = render_caveats(n)
    # Pin risk should appear once even though listed twice in flags
    assert sum(1 for c in out if c.startswith("Pin risk")) == 1
