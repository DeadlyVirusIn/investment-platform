"""Phase 11T.3 - rule_comparator unit tests."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from apps.api.src.ml import rule_comparator as rc_mod
from apps.api.src.ml.rule_comparator import (
    ALL_CATEGORIES,
    CAT_AGREEMENT_HIGH,
    CAT_AGREEMENT_LOW,
    CAT_AGREEMENT_MID,
    CAT_DIS_DET_NEG_MODEL_HIGH,
    CAT_DIS_DET_POS_MODEL_LOW,
    CAT_DIS_OTHER,
    SHADOW_HIGH,
    SHADOW_LOW,
    SHADOW_MID,
    categorize,
    compare_model_vs_rule,
)


def test_comparator_agreement_pos_high():
    assert categorize("positive", SHADOW_HIGH) == CAT_AGREEMENT_HIGH


def test_comparator_agreement_neg_low():
    assert categorize("negative", SHADOW_LOW) == CAT_AGREEMENT_LOW


def test_comparator_agreement_mid():
    assert categorize("neutral", SHADOW_MID) == CAT_AGREEMENT_MID


def test_comparator_disagreement_det_pos_model_low():
    assert (
        categorize("positive", SHADOW_LOW) == CAT_DIS_DET_POS_MODEL_LOW
    )


def test_comparator_disagreement_det_neg_model_high():
    assert (
        categorize("negative", SHADOW_HIGH)
        == CAT_DIS_DET_NEG_MODEL_HIGH
    )


def test_comparator_disagreement_other():
    assert categorize("positive", SHADOW_MID) == CAT_DIS_OTHER
    assert categorize("neutral", SHADOW_HIGH) == CAT_DIS_OTHER
    assert categorize(None, SHADOW_HIGH) == CAT_DIS_OTHER


def test_comparator_returns_counts_only():
    rows = [
        {"deterministic_outcome": "positive",
         "model_bucket": SHADOW_HIGH,
         "deterministic_qualified": True},
        {"deterministic_outcome": "negative",
         "model_bucket": SHADOW_LOW,
         "deterministic_qualified": False},
    ]
    out = compare_model_vs_rule(rows)
    assert out.n_total == 2
    assert out.n_agreement == 2
    assert out.n_disagreement == 0


def test_comparator_returns_rates():
    rows = [
        {"deterministic_outcome": "positive",
         "model_bucket": SHADOW_HIGH,
         "deterministic_qualified": True},
        {"deterministic_outcome": "positive",
         "model_bucket": SHADOW_LOW,
         "deterministic_qualified": True},
    ]
    out = compare_model_vs_rule(rows)
    assert out.agreement_rate == 0.5


def test_comparator_no_winner_label():
    src = Path(rc_mod.__file__).read_text(encoding="utf-8")
    for tok in ("winner", "loser", "better", "worse"):
        assert tok not in src.lower(), f"forbidden token {tok!r}"


def test_comparator_no_better_word():
    out = compare_model_vs_rule([])
    # Sanity: no comparison/preference field exists
    assert not hasattr(out, "winner")
    assert not hasattr(out, "is_better")


def test_comparator_no_recommend_word():
    src = Path(rc_mod.__file__).read_text(encoding="utf-8")
    for pat in (
        r"\brecommend\w*", r"\bsignal\b", r"\bbest\s+trade\b",
    ):
        assert not re.search(pat, src, flags=re.IGNORECASE), (
            f"forbidden pattern {pat!r}"
        )


def test_comparator_pure_function():
    """Calling twice with same input yields identical output."""
    rows = [
        {"deterministic_outcome": "negative",
         "model_bucket": SHADOW_HIGH,
         "deterministic_qualified": False},
    ]
    a = compare_model_vs_rule(rows)
    b = compare_model_vs_rule(rows)
    assert a == b


def test_comparator_handles_empty_input():
    out = compare_model_vs_rule([])
    assert out.n_total == 0
    assert out.n_agreement == 0
    assert out.n_disagreement == 0
    assert out.agreement_rate == 0.0


def test_comparator_handles_provisional_rows():
    rows = [
        {"deterministic_outcome": None,
         "model_bucket": SHADOW_HIGH,
         "deterministic_qualified": True,
         "is_provisional": True},
    ]
    out = compare_model_vs_rule(rows)
    assert out.n_total == 1
    # None outcome falls into disagreement_other
    assert out.by_category[CAT_DIS_OTHER] == 1


def test_comparator_qualified_axis_separate_from_outcome_axis():
    rows = [
        {"deterministic_outcome": "positive",
         "model_bucket": SHADOW_HIGH,
         "deterministic_qualified": True},
        {"deterministic_outcome": "positive",
         "model_bucket": SHADOW_LOW,
         "deterministic_qualified": True},
        {"deterministic_outcome": "negative",
         "model_bucket": SHADOW_HIGH,
         "deterministic_qualified": False},
    ]
    out = compare_model_vs_rule(rows)
    # by_qualified_axis tracks (qualified|rejected)x(low|mid|high)
    assert sum(out.by_qualified_axis.values()) == 3
    assert out.deterministic_accepted_model_low == 1
    assert out.deterministic_rejected_model_high == 1


def test_categories_constant_frozen():
    assert ALL_CATEGORIES == (
        "agreement_high", "agreement_low", "agreement_mid",
        "disagreement_det_pos_model_low",
        "disagreement_det_neg_model_high",
        "disagreement_other",
    )


def test_comparator_no_db_imports():
    src = Path(rc_mod.__file__).read_text(encoding="utf-8")
    for tok in (
        "from apps.api.src.db", "INSERT INTO", "session.execute",
    ):
        assert tok not in src, (
            f"comparator must not touch DB: {tok!r}"
        )
