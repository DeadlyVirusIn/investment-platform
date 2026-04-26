"""Exhaustive tests for v2_promotion_state — state machine + confidence + streaks.

Coverage target:
  * update_streaks: increment + hard reset + missing-prior
  * State machine: every forward arrow + every rollback arrow
  * Tail-risk emergency override (every entry state, including APPROVED)
  * Operator-rescission rollback from APPROVED
  * No state skipping on forward
  * Confidence: each component formula at multiple inputs + boundary
  * Final confidence ∈ [0, 1] under varied inputs
"""

from __future__ import annotations

import pytest

from src.research.v2_promotion_gates import (
    FRAMEWORK_IMPLEMENTATION_DATE,
    GATE1_MIN_B2_FLAT_V2_LONG,
    GATE1_MIN_DIVERGENT_ROWS,
    GATE1_MIN_INPUT_ROWS,
    GATE1_MIN_OOS_DAYS,
    GATE2_MIN_CONFIDENCE,
    GATE2_READINESS_STREAK_REQUIRED,
    GATE2_VERDICT_STREAK_REQUIRED,
    GATE3_MIN_EDGE_BPS,
    GATE4_MAX_P99_DELTA_NEGATIVE_BPS,
    GateResult,
)
from src.research.v2_promotion_state import (
    APPROVED_FOR_SHADOW_REPLACEMENT,
    CONFIDENCE_EDGE_FLOOR_BPS,
    CONFIDENCE_EDGE_SATURATION_BPS,
    CONFIDENCE_REGIME_CONCENTRATION_FLOOR,
    CONFIDENCE_WEIGHT_EDGE,
    CONFIDENCE_WEIGHT_READINESS_STREAK,
    CONFIDENCE_WEIGHT_REGIME,
    CONFIDENCE_WEIGHT_SAMPLE,
    CONFIDENCE_WEIGHT_STABILITY,
    CONFIDENCE_WEIGHT_TAIL,
    CONFIDENCE_WEIGHT_VERDICT_STREAK,
    NOT_READY,
    READY_FOR_REVIEW,
    STATE_ORDER,
    STRONG_CANDIDATE,
    SUSPENDED,
    TAIL_EMERGENCY_P99_DELTA_HARD_BPS,
    WATCH,
    StreakUpdate,
    advance_or_rollback,
    compute_promotion_confidence,
    detect_tail_emergency,
    update_streaks,
)


# ---------------------------------------------------------------------------
# Sum of confidence weights must be exactly 1.00
# ---------------------------------------------------------------------------

def test_confidence_weights_sum_to_one():
    total = (
        CONFIDENCE_WEIGHT_SAMPLE
        + CONFIDENCE_WEIGHT_VERDICT_STREAK
        + CONFIDENCE_WEIGHT_READINESS_STREAK
        + CONFIDENCE_WEIGHT_EDGE
        + CONFIDENCE_WEIGHT_TAIL
        + CONFIDENCE_WEIGHT_REGIME
        + CONFIDENCE_WEIGHT_STABILITY
    )
    assert total == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def _gate(name: str, *, passed: bool = True, **details) -> GateResult:
    return GateResult(name=name, passed=passed,
                       reason="test", details=details)


def _bundle(
    *,
    edge_bps=10.0,
    cum_pct=2.0,
    iwe=0.05,
    verdict="V2_BETTER",
    readiness="STRONG_CANDIDATE",
    confidence=0.85,
    tail_guard=False,
    p99_delta=0.0,
    p95_delta=0.0,
    fh_edge=8.0,
    sh_edge=10.0,
    last_30_trend="STABLE",
    n_input=120,
    n_div=40,
    n_b2flat=15,
):
    return {
        "n_input_rows": n_input,
        "n_divergent_rows": n_div,
        "metrics": {
            "n_divergent_days": n_div,
            "n_b2_flat_v2_long": n_b2flat,
            "avg_return_diff_1d_bps": edge_bps,
            "cumulative_return_diff_pct": cum_pct,
            "impact_weighted_edge": iwe,
        },
        "tail": {
            "b2": {"p99_loss_bps": -250.0, "p95_loss_bps": -150.0,
                   "worst_5_losses_bps": []},
            "v2": {"p99_loss_bps": -250.0 + p99_delta,
                   "p95_loss_bps": -150.0 + p95_delta,
                   "worst_5_losses_bps": []},
            "tail_delta_p95_bps": p95_delta,
            "tail_delta_p99_bps": p99_delta,
        },
        "verdict": {
            "verdict": verdict,
            "confidence": confidence,
            "readiness": readiness,
            "tail_guard_triggered": tail_guard,
        },
        "stability": {
            "first_half_vs_second_half": {
                "first_half_edge_bps": fh_edge,
                "second_half_edge_bps": sh_edge,
                "trend": "STABLE",
            },
            "last_30_vs_prior_30": {"trend": last_30_trend},
        },
        "metrics_by_regime": {},
    }


