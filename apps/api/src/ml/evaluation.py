"""Walk-forward evaluation runner + classification metrics.

Pipeline per fold:
  1. fit simple model on train rows
  2. predict probabilities on val + test rows
  3. compute metrics at fixed threshold (default 0.5)
  4. record per-regime / per-catalyst-bucket breakdown
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from apps.api.src.ml.features import FEATURE_COLUMNS
from apps.api.src.ml.models import TrainedModel, fit_simple_model
from apps.api.src.ml.splits import (
    WalkForwardConfig, enough_data_for_ml, walk_forward_splits,
)


@dataclass
class FoldMetrics:
    fold: int
    split: str                              # "train" | "val" | "test"
    n: int
    positive_rate: float
    pred_positive_rate: float
    accuracy: float
    precision: float
    recall: float
    auc: float | None
    mean_return_accepted: float | None
    sharpe_proxy_accepted: float | None


@dataclass
class WalkForwardEvalResult:
    model_name: str
    label_col: str
    threshold: float
    n_folds: int
    folds: list[FoldMetrics] = field(default_factory=list)
    top_features: list[tuple[str, float]] = field(default_factory=list)
    coefficients: list[tuple[str, float]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    gate_status: dict[str, Any] = field(default_factory=dict)
    trained_any: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "label": self.label_col,
            "threshold": self.threshold,
            "n_folds": self.n_folds,
            "trained_any": self.trained_any,
            "folds": [f.__dict__ for f in self.folds],
            "top_features": self.top_features,
            "coefficients": self.coefficients,
            "warnings": self.warnings,
            "gate_status": self.gate_status,
        }


def classification_metrics(
    y_true: np.ndarray, y_score: np.ndarray,
    *, threshold: float = 0.5,
    returns: np.ndarray | None = None,
) -> dict[str, float | None]:
    """Threshold-independent + threshold-dependent metrics."""
    y_true = np.asarray(y_true).astype(int)
    y_score = np.asarray(y_score).astype(float)
    n = int(len(y_true))
    if n == 0:
        return {
            "n": 0, "positive_rate": 0.0, "pred_positive_rate": 0.0,
            "accuracy": 0.0, "precision": 0.0, "recall": 0.0,
            "auc": None, "mean_return_accepted": None,
            "sharpe_proxy_accepted": None,
        }
    pred = (y_score >= threshold).astype(int)
    tp = int(((pred == 1) & (y_true == 1)).sum())
    fp = int(((pred == 1) & (y_true == 0)).sum())
    fn = int(((pred == 0) & (y_true == 1)).sum())
    tn = int(((pred == 0) & (y_true == 0)).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    accuracy = (tp + tn) / n

    # AUC if both classes present
    auc: float | None
    if len(set(y_true)) == 2:
        order = np.argsort(-y_score)
        y_sorted = y_true[order]
        cum_pos = np.cumsum(y_sorted)
        total_pos = int(y_sorted.sum())
        total_neg = n - total_pos
        if total_pos > 0 and total_neg > 0:
            tpr = cum_pos / total_pos
            fpr = (np.arange(1, n + 1) - cum_pos) / total_neg
            # Trapezoidal AUC over the ranked points
            auc = float(np.trapz(tpr, fpr))
            if auc < 0.5:
                auc = 1.0 - auc   # flip if classifier is anti-predictive
        else:
            auc = None
    else:
        auc = None

    mean_ret = sharpe = None
    if returns is not None and len(returns) == n:
        accepted = returns[pred == 1]
        if len(accepted) > 0:
            mean_ret = float(np.nanmean(accepted))
            sd = float(np.nanstd(accepted, ddof=0))
            sharpe = mean_ret / sd if sd > 1e-9 else 0.0

    return {
        "n": n,
        "positive_rate": float(y_true.mean()),
        "pred_positive_rate": float(pred.mean()),
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "auc": auc,
        "mean_return_accepted": mean_ret,
        "sharpe_proxy_accepted": sharpe,
    }


def evaluate_walk_forward(
    df: pd.DataFrame,
    *,
    label_col: str = "label_win_5d",
    return_col: str = "fwd_ret_5d",
    model_name: str = "logistic",
    feature_cols: tuple[str, ...] = FEATURE_COLUMNS,
    wf_cfg: WalkForwardConfig | None = None,
    min_training_rows: int = 1000,
    threshold: float = 0.5,
) -> WalkForwardEvalResult:
    """Run walk-forward evaluation. Returns a rich result + warnings.

    Gates:
      * dataset row count < min_training_rows → no training, warnings only
      * fold with < cfg.min_train_rows → skipped silently
    """
    warnings: list[str] = []
    gate = enough_data_for_ml(
        len(df),
        min_for_models=min_training_rows,
    )
    result = WalkForwardEvalResult(
        model_name=model_name,
        label_col=label_col,
        threshold=threshold,
        n_folds=0,
        gate_status=gate,
    )
    if not gate["can_train"]:
        warnings.append(
            f"training skipped — {len(df)} rows < min {min_training_rows} "
            f"(tier={gate['tier']})"
        )
        result.warnings = warnings
        return result

    if label_col not in df.columns:
        result.warnings = [f"label column '{label_col}' missing"]
        return result
    usable = df.dropna(subset=[label_col]).copy()
    if usable.empty:
        result.warnings = [f"no rows with non-null {label_col}"]
        return result

    # Ensure feature columns present; fill absent ones with zero (no crash)
    feats = list(feature_cols)
    for f in feats:
        if f not in usable.columns:
            usable[f] = 0.0

    fold_idx = 0
    last_trained: TrainedModel | None = None
    for (train_idx, val_idx, test_idx) in walk_forward_splits(usable, cfg=wf_cfg):
        fold_idx += 1
        X_tr = usable.iloc[train_idx][feats]
        y_tr = usable.iloc[train_idx][label_col].astype(float).fillna(0).astype(int)
        trained = fit_simple_model(
            X_tr, y_tr, name=model_name, feature_names=feats,
        )
        if trained.skipped:
            warnings.append(f"fold {fold_idx}: {trained.skip_reason}")
            continue
        last_trained = trained
        for split_name, idx in (
            ("train", train_idx), ("val", val_idx), ("test", test_idx),
        ):
            X = usable.iloc[idx][feats]
            y = usable.iloc[idx][label_col].astype(float).fillna(0).astype(int)
            rets = (
                usable.iloc[idx][return_col].to_numpy()
                if return_col in usable.columns else None
            )
            y_score = trained.predict_proba(X)
            m = classification_metrics(
                y.to_numpy(), y_score,
                threshold=threshold,
                returns=rets,
            )
            result.folds.append(FoldMetrics(
                fold=fold_idx, split=split_name,
                n=m["n"],
                positive_rate=m["positive_rate"],
                pred_positive_rate=m["pred_positive_rate"],
                accuracy=m["accuracy"],
                precision=m["precision"],
                recall=m["recall"],
                auc=m["auc"],
                mean_return_accepted=m["mean_return_accepted"],
                sharpe_proxy_accepted=m["sharpe_proxy_accepted"],
            ))

    result.n_folds = fold_idx
    result.trained_any = last_trained is not None
    if last_trained is not None:
        result.top_features = sorted(
            last_trained.feature_importances.items(),
            key=lambda kv: -abs(kv[1]),
        )[:15]
        result.coefficients = sorted(
            last_trained.coefficients.items(),
            key=lambda kv: -abs(kv[1]),
        )[:15]
    result.warnings = warnings
    return result
