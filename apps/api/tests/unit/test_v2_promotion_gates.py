"""Exhaustive tests for v2_promotion_gates pure functions.

Coverage target:
  * Each gate: at least one PASS case + one FAIL case per sub-condition
  * Boundary values for every numeric threshold
  * Regime concentration logic (multiple distributions)
  * Worst-5 rank-aligned comparison (multi-rank, mixed loss/no-loss)
  * Tail guard scenarios (handled inside Gate 4)
  * evaluate_all_gates wiring
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

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
    GATE3_IMPACT_WEIGHTED_NOISE_BAND,
    GATE3_MIN_CUM_DIFF_PCT,
    GATE3_MIN_EDGE_BPS,
    GATE4_MAX_P95_DELTA_NEGATIVE_BPS,
    GATE4_MAX_P99_DELTA_NEGATIVE_BPS,
    GATE4_MIN_DIVERGENT_DAYS_FOR_TAIL,
    GATE4_MIN_RETURN_OBSERVATIONS_FOR_P99,
    GATE4_WORST5_DEEPER_FACTOR,
    GATE5_MAX_NEUTRAL_NEG_EDGE_BPS,
    GATE5_MIN_DIRECTIONAL_EDGE_BPS,
    GATE5_REGIME_CONCENTRATION_MAX,
    GATE7_VALID_ENGINE_B_MODES,
    GATE8_APPROVAL_STALENESS_DAYS,
    evaluate_all_gates,
    evaluate_gate_1,
    evaluate_gate_2,
    evaluate_gate_3,
    evaluate_gate_4,
    evaluate_gate_5,
    evaluate_gate_6,
    evaluate_gate_7,
    evaluate_gate_8,
)


SNAPSHOT_DATE_OK = FRAMEWORK_IMPLEMENTATION_DATE + timedelta(days=GATE1_MIN_OOS_DAYS + 5)


# ---------------------------------------------------------------------------
# Bundle / snapshot factories
# ---------------------------------------------------------------------------

def _bundle(
    *,
    n_input=300,    # Phase 9B.1: bumped to satisfy Gate 4 sample guard (>=250)
    n_div=60,       # Phase 9B.1: bumped to satisfy Gate 4 (>=50) + Gate 1 (>=30)
    n_b2flat=15,
    edge_bps=8.0,
    cum_pct=1.0,
    iwe=0.05,
    avg_5d_bps=8.0,
    win_pct=60.0,
    verdict="V2_BETTER",
    confidence=0.80,
    readiness="STRONG_CANDIDATE",
    tail_guard=False,
    p99_delta=0.0,
    p95_delta=0.0,
    b2_w5=None,
    v2_w5=None,
    by_regime=None,
    fh_edge=8.0,
    sh_edge=10.0,
    last_30_trend="STABLE",
):
    if b2_w5 is None:
        b2_w5 = [-200.0, -150.0, -120.0, -90.0, -50.0]
    if v2_w5 is None:
        v2_w5 = list(b2_w5)
    if by_regime is None:
        by_regime = {
            "stress": _regime_metrics(n=10, edge_bps=4.0, cum_pct=0.30),
            "directional": _regime_metrics(n=20, edge_bps=10.0, cum_pct=0.60),
            "neutral": _regime_metrics(n=10, edge_bps=2.0, cum_pct=0.20),
        }
    return {
        "n_input_rows": n_input,
        "n_divergent_rows": n_div,
        "metrics": {
            "n_divergent_days": n_div,
            "n_b2_flat_v2_long": n_b2flat,
            "n_b2_long_v2_flat": max(0, n_div - n_b2flat),
            "win_rate_v2_vs_b2_pct": win_pct,
            "avg_return_diff_1d_bps": edge_bps,
            "avg_return_diff_5d_bps": avg_5d_bps,
            "cumulative_return_diff_pct": cum_pct,
            "avoided_losses_count": 5,
            "avoided_losses_avg_bps": 80.0,
            "new_losses_count": 3,
            "new_losses_avg_bps": 50.0,
            "impact_weighted_edge": iwe,
        },
        "metrics_by_regime": by_regime,
        "tail": {
            "b2": {"n": n_input, "p95_loss_bps": -150.0, "p99_loss_bps": -250.0,
                   "worst_5_losses_bps": b2_w5},
            "v2": {"n": n_input,
                   "p95_loss_bps": -150.0 + p95_delta,
                   "p99_loss_bps": -250.0 + p99_delta,
                   "worst_5_losses_bps": v2_w5},
            "tail_delta_p95_bps": p95_delta,
            "tail_delta_p99_bps": p99_delta,
        },
        "stability": {
            "first_half_vs_second_half": {
                "first_half_edge_bps": fh_edge,
                "second_half_edge_bps": sh_edge,
                "n_first": n_div // 2, "n_second": n_div // 2,
                "trend": "STABLE",
            },
            "last_30_vs_prior_30": {
                "last_30_edge_bps": edge_bps,
                "prior_30_edge_bps": edge_bps,
                "n_last": 30, "n_prior": 30,
                "trend": last_30_trend,
            },
        },
        "verdict": {
            "verdict": verdict,
            "confidence": confidence,
            "tail_guard_triggered": tail_guard,
            "tail_guard_reason": None,
            "readiness": readiness,
            "base_verdict_before_guard": verdict,
            "base_confidence_before_guard": confidence,
        },
        "thresholds": {},
    }


def _regime_metrics(*, n, edge_bps, cum_pct):
    return {
        "n_divergent_days": n,
        "n_b2_flat_v2_long": n,
        "n_b2_long_v2_flat": 0,
        "win_rate_v2_vs_b2_pct": 60.0,
        "avg_return_diff_1d_bps": edge_bps,
        "avg_return_diff_5d_bps": edge_bps,
        "cumulative_return_diff_pct": cum_pct,
        "avoided_losses_count": 0,
        "avoided_losses_avg_bps": None,
        "new_losses_count": 0,
        "new_losses_avg_bps": None,
        "impact_weighted_edge": 0.05,
    }


def _prior_snap(
    *,
    verdict="V2_BETTER",
    readiness="STRONG_CANDIDATE",
    iwe=0.04,
    fetch_ok=True,
):
    return {
        "verdict": {"verdict": verdict, "readiness": readiness},
        "metrics": {"impact_weighted_edge": iwe},
        "comparison_fetch_ok": fetch_ok,
    }


# ===========================================================================
# Gate 1 — Minimum Sample
# ===========================================================================

def test_gate1_pass_above_all_thresholds():
    g = evaluate_gate_1(
        _bundle(n_input=120, n_div=40, n_b2flat=15),
        snapshot_as_of_date=SNAPSHOT_DATE_OK,
    )
    assert g.passed
    assert "all sample-size sub-conditions met" in g.reason


def test_gate1_pass_at_exact_thresholds():
    g = evaluate_gate_1(
        _bundle(
            n_input=GATE1_MIN_INPUT_ROWS,
            n_div=GATE1_MIN_DIVERGENT_ROWS,
            n_b2flat=GATE1_MIN_B2_FLAT_V2_LONG,
        ),
        snapshot_as_of_date=FRAMEWORK_IMPLEMENTATION_DATE
            + timedelta(days=GATE1_MIN_OOS_DAYS),
    )
    assert g.passed


def test_gate1_fail_n_input_below():
    g = evaluate_gate_1(
        _bundle(n_input=GATE1_MIN_INPUT_ROWS - 1),
        snapshot_as_of_date=SNAPSHOT_DATE_OK,
    )
    assert not g.passed
    assert "n_input_rows" in g.reason


def test_gate1_fail_n_div_below():
    g = evaluate_gate_1(
        _bundle(n_div=GATE1_MIN_DIVERGENT_ROWS - 1),
        snapshot_as_of_date=SNAPSHOT_DATE_OK,
    )
    assert not g.passed
    assert "n_divergent_rows" in g.reason


def test_gate1_fail_n_b2flat_below():
    g = evaluate_gate_1(
        _bundle(n_b2flat=GATE1_MIN_B2_FLAT_V2_LONG - 1),
        snapshot_as_of_date=SNAPSHOT_DATE_OK,
    )
    assert not g.passed
    assert "n_b2_flat_v2_long" in g.reason


def test_gate1_fail_oos_days_below():
    g = evaluate_gate_1(
        _bundle(),
        snapshot_as_of_date=FRAMEWORK_IMPLEMENTATION_DATE
            + timedelta(days=GATE1_MIN_OOS_DAYS - 1),
    )
    assert not g.passed
    assert "oos_days" in g.reason


def test_gate1_fail_oos_days_before_implementation():
    """Snapshot date before implementation date → 0 OOS days."""
    g = evaluate_gate_1(
        _bundle(),
        snapshot_as_of_date=FRAMEWORK_IMPLEMENTATION_DATE - timedelta(days=5),
    )
    assert not g.passed
    assert "oos_days" in g.reason
    assert g.details["oos_days"] == 0


def test_gate1_fail_multi_subconditions_reports_all():
    g = evaluate_gate_1(
        _bundle(n_input=10, n_div=5, n_b2flat=2),
        snapshot_as_of_date=FRAMEWORK_IMPLEMENTATION_DATE,
    )
    assert not g.passed
    for needle in ("n_input_rows", "n_divergent_rows",
                   "n_b2_flat_v2_long", "oos_days"):
        assert needle in g.reason


# ===========================================================================
# Gate 2 — Verdict Stability
# ===========================================================================

def _streak_history(n: int, *, verdict="V2_BETTER", readiness="STRONG_CANDIDATE"):
    """Build n-1 prior snapshots; the current bundle adds the last 1."""
    return [
        _prior_snap(verdict=verdict, readiness=readiness)
        for _ in range(max(0, n - 1))
    ]


def test_gate2_pass_with_full_streaks_and_high_confidence():
    priors = _streak_history(GATE2_VERDICT_STREAK_REQUIRED)
    g = evaluate_gate_2(
        _bundle(verdict="V2_BETTER", readiness="STRONG_CANDIDATE",
                confidence=0.85),
        prior_snapshots=priors,
    )
    assert g.passed
    assert g.details["verdict_streak"] == GATE2_VERDICT_STREAK_REQUIRED
    assert g.details["readiness_streak"] >= GATE2_READINESS_STREAK_REQUIRED


def test_gate2_pass_at_exact_confidence_threshold():
    priors = _streak_history(GATE2_VERDICT_STREAK_REQUIRED)
    g = evaluate_gate_2(
        _bundle(confidence=GATE2_MIN_CONFIDENCE),
        prior_snapshots=priors,
    )
    assert g.passed


def test_gate2_fail_short_verdict_streak():
    priors = _streak_history(GATE2_VERDICT_STREAK_REQUIRED - 1)
    g = evaluate_gate_2(
        _bundle(),
        prior_snapshots=priors,
    )
    assert not g.passed
    assert "verdict_streak" in g.reason


def test_gate2_fail_streak_broken_by_inconclusive():
    """Even if last 4 are V2_BETTER, an INCONCLUSIVE in the middle breaks it
    only if it's within the trailing streak window."""
    priors = [
        _prior_snap(verdict="V2_BETTER"),
        _prior_snap(verdict="INCONCLUSIVE"),  # breaks streak
        _prior_snap(verdict="V2_BETTER"),
    ]
    g = evaluate_gate_2(
        _bundle(verdict="V2_BETTER"),
        prior_snapshots=priors,
    )
    # Trailing run from current backwards: V2, V2 (priors[-1]), break at INCONCLUSIVE → 2
    assert g.details["verdict_streak"] == 2
    assert not g.passed


