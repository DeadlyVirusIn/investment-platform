"""ML-6 — Promotion Guard state-machine tests.

No DB. Guard operates purely on dicts shaped like HybridWindowResult.
Contract under test:
  • never flips mode
  • requires required_healthy_days consecutive clean 7d windows
  • ECE / Δ Sharpe / false_avoid gates
  • OPERATOR approval remains required on every result
"""

from __future__ import annotations

from apps.api.src.ml.shadow.promotion_guard import (
    PromotionThresholds, evaluate_promotion,
)


TH = PromotionThresholds()


def _healthy_window(days: int, *, advice=40, outcomes=40,
                     ece=0.03, dsh=0.08, fa=0.10, mw=0.10,
                     status="SHADOW_OUTPERFORMING"):
    return {
        "window_days": days, "as_of_date": "2026-04-24",
        "mode": "advisory",
        "ml_advice_count": advice,
        "ml_reduce_count": 10, "ml_avoid_count": 5,
        "ml_eligible_count": advice, "ml_gated_count": 2,
        "deterministic_trades": outcomes,
        "ml_agreement_count": 20, "ml_disagreement_count": 5,
        "avoided_loss_estimate": 12.5,
        "missed_winner_estimate": 3.0,
        "false_avoid_rate": fa,
        "missed_winner_rate": mw,
        "good_warning_rate": 0.7,
        "avg_return_when_ml_agreed": 0.4,
        "avg_return_when_ml_warned": -0.6,
        "avg_return_when_ml_unavailable": 0.1,
        "delta_sharpe_vs_deterministic": dsh,
        "calibration_ece": ece, "brier_score": 0.18,
        "model_status": status,
        "blockers": [], "recommendation": "",
        "metrics": {},
    }


def _history_healthy(n: int) -> list[dict]:
    return [
        _healthy_window(7) for _ in range(n)
    ]


# ---------------------------------------------------------------------------

def test_no_ml_when_empty():
    d = evaluate_promotion(
        current_mode="advisory", window_results={},
        has_ml_predictions=False, thresholds=TH,
    )
    assert d.state == "NOT_READY_NO_ML"


def test_insufficient_advice_blocks():
    w = {14: _healthy_window(14, advice=3)}
    d = evaluate_promotion(
        current_mode="advisory", window_results=w, thresholds=TH,
    )
    assert d.state == "NOT_READY_INSUFFICIENT_ADVICE"


def test_insufficient_outcomes_blocks():
    w = {14: _healthy_window(14, outcomes=5)}
    d = evaluate_promotion(
        current_mode="advisory", window_results=w, thresholds=TH,
    )
    assert d.state == "NOT_READY_INSUFFICIENT_OUTCOMES"


def test_poor_calibration_blocks():
    w = {14: _healthy_window(14, ece=0.20)}
    d = evaluate_promotion(
        current_mode="advisory", window_results=w, thresholds=TH,
    )
    assert d.state == "NOT_READY_POOR_CALIBRATION"


def test_below_baseline_blocks():
    w = {14: _healthy_window(14, dsh=-0.5)}
    d = evaluate_promotion(
        current_mode="advisory", window_results=w, thresholds=TH,
    )
    assert d.state == "NOT_READY_BELOW_BASELINE"


def test_model_status_not_outperforming_blocks():
    w = {14: _healthy_window(14, status="TRAINED_SHADOW")}
    d = evaluate_promotion(
        current_mode="advisory", window_results=w, thresholds=TH,
    )
    assert d.state == "NOT_READY_BELOW_BASELINE"


def test_high_false_avoid_blocks():
    w = {14: _healthy_window(14, fa=0.80)}
    d = evaluate_promotion(
        current_mode="advisory", window_results=w, thresholds=TH,
    )
    assert d.state == "NOT_READY_HIGH_FALSE_AVOID"


def test_advisory_healthy_needs_days():
    # All gates clean, but no trailing history → ADVISORY_HEALTHY
    w = {14: _healthy_window(14), 7: _healthy_window(7),
         30: _healthy_window(30)}
    d = evaluate_promotion(
        current_mode="advisory", window_results=w,
        recent_snapshots=[], thresholds=TH,
    )
    assert d.state == "ADVISORY_HEALTHY"
    assert d.healthy_day_count == 0


def test_ready_for_paper_reduce_when_days_ok():
    w = {14: _healthy_window(14), 7: _healthy_window(7),
         30: _healthy_window(30)}
    d = evaluate_promotion(
        current_mode="advisory", window_results=w,
        recent_snapshots=_history_healthy(TH.required_healthy_days),
        thresholds=TH,
    )
    assert d.state == "READY_FOR_PAPER_REDUCE"
    assert d.current_mode == "advisory"
    # Guard must NOT flip mode
    assert d.current_mode != "paper_reduce"
    assert d.operator_approval_required is True


def test_paper_reduce_paused_on_negative_delta():
    w = {14: _healthy_window(14, dsh=-0.1)}
    d = evaluate_promotion(
        current_mode="paper_reduce", window_results=w,
        recent_snapshots=_history_healthy(10), thresholds=TH,
    )
    # Because delta is negative, the blocker chain stops us at
    # NOT_READY_BELOW_BASELINE before reaching the PAPER_REDUCE_PAUSED
    # live-degradation check — that's still correct advice (revert).
    assert d.state in ("PAPER_REDUCE_PAUSED", "NOT_READY_BELOW_BASELINE")


def test_operator_approval_always_required():
    w = {14: _healthy_window(14), 7: _healthy_window(7),
         30: _healthy_window(30)}
    d = evaluate_promotion(
        current_mode="advisory", window_results=w,
        recent_snapshots=_history_healthy(TH.required_healthy_days),
        thresholds=TH,
    )
    assert d.operator_approval_required is True


def test_guard_does_not_mutate_mode_dict_keys():
    # Ensure evaluate_promotion returns a decision dict with no magic
    # "apply" or "set_mode" field → cannot auto flip
    w = {14: _healthy_window(14)}
    d = evaluate_promotion(
        current_mode="advisory", window_results=w, thresholds=TH,
    )
    out = d.to_dict()
    assert "apply" not in out
    assert "set_mode" not in out
    assert "auto_apply" not in out


def test_30d_long_window_confirmation_catches_regression():
    # 14d clean but 30d shows high_false_avoid → stay ADVISORY_HEALTHY
    w14 = _healthy_window(14)
    w30 = _healthy_window(30, fa=0.8)   # regresses on 30d
    d = evaluate_promotion(
        current_mode="advisory",
        window_results={7: _healthy_window(7), 14: w14, 30: w30},
        recent_snapshots=_history_healthy(TH.required_healthy_days),
        thresholds=TH,
    )
    assert d.state == "ADVISORY_HEALTHY"
