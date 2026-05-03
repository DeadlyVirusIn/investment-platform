"""Metrics for ML research evaluation.

Primary decision metric: Sharpe uplift vs deterministic baseline.
Secondary: max-drawdown delta, trade count reduction.
Informational: AUC, logloss, Bailey-López de Prado DSR, Brier.
"""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean, stdev

import numpy as np
import pandas as pd
from loguru import logger
from scipy import stats
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

TRADING_DAYS = 252


# ---------------------------------------------------------------------------
# Classification metrics (informational only)
# ---------------------------------------------------------------------------


def cv_auc_logloss(
    y_true: np.ndarray, y_proba: np.ndarray,
) -> dict[str, float]:
    if len(np.unique(y_true)) < 2:
        logger.warning("[metrics] degenerate y_true, AUC undefined")
        return {"auc": float("nan"), "logloss": float("nan"), "brier": float("nan")}
    auc = roc_auc_score(y_true, y_proba)
    ll = log_loss(y_true, y_proba, labels=[0, 1])
    brier = brier_score_loss(y_true, y_proba)
    return {"auc": auc, "logloss": ll, "brier": brier}


# ---------------------------------------------------------------------------
# Trading metrics (primary decision)
# ---------------------------------------------------------------------------


def _sharpe(daily_returns: list[float]) -> float:
    if len(daily_returns) < 5:
        return 0.0
    m = mean(daily_returns)
    s = stdev(daily_returns) if len(daily_returns) > 1 else 0.0
    if s == 0:
        return 0.0
    return (m / s) * math.sqrt(TRADING_DAYS)


def _max_drawdown_pct(daily_returns: list[float]) -> float:
    if not daily_returns:
        return 0.0
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in daily_returns:
        equity *= (1.0 + r)
        if equity > peak:
            peak = equity
        dd = (equity - peak) / peak
        if dd < max_dd:
            max_dd = dd
    return max_dd * 100.0


def simulate_filtered_sharpe(
    df: pd.DataFrame,
    proba: np.ndarray,
    threshold: float,
) -> dict[str, float]:
    """Simulate daily PnL when ML filters Buys at proba >= threshold.

    Expects df columns: as_of_date, forward_return_pct, barrier_n_bars.
    Baseline = unfiltered (all Buys).
    """
    assert len(df) == len(proba)
    df = df.copy()
    df["_proba"] = proba
    df["_daily_ret"] = (
        df["forward_return_pct"].astype(float) / 100.0
    ) / df["barrier_n_bars"].clip(lower=1)

    # Baseline (all Buys)
    by_day_base: dict[object, list[float]] = defaultdict(list)
    for _, r in df.iterrows():
        by_day_base[r["as_of_date"]].append(r["_daily_ret"])
    base_rets = [
        sum(v) / max(1, len(v)) for _, v in sorted(by_day_base.items())
    ]

    # Filtered
    mask = df["_proba"] >= threshold
    filt = df[mask]
    by_day_f: dict[object, list[float]] = defaultdict(list)
    for _, r in filt.iterrows():
        by_day_f[r["as_of_date"]].append(r["_daily_ret"])
    filt_rets = [
        sum(v) / max(1, len(v)) for _, v in sorted(by_day_f.items())
    ]

    base_sharpe = _sharpe(base_rets)
    filt_sharpe = _sharpe(filt_rets)
    base_dd = _max_drawdown_pct(base_rets)
    filt_dd = _max_drawdown_pct(filt_rets)

    return {
        "threshold": threshold,
        "baseline_trade_count": len(df),
        "filtered_trade_count": int(mask.sum()),
        "trade_reduction_frac": (
            1.0 - (mask.sum() / max(1, len(df)))
        ),
        "baseline_sharpe": round(base_sharpe, 4),
        "filtered_sharpe": round(filt_sharpe, 4),
        "sharpe_uplift": round(filt_sharpe - base_sharpe, 4),
        "baseline_max_dd_pct": round(base_dd, 4),
        "filtered_max_dd_pct": round(filt_dd, 4),
        "dd_delta_pct": round(filt_dd - base_dd, 4),
    }


# ---------------------------------------------------------------------------
# DSR (informational)
# ---------------------------------------------------------------------------


def bailey_dsr(
    sharpe: float, n_trials: int, n_obs: int,
    skew: float = 0.0, kurt: float = 3.0,
) -> float:
    """Bailey-López de Prado Deflated Sharpe Ratio (probability that true
    Sharpe > 0 given observed sharpe over n_obs samples, deflating for
    n_trials backtests tried). Informational — do not gate on this.
    """
    if n_obs < 2 or n_trials < 1:
        return 0.0
    emc = 0.5772156649
    sr_max_expected = math.sqrt(2 * math.log(max(n_trials, 2)))
    sr_max_expected -= emc / math.sqrt(2 * math.log(max(n_trials, 2)))
    var_sr = (
        1 - skew * sharpe + ((kurt - 1) / 4) * sharpe ** 2
    ) / (n_obs - 1)
    if var_sr <= 0:
        return 0.0
    z = (sharpe - sr_max_expected) / math.sqrt(var_sr)
    return float(stats.norm.cdf(z))
