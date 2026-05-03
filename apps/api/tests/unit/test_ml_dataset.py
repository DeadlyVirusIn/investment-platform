"""Tests for label construction, splits, baselines, feature health, advisory.

No DB — uses hand-built DataFrames to exercise every pure module.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from apps.api.src.ml.advisory import (
    Advisory, AdvisoryAction, EngineCStatus, build_advisory, engine_c_status,
)
from apps.api.src.ml.baselines import run_baselines
from apps.api.src.ml.labels import LabelConfig, attach_labels
from apps.api.src.ml.report import build_feature_health
from apps.api.src.ml.splits import (
    WalkForwardConfig, enough_data_for_ml, walk_forward_splits,
)


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

def _toy_bars():
    dates = pd.date_range("2025-01-01", periods=20, freq="B")
    # Upward drift so positive returns dominate
    closes = np.linspace(100, 110, 20)
    return pd.DataFrame({
        "date": dates,
        "symbol": "SPY",
        "close": closes,
        "high": closes + 0.5,
        "low": closes - 0.5,
    })


def test_attach_labels_forward_close_correct():
    bars = _toy_bars()
    decisions = pd.DataFrame({
        "decision_id": ["d1"],
        "as_of_date": [bars["date"].iloc[2]],
        "symbol": ["SPY"],
        "engine": ["A"],
    })
    out = attach_labels(decisions, bars, None, cfg=LabelConfig(horizons=(1, 5)))
    # +1 day return
    entry = bars["close"].iloc[2]
    exit1 = bars["close"].iloc[3]
    assert abs(out["fwd_ret_1d"].iloc[0] - (exit1 / entry - 1.0)) < 1e-9
    # +5 day return
    exit5 = bars["close"].iloc[7]
    assert abs(out["fwd_ret_5d"].iloc[0] - (exit5 / entry - 1.0)) < 1e-9
    # Win labels
    assert bool(out["label_win_1d"].iloc[0]) is True


def test_attach_labels_emits_nan_when_bars_missing():
    decisions = pd.DataFrame({
        "decision_id": ["d1"],
        "as_of_date": [pd.Timestamp("2025-01-01")],
        "symbol": ["ZZZ"],     # no bars for this symbol
        "engine": ["A"],
    })
    out = attach_labels(decisions, _toy_bars(), None)
    assert pd.isna(out["fwd_ret_1d"].iloc[0])
    assert pd.isna(out["fwd_ret_5d"].iloc[0])


def test_attach_labels_merges_closed_paper_trade():
    bars = _toy_bars()
    decisions = pd.DataFrame({
        "decision_id": ["d1"],
        "as_of_date": [bars["date"].iloc[1]],
        "symbol": ["SPY"],
        "engine": ["A"],
    })
    pt = pd.DataFrame({
        "entry_date": [bars["date"].iloc[1]],
        "symbol": ["SPY"],
        "engine": ["A"],
        "status": ["closed"],
        "net_ret_pct": [1.23],
        "gross_ret_pct": [1.40],
        "days_held": [3],
    })
    out = attach_labels(decisions, bars, pt)
    assert out["realized_net_ret"].iloc[0] == 1.23
    assert out["realized_days_held"].iloc[0] == 3
    assert bool(out["label_win_realized"].iloc[0]) is True


# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------

def test_walk_forward_single_split_orders_indices():
    df = pd.DataFrame({
        "as_of_date": pd.date_range("2025-01-01", periods=500),
        "x": np.random.randn(500),
    })
    splits = list(walk_forward_splits(df))
    assert len(splits) == 1
    tr, va, te = splits[0]
    # All test indices must come after all train indices in time order
    assert df.iloc[tr]["as_of_date"].max() < df.iloc[te]["as_of_date"].min()


def test_walk_forward_returns_nothing_for_tiny_data():
    df = pd.DataFrame({
        "as_of_date": pd.date_range("2025-01-01", periods=5),
    })
    assert list(walk_forward_splits(df)) == []


def test_rolling_walk_forward_multiple_folds():
    df = pd.DataFrame({
        "as_of_date": pd.date_range("2025-01-01", periods=2000),
    })
    cfg = WalkForwardConfig(rolling=True, step_frac=0.05)
    folds = list(walk_forward_splits(df, cfg=cfg))
    assert len(folds) >= 2


def test_enough_data_tiers():
    assert enough_data_for_ml(50)["tier"] == "diagnostics_only"
    assert enough_data_for_ml(400)["tier"] == "baselines_only"
    assert enough_data_for_ml(2000)["can_train"] is True
    assert enough_data_for_ml(100, min_for_models=1000)["can_train"] is False


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------

def test_baselines_run_on_synthetic():
    n = 200
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "feature_confidence": rng.random(n),
        "regime_stress": rng.integers(0, 2, n),
        "event_risk_score": rng.random(n),
        "missing_field_count": rng.integers(0, 3, n),
        "fwd_ret_5d": rng.normal(0.001, 0.02, n),
    })
    results = run_baselines(df, label_col="fwd_ret_5d")
    names = [r.name for r in results]
    assert "b1_engine_conf" in names
    assert "ctrl_always_accept" in names
    assert all(r.n_rows == n for r in results)
    # At least control accepts everything
    always = next(r for r in results if r.name == "ctrl_always_accept")
    assert always.n_accepted == n


def test_baselines_handle_missing_label():
    df = pd.DataFrame({"feature_confidence": [0.5, 0.7]})
    results = run_baselines(df, label_col="fwd_ret_5d")
    assert len(results) == 1
    assert "missing" in results[0].notes


# ---------------------------------------------------------------------------
# Feature health
# ---------------------------------------------------------------------------

def test_feature_health_warns_on_tiny_dataset():
    df = pd.DataFrame({
        "as_of_date": pd.date_range("2025-01-01", periods=5),
        "symbol": ["SPY"] * 5,
        "decision_id": [f"d{i}" for i in range(5)],
        "feature_confidence": [0.5] * 5,
        "fwd_ret_5d": [0.01, -0.005, 0.003, 0.02, -0.01],
        "catalyst_score": [0.1, 0.4, 0.7, 0.2, 0.9],
        "event_risk_score": [0.0, 0.3, 0.6, 0.1, 0.8],
        "has_earnings_soon": [False, False, True, False, True],
    })
    report = build_feature_health(df)
    assert report.n_rows == 5
    assert any("< 200" in w for w in report.warnings)
    assert report.label_availability["fwd_ret_5d"] == 5
    # Catalyst bucket aggregation produced data
    assert len(report.pnl_by_catalyst_score_bucket) >= 1


# ---------------------------------------------------------------------------
# Advisory
# ---------------------------------------------------------------------------

def test_advisory_needs_more_data_when_small():
    a = build_advisory(
        decision_id="x", ml_score=0.9,
        data_confidence=0.9,
        catalyst_blocks=False, catalyst_reduces=False,
        n_training_rows=50, min_training_rows=1000,
    )
    assert a.suggested_action == AdvisoryAction.NEEDS_MORE_DATA


def test_advisory_avoids_when_catalyst_blocks():
    a = build_advisory(
        decision_id="x", ml_score=0.8,
        data_confidence=0.9,
        catalyst_blocks=True, catalyst_reduces=False,
        n_training_rows=2000, min_training_rows=1000,
    )
    assert a.suggested_action == AdvisoryAction.AVOID


def test_advisory_accepts_high_score():
    a = build_advisory(
        decision_id="x", ml_score=0.85,
        data_confidence=0.8,
        catalyst_blocks=False, catalyst_reduces=False,
        n_training_rows=2000, min_training_rows=1000,
    )
    assert a.suggested_action == AdvisoryAction.ACCEPT


def test_advisory_reduces_when_catalyst_nudge():
    a = build_advisory(
        decision_id="x", ml_score=0.85,
        data_confidence=0.8,
        catalyst_blocks=False, catalyst_reduces=True,
        n_training_rows=2000, min_training_rows=1000,
    )
    assert a.suggested_action == AdvisoryAction.REDUCE


# ---------------------------------------------------------------------------
# Engine C status
# ---------------------------------------------------------------------------

def test_engine_c_insufficient_data():
    r = engine_c_status(
        n_rows=50, leakage_ok=True,
        baseline_best_sharpe=0.5, ml_test_sharpe=None,
        min_training_rows=1000,
    )
    assert r.status == EngineCStatus.DISABLED_INSUFFICIENT_DATA


def test_engine_c_promoted_when_ml_beats_baseline():
    r = engine_c_status(
        n_rows=2000, leakage_ok=True,
        baseline_best_sharpe=0.3, ml_test_sharpe=0.9,
        min_training_rows=1000,
    )
    assert r.status == EngineCStatus.ACTIVE_CANDIDATE


def test_engine_c_blocked_when_baseline_wins():
    r = engine_c_status(
        n_rows=2000, leakage_ok=True,
        baseline_best_sharpe=1.0, ml_test_sharpe=0.5,
        min_training_rows=1000,
    )
    assert r.status == EngineCStatus.DISABLED_BASELINE_BEATS_ML


def test_engine_c_leakage_lockout():
    r = engine_c_status(
        n_rows=5000, leakage_ok=False,
        baseline_best_sharpe=0.3, ml_test_sharpe=1.0,
        min_training_rows=1000,
    )
    assert r.status == EngineCStatus.DISABLED_LEAKAGE
