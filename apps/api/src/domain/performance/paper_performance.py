"""Practical performance metrics computed from paper trading data.

Focus: answer "is the system actually good?" using the paper portfolio's
equity curve + trade log. Not academic finance — safe, explainable,
divide-by-zero resistant.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    PaperEquitySnapshot,
    PaperPortfolio,
    PaperTrade,
)

# Annualization factor for daily returns (trading days).
TRADING_DAYS_PER_YEAR = 252


@dataclass
class PaperMetrics:
    total_return: Decimal | None
    max_drawdown: Decimal | None
    hit_rate: Decimal | None
    expectancy: Decimal | None
    profit_factor: Decimal | None
    sharpe: Decimal | None
    trades: int
    wins: int
    losses: int
    breakeven: int


@dataclass
class EquityPoint:
    date: dt.date
    equity: Decimal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _d(v: object) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except Exception:  # noqa: BLE001
        return None


def _decimal_sqrt(x: Decimal, iterations: int = 25) -> Decimal:
    if x <= 0:
        return Decimal("0")
    guess = x / Decimal("2")
    for _ in range(iterations):
        if guess == 0:
            break
        guess = (guess + x / guess) / Decimal("2")
    return guess


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _sample_std(values: list[Decimal]) -> Decimal | None:
    """Sample standard deviation. Returns None when n < 2."""
    n = len(values)
    if n < 2:
        return None
    mean = _mean(values) or Decimal("0")
    var = sum(((v - mean) ** 2 for v in values), Decimal("0")) / Decimal(n - 1)
    return _decimal_sqrt(var)


# ---------------------------------------------------------------------------
# Metric computations — pure functions
# ---------------------------------------------------------------------------


def daily_returns(curve: Iterable[EquityPoint]) -> list[Decimal]:
    """Compute simple day-over-day returns from an equity curve. Zero and
    negative prior-equity values are skipped to avoid undefined returns."""
    curve_sorted = sorted(curve, key=lambda p: p.date)
    out: list[Decimal] = []
    prev: Decimal | None = None
    for p in curve_sorted:
        eq = _d(p.equity)
        if eq is None or eq <= 0:
            prev = eq
            continue
        if prev is not None and prev > 0:
            out.append((eq - prev) / prev)
        prev = eq
    return out


def max_drawdown(curve: Iterable[EquityPoint]) -> Decimal | None:
    """Maximum peak-to-trough drawdown as a negative fraction. None when
    insufficient data or never underwater."""
    curve_sorted = sorted(curve, key=lambda p: p.date)
    if len(curve_sorted) < 2:
        return None
    peak = _d(curve_sorted[0].equity) or Decimal("0")
    worst = Decimal("0")
    for p in curve_sorted:
        eq = _d(p.equity)
        if eq is None:
            continue
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = (eq - peak) / peak
            if dd < worst:
                worst = dd
    return worst if worst < 0 else None


def total_return(
    starting_cash: Decimal | None, latest_equity: Decimal | None,
) -> Decimal | None:
    if starting_cash is None or latest_equity is None or starting_cash <= 0:
        return None
    return (latest_equity - starting_cash) / starting_cash


def hit_rate(wins: int, losses: int) -> Decimal | None:
    decisive = wins + losses
    if decisive == 0:
        return None
    return Decimal(wins) / Decimal(decisive)


def expectancy(realized_pnls: list[Decimal]) -> Decimal | None:
    if not realized_pnls:
        return None
    return _mean(realized_pnls)


def profit_factor(realized_pnls: list[Decimal]) -> Decimal | None:
    wins = sum((p for p in realized_pnls if p > 0), Decimal("0"))
    losses = sum((abs(p) for p in realized_pnls if p < 0), Decimal("0"))
    if losses == 0:
        return None
    return wins / losses


def sharpe(
    returns: list[Decimal],
    annualization: int = TRADING_DAYS_PER_YEAR,
) -> Decimal | None:
    """Simple daily Sharpe = mean / std × sqrt(annualization). Risk-free rate
    assumed 0 for personal-use paper trading. Returns None when n < 2 or
    std == 0."""
    if len(returns) < 2:
        return None
    sd = _sample_std(returns)
    if sd is None or sd == 0:
        return None
    mean = _mean(returns) or Decimal("0")
    factor = _decimal_sqrt(Decimal(annualization))
    return (mean / sd) * factor


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def _closed_trade_pnls(
    session: Session, portfolio_id: str
) -> list[Decimal]:
    """Realized P&L across sell trades with realized_pnl populated."""
    stmt = select(PaperTrade.realized_pnl).where(
        PaperTrade.portfolio_id == portfolio_id,
        PaperTrade.side == "sell",
        PaperTrade.realized_pnl.isnot(None),
    )
    out: list[Decimal] = []
    for (pnl,) in session.execute(stmt).all():
        d = _d(pnl)
        if d is not None:
            out.append(d)
    return out


def _load_equity_curve(
    session: Session, portfolio_id: str
) -> list[EquityPoint]:
    stmt = (
        select(PaperEquitySnapshot)
        .where(PaperEquitySnapshot.portfolio_id == portfolio_id)
        .order_by(PaperEquitySnapshot.snapshot_date.asc())
    )
    points: list[EquityPoint] = []
    for snap in session.scalars(stmt):
        eq = _d(snap.total_equity)
        if snap.snapshot_date is None or eq is None:
            continue
        points.append(EquityPoint(date=snap.snapshot_date.date(), equity=eq))
    return points


def compute_paper_metrics(
    session: Session, portfolio_id: str,
) -> PaperMetrics:
    """Assemble PaperMetrics for a portfolio. Safe on empty state."""
    portfolio = session.get(PaperPortfolio, portfolio_id)
    if portfolio is None:
        return _empty_metrics()

    pnls = _closed_trade_pnls(session, portfolio_id)
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    breakeven = sum(1 for p in pnls if p == 0)

    curve = _load_equity_curve(session, portfolio_id)

    starting_cash = _d(portfolio.starting_cash)
    latest_equity = curve[-1].equity if curve else _d(portfolio.cash)

    return PaperMetrics(
        total_return=total_return(starting_cash, latest_equity),
        max_drawdown=max_drawdown(curve),
        hit_rate=hit_rate(wins, losses),
        expectancy=expectancy(pnls),
        profit_factor=profit_factor(pnls),
        sharpe=sharpe(daily_returns(curve)),
        trades=len(pnls),
        wins=wins,
        losses=losses,
        breakeven=breakeven,
    )


def equity_curve_points(
    session: Session, portfolio_id: str,
) -> list[EquityPoint]:
    return _load_equity_curve(session, portfolio_id)


def _empty_metrics() -> PaperMetrics:
    return PaperMetrics(
        total_return=None,
        max_drawdown=None,
        hit_rate=None,
        expectancy=None,
        profit_factor=None,
        sharpe=None,
        trades=0,
        wins=0,
        losses=0,
        breakeven=0,
    )


# ---------------------------------------------------------------------------
# Portfolio resolver (single-user convenience)
# ---------------------------------------------------------------------------


def resolve_default_portfolio_id(session: Session) -> str | None:
    """Pick the oldest active PaperPortfolio, or None when none exist."""
    stmt = (
        select(PaperPortfolio.id)
        .where(PaperPortfolio.is_active.is_(True))
        .order_by(PaperPortfolio.created_at.asc(), PaperPortfolio.id.asc())
        .limit(1)
    )
    return session.execute(stmt).scalars().first()
