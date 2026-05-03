"""Paper-trading execution. Next-day-open fill. Long-only. No leverage."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    PaperPortfolio,
    PaperPosition,
    PaperTrade,
    PriceBar,
)


DEFAULT_MAX_OPEN_POSITIONS = 10
DEFAULT_SIZING_PCT = Decimal("0.10")   # 10% of equity per position


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PaperTradeRejected(ValueError):
    """Trade could not be executed. Message explains why."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _d(v: object) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _portfolio_config(portfolio: PaperPortfolio) -> dict[str, Any]:
    try:
        return json.loads(portfolio.config_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


def find_next_open(
    session: Session,
    asset_id: str,
    after_ts: dt.datetime,
) -> tuple[dt.datetime, Decimal] | None:
    """Lookup the fill price/timestamp for a submission at ``after_ts``.

    Uses the first daily bar strictly after ``after_ts`` and takes its OPEN.
    Returns None if no future bar exists.
    """
    stmt = (
        select(PriceBar)
        .where(
            PriceBar.asset_id == asset_id,
            PriceBar.timeframe == "1d",
            PriceBar.ts > after_ts,
        )
        .order_by(PriceBar.ts.asc())
        .limit(1)
    )
    bar = session.scalars(stmt).first()
    if bar is None:
        return None
    price = bar.open if bar.open is not None else bar.close
    if price is None:
        return None
    return (bar.ts, _d(price))


def _get_open_position(
    session: Session, portfolio_id: str, asset_id: str
) -> PaperPosition | None:
    stmt = (
        select(PaperPosition)
        .where(
            PaperPosition.portfolio_id == portfolio_id,
            PaperPosition.asset_id == asset_id,
            PaperPosition.is_open.is_(True),
        )
        .limit(1)
    )
    return session.scalars(stmt).first()


def _count_open_positions(session: Session, portfolio_id: str) -> int:
    stmt = (
        select(PaperPosition)
        .where(
            PaperPosition.portfolio_id == portfolio_id,
            PaperPosition.is_open.is_(True),
        )
    )
    return len(list(session.scalars(stmt)))


def _compute_current_equity(
    session: Session, portfolio: PaperPortfolio
) -> Decimal:
    """Estimate current portfolio equity using latest price_bar for each holding."""
    equity = _d(portfolio.cash)
    open_positions = session.scalars(
        select(PaperPosition).where(
            PaperPosition.portfolio_id == portfolio.id,
            PaperPosition.is_open.is_(True),
        )
    ).all()
    for pos in open_positions:
        bar = session.scalars(
            select(PriceBar)
            .where(
                PriceBar.asset_id == pos.asset_id,
                PriceBar.timeframe == "1d",
            )
            .order_by(PriceBar.ts.desc())
            .limit(1)
        ).first()
        if bar is None:
            equity += _d(pos.quantity) * _d(pos.avg_cost)  # fallback: book value
            continue
        last_price = bar.close if bar.close is not None else bar.open
        equity += _d(pos.quantity) * _d(last_price)
    return equity


# ---------------------------------------------------------------------------
# submit_trade
# ---------------------------------------------------------------------------


@dataclass
class TradeResult:
    trade_id: str
    side: str
    quantity: Decimal
    fill_price: Decimal
    fill_ts: dt.datetime
    cash_after: Decimal
    realized_pnl: Decimal | None


def submit_trade(
    session: Session,
    *,
    portfolio_id: str,
    asset_id: str,
    side: str,
    quantity: Decimal | None = None,
    usd_amount: Decimal | None = None,
    submitted_at: dt.datetime | None = None,
    reason: str | None = None,
    recommendation_id: str | None = None,
    fill_price_override: Decimal | None = None,
    slippage_bps: Decimal | None = None,
    commission: Decimal | None = None,
) -> TradeResult:
    """Submit a paper trade.

    Exactly one of ``quantity`` or ``usd_amount`` must be provided. If
    ``usd_amount`` is given, quantity is computed from the effective fill
    price. ``fill_price_override`` — when set, is used directly (used by
    the rebalance engine to pass a cost-model-adjusted fill price). The
    next-bar timestamp is still resolved via ``find_next_open`` for
    determinism. ``slippage_bps`` + ``commission`` are stored on the trade
    row for attribution; they are informational only (already baked into
    ``fill_price_override``).

    Raises :class:`PaperTradeRejected` when validation fails.
    """
    if side not in ("buy", "sell"):
        raise PaperTradeRejected(f"unknown side: {side!r}")
    if (quantity is None) == (usd_amount is None):
        raise PaperTradeRejected("exactly one of quantity or usd_amount required")

    submitted_at = submitted_at or dt.datetime.now(dt.timezone.utc)

    portfolio = session.get(PaperPortfolio, portfolio_id)
    if portfolio is None:
        raise PaperTradeRejected(f"unknown portfolio_id: {portfolio_id}")
    if session.get(Asset, asset_id) is None:
        raise PaperTradeRejected(f"unknown asset_id: {asset_id}")

    fill = find_next_open(session, asset_id, submitted_at)
    if fill is None:
        raise PaperTradeRejected("no price bar available after submitted_at; cannot fill")
    fill_ts, raw_fill_price = fill
    fill_price = fill_price_override if fill_price_override is not None else raw_fill_price
    if fill_price <= 0:
        raise PaperTradeRejected("fill price must be positive")

    if quantity is None:
        assert usd_amount is not None
        qty = _d(usd_amount) / fill_price
    else:
        qty = _d(quantity)
    if qty <= 0:
        raise PaperTradeRejected("quantity must be positive")

    cash = _d(portfolio.cash)
    realized_pnl: Decimal | None = None

    if side == "buy":
        config = _portfolio_config(portfolio)
        max_open = int(config.get("max_open_positions", DEFAULT_MAX_OPEN_POSITIONS))
        existing = _get_open_position(session, portfolio_id, asset_id)
        if existing is None:
            current_open = _count_open_positions(session, portfolio_id)
            if current_open >= max_open:
                raise PaperTradeRejected(
                    f"max open positions reached ({current_open}/{max_open})"
                )

        cost = qty * fill_price
        if cost > cash:
            raise PaperTradeRejected(
                f"insufficient cash: need {cost}, have {cash}"
            )

        portfolio.cash = cash - cost

        if existing is None:
            pos = PaperPosition(
                portfolio_id=portfolio_id,
                asset_id=asset_id,
                quantity=qty,
                avg_cost=fill_price,
                is_open=True,
                opened_at=fill_ts,
            )
            session.add(pos)
        else:
            old_qty = _d(existing.quantity)
            old_basis = _d(existing.avg_cost)
            new_qty = old_qty + qty
            new_avg = ((old_qty * old_basis) + (qty * fill_price)) / new_qty
            existing.quantity = new_qty
            existing.avg_cost = new_avg

    else:  # sell
        existing = _get_open_position(session, portfolio_id, asset_id)
        if existing is None:
            raise PaperTradeRejected("no open position to sell")
        open_qty = _d(existing.quantity)
        if qty > open_qty:
            raise PaperTradeRejected(
                f"insufficient position quantity: have {open_qty}, want {qty}"
            )
        proceeds = qty * fill_price
        basis = _d(existing.avg_cost)
        realized_pnl = qty * (fill_price - basis)

        portfolio.cash = cash + proceeds
        remaining = open_qty - qty
        if remaining == 0:
            existing.quantity = Decimal("0")
            existing.is_open = False
            existing.closed_at = fill_ts
        else:
            existing.quantity = remaining

    trade = PaperTrade(
        portfolio_id=portfolio_id,
        asset_id=asset_id,
        side=side,
        quantity=qty,
        fill_price=fill_price,
        fill_ts=fill_ts,
        submitted_at=submitted_at,
        reason=reason,
        recommendation_id=recommendation_id,
        realized_pnl=realized_pnl,
        slippage_bps=slippage_bps,
        commission=commission if commission is not None else Decimal("0"),
    )
    session.add(trade)
    session.flush()

    return TradeResult(
        trade_id=trade.id,
        side=side,
        quantity=qty,
        fill_price=fill_price,
        fill_ts=fill_ts,
        cash_after=_d(portfolio.cash),
        realized_pnl=realized_pnl,
    )


# ---------------------------------------------------------------------------
# Sizing helpers (callers can use these to size before submitting)
# ---------------------------------------------------------------------------


def compute_sizing_usd(
    session: Session,
    portfolio: PaperPortfolio,
    *,
    pct_of_equity: Decimal | None = None,
) -> Decimal:
    """Return a USD amount sized as `pct_of_equity * current_equity`.

    Defaults to the portfolio's configured sizing pct (or ``DEFAULT_SIZING_PCT``).
    """
    config = _portfolio_config(portfolio)
    pct = pct_of_equity or _d(config.get("sizing_pct_of_equity", DEFAULT_SIZING_PCT))
    equity = _compute_current_equity(session, portfolio)
    return (pct * equity).quantize(Decimal("0.01"))
