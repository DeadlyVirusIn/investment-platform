"""Unit tests — Phase 2 conditional pipeline (no DB)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from apps.ml.dataset import DatasetBundle
from apps.ml.phase2_pipeline import (
    ALPHA158_BASE_COLS,
    ALPHA158_SUFFIXES,
    PHASE2_FRESH_FRAC,
    PROCEED_VERDICTS,
    PROCEED_VERDICTS_WITH_FORCE,
    Phase2GateBlocked,
    Phase2Result,
    asymmetric_barrier_proxy,
    bet_size_probability,
    build_alpha158_block,
    check_e1_gate,
    run_phase2_pipeline,
    split_cv_train_and_fresh_holdout,
)


# ---------------------------------------------------------------------------
# Synthetic bundle
# ---------------------------------------------------------------------------


def _build_bundle(
    n_days: int = 150,
    n_symbols_per_day: int = 20,
    seed: int = 42,
    alpha_signal_strength: float = 0.4,
) -> DatasetBundle:
    rng = np.random.default_rng(seed)
    records: list[dict] = []
    d = dt.date(2025, 1, 6)

    for _ in range(n_days):
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        for j in range(n_symbols_per_day):
            vol = float(rng.lognormal(mean=-3.0, sigma=0.4))
            atr = float(vol * 0.8 + rng.normal(0, 0.002))
            dollar_vol = float(rng.lognormal(mean=17.0, sigma=0.5))
            rm20 = float(rng.normal(0, 0.02))
            atr_pctile = float(rng.uniform(0, 1))

            rm60 = float(rng.normal(0, 0.03))
            sector_rank = float(rng.uniform(0, 1))
            trend_20 = float(rng.normal(0, 0.5))
            price_vs_sma = float(rng.normal(0, 0.15))
            composite = float(rng.uniform(0.2, 0.9))
            confidence = float(rng.uniform(0.3, 0.9))

            logit = alpha_signal_strength * rm60 * 30.0 + rng.normal(0, 0.5)
            p = 1.0 / (1.0 + np.exp(-logit))
            y_hit = int(rng.random() < p)

            forward_ret = float(
                rng.normal(0.002 if y_hit else -0.004, 0.02) * 100
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
# Gate check
# ---------------------------------------------------------------------------


class TestGate:
    def test_pass_verdict_proceeds(self):
        ok, _ = check_e1_gate({"verdict": "PASS"})
        assert ok

    def test_fail_verdict_blocks(self):
        ok, reason = check_e1_gate({"verdict": "FAIL"})
        assert not ok
        assert "FAIL" in reason

    def test_ambiguous_blocks_without_force(self):
        ok, _ = check_e1_gate({"verdict": "AMBIGUOUS_LABEL_SIZING"})
        assert not ok

    def test_ambiguous_proceeds_with_force(self):
        ok, _ = check_e1_gate(
            {"verdict": "AMBIGUOUS_LABEL_SIZING"}, force=True,
        )
        assert ok

    def test_unknown_verdict_blocks(self):
        ok, _ = check_e1_gate({"verdict": "SOMETHING_NEW"})
        assert not ok
        ok2, _ = check_e1_gate({"verdict": "SOMETHING_NEW"}, force=True)
        assert not ok2  # force only extends to AMBIGUOUS_*

    def test_proceed_sets_are_disjoint_superset(self):
        assert PROCEED_VERDICTS <= PROCEED_VERDICTS_WITH_FORCE


# ---------------------------------------------------------------------------
# Alpha158 block
# ---------------------------------------------------------------------------


class TestAlpha158Block:
    def test_adds_rank_and_zscore_per_base_col(self):
        bundle = _build_bundle(n_days=20)
        df, added = build_alpha158_block(bundle.df)
        expected_count = len(ALPHA158_BASE_COLS) * len(ALPHA158_SUFFIXES)
        assert len(added) == expected_count
        for col in ALPHA158_BASE_COLS:
            assert f"{col}_xs_rank" in df.columns
            assert f"{col}_xs_zscore" in df.columns

    def test_rank_in_unit_interval(self):
        bundle = _build_bundle(n_days=10)
        df, _ = build_alpha158_block(bundle.df)
        for col in ALPHA158_BASE_COLS:
            rc = df[f"{col}_xs_rank"]
            assert rc.min() > 0 and rc.max() <= 1.0

    def test_zscore_centered_per_day(self):
        bundle = _build_bundle(n_days=10, n_symbols_per_day=25)
        df, _ = build_alpha158_block(bundle.df)
        # Each day's zscore should approximately sum to zero
        for col in ALPHA158_BASE_COLS:
            daily_sum = df.groupby("as_of_date")[f"{col}_xs_zscore"].sum()
            assert daily_sum.abs().max() < 1e-6

    def test_missing_base_col_is_skipped(self):
        bundle = _build_bundle(n_days=10)
        df = bundle.df.drop(columns=["composite_score"])
        out, added = build_alpha158_block(df)
        assert "composite_score_xs_rank" not in added
        # other base cols still added
        assert "residual_momentum_60d_xs_rank" in out.columns


# ---------------------------------------------------------------------------
# Asymmetric barrier proxy
# ---------------------------------------------------------------------------


class TestAsymmetricBarrier:
    def test_proxy_adds_column(self):
        bundle = _build_bundle(n_days=20)
        out = asymmetric_barrier_proxy(bundle.df)
        assert "y_hit_asym" in out.columns
        assert out["y_hit_asym"].isin([0, 1]).all()

    def test_positive_forward_return_is_win(self):
        df = pd.DataFrame({
            "y_hit": [1, 0, 1, 0],
            "forward_return_pct": [3.0, -2.0, 1.5, 0.5],
        })
        out = asymmetric_barrier_proxy(df)
        assert out["y_hit_asym"].tolist() == [1, 0, 1, 1]

    def test_missing_forward_return_raises(self):
        df = pd.DataFrame({"y_hit": [0, 1]})
        with pytest.raises(ValueError):
            asymmetric_barrier_proxy(df)


# ---------------------------------------------------------------------------
# Bet sizing (AFML Ch.10)
# ---------------------------------------------------------------------------


class TestBetSizing:
    def test_half_probability_is_zero_size(self):
        out = bet_size_probability(np.array([0.5]))
        assert abs(out[0]) < 1e-6

    def test_monotonic_in_probability(self):
        probs = np.array([0.3, 0.5, 0.7, 0.9])
        sizes = bet_size_probability(probs)
        for i in range(len(sizes) - 1):
            assert sizes[i] <= sizes[i + 1]

    def test_long_only_clips_to_non_negative(self):
        out = bet_size_probability(np.array([0.1, 0.2, 0.3]), long_only=True)
        assert (out >= 0).all()

    def test_range_in_zero_one_long_only(self):
        rng = np.random.default_rng(42)
        p = rng.uniform(0.01, 0.99, 1000)
        sizes = bet_size_probability(p, long_only=True)
        assert sizes.min() >= 0.0
        assert sizes.max() <= 1.0

    def test_range_in_minus_one_one_not_long_only(self):
        rng = np.random.default_rng(42)
        p = rng.uniform(0.01, 0.99, 1000)
        sizes = bet_size_probability(p, long_only=False)
        assert sizes.min() >= -1.0
        assert sizes.max() <= 1.0

    def test_extreme_proba_does_not_explode(self):
        # Test clipping against eps
        out = bet_size_probability(np.array([0.0, 1.0]))
        assert np.isfinite(out).all()


# ---------------------------------------------------------------------------
# Fresh-forward split
# ---------------------------------------------------------------------------


class TestFreshForwardSplit:
    def test_fresh_is_chronologically_later(self):
        bundle = _build_bundle(n_days=50)
        train, fresh = split_cv_train_and_fresh_holdout(bundle.df)
        assert train["as_of_date"].max() < fresh["as_of_date"].min()

    def test_fresh_fraction_preserved(self):
        bundle = _build_bundle(n_days=100)
        train, fresh = split_cv_train_and_fresh_holdout(bundle.df)
        total_dates = bundle.df["as_of_date"].nunique()
        fresh_dates = fresh["as_of_date"].nunique()
        assert 0.20 <= fresh_dates / total_dates <= 0.30

    def test_empty_df_raises(self):
        empty = pd.DataFrame({"as_of_date": pd.to_datetime([])})
        with pytest.raises(ValueError):
            split_cv_train_and_fresh_holdout(empty)


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestEndToEnd:
    def test_full_pipeline_on_pass_verdict(self):
        bundle = _build_bundle(n_days=180, alpha_signal_strength=0.5)
        e1 = {"verdict": "PASS"}
        result = run_phase2_pipeline(bundle, e1)
        assert isinstance(result, Phase2Result)
        assert result.gate_passed is True
        assert result.calibration_applied is False
        assert result.lockbox_rows_untouched > 0
        # CV train + fresh + lockbox = total rows
        assert (
            result.cv_train_rows + result.fresh_holdout_rows
            + result.lockbox_rows_untouched == len(bundle.df)
        )
        assert len(result.features_added_alpha158) > 0
        assert "y_hit_asym" not in result.features_used  # target, not feature

    def test_fail_verdict_raises_gate_blocked(self):
        bundle = _build_bundle(n_days=180)
        with pytest.raises(Phase2GateBlocked):
            run_phase2_pipeline(bundle, {"verdict": "FAIL"})

    def test_ambiguous_requires_force(self):
        bundle = _build_bundle(n_days=180)
        with pytest.raises(Phase2GateBlocked):
            run_phase2_pipeline(bundle, {"verdict": "AMBIGUOUS_NOISE"})
        # With force=True, should proceed
        res = run_phase2_pipeline(
            bundle, {"verdict": "AMBIGUOUS_NOISE"}, force=True,
        )
        assert res.gate_passed is True

    def test_deterministic_seed(self):
        b1 = _build_bundle(n_days=140, seed=99)
        b2 = _build_bundle(n_days=140, seed=99)
        r1 = run_phase2_pipeline(b1, {"verdict": "PASS"})
        r2 = run_phase2_pipeline(b2, {"verdict": "PASS"})
        assert r1.fresh_auc_original_label == r2.fresh_auc_original_label
        assert (
            r1.fresh_bet_sizing_metrics["sized_sharpe"]
            == r2.fresh_bet_sizing_metrics["sized_sharpe"]
        )

    def test_lockbox_split_preserved(self):
        bundle = _build_bundle(n_days=180)
        result = run_phase2_pipeline(bundle, {"verdict": "PASS"})
        # Lockbox should be 20% of dates
        total = bundle.df["as_of_date"].nunique()
        # We can't easily check exact rows here without re-splitting, but
        # n_lockbox_rows_untouched should be roughly 20% of total rows.
        assert result.lockbox_rows_untouched >= int(len(bundle.df) * 0.15)

    def test_phase2_fresh_frac_constant(self):
        assert PHASE2_FRESH_FRAC == 0.25
