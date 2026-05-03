"""Unit tests — E1 risk-feature ablation (no DB)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from apps.ml.dataset import DatasetBundle
from apps.ml.e1_ablation import (
    ENTANGLEMENT_RHO_THRESHOLD,
    FAIL_AUC,
    FAIL_SHARPE,
    PASS_AUC,
    PASS_SHARPE_GROSS,
    RETENTION_QUANTILE,
    RISK_PROXY_FEATURES,
    E1Result,
    classify_verdict,
    compute_spearman_label_vol,
    run_e1_ablation,
    split_features,
)


# ---------------------------------------------------------------------------
# Synthetic dataset builder
# ---------------------------------------------------------------------------


def _build_bundle(
    n_days: int = 120,
    n_symbols_per_day: int = 20,
    seed: int = 42,
    hit_rate: float = 0.55,
    alpha_signal_strength: float = 0.15,
) -> DatasetBundle:
    """Synthetic DatasetBundle mirroring historical_label row shape.

    alpha_signal_strength controls how predictive `residual_momentum_60d`
    (the kept alpha feature) is of y_hit. Use 0.0 to simulate no-alpha case.
    """
    rng = np.random.default_rng(seed)
    records: list[dict] = []
    start = dt.date(2025, 1, 6)  # Monday

    d = start
    for _day_i in range(n_days):
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        for j in range(n_symbols_per_day):
            # Risk-proxy features (correlated with each other)
            vol = float(rng.lognormal(mean=-3.0, sigma=0.4))
            atr = float(vol * 0.8 + rng.normal(0, 0.002))
            dollar_vol = float(rng.lognormal(mean=17.0, sigma=0.5))
            rm20 = float(rng.normal(0, 0.02))
            atr_pctile = float(rng.uniform(0, 1))

            # Alpha-proxy features
            rm60 = float(rng.normal(0, 0.03))
            sector_rank = float(rng.uniform(0, 1))
            trend_20 = float(rng.normal(0, 0.5))
            price_vs_sma = float(rng.normal(0, 0.15))
            composite = float(rng.uniform(0.2, 0.9))
            confidence = float(rng.uniform(0.3, 0.9))

            # Label: alpha feature drives hit probability
            logit = (
                alpha_signal_strength * rm60 * 30.0
                + alpha_signal_strength * (sector_rank - 0.5) * 1.5
                + rng.normal(0, 0.5)
            )
            p = 1.0 / (1.0 + np.exp(-logit))
            # Scale to match hit_rate
            p = float(hit_rate * 2 * p) if p > 0.5 else float(hit_rate)
            y_hit = int(rng.random() < p)

            forward_ret = float(
                rng.normal(0.001 if y_hit else -0.005, 0.02) * 100
            )

            records.append({
                "id": len(records) + 1,
                "as_of_date": d,
                "symbol": f"SYM{j:02d}",
                "action": "Buy",
                "label": 1 if y_hit else -1,
                "forward_return_pct": forward_ret,
                "barrier_n_bars": 20,
                "sector": "TECH",
                "market_trend": "uptrend",
                "vol_regime": "normal",
                "composite_score": composite,
                "confidence": confidence,
                "residual_momentum_20d": rm20,
                "residual_momentum_60d": rm60,
                "sector_relative_rank": sector_rank,
                "trend_strength_20d": trend_20,
                "price_vs_200sma": price_vs_sma,
                "atr_percent_14": atr,
                "avg_dollar_volume_20d": dollar_vol,
                "realized_vol_20d": vol,
                "atr_pctile_1y": atr_pctile,
                "y_hit": y_hit,
            })
        d += dt.timedelta(days=1)

    df = pd.DataFrame.from_records(records).sort_values("as_of_date").reset_index(drop=True)
    df["market_trend_uptrend"] = 1
    df["market_trend_sideways"] = 0
    df["market_trend_downtrend"] = 0
    df["vol_regime_low"] = 0
    df["vol_regime_normal"] = 1
    df["vol_regime_high"] = 0

    features = [
        "composite_score", "confidence",
        "residual_momentum_20d", "residual_momentum_60d",
        "sector_relative_rank", "trend_strength_20d", "price_vs_200sma",
        "atr_percent_14", "avg_dollar_volume_20d",
        "realized_vol_20d", "atr_pctile_1y",
        "market_trend_uptrend", "market_trend_sideways", "market_trend_downtrend",
        "vol_regime_low", "vol_regime_normal", "vol_regime_high",
    ]
    return DatasetBundle(df=df, features=features, target="y_hit")


# ---------------------------------------------------------------------------
# Feature drop logic
# ---------------------------------------------------------------------------


class TestSplitFeatures:
    def test_drops_all_risk_proxies(self):
        features = list(RISK_PROXY_FEATURES) + [
            "composite_score", "residual_momentum_60d", "sector_relative_rank",
        ]
        kept, dropped = split_features(features)
        assert set(dropped) == set(RISK_PROXY_FEATURES)
        assert "composite_score" in kept
        assert "residual_momentum_60d" in kept

    def test_drops_vol_regime_one_hot(self):
        features = [
            "composite_score",
            "vol_regime_low", "vol_regime_normal", "vol_regime_high",
            "market_trend_uptrend",
        ]
        kept, dropped = split_features(features)
        assert "vol_regime_low" in dropped
        assert "vol_regime_normal" in dropped
        assert "vol_regime_high" in dropped
        assert "market_trend_uptrend" in kept  # trend is NOT a risk proxy
        assert "composite_score" in kept

    def test_keeps_rm60_drops_rm20(self):
        features = ["residual_momentum_20d", "residual_momentum_60d"]
        kept, dropped = split_features(features)
        assert dropped == ["residual_momentum_20d"]
        assert kept == ["residual_momentum_60d"]

    def test_empty_features_empty_output(self):
        kept, dropped = split_features([])
        assert kept == [] and dropped == []


# ---------------------------------------------------------------------------
# Verdict classification
# ---------------------------------------------------------------------------


class TestClassifyVerdict:
    def test_pass_high_auc_and_sharpe(self):
        v, _ = classify_verdict(auc=0.58, sharpe_uplift=0.45)
        assert v == "PASS"

    def test_ambiguous_label_sizing_high_auc_low_sharpe(self):
        v, _ = classify_verdict(auc=0.56, sharpe_uplift=0.05)
        assert v == "AMBIGUOUS_LABEL_SIZING"

    def test_ambiguous_noise_near_pass_auc(self):
        v, _ = classify_verdict(auc=0.52, sharpe_uplift=0.10)
        assert v == "AMBIGUOUS_NOISE"

    def test_fail_both_low(self):
        v, action = classify_verdict(auc=0.502, sharpe_uplift=-0.20)
        assert v == "FAIL"
        assert "ABANDON" in action

    def test_boundary_exact_pass_thresholds(self):
        v, _ = classify_verdict(auc=PASS_AUC, sharpe_uplift=PASS_SHARPE_GROSS)
        assert v == "PASS"

    def test_boundary_exact_fail_thresholds(self):
        v, _ = classify_verdict(auc=FAIL_AUC, sharpe_uplift=FAIL_SHARPE - 0.01)
        assert v == "FAIL"


# ---------------------------------------------------------------------------
# Sonnet D1 Spearman
# ---------------------------------------------------------------------------


class TestSpearmanDiagnostic:
    def test_returns_none_if_column_missing(self):
        df = pd.DataFrame({"y_hit": [0, 1, 0, 1]})
        rho, p = compute_spearman_label_vol(df)
        assert rho is None and p is None

    def test_degenerate_y_hit_returns_none(self):
        df = pd.DataFrame({
            "y_hit": [1] * 50,
            "realized_vol_20d": np.linspace(0.01, 0.05, 50),
        })
        rho, p = compute_spearman_label_vol(df)
        assert rho is None

    def test_positive_correlation_detected(self):
        n = 200
        rng = np.random.default_rng(42)
        vol = rng.uniform(0.01, 0.05, n)
        y = (vol > np.median(vol)).astype(int)   # perfect rank correlation
        df = pd.DataFrame({"y_hit": y, "realized_vol_20d": vol})
        rho, p = compute_spearman_label_vol(df)
        assert rho is not None and rho > 0.5

    def test_entanglement_threshold_is_20pct(self):
        assert ENTANGLEMENT_RHO_THRESHOLD == 0.20


# ---------------------------------------------------------------------------
# End-to-end (fast — synthetic data, full pipeline)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestEndToEnd:
    def test_full_run_with_alpha_signal(self):
        bundle = _build_bundle(n_days=120, alpha_signal_strength=0.4)
        result = run_e1_ablation(bundle)
        assert isinstance(result, E1Result)
        assert len(result.folds) == 5
        assert result.calibration_applied is False
        for rf in RISK_PROXY_FEATURES:
            assert rf not in result.features_used
            assert rf in result.features_dropped
        assert result.n_lockbox_rows_untouched > 0
        # no NaN in any fold metrics
        for f in result.folds:
            assert not np.isnan(f.auc)
            assert not np.isnan(f.filtered_sharpe)

    def test_deterministic_seed(self):
        bundle = _build_bundle(n_days=80, seed=123)
        r1 = run_e1_ablation(bundle)
        bundle2 = _build_bundle(n_days=80, seed=123)
        r2 = run_e1_ablation(bundle2)
        assert r1.cv_auc_oof == r2.cv_auc_oof
        assert r1.cv_sharpe_uplift_oof == r2.cv_sharpe_uplift_oof
        assert [f.auc for f in r1.folds] == [f.auc for f in r2.folds]

    def test_lockbox_untouched_shape(self):
        bundle = _build_bundle(n_days=100)
        result = run_e1_ablation(bundle)
        # Lockbox is 20% of dates; CV is 80%
        total_days = len({r for r in bundle.df["as_of_date"]})
        assert result.n_lockbox_rows_untouched > 0
        # Total rows check: CV + lockbox == total
        assert result.n_cv_rows + result.n_lockbox_rows_untouched == len(bundle.df)


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------


class TestConstants:
    def test_retention_is_80pct(self):
        assert RETENTION_QUANTILE == 0.20

    def test_risk_proxy_list(self):
        assert "realized_vol_20d" in RISK_PROXY_FEATURES
        assert "atr_percent_14" in RISK_PROXY_FEATURES
        assert "avg_dollar_volume_20d" in RISK_PROXY_FEATURES
        assert "residual_momentum_20d" in RISK_PROXY_FEATURES
        assert "atr_pctile_1y" in RISK_PROXY_FEATURES
        # Non-risk features must NOT be in the list
        assert "residual_momentum_60d" not in RISK_PROXY_FEATURES
        assert "composite_score" not in RISK_PROXY_FEATURES
        assert "sector_relative_rank" not in RISK_PROXY_FEATURES

    def test_codex_thresholds(self):
        assert PASS_AUC == 0.53
        assert PASS_SHARPE_GROSS == 0.25
        assert FAIL_AUC == 0.505
        assert FAIL_SHARPE == -0.10
