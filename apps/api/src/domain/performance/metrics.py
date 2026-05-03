"""Performance metrics over a list of trade returns.

Deterministic on Decimal inputs. Uses empyrical-reloaded for Sharpe/Sortino/
Calmar/max_drawdown with proper handling of NaN/inf edge cases (all-wins,
all-losses, single trade).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any


@dataclass
class Metrics:
    total_trades: int
    wins: int
    losses: int
    neutral: int
    win_rate: Decimal | None
    expectancy: Decimal | None
    profit_factor: Decimal | None
    total_return: Decimal | None
    sharpe_ratio: Decimal | None
    sortino_ratio: Decimal | None
    calmar_ratio: Decimal | None
    max_drawdown: Decimal | None
    max_drawdown_duration: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _empty_metrics() -> Metrics:
    return Metrics(
        total_trades=0, wins=0, losses=0, neutral=0,
        win_rate=None, expectancy=None, profit_factor=None,
        total_return=None, sharpe_ratio=None, sortino_ratio=None,
        calmar_ratio=None, max_drawdown=None, max_drawdown_duration=None,
    )


def _sanitize_float(x: object) -> Decimal | None:
    """Convert numpy/float → Decimal, dropping NaN/inf."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return Decimal(str(f))


def _compound(returns: list[Decimal]) -> list[Decimal]:
    """Equity curve starting at 1.0; equity[i] after trade i."""
    eq = [Decimal("1")]
    for r in returns:
        eq.append(eq[-1] * (Decimal("1") + r))
    return eq


def _max_drawdown_duration(equity: list[Decimal]) -> int:
    """Longest streak of consecutive bars strictly below a prior peak."""
    if not equity:
        return 0
    running_peak = equity[0]
    underwater_start: int | None = None
    longest = 0
    for i, v in enumerate(equity):
        if v >= running_peak:
            if underwater_start is not None:
                longest = max(longest, i - underwater_start)
                underwater_start = None
            running_peak = v
        elif underwater_start is None:
            underwater_start = i
    if underwater_start is not None:
        longest = max(longest, len(equity) - underwater_start)
    return longest


def compute_metrics(
    returns: list[Decimal],
    labels: list[int],
    annualization: int = 12,
) -> Metrics:
    """Return trade-level performance metrics.

    Args:
        returns:  list of per-trade returns (fractions; e.g. 0.05 = +5%).
        labels:   parallel list of barrier labels (-1, 0, +1).
        annualization: periods per year for Sharpe/Sortino/Calmar
                       (12 for ~30d windows; 4 for 90d).
    """
    n = len(returns)
    if n == 0:
        return _empty_metrics()
    if len(labels) != n:
        raise ValueError("returns and labels must have same length")

    wins = sum(1 for l in labels if l == 1)
    losses = sum(1 for l in labels if l == -1)
    neutral = sum(1 for l in labels if l == 0)

    total_return = None
    equity = _compound(returns)
    total_return = equity[-1] - Decimal("1")

    expectancy = sum(returns, Decimal("0")) / Decimal(n)
    win_rate = Decimal(wins) / Decimal(n)

    pos_sum = sum((r for r in returns if r > 0), Decimal("0"))
    neg_sum = sum((abs(r) for r in returns if r < 0), Decimal("0"))
    profit_factor = (pos_sum / neg_sum) if neg_sum > 0 else None

    # empyrical-reloaded for vol-adjusted ratios + max_drawdown
    sharpe = sortino = calmar = max_dd = None
    if n >= 2:
        try:
            import empyrical
            import pandas as pd

            rs = pd.Series([float(r) for r in returns])
            sharpe = _sanitize_float(
                empyrical.sharpe_ratio(rs, annualization=annualization)
            )
            sortino = _sanitize_float(
                empyrical.sortino_ratio(rs, annualization=annualization)
            )
            calmar = _sanitize_float(
                empyrical.calmar_ratio(rs, annualization=annualization)
            )
            max_dd = _sanitize_float(empyrical.max_drawdown(rs))
        except ImportError:
            # Fallback: compute Sharpe and max_dd manually in pure Decimal.
            sharpe = _sharpe_manual(returns, annualization)
            max_dd = _max_drawdown_manual(equity)

    # Normalize "no drawdown" to None for both magnitude and duration.
    if max_dd is not None and max_dd >= Decimal("0"):
        max_dd = None

    dd_duration = _max_drawdown_duration(equity) if equity else 0

    return Metrics(
        total_trades=n,
        wins=wins,
        losses=losses,
        neutral=neutral,
        win_rate=win_rate,
        expectancy=expectancy,
        profit_factor=profit_factor,
        total_return=total_return,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        calmar_ratio=calmar,
        max_drawdown=max_dd,
        max_drawdown_duration=dd_duration if dd_duration > 0 else None,
    )


# ---------------------------------------------------------------------------
# Pure-Decimal fallbacks (used if empyrical unavailable)
# ---------------------------------------------------------------------------


def _sharpe_manual(
    returns: list[Decimal], annualization: int
) -> Decimal | None:
    from apps.api.src.domain.recommendations.outcome_labeling import (
        _decimal_sqrt,
        compute_sigma_from_returns,
    )
    if len(returns) < 2:
        return None
    sd = compute_sigma_from_returns(returns)
    if sd is None or sd == 0:
        return None
    mean = sum(returns, Decimal("0")) / Decimal(len(returns))
    ann = _decimal_sqrt(Decimal(annualization))
    return (mean / sd) * ann


def _max_drawdown_manual(equity: list[Decimal]) -> Decimal | None:
    if len(equity) < 2:
        return None
    peak = equity[0]
    worst = Decimal("0")
    for v in equity:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (v - peak) / peak
            if dd < worst:
                worst = dd
    return worst if worst < 0 else None