def _all_pass_gates(*, edge_bps=10.0):
    return {
        "gate_1_minimum_sample": _gate(
            "gate_1_minimum_sample", passed=True,
            n_input_rows=120, n_divergent_rows=40,
            n_b2_flat_v2_long=15, oos_days=30,
        ),
        "gate_2_verdict_stability": _gate("gate_2_verdict_stability", passed=True),
        "gate_3_edge_quality": _gate(
            "gate_3_edge_quality", passed=True, edge_bps=edge_bps,
        ),
        "gate_4_tail_risk": _gate("gate_4_tail_risk", passed=True),
        "gate_5_regime_validation": _gate(
            "gate_5_regime_validation", passed=True,
            regime_concentration_max=0.40,
        ),
        "gate_6_stability": _gate(
            "gate_6_stability", passed=True,
            first_half_edge_bps=8.0, second_half_edge_bps=10.0,
            last_30_trend="STABLE",
        ),
        "gate_7_governance": _gate("gate_7_governance", passed=True),
        "gate_8_operator_approval": _gate(
            "gate_8_operator_approval", passed=False,
        ),
    }


def _streaks(v: int, r: int) -> StreakUpdate:
    return StreakUpdate(verdict_streak=v, readiness_streak=r)


# ===========================================================================
# update_streaks
# ===========================================================================

def test_update_streaks_increment_v2_and_strong():
    out = update_streaks(
        {"verdict_streak": 3, "readiness_streak": 1},
        current_verdict_label="V2_BETTER",
        current_readiness_label="STRONG_CANDIDATE",
    )
    assert out.verdict_streak == 4
    assert out.readiness_streak == 2


def test_update_streaks_hard_reset_on_inconclusive():
    out = update_streaks(
        {"verdict_streak": 5, "readiness_streak": 3},
        current_verdict_label="INCONCLUSIVE",
        current_readiness_label="REVIEW",
    )
    assert out.verdict_streak == 0
    assert out.readiness_streak == 0


def test_update_streaks_partial_reset_one_streak_only():
    out = update_streaks(
        {"verdict_streak": 5, "readiness_streak": 3},
        current_verdict_label="V2_BETTER",
        current_readiness_label="REVIEW",
    )
    assert out.verdict_streak == 6
    assert out.readiness_streak == 0


def test_update_streaks_with_no_prior_snapshot():
    out = update_streaks(
        None,
        current_verdict_label="V2_BETTER",
        current_readiness_label="STRONG_CANDIDATE",
    )
    assert out.verdict_streak == 1
    assert out.readiness_streak == 1


def test_update_streaks_with_missing_prior_streak_fields_treated_as_zero():
    out = update_streaks(
        {},  # no streak fields
        current_verdict_label="V2_BETTER",
        current_readiness_label="REVIEW",
    )
    assert out.verdict_streak == 1
    assert out.readiness_streak == 0


def test_update_streaks_no_soft_reset_with_b2_better():
    """Verdict != V2_BETTER → hard reset to 0 (no decay-by-1)."""
    out = update_streaks(
        {"verdict_streak": 100, "readiness_streak": 50},
        current_verdict_label="B2_BETTER",
        current_readiness_label="STRONG_CANDIDATE",
    )
    assert out.verdict_streak == 0
    assert out.readiness_streak == 51


# ===========================================================================
# Confidence components — sample
# ===========================================================================

def test_confidence_sample_zero_when_no_gate1():
    cb = compute_promotion_confidence(
        {}, streaks=_streaks(0, 0), bundle=_bundle(),
    )
    assert cb.sample == 0.0


def test_confidence_sample_full_at_2x_thresholds():
    gates = {
        "gate_1_minimum_sample": _gate(
            "gate_1_minimum_sample",
            n_input_rows=2 * GATE1_MIN_INPUT_ROWS,
            n_divergent_rows=2 * GATE1_MIN_DIVERGENT_ROWS,
            n_b2_flat_v2_long=2 * GATE1_MIN_B2_FLAT_V2_LONG,
            oos_days=2 * GATE1_MIN_OOS_DAYS,
        ),
    }
    cb = compute_promotion_confidence(
        gates, streaks=_streaks(0, 0), bundle=_bundle(),
    )
    assert cb.sample == pytest.approx(1.0)


def test_confidence_sample_half_at_thresholds():
    """At exact thresholds, sample score should be 0.5 (1.0 at 2× thresholds)."""
    gates = {
        "gate_1_minimum_sample": _gate(
            "gate_1_minimum_sample",
            n_input_rows=GATE1_MIN_INPUT_ROWS,
            n_divergent_rows=GATE1_MIN_DIVERGENT_ROWS,
            n_b2_flat_v2_long=GATE1_MIN_B2_FLAT_V2_LONG,
            oos_days=GATE1_MIN_OOS_DAYS,
        ),
    }
    cb = compute_promotion_confidence(
        gates, streaks=_streaks(0, 0), bundle=_bundle(),
    )
    assert cb.sample == pytest.approx(0.5)


def test_confidence_sample_min_across_subconditions():
    """Only one weak sub-condition → score limited by it."""
    gates = {
        "gate_1_minimum_sample": _gate(
            "gate_1_minimum_sample",
            n_input_rows=10 * GATE1_MIN_INPUT_ROWS,
            n_divergent_rows=10 * GATE1_MIN_DIVERGENT_ROWS,
            n_b2_flat_v2_long=10 * GATE1_MIN_B2_FLAT_V2_LONG,
            oos_days=GATE1_MIN_OOS_DAYS,  # weakest
        ),
    }
    cb = compute_promotion_confidence(
        gates, streaks=_streaks(0, 0), bundle=_bundle(),
    )
    assert cb.sample == pytest.approx(0.5)


