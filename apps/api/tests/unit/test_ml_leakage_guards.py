"""Leakage guards MUST fail loudly on common mistakes."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from apps.api.src.ml.features import FEATURE_COLUMNS, is_forbidden_feature_name
from apps.api.src.ml.validation import (
    LeakageError, LeakageReport, validate_no_leakage,
)


def _synthetic_frame() -> pd.DataFrame:
    n = 20
    return pd.DataFrame({
        "decision_id": [f"d{i}" for i in range(n)],
        "as_of_date": pd.date_range("2025-01-01", periods=n),
        "decision_ts": pd.date_range("2025-01-01", periods=n),
        "symbol": ["SPY"] * n,
        "engine_is_a": np.random.randint(0, 2, n),
        "engine_is_b": np.random.randint(0, 2, n),
        "engine_is_c": np.zeros(n, dtype=int),
        "regime_stress": np.random.randint(0, 2, n),
        "regime_directional": np.random.randint(0, 2, n),
        "regime_neutral": np.random.randint(0, 2, n),
        "gates_favorable": np.random.randint(0, 5, n),
        "feature_confidence": np.random.rand(n),
        "missing_field_count": np.zeros(n, dtype=int),
        "stale_field_count": np.zeros(n, dtype=int),
        "data_confidence_bucket": np.random.randint(0, 4, n),
        "catalyst_score": np.random.rand(n),
        "event_risk_score": np.random.rand(n),
        "days_to_earnings": np.random.randint(0, 30, n),
        "has_earnings_soon": np.random.randint(0, 2, n),
        "trade_policy_neutral": np.ones(n, dtype=int),
        "trade_policy_reduce": np.zeros(n, dtype=int),
        "trade_policy_confirm": np.zeros(n, dtype=int),
        "trade_policy_block": np.zeros(n, dtype=int),
        "trade_policy_watch": np.zeros(n, dtype=int),
        "input_rates_calm": np.random.randint(0, 2, n),
        "input_vrp_supportive": np.random.randint(0, 2, n),
        "input_credit_stable": np.random.randint(0, 2, n),
        "input_liquidity_expanding": np.random.randint(0, 2, n),
        "input_vol_elevated": np.random.randint(0, 2, n),
        "input_vol_expanding": np.random.randint(0, 2, n),
        "input_range_loose": np.random.randint(0, 2, n),
        "input_z_score": np.random.randn(n),
        "input_atr_ratio": np.random.rand(n) + 0.5,
        # labels — MUST stay outside FEATURE_COLUMNS
        "fwd_ret_5d": np.random.randn(n) * 0.01,
        "label_win_5d": np.random.randint(0, 2, n),
    })


def test_forbidden_patterns_detected():
    assert is_forbidden_feature_name("fwd_ret_5d")
    assert is_forbidden_feature_name("realized_net_ret")
    assert is_forbidden_feature_name("exit_price")
    assert is_forbidden_feature_name("pnl_dollar")
    assert is_forbidden_feature_name("hit_target")
    assert is_forbidden_feature_name("max_adverse_excursion")
    assert not is_forbidden_feature_name("feature_confidence")
    assert not is_forbidden_feature_name("catalyst_score")


def test_clean_dataset_passes():
    df = _synthetic_frame()
    report = validate_no_leakage(df, strict=True)
    assert report.ok
    assert report.violations == []
    # Label columns present in frame but not in FEATURE_COLUMNS is fine —
    # validator should report forbidden-but-excluded (harmless).
    assert "fwd_ret_5d" in report.forbidden_but_excluded


def test_raises_when_outcome_column_is_declared_feature():
    bad_cols = FEATURE_COLUMNS + ("realized_net_ret",)
    df = _synthetic_frame()
    df["realized_net_ret"] = 0.0
    with pytest.raises(LeakageError):
        validate_no_leakage(df, feature_cols=bad_cols, strict=True)


def test_soft_mode_returns_report_without_raising():
    bad_cols = FEATURE_COLUMNS + ("pnl_dollar",)
    df = _synthetic_frame()
    df["pnl_dollar"] = 0.0
    r: LeakageReport = validate_no_leakage(
        df, feature_cols=bad_cols, strict=False,
    )
    assert r.ok is False
    assert any("pnl_dollar" in v for v in r.violations)


def test_flags_missing_timestamp_column():
    df = _synthetic_frame().drop(columns=["as_of_date", "decision_ts"])
    r = validate_no_leakage(df, strict=False)
    assert any("decision_ts" in v or "as_of_date" in v for v in r.violations)
