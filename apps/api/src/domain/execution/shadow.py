"""Shadow execution framework.

Compares three strategies in parallel on the SAME input stream:

  1. baseline    — size=1.0 on every trade (no sizing, no regime gating)
  2. normalized  — normalized_size * regime_multiplier
  3. kelly       — kelly_size * regime_multiplier

Pure observation. NO decision logic. NO auto-selection of best strategy.
Metrics only. Caller decides what to do with the comparison.

No DB writes. No live-table modification. Safe to run in shadow.
"""

from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import fmean, pstdev

from apps.api.src.domain.execution.integrator import (
    FinalAction,
    PrimarySignal,
    execute_batch,
)
from apps.api.src.domain.execution.regime import (
    RegimeSignal,
    classify_regime,
)
from apps.api.src.domain.execution.sizing import MAX_POSITION_SIZE


STRATEGIES: tuple[str, ...] = ("baseline", "normalized", "kelly")

TRADING_DAYS_PER_YEAR: int = 252


# ---------------------------------------------------------------------------
# Per-primary realized return (for PnL attribution)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PrimaryWithReturn:
    """A PrimarySignal augmented with the realized forward return used for
    PnL attribution. `forward_return_pct` is the terminal return over
    `barrier_n_bars` bars (e.g. 5.0 = +5% over holding horizon).
    """

    primary: PrimarySignal
    forward_return_pct: float
    barrier_n_bars: int


# ---------------------------------------------------------------------------
# Day snapshot + aggregates
# ---------------------------------------------------------------------------


@dataclass
class ShadowDay:
    """Single-day observation across all three strategies."""

    date: dt.date
    regime: RegimeSignal
    n_trades: int
    # Per-strategy
    sizes: dict[str, list[float]] = field(default_factory=dict)
    daily_return: dict[str, float] = field(default_factory=dict)
    avg_position_size: dict[str, float] = field(default_factory=dict)
    total_exposure: dict[str, float] = field(default_factory=dict)
    actions_normalized: list[FinalAction] = field(default_factory=list)
    actions_kelly: list[FinalAction] = field(default_factory=list)


@dataclass
class StrategyMetrics:
    """Aggregate metrics for a single strategy over a shadow window."""

    strategy_name: str
    n_days: int
    n_trades_total: int
    daily_returns: list[float]
    cumulative_return: float
    sharpe: float
    max_drawdown_pct: float
    turnover: float
    avg_position_size: float
    avg_total_exposure: float


# ---------------------------------------------------------------------------
# Per-day computation
# ---------------------------------------------------------------------------


def _per_bar_return(forward_return_pct: float, n_bars: int) -> float:
    """Convert terminal return over n_bars into per-bar return (amortize)."""
    if n_bars <= 0:
        return 0.0
    return (forward_return_pct / 100.0) / n_bars


def _compute_daily_return(
    primaries_with_returns: list[PrimaryWithReturn],
    sizes: list[float],
) -> float:
    """Equal-weighted daily portfolio return given per-trade sizes.

    If total_size = 0, return 0 (no exposure day).
    """
    assert len(primaries_with_returns) == len(sizes)
    if not primaries_with_returns:
        return 0.0
    total_size = sum(sizes)
    if total_size <= 0:
        return 0.0
    weighted = 0.0
    for pr, size in zip(primaries_with_returns, sizes):
        if size <= 0:
            continue
        per_bar = _per_bar_return(pr.forward_return_pct, pr.barrier_n_bars)
        weighted += size * per_bar
    return weighted / total_size


def run_shadow_day(
    date: dt.date,
    primaries_with_returns: list[PrimaryWithReturn],
    market_prices: list[float],
    *,
    max_size: float = MAX_POSITION_SIZE,
) -> ShadowDay:
    """Compute all three strategies for one day. No DB writes."""
    primaries = [p.primary for p in primaries_with_returns]
    regime = classify_regime(market_prices)

    # Strategy 1: baseline = 1.0 flat, no regime gating
    baseline_sizes = [1.0 for _ in primaries]

    # Strategies 2 & 3: use integrator (applies regime gating)
    act_norm = execute_batch(primaries, market_prices, method="normalized", max_size=max_size)
    act_kelly = execute_batch(primaries, market_prices, method="kelly", max_size=max_size)
    norm_sizes = [a.final_size for a in act_norm]
    kelly_sizes = [a.final_size for a in act_kelly]

    # Daily returns
    ret_baseline = _compute_daily_return(primaries_with_returns, baseline_sizes)
    ret_norm = _compute_daily_return(primaries_with_returns, norm_sizes)
    ret_kelly = _compute_daily_return(primaries_with_returns, kelly_sizes)

    def _avg(xs: list[float]) -> float:
        return fmean(xs) if xs else 0.0

    return ShadowDay(
        date=date,
        regime=regime,
        n_trades=len(primaries),
        sizes={
            "baseline": baseline_sizes,
            "normalized": norm_sizes,
            "kelly": kelly_sizes,
        },
        daily_return={
            "baseline": ret_baseline,
            "normalized": ret_norm,
            "kelly": ret_kelly,
        },
        avg_position_size={
            "baseline": _avg(baseline_sizes),
            "normalized": _avg(norm_sizes),
            "kelly": _avg(kelly_sizes),
        },
        total_exposure={
            "baseline": sum(baseline_sizes),
            "normalized": sum(norm_sizes),
            "kelly": sum(kelly_sizes),
        },
        actions_normalized=act_norm,
        actions_kelly=act_kelly,
    )