def test_gate2_fail_short_readiness_streak():
    priors = _streak_history(GATE2_VERDICT_STREAK_REQUIRED, readiness="REVIEW")
    g = evaluate_gate_2(
        _bundle(readiness="REVIEW"),
        prior_snapshots=priors,
    )
    assert not g.passed
    assert "readiness_streak" in g.reason


def test_gate2_fail_low_confidence():
    priors = _streak_history(GATE2_VERDICT_STREAK_REQUIRED)
    g = evaluate_gate_2(
        _bundle(confidence=GATE2_MIN_CONFIDENCE - 0.01),
        prior_snapshots=priors,
    )
    assert not g.passed
    assert "confidence" in g.reason


def test_gate2_fail_missing_confidence():
    priors = _streak_history(GATE2_VERDICT_STREAK_REQUIRED)
    b = _bundle()
    b["verdict"]["confidence"] = None
    g = evaluate_gate_2(b, prior_snapshots=priors)
    assert not g.passed


# ===========================================================================
# Gate 3 — Edge Quality
# ===========================================================================

def test_gate3_pass_clean():
    priors = [_prior_snap(iwe=v) for v in (0.02, 0.03, 0.04)]
    g = evaluate_gate_3(
        _bundle(edge_bps=10.0, cum_pct=2.0, iwe=0.05),
        prior_snapshots=priors,
    )
    assert g.passed