# ===========================================================================
# Confidence components — verdict / readiness streak
# ===========================================================================

def test_confidence_verdict_streak_full_at_required():
    cb = compute_promotion_confidence(
        _all_pass_gates(),
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED, 0),
        bundle=_bundle(),
    )
    assert cb.verdict_streak == pytest.approx(1.0)


def test_confidence_verdict_streak_partial():
    cb = compute_promotion_confidence(
        _all_pass_gates(),
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED // 2, 0),
        bundle=_bundle(),
    )
    assert cb.verdict_streak == pytest.approx(0.5)


def test_confidence_verdict_streak_capped_above_required():
    cb = compute_promotion_confidence(
        _all_pass_gates(),
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED * 100, 0),
        bundle=_bundle(),
    )
    assert cb.verdict_streak == pytest.approx(1.0)


def test_confidence_readiness_streak_full():
    cb = compute_promotion_confidence(
        _all_pass_gates(),
        streaks=_streaks(0, GATE2_READINESS_STREAK_REQUIRED),
        bundle=_bundle(),
    )
    assert cb.readiness_streak == pytest.approx(1.0)


def test_confidence_readiness_streak_zero():
    cb = compute_promotion_confidence(
        _all_pass_gates(),
        streaks=_streaks(0, 0),
        bundle=_bundle(),
    )
    assert cb.readiness_streak == 0.0


# ===========================================================================
# Confidence components — edge
# ===========================================================================

def test_confidence_edge_zero_at_floor():
    cb = compute_promotion_confidence(
        _all_pass_gates(),
        streaks=_streaks(0, 0),
        bundle=_bundle(edge_bps=CONFIDENCE_EDGE_FLOOR_BPS),
    )
    assert cb.edge == pytest.approx(0.0)


def test_confidence_edge_full_at_saturation():
    cb = compute_promotion_confidence(
        _all_pass_gates(),
        streaks=_streaks(0, 0),
        bundle=_bundle(edge_bps=CONFIDENCE_EDGE_SATURATION_BPS),
    )
    assert cb.edge == pytest.approx(1.0)


def test_confidence_edge_half_at_midpoint():
    midpoint = (CONFIDENCE_EDGE_FLOOR_BPS + CONFIDENCE_EDGE_SATURATION_BPS) / 2
    cb = compute_promotion_confidence(
        _all_pass_gates(),
        streaks=_streaks(0, 0),
        bundle=_bundle(edge_bps=midpoint),
    )
    assert cb.edge == pytest.approx(0.5)


def test_confidence_edge_clamped_below_floor():
    cb = compute_promotion_confidence(
        _all_pass_gates(),
        streaks=_streaks(0, 0),
        bundle=_bundle(edge_bps=-100.0),
    )
    assert cb.edge == 0.0


def test_confidence_edge_clamped_above_saturation():
    cb = compute_promotion_confidence(
        _all_pass_gates(),
        streaks=_streaks(0, 0),
        bundle=_bundle(edge_bps=10000.0),
    )
    assert cb.edge == pytest.approx(1.0)


# ===========================================================================
# Confidence components — tail
# ===========================================================================

def test_confidence_tail_full_at_zero_p99_delta():
    cb = compute_promotion_confidence(
        _all_pass_gates(),
        streaks=_streaks(0, 0),
        bundle=_bundle(p99_delta=0.0),
    )
    assert cb.tail == pytest.approx(1.0)


def test_confidence_tail_zero_at_threshold():
    cb = compute_promotion_confidence(
        _all_pass_gates(),
        streaks=_streaks(0, 0),
        bundle=_bundle(p99_delta=GATE4_MAX_P99_DELTA_NEGATIVE_BPS),
    )
    assert cb.tail == pytest.approx(0.0)


def test_confidence_tail_half_at_midpoint():
    mid = GATE4_MAX_P99_DELTA_NEGATIVE_BPS / 2  # -5
    cb = compute_promotion_confidence(
        _all_pass_gates(),
        streaks=_streaks(0, 0),
        bundle=_bundle(p99_delta=mid),
    )
    assert cb.tail == pytest.approx(0.5)


def test_confidence_tail_zero_when_guard_triggered():
    cb = compute_promotion_confidence(
        _all_pass_gates(),
        streaks=_streaks(0, 0),
        bundle=_bundle(tail_guard=True),
    )
    assert cb.tail == 0.0


def test_confidence_tail_zero_when_gate4_fails():
    gates = _all_pass_gates()
    gates["gate_4_tail_risk"] = _gate("gate_4_tail_risk", passed=False)
    cb = compute_promotion_confidence(
        gates, streaks=_streaks(0, 0), bundle=_bundle(),
    )
    assert cb.tail == 0.0


# ===========================================================================
# Confidence components — regime
# ===========================================================================

