"""Pattern discovery: honest bucketing, small-sample guard, lift calc."""

from __future__ import annotations

import numpy as np
import pandas as pd

from apps.api.src.ml.patterns import (
    MIN_SAMPLE, discover_patterns, PatternReport,
)


def _toy_df(n: int = 300, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "decision_id": [f"d{i}" for i in range(n)],
        "as_of_date": pd.date_range("2025-01-01", periods=n),
        "symbol": rng.choice(["SPY", "QQQ", "AAPL"], n),
        "engine": rng.choice(["A", "B"], n),
        "action": rng.choice(["enter_long", "skip"], n),
        "fwd_ret_5d": rng.normal(0.001, 0.02, n),
        "catalyst_score": rng.random(n),
        "event_risk_score": rng.random(n),
        "has_earnings_soon": rng.integers(0, 2, n).astype(bool),
        "trade_policy_neutral": rng.integers(0, 2, n),
        "trade_policy_reduce": np.zeros(n, dtype=int),
        "trade_policy_confirm": np.zeros(n, dtype=int),
        "trade_policy_block": np.zeros(n, dtype=int),
        "trade_policy_watch": np.zeros(n, dtype=int),
        "feature_confidence": rng.random(n),
        "missing_field_count": rng.integers(0, 3, n),
        "stale_field_count": np.zeros(n, dtype=int),
        "regime_stress": rng.integers(0, 2, n),
        "regime_directional": rng.integers(0, 2, n),
        "regime_neutral": rng.integers(0, 2, n),
        "gates_favorable": rng.integers(0, 5, n),
        "input_rates_calm": rng.integers(0, 2, n),
        "input_credit_stable": rng.integers(0, 2, n),
        "input_liquidity_expanding": rng.integers(0, 2, n),
        "input_vrp_supportive": rng.integers(0, 2, n),
        "input_vol_elevated": rng.integers(0, 2, n),
        "input_vol_expanding": rng.integers(0, 2, n),
        "input_range_loose": rng.integers(0, 2, n),
    })


def test_returns_empty_report_when_no_labels():
    df = _toy_df().drop(columns=["fwd_ret_5d"])
    r = discover_patterns(df)
    assert r.n_rows == 0
    assert r.buckets == []


def test_small_sample_flagged_low_confidence():
    df = _toy_df(n=20)
    r = discover_patterns(df)
    # Every bucket should be low_confidence because n<<MIN_SAMPLE
    assert all(b.low_confidence for b in r.buckets)
    assert r.low_confidence_excluded > 0


def test_large_sample_ranks_positives_and_negatives():
    df = _toy_df(n=600, seed=1)
    # Inject a strong signal: regime_directional == 1 → +0.05 return
    mask = df["regime_directional"].astype(bool)
    df.loc[mask, "fwd_ret_5d"] = df.loc[mask, "fwd_ret_5d"] + 0.05
    r = discover_patterns(df)
    assert r.n_rows == 600
    # At least one positive pattern found
    assert len(r.positive_patterns) >= 1
    # Each positive pattern has measured lift and isn't low confidence
    for b in r.positive_patterns:
        assert b.low_confidence is False
        assert b.n >= MIN_SAMPLE


def test_lift_against_control_computed():
    df = _toy_df(n=300)
    r = discover_patterns(df)
    # lift = mean - control_mean ; pick any bucket and verify arithmetic
    for b in r.buckets:
        if b.n == 0:
            continue
        assert abs((b.mean_return - r.control_mean) - b.lift_vs_control) < 1e-9


def test_report_to_dict_stable_schema():
    df = _toy_df(n=300)
    d = discover_patterns(df).to_dict()
    assert set(d.keys()) >= {
        "n_rows", "return_col", "control_mean", "buckets",
        "positive_patterns", "negative_patterns",
        "pattern_warnings", "low_confidence_excluded", "min_sample",
    }
