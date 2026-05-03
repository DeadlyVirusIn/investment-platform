"""Exit strategy simulator — research only, never mutates trades.

Applies candidate exit rules to a per-trade forward-bar window and reports
stats per strategy. Caller supplies OHLC bars.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class ExitStrategyResult:
    name: str
    n_trades: int
    mean_return: float
    median_return: float
    hit_rate: float
    max_adverse_mean: float
    max_favorable_mean: float
    profit_factor: float
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "n_trades": self.n_trades,
            "mean_return": round(self.mean_return, 6),
            "median_return": round(self.median_return, 6),
            "hit_rate": round(self.hit_rate, 4),
            "max_adverse_mean": round(self.max_adverse_mean, 6),
            "max_favorable_mean": round(self.max_favorable_mean, 6),
            "profit_factor": round(self.profit_factor, 4),
            "note": self.note,
        }


def simulate_exits(
    trades: list[dict[str, Any]],
    forward_bars: dict[str, pd.DataFrame],
    *,
    horizons: tuple[int, ...] = (1, 3, 5, 10),
    atr_multiples: tuple[float, ...] = (1.5, 2.5),
    trailing_atr_mult: float = 2.0,
    partial_tp_pct: float = 0.05,
) -> list[ExitStrategyResult]:
    """`trades` = [{trade_id, symbol, entry_date, entry_price, atr}, …]

    `forward_bars` = {symbol: DataFrame(date, close, high, low)} covering
    at least max(horizons) bars after each entry_date.
    """
    current = _stat(trades, forward_bars, rule=_current_exit,
                      name="current_exit_5d")
    time_exits = [
        _stat(trades, forward_bars, rule=_time_exit(h),
              name=f"time_exit_{h}d")
        for h in horizons
    ]
    atr_stops = [
        _stat(trades, forward_bars, rule=_atr_stop(m),
              name=f"atr_stop_{m}x")
        for m in atr_multiples
    ]
    trailing = _stat(
        trades, forward_bars,
        rule=_trailing_stop(trailing_atr_mult),
        name=f"trailing_atr_{trailing_atr_mult}x",
    )
    partial = _stat(
        trades, forward_bars,
        rule=_partial_profit(partial_tp_pct),
        name=f"partial_tp_{int(partial_tp_pct*100)}pct",
    )
    return [current, *time_exits, *atr_stops, trailing, partial]


# ---------------------------------------------------------------------------
# exit rules
# ---------------------------------------------------------------------------

def _current_exit(bars: pd.DataFrame, entry: float, atr: float):
    # Treat "current" as fixed 5d close — matches production default.
    window = bars.head(5)
    if window.empty:
        return None
    return (float(window["close"].iloc[-1]) / entry) - 1.0


def _time_exit(days: int):
    def rule(bars: pd.DataFrame, entry: float, atr: float):
        window = bars.head(days)
        if window.empty or len(window) < days:
            return None
        return (float(window["close"].iloc[-1]) / entry) - 1.0
    return rule


def _atr_stop(mult: float):
    def rule(bars: pd.DataFrame, entry: float, atr: float):
        stop_price = entry - mult * atr
        for _, r in bars.iterrows():
            low = float(r["low"])
            if low <= stop_price:
                return (stop_price / entry) - 1.0
        # Timeout at last close
        if bars.empty:
            return None
        return (float(bars["close"].iloc[-1]) / entry) - 1.0
    return rule


def _trailing_stop(mult: float):
    def rule(bars: pd.DataFrame, entry: float, atr: float):
        peak = entry
        for _, r in bars.iterrows():
            high = float(r["high"])
            low  = float(r["low"])
            if high > peak:
                peak = high
            trail = peak - mult * atr
            if low <= trail:
                return (trail / entry) - 1.0
        if bars.empty:
            return None
        return (float(bars["close"].iloc[-1]) / entry) - 1.0
    return rule


def _partial_profit(target_pct: float):
    def rule(bars: pd.DataFrame, entry: float, atr: float):
        target = entry * (1.0 + target_pct)
        hit = False
        for _, r in bars.iterrows():
            if float(r["high"]) >= target:
                hit = True
                break
        if hit:
            # 50% at target, rest at final close
            final = (
                (float(bars["close"].iloc[-1]) / entry) - 1.0
                if not bars.empty else 0.0
            )
            tp = (target / entry) - 1.0
            return 0.5 * tp + 0.5 * final
        if bars.empty:
            return None
        return (float(bars["close"].iloc[-1]) / entry) - 1.0
    return rule


# ---------------------------------------------------------------------------
def _stat(
    trades, forward_bars, *, rule, name: str,
) -> ExitStrategyResult:
    rets: list[float] = []
    maes: list[float] = []
    mfes: list[float] = []
    for t in trades:
        sym = t["symbol"]
        bars = forward_bars.get(sym)
        if bars is None or bars.empty:
            continue
        entry = float(t.get("entry_price") or 0)
        atr = float(t.get("atr") or entry * 0.02)
        r = rule(bars, entry, atr)
        if r is None:
            continue
        rets.append(r)
        low_min = float(bars["low"].min()) if not bars.empty else entry
        high_max = float(bars["high"].max()) if not bars.empty else entry
        maes.append((low_min / entry) - 1.0)
        mfes.append((high_max / entry) - 1.0)
    if not rets:
        return ExitStrategyResult(
            name=name, n_trades=0, mean_return=0.0, median_return=0.0,
            hit_rate=0.0, max_adverse_mean=0.0, max_favorable_mean=0.0,
            profit_factor=0.0, note="no trades with available bars",
        )
    arr = np.array(rets, dtype=float)
    wins = float((arr > 0).mean())
    gw = float(arr[arr > 0].sum())
    gl = -float(arr[arr < 0].sum())
    pf = gw / gl if gl > 1e-9 else float("inf")
    return ExitStrategyResult(
        name=name, n_trades=len(rets),
        mean_return=float(arr.mean()),
        median_return=float(np.median(arr)),
        hit_rate=wins,
        max_adverse_mean=float(np.mean(maes)),
        max_favorable_mean=float(np.mean(mfes)),
        profit_factor=(float(pf) if np.isfinite(pf) else 1e9),
    )
