"""Engine B → B2 promotion gate + kill switch.

Pure functions. NEVER mutates ENGINE_B_MODE. NEVER changes execution.
Reads observed shadow rows + thresholds; outputs HOLD / ADVANCE / REVERT
recommendation that operator must apply manually.

Architecture: state machine
  LEGACY → SHADOW_COMPARE → PARTIAL_B2_25 → PARTIAL_B2_50 →
  PARTIAL_B2_75 → FULL_B2

Direction:
  ADVANCE = move ONE step forward (LEGACY → SHADOW_COMPARE etc.)
  REVERT  = move ONE step back  (kill-switch trigger or operator review)
  HOLD    = stay put

Auto-promotion is FORBIDDEN. Output is advisory only.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Sequence


PERIODS_PER_YEAR = 252


# State-machine ordering. Index = step.
STATE_ORDER = (
    "LEGACY",
    "SHADOW_COMPARE",
    "PARTIAL_B2_25",
    "PARTIAL_B2_50",
    "PARTIAL_B2_75",
    "FULL_B2",
)


def _next(state: str) -> str | None:
    try:
        i = STATE_ORDER.index(state)
    except ValueError:
        return None
    return STATE_ORDER[i + 1] if i + 1 < len(STATE_ORDER) else None


def _prev(state: str) -> str | None:
    try:
        i = STATE_ORDER.index(state)
    except ValueError:
        return None
    return STATE_ORDER[i - 1] if i > 0 else None


def _sharpe(rets: Sequence[float]) -> float:
    a = [float(r) for r in rets if r is not None and math.isfinite(float(r))]
    if len(a) < 2:
        return float("nan")
    mu = sum(a) / len(a)
    try:
        sd = statistics.stdev(a)
    except statistics.StatisticsError:
        return float("nan")
    if sd == 0 or not math.isfinite(sd):
        return float("nan")
    return (mu / sd) * math.sqrt(PERIODS_PER_YEAR)


def _max_dd_pct(rets: Sequence[float]) -> float:
    a = [float(r) for r in rets if r is not None and math.isfinite(float(r))]
    if not a:
        return 0.0
    eq = peak = 1.0; worst = 0.0
    for r in a:
        eq *= 1 + r
        peak = max(peak, eq)
        worst = min(worst, (eq - peak) / peak)
    return worst * 100.0


@dataclass
class GateResult:
    name: str
    passed: bool
    actual: float | int | None
    threshold: float | int | None
    note: str = ""

    def to_dict(self) -> dict:
        def _f(v):
            if isinstance(v, float):
                return None if not math.isfinite(v) else round(v, 4)
            return v
        return {"name": self.name, "passed": bool(self.passed),
                "actual": _f(self.actual), "threshold": _f(self.threshold),
                "note": self.note}


@dataclass
class KillSwitch:
    triggered: bool
    reason: str
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"triggered": bool(self.triggered),
                "reason": self.reason,
                "metrics": dict(self.metrics)}


@dataclass
class PromotionVerdict:
    current_state: str
    recommended_state: str
    action: str                  # HOLD | ADVANCE | REVERT
    gates: list[GateResult] = field(default_factory=list)
    kill_switch: KillSwitch | None = None
    n_observations: int = 0
    note: str = ""
    advisory_only: bool = True

    def to_dict(self) -> dict:
        return {
            "current_state": self.current_state,
            "recommended_state": self.recommended_state,
            "action": self.action,
            "gates": [g.to_dict() for g in self.gates],
            "kill_switch": (self.kill_switch.to_dict()
                              if self.kill_switch else None),
            "n_observations": int(self.n_observations),
            "note": self.note,
            "advisory_only": True,
            "auto_promote": False,
        }


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------

def evaluate_kill_switch(
    *,
    routed_returns: Sequence[float],
    sharpe_floor: float = -1.0,
    dd_floor_pct: float = -15.0,
    short_window: int = 30,
    dd_window: int = 60,
) -> KillSwitch:
    """Return KillSwitch verdict using rolling 30d Sharpe + 60d DD on
    the routed-signal realized returns."""
    rets = [float(r) for r in routed_returns
            if r is not None and math.isfinite(float(r))]
    if len(rets) < short_window:
        return KillSwitch(False, "insufficient observations",
                              metrics={"n": len(rets)})
    sw = rets[-short_window:]
    sh_30 = _sharpe(sw)
    dd_60 = _max_dd_pct(rets[-max(dd_window, short_window):])
    metrics = {"sharpe_30d": (None if not math.isfinite(sh_30) else round(sh_30, 4)),
               "max_dd_60d_pct": round(dd_60, 4)}
    if math.isfinite(sh_30) and sh_30 <= sharpe_floor:
        return KillSwitch(True,
                              f"30d Sharpe={sh_30:.2f} ≤ floor {sharpe_floor}",
                              metrics=metrics)
    if dd_60 <= dd_floor_pct:
        return KillSwitch(True,
                              f"60d max-DD={dd_60:.2f}% ≤ floor "
                              f"{dd_floor_pct}%",
                              metrics=metrics)
    return KillSwitch(False, "within bounds", metrics=metrics)


# ---------------------------------------------------------------------------
# Advance gates
# ---------------------------------------------------------------------------

def evaluate_advance_gates(
    *,
    n_observations: int,
    b_returns: Sequence[float],
    b2_returns: Sequence[float],
    routed_returns: Sequence[float],
    divergence_outcomes: Sequence[float],
    min_shadow_days: int = 60,
    min_sharpe_improvement: float = 0.10,
    max_dd_increase_pct: float = 0.20,   # 20% buffer over B's max-DD
    operator_approval: bool = False,
) -> list[GateResult]:
    """Compute per-gate pass/fail. ALL gates must pass for ADVANCE."""
    gates: list[GateResult] = []

    # G1: minimum duration of shadow data
    gates.append(GateResult(
        name="min_shadow_days",
        passed=n_observations >= min_shadow_days,
        actual=n_observations, threshold=min_shadow_days,
    ))

    # G2: B2 Sharpe ≥ B Sharpe + improvement
    s_b = _sharpe(b_returns)
    s_b2 = _sharpe(b2_returns)
    delta = (s_b2 - s_b) if (math.isfinite(s_b) and math.isfinite(s_b2)) \
        else float("-inf")
    gates.append(GateResult(
        name="sharpe_improvement",
        passed=delta >= min_sharpe_improvement,
        actual=(None if not math.isfinite(delta) else round(delta, 4)),
        threshold=min_sharpe_improvement,
        note=f"Sharpe B={round(s_b,3) if math.isfinite(s_b) else None} "
              f"vs B2={round(s_b2,3) if math.isfinite(s_b2) else None}",
    ))

    # G3: B2 max-DD must not be materially worse than B
    dd_b = _max_dd_pct(b_returns)
    dd_b2 = _max_dd_pct(b2_returns)
    # Both negative; "worse" = more negative.
    # Allowed: dd_b2 ≥ dd_b * (1 + buffer)  [since dd_b is negative,
    # multiplying by 1.2 makes the threshold MORE negative].
    threshold_dd = dd_b * (1.0 + max_dd_increase_pct) if dd_b < 0 \
        else dd_b - 5.0
    gates.append(GateResult(
        name="dd_constraint",
        passed=dd_b2 >= threshold_dd,
        actual=round(dd_b2, 4), threshold=round(threshold_dd, 4),
        note=f"B2 DD must be ≥ B DD × {1+max_dd_increase_pct} "
              f"(B DD={round(dd_b,2)}%)",
    ))

    # G4: divergence quality — when B and B2 disagreed, B2 won (mean ≥ 0)
    div_arr = [float(d) for d in divergence_outcomes
               if d is not None and math.isfinite(float(d))]
    if div_arr:
        # divergence_outcome stored: positive when B beats B2; we want
        # NEGATIVE mean (B2 wins on divergent days). Flip sign for
        # readability: "advantage to B2".
        adv_b2 = -sum(div_arr) / len(div_arr)
        gates.append(GateResult(
            name="divergence_quality",
            passed=adv_b2 >= 0.0,
            actual=round(adv_b2 * 1e4, 2),       # bps
            threshold=0.0,
            note=f"mean B2-advantage on {len(div_arr)} divergent days; "
                  f"positive = B2 better",
        ))
    else:
        gates.append(GateResult(
            name="divergence_quality",
            passed=False, actual=0, threshold=0,
            note="no divergent days observed yet",
        ))

    # G5: routed-signal Sharpe must not be worse than B
    s_routed = _sharpe(routed_returns)
    routed_delta = (s_routed - s_b) if (math.isfinite(s_routed)
                                              and math.isfinite(s_b)) \
        else float("-inf")
    gates.append(GateResult(
        name="routed_not_worse_than_b",
        passed=routed_delta >= -0.05,   # tiny slippage tolerance
        actual=(None if not math.isfinite(routed_delta)
                  else round(routed_delta, 4)),
        threshold=-0.05,
        note=f"routed Sharpe={round(s_routed,3) if math.isfinite(s_routed) else None}",
    ))

    # G6: operator approval (always required, never auto)
    gates.append(GateResult(
        name="operator_approval",
        passed=bool(operator_approval),
        actual=bool(operator_approval), threshold=True,
        note="ENGINE_B_OPERATOR_APPROVAL flag — never automatic",
    ))

    return gates


# ---------------------------------------------------------------------------
# Top-level evaluator
# ---------------------------------------------------------------------------

def evaluate(
    *,
    current_state: str,
    n_observations: int,
    b_returns: Sequence[float],
    b2_returns: Sequence[float],
    routed_returns: Sequence[float],
    divergence_outcomes: Sequence[float],
    min_shadow_days: int = 60,
    sharpe_floor: float = -1.0,
    dd_floor_pct: float = -15.0,
    operator_approval: bool = False,
) -> PromotionVerdict:
    """Compute promotion verdict.

    Logic:
      1. Kill switch first. If triggered → REVERT to previous state.
      2. Otherwise, evaluate ADVANCE gates. If all pass → ADVANCE.
      3. Otherwise → HOLD.
    """
    # Kill switch
    kill = evaluate_kill_switch(
        routed_returns=routed_returns,
        sharpe_floor=sharpe_floor,
        dd_floor_pct=dd_floor_pct,
    )
    if kill.triggered:
        prev = _prev(current_state)
        if prev is None:
            return PromotionVerdict(
                current_state=current_state,
                recommended_state=current_state,
                action="HOLD",
                gates=[], kill_switch=kill,
                n_observations=n_observations,
                note=f"Kill switch fired but {current_state} has no "
                      f"earlier state; held in place. Operator review "
                      f"required.",
            )
        return PromotionVerdict(
            current_state=current_state,
            recommended_state=prev,
            action="REVERT",
            gates=[], kill_switch=kill,
            n_observations=n_observations,
            note=f"Kill switch fired: {kill.reason}. "
                  f"Recommend revert to {prev}. Operator must approve.",
        )

    # Advance gates
    gates = evaluate_advance_gates(
        n_observations=n_observations,
        b_returns=b_returns, b2_returns=b2_returns,
        routed_returns=routed_returns,
        divergence_outcomes=divergence_outcomes,
        min_shadow_days=min_shadow_days,
        operator_approval=operator_approval,
    )
    failed = [g.name for g in gates if not g.passed]
    nxt = _next(current_state)

    if not failed and nxt is not None:
        return PromotionVerdict(
            current_state=current_state,
            recommended_state=nxt,
            action="ADVANCE",
            gates=gates, kill_switch=kill,
            n_observations=n_observations,
            note=f"All gates passed; recommend ADVANCE to {nxt}. "
                  f"Operator must approve.",
        )

    if not failed and nxt is None:
        return PromotionVerdict(
            current_state=current_state,
            recommended_state=current_state,
            action="HOLD",
            gates=gates, kill_switch=kill,
            n_observations=n_observations,
            note="At terminal state FULL_B2; no further advance. "
                  "Continue monitoring.",
        )

    return PromotionVerdict(
        current_state=current_state,
        recommended_state=current_state,
        action="HOLD",
        gates=gates, kill_switch=kill,
        n_observations=n_observations,
        note=(f"{len(failed)} gate(s) failing: " + ", ".join(failed)
                + ". Continue accumulation."),
    )