# ---------------------------------------------------------------------------
# Aggregate metrics across a window of shadow days
# ---------------------------------------------------------------------------


def _sharpe(daily_returns: list[float]) -> float:
    if len(daily_returns) < 5:
        return 0.0
    m = fmean(daily_returns)
    s = pstdev(daily_returns) if len(daily_returns) > 1 else 0.0
    if s == 0:
        return 0.0
    return (m / s) * math.sqrt(TRADING_DAYS_PER_YEAR)


def _max_drawdown_pct(daily_returns: list[float]) -> float:
    """Worst peak-to-trough drawdown in percent (negative number)."""
    if not daily_returns:
        return 0.0
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in daily_returns:
        equity *= 1.0 + r
        if equity > peak:
            peak = equity
        dd = (equity - peak) / peak
        if dd < max_dd:
            max_dd = dd
    return max_dd * 100.0


def _cumulative_return(daily_returns: list[float]) -> float:
    """Compounded total return expressed as fraction (e.g. 0.05 = +5%)."""
    equity = 1.0
    for r in daily_returns:
        equity *= 1.0 + r
    return equity - 1.0


def _turnover(days: list[ShadowDay], strategy: str) -> float:
    """Mean day-over-day absolute change in total exposure, normalized by
    average exposure. 0 == no turnover; 1.0 == portfolio fully rebuilt each day.
    """
    if len(days) < 2:
        return 0.0
    exposures = [d.total_exposure.get(strategy, 0.0) for d in days]
    deltas = [abs(exposures[i] - exposures[i - 1]) for i in range(1, len(exposures))]
    avg_exposure = fmean(exposures) if exposures else 0.0
    if avg_exposure <= 0:
        return 0.0
    return fmean(deltas) / avg_exposure


def aggregate_metrics(
    days: list[ShadowDay], strategy: str,
) -> StrategyMetrics:
    daily_returns = [d.daily_return.get(strategy, 0.0) for d in days]
    avg_sizes = [d.avg_position_size.get(strategy, 0.0) for d in days]
    exposures = [d.total_exposure.get(strategy, 0.0) for d in days]
    n_trades = sum(d.n_trades for d in days)

    return StrategyMetrics(
        strategy_name=strategy,
        n_days=len(days),
        n_trades_total=n_trades,
        daily_returns=daily_returns,
        cumulative_return=round(_cumulative_return(daily_returns), 6),
        sharpe=round(_sharpe(daily_returns), 4),
        max_drawdown_pct=round(_max_drawdown_pct(daily_returns), 4),
        turnover=round(_turnover(days, strategy), 4),
        avg_position_size=round(fmean(avg_sizes), 6) if avg_sizes else 0.0,
        avg_total_exposure=round(fmean(exposures), 4) if exposures else 0.0,
    )


def aggregate_all(days: list[ShadowDay]) -> dict[str, StrategyMetrics]:
    return {s: aggregate_metrics(days, s) for s in STRATEGIES}


# ---------------------------------------------------------------------------
# Shadow logging (per-day, structured line)
# ---------------------------------------------------------------------------


def format_day_log(day: ShadowDay) -> str:
    """One-line structured log entry for a single shadow day. Pure string;
    caller decides how to emit (logger, stdout, file).
    """
    parts = [
        f"date={day.date}",
        f"regime={day.regime.regime}",
        f"regime_mult={day.regime.multiplier}",
        f"n_trades={day.n_trades}",
    ]
    for s in STRATEGIES:
        parts.append(f"{s}_avg_size={day.avg_position_size.get(s, 0.0):.4f}")
        parts.append(f"{s}_total_exposure={day.total_exposure.get(s, 0.0):.4f}")
        parts.append(f"{s}_daily_return={day.daily_return.get(s, 0.0):+.6f}")
    return "[shadow] " + " ".join(parts)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


@dataclass
class ComparisonReport:
    metrics: dict[str, StrategyMetrics]
    table: str


def compare_strategies(
    metrics_baseline: StrategyMetrics,
    metrics_normalized: StrategyMetrics,
    metrics_kelly: StrategyMetrics,
) -> ComparisonReport:
    """Produce a side-by-side comparison table. Observation only — does
    NOT recommend a winner.
    """
    cols = ("baseline", "normalized", "kelly")
    m = {
        "baseline": metrics_baseline,
        "normalized": metrics_normalized,
        "kelly": metrics_kelly,
    }

    header = f"{'Metric':<24s}" + "".join(f"{c:>14s}" for c in cols)
    sep = "-" * len(header)

    def _row(name: str, fn) -> str:
        return f"{name:<24s}" + "".join(f"{fn(m[c]):>14}" for c in cols)

    lines = [header, sep]
    lines.append(_row("n_days", lambda x: str(x.n_days)))
    lines.append(_row("n_trades_total", lambda x: str(x.n_trades_total)))
    lines.append(_row("cumulative_return", lambda x: f"{x.cumulative_return:+.4f}"))
    lines.append(_row("sharpe (annualized)", lambda x: f"{x.sharpe:+.4f}"))
    lines.append(_row("max_drawdown_pct", lambda x: f"{x.max_drawdown_pct:+.4f}"))
    lines.append(_row("turnover", lambda x: f"{x.turnover:.4f}"))
    lines.append(_row("avg_position_size", lambda x: f"{x.avg_position_size:.4f}"))
    lines.append(_row("avg_total_exposure", lambda x: f"{x.avg_total_exposure:.4f}"))
    table = "\n".join(lines)
    return ComparisonReport(metrics=m, table=table)
