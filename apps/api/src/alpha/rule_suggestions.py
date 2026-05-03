"""Convert analyzer findings → actionable suggestions with risk gating.

Every suggestion carries:
  id, type, description, confidence, sample_size, expected_impact,
  risk_level (low/medium/high), auto_applicable (bool), parameters

Risk gating (deterministic):
  * `reduce_weight` / `tighten_threshold` / `execution_guardrail`
    / `restrict_concentrated_trades` → risk_level=low  (filters/reduces)
  * `increase_weight` → risk_level=medium  (adds exposure)
  * `require_confirmation` → risk_level=low
  * Anything increasing position size / removing guardrails is flagged
    risk_level=high and NEVER auto_applicable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from apps.api.src.alpha.rule_analyzer import Finding


DEFAULT_MIN_SAMPLE = 50
DEFAULT_MIN_CONF = 0.70
AUTO_MIN_CONF   = 0.80
AUTO_MIN_SAMPLE = 100


@dataclass
class Suggestion:
    id: str
    rule_id: str
    type: str
    target: str
    description: str
    confidence: float
    sample_size: int
    expected_impact: str           # positive | negative | uncertain
    risk_level: str                # low | medium | high
    auto_applicable: bool
    parameters: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "type": self.type,
            "target": self.target,
            "description": self.description,
            "confidence": round(self.confidence, 4),
            "sample_size": self.sample_size,
            "expected_impact": self.expected_impact,
            "risk_level": self.risk_level,
            "auto_applicable": self.auto_applicable,
            "parameters": dict(self.parameters),
            "details": dict(self.details),
        }


def generate_suggestions(
    findings: list[Finding],
    *,
    min_sample: int = DEFAULT_MIN_SAMPLE,
    min_confidence: float = DEFAULT_MIN_CONF,
) -> list[Suggestion]:
    out: list[Suggestion] = []
    for f in findings:
        if f.sample_size < min_sample or f.confidence < min_confidence:
            continue
        sug = _from_finding(f)
        if sug is not None:
            out.append(sug)
    return out


# ---------------------------------------------------------------------------
def _from_finding(f: Finding) -> Suggestion | None:
    rule_id = _rule_id_for(f)
    if f.rule_type == "signal_weakness":
        return Suggestion(
            id=_uid(f.target, "signal_weakness"),
            rule_id=rule_id,
            type="reduce_weight",
            target=f.target,
            description=(
                f"Reduce weight for {f.target}: observed lift "
                f"{f.details.get('lift', 0):+.4f} below control."
            ),
            confidence=f.confidence,
            sample_size=f.sample_size,
            expected_impact="positive",     # reduces bad trades
            risk_level="low",
            auto_applicable=_is_auto(f),
            parameters={"weight_multiplier": 0.5,
                         "feature": f.details.get("feature"),
                         "bucket": f.details.get("bucket")},
            details=dict(f.details),
        )
    if f.rule_type == "strong_signal":
        # Increase-weight = additive risk → medium, never auto
        return Suggestion(
            id=_uid(f.target, "strong_signal"),
            rule_id=rule_id,
            type="increase_weight" if f.suggestion == "increase_weight"
                  else "require_confirmation",
            target=f.target,
            description=(
                f"{f.suggestion.replace('_', ' ').title()} for "
                f"{f.target}: positive lift "
                f"{f.details.get('lift', 0):+.4f}."
            ),
            confidence=f.confidence,
            sample_size=f.sample_size,
            expected_impact="positive",
            risk_level=(
                "medium" if f.suggestion == "increase_weight" else "low"
            ),
            auto_applicable=(
                f.suggestion == "require_confirmation" and _is_auto(f)
            ),
            parameters={
                "weight_multiplier": (
                    1.3 if f.suggestion == "increase_weight" else 1.0
                ),
                "feature": f.details.get("feature"),
                "bucket": f.details.get("bucket"),
                "require_confirmation":
                    f.suggestion == "require_confirmation",
            },
            details=dict(f.details),
        )
    if f.rule_type == "failure_pattern":
        return Suggestion(
            id=_uid(f.target, "failure"),
            rule_id=rule_id,
            type="tighten_filters",
            target=f.target,
            description=(
                f"Failure cluster: {f.target} accounts for "
                f"{f.details.get('fraction_of_losers', 0):.0%} of losses."
            ),
            confidence=f.confidence,
            sample_size=f.sample_size,
            expected_impact="positive",
            risk_level="low",
            auto_applicable=_is_auto(f),
            parameters={"cluster_reason": f.target,
                         "action": "add_filter"},
            details=dict(f.details),
        )
    if f.rule_type == "execution_issue":
        return Suggestion(
            id=_uid(f.target, "exec"),
            rule_id=rule_id,
            type="execution_guardrail",
            target=f.target,
            description=(
                "Low entry quality correlates with weaker returns. "
                "Add entry guardrail."
            ),
            confidence=f.confidence,
            sample_size=f.sample_size,
            expected_impact="positive",
            risk_level="low",
            auto_applicable=_is_auto(f),
            parameters={"min_entry_quality": 0.5,
                         "action": "block_if_below"},
            details=dict(f.details),
        )
    if f.rule_type == "risk_issue":
        return Suggestion(
            id=_uid(f.target, "risk"),
            rule_id=rule_id,
            type="restrict_concentrated_trades",
            target=f.target,
            description=(
                "High concentration correlates with weaker returns. "
                "Restrict new entries when concentration > 0.4."
            ),
            confidence=f.confidence,
            sample_size=f.sample_size,
            expected_impact="positive",
            risk_level="low",
            auto_applicable=_is_auto(f),
            parameters={"max_concentration": 0.4,
                         "action": "require_confirmation"},
            details=dict(f.details),
        )
    return None


def _is_auto(f: Finding) -> bool:
    return (f.confidence >= AUTO_MIN_CONF
            and f.sample_size >= AUTO_MIN_SAMPLE)


def _uid(target: str, kind: str) -> str:
    return hashlib.sha1(
        f"{kind}|{target}".encode("utf-8"), usedforsecurity=False,
    ).hexdigest()[:16]


def _rule_id_for(f: Finding) -> str:
    return f"{f.rule_type}:{f.target}".lower()