def test_gate3_pass_at_exact_thresholds():
    g = evaluate_gate_3(
        _bundle(edge_bps=GATE3_MIN_EDGE_BPS, cum_pct=GATE3_MIN_CUM_DIFF_PCT,
                iwe=0.001),
        prior_snapshots=[],
    )
    assert g.passed


def test_gate3_fail_low_edge():
    g = evaluate_gate_3(
        _bundle(edge_bps=GATE3_MIN_EDGE_BPS - 0.01),
        prior_snapshots=[],
    )
    assert not g.passed
    assert "edge_bps" in g.reason


def test_gate3_fail_low_cum():
    g = evaluate_gate_3(
        _bundle(cum_pct=GATE3_MIN_CUM_DIFF_PCT - 0.01),
        prior_snapshots=[],
    )
    assert not g.passed
    assert "cumulative_return_diff_pct" in g.reason


def test_gate3_fail_iwe_zero():
    g = evaluate_gate_3(
        _bundle(iwe=0.0),
        prior_snapshots=[],
    )
    assert not g.passed
    assert "impact_weighted_edge" in g.reason


def test_gate3_fail_iwe_negative():
    g = evaluate_gate_3(
        _bundle(iwe=-0.01),
        prior_snapshots=[],
    )
    assert not g.passed


def test_gate3_pass_iwe_trend_within_noise_band():
    """Current iwe slightly below prior peak but within noise band."""
    prior_peak = 0.10
    current = prior_peak * (1 - GATE3_IMPACT_WEIGHTED_NOISE_BAND + 0.01)
    priors = [_prior_snap(iwe=v) for v in (0.05, 0.08, prior_peak)]
    g = evaluate_gate_3(
        _bundle(iwe=current),
        prior_snapshots=priors,
    )
    assert g.passed
    assert "noise band" in g.details["impact_weighted_trend_reason"]


