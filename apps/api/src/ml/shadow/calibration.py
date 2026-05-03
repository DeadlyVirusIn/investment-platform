"""Calibration diagnostics — reliability buckets + Brier + ECE."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


DEFAULT_BUCKETS = 10


@dataclass
class CalibrationReport:
    n: int
    buckets: int
    brier: float
    ece: float                                # expected calibration error
    reliability: list[dict[str, Any]] = field(default_factory=list)
    poor_calibration: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "buckets": self.buckets,
            "brier": round(self.brier, 6),
            "ece": round(self.ece, 6),
            "reliability": self.reliability,
            "poor_calibration": self.poor_calibration,
        }


def compute_calibration(
    y_true,
    y_score,
    *,
    n_buckets: int = DEFAULT_BUCKETS,
    poor_ece_threshold: float = 0.10,
) -> CalibrationReport:
    """Bucket scores into n_buckets, compute empirical win-rate per bucket.

    Returns reliability table + Brier score + ECE. Marks
    `poor_calibration=True` when ECE > threshold.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_score = np.asarray(y_score, dtype=float)
    n = int(len(y_true))
    if n == 0:
        return CalibrationReport(n=0, buckets=n_buckets, brier=0.0, ece=0.0)

    # Brier score
    brier = float(((y_score - y_true) ** 2).mean())

    # Fixed-width buckets on [0, 1]
    edges = np.linspace(0.0, 1.0, n_buckets + 1)
    rel: list[dict[str, Any]] = []
    ece_sum = 0.0
    for i in range(n_buckets):
        lo, hi = edges[i], edges[i + 1]
        if i == n_buckets - 1:
            mask = (y_score >= lo) & (y_score <= hi)
        else:
            mask = (y_score >= lo) & (y_score < hi)
        k = int(mask.sum())
        if k == 0:
            rel.append({
                "lo": round(float(lo), 3),
                "hi": round(float(hi), 3),
                "n":  0, "mean_score": None, "empirical_rate": None,
                "gap": None,
            })
            continue
        mean_s = float(y_score[mask].mean())
        emp = float(y_true[mask].mean())
        gap = emp - mean_s
        rel.append({
            "lo": round(float(lo), 3),
            "hi": round(float(hi), 3),
            "n":  k,
            "mean_score":     round(mean_s, 4),
            "empirical_rate": round(emp, 4),
            "gap":            round(gap, 4),
        })
        ece_sum += (k / n) * abs(gap)

    ece = float(ece_sum)
    return CalibrationReport(
        n=n, buckets=n_buckets,
        brier=brier, ece=ece,
        reliability=rel,
        poor_calibration=(ece > poor_ece_threshold),
    )
