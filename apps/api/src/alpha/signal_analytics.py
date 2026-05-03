"""Signal bucketing + stability. Reuses ml.patterns primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from apps.api.src.ml.patterns import discover_patterns


@dataclass
class SignalInsights:
    n_rows: int
    return_col: str
    strongest_positive: list[dict[str, Any]] = field(default_factory=list)
    strongest_negative: list[dict[str, Any]] = field(default_factory=list)
    unstable_signals:   list[dict[str, Any]] = field(default_factory=list)
    downweight_recommendations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_rows": self.n_rows,
            "return_col": self.return_col,
            "strongest_positive": self.strongest_positive,
            "strongest_negative": self.strongest_negative,
            "unstable_signals": self.unstable_signals,
            "downweight_recommendations": self.downweight_recommendations,
            "warnings": self.warnings,
        }


def analyze_signals(
    df: pd.DataFrame, *,
    return_col: str = "fwd_ret_5d",
    top_k: int = 5,
    min_sample: int = 30,
) -> SignalInsights:
    if df.empty:
        return SignalInsights(
            n_rows=0, return_col=return_col,
            warnings=["empty frame"],
        )
    pr = discover_patterns(df, return_col=return_col,
                             top_k=top_k, min_sample=min_sample)

    # Find unstable signals: high-variance lift across regimes
    unstable = _stability_check(df, return_col=return_col)
    downweight = [
        {"axis": b["axis"], "bucket": b["bucket"],
         "reason": f"lift {b['lift_vs_control']:.3f} but "
                    f"n={b['n']} < {min_sample}"}
        for b in pr.to_dict().get("buckets", [])
        if b.get("low_confidence")
    ]

    return SignalInsights(
        n_rows=pr.n_rows,
        return_col=pr.return_col,
        strongest_positive=[b.to_dict() for b in pr.positive_patterns],
        strongest_negative=[b.to_dict() for b in pr.negative_patterns],
        unstable_signals=unstable,
        downweight_recommendations=downweight[:10],
        warnings=pr.pattern_warnings,
    )


def _stability_check(
    df: pd.DataFrame, *, return_col: str,
) -> list[dict[str, Any]]:
    """Flag features whose lift swings sign across regimes."""
    if return_col not in df.columns or df.empty:
        return []
    out: list[dict[str, Any]] = []
    for feat in ("catalyst_score", "event_risk_score",
                 "feature_confidence", "input_z_score"):
        if feat not in df.columns:
            continue
        by_regime: dict[str, float] = {}
        for reg_col, lab in (
            ("regime_stress", "stress"),
            ("regime_directional", "directional"),
            ("regime_neutral", "neutral"),
        ):
            if reg_col not in df.columns:
                continue
            sub = df[df[reg_col].astype(bool)]
            if sub.empty:
                continue
            corr = pd.to_numeric(sub[feat], errors="coerce").corr(
                pd.to_numeric(sub[return_col], errors="coerce"),
            )
            if corr is not None and corr == corr:
                by_regime[lab] = float(corr)
        if len(by_regime) >= 2:
            vals = list(by_regime.values())
            if max(vals) > 0.1 and min(vals) < -0.1:
                out.append({
                    "feature": feat,
                    "regime_correlations": by_regime,
                    "warning": "sign flips across regimes",
                })
    return out
