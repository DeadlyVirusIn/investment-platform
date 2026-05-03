"""SYSTEM-ALPHA-4 + gates — policy gating, runtime loader, gate inventory."""

from __future__ import annotations

from apps.api.src.alpha.gate_inventory import GATE_DEFS
from apps.api.src.alpha.rule_policy import (
    RuleAction, RuleMode, evaluate_policy,
)
from apps.api.src.alpha.rule_runtime import (
    ALLOWED_RUNTIME_TYPES, FORBIDDEN_RUNTIME_TYPES, ActiveRule,
    _validate_row,
)

import datetime as dt


# ---------------------------------------------------------------------------
# Runtime loader validation
# ---------------------------------------------------------------------------

def test_runtime_rejects_forbidden_rule_types():
    for t in FORBIDDEN_RUNTIME_TYPES:
        assert _validate_row({"rule_id": "r", "rule_type": t,
                                "parameters": {}}) is False


def test_runtime_accepts_allowed_rule_types():
    for t in ALLOWED_RUNTIME_TYPES:
        assert _validate_row({"rule_id": "r", "rule_type": t,
                                "parameters": {}}) is True


def test_runtime_rejects_unknown_type():
    assert _validate_row({"rule_id": "r",
                            "rule_type": "magic", "parameters": {}}) is False


def test_runtime_rejects_bad_parameters():
    assert _validate_row({"rule_id": "r",
                            "rule_type": "reduce_weight",
                            "parameters": "not-a-dict"}) is False


# ---------------------------------------------------------------------------
# Policy engine constraints
# ---------------------------------------------------------------------------

def _rule(rule_type: str, params: dict) -> ActiveRule:
    return ActiveRule(
        rule_id=f"{rule_type}:r",
        rule_type=rule_type,
        parameters=params,
        applied_at=dt.datetime.now(dt.timezone.utc),
        status="active",
    )


def test_policy_never_exceeds_unity_size():
    rules = [
        _rule("reduce_weight", {
            "feature": "event_risk_score", "bucket": "q4",
            "weight_multiplier": 2.0,     # attacker tries to scale up
        }),
    ]
    adj = evaluate_policy(
        engine_decision={"fire": True},
        symbol="AAPL",
        features={"event_risk_score": 0.9},
        factor_attribution={}, catalyst={}, data_quality={},
        execution_quality={}, portfolio_risk={},
        active_rules=rules,
        mode=RuleMode.PAPER_REDUCE.value,
    )
    assert adj.size_multiplier <= 1.0


def test_policy_multiple_reductions_compound_but_floor():
    rules = [
        _rule("reduce_weight", {
            "feature": "event_risk_score", "bucket": "q4",
            "weight_multiplier": 0.5,
        }),
        _rule("tighten_filters", {"cluster_reason": "bad_timing"}),
    ]
    adj = evaluate_policy(
        engine_decision={}, symbol="AAPL",
        features={"event_risk_score": 0.9},
        factor_attribution={}, catalyst={}, data_quality={},
        execution_quality={}, portfolio_risk={},
        active_rules=rules,
        mode=RuleMode.PAPER_REDUCE.value,
        min_size_multiplier=0.4,
    )
    # 0.5 * 0.7 = 0.35, but floor is 0.4
    assert adj.size_multiplier >= 0.4
    assert adj.size_multiplier <= 1.0


def test_policy_advisory_mode_does_not_change_size():
    rules = [
        _rule("reduce_weight", {
            "feature": "event_risk_score", "bucket": "q4",
            "weight_multiplier": 0.2,
        }),
    ]
    adj = evaluate_policy(
        engine_decision={}, symbol="AAPL",
        features={"event_risk_score": 0.9},
        factor_attribution={}, catalyst={}, data_quality={},
        execution_quality={}, portfolio_risk={},
        active_rules=rules,
        mode=RuleMode.ADVISORY.value,
    )
    assert adj.size_multiplier == 1.0
    assert adj.action == RuleAction.ANNOTATE.value


def test_policy_block_converted_when_allow_block_false():
    rules = [
        _rule("execution_guardrail", {"min_entry_quality": 0.5}),
    ]
    adj = evaluate_policy(
        engine_decision={}, symbol="AAPL",
        features={}, factor_attribution={}, catalyst={}, data_quality={},
        execution_quality={"quality_score": 0.1},   # fails guardrail
        portfolio_risk={},
        active_rules=rules,
        mode=RuleMode.PAPER_FILTER.value,
        allow_block=False,
    )
    assert adj.action != RuleAction.BLOCK_PAPER_TRADE.value


def test_policy_block_respected_when_allow_block_true():
    rules = [
        _rule("execution_guardrail", {"min_entry_quality": 0.5}),
    ]
    adj = evaluate_policy(
        engine_decision={}, symbol="AAPL",
        features={}, factor_attribution={}, catalyst={}, data_quality={},
        execution_quality={"quality_score": 0.1},
        portfolio_risk={},
        active_rules=rules,
        mode=RuleMode.PAPER_FILTER.value,
        allow_block=True,
    )
    assert adj.action == RuleAction.BLOCK_PAPER_TRADE.value


def test_policy_missing_data_skips_rule_without_crash():
    rules = [
        _rule("restrict_concentrated_trades", {"max_concentration": 0.4}),
    ]
    adj = evaluate_policy(
        engine_decision={}, symbol="AAPL",
        features={}, factor_attribution={}, catalyst={}, data_quality={},
        execution_quality={}, portfolio_risk={},  # no concentration
        active_rules=rules,
        mode=RuleMode.PAPER_REDUCE.value,
    )
    assert any(s.reason == "concentration_unavailable"
               for s in adj.skipped_rules)


def test_policy_empty_rules_yields_default_full_size():
    adj = evaluate_policy(
        engine_decision={}, symbol="AAPL",
        features={}, factor_attribution={}, catalyst={}, data_quality={},
        execution_quality={}, portfolio_risk={},
        active_rules=[],
        mode=RuleMode.PAPER_REDUCE.value,
    )
    assert adj.size_multiplier == 1.0
    assert adj.action == RuleAction.NONE.value


# ---------------------------------------------------------------------------
# Gate inventory static checks
# ---------------------------------------------------------------------------

def test_gate_inventory_has_expected_gates():
    ids = {g.gate_id for g in GATE_DEFS}
    assert {"rates_calm", "credit_stable",
             "vrp_supportive", "liquidity_expanding"} <= ids


def test_gate_inventory_has_plain_english_for_all():
    for g in GATE_DEFS:
        assert g.plain_english
        assert g.what_makes_pass
        assert g.source
