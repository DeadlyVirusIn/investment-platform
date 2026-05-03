"""Credit features — credit_stable (HY OAS 20d change, HYG fallback)."""

from __future__ import annotations

import datetime as dt

import pandas as pd

FEATURE_VERSION = "v1.0.0"


def compute_credit_stable(
    hy_oas: pd.Series | None, hyg: pd.Series | None, as_of: dt.date,
) -> bool | None:
    """Primary: HY OAS 20d change <= 0. Fallback when HY OAS missing: HYG 20d return >= 0."""
    # Primary
    if hy_oas is not None and not hy_oas.empty:
        s = hy_oas.loc[:as_of]
        if len(s) >= 21 and pd.notna(s.iloc[-1]):
            return float(s.iloc[-1] - s.iloc[-21]) <= 0
    # Fallback
    if hyg is not None and not hyg.empty:
        s = hyg.loc[:as_of]
        if len(s) >= 21 and pd.notna(s.iloc[-1]):
            return float(s.iloc[-1] / s.iloc[-21] - 1) >= 0
    return None
