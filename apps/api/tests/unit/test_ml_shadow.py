"""Phase ML-3 — eligibility, calibration, disagreement, comparison tests.

DB-free. Synthetic DataFrames only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from apps.api.src.ml.shadow.calibration import (
    compute_calibration,
)
from apps.api.src.ml.shadow.comparison import (
    compare_shadow_vs_baselines,
)
from apps.api.src.ml.shadow.disagreement import compute_disagreements
from apps.api.src.ml.shadow.eligibility import (
    EligibilityStatus, evaluate_eligibility,
)
from apps.api.src.ml.shadow.trainer import (
    MODEL_CAP, ModelType,
)


def _frame(n: int = 200, with_labels: bool = True, seed: int = 0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "decision_id": [f"d{i}" for i in range(n)],
        "as_of_date": pd.date_range("2025-01-01", periods=n),
        "decision_ts": pd.date_range("2025-01-01", periods=n),
        "symbol": "SPY",
        "engine": rng.choice(["A", "B"], n),
        "action": rng.choice(["enter_long", "no_fire"], n),
        "feature_confidence": rng.random(n),
        "engine_is_a": rng.integers(0, 2, n),
        "engine_is_b": rng.integers(0, 2, n),
        "engine_is_c": np.zeros(n, dtype=int),
        "regime_stress": rng.integers(0, 2, n),
        "regime_directional": rng.integers(0, 2, n),
        "regime_neutral": rng.integers(0, 2, n),
        "gates_favorable": rng.integers(0, 5, n),
        "missing_field_count": np.zeros(n, dtype=int),
        "stale_field_count": np.zeros(n, dtype=int),
        "data_confidence_bucket": rng.integers(0, 4, n),
        "catalyst_score": rng.random(n),
        "event_risk_score": rng.random(n),
        "days_to_earnings": rng.integers(0, 30, n),
        "has_earnings_soon": rng.integers(0, 2, n),
        "trade_policy_neutral": np.ones(n, dtype=int),
        "trade_policy_reduce": np.zeros(n, dtype=int),
        "trade_policy_confirm": np.zeros(n, dtype=int),
        "trade_policy_block": np.zeros(n, dtype=int),
        "trade_policy_watch": np.zeros(n, dtype=int),
        "input_rates_calm": rng.integers(0, 2, n),
        "input_vrp_supportive": rng.integers(0, 2, n),
        "input_credit_stable": rng.integers(0, 2, n),
        "input_liquidity_expanding": rng.integers(0, 2, n),
        "input_vol_elevated": rng.integers(0, 2, n),
        "input_vol_expanding": rng.integers(0, 2, n),
        "input_range_loose": rng.integers(0, 2, n),
        "input_z_score": rng.normal(0, 1, n),
        "input_atr_ratio": rng.random(n) + 0.5,
        "fwd_ret_5d": rng.normal(0.001, 0.02, n),
    })
    if with_labels:
        df["label_win_5d"] = (df["fwd_ret_5d"] > 0).astype(int)
    return df


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------

def test_eligibility_blocks_insufficient_data():
    df = _frame(n=50)
    r = evaluate_eligibility(df, min_training_rows=1000)
    assert r.ok is False
    assert r.status == EligibilityStatus.SKIPPED_INSUFFICIENT_DATA


def test_eligibility_blocks_no_labels():
    df = _frame(n=200, with_labels=False)
    r = evaluate_eligibility(df, min_training_rows=100)
    assert r.ok is False
    assert r.status == EligibilityStatus.SKIPPED_NO_LABELS


def test_eligibility_passes_with_enough_data():
    df = _frame(n=2500)
    r = evaluate_eligibility(df, min_training_rows=1000)
    assert r.ok is True
    assert r.status == EligibilityStatus.ELIGIBLE


def test_eligibility_blocks_replay_when_not_ready():
    df = _frame(n=2500)
    r = evaluate_eligibility(
        df, min_training_rows=1000,
        dataset_source="combined",
        replay_readiness_status="CALIBRATION_ONLY",
    )
    assert r.ok is False
    assert r.status == EligibilityStatus.SKIPPED_REPLAY_NOT_READY


def test_eligibility_allows_combined_when_ready():
    df = _frame(n=2500)
    r = evaluate_eligibility(
        df, min_training_rows=1000,
        dataset_source="combined",
        replay_readiness_status="READY_FOR_WEIGHTED_TEST",
    )
    assert r.ok is True


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

def test_calibration_empty():
    r = compute_calibration([], [])
    assert r.n == 0


def test_calibration_perfect_scores_produce_low_ece():
    rng = np.random.default_rng(0)
    n = 500
    y = rng.integers(0, 2, n)
    # Perfect-ish calibration: y_true mean ≈ y_score
    y_score = (y.astype(float) * 0.8 + 0.1)    # 0.1 vs 0.9 buckets
    r = compute_calibration(y, y_score, n_buckets=10)
    assert r.brier >= 0
    assert r.poor_calibration is False or r.ece < 0.25


def test_calibration_bad_scores_flagged():
    # Intentionally miscalibrated: constant 0.9 score, mean-rate ≈ 0.5
    n = 300
    y = np.random.default_rng(1).integers(0, 2, n)
    y_score = np.full(n, 0.9)
    r = compute_calibration(y, y_score, n_buckets=10,
                              poor_ece_threshold=0.10)
    assert r.poor_calibration is True
    assert r.ece > 0.10


# ---------------------------------------------------------------------------
# Disagreement
# ---------------------------------------------------------------------------

def test_disagreement_buckets_populated():
    df = pd.DataFrame({
        "action": ["enter_long"] * 30 + ["no_fire"] * 30,
        "ml_action": ["avoid"] * 15 + ["accept"] * 15 + ["accept"] * 15
                      + ["avoid"] * 15,
        "engine_confidence": [0.7] * 60,
        "ml_confidence": [0.2] * 30 + [0.8] * 30,
        "fwd_ret_5d": np.linspace(-0.01, 0.01, 60),
        "ml_reason_codes": [["cat_block"]] * 30 + [["ml_high"]] * 30,
    })
    r = compute_disagreements(df)
    assert r.total == 60
    names = [b.name for b in r.buckets]
    assert "engine_accept_ml_avoid" in names
    assert "engine_skip_ml_accept" in names


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def test_comparison_produces_winner():
    df = _frame(n=400)
    # Fake a shadow score correlated with fwd_ret_5d so ML wins
    df["__shadow_score"] = (
        (df["fwd_ret_5d"] > 0).astype(float) * 0.6 + 0.2
    )
    r = compare_shadow_vs_baselines(
        df, shadow_score_col="__shadow_score",
        label_col="label_win_5d", return_col="fwd_ret_5d",
    )
    assert r.winner in {"ml", "baseline", "tie"}
    assert r.shadow["n"] == 400


# ---------------------------------------------------------------------------
# Model cap
# ---------------------------------------------------------------------------

def test_model_cap_constant_is_ten():
    assert MODEL_CAP == 10


def test_model_type_enum_members():
    values = {m.value for m in ModelType}
    assert values == {"logistic", "ridge", "rf", "gbm"}