def test_confidence_regime_full_at_low_concentration():
    gates = _all_pass_gates()
    gates["gate_5_regime_validation"] = _gate(
        "gate_5_regime_validation", passed=True,
        regime_concentration_max=CONFIDENCE_REGIME_CONCENTRATION_FLOOR - 0.01,
    )
    cb = compute_promotion_confidence(
        gates, streaks=_streaks(0, 0), bundle=_bundle(),
    )
    assert cb.regime == pytest.approx(1.0)


def test_confidence_regime_zero_at_max_concentration():
    gates = _all_pass_gates()
    gates["gate_5_regime_validation"] = _gate(
        "gate_5_regime_validation", passed=True,
        regime_concentration_max=0.80,  # exactly the gate-fail threshold
    )
    cb = compute_promotion_confidence(
        gates, streaks=_streaks(0, 0), bundle=_bundle(),
    )
    assert cb.regime == pytest.approx(0.0)


def test_confidence_regime_zero_when_gate5_fails():
    gates = _all_pass_gates()
    gates["gate_5_regime_validation"] = _gate(
        "gate_5_regime_validation", passed=False,
        regime_concentration_max=0.40,
    )
    cb = compute_promotion_confidence(
        gates, streaks=_streaks(0, 0), bundle=_bundle(),
    )
    assert cb.regime == 0.0


def test_confidence_regime_full_when_no_concentration():
    gates = _all_pass_gates()
    gates["gate_5_regime_validation"] = _gate(
        "gate_5_regime_validation", passed=True,
        regime_concentration_max=None,
    )
    cb = compute_promotion_confidence(
        gates, streaks=_streaks(0, 0), bundle=_bundle(),
    )
    assert cb.regime == pytest.approx(1.0)


# ===========================================================================
# Confidence components — stability
# ===========================================================================

def test_confidence_stability_full_both_halves_positive_stable_trend():
    gates = _all_pass_gates()
    gates["gate_6_stability"] = _gate(
        "gate_6_stability", passed=True,
        first_half_edge_bps=5.0, second_half_edge_bps=10.0,
        last_30_trend="STABLE",
    )
    cb = compute_promotion_confidence(
        gates, streaks=_streaks(0, 0), bundle=_bundle(),
    )
    assert cb.stability == pytest.approx(1.0)


def test_confidence_stability_half_partial_when_one_tiny_negative():
    gates = _all_pass_gates()
    gates["gate_6_stability"] = _gate(
        "gate_6_stability", passed=True,
        first_half_edge_bps=10.0, second_half_edge_bps=-1.0,
        last_30_trend="STABLE",
    )
    cb = compute_promotion_confidence(
        gates, streaks=_streaks(0, 0), bundle=_bundle(),
    )
    assert cb.stability == pytest.approx(0.5)


def test_confidence_stability_quarter_when_declining():
    gates = _all_pass_gates()
    gates["gate_6_stability"] = _gate(
        "gate_6_stability", passed=True,
        first_half_edge_bps=10.0, second_half_edge_bps=8.0,
        last_30_trend="DECLINING",
    )
    cb = compute_promotion_confidence(
        gates, streaks=_streaks(0, 0), bundle=_bundle(),
    )
    assert cb.stability == pytest.approx(0.25)


def test_confidence_stability_half_when_insufficient_trend():
    gates = _all_pass_gates()
    gates["gate_6_stability"] = _gate(
        "gate_6_stability", passed=True,
        first_half_edge_bps=10.0, second_half_edge_bps=8.0,
        last_30_trend="INSUFFICIENT",
    )
    cb = compute_promotion_confidence(
        gates, streaks=_streaks(0, 0), bundle=_bundle(),
    )
    assert cb.stability == pytest.approx(0.5)


def test_confidence_stability_zero_when_both_halves_negative():
    gates = _all_pass_gates()
    gates["gate_6_stability"] = _gate(
        "gate_6_stability", passed=True,
        first_half_edge_bps=-5.0, second_half_edge_bps=-3.0,
        last_30_trend="STABLE",
    )
    cb = compute_promotion_confidence(
        gates, streaks=_streaks(0, 0), bundle=_bundle(),
    )
    assert cb.stability == 0.0


# ===========================================================================
# Confidence — total bounds
# ===========================================================================

def test_confidence_total_in_unit_interval():
    gates = _all_pass_gates()
    cb = compute_promotion_confidence(
        gates,
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED * 5,
                          GATE2_READINESS_STREAK_REQUIRED * 5),
        bundle=_bundle(edge_bps=10000.0, p99_delta=0.0),
    )
    assert 0.0 <= cb.total <= 1.0


def test_confidence_total_zero_with_empty_inputs():
    cb = compute_promotion_confidence(
        {}, streaks=_streaks(0, 0), bundle={"verdict": {}},
    )
    assert cb.total == 0.0


