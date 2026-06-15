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


DEFAULT_MAX_OPEN_POSITIONS = 30
DEFAULT_SIZING_PCT = Decimal("0.10")   # 10% of equity per position

# Paper-only cash-aware sizing. When the equity-based target exceeds
# available cash by a small margin, shrink to fit. Never removes the
# cash guard — if shrunk size falls below `PAPER_MIN_NOTIONAL_USD`,
# the decision is skipped with `position_too_small` instead.
import os as _os  # local import — no top-level side effects.

DEFAULT_CASH_BUFFER_PCT = Decimal("0.05")     # 5%
DEFAULT_MIN_NOTIONAL_USD = Decimal("50")


def _cash_buffer_pct() -> Decimal:
    raw = _os.environ.get("PAPER_CASH_BUFFER_PCT", "").strip()
    if not raw:
        return DEFAULT_CASH_BUFFER_PCT
    try:
        v = Decimal(raw)
    except Exception:  # noqa: BLE001
        return DEFAULT_CASH_BUFFER_PCT
    if v < 0 or v > Decimal("0.50"):
        return DEFAULT_CASH_BUFFER_PCT
    return v


def _min_notional_usd() -> Decimal:
    raw = _os.environ.get("PAPER_MIN_NOTIONAL_USD", "").strip()
    if not raw:
        return DEFAULT_MIN_NOTIONAL_USD
    try:
        v = Decimal(raw)
    except Exception:  # noqa: BLE001
        return DEFAULT_MIN_NOTIONAL_USD
    if v < 0:
        return DEFAULT_MIN_NOTIONAL_USD
    return v


def shrink_to_cash(
    *, target_usd: Decimal, available_cash: Decimal,
    cash_buffer_pct: Decimal | None = None,
    min_notional_usd: Decimal | None = None,
) -> tuple[Decimal, dict[str, Any]]:
    """Shrink an equity-based sizing target to a cash-aware amount.

    Returns (final_usd, info) where info captures shrink_applied,
    cash_buffer_pct, min_notional_usd, target_usd, available_cash,
    cap_usd, and below_min flag. final_usd <= 0 means the decision
    must be rejected upstream with `position_too_small`."""
    buffer = (
        cash_buffer_pct
        if cash_buffer_pct is not None
        else _cash_buffer_pct()
    )
    min_n = (
        min_notional_usd
        if min_notional_usd is not None
        else _min_notional_usd()
    )
    target = _d(target_usd)
    cash = _d(available_cash)
    cap = (cash * (Decimal("1") - buffer)).quantize(Decimal("0.01"))
    if cap < 0:
        cap = Decimal("0")
    final = min(target, cap)
    shrink_applied = final < target
    below_min = final < min_n
    info = {
        "target_usd": str(target),
        "available_cash": str(cash),
        "cash_buffer_pct": str(buffer),
        "cap_usd": str(cap),
        "min_notional_usd": str(min_n),
        "final_usd": str(final),
        "shrink_applied": shrink_applied,
        "below_min": below_min,
    }
    if below_min:
        return Decimal("0"), info
    return final, info


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
    # MP1S — track new/closed position so trade-id provenance can be stamped
    # after the trade row is flushed (trade.id is DB-assigned).
    created_position: PaperPosition | None = None
    closed_position: PaperPosition | None = None

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
                # MP1S — entry-decision identity (NULL when no rec drove it).
                opened_by_recommendation_id=recommendation_id,
            )
            session.add(pos)
            created_position = pos
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
        # MP1S — accumulate executed P&L at the position level. COALESCE via
        # _d() (None→0). Does NOT alter PaperTrade.realized_pnl set below.
        existing.realized_pnl = _d(existing.realized_pnl) + realized_pnl
        remaining = open_qty - qty
        if remaining == 0:
            existing.quantity = Decimal("0")
            existing.is_open = False
            existing.closed_at = fill_ts
            closed_position = existing
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

    # MP1S — stamp trade-id provenance now that trade.id is assigned.
    if created_position is not None:
        created_position.opening_trade_id = trade.id
    if closed_position is not None:
        closed_position.closed_by_trade_id = trade.id

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
