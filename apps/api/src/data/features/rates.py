"""Rates features — d10y_5d, rates_calm."""

from __future__ import annotations

import datetime as dt

import pandas as pd

FEATURE_VERSION = "v1.0.0"


def compute_d10y_5d(dgs10: pd.Series, as_of: dt.date) -> float | None:
    """DGS10(t) - DGS10(t-5). Requires observations ending on or before as_of.
    Returns None when insufficient history."""
    if dgs10.empty: return None
    s = dgs10.loc[:as_of]
    if len(s) < 6: return None
    return float(s.iloc[-1] - s.iloc[-6])


def compute_rates_calm(dgs10: pd.Series, as_of: dt.date) -> bool | None:
    """rates_calm = d10y_5d < 0  (rates direction favorable)."""
    v = compute_d10y_5d(dgs10, as_of)
    if v is None: return None
    return v < 0
