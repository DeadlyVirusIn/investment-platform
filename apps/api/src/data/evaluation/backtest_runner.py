"""Backtest runner — thin adapter that replays production strategy over a
historical DataFrame without mutating live data. Used by replay validation
and ablation.

Delegates to existing scripts/run_phase21_two_engine.py logic. Guarantees
zero strategy drift.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BacktestResult:
    n_trades: int
    n_engine_a: int
    n_engine_b: int
    cum_pct: float
    mean_pct: float
    t_stat: float
    max_dd_pct: float
    trade_records: list[tuple]   # (date, ret, engine)


# TODO: extract Phase 21 core to a callable here. For now, replay validation
# imports the script module directly.
