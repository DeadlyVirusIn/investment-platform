"""ML-6 — Hybrid Monitor math tests (pure helpers, no DB)."""

from __future__ import annotations

import datetime as dt
import pytest
from unittest.mock import MagicMock

from apps.api.src.ml.shadow.hybrid_monitor import (
    HybridWindowResult, _safe_mean, _safe_sharpe,
    compute_window_performance,
)


# ---------------------------------------------------------------------------
# Pure math
# ---------------------------------------------------------------------------

def test_safe_mean_empty():
    assert _safe_mean([]) is None


def test_safe_mean_basic():
    assert _safe_mean([1.0, 2.0, 3.0]) == 2.0


def test_safe_sharpe_needs_two_points():
    assert _safe_sharpe([1.0]) is None


def test_safe_sharpe_zero_stdev():
    # All equal → stdev=0 → None (guard against div-zero)
    assert _safe_sharpe([1.0, 1.0, 1.0]) is None


def test_safe_sharpe_positive():
    s = _safe_sharpe([0.5, 0.8, 0.3, 1.1])
    assert s is not None
    assert s > 0


# ---------------------------------------------------------------------------
# Result serialization
# ---------------------------------------------------------------------------

def test_result_to_dict_rounds_and_stringifies_date():
    r = HybridWindowResult(
        window_days=14, as_of_date=dt.date(2026, 4, 24),
        mode="advisory",
        avoided_loss_estimate=12.3456789,
        delta_sharpe_vs_deterministic=0.0123456789,
        calibration_ece=0.012345678,
    )
    d = r.to_dict()
    assert d["as_of_date"] == "2026-04-24"
    assert d["avoided_loss_estimate"] == 12.3457
    assert d["delta_sharpe_vs_deterministic"] == 0.0123
    assert d["calibration_ece"] == 0.012346


# ---------------------------------------------------------------------------
# Integrated math via compute_window_performance
# ---------------------------------------------------------------------------

def _mk_trade(
    *, status="closed", ml_avail=True, ml_action="reduce",
    mult=0.8, ret=-1.2, psize=1.0,
):
    # mapping row emitted from SQL
    return {
        "entry_date": dt.date(2026, 4, 20),
        "exit_date":  dt.date(2026, 4, 24),
        "status": status,
        "engine": "B",
        "instrument": "SPY",
        "position_size_pct": 1.0,
        "net_ret_pct": ret,
        "exploratory_paper": False,
        "ml_avail":  "true" if ml_avail else "false",
        "ml_action": ml_action,
        "ml_mult":   str(mult),
        "psize":     str(psize),
    }


def _session_with(trades: list[dict], model: dict | None = None):
    """Build a mock session that returns provided rows for trade + model
    queries. Order matters: compute_window_performance calls trades first,
    then model."""
    s = MagicMock()
    trade_mapping = MagicMock()
    trade_mapping.all.return_value = trades
    model_mapping = MagicMock()
    model_mapping.first.return_value = model
    # execute returns an object whose .mappings() yields different
    # results per call — use side_effect
    s.execute.return_value.mappings.side_effect = [
        trade_mapping, model_mapping,
    ]
    return s


def test_compute_monitor_empty_returns_none_estimates():
    s = _session_with(trades=[], model=None)
    r = compute_window_performance(
        s, as_of=dt.date(2026, 4, 24), window_days=14, mode="advisory",
    )
    assert r.ml_advice_count == 0
    assert r.avoided_loss_estimate is None
    assert r.missed_winner_estimate is None
    assert "insufficient_advice" in r.blockers


def test_compute_monitor_counts_avoided_loss():
    # 25 warn trades — 20 losses, 5 wins → good_warning 0.8, false_avoid 0.2
    trades = []
    for _ in range(20):
        trades.append(_mk_trade(ml_action="avoid", ret=-1.0))
    for _ in range(5):
        trades.append(_mk_trade(ml_action="avoid", ret=+0.5))
    model = {
        "id": "r1", "status": "SHADOW_OUTPERFORMING",
        "created_at": dt.datetime.now(),
        "calibration": {"ece": 0.02, "brier": 0.10,
                         "poor_calibration": False},
        "baseline_comparison": {"winner": "ml", "delta_sharpe": 0.1},
        "metrics": {},
    }
    s = _session_with(trades=trades, model=model)
    r = compute_window_performance(
        s, as_of=dt.date(2026, 4, 24), window_days=14, mode="advisory",
    )
    assert r.ml_advice_count == 25
    assert r.ml_avoid_count == 25
    # avoided_loss_estimate = sum of |−1| over 20 losses = 20.0
    assert r.avoided_loss_estimate == pytest.approx(20.0)
    # missed_winner_estimate = sum of +0.5 over 5 wins = 2.5
    assert r.missed_winner_estimate == pytest.approx(2.5)
    # good_warning_rate = 20/25 = 0.8
    assert r.good_warning_rate == pytest.approx(0.8)
    # false_avoid_rate = 5/25 = 0.2
    assert r.false_avoid_rate == pytest.approx(0.2)


def test_compute_monitor_delta_sharpe_positive_when_ml_reduces_losses():
    # ML warns only on losses, reducing them. Counterfactual Sharpe > det
    trades = []
    for _ in range(15):
        trades.append(_mk_trade(ml_action="reduce", mult=0.5, ret=-2.0))
    for _ in range(15):
        trades.append(_mk_trade(ml_action="accept", mult=1.0, ret=+1.0))
    model = {
        "id": "r1", "status": "SHADOW_OUTPERFORMING",
        "created_at": dt.datetime.now(),
        "calibration": {"ece": 0.03, "brier": 0.15,
                         "poor_calibration": False},
        "baseline_comparison": {"winner": "ml", "delta_sharpe": 0.15},
        "metrics": {},
    }
    s = _session_with(trades=trades, model=model)
    r = compute_window_performance(
        s, as_of=dt.date(2026, 4, 24), window_days=30, mode="advisory",
    )
    assert r.delta_sharpe_vs_deterministic is not None
    assert r.delta_sharpe_vs_deterministic > 0
    # No blockers on sample sizes
    assert "insufficient_advice" not in r.blockers
    assert "insufficient_outcomes" not in r.blockers
    assert "poor_calibration" not in r.blockers
    assert "below_baseline" not in r.blockers


def test_snapshot_to_dict_stable_keys():
    r = HybridWindowResult(
        window_days=7, as_of_date=dt.date(2026, 4, 24),
        mode="advisory",
    )
    d = r.to_dict()
    required = {
        "window_days", "as_of_date", "mode",
        "ml_advice_count", "ml_reduce_count", "ml_avoid_count",
        "ml_eligible_count", "ml_gated_count", "deterministic_trades",
        "ml_agreement_count", "ml_disagreement_count",
        "avoided_loss_estimate", "missed_winner_estimate",
        "false_avoid_rate", "missed_winner_rate", "good_warning_rate",
        "avg_return_when_ml_agreed", "avg_return_when_ml_warned",
        "avg_return_when_ml_unavailable",
        "delta_sharpe_vs_deterministic",
        "calibration_ece", "brier_score", "model_status",
        "blockers", "recommendation", "metrics",
    }
    assert required.issubset(d.keys())
