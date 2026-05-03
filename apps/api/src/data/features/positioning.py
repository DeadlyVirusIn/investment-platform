"""Positioning features — gex_sign, cot_extreme_flag. DIAGNOSTIC / CANDIDATE ONLY."""

from __future__ import annotations

import datetime as dt

import pandas as pd

FEATURE_VERSION = "v0.1.0"


def compute_gex_sign(gex: pd.Series, as_of: dt.date) -> int | None:
    """gex_sign ∈ {+1, -1}. DIAGNOSTIC — never wired to strategy."""
    s = gex.loc[:as_of]
    if s.empty or pd.isna(s.iloc[-1]): return None
    return 1 if float(s.iloc[-1]) > 0 else -1


def compute_cot_extreme_flag(
    cot_noncomm_net: pd.Series, as_of: dt.date,
    extreme_pct: float = 0.1,
) -> bool | None:
    """CANDIDATE — flag when net positioning in top/bottom extreme_pct of history."""
    s = cot_noncomm_net.loc[:as_of].dropna()
    if len(s) < 100: return None
    cur = float(s.iloc[-1])
    hi = s.quantile(1 - extreme_pct)
    lo = s.quantile(extreme_pct)
    return cur >= hi or cur <= lo
