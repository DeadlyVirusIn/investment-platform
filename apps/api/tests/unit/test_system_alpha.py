"""SYSTEM-ALPHA — unit tests for deterministic modules.

No DB. Synthetic data only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from apps.api.src.alpha.catalyst_analytics import build_catalyst_analytics
from apps.api.src.alpha.data_quality import (
    compute_feature_heatmap, compute_provider_reliability,
)
from apps.api.src.alpha.execution_quality import (
    compute_entry_quality, simulate_paper_slippage,
)
from apps.api.src.alpha.exit_research import simulate_exits
from apps.api.src.alpha.factor_attribution import (
    compute_factor_attribution,
)
from apps.api.src.alpha.failure_classifier import classify_failure
from apps.api.src.alpha.feature_registry import (
    FeatureRegistryEntry, detect_drift,
)
from apps.api.src.alpha.health_score import compute_system_health
from apps.api.src.alpha.risk_engine import compute_portfolio_risk
from apps.api.src.alpha.signal_analytics import analyze_signals


# ---------------------------------------------------------------------------
# Factor attribution
# ---------------------------------------------------------------------------

def test_factor_attribution_is_deterministic():
    inputs = {"mean_20d_ret": 0.002, "atr_ratio": 1.1,
              "vol_elevated": False, "vol_expanding": False}
    ctx = {"stress_regime": False, "directional_regime": True,
           "gates_favorable": 3}
    cat = {"event_risk_score": 0.1, "catalyst_score": 0.2,
           "trade_policy": "neutral"}
    dq = {"confidence": 0.95, "missing_fields": [], "stale_fields": []}
    a = compute_factor_attribution(
        inputs_used=inputs, context_values=ctx,
        catalyst=cat, data_quality=dq,
    )
    b = compute_factor_attribution(
        inputs_used=inputs, context_values=ctx,
        catalyst=cat, data_quality=dq,
    )
    assert a.to_dict() == b.to_dict()


def test_factor_attribution_block_catalyst_dominates():
    a = compute_factor_attribution(
        catalyst={"trade_policy": "block_new_entry"},
    )
    assert a.catalyst == -1.0


def test_factor_attribution_clipped_to_unit_range():
    a = compute_factor_attribution(
        inputs_used={"mean_20d_ret": 10.0, "atr_ratio": 5.0},
    )
    for v in (a.momentum, a.volatility, a.regime,
              a.catalyst, a.data_quality, a.risk, a.execution):
        assert -1.0 <= v <= 1.0


def test_factor_attribution_uses_no_future_data():
    # Explicitly pass outcome-like keys; attribution must not reference them
    a = compute_factor_attribution(
        inputs_used={"fwd_ret_5d": 0.5, "realized_net_ret": 0.9,
                      "mean_20d_ret": 0.0},
    )
    assert a.momentum == 0.0   # only driven by mean_20d_ret


# ---------------------------------------------------------------------------
# Execution quality
# ---------------------------------------------------------------------------

def test_entry_quality_flags_chase():
    q = compute_entry_quality(
        symbol="AAPL", entry_price=100.0, next_price=99.5,
        configured_slippage_bps=5.0,
    )
    assert q.adverse_move_bps is not None
    assert q.adverse_move_bps < 0
    assert "possible_chase" in q.flags or "late_entry_adverse_move" in q.flags


def test_slippage_is_analytics_only_flag_separate():
    # Simulator applied correctly for buy
    p = simulate_paper_slippage(raw_price=100.0, side="buy", slippage_bps=10)
    assert p > 100.0
    p2 = simulate_paper_slippage(raw_price=100.0, side="sell", slippage_bps=10)
    assert p2 < 100.0


# ---------------------------------------------------------------------------
# Exit research
# ---------------------------------------------------------------------------

def test_exit_research_does_not_mutate_trades():
    trades = [{
        "trade_id": "t1", "symbol": "SPY",
        "entry_date": "2025-01-02", "entry_price": 100.0, "atr": 1.0,
    }]
    dates = pd.bdate_range("2025-01-03", periods=10)
    bars = {
        "SPY": pd.DataFrame({
            "date": dates,
            "close": np.linspace(101, 110, 10),
            "high":  np.linspace(101, 110, 10) + 0.5,
            "low":   np.linspace(101, 110, 10) - 0.5,
        }),
    }
    results = simulate_exits(trades, bars)
    # Trades list unchanged
    assert trades[0]["entry_price"] == 100.0
    # Returns plausible
    assert all(r.n_trades >= 0 for r in results)


# ---------------------------------------------------------------------------
# Catalyst analytics
# ---------------------------------------------------------------------------

def test_catalyst_analytics_earnings_buckets():
    df = pd.DataFrame({
        "fwd_ret_5d": np.linspace(-0.02, 0.02, 30),
        "days_to_earnings": np.random.default_rng(0).integers(0, 15, 30),
    })
    ca = build_catalyst_analytics(df)
    assert len(ca.earnings_window_buckets) >= 5


# ---------------------------------------------------------------------------
# Risk engine
# ---------------------------------------------------------------------------

def test_risk_score_concentration_detected():
    positions = [
        {"symbol": "AAPL", "weight_pct": 70, "has_earnings_soon": False},
        {"symbol": "MSFT", "weight_pct": 30, "has_earnings_soon": False},
    ]
    r = compute_portfolio_risk(
        positions=positions,
        current_drawdown_pct=-1.0,
        regime="directional",
    )
    assert r.concentration_score > 0.3
    assert r.drawdown_recommendation == "normal"


def test_risk_score_drawdown_triggers_recommendation():
    r = compute_portfolio_risk(
        positions=[], current_drawdown_pct=-8.0, regime="neutral",
    )
    assert r.drawdown_recommendation in {
        "pause_weak_signals", "paper_only_safe_mode", "tighten_filters",
    }


# ---------------------------------------------------------------------------
# Data quality
# ---------------------------------------------------------------------------

def test_provider_reliability_weights_success_highest():
    a = compute_provider_reliability(
        provider="p", success_rate=1.0, freshness_score=0.5,
        missing_rate=0.5, error_rate=0.5,
    )
    b = compute_provider_reliability(
        provider="p", success_rate=0.5, freshness_score=1.0,
        missing_rate=0.0, error_rate=0.0,
    )
    # Success rate 0.5 higher in A; check weights behave
    assert a.reliability_score != b.reliability_score


# ---------------------------------------------------------------------------
# Failure classifier
# ---------------------------------------------------------------------------

def test_failure_classifier_returns_empty_for_winner():
    f = classify_failure(
        trade_id="t", net_ret_pct=0.02,
        regime_at_entry="directional", data_confidence=0.9,
        catalyst_policy="neutral", days_to_earnings=10,
        entry_quality_score=0.9,
        max_adverse=-0.01, max_favorable=0.03,
    )
    assert f.failure_reasons == []
    assert "not a loss" in f.summary


def test_failure_classifier_flags_earnings_window():
    f = classify_failure(
        trade_id="t", net_ret_pct=-0.03,
        regime_at_entry="neutral", data_confidence=0.9,
        catalyst_policy="neutral", days_to_earnings=1,
        entry_quality_score=0.7,
        max_adverse=-0.05, max_favorable=0.005,
    )
    names = [r["reason"] for r in f.failure_reasons]
    assert "catalyst_ignored" in names


def test_failure_classifier_flags_exit_issue_round_trip():
    f = classify_failure(
        trade_id="t", net_ret_pct=-0.005,
        regime_at_entry="directional", data_confidence=0.9,
        catalyst_policy="neutral", days_to_earnings=20,
        entry_quality_score=0.9,
        max_adverse=-0.01, max_favorable=0.04,
    )
    names = [r["reason"] for r in f.failure_reasons]
    assert "exit_issue" in names


# ---------------------------------------------------------------------------
# Health score
# ---------------------------------------------------------------------------

def test_health_score_overall_shape():
    h = compute_system_health(
        data_quality=0.8, signal_quality=0.6,
        catalyst_coverage=0.3, execution_quality=0.7,
        risk_control=0.75, ml_readiness=0.45, paper_feedback=0.6,
    )
    assert 0 <= h.overall <= 100
    assert "catalyst" in h.recommendation.lower() \
           or "paper" in h.recommendation.lower() \
           or "shadow" in h.recommendation.lower()


def test_health_score_low_data_blocks_ml_rec():
    h = compute_system_health(data_quality=0.3)
    assert "data quality" in h.recommendation.lower()


# ---------------------------------------------------------------------------
# Feature registry / drift
# ---------------------------------------------------------------------------

def test_drift_detects_new_and_removed_features():
    baseline = pd.DataFrame({"a": [1.0] * 50, "b": [2.0] * 50})
    recent   = pd.DataFrame({"a": [1.0] * 50, "c": [3.0] * 50})
    r = detect_drift(baseline=baseline, recent=recent, registry=[])
    assert "c" in r.schema_new_features
    assert "b" in r.schema_removed_features


def test_drift_detects_dtype_change():
    b = pd.DataFrame({"a": [1.0] * 50})
    r = pd.DataFrame({"a": ["x"] * 50})
    rep = detect_drift(baseline=b, recent=r, registry=[])
    assert rep.schema_dtype_changes
    assert rep.schema_dtype_changes[0]["feature"] == "a"


def test_drift_out_of_range_flagged():
    b = pd.DataFrame({"a": np.linspace(0, 1, 60)})
    r = pd.DataFrame({"a": np.linspace(0, 5, 60)})
    entry = FeatureRegistryEntry(
        feature_name="a", feature_set_version="v1",
        dtype="float", allowed_range=(0.0, 1.0),
    )
    rep = detect_drift(baseline=b, recent=r, registry=[entry])
    assert rep.out_of_range
    assert rep.out_of_range[0]["feature"] == "a"


# ---------------------------------------------------------------------------
# Signal analytics
# ---------------------------------------------------------------------------

def test_signal_insights_empty_returns_warning():
    out = analyze_signals(pd.DataFrame())
    assert "empty" in " ".join(out.warnings).lower()


# ---------------------------------------------------------------------------
# Feature heatmap
# ---------------------------------------------------------------------------

def test_feature_heatmap_orders_by_missing_rate():
    df = pd.DataFrame({
        "a": [1, 2, 3, None, None],
        "b": [1, 2, 3, 4, 5],
    })
    h = compute_feature_heatmap(df, feature_cols=("a", "b", "c"))
    # "a" has 40% missing, "c" missing entirely, "b" 0%
    names = [r["feature"] for r in h.features]
    assert names[0] == "c" or names[0] == "a"