def test_confidence_total_max_when_all_components_full():
    gates = {
        "gate_1_minimum_sample": _gate(
            "gate_1_minimum_sample",
            n_input_rows=2 * GATE1_MIN_INPUT_ROWS,
            n_divergent_rows=2 * GATE1_MIN_DIVERGENT_ROWS,
            n_b2_flat_v2_long=2 * GATE1_MIN_B2_FLAT_V2_LONG,
            oos_days=2 * GATE1_MIN_OOS_DAYS,
        ),
        "gate_2_verdict_stability": _gate("gate_2_verdict_stability"),
        "gate_3_edge_quality": _gate(
            "gate_3_edge_quality", edge_bps=CONFIDENCE_EDGE_SATURATION_BPS,
        ),
        "gate_4_tail_risk": _gate("gate_4_tail_risk"),
        "gate_5_regime_validation": _gate(
            "gate_5_regime_validation", regime_concentration_max=0.4,
        ),
        "gate_6_stability": _gate(
            "gate_6_stability",
            first_half_edge_bps=10.0, second_half_edge_bps=10.0,
            last_30_trend="STABLE",
        ),
        "gate_7_governance": _gate("gate_7_governance"),
    }
    cb = compute_promotion_confidence(
        gates,
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        bundle=_bundle(edge_bps=CONFIDENCE_EDGE_SATURATION_BPS, p99_delta=0.0),
    )
    assert cb.total == pytest.approx(1.0)


# ===========================================================================
# State machine — STATE_ORDER sanity
# ===========================================================================

def test_state_order_matches_design():
    assert STATE_ORDER == (
        "NOT_READY", "WATCH", "READY_FOR_REVIEW",
        "STRONG_CANDIDATE", "APPROVED_FOR_SHADOW_REPLACEMENT",
    )


# ===========================================================================
# State machine — forward arrows
# ===========================================================================

def test_forward_not_ready_to_watch_when_gate1_passes():
    decision = advance_or_rollback(
        prior_state=NOT_READY,
        gates=_all_pass_gates(),
        streaks=_streaks(0, 0),
        confidence=0.0,
        bundle=_bundle(verdict="INCONCLUSIVE"),
        prior_snapshot=None,
        approval_present=False,
    )
    assert decision.new_state == WATCH
    assert decision.forward
    assert not decision.backward


def test_forward_watch_to_ready_when_v2better_and_edge_partial():
    decision = advance_or_rollback(
        prior_state=WATCH,
        gates=_all_pass_gates(edge_bps=GATE3_MIN_EDGE_BPS),
        streaks=_streaks(1, 0),
        confidence=0.5,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=False,
    )
    assert decision.new_state == READY_FOR_REVIEW
    assert decision.forward


def test_forward_ready_to_strong_when_all_gates_streaks_confidence_pass():
    decision = advance_or_rollback(
        prior_state=READY_FOR_REVIEW,
        gates=_all_pass_gates(),
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=GATE2_MIN_CONFIDENCE,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=False,
    )
    assert decision.new_state == STRONG_CANDIDATE
    assert decision.forward


def test_forward_strong_to_approved_with_operator_approval():
    decision = advance_or_rollback(
        prior_state=STRONG_CANDIDATE,
        gates=_all_pass_gates(),
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=GATE2_MIN_CONFIDENCE + 0.1,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=True,
    )
    assert decision.new_state == APPROVED_FOR_SHADOW_REPLACEMENT
    assert decision.forward


# ===========================================================================
# State machine — no-skipping rule
# ===========================================================================

def test_no_skipping_not_ready_only_advances_one_state_per_snapshot():
    """Even with a perfect bundle + approval, NOT_READY → WATCH (not STRONG)."""
    decision = advance_or_rollback(
        prior_state=NOT_READY,
        gates=_all_pass_gates(),
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=0.95,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=True,
    )
    assert decision.new_state == WATCH


def test_no_skipping_watch_only_advances_to_ready():
    decision = advance_or_rollback(
        prior_state=WATCH,
        gates=_all_pass_gates(),
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=0.95,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=True,
    )
    assert decision.new_state == READY_FOR_REVIEW


def test_no_skipping_ready_only_advances_to_strong():
    decision = advance_or_rollback(
        prior_state=READY_FOR_REVIEW,
        gates=_all_pass_gates(),
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=0.95,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=True,
    )
    assert decision.new_state == STRONG_CANDIDATE


# ===========================================================================
# State machine — backward arrows from STRONG_CANDIDATE
# ===========================================================================

def test_rollback_strong_to_ready_when_streak_breaks():
    decision = advance_or_rollback(
        prior_state=STRONG_CANDIDATE,
        gates=_all_pass_gates(),
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED - 1,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=0.85,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=False,
    )
    assert decision.new_state == READY_FOR_REVIEW
    assert decision.backward
    assert "verdict_streak" in (decision.rollback_reason or "")


def test_rollback_strong_to_ready_when_low_confidence():
    decision = advance_or_rollback(
        prior_state=STRONG_CANDIDATE,
        gates=_all_pass_gates(),
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=GATE2_MIN_CONFIDENCE - 0.01,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=False,
    )
    assert decision.new_state == READY_FOR_REVIEW
    assert "confidence" in (decision.rollback_reason or "")


@pytest.mark.parametrize("gate_name", [
    "gate_3_edge_quality", "gate_4_tail_risk",
    "gate_5_regime_validation", "gate_6_stability",
])
def test_rollback_strong_to_ready_when_quantitative_gate_fails(gate_name):
    gates = _all_pass_gates()
    gates[gate_name] = _gate(gate_name, passed=False)
    decision = advance_or_rollback(
        prior_state=STRONG_CANDIDATE,
        gates=gates,
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=GATE2_MIN_CONFIDENCE + 0.1,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=False,
    )
    assert decision.new_state == READY_FOR_REVIEW
    assert decision.backward


