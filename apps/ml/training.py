"""LightGBM meta-label training pipeline.

Fixed hyperparameters (no tuning). CV with purged-embargoed-grouped folds.
Threshold sweep over [0.40, 0.45, 0.50, 0.55, 0.60].

Shadow-ready gate (all three must hold on lockbox):
  1. sharpe_uplift >= 0.30
  2. dd_delta_pct  >= -5.0   (filtered DD not worse than baseline by >5%)
  3. trade_reduction_frac >= 0.20

AUC / logloss / DSR logged but NOT gated.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from loguru import logger

from apps.ml.dataset import load_dataset, split_cv_and_lockbox
from apps.ml.metrics import (
    bailey_dsr,
    cv_auc_logloss,
    simulate_filtered_sharpe,
)
from apps.ml.splits import purged_embargoed_group_folds

LGB_PARAMS: dict[str, object] = {
    "objective": "binary",
    "metric": ["auc", "binary_logloss"],
    "num_leaves": 31,
    "max_depth": 6,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "min_data_in_leaf": 20,
    "verbose": -1,
    "seed": 42,
}
NUM_BOOST_ROUND = 300
EARLY_STOPPING = 30
# Dense threshold grid — enables retention-constrained search.
THRESHOLDS: list[float] = [round(0.10 + 0.02 * i, 2) for i in range(26)]  # 0.10..0.60

# Retention constraints (primary design goal: no extreme over-filtering).
MIN_RETENTION_FRAC = 0.40   # keep >= 40% of Buy trades
MAX_RETENTION_FRAC = 0.80   # avoid near-pass-through solutions
MIN_LOCKBOX_TRADES = 100

# Shadow-ready gates
GATE_SHARPE_UPLIFT = 0.30
GATE_DD_DELTA = -5.0
GATE_TRADE_REDUCTION = 0.20
GATE_CV_UPLIFT_FLOOR = 0.0   # CV must not degrade Sharpe on the selected threshold

ARTIFACTS_DIR = Path("artifacts")
GATE_STATE_PATH = ARTIFACTS_DIR / "ml_gate.json"
TRAIN_RESULT_PATH = ARTIFACTS_DIR / "ml_training_result.json"


# ---------------------------------------------------------------------------
# Gate check (read from validate_edge.py output)
# ---------------------------------------------------------------------------


class EdgeGateBlocked(RuntimeError):
    pass


def require_edge_gate_open() -> dict:
    if not GATE_STATE_PATH.exists():
        raise EdgeGateBlocked(
            f"edge gate file missing: {GATE_STATE_PATH}. "
            "Run: python -m scripts.validate_edge"
        )
    state = json.loads(GATE_STATE_PATH.read_text())
    if state.get("status") != "OPEN":
        raise EdgeGateBlocked(
            f"edge gate CLOSED: reasons={state.get('reasons')}. "
            "Fix deterministic engine, re-backfill, re-validate. "
            "DO NOT train ML."
        )
    logger.info("[train] edge gate OPEN → proceeding")
    return state


# ---------------------------------------------------------------------------
# Training result containers
# ---------------------------------------------------------------------------


@dataclass
class FoldResult:
    fold: int
    train_rows: int
    val_rows: int
    best_iter: int
    auc: float
    logloss: float
    brier: float


@dataclass
class TrainingResult:
    cv_folds: list[FoldResult]
    cv_mean_auc: float
    cv_mean_logloss: float
    threshold_sweep: list[dict]
    best_threshold: float
    lockbox_eval: dict
    shadow_ready: bool
    shadow_ready_reason: str
    bailey_dsr: float
    feature_list: list[str]
    n_train: int
    n_lockbox: int


# ---------------------------------------------------------------------------
# CV training
# ---------------------------------------------------------------------------


def _train_cv(
    cv_df: pd.DataFrame, features: list[str], target: str,
) -> tuple[np.ndarray, list[FoldResult]]:
    folds = purged_embargoed_group_folds(cv_df, n_splits=5)
    oof_proba = np.full(len(cv_df), np.nan, dtype=float)
    fold_results: list[FoldResult] = []

    for k, (tr_idx, va_idx) in enumerate(folds):
        X_tr = cv_df.iloc[tr_idx][features].values
        y_tr = cv_df.iloc[tr_idx][target].values
        X_va = cv_df.iloc[va_idx][features].values
        y_va = cv_df.iloc[va_idx][target].values

        dtr = lgb.Dataset(X_tr, label=y_tr)
        dva = lgb.Dataset(X_va, label=y_va, reference=dtr)
        model = lgb.train(
            LGB_PARAMS,
            dtr,
            num_boost_round=NUM_BOOST_ROUND,
            valid_sets=[dva],
            callbacks=[
                lgb.early_stopping(EARLY_STOPPING, verbose=False),
                lgb.log_evaluation(period=0),
            ],
        )
        proba_va = model.predict(X_va, num_iteration=model.best_iteration)
        oof_proba[va_idx] = proba_va

        metrics = cv_auc_logloss(y_va, proba_va)
        fr = FoldResult(
            fold=k,
            train_rows=len(tr_idx),
            val_rows=len(va_idx),
            best_iter=int(model.best_iteration or NUM_BOOST_ROUND),
            auc=round(metrics["auc"], 4),
            logloss=round(metrics["logloss"], 4),
            brier=round(metrics["brier"], 4),
        )
        logger.info(
            "[ml.train] fold={} train_rows={} val_rows={} best_iter={} "
            "val_auc={:.4f} val_logloss={:.4f} val_brier={:.4f}",
            fr.fold, fr.train_rows, fr.val_rows, fr.best_iter,
            fr.auc, fr.logloss, fr.brier,
        )
        fold_results.append(fr)

    return oof_proba, fold_results


# ---------------------------------------------------------------------------
# Lockbox fit + evaluation
# ---------------------------------------------------------------------------


def _fit_full(
    cv_df: pd.DataFrame, features: list[str], target: str,
    best_iter: int,
) -> lgb.Booster:
    X = cv_df[features].values
    y = cv_df[target].values
    dtr = lgb.Dataset(X, label=y)
    model = lgb.train(
        LGB_PARAMS,
        dtr,
        num_boost_round=max(best_iter, 50),
    )
    return model


# ---------------------------------------------------------------------------
# Decision gate
# ---------------------------------------------------------------------------


def decide_ready_for_shadow(
    lockbox_eval: dict,
    cv_uplift: float | None = None,
) -> tuple[bool, str]:
    sharpe_uplift = lockbox_eval.get("sharpe_uplift", 0.0)
    dd_delta = lockbox_eval.get("dd_delta_pct", 0.0)
    trade_red = lockbox_eval.get("trade_reduction_frac", 0.0)
    filt_trades = lockbox_eval.get("filtered_trade_count", 0)

    if cv_uplift is not None and cv_uplift < GATE_CV_UPLIFT_FLOOR:
        return False, (
            f"CV uplift negative: {cv_uplift:.4f} < {GATE_CV_UPLIFT_FLOOR} — "
            "model not generalizing"
        )
    if filt_trades < MIN_LOCKBOX_TRADES:
        return False, (
            f"lockbox trades too few: {filt_trades} < {MIN_LOCKBOX_TRADES}"
        )
    if sharpe_uplift < GATE_SHARPE_UPLIFT:
        return False, (
            f"sharpe_uplift insufficient: {sharpe_uplift:.4f} < "
            f"{GATE_SHARPE_UPLIFT}"
        )
    if dd_delta < GATE_DD_DELTA:
        return False, (
            f"drawdown worse than baseline: {dd_delta:.4f} < {GATE_DD_DELTA}"
        )
    if trade_red < GATE_TRADE_REDUCTION:
        return False, (
            f"trade reduction insufficient: {trade_red:.4f} < "
            f"{GATE_TRADE_REDUCTION}"
        )
    return True, "ready for shadow"


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def train_and_evaluate() -> TrainingResult:
    require_edge_gate_open()

    bundle = load_dataset()
    cv_df, lockbox_df = split_cv_and_lockbox(bundle.df)

    if len(cv_df) < 200:
        raise RuntimeError(
            f"too few CV rows ({len(cv_df)}) — need more backfill history"
        )

    oof_proba, fold_results = _train_cv(cv_df, bundle.features, bundle.target)

    # OOF-level classification metrics
    mask = ~np.isnan(oof_proba)
    oof_metrics = cv_auc_logloss(
        cv_df[bundle.target].values[mask], oof_proba[mask],
    )
    cv_mean_auc = float(np.mean([f.auc for f in fold_results]))
    cv_mean_logloss = float(np.mean([f.logloss for f in fold_results]))
    logger.info(
        "[ml.train] CV oof auc={:.4f} logloss={:.4f} brier={:.4f} "
        "fold_mean_auc={:.4f}",
        oof_metrics["auc"], oof_metrics["logloss"], oof_metrics["brier"],
        cv_mean_auc,
    )

    # Threshold sweep on CV OOF
    sweep: list[dict] = []
    cv_slice = cv_df.iloc[mask].copy()
    for th in THRESHOLDS:
        res = simulate_filtered_sharpe(cv_slice, oof_proba[mask], th)
        logger.info(
            "[ml.train] CV threshold={:.2f} filtered_trades={} "
            "sharpe={:.4f} baseline_sharpe={:.4f} uplift={:.4f}",
            th, res["filtered_trade_count"], res["filtered_sharpe"],
            res["baseline_sharpe"], res["sharpe_uplift"],
        )
        sweep.append(res)

    # Retention-constrained threshold selection.
    total_cv = max(1, len(cv_slice))
    eligible: list[dict] = []
    for r in sweep:
        retention = r["filtered_trade_count"] / total_cv
        r["retention_frac"] = retention
        if (
            MIN_RETENTION_FRAC <= retention <= MAX_RETENTION_FRAC
            and r["sharpe_uplift"] >= GATE_CV_UPLIFT_FLOOR
        ):
            eligible.append(r)

    if eligible:
        best = max(eligible, key=lambda r: r["sharpe_uplift"])
        selection_mode = "constrained"
    else:
        # Relax CV-uplift floor first; keep retention band.
        retained = [
            r for r in sweep
            if MIN_RETENTION_FRAC <= r["retention_frac"] <= MAX_RETENTION_FRAC
        ]
        if retained:
            best = max(retained, key=lambda r: r["sharpe_uplift"])
            selection_mode = "retention_only"
        else:
            best = max(sweep, key=lambda r: r["sharpe_uplift"])
            selection_mode = "unconstrained"
    best_threshold = float(best["threshold"])
    logger.info(
        "[ml.train] best CV threshold={:.2f} uplift={:.4f} retention={:.4f} mode={}",
        best_threshold, best["sharpe_uplift"], best["retention_frac"],
        selection_mode,
    )

    # Full-fit on CV and evaluate on lockbox
    avg_best_iter = int(np.median([f.best_iter for f in fold_results]))
    full_model = _fit_full(
        cv_df, bundle.features, bundle.target, avg_best_iter,
    )
    X_lock = lockbox_df[bundle.features].values
    proba_lock = full_model.predict(X_lock)
    lockbox_eval = simulate_filtered_sharpe(
        lockbox_df, proba_lock, best_threshold,
    )
    lockbox_cls = cv_auc_logloss(
        lockbox_df[bundle.target].values, proba_lock,
    )
    logger.info(
        "[ml.train] LOCKBOX threshold={:.2f} sharpe={:.4f} "
        "baseline_sharpe={:.4f} uplift={:.4f} dd_delta={:.4f} "
        "trade_reduction={:.4f} trades={}",
        best_threshold, lockbox_eval["filtered_sharpe"],
        lockbox_eval["baseline_sharpe"], lockbox_eval["sharpe_uplift"],
        lockbox_eval["dd_delta_pct"], lockbox_eval["trade_reduction_frac"],
        lockbox_eval["filtered_trade_count"],
    )
    logger.info(
        "[ml.train] LOCKBOX informational auc={:.4f} logloss={:.4f} brier={:.4f}",
        lockbox_cls["auc"], lockbox_cls["logloss"], lockbox_cls["brier"],
    )

    ready, reason = decide_ready_for_shadow(
        lockbox_eval, cv_uplift=best.get("sharpe_uplift"),
    )
    verdict = "READY" if ready else "NOT_READY"
    logger.info("[ml.train] GATE shadow_ready={} reason={}", verdict, reason)

    dsr = bailey_dsr(
        sharpe=lockbox_eval["filtered_sharpe"],
        n_trials=len(THRESHOLDS),
        n_obs=max(30, len(lockbox_df)),
    )
    logger.info("[ml.train] bailey_dsr={:.4f} (informational)", dsr)

    result = TrainingResult(
        cv_folds=fold_results,
        cv_mean_auc=cv_mean_auc,
        cv_mean_logloss=cv_mean_logloss,
        threshold_sweep=sweep,
        best_threshold=best_threshold,
        lockbox_eval=lockbox_eval,
        shadow_ready=ready,
        shadow_ready_reason=reason,
        bailey_dsr=round(dsr, 4),
        feature_list=bundle.features,
        n_train=len(cv_df),
        n_lockbox=len(lockbox_df),
    )

    # Feature importance (gain-based from full-fit model)
    gains = full_model.feature_importance(importance_type="gain")
    importance = sorted(
        [(feat, float(g)) for feat, g in zip(bundle.features, gains)],
        key=lambda x: -x[1],
    )
    logger.info("[ml.train] feature_importance (top 10):")
    for feat, g in importance[:10]:
        logger.info("  {:<30s} {:.1f}", feat, g)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    TRAIN_RESULT_PATH.write_text(
        json.dumps(
            {
                "cv_folds": [asdict(f) for f in result.cv_folds],
                "cv_mean_auc": result.cv_mean_auc,
                "cv_mean_logloss": result.cv_mean_logloss,
                "threshold_sweep": result.threshold_sweep,
                "best_threshold": result.best_threshold,
                "lockbox_eval": result.lockbox_eval,
                "lockbox_classification": lockbox_cls,
                "shadow_ready": result.shadow_ready,
                "shadow_ready_reason": result.shadow_ready_reason,
                "bailey_dsr": result.bailey_dsr,
                "n_train": result.n_train,
                "n_lockbox": result.n_lockbox,
                "feature_list": result.feature_list,
                "feature_importance": importance,
            },
            indent=2, default=str,
        )
    )
    logger.info("[ml.train] results written → {}", TRAIN_RESULT_PATH)
    return result
