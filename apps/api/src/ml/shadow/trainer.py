"""Constrained shadow model trainer.

Hard rules:
  * walk-forward only (no random k-fold)
  * max MODEL_CAP hyperparam configs per run
  * allowed models: logistic, ridge, rf_shallow, gbm_shallow
  * sample_weight respects dataset_source — real=1.0, replay<=0.25
  * sklearn optional — skipped cleanly when absent
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

from apps.api.src.ml.features import (
    FEATURE_COLUMNS, TRAINING_FEATURE_WHITELIST,
)
from apps.api.src.ml.models import fit_simple_model, TrainedModel
from apps.api.src.ml.splits import WalkForwardConfig, walk_forward_splits

MODEL_CAP = 10   # absolute cap across all model/config combos


class ModelType(str, Enum):
    LOGISTIC   = "logistic"
    RIDGE      = "ridge"
    RF_SHALLOW = "rf"
    GBM        = "gbm"


ALLOWED = {
    ModelType.LOGISTIC, ModelType.RIDGE,
    ModelType.RF_SHALLOW, ModelType.GBM,
}


@dataclass
class FoldResult:
    fold: int
    split: str                        # train | val | test
    n: int
    mean_score: float
    auc: float | None
    accuracy: float
    precision: float
    recall: float
    mean_return_accepted: float | None
    sharpe_proxy_accepted: float | None


@dataclass
class TrainerResult:
    model_type: ModelType
    label_col: str
    feature_list: list[str]
    fold_results: list[FoldResult] = field(default_factory=list)
    top_features: list[tuple[str, float]] = field(default_factory=list)
    coefficients: list[tuple[str, float]] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""
    final_model: Any | None = None
    test_sharpe_proxy: float | None = None
    test_auc:          float | None = None
    val_sharpe_proxy:  float | None = None
    val_auc:           float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_type": self.model_type.value,
            "label_col": self.label_col,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "feature_list": list(self.feature_list),
            "top_features": list(self.top_features),
            "coefficients": list(self.coefficients),
            "test_sharpe_proxy": _safe_float(self.test_sharpe_proxy),
            "test_auc":          _safe_float(self.test_auc),
            "val_sharpe_proxy":  _safe_float(self.val_sharpe_proxy),
            "val_auc":           _safe_float(self.val_auc),
            "folds": [f.__dict__ for f in self.fold_results],
        }


def train_shadow_models(
    df: pd.DataFrame,
    *,
    label_col: str = "label_win_5d",
    return_col: str = "fwd_ret_5d",
    # PD-5 — train on non-endogenous whitelist; engine/regime one-hots
    # remain in dataset metadata for analysis but are NOT consumed.
    feature_cols: tuple[str, ...] = TRAINING_FEATURE_WHITELIST,
    model_types: tuple[ModelType, ...] = (
        ModelType.LOGISTIC, ModelType.RIDGE, ModelType.RF_SHALLOW,
    ),
    wf_cfg: WalkForwardConfig | None = None,
    sample_weight_col: str = "sample_weight",
    replay_weight_cap: float = 0.25,
) -> list[TrainerResult]:
    """Train N constrained models; return per-model results.

    Select best by validation sharpe_proxy, then report test metrics.
    """
    if label_col not in df.columns:
        return [_skipped_result(mt, label_col,
                                f"label '{label_col}' missing")
                for mt in model_types]
    usable = df.dropna(subset=[label_col]).copy()
    if usable.empty:
        return [_skipped_result(mt, label_col, "no labeled rows")
                for mt in model_types]

    feats = [f for f in feature_cols if f != label_col]
    for f in feats:
        if f not in usable.columns:
            usable[f] = 0.0

    # Clamp replay sample_weight to ≤ replay_weight_cap
    if sample_weight_col in usable.columns \
       and "source_type" in usable.columns:
        replay_mask = usable["source_type"].eq("replay")
        usable.loc[replay_mask, sample_weight_col] = (
            usable.loc[replay_mask, sample_weight_col]
                  .clip(upper=replay_weight_cap)
        )

    # Enforce MODEL_CAP: pick at most N model types (default order)
    mt_list = list(model_types)[:MODEL_CAP]

    results: list[TrainerResult] = []
    for mt in mt_list:
        if mt not in ALLOWED:
            results.append(_skipped_result(
                mt, label_col, f"{mt.value} not in ALLOWED"
            ))
            continue
        results.append(_walk_forward_train(
            usable, label_col=label_col, return_col=return_col,
            feats=feats, mt=mt, wf_cfg=wf_cfg,
        ))
    return results


# ---------------------------------------------------------------------------
def _walk_forward_train(
    df: pd.DataFrame, *,
    label_col: str, return_col: str,
    feats: list[str], mt: ModelType,
    wf_cfg: WalkForwardConfig | None,
) -> TrainerResult:
    cfg = wf_cfg or WalkForwardConfig()
    out = TrainerResult(
        model_type=mt, label_col=label_col, feature_list=feats,
    )
    last_trained: TrainedModel | None = None
    has_sw_col = "sample_weight" in df.columns
    for (train_idx, val_idx, test_idx) in walk_forward_splits(df, cfg=cfg):
        X_tr = df.iloc[train_idx][feats]
        y_tr = df.iloc[train_idx][label_col].astype(float).fillna(0).astype(int)
        # PA-1 — pull per-row sample_weight (real=1.0, replay≤cap)
        sw_tr = (
            df.iloc[train_idx]["sample_weight"]
              .astype(float).fillna(1.0)
            if has_sw_col else None
        )
        trained = fit_simple_model(
            X_tr, y_tr, name=mt.value, feature_names=feats,
            sample_weight=sw_tr,
        )
        if trained.skipped:
            out.skipped = True
            out.skip_reason = trained.skip_reason
            continue
        last_trained = trained
        for split, idx in (
            ("train", train_idx), ("val", val_idx), ("test", test_idx),
        ):
            metrics = _fold_metrics(
                df.iloc[idx], trained, feats, label_col, return_col,
            )
            out.fold_results.append(FoldResult(
                fold=len(out.fold_results) + 1, split=split, **metrics,
            ))
    # Aggregate val / test metrics
    vals = [f for f in out.fold_results if f.split == "val"]
    tests = [f for f in out.fold_results if f.split == "test"]
    if vals:
        out.val_sharpe_proxy = _avg(f.sharpe_proxy_accepted for f in vals)
        out.val_auc = _avg(f.auc for f in vals)
    if tests:
        out.test_sharpe_proxy = _avg(f.sharpe_proxy_accepted for f in tests)
        out.test_auc = _avg(f.auc for f in tests)
    if last_trained is not None:
        out.final_model = last_trained
        out.top_features = sorted(
            last_trained.feature_importances.items(),
            key=lambda kv: -abs(kv[1]),
        )[:10]
        out.coefficients = sorted(
            last_trained.coefficients.items(),
            key=lambda kv: -abs(kv[1]),
        )[:10]
    return out


def _fold_metrics(
    frame: pd.DataFrame, trained: TrainedModel,
    feats: list[str], label_col: str, return_col: str,
) -> dict[str, Any]:
    from apps.api.src.ml.evaluation import classification_metrics
    y = frame[label_col].astype(float).fillna(0).astype(int).to_numpy()
    X = frame[feats]
    scores = trained.predict_proba(X)
    rets = frame[return_col].to_numpy() if return_col in frame.columns \
           else None
    m = classification_metrics(y, scores, threshold=0.5, returns=rets)
    return {
        "n": m["n"],
        "mean_score": float(scores.mean()) if len(scores) else 0.0,
        "auc": m["auc"],
        "accuracy": m["accuracy"],
        "precision": m["precision"],
        "recall": m["recall"],
        "mean_return_accepted": m["mean_return_accepted"],
        "sharpe_proxy_accepted": m["sharpe_proxy_accepted"],
    }


def _avg(values) -> float | None:
    vs = [v for v in values if v is not None and not _is_nan(v)]
    return float(sum(vs) / len(vs)) if vs else None


def _is_nan(v: Any) -> bool:
    try:
        return v != v  # NaN trick
    except TypeError:
        return False


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
        return x if not _is_nan(x) else None
    except (TypeError, ValueError):
        return None


def _skipped_result(
    mt: ModelType, label_col: str, reason: str,
) -> TrainerResult:
    return TrainerResult(
        model_type=mt, label_col=label_col, feature_list=[],
        skipped=True, skip_reason=reason,
    )
