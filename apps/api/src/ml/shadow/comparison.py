"""Compare shadow ML against existing baselines + engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from apps.api.src.ml.baselines import run_baselines
from apps.api.src.ml.baselines_v2 import run_improved_baselines


@dataclass
class ShadowComparison:
    baselines_best: dict[str, Any] | None
    shadow: dict[str, Any]
    winner: str                              # "ml" | "baseline" | "tie"
    delta_sharpe: float
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "baselines_best": self.baselines_best,
            "shadow": self.shadow,
            "winner": self.winner,
            "delta_sharpe": round(self.delta_sharpe, 4),
            "notes": list(self.notes),
        }


def compare_shadow_vs_baselines(
    df: pd.DataFrame,
    *,
    shadow_score_col: str,
    label_col: str = "label_win_5d",
    return_col: str = "fwd_ret_5d",
    threshold: float = 0.5,
) -> ShadowComparison:
    """Treat ML as a scorer with threshold 0.5; compare sharpe vs best
    baseline on the same label."""
    if shadow_score_col not in df.columns or df[shadow_score_col].isna().all():
        return ShadowComparison(
            baselines_best=None,
            shadow={"n": 0, "sharpe_proxy": 0.0},
            winner="baseline",
            delta_sharpe=0.0,
            notes=["shadow score column empty"],
        )

    v1 = run_baselines(df, label_col=return_col)
    v2 = run_improved_baselines(df, label_col=return_col)
    all_b = v1 + v2
    best = None
    if all_b:
        best = max(
            (b for b in all_b
             if np.isfinite(b.sharpe_proxy)),
            key=lambda b: b.sharpe_proxy,
            default=None,
        )
    baseline_dict = best.to_dict() if best else None

    shadow_m = _shadow_metrics(df, shadow_score_col, return_col, threshold)
    baseline_sharpe = float(best.sharpe_proxy) if best else 0.0
    delta = shadow_m["sharpe_proxy"] - baseline_sharpe
    if abs(delta) < 1e-4:
        winner = "tie"
    elif delta > 0:
        winner = "ml"
    else:
        winner = "baseline"

    notes: list[str] = []
    if shadow_m["n"] < 30:
        notes.append(f"n={shadow_m['n']} — result directional only")
    if best is not None and abs(delta) < 0.05:
        notes.append("delta < 0.05 sharpe — not materially different")

    return ShadowComparison(
        baselines_best=baseline_dict,
        shadow=shadow_m,
        winner=winner,
        delta_sharpe=delta,
        notes=notes,
    )


def _shadow_metrics(
    df: pd.DataFrame, score_col: str,
    return_col: str, threshold: float,
) -> dict[str, Any]:
    score = pd.to_numeric(df[score_col], errors="coerce").fillna(0.5)
    rets = pd.to_numeric(df[return_col], errors="coerce")
    accept = score >= threshold
    accepted = rets[accept].dropna().to_numpy()
    rejected = rets[~accept].dropna().to_numpy()
    n_acc = int(len(accepted))
    if n_acc == 0:
        return {
            "n": 0, "n_accepted": 0, "hit_rate": 0.0,
            "mean_return": 0.0, "sharpe_proxy": 0.0,
            "avoided_loss_mean_ret": float(rejected.mean())
                                     if len(rejected) else None,
        }
    wins = int((accepted > 0).sum())
    mean_r = float(accepted.mean())
    sd = float(accepted.std(ddof=0))
    sharpe = mean_r / sd if sd > 1e-9 else 0.0
    return {
        "n": int(len(df)),
        "n_accepted": n_acc,
        "hit_rate": wins / n_acc,
        "mean_return": mean_r,
        "sharpe_proxy": sharpe,
        "avoided_loss_mean_ret": float(rejected.mean())
                                 if len(rejected) else None,
    }
