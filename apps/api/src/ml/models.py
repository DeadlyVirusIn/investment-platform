"""Simple, inspectable ML models for walk-forward evaluation.

Allowed:
  * logistic regression (sklearn.linear_model.LogisticRegression)
  * ridge regression   (sklearn.linear_model.RidgeClassifier)
  * random forest      (sklearn.ensemble.RandomForestClassifier, shallow)
  * gradient boosting  (sklearn.ensemble.GradientBoostingClassifier)

sklearn is optional — `SKLEARN_AVAILABLE` guards all imports so the rest of
the ML module works without sklearn installed. If sklearn is absent, model
training functions return a non-trained result with `skipped=True`.

No deep learning. No GPU. Max tree depth capped. `max_features` bounded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

try:
    from sklearn.linear_model import LogisticRegression, RidgeClassifier
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


ALLOWED_MODELS = ("logistic", "ridge", "rf", "gbm")


@dataclass
class TrainedModel:
    name: str
    feature_names: list[str]
    label_col: str
    model: Any | None                       # sklearn estimator or None
    skipped: bool = False
    skip_reason: str = ""
    # Pulled out so report can surface without re-peeking sklearn internals
    feature_importances: dict[str, float] = field(default_factory=dict)
    coefficients:        dict[str, float] = field(default_factory=dict)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        if self.skipped or self.model is None:
            # Neutral score so downstream code doesn't crash
            return np.full(shape=(len(X),), fill_value=0.5, dtype=float)
        Xv = X[self.feature_names].to_numpy(dtype=float)
        Xv = np.nan_to_num(Xv, nan=0.0, posinf=0.0, neginf=0.0)
        m = self.model
        if hasattr(m, "predict_proba"):
            return m.predict_proba(Xv)[:, 1]
        # RidgeClassifier has decision_function only
        if hasattr(m, "decision_function"):
            raw = m.decision_function(Xv)
            return 1.0 / (1.0 + np.exp(-raw))
        return np.full(shape=(len(X),), fill_value=0.5, dtype=float)


def fit_simple_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    *,
    name: str = "logistic",
    feature_names: list[str] | None = None,
    class_balanced: bool = True,
    sample_weight: pd.Series | np.ndarray | None = None,
) -> TrainedModel:
    """Fit a single simple model. Returns a TrainedModel (never raises).

    Phase A-1 (Octo MUST-FIX): sample_weight is now passed through to
    the underlying estimator's fit(). Pipelines need step-prefixed
    kwargs; standalone estimators take it directly.
    """
    feats = feature_names or list(X_train.columns)
    label_col = str(y_train.name) if y_train.name else "y"

    if not SKLEARN_AVAILABLE:
        return TrainedModel(
            name=name, feature_names=feats, label_col=label_col,
            model=None, skipped=True,
            skip_reason="sklearn not installed",
        )

    if name not in ALLOWED_MODELS:
        return TrainedModel(
            name=name, feature_names=feats, label_col=label_col,
            model=None, skipped=True,
            skip_reason=f"model '{name}' not in allowed list {ALLOWED_MODELS}",
        )

    # Prep data — NaN/inf → 0 for numeric safety
    X = X_train[feats].to_numpy(dtype=float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    y = y_train.fillna(0).astype(int).to_numpy()

    if len(set(y)) < 2:
        return TrainedModel(
            name=name, feature_names=feats, label_col=label_col,
            model=None, skipped=True,
            skip_reason="only one class in training labels",
        )

    cw = "balanced" if class_balanced else None
    if name == "logistic":
        pipe = Pipeline([
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(
                C=1.0, penalty="l2", solver="liblinear",
                max_iter=200, class_weight=cw,
            )),
        ])
    elif name == "ridge":
        pipe = Pipeline([
            ("scale", StandardScaler()),
            ("clf", RidgeClassifier(alpha=1.0, class_weight=cw)),
        ])
    elif name == "rf":
        pipe = RandomForestClassifier(
            n_estimators=200, max_depth=5, min_samples_leaf=20,
            max_features="sqrt", class_weight=cw, n_jobs=1, random_state=42,
        )
    elif name == "gbm":
        pipe = GradientBoostingClassifier(
            n_estimators=150, max_depth=3, learning_rate=0.05,
            random_state=42,
        )

    # ── PA-1: prepare sample_weight aligned to X ─────────────────────
    sw_arr: np.ndarray | None = None
    if sample_weight is not None:
        try:
            sw_arr = np.asarray(sample_weight, dtype=float)
            if sw_arr.shape[0] != X.shape[0]:
                from loguru import logger as _log
                _log.warning(
                    "fit_simple_model: sample_weight length {} != X {} "
                    "— ignoring weights",
                    sw_arr.shape[0], X.shape[0],
                )
                sw_arr = None
            else:
                sw_arr = np.nan_to_num(sw_arr, nan=0.0, posinf=0.0, neginf=0.0)
                # Negative weights are invalid for sklearn estimators
                if (sw_arr < 0).any():
                    from loguru import logger as _log
                    _log.warning(
                        "fit_simple_model: sample_weight had negative "
                        "values — clipping to 0",
                    )
                    sw_arr = np.clip(sw_arr, 0.0, None)
        except Exception:
            sw_arr = None

    # ── PA-1: pipeline vs standalone estimators take different kwargs ──
    fit_kwargs: dict[str, np.ndarray] = {}
    if sw_arr is not None:
        if isinstance(pipe, Pipeline):
            # last step is "clf"
            fit_kwargs["clf__sample_weight"] = sw_arr
        else:
            fit_kwargs["sample_weight"] = sw_arr

    try:
        pipe.fit(X, y, **fit_kwargs)
    except TypeError as e:
        # Estimator does not accept sample_weight (e.g. some sklearn
        # versions of RidgeClassifier). Fail explicitly per spec.
        if sw_arr is not None and "sample_weight" in str(e):
            return TrainedModel(
                name=name, feature_names=feats, label_col=label_col,
                model=None, skipped=True,
                skip_reason=(
                    f"{name} does not accept sample_weight in this "
                    "sklearn version — skipping rather than dropping "
                    "weights"
                ),
            )
        raise
    except Exception as e:
        return TrainedModel(
            name=name, feature_names=feats, label_col=label_col,
            model=None, skipped=True,
            skip_reason=f"fit failed: {type(e).__name__}: {e}",
        )

    # Extract importances / coefficients
    importances: dict[str, float] = {}
    coeffs: dict[str, float] = {}
    clf = pipe.named_steps["clf"] if hasattr(pipe, "named_steps") else pipe
    if hasattr(clf, "feature_importances_"):
        for f, v in zip(feats, clf.feature_importances_):
            importances[f] = float(v)
    if hasattr(clf, "coef_"):
        coef_vec = np.ravel(clf.coef_)
        for f, v in zip(feats, coef_vec[: len(feats)]):
            coeffs[f] = float(v)

    return TrainedModel(
        name=name, feature_names=feats, label_col=label_col,
        model=pipe, skipped=False,
        feature_importances=importances,
        coefficients=coeffs,
    )