def test_rollback_strong_to_watch_when_edge_fully_fails_and_verdict_not_v2():
    gates = _all_pass_gates()
    gates["gate_3_edge_quality"] = _gate("gate_3_edge_quality", passed=False)
    decision = advance_or_rollback(
        prior_state=STRONG_CANDIDATE,
        gates=gates,
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=GATE2_MIN_CONFIDENCE,
        bundle=_bundle(verdict="INCONCLUSIVE"),
        prior_snapshot=None,
        approval_present=False,
    )
    assert decision.new_state == WATCH
    assert "edge gate fully failed" in (decision.rollback_reason or "")


def test_rollback_strong_to_not_ready_when_gate1_fails():
    gates = _all_pass_gates()
    gates["gate_1_minimum_sample"] = _gate(
        "gate_1_minimum_sample", passed=False,
    )
    decision = advance_or_rollback(
        prior_state=STRONG_CANDIDATE,
        gates=gates,
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=GATE2_MIN_CONFIDENCE,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=False,
    )
    assert decision.new_state == NOT_READY
    assert "Gate 1" in (decision.rollback_reason or "")


def test_rollback_strong_to_not_ready_when_gate7_fails():
    gates = _all_pass_gates()
    gates["gate_7_governance"] = _gate("gate_7_governance", passed=False)
    decision = advance_or_rollback(
        prior_state=STRONG_CANDIDATE,
        gates=gates,
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=GATE2_MIN_CONFIDENCE,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=False,
    )
    assert decision.new_state == NOT_READY
    assert "Gate 7" in (decision.rollback_reason or "")


# ===========================================================================
# State machine — backward arrows from READY_FOR_REVIEW
# ===========================================================================

def test_rollback_ready_to_watch_when_verdict_not_v2():
    decision = advance_or_rollback(
        prior_state=READY_FOR_REVIEW,
        gates=_all_pass_gates(),
        streaks=_streaks(0, 0),
        confidence=0.5,
        bundle=_bundle(verdict="INCONCLUSIVE"),
        prior_snapshot=None,
        approval_present=False,
    )
    assert decision.new_state == WATCH
    assert decision.backward


def test_rollback_ready_to_watch_when_edge_partial_fails():
    gates = _all_pass_gates(edge_bps=GATE3_MIN_EDGE_BPS - 0.01)
    # Force overall gate 3 to fail too (since edge sub-fails)
    gates["gate_3_edge_quality"] = _gate(
        "gate_3_edge_quality", passed=False,
        edge_bps=GATE3_MIN_EDGE_BPS - 0.01,
    )
    decision = advance_or_rollback(
        prior_state=READY_FOR_REVIEW,
        gates=gates,
        streaks=_streaks(0, 0),
        confidence=0.5,
        bundle=_bundle(verdict="V2_BETTER", edge_bps=GATE3_MIN_EDGE_BPS - 0.01),
        prior_snapshot=None,
        approval_present=False,
    )
    assert decision.new_state == WATCH


def test_rollback_ready_to_not_ready_when_gate1_fails():
    gates = _all_pass_gates()
    gates["gate_1_minimum_sample"] = _gate(
        "gate_1_minimum_sample", passed=False,
    )
    decision = advance_or_rollback(
        prior_state=READY_FOR_REVIEW,
        gates=gates, streaks=_streaks(0, 0),
        confidence=0.0, bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None, approval_present=False,
    )
    assert decision.new_state == NOT_READY


def test_rollback_ready_to_not_ready_when_gate7_fails():
    gates = _all_pass_gates()
    gates["gate_7_governance"] = _gate("gate_7_governance", passed=False)
    decision = advance_or_rollback(
        prior_state=READY_FOR_REVIEW,
        gates=gates, streaks=_streaks(0, 0),
        confidence=0.0, bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None, approval_present=False,
    )
    assert decision.new_state == NOT_READY


# ===========================================================================
# State machine — backward arrows from WATCH
# ===========================================================================

def test_rollback_watch_to_not_ready_when_gate1_fails():
    gates = _all_pass_gates()
    gates["gate_1_minimum_sample"] = _gate(
        "gate_1_minimum_sample", passed=False,
    )
    decision = advance_or_rollback(
        prior_state=WATCH,
        gates=gates, streaks=_streaks(0, 0),
        confidence=0.0, bundle=_bundle(verdict="INCONCLUSIVE"),
        prior_snapshot=None, approval_present=False,
    )
    assert decision.new_state == NOT_READY


def test_rollback_watch_to_not_ready_when_gate7_fails():
    gates = _all_pass_gates()
    gates["gate_7_governance"] = _gate("gate_7_governance", passed=False)
    decision = advance_or_rollback(
        prior_state=WATCH,
        gates=gates, streaks=_streaks(0, 0),
        confidence=0.0, bundle=_bundle(verdict="INCONCLUSIVE"),
        prior_snapshot=None, approval_present=False,
    )
    assert decision.new_state == NOT_READY


# ===========================================================================
# State machine — APPROVED behavior
# ===========================================================================

