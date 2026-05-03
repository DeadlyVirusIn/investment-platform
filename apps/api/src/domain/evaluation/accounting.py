"""Phase 6.5 — standardized daily mark-to-market accounting.

Single, explicit return-attribution engine applied uniformly to:
  - pre-Phase-6 strategies (daily fresh basket)
  - Phase-6 disciplined strategies (positions may persist)

Position generation is STRATEGY-SPECIFIC and is NOT touched here. Only PnL
attribution is standardized so pre/post-discipline runs become directly
comparable.

Accounting rule (mark-to-market, close-to-close):

    daily_strategy_return_t
        = Σ_{sym} ( size_t[sym] × r_{sym, t} )  /  Σ_{sym} size_t[sym]

    where  r_{sym, t}  = (close_{t+1} − close_t) / close_t

Convention: day t's `sizes_by_symbol` represents positions held OVERNIGHT
from close of day t to close of day t+1. The daily return r_{sym, t} in
the lookup is therefore the return EARNED over (t, t+1), INDEXED by t.

- Hold K days without signal refresh → the SAME `sizes_by_symbol` gets
  repriced at each of K daily returns.
- Entry-day forward return is NEVER reused. No phantom attribution.
- Missing market data (symbol not in lookup on a given day) → that
  symbol is SKIPPED in the weighted average; size is excluded from both
  numerator and denominator (so the remaining book is still priced
  correctly).

Costs are handled by the existing turnover-based cost model and are
deducted post-MTM. This module does not touch costs.

Pure functions. No DB. No I/O. No mutation. One source of truth.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Daily-return lookup
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DailyReturnLookup:
    """Close-to-close daily returns indexed by (symbol, start_date).

    `by_symbol_date[(sym, t)]` = (close_{t+1} − close_t) / close_t
    (the return a position held from close_t to close_{t+1} earns,
    attributed to the calendar date `t`).

    Use `get(sym, t)` to fetch; returns None if not populated (calendar
    boundaries, missing bars, etc.) — caller must skip such entries.
    """

    by_symbol_date: dict[tuple[str, dt.date], float] = field(default_factory=dict)

    def get(self, symbol: str, date: dt.date) -> float | None:
        return self.by_symbol_date.get((symbol, date))

    def __contains__(self, key: tuple[str, dt.date]) -> bool:
        return key in self.by_symbol_date

    def __len__(self) -> int:
        return len(self.by_symbol_date)


# ---------------------------------------------------------------------------
# Build lookup from (symbol → list[(date, close)])
# ---------------------------------------------------------------------------


def build_daily_return_lookup(
    closes_by_symbol: dict[str, list[tuple[dt.date, float]]],
) -> DailyReturnLookup:
    """Construct a DailyReturnLookup from per-symbol close series.

    Each input series MUST be ordered ascending by date. Duplicates /
    non-positive prices skipped. Entry for (sym, t_i) is the return from
    t_i to t_{i+1}; the last bar in a symbol's series has no entry.
    """
    out: dict[tuple[dt.date, float]] = {}
    for sym, bars in closes_by_symbol.items():
        if not bars or len(bars) < 2:
            continue
        seen = set()
        for i in range(len(bars) - 1):
            d_curr, p_curr = bars[i]
            d_next, p_next = bars[i + 1]
            if d_curr in seen:
                continue
            seen.add(d_curr)
            if p_curr <= 0 or p_next <= 0:
                continue
            out[(sym, d_curr)] = (p_next - p_curr) / p_curr
    return DailyReturnLookup(by_symbol_date=out)


# ---------------------------------------------------------------------------
# MTM daily strategy return
# ---------------------------------------------------------------------------


def compute_mtm_daily_return(
    positions: dict[str, float],
    returns: DailyReturnLookup,
    date: dt.date,
) -> float:
    """Size-weighted mean of per-symbol close-to-close returns.

    - `positions[sym] > 0`  : contributes to the weighted average.
    - `positions[sym] <= 0` : skipped.
    - missing return for (sym, date): skipped; weight rebalances across
      the remaining book.
    - no positive sizes at all: returns 0.0.

    Returns a return fraction (e.g. 0.002 = +0.2%).
    """
    if not positions:
        return 0.0
    weighted = 0.0
    total_weight = 0.0
    for sym, size in positions.items():
        if size <= 0:
            continue
        r = returns.get(sym, date)
        if r is None:
            continue
        weighted += size * r
        total_weight += size
    if total_weight <= 0:
        return 0.0
    return weighted / total_weight


def coverage_fraction(
    positions: dict[str, float],
    returns: DailyReturnLookup,
    date: dt.date,
) -> float:
    """Fraction of size covered by the return lookup (0..1).

    Useful for auditing: if coverage is materially below 1.0, the MTM
    daily return for that date is averaging over fewer symbols than the
    strategy held.
    """
    total = sum(s for s in positions.values() if s > 0)
    if total <= 0:
        return 0.0
    covered = 0.0
    for sym, size in positions.items():
        if size <= 0:
            continue
        if returns.get(sym, date) is not None:
            covered += size
    return covered / total
