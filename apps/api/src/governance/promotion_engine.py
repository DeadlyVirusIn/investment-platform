"""ML promotion-readiness state machine.

Pure function. Takes observed metrics + thresholds; returns one of
NOT_READY / READY_FOR_REVIEW / BLOCKED with full per-gate breakdown.

NEVER auto-promotes. Output is consumed by Ops UI + nightly logs and
discarded unless an operator manually flips ML_HYBRID_MODE via the
admin endpoint.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


# Defaults — match settings.ML_PROMOTION_*
DEFAULTS = dict(
    min_outcomes=30,
    min_advice=20,
    required_healthy_days=7,
    max_ece=0.10,
    max_false_avoid=0.35,
    max_false_allow=0.35,
    min_delta_sharpe_vs_det=0.0,
    min_delta_sharpe_vs_baseline=0.0,
    min_engine_a_avg_multiplier=0.85,
)


@dataclass
class PromotionInputs:
    labeled_outcomes: int
    advice_count: int
    healthy_days: int
    ece: float | None
    false_avoid_rate: float | None
    false_allow_rate: float | None
    delta_sharpe_vs_deterministic: float | None
    delta_sharpe_vs_baseline: float | None
    engine_a_avg_multiplier: float | None
    model_status: str | None
    operator_approval: bool = False
    # Hard blockers
    ml_can_affect_trades: bool = False
    underperforming_baseline: bool = False


@dataclass
class GateResult:
    name: str
    passed: bool
    actual: Any
    threshold: Any
    note: str = ""

    def to_dict(self) -> dict:
        def _f(v):
            if isinstance(v, float):
                return None if not math.isfinite(v) else round(v, 4)
            return v
        return {
            "name": self.name, "passed": bool(self.passed),
            "actual": _f(self.actual), "threshold": _f(self.threshold),
            "note": self.note,
        }


@dataclass
class PromotionVerdict:
    state: str                  # NOT_READY | READY_FOR_REVIEW | BLOCKED
    gates: list[GateResult] = field(default_factory=list)
    failed_gates: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    recommendation: str = ""
    operator_approval_required: bool = True

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "gates": [g.to_dict() for g in self.gates],
            "failed_gates": list(self.failed_gates),
            "blockers": list(self.blockers),
            "recommendation": self.recommendation,
            "operator_approval_required": True,
            "auto_promote": False,
        }


def evaluate(
    inputs: PromotionInputs,
    *,
    thresholds: dict | None = None,
) -> PromotionVerdict:
    """Compute promotion verdict. NEVER promotes. NEVER mutates."""
    th = {**DEFAULTS, **(thresholds or {})}
    gates: list[GateResult] = []

    # Hard blockers — short-circuit BLOCKED state regardless of metrics.
    blockers: list[str] = []
    if inputs.ml_can_affect_trades:
        blockers.append("ML_CAN_AFFECT_TRADES is true — hard block")
    if inputs.underperforming_baseline:
        blockers.append("system underperforms baselines")

    def _gate(name: str, ok: bool, actual, threshold,
                note: str = "") -> None:
        gates.append(GateResult(name=name, passed=bool(ok),
                                  actual=actual, threshold=threshold,
                                  note=note))

    _gate("min_labeled_outcomes",
           inputs.labeled_outcomes >= th["min_outcomes"],
           inputs.labeled_outcomes, th["min_outcomes"])
    _gate("min_advice",
           inputs.advice_count >= th["min_advice"],
           inputs.advice_count, th["min_advice"])
    _gate("min_healthy_days",
           inputs.healthy_days >= th["required_healthy_days"],
           inputs.healthy_days, th["required_healthy_days"])
    _gate("max_ece",
           inputs.ece is not None and float(inputs.ece) < th["max_ece"],
           inputs.ece, th["max_ece"],
           note="" if inputs.ece is not None else "no ECE yet")
    _gate("max_false_avoid",
           (inputs.false_avoid_rate is None
            or float(inputs.false_avoid_rate) < th["max_false_avoid"]),
           inputs.false_avoid_rate, th["max_false_avoid"])
    _gate("max_false_allow",
           (inputs.false_allow_rate is None
            or float(inputs.false_allow_rate) < th["max_false_allow"]),
           inputs.false_allow_rate, th["max_false_allow"])
    _gate("delta_sharpe_vs_deterministic",
           (inputs.delta_sharpe_vs_deterministic is not None
            and float(inputs.delta_sharpe_vs_deterministic)
                > th["min_delta_sharpe_vs_det"]),
           inputs.delta_sharpe_vs_deterministic,
           th["min_delta_sharpe_vs_det"])
    _gate("delta_sharpe_vs_baseline",
           (inputs.delta_sharpe_vs_baseline is not None
            and float(inputs.delta_sharpe_vs_baseline)
                > th["min_delta_sharpe_vs_baseline"]),
           inputs.delta_sharpe_vs_baseline,
           th["min_delta_sharpe_vs_baseline"])
    _gate("engine_a_avg_multiplier",
           (inputs.engine_a_avg_multiplier is None
            or float(inputs.engine_a_avg_multiplier)
                >= th["min_engine_a_avg_multiplier"]),
           inputs.engine_a_avg_multiplier,
           th["min_engine_a_avg_multiplier"],
           note="ML must NOT systematically down-weight Engine A")
    _gate("model_status_outperforming",
           inputs.model_status == "SHADOW_OUTPERFORMING",
           inputs.model_status, "SHADOW_OUTPERFORMING")
    _gate("operator_approval",
           bool(inputs.operator_approval),
           inputs.operator_approval, True,
           note="Always required — never automatic")

    failed = [g.name for g in gates if not g.passed]

    if blockers:
        state = "BLOCKED"
        reco = ("Blocked by: " + "; ".join(blockers)
                + ". Resolve before re-evaluating.")
    elif not failed:
        state = "READY_FOR_REVIEW"
        reco = ("All gates clean. Operator may review and switch "
                "ML_HYBRID_MODE → paper_reduce. Never automatic.")
    else:
        state = "NOT_READY"
        reco = (f"{len(failed)} gate(s) failing: "
                + ", ".join(failed[:4])
                + (". Continue advisory accumulation." if not blockers
                   else ""))

    return PromotionVerdict(
        state=state, gates=gates,
        failed_gates=failed, blockers=blockers,
        recommendation=reco,
        operator_approval_required=True,
    )
