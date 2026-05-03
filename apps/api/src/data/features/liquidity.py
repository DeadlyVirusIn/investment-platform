"""Fed net liquidity — liquidity_expanding."""

from __future__ import annotations

import datetime as dt

import pandas as pd

FEATURE_VERSION = "v1.0.0"


def compute_fed_net_liquidity(
    walcl: pd.Series, wtregen: pd.Series, rrp: pd.Series, as_of: dt.date,
) -> float | None:
    """WALCL - WTREGEN - RRPONTSYD at as_of (forward-filled to daily)."""
    def _lookup(s: pd.Series) -> float | None:
        s2 = s.loc[:as_of]
        return float(s2.iloc[-1]) if not s2.empty and pd.notna(s2.iloc[-1]) else None
    w = _lookup(walcl); t = _lookup(wtregen); r = _lookup(rrp)
    if w is None or t is None or r is None: return None
    return w - t - r


def compute_liquidity_expanding(
    walcl: pd.Series, wtregen: pd.Series, rrp: pd.Series, as_of: dt.date,
    lookback_days: int = 20,
) -> bool | None:
    now = compute_fed_net_liquidity(walcl, wtregen, rrp, as_of)
    past = compute_fed_net_liquidity(
        walcl, wtregen, rrp, as_of - dt.timedelta(days=lookback_days),
    )
    if now is None or past is None: return None
    return (now - past) > 0
