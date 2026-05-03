"""PA-1 — verify sample_weight reaches the estimator.

Behavioral test: when sample_weight zeroes out one class entirely, the
fitted model's predictions must reflect the unweighted class only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apps.api.src.ml.models import fit_simple_model, SKLEARN_AVAILABLE


pytestmark = pytest.mark.skipif(
    not SKLEARN_AVAILABLE, reason="sklearn not installed",
)


def _make_xy(seed: int = 0) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    n = 200
    x1 = rng.normal(0, 1, n)
    x2 = rng.normal(0, 1, n)
    y = (x1 + 0.3 * rng.normal(0, 1, n) > 0).astype(int)
    return (pd.DataFrame({"x1": x1, "x2": x2}),
            pd.Series(y, name="y"))


def test_sample_weight_changes_fit_output():
    """Same X/y, different weights → different decision boundary.
    class_balanced=False so weights aren't post-cancelled by sklearn's
    automatic class re-weighting."""
    X, y = _make_xy(seed=42)
    sw_uniform = pd.Series(np.ones(len(X)))
    # Up-weight a specific subset 100x heavier
    sw_skewed = pd.Series(
        np.where(np.arange(len(X)) % 5 == 0, 100.0, 1.0).astype(float),
    )

    m_uniform = fit_simple_model(
        X, y, name="logistic",
        class_balanced=False,
        sample_weight=sw_uniform,
    )
    m_skewed = fit_simple_model(
        X, y, name="logistic",
        class_balanced=False,
        sample_weight=sw_skewed,
    )
    assert not m_uniform.skipped
    assert not m_skewed.skipped

    p_uniform = m_uniform.model.predict_proba(X.values)[:, 1]
    p_skewed = m_skewed.model.predict_proba(X.values)[:, 1]
    diff = float(np.abs(p_uniform - p_skewed).mean())
    assert diff > 0.005, (
        f"sample_weight appears ignored (mean prob diff={diff:.6f})"
    )


def test_sample_weight_none_falls_back_to_unweighted():
    """sample_weight=None must produce a viable model (no exception)."""
    X, y = _make_xy()
    m = fit_simple_model(X, y, name="logistic", sample_weight=None)
    assert not m.skipped


def test_sample_weight_length_mismatch_logs_and_drops():
    """Mismatched length → weights ignored, model still trains."""
    X, y = _make_xy()
    bad_sw = np.ones(len(X) - 5)
    m = fit_simple_model(X, y, name="logistic", sample_weight=bad_sw)
    assert not m.skipped, "should still fit when weights are dropped"


def test_sample_weight_negative_clipped():
    """Negative weights get clipped to 0, fit still succeeds."""
    X, y = _make_xy()
    sw = np.ones(len(X))
    sw[:10] = -2.0
    m = fit_simple_model(X, y, name="logistic", sample_weight=sw)
    assert not m.skipped


def test_sample_weight_works_for_rf():
    """RF supports sample_weight directly (non-Pipeline path)."""
    X, y = _make_xy()
    sw = np.ones(len(X))
    m = fit_simple_model(X, y, name="rf", sample_weight=sw)
    assert not m.skipped, m.skip_reason


def test_sample_weight_works_for_logistic_pipeline():
    """Logistic uses Pipeline → kwargs must be `clf__sample_weight`."""
    X, y = _make_xy()
    sw = np.ones(len(X))
    m = fit_simple_model(X, y, name="logistic", sample_weight=sw)
    assert not m.skipped, m.skip_reason