def test_gate3_fail_iwe_trend_beyond_noise_band():
    prior_peak = 0.10
    current = prior_peak * (1 - GATE3_IMPACT_WEIGHTED_NOISE_BAND - 0.05)
    priors = [_prior_snap(iwe=v) for v in (0.05, 0.08, prior_peak)]
    g = evaluate_gate_3(
        _bundle(iwe=current),
        prior_snapshots=priors,
    )
    assert not g.passed
    assert "trend" in g.reason


def test_gate3_pass_iwe_non_decreasing_strict():
    priors = [_prior_snap(iwe=v) for v in (0.01, 0.02, 0.03)]
    g = evaluate_gate_3(
        _bundle(iwe=0.04),
        prior_snapshots=priors,
    )
    assert g.passed
    assert g.details["impact_weighted_trend_reason"] == "non-decreasing"


def test_gate3_pass_iwe_insufficient_history():
    g = evaluate_gate_3(
        _bundle(iwe=0.01),
        prior_snapshots=[],
    )
    assert g.passed
    assert "vacuously stable" in g.details["impact_weighted_trend_reason"]


# ===========================================================================
# Gate 4 — Tail Risk
# ===========================================================================

def test_gate4_pass_clean():
    g = evaluate_gate_4(_bundle())
    assert g.passed


def test_gate4_pass_at_exact_thresholds():
    g = evaluate_gate_4(_bundle(
        p99_delta=GATE4_MAX_P99_DELTA_NEGATIVE_BPS,
        p95_delta=GATE4_MAX_P95_DELTA_NEGATIVE_BPS,
    ))
    assert g.passed


def test_gate4_fail_tail_guard_triggered():
    g = evaluate_gate_4(_bundle(tail_guard=True))
    assert not g.passed
    assert "tail_guard_triggered" in g.reason


def test_gate4_fail_p99_too_negative():
    g = evaluate_gate_4(_bundle(
        p99_delta=GATE4_MAX_P99_DELTA_NEGATIVE_BPS - 0.01,
    ))
    assert not g.passed
    assert "tail_delta_p99_bps" in g.reason


def test_gate4_fail_p95_too_negative():
    g = evaluate_gate_4(_bundle(
        p95_delta=GATE4_MAX_P95_DELTA_NEGATIVE_BPS - 0.01,
    ))
    assert not g.passed
    assert "tail_delta_p95_bps" in g.reason


def test_gate4_pass_worst5_v2_better_at_every_rank():
    g = evaluate_gate_4(_bundle(
        b2_w5=[-200, -150, -120, -90, -50],
        v2_w5=[-180, -140, -110, -80, -40],
    ))
    assert g.passed
    rows = g.details["worst_5_rows"]
    assert all(r["passed"] for r in rows)


def test_gate4_pass_worst5_at_exact_10pct_deeper_boundary():
    """V2 exactly 1.10× as deep as B2 at every rank passes (boundary case)."""
    b2 = [-100.0, -80.0, -60.0, -40.0, -20.0]
    v2 = [x * GATE4_WORST5_DEEPER_FACTOR for x in b2]
    g = evaluate_gate_4(_bundle(b2_w5=b2, v2_w5=v2))
    assert g.passed


def test_gate4_fail_worst5_v2_more_than_10pct_deeper_at_one_rank():
    b2 = [-100.0, -80.0, -60.0, -40.0, -20.0]
    v2 = [-100.0, -80.0, -67.0, -40.0, -20.0]  # rank 2: -67 < 1.10×-60 = -66
    g = evaluate_gate_4(_bundle(b2_w5=b2, v2_w5=v2))
    assert not g.passed
    rows = g.details["worst_5_rows"]
    failing = [r for r in rows if not r["passed"]]
    assert len(failing) == 1
    assert failing[0]["rank"] == 2


def test_gate4_pass_worst5_v2_no_loss_where_b2_has_loss():
    g = evaluate_gate_4(_bundle(
        b2_w5=[-200, -150, -120, -90, -50],
        v2_w5=[0.0, 0.0, 0.0, 0.0, 0.0],
    ))
    assert g.passed


def test_gate4_fail_worst5_v2_introduces_loss_where_b2_has_none():
    g = evaluate_gate_4(_bundle(
        b2_w5=[0.0, 0.0, 0.0, 0.0, 0.0],
        v2_w5=[-1.0, 0.0, 0.0, 0.0, 0.0],
    ))
    assert not g.passed


def test_gate4_pass_worst5_when_neither_has_losses_at_a_rank():
    g = evaluate_gate_4(_bundle(
        b2_w5=[-200, -150, 0.0, 0.0, 0.0],
        v2_w5=[-180, -140, 0.0, 0.0, 0.0],
    ))
    assert g.passed


# ===========================================================================
# Gate 5 — Regime Validation
# ===========================================================================

def test_gate5_pass_clean():
    g = evaluate_gate_5(_bundle())
    assert g.passed


def test_gate5_fail_directional_edge_zero():
    by = {
        "stress": _regime_metrics(n=10, edge_bps=4.0, cum_pct=0.30),
        "directional": _regime_metrics(n=20, edge_bps=0.0, cum_pct=0.0),
        "neutral": _regime_metrics(n=10, edge_bps=2.0, cum_pct=0.20),
    }
    g = evaluate_gate_5(_bundle(by_regime=by))
    assert not g.passed
    assert "directional" in g.reason


