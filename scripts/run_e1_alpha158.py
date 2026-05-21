"""One-shot alpha158 verification on top of asymmetric label.

Strict scope per 2026-04-21 decision:
  - Label: asymmetric (PT=2, SL=1)  → uses engine_version :asym_2_1
  - Features: E1 risk-feature ablation PLUS alpha158-style cross-sectional
    (rank-within-day + z-score-within-day) for 5 base alpha columns.
  - Everything else identical to E1: same CV splits, same lockbox isolation,
    same retention target (top 80% quantile), same LightGBM hyperparameters.

Gates (Codex R3, unchanged):
  - PASS      if AUC >= 0.53 AND Sharpe uplift >= 0.25
  - BORDERLINE (AUC in [0.525, 0.53)) → **ABANDON** per user one-shot rule
  - FAIL     (AUC <= 0.525 OR uplift < 0) → ABANDON

No iteration. No second attempts. No tuning.

Usage::

    python -m scripts.run_e1_alpha158
    python -m scripts.run_e1_alpha158 --engine-version "stock_swing_v1:...:asym_2_1"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION
from apps.ml.dataset import DatasetBundle, load_dataset
from apps.ml.e1_ablation import (
    FAIL_AUC,
    FAIL_SHARPE,
    PASS_AUC,
    PASS_SHARPE_GROSS,
    memo_path as memo_path_fn,
    result_path as result_path_fn,
    run_e1_ablation,
    write_json,
    write_memo,
)
from apps.ml.phase2_pipeline import build_alpha158_block


# BORDERLINE band per user one-shot spec
BORDERLINE_AUC_LOW: float = 0.525


def classify_final_verdict(auc: float, sharpe_uplift: float) -> tuple[str, str]:
    """PASS / ABANDON one-shot classifier.

    One-shot rule: BORDERLINE collapses to ABANDON. No iterative tuning.
    """
    if auc >= PASS_AUC and sharpe_uplift >= PASS_SHARPE_GROSS:
        return "PASS", (
            "Alpha158 cross-sectional block lifted model above both gates "
            "(AUC >= 0.53 AND Sharpe uplift >= 0.25). Continue to Phase 2."
        )
    if BORDERLINE_AUC_LOW <= auc < PASS_AUC:
        return "ABANDON", (
            f"BORDERLINE result (AUC={auc:.4f} in [0.525, 0.53)). Per "
            "one-shot rule no second attempts permitted — ABANDON."
        )
    if sharpe_uplift < 0:
        return "ABANDON", (
            f"Sharpe uplift negative (uplift={sharpe_uplift:+.4f}). Signal "
            "does not produce trading utility even with cross-sectional "
            "features — ABANDON."
        )
    return "ABANDON", (
        f"Below BORDERLINE (AUC={auc:.4f} < 0.525). No alpha signal "
        "survives one-shot cross-sectional feature verification — ABANDON."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--engine-version", type=str,
        default=f"{MODEL_VERSION}:asym_2_1",
        help="label version (default: asymmetric)",
    )
    parser.add_argument("--suffix", type=str, default="_asym_alpha158")
    args = parser.parse_args()

    logger.info(
        "[e1.alpha158] one-shot verification engine_version={}",
        args.engine_version,
    )
    bundle = load_dataset(engine_version=args.engine_version)

    # --- Add alpha158 cross-sectional block on top of existing features ---
    augmented_df, added = build_alpha158_block(bundle.df)
    new_features = list(bundle.features) + added
    bundle = DatasetBundle(
        df=augmented_df, features=new_features, target=bundle.target,
    )
    logger.info(
        "[e1.alpha158] original_features={} + alpha158={} = {} total",
        len(bundle.features) - len(added), len(added), len(bundle.features),
    )
    logger.info("[e1.alpha158] alpha158 features added: {}", added)

    # --- Run E1 (same CV, same lockbox split, same LGB params) ---
    result = run_e1_ablation(bundle)

    json_p = write_json(result, result_path_fn(args.suffix))
    memo_p = write_memo(result, memo_path_fn(args.suffix))

    # --- One-shot final verdict ---
    final_verdict, explanation = classify_final_verdict(
        result.cv_auc_oof, result.cv_sharpe_uplift_oof,
    )

    # Print plain-ASCII report (avoid Windows cp1252 issues)
    print()
    print("=" * 72)
    print("ONE-SHOT ALPHA158 VERIFICATION — RESULTS")
    print("=" * 72)
    print(f"Engine version:          {args.engine_version}")
    print(f"Features total:          {len(bundle.features)}")
    print(f"Alpha158 added:          {len(added)}")
    print(f"CV rows:                 {result.n_cv_rows}")
    print(f"Lockbox rows UNTOUCHED:  {result.n_lockbox_rows_untouched}")
    print("-" * 72)
    print(f"CV AUC (OOF):            {result.cv_auc_oof:.4f}")
    print(f"CV Sharpe uplift:        {result.cv_sharpe_uplift_oof:+.4f}")
    print(f"CV filtered Sharpe:      {result.cv_filtered_sharpe_oof:.4f}")
    print(f"CV baseline Sharpe:      {result.cv_baseline_sharpe_oof:.4f}")
    print(
        f"Spearman(y_hit, vol):    "
        f"{result.spearman_label_vs_vol20d:+.4f}"
        if result.spearman_label_vs_vol20d is not None else
        "Spearman(y_hit, vol):    n/a"
    )
    print("-" * 72)
    print("Gates:")
    print(
        f"  PASS AUC >= {PASS_AUC}          -> "
        f"{'PASS' if result.cv_auc_oof >= PASS_AUC else 'FAIL'}"
    )
    print(
        f"  PASS uplift >= {PASS_SHARPE_GROSS}      -> "
        f"{'PASS' if result.cv_sharpe_uplift_oof >= PASS_SHARPE_GROSS else 'FAIL'}"
    )
    print("-" * 72)
    print(f"FINAL VERDICT: {final_verdict}")
    print(f"  {explanation}")
    print("=" * 72)
    print()
    print(f"JSON -> {json_p}")
    print(f"Memo -> {memo_p}")

    return 0 if final_verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
