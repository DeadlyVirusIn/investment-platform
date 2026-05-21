"""Portfolio-level PnL + per-symbol PnL.

Reuses: paper_portfolio, paper_position, paper_trade, paper_equity_snapshot,
price_bar, asset. Read-only. Deterministic. No schema additions.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    PaperEquitySnapshot,
    PaperPortfolio,
    PaperPosition,
    PaperTrade,
    PriceBar,
)


# ---------------------------------------------------------------------------
# Resolvers
# ---------------------------------------------------------------------------


def resolve_portfolio(
    session: Session, portfolio_id: str | None,
) -> PaperPortfolio | None:
    if portfolio_id:
        return session.get(PaperPortfolio, portfolio_id)
    stmt = (
        select(PaperPortfolio)
        .where(PaperPortfolio.is_active.is_(True))
        .order_by(PaperPortfolio.created_at.asc(), PaperPortfolio.id.asc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def latest_price(session: Session, asset_id: str) -> Decimal | None:
    stmt = (
        select(PriceBar.close)
        .where(PriceBar.asset_id == asset_id, PriceBar.timeframe == "1d")
        .order_by(desc(PriceBar.ts))
        .limit(1)
    )
    row = session.execute(stmt).first()
    if row is None or row[0] is None:
        return None
    v = row[0]
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _d(v: object) -> Decimal:
    if v is None:
        return Decimal("0")
    return v if isinstance(v, Decimal) else Decimal(str(v))


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------


@dataclass
class PositionMark:
    asset_id: str
    symbol: str | None
    quantity: Decimal
    avg_cost: Decimal
    mark: Decimal | None
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pct: Decimal | None
    opened_at: dt.datetime | None
    holding_days: int | None


@dataclass
class PortfolioPnl:
    portfolio_id: str
    starting_cash: Decimal
    cash: Decimal
    invested: Decimal
    nav: Decimal
    cumulative_pnl: Decimal
    daily_pnl: Decimal | None
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    open_positions_count: int
    closed_trade_count: int
    wins: int
    losses: int
    breakeven: int
    win_rate: Decimal | None
    avg_win: Decimal | None
    avg_loss: Decimal | None
    positions: list[PositionMark] = field(default_factory=list)


def _holding_days(opened_at: dt.datetime | None, now: dt.datetime) -> int | None:
    if opened_at is None:
        return None
    if opened_at.tzinfo is None:
        opened_at = opened_at.replace(tzinfo=dt.timezone.utc)
    return max(0, (now.date() - opened_at.date()).days)


def _load_open_positions(
    session: Session, portfolio_id: str,
) -> list[PaperPosition]:
    stmt = (
        select(PaperPosition)
        .where(
            PaperPosition.portfolio_id == portfolio_id,
            PaperPosition.is_open.is_(True),
            PaperPosition.quantity > 0,
        )
    )
    return list(session.scalars(stmt))


def _symbol_map(session: Session, asset_ids: list[str]) -> dict[str, str]:
    if not asset_ids:
        return {}
    rows = session.execute(
        select(Asset.id, Asset.symbol).where(Asset.id.in_(asset_ids))
    ).all()
    return {aid: sym for aid, sym in rows}


def _mark_positions(
    session: Session, positions: Sequence[PaperPosition], now: dt.datetime,
) -> list[PositionMark]:
    asset_ids = [p.asset_id for p in positions]
    symbols = _symbol_map(session, asset_ids)
    out: list[PositionMark] = []
    for p in positions:
        qty = _d(p.quantity)
        avg = _d(p.avg_cost)
        mark = latest_price(session, p.asset_id)
        mv = qty * mark if mark is not None else Decimal("0")
        pnl = (mark - avg) * qty if mark is not None else Decimal("0")
        pct = (mark - avg) / avg if mark is not None and avg > 0 else None
        out.append(PositionMark(
            asset_id=p.asset_id,
            symbol=symbols.get(p.asset_id),
            quantity=qty, avg_cost=avg, mark=mark,
            market_value=mv, unrealized_pnl=pnl, unrealized_pct=pct,
            opened_at=p.opened_at,
            holding_days=_holding_days(p.opened_at, now),
        ))
    return out


def _closed_trade_pnls(
    session: Session, portfolio_id: str,
) -> list[Decimal]:
    stmt = select(PaperTrade.realized_pnl).where(
        PaperTrade.portfolio_id == portfolio_id,
        PaperTrade.side == "sell",
        PaperTrade.realized_pnl.is_not(None),
    )
    out: list[Decimal] = []
    for (pnl,) in session.execute(stmt).all():
        out.append(_d(pnl))
    return out


def _prior_equity_snapshot(
    session: Session, portfolio_id: str, as_of: dt.date,
) -> Decimal | None:
    """Latest snapshot strictly before ``as_of``."""
    # Phase L M079: canonical P&L — live-only.
    stmt = (
        select(PaperEquitySnapshot.total_equity)
        .where(
            PaperEquitySnapshot.portfolio_id == portfolio_id,
            PaperEquitySnapshot.source == "live",
            PaperEquitySnapshot.snapshot_date < dt.datetime.combine(
                as_of, dt.time(0, 0, 0, tzinfo=dt.timezone.utc),
            ),
        )
        .order_by(
            desc(PaperEquitySnapshot.snapshot_date),
            desc(PaperEquitySnapshot.recorded_at),
        )
        .limit(1)
    )
    row = session.execute(stmt).first()
    if row is None or row[0] is None:
        return None
    return _d(row[0])


def portfolio_pnl(
    session: Session, portfolio: PaperPortfolio,
    now: dt.datetime | None = None,
) -> PortfolioPnl:
    when = now or dt.datetime.now(dt.timezone.utc)
    positions = _load_open_positions(session, portfolio.id)
    marks = _mark_positions(session, positions, when)

    cash = _d(portfolio.cash)
    starting_cash = _d(portfolio.starting_cash)
    invested = sum((m.market_value for m in marks), Decimal("0"))
    unrealized = sum((m.unrealized_pnl for m in marks), Decimal("0"))
    nav = cash + invested
    cumulative = nav - starting_cash

    realized_list = _closed_trade_pnls(session, portfolio.id)
    realized_total = sum(realized_list, Decimal("0"))
    wins = sum(1 for p in realized_list if p > 0)
    losses = sum(1 for p in realized_list if p < 0)
    breakeven = sum(1 for p in realized_list if p == 0)
    decisive = wins + losses
    win_rate = Decimal(wins) / Decimal(decisive) if decisive > 0 else None
    win_pnls = [p for p in realized_list if p > 0]
    loss_pnls = [p for p in realized_list if p < 0]
    avg_win = sum(win_pnls, Decimal("0")) / Decimal(len(win_pnls)) if win_pnls else None
    avg_loss = sum(loss_pnls, Decimal("0")) / Decimal(len(loss_pnls)) if loss_pnls else None

    prior = _prior_equity_snapshot(session, portfolio.id, when.date())
    daily_pnl = nav - prior if prior is not None else None

    return PortfolioPnl(
        portfolio_id=portfolio.id,
        starting_cash=starting_cash,
        cash=cash,
        invested=invested,
        nav=nav,
        cumulative_pnl=cumulative,
        daily_pnl=daily_pnl,
        realized_pnl=realized_total,
        unrealized_pnl=unrealized,
        open_positions_count=len(marks),
        closed_trade_count=len(realized_list),
        wins=wins, losses=losses, breakeven=breakeven,
        win_rate=win_rate, avg_win=avg_win, avg_loss=avg_loss,
        positions=marks,
    )


# ---------------------------------------------------------------------------
# Per-symbol
# ---------------------------------------------------------------------------


@dataclass
class SymbolPnl:
    asset_id: str
    symbol: str | None
    status: str                    # 'open' | 'closed'
    quantity: Decimal
    avg_cost: Decimal | None
    mark: Decimal | None
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    holding_days: int | None
    entry_composite_score: Decimal | None = None
    entry_confidence: Decimal | None = None
    entry_market_trend: str | None = None
    entry_vol_regime: str | None = None


def per_symbol_pnl(
    session: Session, portfolio: PaperPortfolio,
    now: dt.datetime | None = None,
) -> list[SymbolPnl]:
    from apps.api.src.domain.pnl.attribution import entry_context_map

    when = now or dt.datetime.now(dt.timezone.utc)
    open_positions = {
        p.asset_id: p for p in _load_open_positions(session, portfolio.id)
    }
    # All assets ever traded by this portfolio
    traded_ids_stmt = (
        select(PaperTrade.asset_id)
        .where(PaperTrade.portfolio_id == portfolio.id)
        .distinct()
    )
    traded_ids = {row[0] for row in session.execute(traded_ids_stmt).all()}
    traded_ids |= set(open_positions.keys())
    if not traded_ids:
        return []

    symbols = _symbol_map(session, list(traded_ids))
    entry_ctx = entry_context_map(session, portfolio.id)

    # Realized per-symbol
    realized_stmt = (
        select(PaperTrade.asset_id, PaperTrade.realized_pnl)
        .where(
            PaperTrade.portfolio_id == portfolio.id,
            PaperTrade.side == "sell",
            PaperTrade.realized_pnl.is_not(None),
        )
    )
    realized_by_asset: dict[str, Decimal] = {}
    for aid, pnl in session.execute(realized_stmt).all():
        realized_by_asset[aid] = realized_by_asset.get(aid, Decimal("0")) + _d(pnl)

    # First buy timestamp per symbol (for holding_days on closed positions)
    first_buy_stmt = (
        select(PaperTrade.asset_id, PaperTrade.fill_ts)
        .where(
            PaperTrade.portfolio_id == portfolio.id,
            PaperTrade.side == "buy",
        )
        .order_by(PaperTrade.fill_ts.asc())
    )
    first_buy_by_asset: dict[str, dt.datetime] = {}
    for aid, ts in session.execute(first_buy_stmt).all():
        first_buy_by_asset.setdefault(aid, ts)
    last_sell_stmt = (
        select(PaperTrade.asset_id, PaperTrade.fill_ts)
        .where(
            PaperTrade.portfolio_id == portfolio.id,
            PaperTrade.side == "sell",
        )
        .order_by(PaperTrade.fill_ts.desc())
    )
    last_sell_by_asset: dict[str, dt.datetime] = {}
    for aid, ts in session.execute(last_sell_stmt).all():
        last_sell_by_asset.setdefault(aid, ts)

    rows: list[SymbolPnl] = []
    for aid in sorted(traded_ids, key=lambda x: symbols.get(x, x) or x):
        sym = symbols.get(aid)
        ctx = entry_ctx.get(aid)
        realized = realized_by_asset.get(aid, Decimal("0"))
        pos = open_positions.get(aid)
        if pos is not None:
            qty = _d(pos.quantity)
            avg = _d(pos.avg_cost)
            mark = latest_price(session, aid)
            unrealized = (mark - avg) * qty if mark is not None else Decimal("0")
            hdays = _holding_days(pos.opened_at, when)
            rows.append(SymbolPnl(
                asset_id=aid, symbol=sym, status="open",
                quantity=qty, avg_cost=avg, mark=mark,
                realized_pnl=realized, unrealized_pnl=unrealized,
                total_pnl=realized + unrealized,
                holding_days=hdays,
                entry_composite_score=ctx.get("composite_score") if ctx else None,
                entry_confidence=ctx.get("confidence") if ctx else None,
                entry_market_trend=ctx.get("market_trend") if ctx else None,
                entry_vol_regime=ctx.get("vol_regime") if ctx else None,
            ))
        else:
            buy_ts = first_buy_by_asset.get(aid)
            sell_ts = last_sell_by_asset.get(aid)
            hdays = None
            if buy_ts is not None and sell_ts is not None:
                hdays = max(0, (sell_ts.date() - buy_ts.date()).days)
            rows.append(SymbolPnl(
                asset_id=aid, symbol=sym, status="closed",
                quantity=Decimal("0"), avg_cost=None, mark=None,
                realized_pnl=realized, unrealized_pnl=Decimal("0"),
                total_pnl=realized,
                holding_days=hdays,
                entry_composite_score=ctx.get("composite_score") if ctx else None,
                entry_confidence=ctx.get("confidence") if ctx else None,
                entry_market_trend=ctx.get("market_trend") if ctx else None,
                entry_vol_regime=ctx.get("vol_regime") if ctx else None,
            ))
    return rows