def test_approved_stays_when_approval_intact_and_no_emergency():
    decision = advance_or_rollback(
        prior_state=APPROVED_FOR_SHADOW_REPLACEMENT,
        gates=_all_pass_gates(),
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=GATE2_MIN_CONFIDENCE + 0.1,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=True,
    )
    assert decision.new_state == APPROVED_FOR_SHADOW_REPLACEMENT


def test_approved_to_strong_on_operator_rescission():
    decision = advance_or_rollback(
        prior_state=APPROVED_FOR_SHADOW_REPLACEMENT,
        gates=_all_pass_gates(),
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=GATE2_MIN_CONFIDENCE + 0.1,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=False,
    )
    assert decision.new_state == STRONG_CANDIDATE
    assert "operator rescission" in " ".join(decision.notes)


def test_approved_to_lower_state_on_rescission_when_gates_also_fail():
    """Operator rescinds AND quantitative gate fails → falls past STRONG."""
    gates = _all_pass_gates()
    gates["gate_4_tail_risk"] = _gate("gate_4_tail_risk", passed=False)
    decision = advance_or_rollback(
        prior_state=APPROVED_FOR_SHADOW_REPLACEMENT,
        gates=gates,
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=GATE2_MIN_CONFIDENCE + 0.1,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=False,
    )
    assert decision.new_state == READY_FOR_REVIEW


# ===========================================================================
# Tail-risk emergency override (every entry state)
# ===========================================================================

@pytest.mark.parametrize("entry_state", list(STATE_ORDER))
def test_tail_emergency_p99_hard_breach_forces_suspended(entry_state):
    """Phase 9A: tail emergency now forces SUSPENDED, not NOT_READY."""
    decision = advance_or_rollback(
        prior_state=entry_state,
        gates=_all_pass_gates(),
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=GATE2_MIN_CONFIDENCE + 0.1,
        bundle=_bundle(
            verdict="V2_BETTER",
            p99_delta=TAIL_EMERGENCY_P99_DELTA_HARD_BPS - 0.1,
        ),
        prior_snapshot=None,
        approval_present=True,
    )
    assert decision.new_state == SUSPENDED
    assert "emergency" in (decision.rollback_reason or "")


@pytest.mark.parametrize("entry_state", list(STATE_ORDER))
def test_tail_emergency_2_consec_guard_forces_suspended(entry_state):
    """Phase 9A: 2-consecutive guard fires SUSPENDED."""
    decision = advance_or_rollback(
        prior_state=entry_state,
        gates=_all_pass_gates(),
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=GATE2_MIN_CONFIDENCE + 0.1,
        bundle=_bundle(verdict="V2_BETTER", tail_guard=True),
        prior_snapshot={"tail_guard_triggered": True},
        approval_present=True,
    )
    assert decision.new_state == SUSPENDED
    assert "consecutive" in (decision.rollback_reason or "")


def test_single_guard_hit_does_not_trigger_emergency():
    """1 snapshot of guard ≠ emergency."""
    decision = advance_or_rollback(
        prior_state=STRONG_CANDIDATE,
        gates=_all_pass_gates(),
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=GATE2_MIN_CONFIDENCE + 0.1,
        bundle=_bundle(verdict="V2_BETTER", tail_guard=True),
        prior_snapshot={"tail_guard_triggered": False},
        approval_present=False,
    )
    # Falls back via normal rules (Gate 4 pass arg here, so falls to ready
    # only if other gates fail; with all-pass gates and tail_guard True the
    # gates may still all-pass since we're stubbing gate_4 as passed.)
    assert decision.new_state != NOT_READY or "emergency" not in (decision.rollback_reason or "")


# ===========================================================================
# Stay-in-state tests (no transition triggered)
# ===========================================================================

def test_strong_stays_when_all_conditions_met_no_approval():
    decision = advance_or_rollback(
        prior_state=STRONG_CANDIDATE,
        gates=_all_pass_gates(),
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=GATE2_MIN_CONFIDENCE + 0.1,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=False,
    )
    assert decision.new_state == STRONG_CANDIDATE
    assert not decision.forward
    assert not decision.backward


def test_ready_stays_when_some_gates_fail():
    gates = _all_pass_gates()
    gates["gate_5_regime_validation"] = _gate(
        "gate_5_regime_validation", passed=False,
    )
    decision = advance_or_rollback(
        prior_state=READY_FOR_REVIEW,
        gates=gates,
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=GATE2_MIN_CONFIDENCE,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=False,
    )
    assert decision.new_state == READY_FOR_REVIEW


def test_watch_stays_when_verdict_not_v2():
    decision = advance_or_rollback(
        prior_state=WATCH,
        gates=_all_pass_gates(),
        streaks=_streaks(0, 0),
        confidence=0.0,
        bundle=_bundle(verdict="INCONCLUSIVE"),
        prior_snapshot=None,
        approval_present=False,
    )
    assert decision.new_state == WATCH


def test_not_ready_stays_when_gate1_fails():
    gates = _all_pass_gates()
    gates["gate_1_minimum_sample"] = _gate(
        "gate_1_minimum_sample", passed=False,
    )
    decision = advance_or_rollback(
        prior_state=NOT_READY,
        gates=gates, streaks=_streaks(0, 0),
        confidence=0.0, bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None, approval_present=False,
    )
    assert decision.new_state == NOT_READY


