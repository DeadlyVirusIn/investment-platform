"""Engine C readiness state transitions + baselines_v2 + recommendation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from apps.api.src.ml.baselines_v2 import run_improved_baselines
from apps.api.src.ml.recommendation import build_recommendation
from apps.api.src.ml.snapshots import engine_c_readiness


def _toy(n=400, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "as_of_date": pd.date_range("2025-01-01", periods=n),
        "symbol": rng.choice(["SPY", "QQQ"], n),
        "fwd_ret_5d": rng.normal(0.001, 0.02, n),
        "feature_confidence": rng.random(n),
        "event_risk_score": rng.random(n),
        "has_earnings_soon": rng.integers(0, 2, n).astype(bool),
        "gates_favorable": rng.integers(0, 5, n),
        "regime_stress": rng.integers(0, 2, n),
        "regime_directional": rng.integers(0, 2, n),
        "regime_neutral": rng.integers(0, 2, n),
    })


# ---------------------------------------------------------------------------
# Baselines v2
# ---------------------------------------------------------------------------

def test_improved_baselines_all_return_results():
    df = _toy(n=300)
    rows = run_improved_baselines(df, label_col="fwd_ret_5d")
    names = [r.name for r in rows]
    # At least one of each family present
    assert any(n.startswith("v2_catalyst_overlay@") for n in names)
    assert any(n.startswith("v2_data_conf@") for n in names)
    assert any(n.startswith("v2_regime_gate") for n in names)
    assert "v2_hybrid_conservative" in names
    # Totals sum correctly (accepted + rejected == n_total)
    for r in rows:
        assert r.n_rows == 300


def test_improved_baselines_handle_missing_label():
    df = _toy(n=50).drop(columns=["fwd_ret_5d"])
    rows = run_improved_baselines(df, label_col="fwd_ret_5d")
    assert rows == []


# ---------------------------------------------------------------------------
# Readiness transitions
# ---------------------------------------------------------------------------

def test_readiness_disabled_leakage():
    r = engine_c_readiness(
        n_rows=5000, labeled_rows=5000,
        leakage_ok=False, best_baseline_sharpe=0.5,
        ml_test_sharpe=0.9, catalyst_coverage=0.9,
        avg_feature_conf=0.9, min_training_rows=1000,
    )
    assert r["engine_c_ml_status"] == "DISABLED_LEAKAGE_RISK"
    assert "leakage" in r["engine_c_ml_reason"].lower()


def test_readiness_insufficient_data_hard_floor():
    r = engine_c_readiness(
        n_rows=100, labeled_rows=50,
        leakage_ok=True, best_baseline_sharpe=0.0,
        ml_test_sharpe=None, catalyst_coverage=0.5,
        avg_feature_conf=0.7, min_training_rows=1000,
    )
    assert r["engine_c_ml_status"] == "DISABLED_INSUFFICIENT_DATA"


def test_readiness_baselines_only_when_labeled_below_min():
    r = engine_c_readiness(
        n_rows=800, labeled_rows=500,
        leakage_ok=True, best_baseline_sharpe=0.2,
        ml_test_sharpe=None, catalyst_coverage=0.4,
        avg_feature_conf=0.7, min_training_rows=1000,
    )
    assert r["engine_c_ml_status"] == "BASELINES_ONLY"


def test_readiness_advisory_ready_when_rows_sufficient():
    r = engine_c_readiness(
        n_rows=2000, labeled_rows=1500,
        leakage_ok=True, best_baseline_sharpe=0.2,
        ml_test_sharpe=None, catalyst_coverage=0.5,
        avg_feature_conf=0.8, min_training_rows=1000,
    )
    assert r["engine_c_ml_status"] == "ADVISORY_READY"


def test_readiness_shadow_ready_when_ml_below_baseline():
    r = engine_c_readiness(
        n_rows=2000, labeled_rows=1500,
        leakage_ok=True, best_baseline_sharpe=1.0,
        ml_test_sharpe=0.6, catalyst_coverage=0.8,
        avg_feature_conf=0.9, min_training_rows=1000,
    )
    assert r["engine_c_ml_status"] == "SHADOW_READY"


def test_readiness_active_candidate_when_ml_beats_baseline():
    r = engine_c_readiness(
        n_rows=2000, labeled_rows=1500,
        leakage_ok=True, best_baseline_sharpe=0.3,
        ml_test_sharpe=0.9, catalyst_coverage=0.9,
        avg_feature_conf=0.9, min_training_rows=1000,
    )
    assert r["engine_c_ml_status"] == "ACTIVE_CANDIDATE"


# ---------------------------------------------------------------------------
# Recommendation generator
# ---------------------------------------------------------------------------

def test_recommendation_prioritises_leakage():
    msg = build_recommendation(
        n_rows=5000, tier="walk_forward_ok",
        leakage_ok=False, catalyst_coverage=0.9,
        best_baseline_sharpe=1.0, engine_c_status="ADVISORY_READY",
        warnings=[],
    )
    assert "leakage" in msg.lower()


def test_recommendation_tier_diagnostics_only():
    msg = build_recommendation(
        n_rows=50, tier="diagnostics_only",
        leakage_ok=True, catalyst_coverage=0.0,
        best_baseline_sharpe=0.0,
        engine_c_status="DISABLED_INSUFFICIENT_DATA",
        warnings=[],
    )
    assert "continue collecting" in msg.lower()


def test_recommendation_rich_experiments_when_active_candidate():
    msg = build_recommendation(
        n_rows=8000, tier="rich_experiments_allowed",
        leakage_ok=True, catalyst_coverage=0.8,
        best_baseline_sharpe=0.4, engine_c_status="ACTIVE_CANDIDATE",
        warnings=[],
    )
    assert ("promotion" in msg.lower()) or ("candidate" in msg.lower())