def test_gate5_fail_directional_edge_negative():
    by = {
        "stress": _regime_metrics(n=10, edge_bps=4.0, cum_pct=0.30),
        "directional": _regime_metrics(n=20, edge_bps=-1.0, cum_pct=0.0),
        "neutral": _regime_metrics(n=10, edge_bps=2.0, cum_pct=0.20),
    }
    g = evaluate_gate_5(_bundle(by_regime=by))
    assert not g.passed


def test_gate5_pass_neutral_at_exact_minus_2_bps():
    by = {
        "stress": _regime_metrics(n=10, edge_bps=4.0, cum_pct=0.30),
        "directional": _regime_metrics(n=20, edge_bps=10.0, cum_pct=0.60),
        "neutral": _regime_metrics(
            n=10, edge_bps=GATE5_MAX_NEUTRAL_NEG_EDGE_BPS, cum_pct=0.0,
        ),
    }
    g = evaluate_gate_5(_bundle(by_regime=by))
    assert g.passed


def test_gate5_fail_neutral_below_minus_2_bps():
    by = {
        "stress": _regime_metrics(n=10, edge_bps=4.0, cum_pct=0.30),
        "directional": _regime_metrics(n=20, edge_bps=10.0, cum_pct=0.60),
        "neutral": _regime_metrics(
            n=10, edge_bps=GATE5_MAX_NEUTRAL_NEG_EDGE_BPS - 0.01, cum_pct=0.0,
        ),
    }
    g = evaluate_gate_5(_bundle(by_regime=by))
    assert not g.passed
    assert "neutral" in g.reason


def test_gate5_pass_neutral_empty_bucket_is_ok():
    by = {
        "stress": _regime_metrics(n=10, edge_bps=4.0, cum_pct=0.30),
        "directional": _regime_metrics(n=20, edge_bps=10.0, cum_pct=0.60),
        "neutral": {
            "n_divergent_days": 0,
            "n_b2_flat_v2_long": 0, "n_b2_long_v2_flat": 0,
            "win_rate_v2_vs_b2_pct": None,
            "avg_return_diff_1d_bps": None,
            "avg_return_diff_5d_bps": None,
            "cumulative_return_diff_pct": None,
            "avoided_losses_count": 0, "avoided_losses_avg_bps": None,
            "new_losses_count": 0, "new_losses_avg_bps": None,
            "impact_weighted_edge": None,
        },
    }
    g = evaluate_gate_5(_bundle(by_regime=by))
    assert g.passed


def test_gate5_fail_concentration_above_80pct():
    by = {
        "stress": _regime_metrics(n=10, edge_bps=4.0, cum_pct=0.05),
        "directional": _regime_metrics(n=20, edge_bps=10.0, cum_pct=1.00),
        "neutral": _regime_metrics(n=10, edge_bps=2.0, cum_pct=0.05),
    }
    g = evaluate_gate_5(_bundle(by_regime=by))
    assert not g.passed
    assert "concentration" in g.reason
    # share computation: 1.00 / (0.05 + 1.00 + 0.05) = ~0.909 > 0.80
    assert g.details["regime_concentration_max"] > 0.80


def test_gate5_pass_concentration_at_exact_80pct():
    by = {
        "stress": _regime_metrics(n=10, edge_bps=4.0, cum_pct=0.10),
        "directional": _regime_metrics(n=20, edge_bps=10.0, cum_pct=0.80),
        "neutral": _regime_metrics(n=10, edge_bps=2.0, cum_pct=0.10),
    }
    # 0.80 / 1.00 = exactly 0.80 → passes (≤)
    g = evaluate_gate_5(_bundle(by_regime=by))
    assert g.passed
    assert g.details["regime_concentration_max"] == pytest.approx(0.80)


def test_gate5_pass_when_no_positive_regime_cum():
    """All cum_pct ≤ 0 → concentration check N-A → does not fail."""
    by = {
        "stress": _regime_metrics(n=10, edge_bps=4.0, cum_pct=-0.10),
        "directional": _regime_metrics(n=20, edge_bps=10.0, cum_pct=0.0),
        "neutral": _regime_metrics(n=10, edge_bps=2.0, cum_pct=-0.20),
    }
    g = evaluate_gate_5(_bundle(by_regime=by))
    # Other Gate-5 sub-conditions still pass; concentration N-A
    assert g.passed
    assert g.details["regime_concentration_max"] is None


def test_gate5_fail_stress_proxy_when_v2_introduces_large_losses():
    by = {
        "stress": {
            **_regime_metrics(n=20, edge_bps=4.0, cum_pct=0.30),
            "new_losses_count": 5,
            "new_losses_avg_bps": 200.0,
            "avoided_losses_count": 1,
            "avoided_losses_avg_bps": 50.0,
        },
        "directional": _regime_metrics(n=20, edge_bps=10.0, cum_pct=0.60),
        "neutral": _regime_metrics(n=10, edge_bps=2.0, cum_pct=0.20),
    }
    # net = 200 − 50 = 150 > 10 → fail
    g = evaluate_gate_5(_bundle(by_regime=by))
    assert not g.passed
    assert "stress_tail" in g.reason


