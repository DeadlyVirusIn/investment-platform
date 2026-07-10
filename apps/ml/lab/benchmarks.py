"""Naive benchmarks every Experiment Lab study is compared against.

Pure functions over price series / label arrays. Deterministic: momentum
ranking ties break on column name, never on incidental row order. Metrics
only — a benchmark here is a comparison floor, not a strategy.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

MOMENTUM_LOOKBACK_MONTHS = 12
MOMENTUM_SKIP_MONTHS = 1


def buy_and_hold_return(prices: Sequence[float] | pd.Series) -> float:
    """Total return of holding from the first to the last price."""
    p = np.asarray(list(prices), dtype=float)
    if p.size < 2:
        raise ValueError("need at least 2 prices")
    if p[0] <= 0:
        raise ValueError(f"non-positive starting price: {p[0]}")
    return float(p[-1] / p[0] - 1.0)


def momentum_12_1_signal(
    monthly_prices: pd.DataFrame,
    lookback: int = MOMENTUM_LOOKBACK_MONTHS,
    skip: int = MOMENTUM_SKIP_MONTHS,
) -> pd.DataFrame:
    """Classic 12-1 momentum: return over the lookback window excluding
    the most recent `skip` months. Rows = month-ends ascending, columns =
    assets. signal_t = P_{t-skip} / P_{t-lookback} − 1; NaN where history
    is insufficient."""
    if skip >= lookback:
        raise ValueError(f"skip ({skip}) must be < lookback ({lookback})")
    return monthly_prices.shift(skip) / monthly_prices.shift(lookback) - 1.0


def momentum_12_1_portfolio_returns(
    monthly_prices: pd.DataFrame,
    top_frac: float = 0.5,
    lookback: int = MOMENTUM_LOOKBACK_MONTHS,
    skip: int = MOMENTUM_SKIP_MONTHS,
) -> pd.Series:
    """Equal-weight the top `top_frac` of assets by 12-1 signal each
    month; hold for the following month. Returns the monthly portfolio
    return series (months with no usable signal or no forward bar are
    omitted)."""
    if not 0.0 < top_frac <= 1.0:
        raise ValueError(f"top_frac must be in (0, 1], got {top_frac}")
    signal = momentum_12_1_signal(monthly_prices, lookback=lookback, skip=skip)
    fwd = monthly_prices.pct_change().shift(-1)  # next month's return

    out: dict[object, float] = {}
    for t in monthly_prices.index:
        sig_row = signal.loc[t].dropna()
        if sig_row.empty:
            continue
        n_pick = max(1, int(np.ceil(top_frac * len(sig_row))))
        # deterministic tie-break: sort by (-signal, column name)
        ranked = sorted(sig_row.items(), key=lambda kv: (-kv[1], str(kv[0])))
        picks = [name for name, _ in ranked[:n_pick]]
        fwd_row = fwd.loc[t, picks].dropna()
        if fwd_row.empty:
            continue
        out[t] = float(fwd_row.mean())
    return pd.Series(out, dtype=float)


def base_rate_brier(y_true, base_rate: float | None = None) -> float:
    """Brier score of the constant classifier predicting `base_rate` for
    every row. base_rate=None uses the in-sample mean of y_true — that is
    hindsight and only valid as a reference floor; pass the TRAIN base
    rate for an honest out-of-sample benchmark."""
    y = np.asarray(list(y_true), dtype=float)
    if y.size == 0:
        raise ValueError("empty y_true")
    rate = float(y.mean()) if base_rate is None else float(base_rate)
    if not 0.0 <= rate <= 1.0:
        raise ValueError(f"base_rate must be in [0, 1], got {rate}")
    return float(np.mean((rate - y) ** 2))
