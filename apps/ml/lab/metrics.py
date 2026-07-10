"""Experiment Lab metrics — calibration, classification, trading.

Edge policy: metrics that are undefined on the given data (single-class
AUC, precision with zero predicted positives) return None instead of NaN —
None survives canonical JSON and the registry's NaN guard; NaN does not.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

DEFAULT_BINS = 10


def _arrays(y_true, p) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(y_true, dtype=float)
    q = np.asarray(p, dtype=float)
    if y.shape != q.shape:
        raise ValueError(f"shape mismatch: y{y.shape} vs p{q.shape}")
    if y.size == 0:
        raise ValueError("empty inputs")
    return y, q


# ---------------------------------------------------------------------------
# calibration / classification
# ---------------------------------------------------------------------------


def brier(y_true, p) -> float:
    y, q = _arrays(y_true, p)
    return float(np.mean((q - y) ** 2))


def _bin_gaps(y: np.ndarray, q: np.ndarray, n_bins: int) -> list[tuple[float, float]]:
    """(weight, |mean p − mean y|) per non-empty equal-width bin."""
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    out: list[tuple[float, float]] = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (q >= lo) & (q < hi) if hi < 1.0 else (q >= lo) & (q <= hi)
        n = int(mask.sum())
        if n == 0:
            continue
        out.append((n / len(q), float(abs(q[mask].mean() - y[mask].mean()))))
    return out


def ece(y_true, p, n_bins: int = DEFAULT_BINS) -> float:
    """Expected calibration error: bin-weight-averaged |pred − observed|."""
    y, q = _arrays(y_true, p)
    return float(sum(w * g for w, g in _bin_gaps(y, q, n_bins)))


def mce(y_true, p, n_bins: int = DEFAULT_BINS) -> float:
    """Maximum calibration error: worst non-empty bin gap."""
    y, q = _arrays(y_true, p)
    gaps = _bin_gaps(y, q, n_bins)
    return float(max(g for _, g in gaps)) if gaps else 0.0


def auc(y_true, p) -> float | None:
    """ROC AUC; None when y_true has a single class (undefined)."""
    y, q = _arrays(y_true, p)
    if len(np.unique(y)) < 2:
        return None
    return float(roc_auc_score(y, q))


def precision_recall(y_true, y_pred) -> tuple[float | None, float | None]:
    """(precision, recall) for binary labels; each is None when its
    denominator is zero (no predicted positives / no actual positives)."""
    y, yp = _arrays(y_true, y_pred)
    tp = float(np.sum((yp == 1) & (y == 1)))
    pred_pos = float(np.sum(yp == 1))
    actual_pos = float(np.sum(y == 1))
    precision = (tp / pred_pos) if pred_pos > 0 else None
    recall = (tp / actual_pos) if actual_pos > 0 else None
    return precision, recall


# ---------------------------------------------------------------------------
# trading
# ---------------------------------------------------------------------------


def max_drawdown(returns: Sequence[float]) -> float:
    """Max peak-to-trough drawdown of the compounded equity curve, as a
    non-positive fraction (e.g. -0.5 = halved from peak)."""
    r = np.asarray(list(returns), dtype=float)
    if r.size == 0:
        return 0.0
    equity = np.cumprod(1.0 + r)
    peaks = np.maximum.accumulate(equity)
    return float(np.min(equity / peaks - 1.0))


def turnover(weights: pd.DataFrame) -> float:
    """Mean one-way turnover per period: 0.5 * Σ|w_t − w_{t−1}| averaged
    over rebalances. Rows = periods, columns = assets; NaN weight = 0."""
    w = weights.fillna(0.0).to_numpy(dtype=float)
    if w.shape[0] < 2:
        return 0.0
    per_period = 0.5 * np.abs(np.diff(w, axis=0)).sum(axis=1)
    return float(per_period.mean())


def cost_adjusted_return(
    gross_returns: Sequence[float], cost_bps: float,
) -> dict:
    """Deduct a flat per-period cost (bps of notional) from each gross
    return; totals are compounded. Cost timing/shape lives in lab.costs —
    this is the flat-haircut comparator."""
    g = np.asarray(list(gross_returns), dtype=float)
    if g.size == 0:
        raise ValueError("empty gross_returns")
    haircut = cost_bps / 1e4
    net = g - haircut
    return {
        "cost_bps": float(cost_bps),
        "gross_total_return": float(np.prod(1.0 + g) - 1.0),
        "net_total_return": float(np.prod(1.0 + net) - 1.0),
        "net_returns": [float(x) for x in net],
    }
