"""Unit tests for decision policy layer."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.src.domain.recommendations.decision_policy import (
    PolicyContext,
    PolicyDecision,
    apply_policy,
)
from apps.api.src.domain.recommendations.recommendation_engine import (
    RecommendationResult,
)


def _result(
    action: str = "Buy",
    composite: str = "0.30",
    confidence: str = "70",
    trend: str | None = None,
    vol: str | None = None,
    dd: str | None = None,
) -> RecommendationResult:
    return RecommendationResult(
        asset_id="a1",
        action=action,
        confidence=Decimal(confidence),
        confidence_label="High",
        enough_data=True,
        engine_version="0.1.0",
        snapshot_hash="snap",
        thesis="test",
        composite_score=Decimal(composite),
        family_scores={"trend_momentum": Decimal("0.3")},
        signals=[],
        tags=["equity"],
        stale_data=False,
        current_price=Decimal("100"),
        trend_regime=trend,
        volatility_regime=vol,
        drawdown_regime=dd,
    )


_THRESHOLDS = {
    "BUY": Decimal("0.25"),
    "HOLD": Decimal("-0.25"),
    "REDUCE": Decimal("-0.65"),
    "SELL": Decimal("-1.0"),
}


# ---------------------------------------------------------------------------
# Passthrough / feature flag
# ---------------------------------------------------------------------------


def test_passthrough_when_disabled() -> None:
    result = _result(vol="high", trend="downtrend", confidence="90")
    ctx = PolicyContext(enabled=False)
    decision = apply_policy(result, ctx, _THRESHOLDS)
    assert decision.adjustments == []
    assert decision.adjusted_action == result.action
    assert decision.adjusted_composite_score == result.composite_score
    assert decision.adjusted_confidence == result.confidence


def test_no_adjustment_when_all_conditions_absent() -> None:
    result = _result(vol="low", trend="uptrend", confidence="70")
    ctx = PolicyContext(enabled=True)
    decision = apply_policy(result, ctx, _THRESHOLDS)
    assert decision.adjustments == []
    assert decision.adjusted_composite_score == result.composite_score
    assert decision.adjusted_confidence == result.confidence
    assert decision.adjusted_action == result.action


# ---------------------------------------------------------------------------
# Rule 1 — High volatility damping
# ---------------------------------------------------------------------------


def test_high_volatility_damps_composite() -> None:
    result = _result(composite="0.40", vol="high")
    ctx = PolicyContext(enabled=True, high_vol_factor=Decimal("0.5"))
    decision = apply_policy(result, ctx, _THRESHOLDS)
    # 0.40 × 0.5 = 0.20 → below BUY (0.25) → Hold
    assert decision.adjusted_composite_score == Decimal("0.20")
    assert decision.adjusted_action == "Hold"
    rules = [a["rule"] for a in decision.adjustments]
    assert "high_volatility_damping" in rules


def test_low_vol_no_damping() -> None:
    result = _result(composite="0.40", vol="low")
    ctx = PolicyContext(enabled=True, high_vol_factor=Decimal("0.5"))
    decision = apply_policy(result, ctx, _THRESHOLDS)
    assert decision.adjusted_composite_score == Decimal("0.40")
    assert "high_volatility_damping" not in [a["rule"] for a in decision.adjustments]


def test_high_vol_damping_disabled() -> None:
    result = _result(composite="0.40", vol="high")
    ctx = PolicyContext(enabled=True, high_vol_damping_enabled=False)
    decision = apply_policy(result, ctx, _THRESHOLDS)
    assert decision.adjusted_composite_score == Decimal("0.40")
    assert decision.adjustments == []


# ---------------------------------------------------------------------------
# Rule 2 — Regime suppression
# ---------------------------------------------------------------------------


def test_trend_regime_suppression() -> None:
    result = _result(composite="0.60", trend="downtrend")
    ctx = PolicyContext(
        enabled=True,
        suppress_regimes=frozenset({("trend", "downtrend")}),
        suppressed_regime_factor=Decimal("0.5"),
    )
    decision = apply_policy(result, ctx, _THRESHOLDS)
    # 0.60 × 0.5 = 0.30 → still Buy (just barely)
    assert decision.adjusted_composite_score == Decimal("0.30")
    supp = [a for a in decision.adjustments if a["rule"] == "regime_suppression"]
    assert len(supp) == 1
    assert supp[0]["dimension"] == "trend"
    assert supp[0]["regime"] == "downtrend"


def test_multi_dimension_suppression_compounds() -> None:
    result = _result(composite="0.80", trend="downtrend", vol="high", dd="severe")
    ctx = PolicyContext(
        enabled=True,
        high_vol_damping_enabled=False,  # isolate suppression rule
        suppress_regimes=frozenset({
            ("trend", "downtrend"),
            ("drawdown", "severe"),
        }),
        suppressed_regime_factor=Decimal("0.5"),
    )
    decision = apply_policy(result, ctx, _THRESHOLDS)
    # 0.80 × 0.5 × 0.5 = 0.20 (two suppressions compound)
    assert decision.adjusted_composite_score == Decimal("0.20")
    rules = [a for a in decision.adjustments if a["rule"] == "regime_suppression"]
    assert len(rules) == 2


def test_no_suppression_when_regime_not_in_set() -> None:
    result = _result(composite="0.40", trend="uptrend")
    ctx = PolicyContext(
        enabled=True,
        suppress_regimes=frozenset({("trend", "downtrend")}),
    )
    decision = apply_policy(result, ctx, _THRESHOLDS)
    assert decision.adjusted_composite_score == Decimal("0.40")


# ---------------------------------------------------------------------------
# Rule 3 — Confidence inversion cap
# ---------------------------------------------------------------------------


def test_confidence_inversion_caps() -> None:
    result = _result(confidence="85")
    ctx = PolicyContext(
        enabled=True,
        confidence_inversion=True,
        confidence_inversion_cap=Decimal("50"),
    )
    decision = apply_policy(result, ctx, _THRESHOLDS)
    assert decision.adjusted_confidence == Decimal("50")
    assert "confidence_inversion_cap" in [a["rule"] for a in decision.adjustments]


def test_confidence_below_cap_not_adjusted() -> None:
    result = _result(confidence="40")
    ctx = PolicyContext(
        enabled=True,
        confidence_inversion=True,
        confidence_inversion_cap=Decimal("50"),
    )
    decision = apply_policy(result, ctx, _THRESHOLDS)
    assert decision.adjusted_confidence == Decimal("40")


def test_no_inversion_cap_when_flag_off() -> None:
    result = _result(confidence="90")
    ctx = PolicyContext(enabled=True, confidence_inversion=False)
    decision = apply_policy(result, ctx, _THRESHOLDS)
    assert decision.adjusted_confidence == Decimal("90")


# ---------------------------------------------------------------------------
# Combined rules + action remap
# ---------------------------------------------------------------------------


def test_rules_compose_and_action_remaps_to_hold() -> None:
    # 0.70 × 0.7 (high vol) × 0.5 (suppressed) = 0.245 → BUY threshold is 0.25 → Hold
    result = _result(composite="0.70", confidence="80", vol="high", trend="downtrend")
    ctx = PolicyContext(
        enabled=True,
        high_vol_factor=Decimal("0.7"),
        suppress_regimes=frozenset({("trend", "downtrend")}),
        suppressed_regime_factor=Decimal("0.5"),
        confidence_inversion=True,
        confidence_inversion_cap=Decimal("50"),
    )
    decision = apply_policy(result, ctx, _THRESHOLDS)
    # Action should drop from Buy to Hold (0.245 < 0.25)
    assert decision.original_action == "Buy"
    assert decision.adjusted_action == "Hold"
    assert decision.adjusted_confidence == Decimal("50")
    assert len(decision.adjustments) == 3


def test_watch_preserved_under_policy() -> None:
    result = _result(action="Watch", composite="0", confidence="0", vol="high")
    ctx = PolicyContext(
        enabled=True,
        suppress_regimes=frozenset({("trend", "downtrend")}),
        confidence_inversion=True,
    )
    decision = apply_policy(result, ctx, _THRESHOLDS)
    # Watch always preserved regardless of score adjustments.
    assert decision.adjusted_action == "Watch"


def test_original_fields_preserved() -> None:
    result = _result(composite="0.40", confidence="80", vol="high")
    ctx = PolicyContext(enabled=True)
    decision = apply_policy(result, ctx, _THRESHOLDS)
    assert decision.original_composite_score == Decimal("0.40")
    assert decision.original_confidence == Decimal("80")
    assert decision.original_action == "Buy"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_determinism_same_input_same_output() -> None:
    result = _result(composite="0.55", confidence="75", vol="high", trend="downtrend")
    ctx = PolicyContext(
        enabled=True,
        suppress_regimes=frozenset({("trend", "downtrend")}),
        confidence_inversion=True,
    )
    d1 = apply_policy(result, ctx, _THRESHOLDS)
    d2 = apply_policy(result, ctx, _THRESHOLDS)
    assert d1.adjusted_composite_score == d2.adjusted_composite_score
    assert d1.adjusted_confidence == d2.adjusted_confidence
    assert d1.adjusted_action == d2.adjusted_action
    assert d1.adjustments == d2.adjustments
