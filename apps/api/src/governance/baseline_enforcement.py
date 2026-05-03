"""Baseline enforcement governance.

Compute B&H / TSMOM / MA crossover Sharpe + hit + drawdown from a price
series. Compare to system Sharpe. Emit `system_underperforming_baseline`
flag.

Read-only. No side effects. Caller invokes once per day from nightly
job (or on-demand from API).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Sequence


PERIODS_PER_YEAR = 252
COST_BPS_ROUND_TRIP = 10.0


def _pct_changes(prices: Sequence[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(prices)):
        prev = float(prices[i - 1])
        curr = float(prices[i])
        if prev == 0 or not math.isfinite(prev) or not math.isfinite(curr):
            continue
        out.append((curr / prev) - 1.0)
    return out


def _sharpe(returns: Sequence[float]) -> float:
    arr = [float(r) for r in returns
           if r is not None and math.isfinite(float(r))]
    if len(arr) < 2:
        return float("nan")
    mu = sum(arr) / len(arr)
    try:
        sd = statistics.stdev(arr)
    except statistics.StatisticsError:
        return float("nan")
    if sd == 0 or not math.isfinite(sd):
        return float("nan")
    return mu / sd * math.sqrt(PERIODS_PER_YEAR)


def _max_dd(returns: Sequence[float]) -> float:
    eq = 1.0
    peak = 1.0
    worst = 0.0
    for r in returns:
        if r is None or not math.isfinite(float(r)):
            continue
        eq *= 1 + float(r)
        peak = max(peak, eq)
        worst = min(worst, (eq - peak) / peak)
    return worst * 100.0


def _hit(returns: Sequence[float]) -> float:
    arr = [float(r) for r in returns
           if r is not None and math.isfinite(float(r))]
    if not arr:
        return 0.0
    return sum(1 for r in arr if r > 0) / len(arr)


@dataclass
class BaselineResult:
    name: str
    sharpe: float
    hit: float
    drawdown_pct: float
    total_pct: float
    n: int

    def to_dict(self) -> dict:
        def _f(v):
            return round(float(v), 4) if math.isfinite(float(v)) else None
        return {
            "name": self.name,
            "sharpe": _f(self.sharpe),
            "hit": _f(self.hit),
            "drawdown_pct": _f(self.drawdown_pct),
            "total_pct": _f(self.total_pct),
            "n": int(self.n),
        }


@dataclass
class BaselineSnapshot:
    baselines: list[BaselineResult]
    system_sharpe: float
    best_baseline_name: str
    best_baseline_sharpe: float
    delta_sharpe_vs_baseline: float
    system_underperforming_baseline: bool

    def to_dict(self) -> dict:
        return {
            "baselines": [b.to_dict() for b in self.baselines],
            "system_sharpe": round(self.system_sharpe, 4)
                                if math.isfinite(self.system_sharpe) else None,
            "best_baseline_name": self.best_baseline_name,
            "best_baseline_sharpe": round(self.best_baseline_sharpe, 4)
                                       if math.isfinite(self.best_baseline_sharpe) else None,
            "delta_sharpe_vs_baseline":
                round(self.delta_sharpe_vs_baseline, 4)
                if math.isfinite(self.delta_sharpe_vs_baseline) else None,
            "system_underperforming_baseline":
                bool(self.system_underperforming_baseline),
        }


def buy_and_hold(prices: Sequence[float]) -> BaselineResult:
    rets = _pct_changes(prices)
    return BaselineResult(
        name="buy_hold",
        sharpe=_sharpe(rets),
        hit=_hit(rets),
        drawdown_pct=_max_dd(rets),
        total_pct=(
            (float(prices[-1]) / float(prices[0]) - 1.0) * 100.0
            if len(prices) >= 2 and prices[0] else 0.0
        ),
        n=len(rets),
    )


def tsmom_long_flat(prices: Sequence[float], horizon: int,
                     cost_bps: float = COST_BPS_ROUND_TRIP) -> BaselineResult:
    """Sign(close[t]/close[t-h] − 1) → 1 long / 0 flat. 1-day forward
    return applied with t+1 lag (no lookahead). Apply round-trip cost
    when position changes."""
    if len(prices) < horizon + 2:
        return BaselineResult(
            name=f"tsmom_{horizon}d",
            sharpe=float("nan"), hit=0.0, drawdown_pct=0.0,
            total_pct=0.0, n=0,
        )
    cost = cost_bps / 1e4
    rets: list[float] = []
    prev_pos = 0
    for t in range(horizon, len(prices) - 1):
        pos = 1 if (float(prices[t]) / float(prices[t - horizon]) - 1.0) > 0 else 0
        try:
            r = (float(prices[t + 1]) / float(prices[t]) - 1.0)
        except Exception:
            continue
        applied = pos * r
        if pos != prev_pos:
            applied -= cost
        rets.append(applied)
        prev_pos = pos
    return BaselineResult(
        name=f"tsmom_{horizon}d",
        sharpe=_sharpe(rets),
        hit=_hit(rets),
        drawdown_pct=_max_dd(rets),
        total_pct=(
            ((1.0 + sum(rets) / max(1, len(rets))) ** len(rets) - 1.0) * 100.0
        ),
        n=len(rets),
    )


def ma_crossover(prices: Sequence[float],
                  fast: int = 50, slow: int = 200,
                  cost_bps: float = COST_BPS_ROUND_TRIP) -> BaselineResult:
    if len(prices) < slow + 2:
        return BaselineResult(
            name=f"ma_{fast}_{slow}",
            sharpe=float("nan"), hit=0.0, drawdown_pct=0.0,
            total_pct=0.0, n=0,
        )
    cost = cost_bps / 1e4
    rets: list[float] = []
    prev_pos = 0
    for t in range(slow, len(prices) - 1):
        ma_fast = sum(prices[t - fast:t]) / fast
        ma_slow = sum(prices[t - slow:t]) / slow
        pos = 1 if ma_fast > ma_slow else 0
        try:
            r = (float(prices[t + 1]) / float(prices[t]) - 1.0)
        except Exception:
            continue
        applied = pos * r
        if pos != prev_pos:
            applied -= cost
        rets.append(applied)
        prev_pos = pos
    return BaselineResult(
        name=f"ma_{fast}_{slow}",
        sharpe=_sharpe(rets),
        hit=_hit(rets),
        drawdown_pct=_max_dd(rets),
        total_pct=(
            ((1.0 + sum(rets) / max(1, len(rets))) ** len(rets) - 1.0) * 100.0
        ),
        n=len(rets),
    )


def compute_baselines(prices: Sequence[float]) -> list[BaselineResult]:
    return [
        buy_and_hold(prices),
        tsmom_long_flat(prices, horizon=20),
        tsmom_long_flat(prices, horizon=60),
        ma_crossover(prices, fast=50, slow=200),
    ]


def evaluate_vs_baseline(
    prices: Sequence[float], system_sharpe: float,
) -> BaselineSnapshot:
    baselines = compute_baselines(prices)
    finite_sh = [(b.name, b.sharpe) for b in baselines
                 if math.isfinite(b.sharpe)]
    if finite_sh:
        best_name, best_sh = max(finite_sh, key=lambda p: p[1])
    else:
        best_name, best_sh = "—", float("nan")
    delta = (system_sharpe - best_sh
              if math.isfinite(system_sharpe) and math.isfinite(best_sh)
              else float("nan"))
    underperform = (
        math.isfinite(delta) and delta < 0
    )
    return BaselineSnapshot(
        baselines=baselines,
        system_sharpe=system_sharpe,
        best_baseline_name=best_name,
        best_baseline_sharpe=best_sh,
        delta_sharpe_vs_baseline=delta,
        system_underperforming_baseline=underperform,
    )
