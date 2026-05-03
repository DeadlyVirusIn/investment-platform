"""Vol features — VRP, ts_ratio."""

from __future__ import annotations

import datetime as dt
import math

import pandas as pd

FEATURE_VERSION = "v1.0.0"


def compute_vrp(
    vix: pd.Series, spy: pd.Series, as_of: dt.date,
    rv_window: int = 21,
) -> float | None:
    """VRP = VIX² − annualized realized variance² (both as % points)."""
    vx = vix.loc[:as_of]
    sx = spy.loc[:as_of]
    if len(vx) < 1 or len(sx) < rv_window + 1: return None
    daily_ret = sx.pct_change().dropna()
    rv21 = daily_ret.tail(rv_window).std() * math.sqrt(252) * 100  # %
    vix_t = float(vx.iloc[-1])
    return (vix_t ** 2) - (rv21 ** 2)


def compute_vrp_supportive(
    vix: pd.Series, spy: pd.Series, as_of: dt.date,
    window_bars: int = 126,
) -> bool | None:
    """vrp_supportive = VRP > rolling 6M median."""
    # Compute VRP for last N bars ending at as_of
    sx = spy.loc[:as_of]
    vx = vix.loc[:as_of]
    if len(sx) < 22 or len(vx) < 1: return None
    # Build recent VRP series
    daily_ret = sx.pct_change()
    rv21 = daily_ret.rolling(21).std() * math.sqrt(252) * 100
    aligned_vix = vx.reindex(rv21.index).ffill()
    vrp_series = (aligned_vix ** 2) - (rv21 ** 2)
    vrp_series = vrp_series.dropna().tail(window_bars)
    if len(vrp_series) < 30: return None
    return bool(vrp_series.iloc[-1] > vrp_series.median())


def compute_ts_ratio(
    vix: pd.Series, vix3m: pd.Series, as_of: dt.date,
) -> float | None:
    """ts_ratio = VIX / VIX3M. CANDIDATE feature (Phase X2 failed)."""
    v1 = vix.loc[:as_of]; v3 = vix3m.loc[:as_of]
    if v1.empty or v3.empty: return None
    n = float(v1.iloc[-1]); d = float(v3.iloc[-1])
    return n / d if d != 0 else None
