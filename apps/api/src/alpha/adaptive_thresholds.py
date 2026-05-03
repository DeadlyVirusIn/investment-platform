"""Adaptive threshold optimizer — tries threshold grid, proposes best.

Never mutates engines. Produces recommendations the executor gates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd


@dataclass
class ThresholdRecommendation:
    threshold: str
    current: float
    recommended: float
    confidence: float
    sample_size: int
    expected_lift: float
    risk: str                        # low | medium | high
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "current": round(self.current, 4),
            "recommended": round(self.recommended, 4),
            "confidence": round(self.confidence, 4),
            "sample_size": self.sample_size,
            "expected_lift": round(self.expected_lift, 6),
            "risk": self.risk,
            "notes": self.notes,
        }


def recommend_thresholds(
    df: pd.DataFrame,
    *,
    return_col: str = "fwd_ret_5d",
) -> list[ThresholdRecommendation]:
    out: list[ThresholdRecommendation] = []
    out.extend(_min_threshold_sweep(
        df, col="feature_confidence", current=0.6,
        grid=(0.5, 0.6, 0.7, 0.8),
        name="min_data_confidence",
        return_col=return_col, direction="gte",
    ))
    out.extend(_min_threshold_sweep(
        df, col="event_risk_score", current=0.7,
        grid=(0.5, 0.6, 0.7, 0.8),
        name="max_event_risk",
        return_col=return_col, direction="lt",
    ))
    out.extend(_min_threshold_sweep(
        df, col="gates_favorable", current=1,
        grid=(0, 1, 2, 3),
        name="min_gates_favorable",
        return_col=return_col, direction="gte",
    ))
    return out


def _min_threshold_sweep(
    df: pd.DataFrame, *,
    col: str, current: float,
    grid: Iterable[float],
    name: str, return_col: str,
    direction: str = "gte",
) -> list[ThresholdRecommendation]:
    if col not in df.columns or return_col not in df.columns:
        return []
    sub = df.dropna(subset=[col, return_col])
    if len(sub) < 80:
        return []

    best = None
    current_mean = _mean_above(sub, col, current, return_col, direction)
    for t in grid:
        mean_sel, n_sel = _mean_above_n(
            sub, col, t, return_col, direction,
        )
        if n_sel < 30:
            continue
        lift = mean_sel - current_mean
        # Penalise low-sample thresholds; prefer moderate change
        score = lift * (n_sel ** 0.5)
        if best is None or score > best["score"]:
            best = {"t": t, "lift": lift, "n": n_sel, "score": score,
                    "mean": mean_sel}
    if best is None or best["t"] == current:
        return []
    # Only accept tighter-risk (reduces exposure) as low-risk
    risk = "low"
    if direction == "gte" and best["t"] < current:
        risk = "medium"           # loosens requirement
    if direction == "lt" and best["t"] > current:
        risk = "medium"
    confidence = min(1.0, max(0.0, abs(best["lift"]) * 80))
    return [ThresholdRecommendation(
        threshold=name,
        current=float(current),
        recommended=float(best["t"]),
        confidence=confidence,
        sample_size=int(best["n"]),
        expected_lift=float(best["lift"]),
        risk=risk,
        notes=(
            f"grid selected {best['t']} from {list(grid)} by lift×√n"
        ),
    )]


def _mean_above(
    df: pd.DataFrame, col: str, t: float,
    return_col: str, direction: str,
) -> float:
    mask = df[col] >= t if direction == "gte" else df[col] < t
    sub = df.loc[mask, return_col].dropna()
    return float(sub.mean()) if not sub.empty else 0.0


def _mean_above_n(
    df: pd.DataFrame, col: str, t: float,
    return_col: str, direction: str,
) -> tuple[float, int]:
    mask = df[col] >= t if direction == "gte" else df[col] < t
    sub = df.loc[mask, return_col].dropna()
    return (
        float(sub.mean()) if not sub.empty else 0.0,
        int(len(sub)),
    )
