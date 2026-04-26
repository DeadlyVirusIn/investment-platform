"""V2 promotion-trigger framework — state machine + confidence + streaks.

Phase 3. Pure functions only. Deterministic: same inputs → same outputs.
No DB, no side effects, no I/O, no clock reads, no randomness.

Inputs are explicit:
- `prior_state`            previous snapshot's stored state (str)
- `gates`                  dict of GateResult from v2_promotion_gates
- `streaks`                (verdict_streak, readiness_streak) for current snapshot
- `bundle`                 read-only comparison bundle (for verdict / tail values)
- `prior_snapshot`         (optional) immediate prior snapshot dict, used for:
                              * tail_guard_triggered (2-consecutive emergency)
                              * stored verdict/readiness streaks
- `approval_present`       bool — Gate 8 passed

Spec: docs/research/V2_PROMOTION_TRIGGER_DESIGN.md (State Machine §,
      Confidence Score §, Rollback Rules §).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from apps.api.src.research.v2_promotion_gates import (
    GATE1_MIN_B2_FLAT_V2_LONG,
    GATE1_MIN_DIVERGENT_ROWS,
    GATE1_MIN_INPUT_ROWS,
    GATE1_MIN_OOS_DAYS,
    GATE2_MIN_CONFIDENCE,
    GATE2_READINESS_STREAK_REQUIRED,
    GATE2_VERDICT_STREAK_REQUIRED,
    GATE3_MIN_EDGE_BPS,
    GATE4_MAX_P99_DELTA_NEGATIVE_BPS,
    GATE5_REGIME_CONCENTRATION_MAX,
    GateResult,
)


# ---------------------------------------------------------------------------
# Frozen state-machine constants
# ---------------------------------------------------------------------------

NOT_READY = "NOT_READY"
SUSPENDED = "SUSPENDED"
WATCH = "WATCH"
READY_FOR_REVIEW = "READY_FOR_REVIEW"
STRONG_CANDIDATE = "STRONG_CANDIDATE"
APPROVED_FOR_SHADOW_REPLACEMENT = "APPROVED_FOR_SHADOW_REPLACEMENT"

# Phase 9A: SUSPENDED is a parallel "circuit breaker" state, not part of
# the forward progression. State-index ordering excludes it; SUSPENDED
# blocks all evaluation and exits only via explicit operator RESUME.
STATE_ORDER = (
    NOT_READY,
    WATCH,
    READY_FOR_REVIEW,
    STRONG_CANDIDATE,
    APPROVED_FOR_SHADOW_REPLACEMENT,
)

# All valid stored states (includes SUSPENDED). Used by DB CHECK +
# JSON validators.
ALL_STATES = STATE_ORDER + (SUSPENDED,)

# Operator decision label that exits SUSPENDED → returns to a fresh
# evaluation cycle starting at NOT_READY (or whatever the gates yield
# in the next snapshot, no skipping).
RESUME_DECISION_LABEL = "RESUME_FROM_SUSPENDED"

# Tail-risk emergency thresholds (exact per design §Rollback Rules → Tail-risk)
TAIL_EMERGENCY_P99_DELTA_HARD_BPS = -25.0
TAIL_EMERGENCY_GUARD_CONSECUTIVE = 2

# Confidence component weights (sum = 1.00)
CONFIDENCE_WEIGHT_SAMPLE = 0.20
CONFIDENCE_WEIGHT_VERDICT_STREAK = 0.20
CONFIDENCE_WEIGHT_READINESS_STREAK = 0.15
CONFIDENCE_WEIGHT_EDGE = 0.15
CONFIDENCE_WEIGHT_TAIL = 0.10
CONFIDENCE_WEIGHT_REGIME = 0.10
CONFIDENCE_WEIGHT_STABILITY = 0.10

# Edge-component normalization range: linear from 0 at +5 bps → 1 at +20 bps
CONFIDENCE_EDGE_FLOOR_BPS = GATE3_MIN_EDGE_BPS   # 5.0
CONFIDENCE_EDGE_SATURATION_BPS = 20.0

# Regime-concentration component degrades linearly from share=0.5 (=1.0)
# down to share=GATE5_REGIME_CONCENTRATION_MAX (=0.0).
CONFIDENCE_REGIME_CONCENTRATION_FLOOR = 0.5

# Stability tiny-negative tolerance for the 0.5 partial-credit band.
CONFIDENCE_STABILITY_TINY_NEG_BPS = -2.0


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StreakUpdate:
    verdict_streak: int
    readiness_streak: int


@dataclass(frozen=True)
class StateDecision:
    new_state: str
    prior_state: str
    rollback_reason: str | None
    forward: bool         # True if the state index advanced
    backward: bool        # True if the state index regressed
    notes: list[str]      # ordered diagnostics for audit


@dataclass(frozen=True)
class ConfidenceBreakdown:
    sample: float
    verdict_streak: float
    readiness_streak: float
    edge: float
    tail: float
    regime: float
    stability: float
    total: float
    # Phase 9B.2 — list of components whose score is "vacuously high"
    # because their underlying input was insufficient (e.g. trend = STABLE
    # only because last_30 history was too short). Operators should
    # discount the total when basis warnings are present.
    basis_warnings: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp01(x: float) -> float:
    if x is None or not math.isfinite(x):
        return 0.0
    return max(0.0, min(1.0, x))


def _f(x: Any) -> float | None:
    if x is None:
        return None
    if isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _gate(gates: dict[str, GateResult], name: str) -> GateResult | None:
    return gates.get(name)


def _passed(gates: dict[str, GateResult], name: str) -> bool:
    g = _gate(gates, name)
    return bool(g and g.passed)


# ---------------------------------------------------------------------------
# update_streaks
# ---------------------------------------------------------------------------

def update_streaks(
    prior_snapshot: dict | None,
    *,
    current_verdict_label: str | None,
    current_readiness_label: str | None,
    force_reset: bool = False,
) -> StreakUpdate:
    """Increment / reset streaks based on current snapshot's labels.

    Reset is HARD — any non-target label sets the streak to 0. There
    is no soft reset, no leniency window, no decay.

    Phase 9A: `force_reset=True` zeroes both streaks regardless of
    labels. Used when the caller has detected tail-risk emergency or
    SUSPENDED entry — both should invalidate accumulated evidence.
    """
    if force_reset:
        return StreakUpdate(verdict_streak=0, readiness_streak=0)
    prior_v = int((prior_snapshot or {}).get("verdict_streak") or 0)
    prior_r = int((prior_snapshot or {}).get("readiness_streak") or 0)
    # Streaks accumulate only when prior state is NOT SUSPENDED.
    # SUSPENDED snapshots carry streaks=0 by construction (force_reset
    # at SUSPENDED entry); after RESUME, evidence rebuilds from scratch.
    if (prior_snapshot or {}).get("state") == SUSPENDED:
        prior_v = 0
        prior_r = 0
    new_v = prior_v + 1 if current_verdict_label == "V2_BETTER" else 0
    new_r = (
        prior_r + 1
        if current_readiness_label == "STRONG_CANDIDATE"
        else 0
    )
    return StreakUpdate(verdict_streak=new_v, readiness_streak=new_r)


def detect_tail_emergency(
    bundle: dict,
    *,
    prior_snapshot: dict | None,
) -> tuple[bool, str | None]:
    """Public helper exposing the tail-emergency check (Phase 9A).

    Snapshot job calls this BEFORE update_streaks so it can pass
    `force_reset=True` when the emergency fires (which forces SUSPENDED
    in advance_or_rollback). Pure function; no side effects.
    """
    return _tail_emergency_active(bundle, prior_snapshot=prior_snapshot)


# ---------------------------------------------------------------------------
# Confidence components
# ---------------------------------------------------------------------------

def _sample_component(gate1: GateResult | None) -> float:
    if not gate1:
        return 0.0
    d = gate1.details
    pairs = (
        (d.get("n_input_rows", 0), GATE1_MIN_INPUT_ROWS),
        (d.get("n_divergent_rows", 0), GATE1_MIN_DIVERGENT_ROWS),
        (d.get("n_b2_flat_v2_long", 0), GATE1_MIN_B2_FLAT_V2_LONG),
        (d.get("oos_days", 0), GATE1_MIN_OOS_DAYS),
    )
    sub_scores = []
    for actual, threshold in pairs:
        a = float(actual or 0)
        t = float(threshold)
        sub_scores.append(_clamp01(a / (2.0 * t)))
    return min(sub_scores)


def _verdict_streak_component(verdict_streak: int) -> float:
    return _clamp01(verdict_streak / GATE2_VERDICT_STREAK_REQUIRED)


def _readiness_streak_component(readiness_streak: int) -> float:
    return _clamp01(readiness_streak / GATE2_READINESS_STREAK_REQUIRED)


def _edge_component(bundle: dict) -> float:
    metrics = bundle.get("metrics") or {}
    edge = _f(metrics.get("avg_return_diff_1d_bps"))
    if edge is None:
        return 0.0
    span = CONFIDENCE_EDGE_SATURATION_BPS - CONFIDENCE_EDGE_FLOOR_BPS
    if span <= 0:
        return 1.0 if edge >= CONFIDENCE_EDGE_SATURATION_BPS else 0.0
    return _clamp01((edge - CONFIDENCE_EDGE_FLOOR_BPS) / span)


def _tail_component(gate4: GateResult | None, bundle: dict) -> float:
    if not gate4:
        return 0.0
    verdict = bundle.get("verdict") or {}
    if bool(verdict.get("tail_guard_triggered")):
        return 0.0
    if not gate4.passed:
        return 0.0
    tail = bundle.get("tail") or {}
    p99_d = _f(tail.get("tail_delta_p99_bps"))
    if p99_d is None:
        return 1.0
    if p99_d < TAIL_EMERGENCY_P99_DELTA_HARD_BPS:
        return 0.0
    threshold = GATE4_MAX_P99_DELTA_NEGATIVE_BPS  # -10
    if p99_d >= 0.0:
        return 1.0
    if p99_d <= threshold:
        return 0.0
    # Linear: 1.0 at p99_delta=0, 0.0 at threshold (= -10)
    return _clamp01((p99_d - threshold) / (0.0 - threshold))


def _regime_component(gate5: GateResult | None) -> float:
    if not gate5:
        return 0.0
    if not gate5.passed:
        return 0.0
    max_share = gate5.details.get("regime_concentration_max")
    if max_share is None:
        return 1.0
    if max_share <= CONFIDENCE_REGIME_CONCENTRATION_FLOOR:
        return 1.0
    if max_share >= GATE5_REGIME_CONCENTRATION_MAX:
        return 0.0
    span = GATE5_REGIME_CONCENTRATION_MAX - CONFIDENCE_REGIME_CONCENTRATION_FLOOR
    return _clamp01(1.0 - (max_share - CONFIDENCE_REGIME_CONCENTRATION_FLOOR) / span)


def _stability_component(gate6: GateResult | None) -> float:
    if not gate6:
        return 0.0
    d = gate6.details
    fh = _f(d.get("first_half_edge_bps"))
    sh = _f(d.get("second_half_edge_bps"))
    trend = d.get("last_30_trend")
    if fh is None or sh is None:
        return 0.0
    both_positive = fh > 0 and sh > 0
    one_tiny_neg = (
        ((fh > 0 and CONFIDENCE_STABILITY_TINY_NEG_BPS <= sh <= 0)
         or (sh > 0 and CONFIDENCE_STABILITY_TINY_NEG_BPS <= fh <= 0))
    )
    if trend == "DECLINING":
        return 0.25
    if both_positive and trend in ("IMPROVING", "STABLE"):
        return 1.0
    if both_positive and trend == "INSUFFICIENT":
        return 0.5
    if one_tiny_neg:
        return 0.5
    return 0.0


# ---------------------------------------------------------------------------
# compute_promotion_confidence
# ---------------------------------------------------------------------------

def compute_promotion_confidence(
    gates: dict[str, GateResult],
    *,
    streaks: StreakUpdate,
    bundle: dict,
) -> ConfidenceBreakdown:
    """Weighted 7-component score in [0, 1]. Deterministic."""
    sample = _sample_component(_gate(gates, "gate_1_minimum_sample"))
    verdict = _verdict_streak_component(streaks.verdict_streak)
    readiness = _readiness_streak_component(streaks.readiness_streak)
    edge = _edge_component(bundle)
    tail = _tail_component(_gate(gates, "gate_4_tail_risk"), bundle)
    regime = _regime_component(_gate(gates, "gate_5_regime_validation"))
    stability = _stability_component(_gate(gates, "gate_6_stability"))

    # Phase 9B.2 — detect "vacuously high" components
    basis_warnings: list[str] = []
    g6 = _gate(gates, "gate_6_stability")
    if g6 and g6.details.get("last_30_trend") == "INSUFFICIENT":
        basis_warnings.append(
            "stability: last_30 trend INSUFFICIENT (insufficient history)"
        )
    g5 = _gate(gates, "gate_5_regime_validation")
    if g5 and g5.details.get("regime_concentration_max") is None and regime > 0:
        basis_warnings.append(
            "regime: no positive cumulative diff per regime "
            "(concentration check N-A)"
        )
    if streaks.verdict_streak >= GATE2_VERDICT_STREAK_REQUIRED \
       and (bundle.get("verdict") or {}).get("verdict") != "V2_BETTER":
        # Streak met threshold but current snapshot isn't V2_BETTER —
        # this should not happen via update_streaks, but guard anyway.
        basis_warnings.append(
            "verdict_streak: threshold met but current verdict is "
            "not V2_BETTER (data inconsistency)"
        )
    g3 = _gate(gates, "gate_3_edge_quality")
    if g3 and not g3.details.get("impact_weighted_series", []):
        basis_warnings.append(
            "edge_trend: insufficient impact-weighted history "
            "(vacuously stable)"
        )

    total = (
        CONFIDENCE_WEIGHT_SAMPLE * sample
        + CONFIDENCE_WEIGHT_VERDICT_STREAK * verdict
        + CONFIDENCE_WEIGHT_READINESS_STREAK * readiness
        + CONFIDENCE_WEIGHT_EDGE * edge
        + CONFIDENCE_WEIGHT_TAIL * tail
        + CONFIDENCE_WEIGHT_REGIME * regime
        + CONFIDENCE_WEIGHT_STABILITY * stability
    )
    return ConfidenceBreakdown(
        sample=round(sample, 6),
        verdict_streak=round(verdict, 6),
        readiness_streak=round(readiness, 6),
        edge=round(edge, 6),
        tail=round(tail, 6),
        regime=round(regime, 6),
        stability=round(stability, 6),
        total=round(_clamp01(total), 6),
        basis_warnings=tuple(basis_warnings),
    )


# ---------------------------------------------------------------------------
# State-machine helpers
# ---------------------------------------------------------------------------

def _state_index(state: str) -> int:
    try:
        return STATE_ORDER.index(state)
    except ValueError:
        return 0  # treat unknown as NOT_READY


def _edge_gate_fully_failed(gates: dict[str, GateResult]) -> bool:
    """All design-checked Gate-3 sub-conditions failed = entire Gate 3 failed.

    Per design §Rollback STRONG_CANDIDATE→WATCH: 'Edge gate fully fails'.
    """
    return not _passed(gates, "gate_3_edge_quality")


def _gate3_partial_passed(gates: dict[str, GateResult]) -> bool:
    """edge_bps ≥ +5 sub-condition only (referenced by WATCH→READY transition)."""
    g = _gate(gates, "gate_3_edge_quality")
    if not g:
        return False
    edge = g.details.get("edge_bps")
    return edge is not None and edge >= GATE3_MIN_EDGE_BPS


def _tail_emergency_active(
    bundle: dict,
    *,
    prior_snapshot: dict | None,
) -> tuple[bool, str | None]:
    """Tail-risk emergency rollback condition.

    Returns (triggered, reason) per design exactly:
      * tail_delta_p99_bps < -25 (current snapshot), OR
      * tail_guard_triggered for 2 consecutive snapshots
    """
    tail = bundle.get("tail") or {}
    verdict = bundle.get("verdict") or {}
    p99_d = _f(tail.get("tail_delta_p99_bps"))
    current_guard = bool(verdict.get("tail_guard_triggered"))
    prior_guard = bool((prior_snapshot or {}).get("tail_guard_triggered"))

    if p99_d is not None and p99_d < TAIL_EMERGENCY_P99_DELTA_HARD_BPS:
        return True, (
            f"tail_delta_p99_bps {p99_d:.2f} < hard floor "
            f"{TAIL_EMERGENCY_P99_DELTA_HARD_BPS}"
        )
    if current_guard and prior_guard:
        return True, (
            f"tail_guard_triggered for {TAIL_EMERGENCY_GUARD_CONSECUTIVE} "
            f"consecutive snapshots"
        )
    return False, None


# ---------------------------------------------------------------------------
# advance_or_rollback
# ---------------------------------------------------------------------------

def advance_or_rollback(
    *,
    prior_state: str,
    gates: dict[str, GateResult],
    streaks: StreakUpdate,
    confidence: float,
    bundle: dict,
    prior_snapshot: dict | None,
    approval_present: bool,
    resume_present: bool = False,
) -> StateDecision:
    """Single-step state machine. No state skipping on forward transitions.

    Evaluation order (Phase 9A revised):
      1. Tail-risk emergency override forces SUSPENDED (NOT NOT_READY)
         from any state, including APPROVED_FOR_SHADOW_REPLACEMENT.
         SUSPENDED is the ONLY auto-exit from APPROVED.
      2. SUSPENDED + no resume → stay SUSPENDED (block all evaluation).
      3. SUSPENDED + resume → re-evaluate as if from NOT_READY.
      4. Per-state rollback rules (downgrade-only, may skip levels).
      5. Per-state forward rule (single-step only, no skipping).

    Returns StateDecision with new_state, rollback_reason, forward/backward
    flags, and ordered notes for audit.
    """
    notes: list[str] = []
    prior_idx = _state_index(prior_state)

    # 1. Tail emergency → SUSPENDED (Phase 9A: was NOT_READY).
    # Streaks must already be reset to 0 by the caller's update_streaks
    # call when the new_state is SUSPENDED. See SUSPENDED handling below
    # for documentation on this contract.
    emerg, emerg_reason = _tail_emergency_active(
        bundle, prior_snapshot=prior_snapshot,
    )
    if emerg:
        notes.append(f"tail-risk emergency → SUSPENDED: {emerg_reason}")
        return StateDecision(
            new_state=SUSPENDED,
            prior_state=prior_state,
            rollback_reason=f"tail-risk emergency: {emerg_reason}",
            forward=False,
            backward=prior_state != SUSPENDED,
            notes=notes,
        )

    # 2 + 3. SUSPENDED handling
    if prior_state == SUSPENDED:
        if not resume_present:
            return StateDecision(
                new_state=SUSPENDED,
                prior_state=SUSPENDED,
                rollback_reason=None,
                forward=False,
                backward=False,
                notes=["awaiting operator RESUME_FROM_SUSPENDED"],
            )
        notes.append("operator RESUME_FROM_SUSPENDED detected")
        # Operator resumed → re-evaluate as if entering from NOT_READY.
        # Streaks remain reset (caller responsibility on SUSPENDED entry).
        return _evaluate_from_state(
            NOT_READY, gates=gates, streaks=streaks,
            confidence=confidence, bundle=bundle,
            approval_present=False,
            prior_state_label=SUSPENDED,
            extra_notes=notes,
        )

    # APPROVED_FOR_SHADOW_REPLACEMENT only auto-exits via tail emergency.
    # Operator rescission must be expressed by approval_present=False on the
    # following snapshot AND the next state evaluation regresses to
    # STRONG_CANDIDATE if Gates 1–7 still pass, else falls further.
    if prior_state == APPROVED_FOR_SHADOW_REPLACEMENT and approval_present:
        # No emergency, approval intact → stay
        return StateDecision(
            new_state=APPROVED_FOR_SHADOW_REPLACEMENT,
            prior_state=prior_state,
            rollback_reason=None,
            forward=False,
            backward=False,
            notes=["approval intact; staying APPROVED"],
        )
    if prior_state == APPROVED_FOR_SHADOW_REPLACEMENT and not approval_present:
        # Operator rescinded → fall back per remaining gate health
        notes.append("operator rescission detected")
        # Determine target by re-evaluating from STRONG_CANDIDATE downwards
        return _evaluate_from_state(
            STRONG_CANDIDATE, gates=gates, streaks=streaks,
            confidence=confidence, bundle=bundle,
            approval_present=False, prior_state=prior_state,
            extra_notes=notes,
        )

    # 2 + 3. From-state evaluation
    return _evaluate_from_state(
        prior_state, gates=gates, streaks=streaks,
        confidence=confidence, bundle=bundle,
        approval_present=approval_present,
        prior_state_label=prior_state,
        extra_notes=notes,
    )


def _evaluate_from_state(
    eval_state: str,
    *,
    gates: dict[str, GateResult],
    streaks: StreakUpdate,
    confidence: float,
    bundle: dict,
    approval_present: bool,
    prior_state: str | None = None,
    prior_state_label: str | None = None,
    extra_notes: list[str] | None = None,
) -> StateDecision:
    """Apply rollback / forward rules treating `eval_state` as the basis.

    `prior_state_label` is what we report as prior_state (for audit). When
    called from APPROVED-rescission path, prior_state_label is APPROVED but
    eval_state is STRONG_CANDIDATE.
    """
    notes = list(extra_notes or [])
    label = prior_state_label or eval_state
    label_idx = _state_index(label)
    verdict = (bundle.get("verdict") or {}).get("verdict")

    g1_pass = _passed(gates, "gate_1_minimum_sample")
    g3_pass = _passed(gates, "gate_3_edge_quality")
    g4_pass = _passed(gates, "gate_4_tail_risk")
    g5_pass = _passed(gates, "gate_5_regime_validation")
    g6_pass = _passed(gates, "gate_6_stability")
    g7_pass = _passed(gates, "gate_7_governance")
    gates_1_to_7 = (
        g1_pass and _passed(gates, "gate_2_verdict_stability")
        and g3_pass and g4_pass and g5_pass and g6_pass and g7_pass
    )
    streaks_intact = (
        streaks.verdict_streak >= GATE2_VERDICT_STREAK_REQUIRED
        and streaks.readiness_streak >= GATE2_READINESS_STREAK_REQUIRED
    )
    confidence_ok = confidence >= GATE2_MIN_CONFIDENCE
    edge_partial = _gate3_partial_passed(gates)

    def _result(new_state: str, reason: str | None) -> StateDecision:
        new_idx = _state_index(new_state)
        return StateDecision(
            new_state=new_state,
            prior_state=label,
            rollback_reason=reason,
            forward=new_idx > label_idx,
            backward=new_idx < label_idx,
            notes=notes,
        )

    # --- Per-state rollback then forward ---

    if eval_state == STRONG_CANDIDATE:
        # Rollback STRONG_CANDIDATE → NOT_READY (Gate 1 or Gate 7 hard fail)
        if not g1_pass or not g7_pass:
            reason = (
                "Gate 1 sample fail" if not g1_pass else "Gate 7 governance fail"
            )
            notes.append(f"rollback: {reason}")
            return _result(NOT_READY, reason)
        # Rollback STRONG_CANDIDATE → WATCH
        if _edge_gate_fully_failed(gates) and verdict != "V2_BETTER":
            reason = "edge gate fully failed AND verdict != V2_BETTER"
            notes.append(f"rollback: {reason}")
            return _result(WATCH, reason)
        # Rollback STRONG_CANDIDATE → READY_FOR_REVIEW
        rfr_reasons: list[str] = []
        if streaks.verdict_streak < GATE2_VERDICT_STREAK_REQUIRED:
            rfr_reasons.append(
                f"verdict_streak {streaks.verdict_streak} < "
                f"{GATE2_VERDICT_STREAK_REQUIRED}"
            )
        if streaks.readiness_streak < GATE2_READINESS_STREAK_REQUIRED:
            rfr_reasons.append(
                f"readiness_streak {streaks.readiness_streak} < "
                f"{GATE2_READINESS_STREAK_REQUIRED}"
            )
        if not confidence_ok:
            rfr_reasons.append(f"confidence {confidence:.3f} < {GATE2_MIN_CONFIDENCE}")
        for n, p in (("3", g3_pass), ("4", g4_pass), ("5", g5_pass), ("6", g6_pass)):
            if not p:
                rfr_reasons.append(f"Gate {n} fail")
        if rfr_reasons:
            reason = "; ".join(rfr_reasons)
            notes.append(f"rollback: {reason}")
            return _result(READY_FOR_REVIEW, reason)
        # Forward STRONG_CANDIDATE → APPROVED
        if approval_present:
            notes.append("forward: operator approval present")
            return _result(APPROVED_FOR_SHADOW_REPLACEMENT, None)
        # Stay
        return _result(STRONG_CANDIDATE, None)

    if eval_state == READY_FOR_REVIEW:
        if not g1_pass or not g7_pass:
            reason = (
                "Gate 1 sample fail" if not g1_pass else "Gate 7 governance fail"
            )
            notes.append(f"rollback: {reason}")
            return _result(NOT_READY, reason)
        if verdict != "V2_BETTER" or not edge_partial:
            sub = []
            if verdict != "V2_BETTER":
                sub.append(f"verdict={verdict!r}")
            if not edge_partial:
                sub.append(f"edge_bps < {GATE3_MIN_EDGE_BPS}")
            reason = "; ".join(sub)
            notes.append(f"rollback: {reason}")
            return _result(WATCH, reason)
        # Forward to STRONG_CANDIDATE if all conditions met
        if gates_1_to_7 and streaks_intact and confidence_ok:
            notes.append("forward: gates 1–7 pass, streaks intact, confidence ≥ 0.70")
            return _result(STRONG_CANDIDATE, None)
        return _result(READY_FOR_REVIEW, None)

    if eval_state == WATCH:
        if not g1_pass or not g7_pass:
            reason = (
                "Gate 1 sample fail" if not g1_pass else "Gate 7 governance fail"
            )
            notes.append(f"rollback: {reason}")
            return _result(NOT_READY, reason)
        if verdict == "V2_BETTER" and edge_partial:
            notes.append("forward: V2_BETTER and edge ≥ +5 bps")
            return _result(READY_FOR_REVIEW, None)
        return _result(WATCH, None)

    if eval_state == NOT_READY:
        if g1_pass:
            notes.append("forward: Gate 1 passes")
            return _result(WATCH, None)
        return _result(NOT_READY, None)

    # Unknown state — treat as NOT_READY
    notes.append(f"unknown prior_state={eval_state!r}; defaulting to NOT_READY")
    return _result(NOT_READY, "unknown prior state")
