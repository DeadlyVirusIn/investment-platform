"""Rule policy engine — deterministic, never-increase-risk evaluator.

Input: engine decision + context + active rules.
Output: rule_adjustment dict attached to decision. Never mutates engine
decision; paper pipeline chooses whether to consume `size_multiplier` or
the `block_paper_trade` action.

Config read lazily from settings at each call so operator flips land on
next decision without a restart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger

from apps.api.src.alpha.rule_runtime import ActiveRule


class RuleMode(str, Enum):
    ADVISORY      = "advisory"        # default — no execution change
    PAPER_REDUCE  = "paper_reduce"    # size_multiplier only
    PAPER_FILTER  = "paper_filter"    # reduce + confirm + optional block


class RuleAction(str, Enum):
    NONE                  = "none"
    ANNOTATE              = "annotate"
    REDUCE_SIZE           = "reduce_size"
    TIGHTEN_FILTER        = "tighten_filter"
    REQUIRE_CONFIRMATION  = "require_confirmation"
    BLOCK_PAPER_TRADE     = "block_paper_trade"


@dataclass
class AppliedRule:
    rule_id: str
    rule_type: str
    size_impact: float
    reason_code: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_type": self.rule_type,
            "size_impact": round(self.size_impact, 4),
            "reason_code": self.reason_code,
        }


@dataclass
class SkippedRule:
    rule_id: str
    rule_type: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_type": self.rule_type,
            "reason": self.reason,
        }


@dataclass
class RuleAdjustment:
    enabled: bool
    mode: str
    action: str
    size_multiplier: float
    applied_rules: list[AppliedRule] = field(default_factory=list)
    blocked_rules: list[SkippedRule] = field(default_factory=list)
    skipped_rules: list[SkippedRule] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "action": self.action,
            "size_multiplier": round(self.size_multiplier, 4),
            "applied_rules": [r.to_dict() for r in self.applied_rules],
            "blocked_rules": [r.to_dict() for r in self.blocked_rules],
            "skipped_rules": [r.to_dict() for r in self.skipped_rules],
            "reason_codes": list(self.reason_codes),
            "audit": dict(self.audit),
        }


# ---------------------------------------------------------------------------

def evaluate_policy(
    *,
    engine_decision: dict[str, Any],
    symbol: str,
    features: dict[str, Any] | None,
    factor_attribution: dict[str, Any] | None,
    catalyst: dict[str, Any] | None,
    data_quality: dict[str, Any] | None,
    execution_quality: dict[str, Any] | None,
    portfolio_risk: dict[str, Any] | None,
    active_rules: list[ActiveRule],
    mode: str = "advisory",
    allow_block: bool = False,
    min_size_multiplier: float = 0.5,
) -> RuleAdjustment:
    """Compute rule_adjustment for one decision. Never increases size."""
    adj = RuleAdjustment(
        enabled=True, mode=mode, action=RuleAction.NONE.value,
        size_multiplier=1.0,
    )
    if not active_rules:
        adj.reason_codes.append("no_active_rules")
        return adj

    size_mult = 1.0
    require_confirmation = False
    block = False

    features = features or {}
    catalyst = catalyst or {}
    data_quality = data_quality or {}
    execution_quality = execution_quality or {}
    portfolio_risk = portfolio_risk or {}

    for rule in active_rules:
        try:
            outcome = _evaluate_single_rule(
                rule, engine_decision=engine_decision, symbol=symbol,
                features=features, factor_attribution=factor_attribution,
                catalyst=catalyst, data_quality=data_quality,
                execution_quality=execution_quality,
                portfolio_risk=portfolio_risk,
            )
        except Exception as e:
            logger.warning(
                "rule_policy: rule {} crashed: {}", rule.rule_id, e,
            )
            adj.skipped_rules.append(SkippedRule(
                rule_id=rule.rule_id, rule_type=rule.rule_type,
                reason=f"crash:{type(e).__name__}",
            ))
            continue
        if outcome is None:
            adj.skipped_rules.append(SkippedRule(
                rule_id=rule.rule_id, rule_type=rule.rule_type,
                reason="rule_not_applicable",
            ))
            continue
        if outcome.get("skip_reason"):
            adj.skipped_rules.append(SkippedRule(
                rule_id=rule.rule_id, rule_type=rule.rule_type,
                reason=outcome["skip_reason"],
            ))
            continue

        action = outcome.get("action")
        size_impact = float(outcome.get("size_multiplier") or 1.0)
        # HARD FLOOR — never increase size
        size_impact = min(1.0, max(0.0, size_impact))
        size_mult = size_mult * size_impact
        if action == RuleAction.REQUIRE_CONFIRMATION.value:
            require_confirmation = True
        if action == RuleAction.BLOCK_PAPER_TRADE.value:
            block = True

        adj.applied_rules.append(AppliedRule(
            rule_id=rule.rule_id, rule_type=rule.rule_type,
            size_impact=size_impact,
            reason_code=outcome.get("reason_code", ""),
        ))
        adj.reason_codes.append(outcome.get("reason_code", ""))

    # Floor size_multiplier
    size_mult = max(min_size_multiplier, min(1.0, size_mult))

    # Determine final action by mode
    if mode == RuleMode.ADVISORY.value:
        final_action = RuleAction.ANNOTATE.value
        # Do NOT apply multiplier downstream — leave engine size intact
        adj.size_multiplier = 1.0
    elif mode == RuleMode.PAPER_REDUCE.value:
        # Apply size reduction only; confirm/block downgraded
        adj.size_multiplier = size_mult
        if size_mult < 1.0:
            final_action = RuleAction.REDUCE_SIZE.value
        else:
            final_action = RuleAction.NONE.value
        if require_confirmation or block:
            adj.reason_codes.append("downgraded_confirm_block_in_paper_reduce")
    elif mode == RuleMode.PAPER_FILTER.value:
        adj.size_multiplier = size_mult
        if block and allow_block:
            final_action = RuleAction.BLOCK_PAPER_TRADE.value
        elif block and not allow_block:
            # Downgrade block to require_confirmation
            final_action = RuleAction.REQUIRE_CONFIRMATION.value
            adj.reason_codes.append("block_downgraded_to_confirmation")
        elif require_confirmation:
            final_action = RuleAction.REQUIRE_CONFIRMATION.value
        elif size_mult < 1.0:
            final_action = RuleAction.REDUCE_SIZE.value
        else:
            final_action = RuleAction.NONE.value
    else:
        # Unknown mode → advisory for safety
        final_action = RuleAction.ANNOTATE.value
        adj.size_multiplier = 1.0
        adj.reason_codes.append(f"unknown_mode_{mode}")

    adj.action = final_action
    adj.audit = {
        "raw_size_mult": round(size_mult, 4),
        "require_confirmation": require_confirmation,
        "block_raised": block,
        "allow_block": allow_block,
        "min_floor": min_size_multiplier,
    }
    return adj


# ---------------------------------------------------------------------------
# per-rule evaluators
# ---------------------------------------------------------------------------

def _evaluate_single_rule(
    rule: ActiveRule, *,
    engine_decision: dict[str, Any],
    symbol: str,
    features: dict[str, Any],
    factor_attribution: dict[str, Any] | None,
    catalyst: dict[str, Any],
    data_quality: dict[str, Any],
    execution_quality: dict[str, Any],
    portfolio_risk: dict[str, Any],
) -> dict[str, Any] | None:
    """Deterministic handler per rule_type. Returns dict or None to skip."""
    p = rule.parameters or {}
    if rule.rule_type == "reduce_weight":
        feat = p.get("feature")
        bucket = p.get("bucket")
        mult = float(p.get("weight_multiplier", 1.0))
        if feat is None or bucket is None:
            return {"skip_reason": "missing_feature_or_bucket"}
        value = features.get(feat)
        if value is None:
            return {"skip_reason": f"feature_{feat}_missing"}
        if not _matches_bucket(value, bucket):
            return None
        # Reduce only — never > 1.0
        return {
            "action": "reduce_size",
            "size_multiplier": min(1.0, mult),
            "reason_code": f"reduce_weight:{feat}:{bucket}",
        }
    if rule.rule_type == "tighten_filters":
        reason = p.get("cluster_reason")
        # No direct features to match; annotate-only reduction
        return {
            "action": "reduce_size",
            "size_multiplier": 0.7,
            "reason_code": f"tighten_filters:{reason or 'cluster'}",
        }
    if rule.rule_type == "execution_guardrail":
        min_q = float(p.get("min_entry_quality", 0.5))
        q_score = execution_quality.get("quality_score")
        if q_score is None:
            return {"skip_reason": "entry_quality_unavailable"}
        if float(q_score) < min_q:
            return {
                "action": "block_paper_trade",
                "size_multiplier": 0.0,
                "reason_code": (
                    f"execution_guardrail:quality<{min_q}"
                ),
            }
        return None
    if rule.rule_type == "restrict_concentrated_trades":
        max_c = float(p.get("max_concentration", 0.4))
        conc = portfolio_risk.get("concentration_score")
        if conc is None:
            return {"skip_reason": "concentration_unavailable"}
        if float(conc) > max_c:
            return {
                "action": "require_confirmation",
                "size_multiplier": 0.5,
                "reason_code": f"restrict_concentration>{max_c}",
            }
        return None
    if rule.rule_type == "tighten_threshold":
        threshold_name = p.get("threshold")
        min_val = p.get("min_value")
        # Map known thresholds
        val = {
            "min_data_confidence": data_quality.get("confidence"),
            "max_event_risk":      catalyst.get("event_risk_score"),
            "min_gates_favorable": features.get("gates_favorable"),
        }.get(str(threshold_name))
        if val is None:
            return {"skip_reason": f"{threshold_name}_missing"}
        try:
            v = float(val)
            m = float(min_val) if min_val is not None else None
        except (TypeError, ValueError):
            return {"skip_reason": "bad_threshold_value"}
        # Below threshold → block-worthy; default reduce
        if m is not None and v < m:
            return {
                "action": "reduce_size",
                "size_multiplier": 0.5,
                "reason_code": f"tighten_threshold:{threshold_name}<{m}",
            }
        return None
    return {"skip_reason": f"unsupported_rule_type:{rule.rule_type}"}


def _matches_bucket(value: Any, bucket: str) -> bool:
    """Crude bucket match — supports boolean 'true'/'false' and 'qN'."""
    try:
        if bucket in {"true", "false"}:
            v = bool(value) if not isinstance(value, bool) else value
            return (bucket == "true" and v) or (bucket == "false" and not v)
        if bucket.startswith("q"):
            # Quartile match requires upstream distribution — conservative
            # fallback: treat q4 as "top 25%" via >= 0.75 proxy
            if bucket == "q4":
                return float(value) >= 0.75
            if bucket == "q1":
                return float(value) <= 0.25
            if bucket == "q2":
                return 0.25 < float(value) <= 0.5
            if bucket == "q3":
                return 0.5 < float(value) <= 0.75
    except (TypeError, ValueError):
        return False
    return False
