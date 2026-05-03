"""Unit tests — asymmetric barrier math + label-version compare logic."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from apps.api.src.domain.ml.backfill_service import (
    BARRIER_SIGMA,
    compute_triple_barrier_prices,
)
from scripts.compare_label_versions import _classify_verdict, build_memo


# ---------------------------------------------------------------------------
# compute_triple_barrier_prices — symmetric and asymmetric math
# ---------------------------------------------------------------------------


class TestComputeTripleBarrierPrices:
    def test_symmetric_default_matches_legacy(self):
        """Default (pt_sigma=BARRIER_SIGMA, sl_sigma=BARRIER_SIGMA) gives
        symmetric barrier equal to the original `_compute_barrier`."""
        entry = Decimal("100")
        rv = Decimal("0.02")
        pt, sl = compute_triple_barrier_prices(entry, rv, 20)
        pt_move = pt - entry
        sl_move = entry - sl
        assert pt_move == sl_move  # symmetric

    def test_asymmetric_pt2_sl1_stop_is_tighter(self):
        entry = Decimal("100")
        rv = Decimal("0.02")
        pt, sl = compute_triple_barrier_prices(
            entry, rv, 20,
            pt_sigma=Decimal("2.0"), sl_sigma=Decimal("1.0"),
        )
        pt_move = pt - entry
        sl_move = entry - sl
        # PT 2σ, SL 1σ → SL is HALF the distance from entry that PT is
        assert pt_move == 2 * sl_move

    def test_above_entry_always(self):
        """Profit target must be above entry price for any positive sigma."""
        entry = Decimal("50")
        pt, sl = compute_triple_barrier_prices(
            entry, Decimal("0.015"), 20,
            pt_sigma=Decimal("2.0"), sl_sigma=Decimal("1.0"),
        )
        assert pt > entry
        assert sl < entry

    def test_scales_with_sqrt_bars(self):
        """Barrier width scales with sqrt(n_bars/252) per Brownian motion."""
        entry = Decimal("100")
        rv = Decimal("0.02")
        pt20, sl20 = compute_triple_barrier_prices(entry, rv, 20)
        pt80, sl80 = compute_triple_barrier_prices(entry, rv, 80)
        move_20 = pt20 - entry
        move_80 = pt80 - entry
        # sqrt(80/20) = 2 → barrier 2x wider at 80 bars
        ratio = move_80 / move_20
        assert abs(float(ratio) - 2.0) < 1e-3

    def test_backfill_sigma_is_2(self):
        assert BARRIER_SIGMA == Decimal("2.0")


# ---------------------------------------------------------------------------
# _classify_verdict — old vs new recommendation
# ---------------------------------------------------------------------------


class TestClassifyVerdict:
    def test_new_passes_continue(self):
        tag, _ = _classify_verdict(
            "PASS", old_auc=0.50, new_auc=0.55,
            old_uplift=-1.4, new_uplift=0.30,
        )
        assert tag == "CONTINUE"

    def test_fail_but_auc_improved_materially(self):
        tag, _ = _classify_verdict(
            "FAIL", old_auc=0.503, new_auc=0.515,
            old_uplift=-1.4, new_uplift=-1.2,
        )
        assert tag == "OPTIONAL_ALPHA158"

    def test_fail_uplift_materially_improved(self):
        tag, _ = _classify_verdict(
            "FAIL", old_auc=0.503, new_auc=0.504,
            old_uplift=-1.4, new_uplift=-0.5,   # +0.9 improvement
        )
        assert tag == "OPTIONAL_ALPHA158"

    def test_fail_no_improvement_abandon(self):
        tag, _ = _classify_verdict(
            "FAIL", old_auc=0.503, new_auc=0.506,
            old_uplift=-1.4, new_uplift=-1.3,   # +0.1 - not material
        )
        assert tag == "ABANDON"

    def test_fail_worse_abandon(self):
        tag, _ = _classify_verdict(
            "FAIL", old_auc=0.503, new_auc=0.490,
            old_uplift=-1.4, new_uplift=-1.8,
        )
        assert tag == "ABANDON"


# ---------------------------------------------------------------------------
# build_memo smoke test
# ---------------------------------------------------------------------------


def _fake_result(
    verdict: str, auc: float, uplift: float, spearman: float,
    fold_uplifts: list[float] | None = None,
    fold_aucs: list[float] | None = None,
) -> dict:
    folds = []
    if fold_uplifts is None:
        fold_uplifts = [uplift] * 5
    if fold_aucs is None:
        fold_aucs = [auc] * 5
    for i, (u, a) in enumerate(zip(fold_uplifts, fold_aucs)):
        folds.append({
            "fold": i, "auc": a, "sharpe_uplift": u,
            "filtered_sharpe": 0.0, "baseline_sharpe": 0.0,
            "retention_frac": 0.8,
        })
    return {
        "experiment": f"E1 {verdict}",
        "verdict": verdict,
        "metrics": {
            "cv_auc_oof": auc,
            "cv_sharpe_uplift_oof": uplift,
            "cv_filtered_sharpe_oof": 0.5,
            "cv_baseline_sharpe_oof": 2.0,
            "bailey_dsr": 0.0,
            "retention_frac": 0.8,
        },
        "diagnostic_D1_sonnet": {
            "spearman_label_vs_realized_vol_20d": spearman,
            "barrier_structurally_entangled": abs(spearman) > 0.20,
        },
        "n_cv_rows": 3472,
        "n_lockbox_rows_untouched": 963,
        "proba_stats": {
            "mean": 0.28, "std": 0.024, "quantile_20_threshold": 0.258,
        },
        "folds": folds,
    }


class TestBuildMemo:
    def test_memo_contains_all_sections(self):
        old = _fake_result("FAIL", auc=0.5033, uplift=-1.4425, spearman=-0.2001)
        new = _fake_result("PASS", auc=0.55, uplift=0.35, spearman=-0.10)
        memo = build_memo(old, new)
        assert "Old vs New Label Comparison" in memo
        assert "Headline comparison" in memo
        assert "Sonnet D1" in memo
        assert "Per-fold" in memo
        assert "Decision recommendation" in memo
        assert "CONTINUE" in memo

    def test_reduced_entanglement_detected(self):
        old = _fake_result("FAIL", 0.50, -1.4, spearman=-0.30)
        new = _fake_result("FAIL", 0.52, -0.5, spearman=-0.10)
        memo = build_memo(old, new)
        assert "REDUCED vol-entanglement" in memo

    def test_unchanged_entanglement_detected(self):
        old = _fake_result("FAIL", 0.50, -1.4, spearman=-0.20)
        new = _fake_result("FAIL", 0.50, -1.4, spearman=-0.25)
        memo = build_memo(old, new)
        assert "did NOT reduce" in memo or "unchanged" in memo.lower()

    def test_per_fold_stability_improved(self):
        old = _fake_result(
            "FAIL", 0.50, -1.0, -0.2,
            fold_uplifts=[-1.6, -1.6, 0.3, 1.2, 0.0],  # wide spread
        )
        new = _fake_result(
            "FAIL", 0.51, -0.3, -0.1,
            fold_uplifts=[-0.3, -0.4, -0.2, -0.3, -0.3],  # tight
        )
        memo = build_memo(old, new)
        assert "REDUCED per-fold uplift volatility" in memo

    def test_verdict_abandon_path_shown(self):
        old = _fake_result("FAIL", 0.50, -1.44, -0.20)
        new = _fake_result("FAIL", 0.502, -1.42, -0.19)
        memo = build_memo(old, new)
        assert "ABANDON" in memo

    def test_memo_handles_missing_folds(self):
        old = _fake_result("FAIL", 0.50, -1.44, -0.20)
        new = {
            "verdict": "FAIL",
            "metrics": {"cv_auc_oof": 0.50, "cv_sharpe_uplift_oof": -1.4},
            "diagnostic_D1_sonnet": {"spearman_label_vs_realized_vol_20d": None},
            "folds": [],
        }
        memo = build_memo(old, new)
        assert "Per-fold detail" in memo
