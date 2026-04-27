"""Phase 11I unit tests — pure-fn decision support modules.

Covers:
  * Bucket classification cascade (5 buckets, deterministic)
  * Severe flag detection
  * Data-quality penalty detection
  * Ranking determinism + tie-breaker order
  * Ranking explanation always present per row
  * Boundary import scan — no V2/equity/ML/paper-engine-mutation
  * No mutating SQL or session calls
  * No recommendation language in serialised output
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

from apps.api.src.options.decision_support.buckets import (
    BUCKET_DATA_QUALITY_REVIEW,
    BUCKET_EXCLUDED,
    BUCKET_HIGH_REVIEW_PRIORITY,
    BUCKET_MODEL_LIMITATION_REVIEW,
    BUCKET_NEUTRAL,
    DATA_QUALITY_PENALTY_CODES,
    EXCLUDED_MAX_SCORE,
    HIGH_PRIORITY_MIN_SCORE,
    SEVERE_FLAGS,
    classify,
    has_data_quality_penalty,
    has_severe_flag,
    severe_flag_count,
)
from apps.api.src.options.decision_support.ranking import (
    TIE_BREAKERS,
    rank,
)
from apps.api.src.options.paper.expiration import (
    FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
    FLAG_MISSING_SETTLEMENT,
    FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
)


def _score(
    *,
    id="SPY:2026-04-27:SHORT_PUT_CREDIT_SPREAD",
    total=80,
    qualified=True,
    flags=(),
    penalties=(),
    components=None,
    as_of_date="2026-04-27",
) -> dict:
    return {
        "id": id,
        "total_score": int(total),
        "qualified": bool(qualified),
        "flags": list(flags),
        "penalties": list(penalties),
        "components": components or [
            {"component": "liquidity",   "weight_max": 25, "score": 22, "explanation": "x"},
            {"component": "risk_reward", "weight_max": 25, "score": 18, "explanation": "x"},
            {"component": "vol_context", "weight_max": 20, "score": 14, "explanation": "x"},
            {"component": "structure",   "weight_max": 20, "score": 18, "explanation": "x"},
        ],
        "as_of_date": as_of_date,
        "rule_id": "SHORT_PUT_CREDIT_SPREAD",
        "underlying": "SPY",
    }


# ===========================================================================
# Bucket classification
# ===========================================================================

def test_high_review_priority_when_score_high_qualified_clean():
    s = _score(total=85, qualified=True, flags=(), penalties=())
    bucket, reason = classify(s)
    assert bucket == BUCKET_HIGH_REVIEW_PRIORITY
    assert "High review priority" in reason


def test_excluded_when_score_below_threshold():
    s = _score(total=40, qualified=True)
    bucket, _ = classify(s)
    assert bucket == BUCKET_EXCLUDED


def test_excluded_when_unqualified_no_severe_flag():
    s = _score(total=70, qualified=False)
    bucket, _ = classify(s)
    assert bucket == BUCKET_EXCLUDED


def test_model_limitation_when_severe_flag_present():
    s = _score(total=70, qualified=True, flags=(FLAG_PIN_RISK_UNCERTAIN_OUTCOME,))
    bucket, _ = classify(s)
    assert bucket == BUCKET_MODEL_LIMITATION_REVIEW


def test_model_limitation_assignment_simplified_exit():
    s = _score(total=70, qualified=True, flags=(FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,))
    bucket, _ = classify(s)
    assert bucket == BUCKET_MODEL_LIMITATION_REVIEW


def test_model_limitation_missing_settlement():
    s = _score(total=70, qualified=True, flags=(FLAG_MISSING_SETTLEMENT,))
    bucket, _ = classify(s)
    assert bucket == BUCKET_MODEL_LIMITATION_REVIEW


def test_data_quality_when_dq_penalty_present_no_severe_flag():
    s = _score(
        total=70, qualified=True,
        penalties=[{"code": "MISSING_GREEKS", "points": -3, "label": "x", "reason": "x"}],
    )
    bucket, _ = classify(s)
    assert bucket == BUCKET_DATA_QUALITY_REVIEW


def test_neutral_when_mid_range_clean():
    s = _score(total=65, qualified=True, flags=(), penalties=())
    bucket, _ = classify(s)
    assert bucket == BUCKET_NEUTRAL


def test_excluded_severe_combo_when_unqualified():
    s = _score(total=80, qualified=False,
               flags=(FLAG_PIN_RISK_UNCERTAIN_OUTCOME,))
    bucket, _ = classify(s)
    assert bucket == BUCKET_EXCLUDED


# ===========================================================================
# Severe flag + DQ helpers
# ===========================================================================

def test_severe_flag_count_counts_only_severe():
    s = _score(flags=(FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
                      "MISSING_IV", FLAG_MISSING_SETTLEMENT))
    assert severe_flag_count(s) == 2


def test_has_severe_flag_true_when_present():
    assert has_severe_flag(_score(flags=(FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,)))


def test_has_severe_flag_false_when_absent():
    assert not has_severe_flag(_score(flags=()))


def test_has_data_quality_penalty():
    s = _score(penalties=[{"code": "MISSING_IV", "points": -3,
                            "label": "x", "reason": "x"}])
    assert has_data_quality_penalty(s)


def test_has_data_quality_penalty_negative_for_unrelated_code():
    s = _score(penalties=[{"code": "UNRELATED", "points": -3,
                            "label": "x", "reason": "x"}])
    assert not has_data_quality_penalty(s)


# ===========================================================================
# Ranking determinism + tie-breakers
# ===========================================================================

def test_ranking_is_deterministic_same_inputs_same_order():
    rows = [
        _score(id="A", total=70),
        _score(id="B", total=85),
        _score(id="C", total=85),
    ]
    out_a = [r["id"] for r in rank(rows)]
    out_b = [r["id"] for r in rank(rows)]
    assert out_a == out_b


def test_ranking_orders_by_score_desc_first():
    rows = [
        _score(id="LOW",  total=40),
        _score(id="HIGH", total=90),
        _score(id="MID",  total=70),
    ]
    ids = [r["id"] for r in rank(rows)]
    assert ids == ["HIGH", "MID", "LOW"]


def test_ranking_severe_flag_count_breaks_ties():
    rows = [
        _score(id="A", total=80, flags=(FLAG_PIN_RISK_UNCERTAIN_OUTCOME,)),
        _score(id="B", total=80, flags=()),
    ]
    ids = [r["id"] for r in rank(rows)]
    # Fewer severe flags wins
    assert ids == ["B", "A"]


def test_ranking_liquidity_breaks_score_and_severe_ties():
    base = _score(id="X", total=80, flags=())
    rows = [
        {**base, "id": "LO_LIQ", "components": [
            {"component": "liquidity", "weight_max": 25, "score": 10, "explanation": ""},
            {"component": "risk_reward", "weight_max": 25, "score": 15, "explanation": ""},
            {"component": "vol_context", "weight_max": 20, "score": 10, "explanation": ""},
            {"component": "structure", "weight_max": 20, "score": 10, "explanation": ""},
        ]},
        {**base, "id": "HI_LIQ", "components": [
            {"component": "liquidity", "weight_max": 25, "score": 22, "explanation": ""},
            {"component": "risk_reward", "weight_max": 25, "score": 15, "explanation": ""},
            {"component": "vol_context", "weight_max": 20, "score": 10, "explanation": ""},
            {"component": "structure", "weight_max": 20, "score": 10, "explanation": ""},
        ]},
    ]
    ids = [r["id"] for r in rank(rows)]
    assert ids == ["HI_LIQ", "LO_LIQ"]


def test_ranking_newer_date_breaks_remaining_ties():
    rows = [
        _score(id="OLD", total=80, as_of_date="2026-01-01"),
        _score(id="NEW", total=80, as_of_date="2026-04-27"),
    ]
    ids = [r["id"] for r in rank(rows)]
    assert ids == ["NEW", "OLD"]


def test_ranking_id_alpha_final_tie_break():
    rows = [
        _score(id="Z", total=80, as_of_date="2026-04-27"),
        _score(id="A", total=80, as_of_date="2026-04-27"),
    ]
    ids = [r["id"] for r in rank(rows)]
    assert ids == ["A", "Z"]


def test_each_row_has_ranking_explanation_and_tie_breakers():
    rows = [_score(id="X", total=80)]
    ranked = rank(rows)
    assert ranked[0]["rank_position"] == 1
    assert "deterministic sort" in ranked[0]["ranking_explanation"]
    assert ranked[0]["tie_breakers"] == list(TIE_BREAKERS)


def test_tie_breakers_documented_order_matches_constant():
    assert TIE_BREAKERS == (
        "evaluation_score DESC",
        "severe_flag_count ASC",
        "liquidity_component_score DESC",
        "as_of_date DESC",
        "observation_id ASC",
    )


# ===========================================================================
# Source-static — no mutation, no V2/ML/paper-engine-mutation, no
# recommendation language
# ===========================================================================

_DS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "src" / "options" / "decision_support"
)


def _ds_files() -> list[Path]:
    return list(_DS_DIR.rglob("*.py"))


_FORBIDDEN_DECORATORS = (
    r"@router\.post\b", r"@router\.put\b",
    r"@router\.patch\b", r"@router\.delete\b",
)


def test_no_router_decorators_in_decision_support_modules():
    for p in _ds_files():
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


def test_no_mutating_sql_in_decision_support_modules():
    for p in _ds_files():
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
    r"options\.paper\.engine\b",
)


def test_no_forbidden_imports_in_decision_support():
    for p in _ds_files():
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


def test_decision_support_modules_import_in_isolation():
    import sys
    before = set(sys.modules)
    importlib.import_module("apps.api.src.options.decision_support.buckets")
    importlib.import_module("apps.api.src.options.decision_support.ranking")
    importlib.import_module("apps.api.src.options.decision_support.review_queue")
    importlib.import_module("apps.api.src.options.decision_support.diagnostics")
    after = set(sys.modules)
    new_modules = after - before
    forbidden = (
        "v2_promotion_gates", "v2_promotion_state", "v2_promotion_snapshot",
        "v2_oos_monitoring", "v2_stat_validation", "b2_v2_comparison",
        "engine_b", "shadow_strategy",
        "ml_hybrid", "ml_research", "ml_replay",
        "options.paper.engine",
    )
    for f in forbidden:
        assert not any(f in m for m in new_modules), (
            f"decision support indirectly pulled in {f}"
        )


_FORBIDDEN_USER_FACING = (
    r"\bRecommended\b", r"\bRecommendation\b",
    r"\bBest Trade\b", r"\bTop pick\b", r"\bTrade now\b",
    r"\bAuto-?trade\b",
    r"\bExecute Trade\b", r"\bPlace Order\b",
    r"\bConfidence Score\b", r"\bML Signal\b",
    r"\bPromote\b",
)


def test_no_recommendation_language_in_decision_support():
    for p in _ds_files():
        src = p.read_text(encoding="utf-8")
        for pat in _FORBIDDEN_USER_FACING:
            assert not re.search(pat, src), (
                f"forbidden user-facing wording {pat!r} in {p.name}"
            )


def test_decision_support_disclaimer_defined_in_review_queue():
    """Disclaimer constant defined in review_queue.py; diagnostics.py
    imports it. We assert the literal exists in the defining module
    (after stripping quotes + whitespace). The runtime payload is
    smoke-tested via the integration suite."""
    src = (_DS_DIR / "review_queue.py").read_text(encoding="utf-8")
    flat = re.sub(r"[\s\"]+", " ", src)
    assert "Review queues are for human inspection only" in flat
    assert "not trade recommendations or execution guidance" in flat
    # diagnostics.py must consume the constant by name
    diag = (_DS_DIR / "diagnostics.py").read_text(encoding="utf-8")
    assert "DECISION_SUPPORT_DISCLAIMER" in diag