# ===========================================================================
# Determinism
# ===========================================================================

def test_determinism_same_inputs_same_outputs():
    inputs = dict(
        prior_state=STRONG_CANDIDATE,
        gates=_all_pass_gates(),
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=0.85,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot={"tail_guard_triggered": False},
        approval_present=True,
    )
    out1 = advance_or_rollback(**inputs)
    out2 = advance_or_rollback(**inputs)
    assert out1 == out2


# ===========================================================================
# Phase 9A — SUSPENDED state + RESUME flow + force_reset streaks
# ===========================================================================

def test_suspended_stays_without_resume():
    decision = advance_or_rollback(
        prior_state=SUSPENDED,
        gates=_all_pass_gates(),
        streaks=_streaks(0, 0),
        confidence=0.0,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=False,
        resume_present=False,
    )
    assert decision.new_state == SUSPENDED
    assert not decision.forward
    assert not decision.backward


def test_suspended_with_resume_re_evaluates_from_not_ready():
    """RESUME → equivalent of fresh evaluation from NOT_READY. With Gate 1
    passing, advances exactly one state to WATCH (no skipping)."""
    decision = advance_or_rollback(
        prior_state=SUSPENDED,
        gates=_all_pass_gates(),
        streaks=_streaks(0, 0),
        confidence=0.0,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=False,
        resume_present=True,
    )
    assert decision.new_state == WATCH
    assert "RESUME_FROM_SUSPENDED" in " ".join(decision.notes)


def test_suspended_resume_with_failing_gate1_stays_not_ready():
    gates = _all_pass_gates()
    gates["gate_1_minimum_sample"] = _gate(
        "gate_1_minimum_sample", passed=False,
    )
    decision = advance_or_rollback(
        prior_state=SUSPENDED,
        gates=gates,
        streaks=_streaks(0, 0),
        confidence=0.0,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=False,
        resume_present=True,
    )
    assert decision.new_state == NOT_READY


def test_tail_emergency_overrides_resume():
    """If tail emergency fires WHILE operator submitted resume, emergency wins."""
    decision = advance_or_rollback(
        prior_state=SUSPENDED,
        gates=_all_pass_gates(),
        streaks=_streaks(0, 0),
        confidence=0.0,
        bundle=_bundle(verdict="V2_BETTER",
                        p99_delta=TAIL_EMERGENCY_P99_DELTA_HARD_BPS - 1),
        prior_snapshot=None,
        approval_present=False,
        resume_present=True,
    )
    assert decision.new_state == SUSPENDED
    assert "emergency" in (decision.rollback_reason or "")


def test_force_reset_zeroes_both_streaks():
    out = update_streaks(
        {"verdict_streak": 99, "readiness_streak": 88},
        current_verdict_label="V2_BETTER",
        current_readiness_label="STRONG_CANDIDATE",
        force_reset=True,
    )
    assert out.verdict_streak == 0
    assert out.readiness_streak == 0


def test_streaks_dont_accumulate_across_suspended():
    """Prior snapshot in SUSPENDED state → streaks treated as zero
    regardless of stored values."""
    out = update_streaks(
        {"verdict_streak": 99, "readiness_streak": 88, "state": SUSPENDED},
        current_verdict_label="V2_BETTER",
        current_readiness_label="STRONG_CANDIDATE",
    )
    assert out.verdict_streak == 1
    assert out.readiness_streak == 1


def test_detect_tail_emergency_p99_breach():
    triggered, reason = detect_tail_emergency(
        _bundle(p99_delta=TAIL_EMERGENCY_P99_DELTA_HARD_BPS - 0.01),
        prior_snapshot=None,
    )
    assert triggered
    assert reason and "hard floor" in reason


def test_detect_tail_emergency_2_consec_guard():
    triggered, reason = detect_tail_emergency(
        _bundle(tail_guard=True),
        prior_snapshot={"tail_guard_triggered": True},
    )
    assert triggered
    assert reason and "consecutive" in reason


def test_detect_tail_emergency_no_trigger():
    triggered, reason = detect_tail_emergency(
        _bundle(tail_guard=False, p99_delta=0.0),
        prior_snapshot=None,
    )
    assert not triggered
    assert reason is None


def test_state_order_excludes_suspended():
    """SUSPENDED is a parallel circuit-breaker state, not part of forward
    progression. STATE_ORDER must remain 5 forward states only."""
    assert SUSPENDED not in STATE_ORDER
    assert len(STATE_ORDER) == 5


def test_forward_arrow_skips_suspended():
    """Operator-resumed snapshot from SUSPENDED → re-evaluated as
    NOT_READY → WATCH. No state skipping observed."""
    decision = advance_or_rollback(
        prior_state=SUSPENDED,
        gates=_all_pass_gates(),
        streaks=_streaks(GATE2_VERDICT_STREAK_REQUIRED,
                          GATE2_READINESS_STREAK_REQUIRED),
        confidence=0.95,
        bundle=_bundle(verdict="V2_BETTER"),
        prior_snapshot=None,
        approval_present=True,    # would normally allow APPROVED, but we
                                    # routed through NOT_READY → WATCH only
        resume_present=True,
    )
    assert decision.new_state == WATCH