def test_gate5_pass_stress_proxy_when_avoided_offsets():
    by = {
        "stress": {
            **_regime_metrics(n=20, edge_bps=4.0, cum_pct=0.30),
            "new_losses_count": 2,
            "new_losses_avg_bps": 12.0,
            "avoided_losses_count": 5,
            "avoided_losses_avg_bps": 8.0,
        },
        "directional": _regime_metrics(n=20, edge_bps=10.0, cum_pct=0.60),
        "neutral": _regime_metrics(n=10, edge_bps=2.0, cum_pct=0.20),
    }
    # net = 12 − 8 = 4 ≤ 10 → pass
    g = evaluate_gate_5(_bundle(by_regime=by))
    assert g.passed


# ===========================================================================
# Gate 6 — Stability
# ===========================================================================

def test_gate6_pass_clean():
    g = evaluate_gate_6(_bundle(fh_edge=5.0, sh_edge=8.0,
                                 last_30_trend="STABLE"))
    assert g.passed


def test_gate6_fail_first_half_zero():
    g = evaluate_gate_6(_bundle(fh_edge=0.0))
    assert not g.passed
    assert "first_half_edge_bps" in g.reason


def test_gate6_fail_first_half_negative():
    g = evaluate_gate_6(_bundle(fh_edge=-1.0))
    assert not g.passed


def test_gate6_fail_second_half_zero():
    g = evaluate_gate_6(_bundle(sh_edge=0.0))
    assert not g.passed
    assert "second_half_edge_bps" in g.reason


def test_gate6_fail_trend_declining():
    g = evaluate_gate_6(_bundle(last_30_trend="DECLINING"))
    assert not g.passed
    assert "DECLINING" in g.reason


def test_gate6_fail_trend_insufficient():
    g = evaluate_gate_6(_bundle(last_30_trend="INSUFFICIENT"))
    assert not g.passed


def test_gate6_pass_trend_improving():
    g = evaluate_gate_6(_bundle(last_30_trend="IMPROVING"))
    assert g.passed


def test_gate6_pass_trend_stable():
    g = evaluate_gate_6(_bundle(last_30_trend="STABLE"))
    assert g.passed


# ===========================================================================
# Gate 7 — Governance
# ===========================================================================

def _gov(*, mode="SHADOW_COMPARE", ml=True, healthy=True, paused=False):
    return {
        "engine_b_mode": mode,
        "ml_advisory_only": ml,
        "comparison_framework_healthy": healthy,
        "b2_promotion_paused": paused,
    }


def _healthy_priors(n: int):
    return [_prior_snap(fetch_ok=True) for _ in range(n)]


def test_gate7_pass_legacy_mode():
    g = evaluate_gate_7(
        governance_state=_gov(mode="LEGACY"),
        prior_snapshots=_healthy_priors(10),
    )
    assert g.passed


def test_gate7_pass_shadow_compare_mode():
    g = evaluate_gate_7(
        governance_state=_gov(mode="SHADOW_COMPARE"),
        prior_snapshots=_healthy_priors(10),
    )
    assert g.passed


def test_gate7_pass_b2_paused_is_informational():
    g = evaluate_gate_7(
        governance_state=_gov(paused=True),
        prior_snapshots=_healthy_priors(10),
    )
    assert g.passed
    assert g.details["b2_promotion_paused"] is True


def test_gate7_fail_disallowed_mode():
    for mode in ("PARTIAL_B2_25", "PARTIAL_B2_50", "PARTIAL_B2_75",
                 "FULL_B2", "ANYTHING_ELSE"):
        g = evaluate_gate_7(
            governance_state=_gov(mode=mode),
            prior_snapshots=_healthy_priors(10),
        )
        assert not g.passed, f"mode={mode} should fail"
        assert "engine_b_mode" in g.reason


def test_gate7_fail_ml_not_advisory():
    g = evaluate_gate_7(
        governance_state=_gov(ml=False),
        prior_snapshots=_healthy_priors(10),
    )
    assert not g.passed
    assert "ml_advisory_only" in g.reason


def test_gate7_fail_recent_fetch_failure():
    priors = [_prior_snap(fetch_ok=True) for _ in range(8)]
    priors[-2] = _prior_snap(fetch_ok=False)
    g = evaluate_gate_7(
        governance_state=_gov(),
        prior_snapshots=priors,
    )
    assert not g.passed
    assert "comparison framework" in g.reason


def test_gate7_pass_insufficient_history_uses_current_health():
    g = evaluate_gate_7(
        governance_state=_gov(healthy=True),
        prior_snapshots=[],
    )
    assert g.passed


