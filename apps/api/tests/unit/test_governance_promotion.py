"""Tests for governance.promotion_engine — gate state machine."""

from __future__ import annotations

from src.governance.promotion_engine import (
    DEFAULTS,
    PromotionInputs,
    evaluate,
)


def _clean_inputs(**overrides) -> PromotionInputs:
    base = dict(
        labeled_outcomes=100,
        advice_count=50,
        healthy_days=10,
        ece=0.05,
        false_avoid_rate=0.10,
        false_allow_rate=0.10,
        delta_sharpe_vs_deterministic=0.5,
        delta_sharpe_vs_baseline=0.3,
        engine_a_avg_multiplier=1.0,
        model_status="SHADOW_OUTPERFORMING",
        operator_approval=True,
        ml_can_affect_trades=False,
        underperforming_baseline=False,
    )
    base.update(overrides)
    return PromotionInputs(**base)


def test_clean_inputs_ready_for_review():
    v = evaluate(_clean_inputs())
    assert v.state == "READY_FOR_REVIEW"
    assert v.failed_gates == []
    assert v.blockers == []
    d = v.to_dict()
    assert d["operator_approval_required"] is True
    assert d["auto_promote"] is False


def test_hard_blocker_ml_can_affect_trades():
    v = evaluate(_clean_inputs(ml_can_affect_trades=True))
    assert v.state == "BLOCKED"
    assert any("hard block" in b.lower() for b in v.blockers)


def test_hard_blocker_underperforming_baseline():
    v = evaluate(_clean_inputs(underperforming_baseline=True))
    assert v.state == "BLOCKED"
    assert any("baseline" in b.lower() for b in v.blockers)


def test_insufficient_outcomes_not_ready():
    v = evaluate(_clean_inputs(labeled_outcomes=5))
    assert v.state == "NOT_READY"
    assert "min_labeled_outcomes" in v.failed_gates


def test_high_ece_blocks_readiness():
    v = evaluate(_clean_inputs(ece=0.5))
    assert v.state == "NOT_READY"
    assert "max_ece" in v.failed_gates


def test_negative_delta_sharpe_blocks():
    v = evaluate(_clean_inputs(delta_sharpe_vs_deterministic=-0.5))
    assert v.state == "NOT_READY"
    assert "delta_sharpe_vs_deterministic" in v.failed_gates


def test_engine_a_systematic_downweight_blocks():
    v = evaluate(_clean_inputs(engine_a_avg_multiplier=0.5))
    assert v.state == "NOT_READY"
    assert "engine_a_avg_multiplier" in v.failed_gates


def test_model_status_must_be_outperforming():
    v = evaluate(_clean_inputs(model_status="SHADOW_TRAINING"))
    assert v.state == "NOT_READY"
    assert "model_status_outperforming" in v.failed_gates


def test_operator_approval_required():
    v = evaluate(_clean_inputs(operator_approval=False))
    assert v.state == "NOT_READY"
    assert "operator_approval" in v.failed_gates


def test_auto_promote_always_false():
    for cfg in [_clean_inputs(),
                _clean_inputs(ml_can_affect_trades=True),
                _clean_inputs(labeled_outcomes=0)]:
        d = evaluate(cfg).to_dict()
        assert d["auto_promote"] is False
        assert d["operator_approval_required"] is True


def test_threshold_overrides():
    v = evaluate(_clean_inputs(labeled_outcomes=15),
                  thresholds={"min_outcomes": 10})
    assert v.state == "READY_FOR_REVIEW"


def test_defaults_present():
    for k in (
        "min_outcomes", "min_advice", "required_healthy_days",
        "max_ece", "max_false_avoid", "max_false_allow",
        "min_delta_sharpe_vs_det", "min_delta_sharpe_vs_baseline",
        "min_engine_a_avg_multiplier",
    ):
        assert k in DEFAULTS
