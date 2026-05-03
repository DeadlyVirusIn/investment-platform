"""Baselines — run before any ML model. Hype filter.

Four baselines as specified:
  B1: engine confidence only                    (proxy: feature_confidence)
  B2: engine confidence + regime
  B3: engine confidence + catalyst overlay
  B4: data_quality-aware filter

Plus control strategies:
  * always_accept
  * confidence_threshold@0.5

Metrics computed against the primary label (default `fwd_ret_5d`):
  hit_rate, mean_return, median_return, profit_factor, max_dd, sharpe_proxy,
  precision_positive, avoided_loss (for filters — return of REJECTED rows)

Baselines score each row and threshold at a default cutoff. They do NOT
train. Thresholds are fixed in code so "baseline" is reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd


@dataclass
class BaselineResult:
    name: str
    threshold: float
    n_rows: int
    n_accepted: int
    hit_rate: float
    mean_return: float
    median_return: float
    profit_factor: float
    max_drawdown: float
    sharpe_proxy: float
    precision_positive: float
    avoided_loss_mean_ret: float | None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "threshold": self.threshold,
            "n_rows": self.n_rows,
            "n_accepted": self.n_accepted,
            "acceptance_rate": (
                self.n_accepted / self.n_rows if self.n_rows else 0.0
            ),
            "hit_rate": round(self.hit_rate, 4),
            "mean_return": round(self.mean_return, 6),
            "median_return": round(self.median_return, 6),
            "profit_factor": round(self.profit_factor, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "sharpe_proxy": round(self.sharpe_proxy, 4),
            "precision_positive": round(self.precision_positive, 4),
            "avoided_loss_mean_ret": (
                None if self.avoided_loss_mean_ret is None
                else round(self.avoided_loss_mean_ret, 6)
            ),
            "notes": self.notes,
        }


def run_baselines(
    df: pd.DataFrame,
    *,
    label_col: str = "fwd_ret_5d",
    threshold: float = 0.0,
) -> list[BaselineResult]:
    """Run all baselines + controls against one label column.

    Rows with NaN labels are dropped for the evaluation.
    """
    if label_col not in df.columns:
        return [
            _empty(f"label '{label_col}' missing"),
        ]
    work = df.dropna(subset=[label_col]).copy()
    if work.empty:
        return [_empty("no labeled rows")]

    baselines: list[tuple[str, Callable[[pd.DataFrame], pd.Series], str]] = [
        ("b1_engine_conf",
         lambda d: d.get("feature_confidence", pd.Series(1.0, index=d.index)),
         "score = feature_confidence"),
        ("b2_conf_plus_regime",
         lambda d: (
             d.get("feature_confidence", pd.Series(1.0, index=d.index)).fillna(0.0)
             * (1.0 - d.get("regime_stress",
                            pd.Series(0, index=d.index)).astype(float) * 0.4)
         ),
         "conf * (1 - 0.4*stress)"),
        ("b3_conf_plus_catalyst",
         lambda d: (
             d.get("feature_confidence", pd.Series(1.0, index=d.index)).fillna(0.0)
             * (1.0 - d.get("event_risk_score",
                            pd.Series(0.0, index=d.index)).fillna(0.0))
         ),
         "conf * (1 - event_risk_score)"),
        ("b4_data_quality_filter",
         lambda d: (
             d.get("feature_confidence", pd.Series(1.0, index=d.index)).fillna(0.0)
             * (d.get("missing_field_count",
                      pd.Series(0, index=d.index)).fillna(0).eq(0)).astype(float)
         ),
         "conf * (missing==0)"),
        ("ctrl_always_accept",
         lambda d: pd.Series(1.0, index=d.index),
         "score = 1.0 (accept everything)"),
        ("ctrl_conf_threshold_0.5",
         lambda d: d.get("feature_confidence",
                         pd.Series(0.0, index=d.index)).fillna(0.0),
         "score = feature_confidence; threshold 0.5"),
    ]

    out: list[BaselineResult] = []
    for name, scorer, note in baselines:
        score = scorer(work).astype(float).fillna(0.0)
        thr = 0.5 if name == "ctrl_conf_threshold_0.5" else threshold
        # Baseline accept = score above threshold (scores are in [0,1] range)
        accept_mask = score > thr
        accepted = work.loc[accept_mask, label_col]
        rejected = work.loc[~accept_mask, label_col]
        out.append(_score_block(
            name=name, threshold=thr, note=note,
            accepted_returns=accepted.to_numpy(),
            rejected_returns=rejected.to_numpy(),
            n_total=len(work),
        ))

    return out


# ---------------------------------------------------------------------------
# metric computation
# ---------------------------------------------------------------------------

def _score_block(
    *, name: str, threshold: float, note: str,
    accepted_returns: np.ndarray,
    rejected_returns: np.ndarray,
    n_total: int,
) -> BaselineResult:
    n_acc = int(len(accepted_returns))
    if n_acc == 0:
        return BaselineResult(
            name=name, threshold=threshold, n_rows=n_total, n_accepted=0,
            hit_rate=0.0, mean_return=0.0, median_return=0.0,
            profit_factor=0.0, max_drawdown=0.0, sharpe_proxy=0.0,
            precision_positive=0.0,
            avoided_loss_mean_ret=(
                float(np.nanmean(rejected_returns))
                if len(rejected_returns) else None
            ),
            notes=f"{note} · no rows accepted",
        )
    wins = (accepted_returns > 0).sum()
    losses = (accepted_returns < 0).sum()
    gross_win = accepted_returns[accepted_returns > 0].sum()
    gross_loss = -accepted_returns[accepted_returns < 0].sum()
    pf = float(gross_win / gross_loss) if gross_loss > 1e-9 else float("inf")
    curve = np.cumsum(accepted_returns)
    peak = np.maximum.accumulate(curve) if len(curve) else np.zeros_like(curve)
    dd = float(np.min(curve - peak)) if len(curve) else 0.0
    sd = float(np.std(accepted_returns, ddof=0))
    sharpe = (float(np.mean(accepted_returns)) / sd) if sd > 1e-9 else 0.0
    return BaselineResult(
        name=name,
        threshold=threshold,
        n_rows=n_total,
        n_accepted=n_acc,
        hit_rate=float(wins / n_acc),
        mean_return=float(np.mean(accepted_returns)),
        median_return=float(np.median(accepted_returns)),
        profit_factor=float(pf if np.isfinite(pf) else 1e9),
        max_drawdown=dd,
        sharpe_proxy=sharpe,
        precision_positive=float(wins / max(1, wins + losses)),
        avoided_loss_mean_ret=(
            float(np.nanmean(rejected_returns))
            if len(rejected_returns) else None
        ),
        notes=note,
    )


def _empty(note: str) -> BaselineResult:
    return BaselineResult(
        name="none", threshold=0.0, n_rows=0, n_accepted=0,
        hit_rate=0.0, mean_return=0.0, median_return=0.0,
        profit_factor=0.0, max_drawdown=0.0, sharpe_proxy=0.0,
        precision_positive=0.0, avoided_loss_mean_ret=None,
        notes=note,
    )