def test_gate7_fail_insufficient_history_unhealthy_now():
    g = evaluate_gate_7(
        governance_state=_gov(healthy=False),
        prior_snapshots=[],
    )
    assert not g.passed


# ===========================================================================
# Gate 8 — Operator Approval
# ===========================================================================

def test_gate8_pass_fresh_approval():
    snap_date = SNAPSHOT_DATE_OK
    approval = {
        "decision": "APPROVE",
        "approver": "ops@example.com",
        "approved_at": datetime(snap_date.year, snap_date.month, snap_date.day,
                                tzinfo=timezone.utc) - timedelta(days=2),
        "snapshot_id": 42,
    }
    g = evaluate_gate_8(
        snapshot_as_of_date=snap_date,
        snapshot_id=42,
        approval_records=[approval],
    )
    assert g.passed
    assert "ops@example.com" in g.reason


def test_gate8_fail_no_records():
    g = evaluate_gate_8(
        snapshot_as_of_date=SNAPSHOT_DATE_OK,
        snapshot_id=42,
        approval_records=[],
    )
    assert not g.passed
    assert "no fresh approval" in g.reason


def test_gate8_fail_approval_for_different_snapshot():
    approval = {
        "decision": "APPROVE",
        "approver": "ops@example.com",
        "approved_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
        "snapshot_id": 99,
    }
    g = evaluate_gate_8(
        snapshot_as_of_date=SNAPSHOT_DATE_OK,
        snapshot_id=42,
        approval_records=[approval],
    )
    assert not g.passed


def test_gate8_fail_approval_too_old():
    snap_date = SNAPSHOT_DATE_OK
    approval = {
        "decision": "APPROVE",
        "approver": "ops@example.com",
        "approved_at": datetime(snap_date.year, snap_date.month, snap_date.day,
                                tzinfo=timezone.utc)
            - timedelta(days=GATE8_APPROVAL_STALENESS_DAYS + 1),
        "snapshot_id": 42,
    }
    g = evaluate_gate_8(
        snapshot_as_of_date=snap_date,
        snapshot_id=42,
        approval_records=[approval],
    )
    assert not g.passed
    assert "no fresh approval" in g.reason


def test_gate8_pass_at_exact_staleness_boundary():
    snap_date = SNAPSHOT_DATE_OK
    approval = {
        "decision": "APPROVE",
        "approver": "ops@example.com",
        "approved_at": datetime(snap_date.year, snap_date.month, snap_date.day,
                                tzinfo=timezone.utc)
            - timedelta(days=GATE8_APPROVAL_STALENESS_DAYS),
        "snapshot_id": 42,
    }
    g = evaluate_gate_8(
        snapshot_as_of_date=snap_date,
        snapshot_id=42,
        approval_records=[approval],
    )
    assert g.passed


def test_gate8_fail_rescinded():
    snap_date = SNAPSHOT_DATE_OK
    base = {
        "approver": "ops@example.com",
        "approved_at": datetime(snap_date.year, snap_date.month, snap_date.day,
                                tzinfo=timezone.utc) - timedelta(days=1),
        "snapshot_id": 42,
    }
    g = evaluate_gate_8(
        snapshot_as_of_date=snap_date,
        snapshot_id=42,
        approval_records=[
            {**base, "decision": "APPROVE"},
            {**base, "decision": "RESCIND"},
        ],
    )
    assert not g.passed
    assert "rescinded" in g.reason


def test_gate8_fail_empty_approver():
    snap_date = SNAPSHOT_DATE_OK
    approval = {
        "decision": "APPROVE",
        "approver": "  ",
        "approved_at": datetime(snap_date.year, snap_date.month, snap_date.day,
                                tzinfo=timezone.utc) - timedelta(days=1),
        "snapshot_id": 42,
    }
    g = evaluate_gate_8(
        snapshot_as_of_date=snap_date,
        snapshot_id=42,
        approval_records=[approval],
    )
    assert not g.passed


def test_gate8_uses_most_recent_fresh_approver():
    snap_date = SNAPSHOT_DATE_OK
    base_dt = datetime(snap_date.year, snap_date.month, snap_date.day,
                       tzinfo=timezone.utc)
    g = evaluate_gate_8(
        snapshot_as_of_date=snap_date,
        snapshot_id=42,
        approval_records=[
            {"decision": "APPROVE", "approver": "first@example.com",
             "approved_at": base_dt - timedelta(days=10), "snapshot_id": 42},
            {"decision": "APPROVE", "approver": "second@example.com",
             "approved_at": base_dt - timedelta(days=1), "snapshot_id": 42},
        ],
    )
    assert g.passed
    assert "second@example.com" in g.reason


# ===========================================================================
# evaluate_all_gates — wiring
# ===========================================================================

def test_evaluate_all_gates_returns_all_8_named_results():
    out = evaluate_all_gates(
        _bundle(),
        snapshot_as_of_date=SNAPSHOT_DATE_OK,
        snapshot_id=1,
        prior_snapshots=_healthy_priors(GATE2_VERDICT_STREAK_REQUIRED - 1),
        governance_state=_gov(),
        approval_records=[],
    )
    expected = {
        "gate_1_minimum_sample",
        "gate_2_verdict_stability",
        "gate_3_edge_quality",
        "gate_4_tail_risk",
        "gate_5_regime_validation",
        "gate_6_stability",
        "gate_7_governance",
        "gate_8_operator_approval",
    }
    assert set(out.keys()) == expected
    assert len(out) == 8


