"""SYSTEM-ALPHA-3 — analyzer, suggestions, thresholds, executor gates."""

from __future__ import annotations

import numpy as np
import pandas as pd

from apps.api.src.alpha.adaptive_thresholds import recommend_thresholds
from apps.api.src.alpha.rule_analyzer import analyze_rules
from apps.api.src.alpha.rule_executor import (
    ALLOWED_AUTO_TYPES, FORBIDDEN_AUTO_TYPES, is_auto_applicable,
)
from apps.api.src.alpha.rule_suggestions import (
    AUTO_MIN_CONF, AUTO_MIN_SAMPLE, Suggestion, generate_suggestions,
)


def _toy(n=500, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "fwd_ret_5d": rng.normal(0.001, 0.02, n),
        "feature_confidence": rng.random(n),
        "event_risk_score": rng.random(n),
        "catalyst_score": rng.random(n),
        "gates_favorable": rng.integers(0, 5, n),
        "regime_stress": rng.integers(0, 2, n),
        "regime_directional": rng.integers(0, 2, n),
        "regime_neutral": rng.integers(0, 2, n),
    })
    # Inject strong pattern: low event_risk_score → better returns
    low_mask = df["event_risk_score"] < 0.25
    df.loc[low_mask, "fwd_ret_5d"] += 0.01
    # Inject weakness: high event_risk_score → worse
    high_mask = df["event_risk_score"] > 0.75
    df.loc[high_mask, "fwd_ret_5d"] -= 0.02
    return df


# ---------------------------------------------------------------------------
# Rule analyzer
# ---------------------------------------------------------------------------

def test_analyzer_returns_empty_on_missing_return_col():
    df = pd.DataFrame({"feature_confidence": [0.5, 0.6]})
    assert analyze_rules(df) == []


def test_analyzer_detects_weak_and_strong_signals():
    df = _toy(n=800)
    findings = analyze_rules(df, min_sample=30, confidence_min=0.5)
    types = {f.rule_type for f in findings}
    assert "signal_weakness" in types or "strong_signal" in types
    for f in findings:
        assert f.sample_size >= 30
        assert 0.0 <= f.confidence <= 1.0


def test_analyzer_small_sample_produces_no_findings():
    df = _toy(n=40)
    findings = analyze_rules(df, min_sample=50, confidence_min=0.7)
    assert findings == []


# ---------------------------------------------------------------------------
# Suggestion generator
# ---------------------------------------------------------------------------

def test_generator_filters_low_sample_or_confidence():
    df = _toy(n=800)
    findings = analyze_rules(df, min_sample=30, confidence_min=0.5)
    sugs = generate_suggestions(findings, min_sample=200,
                                  min_confidence=0.99)
    # Stricter gates → fewer/zero suggestions
    assert len(sugs) <= len(findings)


def test_suggestion_increase_weight_never_auto():
    sug = Suggestion(
        id="x", rule_id="r", type="increase_weight", target="t",
        description="d", confidence=0.99, sample_size=500,
        expected_impact="positive", risk_level="medium",
        auto_applicable=True,   # caller claims True — executor must reject
    )
    ok, reason = is_auto_applicable(sug)
    assert ok is False
    assert "ALLOWED_AUTO_TYPES" in reason or "FORBIDDEN" in reason \
           or "risk_level" in reason


def test_suggestion_reduce_weight_auto_pass():
    sug = Suggestion(
        id="x", rule_id="r", type="reduce_weight", target="t",
        description="d", confidence=0.9, sample_size=200,
        expected_impact="positive", risk_level="low",
        auto_applicable=True,
    )
    ok, _ = is_auto_applicable(sug)
    assert ok is True


def test_suggestion_below_confidence_rejected():
    sug = Suggestion(
        id="x", rule_id="r", type="reduce_weight", target="t",
        description="d", confidence=0.5, sample_size=500,
        expected_impact="positive", risk_level="low",
        auto_applicable=True,
    )
    ok, _ = is_auto_applicable(sug)
    assert ok is False


def test_suggestion_below_sample_rejected():
    sug = Suggestion(
        id="x", rule_id="r", type="reduce_weight", target="t",
        description="d", confidence=0.95, sample_size=10,
        expected_impact="positive", risk_level="low",
        auto_applicable=True,
    )
    ok, _ = is_auto_applicable(sug)
    assert ok is False


def test_suggestion_forbidden_types_fixed():
    assert "increase_position_size" in FORBIDDEN_AUTO_TYPES
    assert "remove_guardrail"       in FORBIDDEN_AUTO_TYPES
    assert "reduce_weight"          in ALLOWED_AUTO_TYPES
    assert "tighten_filters"        in ALLOWED_AUTO_TYPES


# ---------------------------------------------------------------------------
# Adaptive thresholds
# ---------------------------------------------------------------------------

def test_threshold_recs_return_shape():
    df = _toy(n=400)
    recs = recommend_thresholds(df)
    for r in recs:
        d = r.to_dict()
        assert set(d.keys()) >= {
            "threshold", "current", "recommended", "confidence",
            "sample_size", "expected_lift", "risk", "notes",
        }
        assert d["risk"] in {"low", "medium", "high"}


def test_threshold_recs_reject_small_data():
    df = pd.DataFrame({
        "feature_confidence": [0.5, 0.6, 0.7],
        "fwd_ret_5d": [0.01, -0.005, 0.003],
    })
    recs = recommend_thresholds(df)
    assert recs == []


# ---------------------------------------------------------------------------
# Executor constants
# ---------------------------------------------------------------------------

def test_auto_min_constants_are_strict():
    assert AUTO_MIN_CONF >= 0.80
    assert AUTO_MIN_SAMPLE >= 100
