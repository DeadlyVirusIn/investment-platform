"""Paper-exploratory gate evaluator.

Pure function: given strict selector output + context + config, decide
whether a paper-only reduced-size decision is allowed. Never touches
execution path; caller persists result to decision_log.

Rules (strict safety):
  * Never overrides strict mode — only reached when selector returned
    fire=False AND PAPER_GATE_MODE=exploratory.
  * Never allows entry when:
      - severe anomaly present (if PAPER_EXPLORATORY_BLOCK_ON_ANOMALY)
      - risk not low (if PAPER_EXPLORATORY_REQUIRE_LOW_RISK)
      - data quality below floor
  * Applies fixed size multiplier — no dynamic scaling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExploratoryResult:
    allowed: bool
    reason: str
    size_multiplier: float
    gates_passed: int
    gates_total: int
    gates_failed: list[str] = field(default_factory=list)
    strict_would_block: bool = True
    severity_blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "size_multiplier": round(self.size_multiplier, 4),
            "gates_passed": self.gates_passed,
            "gates_total":  self.gates_total,
            "gates_failed": list(self.gates_failed),
            "strict_would_block": self.strict_would_block,
            "severity_blockers": list(self.severity_blockers),
        }


def evaluate_exploratory(
    *,
    strict_fire: bool,
    context_values: dict[str, Any] | None,
    anomaly_severity: str | None = None,     # "critical" | "warning" | None
    risk_level: str | None = None,            # "low" | "medium" | "high" | None
    data_confidence: float | None = None,
    # Config (read from settings at callsite)
    gate_mode: str = "strict",
    min_gates: int = 2,
    size_multiplier: float = 0.25,
    require_low_risk: bool = True,
    block_on_anomaly: bool = True,
    min_data_confidence: float = 0.5,
    required_gates: tuple[str, ...] = (
        "rates_calm", "vrp_supportive",
        "credit_stable", "liquidity_expanding",
    ),
) -> ExploratoryResult:
    """Return ExploratoryResult. `allowed=True` → paper may proceed at
    reduced size with the exploratory tag."""
    ctx = context_values or {}
    passed = [g for g in required_gates if bool(ctx.get(g))]
    failed = [g for g in required_gates if ctx.get(g) is False]
    g_pass = len(passed)
    g_total = len(required_gates)

    # Strict-mode short circuit: must be fire=False AND strict wouldn't fire
    strict_would_block = not strict_fire

    if gate_mode != "exploratory":
        return ExploratoryResult(
            allowed=False,
            reason="gate_mode=strict — exploratory disabled",
            size_multiplier=0.0,
            gates_passed=g_pass, gates_total=g_total,
            gates_failed=failed,
            strict_would_block=strict_would_block,
        )

    if strict_fire:
        # Strict already fires — not exploratory territory
        return ExploratoryResult(
            allowed=False,
            reason="strict mode already firing — exploratory not needed",
            size_multiplier=0.0,
            gates_passed=g_pass, gates_total=g_total,
            gates_failed=failed,
            strict_would_block=False,
        )

    severity_blockers: list[str] = []

    # Anomaly gate — critical always blocks
    if anomaly_severity == "critical":
        severity_blockers.append("critical_anomaly")
    if block_on_anomaly and anomaly_severity in {"critical", "warning"}:
        severity_blockers.append("anomaly_present")

    # Risk gate
    if require_low_risk and risk_level not in {None, "low"}:
        severity_blockers.append(f"risk_level={risk_level}")

    # Data quality gate
    if data_confidence is not None and data_confidence < min_data_confidence:
        severity_blockers.append(
            f"data_confidence {data_confidence:.2f} < {min_data_confidence}"
        )

    # Gate count
    if g_pass < min_gates:
        return ExploratoryResult(
            allowed=False,
            reason=(f"gates_passed {g_pass} < "
                    f"exploratory_min {min_gates}"),
            size_multiplier=0.0,
            gates_passed=g_pass, gates_total=g_total,
            gates_failed=failed,
            strict_would_block=strict_would_block,
            severity_blockers=severity_blockers,
        )

    if severity_blockers:
        return ExploratoryResult(
            allowed=False,
            reason="; ".join(severity_blockers),
            size_multiplier=0.0,
            gates_passed=g_pass, gates_total=g_total,
            gates_failed=failed,
            strict_would_block=strict_would_block,
            severity_blockers=severity_blockers,
        )

    # Approved — reduced-size paper entry
    return ExploratoryResult(
        allowed=True,
        reason=(f"exploratory_paper: {g_pass}/{g_total} gates, "
                f"low risk, no severe anomaly"),
        size_multiplier=max(0.0, min(1.0, float(size_multiplier))),
        gates_passed=g_pass, gates_total=g_total,
        gates_failed=failed,
        strict_would_block=strict_would_block,
        severity_blockers=severity_blockers,
    )