def test_evaluate_all_gates_full_pass_with_approval():
    snap_date = SNAPSHOT_DATE_OK
    priors_v2 = _healthy_priors(GATE2_VERDICT_STREAK_REQUIRED - 1)
    out = evaluate_all_gates(
        _bundle(),
        snapshot_as_of_date=snap_date,
        snapshot_id=42,
        prior_snapshots=priors_v2,
        governance_state=_gov(),
        approval_records=[{
            "decision": "APPROVE",
            "approver": "ops@example.com",
            "approved_at": datetime(snap_date.year, snap_date.month,
                                     snap_date.day, tzinfo=timezone.utc)
                - timedelta(days=1),
            "snapshot_id": 42,
        }],
    )
    failing = [name for name, r in out.items() if not r.passed]
    assert failing == []


def test_evaluate_all_gates_partial_pass_no_approval_no_streak():
    out = evaluate_all_gates(
        _bundle(),
        snapshot_as_of_date=SNAPSHOT_DATE_OK,
        snapshot_id=1,
        prior_snapshots=[],
        governance_state=_gov(),
        approval_records=[],
    )
    # Gate 2 fails (no streak history), Gate 8 fails (no approval),
    # Gates 1, 3, 4, 5, 6, 7 pass on the clean default bundle.
    expected_failing = {"gate_2_verdict_stability", "gate_8_operator_approval"}
    failing = {name for name, r in out.items() if not r.passed}
    assert failing == expected_failing


def test_evaluate_all_gates_with_no_optional_inputs():
    """Defaults to empty lists / dicts for all optional inputs."""
    out = evaluate_all_gates(
        _bundle(),
        snapshot_as_of_date=SNAPSHOT_DATE_OK,
    )
    assert "gate_1_minimum_sample" in out
    # Gate 7 must run even without governance_state — and fail (no mode set)
    assert not out["gate_7_governance"].passed
    # Gate 8 must run without approval_records — and fail
    assert not out["gate_8_operator_approval"].passed


# ===========================================================================
# Phase 9B.1 — Gate 4 internal sample guard + Gate 1 OOS floor 60d
# ===========================================================================

def test_gate1_oos_floor_now_60_days_not_10():
    """Phase 9B.1: GATE1_MIN_OOS_DAYS raised from 10 to 60."""
    assert GATE1_MIN_OOS_DAYS == 60
    g = evaluate_gate_1(
        _bundle(),
        snapshot_as_of_date=FRAMEWORK_IMPLEMENTATION_DATE
            + timedelta(days=30),
    )
    assert not g.passed
    assert "oos_days" in g.reason
    assert g.details["oos_days"] == 30


def test_gate1_passes_at_exactly_60_oos_days():
    g = evaluate_gate_1(
        _bundle(n_input=GATE1_MIN_INPUT_ROWS,
                n_div=GATE1_MIN_DIVERGENT_ROWS,
                n_b2flat=GATE1_MIN_B2_FLAT_V2_LONG),
        snapshot_as_of_date=FRAMEWORK_IMPLEMENTATION_DATE
            + timedelta(days=GATE1_MIN_OOS_DAYS),
    )
    assert g.passed


def test_gate4_insufficient_tail_sample_n_div_below_50():
    """Phase 9B.1: Gate 4 fails fast when n_div < 50 with explicit reason."""
    bundle = _bundle(n_div=GATE4_MIN_DIVERGENT_DAYS_FOR_TAIL - 1, n_input=300)
    g = evaluate_gate_4(bundle)
    assert not g.passed
    assert "INSUFFICIENT_TAIL_SAMPLE" in g.reason
    assert g.details["n_divergent_days"] == GATE4_MIN_DIVERGENT_DAYS_FOR_TAIL - 1


def test_gate4_insufficient_tail_sample_b2_n_below_250():
    """Phase 9B.1: Gate 4 fails when len(b2 returns) < 250 even if
    other thresholds pass."""
    bundle = _bundle(n_input=GATE4_MIN_RETURN_OBSERVATIONS_FOR_P99 - 1, n_div=60)
    g = evaluate_gate_4(bundle)
    assert not g.passed
    assert "INSUFFICIENT_TAIL_SAMPLE" in g.reason


def test_gate4_passes_when_all_floors_met():
    """Sanity — fixture defaults satisfy both 9B.1 floors."""
    g = evaluate_gate_4(_bundle())
    assert g.passed


def test_gate4_floors_are_module_constants():
    """Phase 9B.1: floors must be frozen module-level constants."""
    assert GATE4_MIN_DIVERGENT_DAYS_FOR_TAIL == 50
    assert GATE4_MIN_RETURN_OBSERVATIONS_FOR_P99 == 250
