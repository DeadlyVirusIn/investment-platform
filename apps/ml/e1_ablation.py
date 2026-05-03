"""E1 — Week-1 risk-feature ablation experiment.

Independent of production training (apps/ml/training.py). Drops risk-proxy
features per the 2026-04-21 debate synthesis and retrains LightGBM with
identical CV geometry and hyperparameters. Decision gate only — not
shadow-ready, not live, not persisted to live models.

Per debate synthesis:
  - Drop risk-proxy features: realized_vol_20d, atr_percent_14,
    avg_dollar_volume_20d, residual_momentum_20d (rm20), atr_pctile_1y,
    plus vol_regime one-hot dummies.
  - Lockbox (final 20% by date) NOT touched. Decision is on CV only.
  - No threshold grid search — CV Sharpe evaluated at fixed top-80%
    quantile floor (Codex R3 prescription).
  - Sonnet D1 diagnostic: Spearman(y_hit, realized_vol_20d) on raw CV
    rows BEFORE dropping vol. Flag if abs(rho) > 0.20.
  - Codex R3 pass/fail thresholds applied.
  - calibration_applied=False in output for Phase 1/4 alignment.

No DB access in this module — takes DatasetBundle as input for testability.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from loguru import logger
from scipy.stats import spearmanr

from apps.ml.dataset import DatasetBundle, split_cv_and_lockbox
from apps.ml.metrics import bailey_dsr, cv_auc_logloss, simulate_filtered_sharpe
from apps.ml.splits import purged_embargoed_group_folds
from apps.ml.training import EARLY_STOPPING, LGB_PARAMS, NUM_BOOST_ROUND

# ---------------------------------------------------------------------------
# E1 spec constants
# ---------------------------------------------------------------------------

RISK_PROXY_FEATURES: tuple[str, ...] = (
    "realized_vol_20d",
    "atr_percent_14",
    "avg_dollar_volume_20d",
    "residual_momentum_20d",   # rm20 per debate spec 2026-04-21
    "atr_pctile_1y",           # direct transform of ATR
)
RISK_PROXY_CATEGORICAL_PREFIXES: tuple[str, ...] = ("vol_regime_",)

# Pass/fail thresholds — Codex R3 (debate synthesis 2026-04-21)
PASS_AUC: float = 0.53
PASS_SHARPE_GROSS: float = 0.25
FAIL_AUC: float = 0.505
FAIL_SHARPE: float = -0.10

# CV Sharpe eval — quantile floor, NOT threshold grid search
RETENTION_QUANTILE: float = 0.20   # keep top 80% (drop bottom 20% of proba)

# Sonnet D1 — vol-label entanglement flag
ENTANGLEMENT_RHO_THRESHOLD: float = 0.20

# Threshold method in production training.py (for the record)
THRESHOLD_METHOD_IN_PRODUCTION: str = (
    "grid_search_26_thresholds_0.10_to_0.60_step_0.02"
    " (apps/ml/training.py:49)"
)

ARTIFACTS_DIR = Path("artifacts")
E1_RESULT_PATH = ARTIFACTS_DIR / "e1_ablation_result.json"
E1_MEMO_PATH = ARTIFACTS_DIR / "e1_ablation_memo.md"


def result_path(suffix: str = "") -> Path:
    """Output JSON path. Pass `suffix=\"_asym\"` to keep versions separate."""
    return ARTIFACTS_DIR / f"e1_ablation_result{suffix}.json"


def memo_path(suffix: str = "") -> Path:
    return ARTIFACTS_DIR / f"e1_ablation_memo{suffix}.md"


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------


@dataclass
class E1FoldResult:
    fold: int
    train_rows: int
    val_rows: int
    best_iter: int
    auc: float
    logloss: float
    brier: float
    filtered_sharpe: float
    baseline_sharpe: float
    sharpe_uplift: float
    retention_frac: float


@dataclass
class E1Result:
    verdict: str                        # PASS / AMBIGUOUS_* / FAIL
    action: str                         # next-action prescription
    features_used: list[str]
    features_dropped: list[str]
    threshold_method_in_production: str
    cv_auc_oof: float
    cv_sharpe_uplift_oof: float
    cv_filtered_sharpe_oof: float
    cv_baseline_sharpe_oof: float
    retention_frac: float
    spearman_label_vs_vol20d: float | None
    spearman_p_value: float | None
    barrier_structurally_entangled: bool
    folds: list[E1FoldResult]
    feature_importance: list[tuple[str, float]]
    n_cv_rows: int
    n_lockbox_rows_untouched: int
    bailey_dsr: float
    calibration_applied: bool           # always False for E1
    proba_stats: dict


# ---------------------------------------------------------------------------
# Feature drop
# ---------------------------------------------------------------------------


def split_features(features: list[str]) -> tuple[list[str], list[str]]:
    """Partition feature list into (kept, dropped) per E1 risk-proxy spec."""
    kept: list[str] = []
    dropped: list[str] = []
    for f in features:
        if f in RISK_PROXY_FEATURES:
            dropped.append(f)
            continue
        if any(f.startswith(p) for p in RISK_PROXY_CATEGORICAL_PREFIXES):
            dropped.append(f)
            continue
        kept.append(f)
    return kept, dropped


# ---------------------------------------------------------------------------
# Sonnet D1 — vol-label entanglement
# ---------------------------------------------------------------------------


def compute_spearman_label_vol(
    cv_df: pd.DataFrame,
) -> tuple[float | None, float | None]:
    """Spearman(y_hit, realized_vol_20d) on raw CV rows BEFORE feature drop.

    Per Sonnet R3 — if abs(rho) > 0.20, the barrier is structurally
    vol-entangled and asymmetric-barrier becomes priority-1 regardless of
    feature-ablation outcome.
    """
    if "realized_vol_20d" not in cv_df.columns or "y_hit" not in cv_df.columns:
        return None, None
    sub = cv_df[["y_hit", "realized_vol_20d"]].dropna()
    if len(sub) < 30 or sub["y_hit"].nunique() < 2:
        return None, None
    rho, pval = spearmanr(sub["y_hit"], sub["realized_vol_20d"])
    return float(rho), float(pval)


# ---------------------------------------------------------------------------
# Verdict classification — Codex R3 buckets
# ---------------------------------------------------------------------------


def classify_verdict(auc: float, sharpe_uplift: float) -> tuple[str, str]:
    if auc >= PASS_AUC and sharpe_uplift >= PASS_SHARPE_GROSS:
        return "PASS", (
            "Green-light full 4-week redesign — features + label + sizing. "
            "Alpha signal survives risk-feature removal."
        )
    if auc >= PASS_AUC and FAIL_SHARPE <= sharpe_uplift < PASS_SHARPE_GROSS:
        return "AMBIGUOUS_LABEL_SIZING", (
            "Alpha present but label/sizing broken. Weeks 2-3 priority: "
            "asymmetric triple-barrier + mlfinlab.bet_sizing.bet_size_probability. "
            "Feature augmentation (alpha158) becomes secondary."
        )
    if FAIL_AUC < auc < PASS_AUC:
        return "AMBIGUOUS_NOISE", (
            "Signal near noise floor. Proceed with caution — only if Sonnet D1 "
            "Spearman abs > 0.20 (then asymmetric barrier first). Otherwise "
            "rethink whether meta-label adds value on this primary."
        )
    if auc <= FAIL_AUC and sharpe_uplift < FAIL_SHARPE:
        return "FAIL", (
            "Pure regime classifier — no alpha signal survives risk-feature "
            "removal. ABANDON re-enters consideration. Before abandoning, "
            "verify with Qlib alpha158 cross-sectional features (Week 2) as a "
            "one-shot: if alpha158 still gives AUC ~0.50 the model is dead."
        )
    return "AMBIGUOUS_OTHER", (
        "Outside predefined Codex R3 buckets — manual review required. "
        f"auc={auc:.4f} sharpe_uplift={sharpe_uplift:.4f}"
    )


# ---------------------------------------------------------------------------
# Per-fold train
# ---------------------------------------------------------------------------


def _train_one_fold(
    cv_df: pd.DataFrame, features: list[str], target: str,
    tr_idx: np.ndarray, va_idx: np.ndarray, fold_k: int,
) -> tuple[np.ndarray, E1FoldResult]:
    X_tr = cv_df.iloc[tr_idx][features].values
    y_tr = cv_df.iloc[tr_idx][target].values
    X_va = cv_df.iloc[va_idx][features].values
    y_va = cv_df.iloc[va_idx][target].values

    dtr = lgb.Dataset(X_tr, label=y_tr)
    dva = lgb.Dataset(X_va, label=y_va, reference=dtr)
    model = lgb.train(
        LGB_PARAMS, dtr,
        num_boost_round=NUM_BOOST_ROUND,
        valid_sets=[dva],
        callbacks=[
            lgb.early_stopping(EARLY_STOPPING, verbose=False),
            lgb.log_evaluation(period=0),
        ],
    )
    proba_va = model.predict(X_va, num_iteration=model.best_iteration)

    metrics = cv_auc_logloss(y_va, proba_va)

    fold_df = cv_df.iloc[va_idx]
    threshold = float(np.quantile(proba_va, RETENTION_QUANTILE))
    sharpe = simulate_filtered_sharpe(fold_df, proba_va, threshold)

    fr = E1FoldResult(
        fold=fold_k,
        train_rows=len(tr_idx),
        val_rows=len(va_idx),
        best_iter=int(model.best_iteration or NUM_BOOST_ROUND),
        auc=round(metrics["auc"], 4),
        logloss=round(metrics["logloss"], 4),
        brier=round(metrics["brier"], 4),
        filtered_sharpe=round(sharpe["filtered_sharpe"], 4),
        baseline_sharpe=round(sharpe["baseline_sharpe"], 4),
        sharpe_uplift=round(sharpe["sharpe_uplift"], 4),
        retention_frac=round(1.0 - RETENTION_QUANTILE, 4),
    )
    return proba_va, fr


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def run_e1_ablation(bundle: DatasetBundle) -> E1Result:
    """Execute E1. Takes pre-loaded DatasetBundle; does not touch DB.

    Lockbox rows are split off and then NEVER referenced again.
    """
    cv_df, lockbox_df = split_cv_and_lockbox(bundle.df)
    n_lockbox_rows_untouched = len(lockbox_df)
    del lockbox_df  # safety: prevent accidental access downstream

    if len(cv_df) < 200:
        raise RuntimeError(f"too few CV rows ({len(cv_df)}) for E1")

    kept, dropped = split_features(bundle.features)
    logger.info(
        "[e1] kept={} dropped={} ({})",
        len(kept), len(dropped), dropped,
    )
    if not kept:
        raise RuntimeError("all features classified as risk-proxy")
    if not dropped:
        raise RuntimeError(
            "no features dropped — check RISK_PROXY_FEATURES list "
            "against dataset NUMERIC_FEATURES"
        )

    # Sonnet D1 — BEFORE any feature removal
    rho, pval = compute_spearman_label_vol(cv_df)
    entangled = rho is not None and abs(rho) > ENTANGLEMENT_RHO_THRESHOLD
    logger.info(
        "[e1][D1] spearman(y_hit, realized_vol_20d) rho={} p={} entangled={}",
        rho, pval, entangled,
    )

    # --- purged k-fold CV on ablated feature set ----------------------------
    folds = purged_embargoed_group_folds(cv_df, n_splits=5)
    oof_proba = np.full(len(cv_df), np.nan, dtype=float)
    fold_results: list[E1FoldResult] = []

    for k, (tr_idx, va_idx) in enumerate(folds):
        proba_va, fr = _train_one_fold(
            cv_df, kept, "y_hit", tr_idx, va_idx, k,
        )
        oof_proba[va_idx] = proba_va
        logger.info(
            "[e1] fold={} train={} val={} best_iter={} auc={:.4f} "
            "filt_sharpe={:.4f} base={:.4f} uplift={:.4f}",
            fr.fold, fr.train_rows, fr.val_rows, fr.best_iter,
            fr.auc, fr.filtered_sharpe, fr.baseline_sharpe, fr.sharpe_uplift,
        )
        fold_results.append(fr)

    # Validate no NaN OOF remains (every CV row must be in exactly one fold)
    oof_mask = ~np.isnan(oof_proba)
    n_oof_nan = int((~oof_mask).sum())
    if n_oof_nan > 0:
        logger.warning(
            "[e1] {} CV rows have no OOF proba (unassigned by folds). "
            "Purge-embargo may have excluded them from all val folds. "
            "Excluding from OOF metrics.",
            n_oof_nan,
        )

    # --- OOF aggregate -------------------------------------------------------
    oof_cls = cv_auc_logloss(
        cv_df["y_hit"].values[oof_mask], oof_proba[oof_mask],
    )
    cv_slice = cv_df.iloc[oof_mask].copy()
    threshold_oof = float(np.quantile(oof_proba[oof_mask], RETENTION_QUANTILE))
    sharpe_oof = simulate_filtered_sharpe(
        cv_slice, oof_proba[oof_mask], threshold_oof,
    )

    # --- Feature importance (full-fit on CV) --------------------------------
    avg_best_iter = int(np.median([f.best_iter for f in fold_results]))
    X_all = cv_df[kept].values
    y_all = cv_df["y_hit"].values
    dtr = lgb.Dataset(X_all, label=y_all)
    full_model = lgb.train(
        LGB_PARAMS, dtr, num_boost_round=max(avg_best_iter, 50),
    )
    gains = full_model.feature_importance(importance_type="gain")
    importance: list[tuple[str, float]] = sorted(
        [(f, float(g)) for f, g in zip(kept, gains)],
        key=lambda x: -x[1],
    )

    # Proba stats (for Phase 1 shadow-mode confidence logging; NOT calibrated)
    proba_stats = {
        "mean": float(np.mean(oof_proba[oof_mask])),
        "std": float(np.std(oof_proba[oof_mask])),
        "min": float(np.min(oof_proba[oof_mask])),
        "max": float(np.max(oof_proba[oof_mask])),
        "quantile_20_threshold": threshold_oof,
    }

    verdict, action = classify_verdict(
        oof_cls["auc"], sharpe_oof["sharpe_uplift"],
    )

    dsr = bailey_dsr(
        sharpe=sharpe_oof["filtered_sharpe"],
        n_trials=1,      # E1 runs 1 config — no threshold search
        n_obs=max(30, len(cv_slice)),
    )

    result = E1Result(
        verdict=verdict,
        action=action,
        features_used=kept,
        features_dropped=dropped,
        threshold_method_in_production=THRESHOLD_METHOD_IN_PRODUCTION,
        cv_auc_oof=round(oof_cls["auc"], 4),
        cv_sharpe_uplift_oof=round(sharpe_oof["sharpe_uplift"], 4),
        cv_filtered_sharpe_oof=round(sharpe_oof["filtered_sharpe"], 4),
        cv_baseline_sharpe_oof=round(sharpe_oof["baseline_sharpe"], 4),
        retention_frac=round(1.0 - RETENTION_QUANTILE, 4),
        spearman_label_vs_vol20d=rho,
        spearman_p_value=pval,
        barrier_structurally_entangled=entangled,
        folds=fold_results,
        feature_importance=importance,
        n_cv_rows=len(cv_df),
        n_lockbox_rows_untouched=n_lockbox_rows_untouched,
        bailey_dsr=round(dsr, 4),
        calibration_applied=False,
        proba_stats=proba_stats,
    )
    logger.info(
        "[e1] VERDICT={} auc={:.4f} sharpe_uplift={:.4f}",
        verdict, result.cv_auc_oof, result.cv_sharpe_uplift_oof,
    )
    logger.info("[e1] action: {}", action)
    return result


# ---------------------------------------------------------------------------
# Artifact writers
# ---------------------------------------------------------------------------


def write_json(result: E1Result, path: Path = E1_RESULT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "experiment": "E1 — Week-1 risk-feature ablation",
        "debate_ref": (
            "~/debates/meta_label_lightgbm_20260421_162118/synthesis.md"
        ),
        "verdict": result.verdict,
        "action": result.action,
        "pass_fail_thresholds": {
            "pass_auc": PASS_AUC,
            "pass_sharpe_gross": PASS_SHARPE_GROSS,
            "fail_auc": FAIL_AUC,
            "fail_sharpe": FAIL_SHARPE,
        },
        "metrics": {
            "cv_auc_oof": result.cv_auc_oof,
            "cv_sharpe_uplift_oof": result.cv_sharpe_uplift_oof,
            "cv_filtered_sharpe_oof": result.cv_filtered_sharpe_oof,
            "cv_baseline_sharpe_oof": result.cv_baseline_sharpe_oof,
            "retention_frac": result.retention_frac,
            "bailey_dsr": result.bailey_dsr,
        },
        "diagnostic_D1_sonnet": {
            "spearman_label_vs_realized_vol_20d": result.spearman_label_vs_vol20d,
            "p_value": result.spearman_p_value,
            "entanglement_rho_threshold": ENTANGLEMENT_RHO_THRESHOLD,
            "barrier_structurally_entangled": result.barrier_structurally_entangled,
        },
        "features_used": result.features_used,
        "features_dropped": result.features_dropped,
        "feature_importance_gain": result.feature_importance,
        "threshold_method_in_production": result.threshold_method_in_production,
        "proba_stats": result.proba_stats,
        "calibration_applied": result.calibration_applied,
        "n_cv_rows": result.n_cv_rows,
        "n_lockbox_rows_untouched": result.n_lockbox_rows_untouched,
        "folds": [asdict(f) for f in result.folds],
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    logger.info("[e1] json written → {}", path)
    return path


def write_memo(result: E1Result, path: Path = E1_MEMO_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# E1 — Risk-Feature Ablation Memo")
    lines.append("")
    lines.append(f"**Verdict:** `{result.verdict}`")
    lines.append(f"**Action:** {result.action}")
    lines.append("")
    lines.append("## Metrics table")
    lines.append("")
    lines.append("| Metric | Value | Gate | Pass? |")
    lines.append("|--------|-------|------|-------|")
    lines.append(
        f"| CV AUC (OOF) | {result.cv_auc_oof:.4f} | ≥ {PASS_AUC} | "
        f"{'✓' if result.cv_auc_oof >= PASS_AUC else '✗'} |"
    )
    lines.append(
        f"| CV Sharpe uplift (OOF, gross) | {result.cv_sharpe_uplift_oof:.4f} | "
        f"≥ {PASS_SHARPE_GROSS} | "
        f"{'✓' if result.cv_sharpe_uplift_oof >= PASS_SHARPE_GROSS else '✗'} |"
    )
    lines.append(
        f"| CV filtered Sharpe | {result.cv_filtered_sharpe_oof:.4f} | — | — |"
    )
    lines.append(
        f"| CV baseline Sharpe | {result.cv_baseline_sharpe_oof:.4f} | — | — |"
    )
    lines.append(
        f"| Retention fraction | {result.retention_frac:.2%} | 80% (fixed) | ✓ |"
    )
    lines.append(
        f"| Bailey DSR (informational) | {result.bailey_dsr:.4f} | — | — |"
    )
    lines.append("")
    lines.append("## Sonnet D1 — vol-label entanglement diagnostic")
    lines.append("")
    rho_str = (
        f"{result.spearman_label_vs_vol20d:.4f}"
        if result.spearman_label_vs_vol20d is not None else "n/a"
    )
    p_str = (
        f"{result.spearman_p_value:.4g}"
        if result.spearman_p_value is not None else "n/a"
    )
    lines.append(
        f"- Spearman(y_hit, realized_vol_20d) = **{rho_str}** (p = {p_str})"
    )
    lines.append(
        f"- Entanglement threshold: |rho| > {ENTANGLEMENT_RHO_THRESHOLD}"
    )
    lines.append(
        f"- **Barrier structurally vol-entangled:** "
        f"{'YES — asymmetric barrier becomes priority-1' if result.barrier_structurally_entangled else 'no'}"
    )
    lines.append("")
    lines.append("## Per-fold metrics")
    lines.append("")
    lines.append(
        "| Fold | Train rows | Val rows | Best iter | AUC | "
        "Filt Sharpe | Base Sharpe | Uplift |"
    )
    lines.append("|------|-----------|----------|-----------|-----|-----|-----|-----|")
    for f in result.folds:
        lines.append(
            f"| {f.fold} | {f.train_rows} | {f.val_rows} | {f.best_iter} | "
            f"{f.auc:.4f} | {f.filtered_sharpe:.4f} | {f.baseline_sharpe:.4f} | "
            f"{f.sharpe_uplift:.4f} |"
        )
    lines.append("")
    lines.append("## Features")
    lines.append("")
    lines.append(f"**Kept ({len(result.features_used)}):**")
    lines.append(", ".join(f"`{f}`" for f in result.features_used))
    lines.append("")
    lines.append(f"**Dropped ({len(result.features_dropped)}):**")
    lines.append(", ".join(f"`{f}`" for f in result.features_dropped))
    lines.append("")
    lines.append("## Feature importance (gain, top 15)")
    lines.append("")
    lines.append("| # | Feature | Gain |")
    lines.append("|---|---------|------|")
    for i, (f, g) in enumerate(result.feature_importance[:15], 1):
        lines.append(f"| {i} | `{f}` | {g:.1f} |")
    lines.append("")
    lines.append("## Experiment metadata")
    lines.append("")
    lines.append(f"- CV rows: {result.n_cv_rows}")
    lines.append(
        f"- Lockbox rows (UNTOUCHED): {result.n_lockbox_rows_untouched}"
    )
    lines.append(f"- Calibration applied: `{result.calibration_applied}`")
    lines.append(
        f"- Threshold selection method in production training: "
        f"`{result.threshold_method_in_production}`"
    )
    lines.append(
        "- E1 threshold selection method: **fixed quantile floor (top 80%)**, "
        "NO grid search"
    )
    lines.append(f"- Proba stats: `{json.dumps(result.proba_stats)}`")
    lines.append("")
    lines.append("## Conditional Weeks 2-4 plan (per debate synthesis)")
    lines.append("")
    lines.append("Only proceed if verdict == `PASS`:")
    lines.append("")
    lines.append(
        "- **Week 2** — Add Qlib alpha158 cross-sectional features: "
        "rank-normalized momentum (`Rank(Return(Close, N))`), VWAP divergence "
        "(`Rank(VWAP/Close)`), residualized returns (`Rank(Resi(Return, 20))`), "
        "volume-price interactions. Retrain with purged k-fold. Gate: "
        "AUC improvement ≥ 0.02 vs E1."
    )
    lines.append(
        "- **Week 3** — Asymmetric triple-barrier via "
        "`mlfinlab.filters.get_events` with `pt_sl=[2.0, 1.0]`. Replace "
        "filter-at-threshold with `mlfinlab.bet_sizing.bet_size_probability` "
        "continuous sizer (m=2p−1). Gate: CV Sharpe uplift > 0 with deflated "
        "Sharpe significance (Bailey/Lopez de Prado)."
    )
    lines.append(
        "- **Week 4** — Walk-forward re-validation on **fresh** 3-month data "
        "(rolling window, NOT the original 537-trade lockbox). Decision: "
        "shadow at **full size** or iterate."
    )
    lines.append(
        "- **Weeks 5+** — Shadow redesigned model at full position weight "
        "against fresh forward data for 2-4 weeks."
    )
    lines.append("")
    lines.append("## Lockbox protection")
    lines.append("")
    lines.append(
        "Per Lopez de Prado backtest-overfitting framework: the existing "
        f"lockbox ({result.n_lockbox_rows_untouched} rows) is NOT read during "
        "E1 or any Week 2-4 iteration. Model selection happens in nested "
        "purged k-fold CV on pre-lockbox data. Exactly ONE final lockbox "
        "read permitted after the redesigned model is locked."
    )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("[e1] memo written → {}", path)
    return path
