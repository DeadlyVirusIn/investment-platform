"""Engine B → B2 promotion decision framework.

Unified evaluator for ALL state transitions in the migration state
machine:

    LEGACY ──▶ SHADOW_COMPARE ──▶ PARTIAL_B2_25 ──▶ PARTIAL_B2_50 ──▶
    PARTIAL_B2_75 ──▶ FULL_B2

Composes:
  - 9 hard gates (state-specific thresholds)
  - 3-window stability check (used for partial→partial transitions)
  - 0-100 confidence score
  - Recommendation: NOT_READY | READY_FOR_REVIEW | STRONG_CANDIDATE
  - Action     : HOLD | ADVANCE / READY_FOR_NEXT | REVERT

Pure functions. NEVER mutates anything. NEVER triggers execution.
Operator approval is always the FINAL gate.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field

from apps.api.src.research.engine_b_analytics import (
    PERIODS_PER_YEAR, _engine_ret, _finite, _quantile, _sharpe,
    compute_all,
)
from apps.api.src.research.engine_b_pause import (
    PauseState, evaluate_pause,
)


# ---------------------------------------------------------------------------
# State-specific gate thresholds
# ---------------------------------------------------------------------------

# All values are conservative defaults. Operator may override via API.
# Each state-from has its own minimum sample/duration requirements
# because partial→partial steps need less burn-in than the LEGACY entry.

DEFAULT_THRESHOLDS_BY_FROM = {
    "LEGACY": dict(
        min_shadow_days=60,
        min_divergence_events=50,
        sharpe_edge_min=0.10,
        combined_sharpe_min=0.0,         # ≥ 0 vs implicit baseline
        dd_ratio_max=1.20,               # b2_dd ≤ 1.20 × b_dd
        p95_not_worse=True,              # b2_p95 ≥ b_p95 (less negative)
        divergence_win_rate_min=0.55,
        mean_edge_min_bps=10.0,
        stress_exposure_max=0.05,
        require_window_stability=False,
    ),
    "SHADOW_COMPARE": dict(
        min_shadow_days=60,
        min_divergence_events=50,
        sharpe_edge_min=0.10,
        combined_sharpe_min=0.0,
        dd_ratio_max=1.20,
        p95_not_worse=True,
        divergence_win_rate_min=0.55,
        mean_edge_min_bps=10.0,
        stress_exposure_max=0.05,
        require_window_stability=False,
    ),
    "PARTIAL_B2_25": dict(
        min_shadow_days=30,
        min_divergence_events=20,        # smaller divergent sample OK
        sharpe_edge_min=0.0,             # rolling Sharpe ≥ 0 instead
        combined_sharpe_min=0.0,
        dd_ratio_max=1.10,               # tighter — 110% of baseline
        p95_not_worse=True,
        divergence_win_rate_min=0.55,
        mean_edge_min_bps=10.0,
        stress_exposure_max=0.05,
        require_window_stability=True,   # 3-window check ON
    ),
    "PARTIAL_B2_50": dict(
        min_shadow_days=30,
        min_divergence_events=20,
        sharpe_edge_min=0.0,
        combined_sharpe_min=0.0,
        dd_ratio_max=1.10,
        p95_not_worse=True,
        divergence_win_rate_min=0.55,
        mean_edge_min_bps=10.0,
        stress_exposure_max=0.05,
        require_window_stability=True,
    ),
    "PARTIAL_B2_75": dict(
        min_shadow_days=30,
        min_divergence_events=20,
        sharpe_edge_min=0.0,
        combined_sharpe_min=0.0,
        dd_ratio_max=1.10,
        p95_not_worse=True,
        divergence_win_rate_min=0.55,
        mean_edge_min_bps=10.0,
        stress_exposure_max=0.05,
        require_window_stability=True,
    ),
}


STATE_ORDER = (
    "LEGACY", "SHADOW_COMPARE",
    "PARTIAL_B2_25", "PARTIAL_B2_50", "PARTIAL_B2_75",
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


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Gate:
    name: str
    passed: bool
    actual: float | int | bool | None
    threshold: float | int | bool | None
    note: str = ""

    def to_dict(self) -> dict:
        def _f(v):
            if isinstance(v, float):
                return None if not math.isfinite(v) else round(v, 6)
            return v
        return {"name": self.name, "passed": bool(self.passed),
                "actual": _f(self.actual), "threshold": _f(self.threshold),
                "note": self.note}


@dataclass
class StabilityWindowResult:
    window_days: int
    n: int
    sharpe: float | None
    cumulative_pct: float | None
    mean_edge_bps: float | None
    pass_threshold: bool

    def to_dict(self) -> dict:
        return {
            "window_days": int(self.window_days),
            "n": int(self.n),
            "sharpe": (None if self.sharpe is None
                          else round(self.sharpe, 4)),
            "cumulative_pct": (None if self.cumulative_pct is None
                                  else round(self.cumulative_pct, 4)),
            "mean_edge_bps": (None if self.mean_edge_bps is None
                                  else round(self.mean_edge_bps, 2)),
            "pass_threshold": bool(self.pass_threshold),
        }


@dataclass
class DecisionResult:
    current_state: str
    recommended_state: str
    action: str                  # HOLD | READY_FOR_NEXT | REVERT
    label: str                   # NOT_READY | READY_FOR_REVIEW | STRONG_CANDIDATE | *_PAUSED
    score: int                   # 0..100
    score_breakdown: dict
    gates: list[Gate]
    failed_gates: list[str]
    stability_windows: list[StabilityWindowResult]
    kill_switch_triggered: bool
    kill_switch_reason: str
    operator_approval: bool
    note: str
    n_observations: int
    edge_trajectory: dict = field(default_factory=dict)
    promotion_pause: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "current_state": self.current_state,
            "recommended_state": self.recommended_state,
            "action": self.action,
            "label": self.label,
            "score": int(self.score),
            "score_breakdown": dict(self.score_breakdown),
            "gates": [g.to_dict() for g in self.gates],
            "failed_gates": list(self.failed_gates),
            "stability_windows":
                [w.to_dict() for w in self.stability_windows],
            "kill_switch": {
                "triggered": bool(self.kill_switch_triggered),
                "reason": self.kill_switch_reason,
            },
            "operator_approval": bool(self.operator_approval),
            "edge_trajectory": dict(self.edge_trajectory),
            "promotion_pause": dict(self.promotion_pause),
            "note": self.note,
            "n_observations": int(self.n_observations),
            "advisory_only": True,
            "auto_promote": False,
        }


# ---------------------------------------------------------------------------
# 3-window stability split
# ---------------------------------------------------------------------------

def _three_window_stability(
    rows: list[dict],
    *,
    last_n_days: int = 30,
    min_per_window_sharpe: float = 0.0,
    min_per_window_edge_bps: float = 0.0,
) -> list[StabilityWindowResult]:
    """Split last `last_n_days` decision-rows into 3 equal windows.

    Each window must show non-negative Sharpe + non-negative mean B2 edge
    to "pass". This is conservative: we want partial→partial transitions
    only when no recent window collapses.
    """
    eligible = [r for r in rows
                if r.get("fwd_return_1d") is not None
                and r.get("b2_signal") in ("LONG", "FLAT")
                and r.get("engine_b_signal") in ("LONG", "FLAT")]
    sub = eligible[-last_n_days:]
    if len(sub) < 9:
        return []
    chunk = max(1, len(sub) // 3)
    out: list[StabilityWindowResult] = []
    for i in range(3):
        start = i * chunk
        end = (i + 1) * chunk if i < 2 else len(sub)
        rs = sub[start:end]
        b_rets = _finite([_engine_ret(r, "engine_b") for r in rs])
        b2_rets = _finite([_engine_ret(r, "b2") for r in rs])
        if not b2_rets:
            out.append(StabilityWindowResult(
                window_days=len(rs), n=0, sharpe=None,
                cumulative_pct=None, mean_edge_bps=None,
                pass_threshold=False))
            continue
        sh = _sharpe(b2_rets)
        eq = 1.0
        for x in b2_rets:
            eq *= (1 + x)
        edge = [b - a for a, b in zip(b_rets, b2_rets)]
        edge_mean = (sum(edge) / len(edge)) * 1e4 if edge else None
        passes = (math.isfinite(sh) and sh >= min_per_window_sharpe and
                    edge_mean is not None and edge_mean >= min_per_window_edge_bps)
        out.append(StabilityWindowResult(
            window_days=len(rs), n=len(b2_rets),
            sharpe=(round(sh, 4) if math.isfinite(sh) else None),
            cumulative_pct=round((eq - 1) * 100, 4),
            mean_edge_bps=(round(edge_mean, 2) if edge_mean is not None
                            else None),
            pass_threshold=passes,
        ))
    return out


# ---------------------------------------------------------------------------
# Hard-gate evaluation
# ---------------------------------------------------------------------------

def _evaluate_gates(
    rows: list[dict],
    analytics: dict,
    th: dict,
) -> list[Gate]:
    """Compute the 9 hard gates against analytics + thresholds."""
    gates: list[Gate] = []

    n_obs = len(rows)
    div = analytics.get("divergence", {})
    tail = analytics.get("tail_risk", {})
    regime = analytics.get("regime_consistency", {})

    b_rets = _finite([_engine_ret(r, "engine_b") for r in rows])
    b2_rets = _finite([_engine_ret(r, "b2") for r in rows])
    routed_rets = _finite([(_engine_ret(r, "b2")
                              if r.get("routed_signal") == "LONG"
                              and r.get("b2_signal") == "LONG"
                              else _engine_ret(r, "engine_b"))
                             for r in rows])

    s_b = _sharpe(b_rets)
    s_b2 = _sharpe(b2_rets)
    s_combined = _sharpe(routed_rets)

    # G1: min_shadow_days
    gates.append(Gate(
        name="min_shadow_days",
        passed=n_obs >= th["min_shadow_days"],
        actual=n_obs, threshold=th["min_shadow_days"],
    ))

    # G2: min_divergence_events
    n_div = int(div.get("n_divergent_days") or 0)
    gates.append(Gate(
        name="min_divergence_events",
        passed=n_div >= th["min_divergence_events"],
        actual=n_div, threshold=th["min_divergence_events"],
    ))

    # G3: sharpe_b2 >= sharpe_b + edge
    edge = ((s_b2 - s_b) if (math.isfinite(s_b) and math.isfinite(s_b2))
              else float("-inf"))
    gates.append(Gate(
        name="sharpe_edge",
        passed=edge >= th["sharpe_edge_min"],
        actual=(None if not math.isfinite(edge) else round(edge, 4)),
        threshold=th["sharpe_edge_min"],
        note=f"Sharpe B={round(s_b,3) if math.isfinite(s_b) else None} "
              f"vs B2={round(s_b2,3) if math.isfinite(s_b2) else None}",
    ))

    # G4: combined_sharpe >= baseline (0.0 default)
    gates.append(Gate(
        name="combined_sharpe_min",
        passed=(math.isfinite(s_combined)
                  and s_combined >= th["combined_sharpe_min"]),
        actual=(None if not math.isfinite(s_combined)
                  else round(s_combined, 4)),
        threshold=th["combined_sharpe_min"],
    ))

    # G5: dd_b2 ≤ dd_b × dd_ratio_max (both negative)
    eb = tail.get("engine_b") or {}
    eb2 = tail.get("engine_b2") or {}

    def _equity_dd(arr):
        if not arr: return 0.0
        eq = 1.0; peak = 1.0; worst = 0.0
        for x in arr:
            eq *= 1 + x
            peak = max(peak, eq)
            worst = min(worst, (eq - peak) / peak)
        return worst * 100.0
    dd_b = _equity_dd(b_rets)
    dd_b2 = _equity_dd(b2_rets)
    # Both negative; "B2 better" = closer to 0. Threshold:
    #   require dd_b2 >= dd_b × dd_ratio_max
    # If dd_b is 0 (no DD yet), allow up to a tiny absolute floor.
    if dd_b == 0:
        gate_pass = dd_b2 >= -1.0       # very small absolute fallback
        thr_value = -1.0
    else:
        thr_value = dd_b * th["dd_ratio_max"]
        gate_pass = dd_b2 >= thr_value
    gates.append(Gate(
        name="dd_ratio",
        passed=bool(gate_pass),
        actual=round(dd_b2, 4), threshold=round(thr_value, 4),
        note=f"B DD={round(dd_b,2)}%; allowed ratio {th['dd_ratio_max']}",
    ))

    # G6: p95_loss_b2 ≤ p95_loss_b
    p95_b  = eb.get("p95_loss_pct")
    p95_b2 = eb2.get("p95_loss_pct")
    if p95_b is None or p95_b2 is None:
        gates.append(Gate(
            name="p95_not_worse",
            passed=False,
            actual=p95_b2, threshold=p95_b,
            note="insufficient data for p95",
        ))
    else:
        gates.append(Gate(
            name="p95_not_worse",
            passed=p95_b2 >= p95_b,    # less negative = better
            actual=p95_b2, threshold=p95_b,
            note="B2 p95 must be ≥ (less negative than) B p95",
        ))

    # G7: divergence_win_rate
    wr_pct = div.get("win_rate_b2_vs_b_pct")
    wr = (wr_pct / 100.0) if wr_pct is not None else None
    gates.append(Gate(
        name="divergence_win_rate",
        passed=(wr is not None and wr >= th["divergence_win_rate_min"]),
        actual=(None if wr is None else round(wr, 4)),
        threshold=th["divergence_win_rate_min"],
    ))

    # G8: mean_edge_bps
    mean_edge = div.get("avg_return_diff_bps")
    gates.append(Gate(
        name="mean_edge_bps",
        passed=(mean_edge is not None
                  and mean_edge >= th["mean_edge_min_bps"]),
        actual=mean_edge,
        threshold=th["mean_edge_min_bps"],
    ))

    # G9: stress_exposure
    stress_long_pct = regime.get("stress_b2_long_pct")
    stress_long = (stress_long_pct / 100.0) if stress_long_pct is not None \
        else None
    gates.append(Gate(
        name="stress_exposure",
        passed=(stress_long is not None
                  and stress_long <= th["stress_exposure_max"]),
        actual=(None if stress_long is None else round(stress_long, 4)),
        threshold=th["stress_exposure_max"],
        note="B2 must be ~0% LONG during stress regime",
    ))

    return gates


# ---------------------------------------------------------------------------
# Confidence score
# ---------------------------------------------------------------------------

def _confidence_score(
    gates: list[Gate],
    analytics: dict,
    stability_windows: list[StabilityWindowResult],
) -> tuple[int, dict]:
    """0-100 score across 6 dimensions."""
    breakdown: dict[str, str] = {}
    score = 0

    # 1. Divergence quality (20 pts)
    div = analytics.get("divergence", {})
    wr = div.get("win_rate_b2_vs_b_pct")
    cum = div.get("cumulative_return_diff_pct")
    pts = 0
    if wr is not None:
        if wr >= 60: pts += 12
        elif wr >= 55: pts += 9
        elif wr >= 50: pts += 5
    if cum is not None:
        if cum >= 5: pts += 8
        elif cum >= 0: pts += 4
    score += pts
    breakdown["divergence_quality"] = (
        f"+{pts}/20 (win={wr}%, cum={cum}%)")

    # 2. Tail risk improvement (20 pts)
    tail = analytics.get("tail_risk", {})
    p99imp = tail.get("p99_improvement_pct")
    pts = 0
    if p99imp is not None:
        if p99imp >= 0.5:   pts += 20
        elif p99imp >= 0.1: pts += 14
        elif p99imp >= 0:   pts += 8
    score += pts
    breakdown["tail_risk_improvement"] = (
        f"+{pts}/20 (p99 imp={p99imp}%)")

    # 3. Rolling stability (15 pts)
    stab = analytics.get("stability", {})
    drift = stab.get("sharpe_drift")
    e_b2 = (stab.get("early") or {}).get("b2_sharpe")
    r_b2 = (stab.get("recent") or {}).get("b2_sharpe")
    pts = 0
    if e_b2 is not None and r_b2 is not None:
        if min(e_b2, r_b2) >= 0.5: pts += 8
        elif min(e_b2, r_b2) >= 0: pts += 5
    if drift is not None and drift >= 0: pts += 7
    elif drift is not None and drift > -0.3: pts += 3
    score += pts
    breakdown["rolling_stability"] = (
        f"+{pts}/15 (drift={drift}, e={e_b2}, r={r_b2})")

    # 4. Regime alignment (15 pts)
    regime = analytics.get("regime_consistency", {})
    s_long = regime.get("stress_b2_long_pct")
    nperf = (regime.get("nonstress_perf") or {})
    n_sh = nperf.get("sharpe")
    pts = 0
    if s_long is not None and s_long <= 5: pts += 8
    elif s_long is not None and s_long <= 10: pts += 5
    if n_sh is not None and n_sh >= 1.0: pts += 7
    elif n_sh is not None and n_sh >= 0.5: pts += 5
    elif n_sh is not None and n_sh >= 0: pts += 2
    score += pts
    breakdown["regime_alignment"] = (
        f"+{pts}/15 (stress%={s_long}, nonstress_sh={n_sh})")

    # 5. Edge consistency (15 pts) — 3-window check
    pts = 0
    if stability_windows:
        n_pass = sum(1 for w in stability_windows if w.pass_threshold)
        if n_pass == 3: pts += 15
        elif n_pass == 2: pts += 9
        elif n_pass == 1: pts += 4
    else:
        pts = 0
    score += pts
    breakdown["edge_consistency"] = (
        f"+{pts}/15 (windows pass={sum(1 for w in stability_windows if w.pass_threshold)}/{len(stability_windows)})"
    )

    # 6. Sample size (15 pts)
    n_obs = analytics.get("n_rows", 0)
    n_div = (analytics.get("divergence") or {}).get("n_divergent_days") or 0
    pts = 0
    if n_obs >= 120: pts += 8
    elif n_obs >= 60: pts += 5
    if n_div >= 60: pts += 7
    elif n_div >= 30: pts += 4
    score += pts
    breakdown["sample_size"] = f"+{pts}/15 (n_obs={n_obs}, n_div={n_div})"

    return min(100, int(score)), breakdown


def _label_for_score(score: int) -> str:
    if score >= 75:
        return "STRONG_CANDIDATE"
    if score >= 50:
        return "READY_FOR_REVIEW"
    return "NOT_READY"


# ---------------------------------------------------------------------------
# Kill switch (recent-window collapse)
# ---------------------------------------------------------------------------

def _kill_switch(
    rows: list[dict],
    *,
    sharpe_floor_30d: float = 0.0,
    dd_floor_60d_pct: float = -15.0,
    div_win_floor_30d: float = 0.40,
) -> tuple[bool, str]:
    """Return (triggered, reason). Computed on routed_signal returns."""
    routed = []
    for r in rows:
        sig = r.get("routed_signal")
        ret = r.get("fwd_return_1d")
        if ret is None or sig not in ("LONG", "FLAT"):
            continue
        routed.append(float(ret) if sig == "LONG" else 0.0)
    if len(routed) < 30:
        return False, "insufficient routed observations"
    sw = routed[-30:]
    sh_30 = _sharpe(sw)
    if math.isfinite(sh_30) and sh_30 < sharpe_floor_30d:
        return True, f"30d routed Sharpe={sh_30:.2f} < floor {sharpe_floor_30d}"
    eq = peak = 1.0; worst = 0.0
    for x in routed[-60:]:
        eq *= 1 + x; peak = max(peak, eq)
        worst = min(worst, (eq - peak) / peak)
    dd_60 = worst * 100.0
    if dd_60 <= dd_floor_60d_pct:
        return True, (f"60d routed DD={dd_60:.2f}% ≤ floor "
                        f"{dd_floor_60d_pct}%")
    # Divergence-win recent collapse
    div = [r for r in rows[-30:]
           if r.get("divergence_flag") and
           r.get("divergence_outcome") is not None]
    if len(div) >= 5:
        wins = sum(1 for r in div
                   if -float(r["divergence_outcome"]) > 0)
        rate = wins / len(div)
        if rate < div_win_floor_30d:
            return True, (f"30d divergence-win rate {rate:.2f} < "
                            f"floor {div_win_floor_30d}")
    return False, "within bounds"


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

def evaluate(
    *,
    rows: list[dict],
    current_state: str,
    operator_approval: bool = False,
    thresholds: dict | None = None,
    require_score_for_promotion: int = 80,
    previous_pause_states: list[bool] | None = None,
) -> DecisionResult:
    """End-to-end evaluation. Pure function.

    `previous_pause_states` (chronological, most-recent-LAST) is used by
    the pause module to enforce the "2 consecutive healthy snapshots"
    clear condition. Defaults to None → no clear-history enforcement.
    """
    th_default = DEFAULT_THRESHOLDS_BY_FROM.get(current_state) or \
        DEFAULT_THRESHOLDS_BY_FROM["LEGACY"]
    th = {**th_default, **(thresholds or {})}

    # Kill switch first
    kill, reason = _kill_switch(rows)
    if kill:
        from apps.api.src.research.engine_b_analytics import (
            edge_trajectory,
        )
        prev = _prev(current_state) or current_state
        # Even on REVERT we still compute pause for visibility
        pause_kill = evaluate_pause(
            rows, previous_pause_states=previous_pause_states or [])
        return DecisionResult(
            current_state=current_state,
            recommended_state=prev,
            action="REVERT",
            label="NOT_READY",
            score=0, score_breakdown={},
            gates=[], failed_gates=[],
            stability_windows=[],
            kill_switch_triggered=True,
            kill_switch_reason=reason,
            operator_approval=bool(operator_approval),
            note=(f"Kill switch fired: {reason}. Recommend revert "
                    f"to {prev}. Operator must approve."),
            n_observations=len(rows),
            edge_trajectory=edge_trajectory(rows),
            promotion_pause=pause_kill.to_dict(),
        )

    analytics = compute_all(rows)
    gates = _evaluate_gates(rows, analytics, th)

    # 3-window stability if required for this transition
    stab_windows: list[StabilityWindowResult] = []
    if th.get("require_window_stability"):
        stab_windows = _three_window_stability(rows)

    failed = [g.name for g in gates if not g.passed]
    if th.get("require_window_stability"):
        if not stab_windows or not all(w.pass_threshold
                                            for w in stab_windows):
            failed.append("three_window_stability")

    # Confidence score
    score, breakdown = _confidence_score(gates, analytics, stab_windows)
    label = _label_for_score(score)

    # Pause evaluation (governance protection on top of gate logic)
    pause = evaluate_pause(
        rows,
        previous_pause_states=previous_pause_states or [],
        edge_blocks={
            "30d": analytics.get("edge_trajectory") or {},
            "60d": _edge_for_window(rows, 60),
            "90d": _edge_for_window(rows, 90),
        },
    )

    # Decision logic
    nxt = _next(current_state)
    if (not failed and operator_approval and score >= require_score_for_promotion
        and nxt is not None):
        action = "READY_FOR_NEXT"
        recommended = nxt
        note = (f"All gates pass · score={score}/100 ({label}) · "
                  f"operator approved · ready to ADVANCE to {nxt}.")
    elif not failed and nxt is not None and score >= require_score_for_promotion:
        action = "HOLD"
        recommended = current_state
        note = (f"All gates pass · score={score}/100 ({label}) · "
                  f"awaiting operator approval before ADVANCE to {nxt}.")
    elif not failed and nxt is None:
        action = "HOLD"
        recommended = current_state
        note = "Terminal state FULL_B2; continue monitoring."
    else:
        action = "HOLD"
        recommended = current_state
        note = (f"{len(failed)} gate(s) failing: " + ", ".join(failed[:5])
                  + ". Continue accumulation.")

    # Pause override: BLOCKING pause forces HOLD, prevents ADVANCE
    if pause.active and pause.severity == "BLOCKING":
        action = "HOLD"
        recommended = current_state
        if pause.label_override:
            label = pause.label_override
        note = (f"Promotion paused (BLOCKING): {pause.reason} "
                  f"Even if all gates pass, ADVANCE is blocked.")
    elif pause.active and pause.severity == "WARNING":
        # Warn but keep HOLD; never let action become READY_FOR_NEXT
        if action == "READY_FOR_NEXT":
            action = "HOLD"
            recommended = current_state
        if pause.label_override:
            label = pause.label_override
        note = (f"Promotion paused (WARNING): {pause.reason} {note}")

    return DecisionResult(
        current_state=current_state,
        recommended_state=recommended,
        action=action,
        label=label, score=score, score_breakdown=breakdown,
        gates=gates, failed_gates=failed,
        stability_windows=stab_windows,
        kill_switch_triggered=False,
        kill_switch_reason="within bounds",
        operator_approval=bool(operator_approval),
        note=note,
        n_observations=len(rows),
        edge_trajectory=analytics.get("edge_trajectory", {}),
        promotion_pause=pause.to_dict(),
    )


def _edge_for_window(rows: list[dict], w: int) -> dict:
    from apps.api.src.research.engine_b_analytics import edge_trajectory
    return edge_trajectory(rows, window_days=w)
