"""PD-5 — training feature whitelist + non-endogenous market features."""

from __future__ import annotations

import datetime as dt
import numpy as np
import pandas as pd
import pytest

from apps.api.src.ml.features import (
    FEATURE_COLUMNS, TRAINING_FEATURE_WHITELIST,
    FEATURES_ENGINE_STATE, FEATURE_GROUPS,
)


def test_engine_state_excluded_from_training_whitelist():
    """No engine/regime/policy/gate one-hot may appear in TRAIN whitelist."""
    bad = set(TRAINING_FEATURE_WHITELIST) & set(FEATURES_ENGINE_STATE)
    assert bad == set(), f"endogenous in whitelist: {bad}"


def test_training_whitelist_subset_of_full_columns():
    assert set(TRAINING_FEATURE_WHITELIST).issubset(FEATURE_COLUMNS)


def test_market_new_features_present_in_whitelist():
    expected = {
        "ret_z_5d", "ret_z_20d", "ret_z_60d",
        "rvol_20d", "vol_of_vol_20d", "log_atr_20d",
    }
    assert expected.issubset(set(TRAINING_FEATURE_WHITELIST))


def test_feature_groups_partition_full_set():
    union: set[str] = set()
    for group in FEATURE_GROUPS.values():
        union |= set(group)
    assert union == set(FEATURE_COLUMNS), \
        f"groups don't cover FEATURE_COLUMNS: {set(FEATURE_COLUMNS) - union}"


def test_no_label_pattern_in_whitelist():
    """No future-looking column may sneak into training features."""
    forbidden = ("fwd_ret", "label_win", "label_tb",
                  "realized_", "hit_target", "hit_stop")
    for col in TRAINING_FEATURE_WHITELIST:
        for pat in forbidden:
            assert pat not in col, f"leakage column in whitelist: {col}"


def test_market_feature_helper_handles_empty_bars():
    from apps.api.src.ml.dataset import _derive_market_features
    decisions = pd.DataFrame({
        "decision_id": ["d1"],
        "as_of_date": [pd.Timestamp("2026-01-15")],
        "symbol": ["ES"],
    })
    out = _derive_market_features(decisions, pd.DataFrame())
    for col in ("ret_z_5d", "rvol_20d", "log_atr_20d"):
        assert col in out.columns
        assert pd.isna(out[col].iloc[0])


def test_market_feature_helper_computes_when_bars_present():
    from apps.api.src.ml.dataset import _derive_market_features
    n = 80
    rng = np.random.default_rng(0)
    closes = 100.0 * np.cumprod(1.0 + rng.normal(0.0005, 0.01, n))
    dates = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(n)]
    bars = pd.DataFrame({
        "date":   pd.to_datetime(dates),
        "symbol": "ES",
        "open":   closes,
        "high":   closes * 1.005,
        "low":    closes * 0.995,
        "close":  closes,
    })
    decisions = pd.DataFrame({
        "decision_id": ["d1"],
        "as_of_date":  [pd.Timestamp(dates[-1])],
        "symbol":      ["ES"],
    })
    out = _derive_market_features(decisions, bars)
    assert pd.notna(out["ret_z_5d"].iloc[0])
    assert pd.notna(out["ret_z_20d"].iloc[0])
    assert pd.notna(out["rvol_20d"].iloc[0])
    assert pd.notna(out["vol_of_vol_20d"].iloc[0])
    assert pd.notna(out["log_atr_20d"].iloc[0])


def test_trainer_default_uses_whitelist():
    """Production trainer signature should default to TRAINING whitelist."""
    import inspect
    from apps.api.src.ml.shadow.trainer import train_shadow_models
    sig = inspect.signature(train_shadow_models)
    default_feats = sig.parameters["feature_cols"].default
    # Must be the whitelist, not the full FEATURE_COLUMNS
    assert default_feats == TRAINING_FEATURE_WHITELIST
