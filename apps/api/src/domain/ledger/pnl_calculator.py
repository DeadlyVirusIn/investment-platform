"""Positions + P&L aggregation from open lots and lot_close rows."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, Lot, LotClose, PriceBar, Transaction


def _d(v: object) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _latest_price(session: Session, asset_id: str) -> Decimal | None:
    stmt = (
        select(PriceBar.adjusted_close, PriceBar.close)
        .where(PriceBar.asset_id == asset_id)
        .order_by(PriceBar.ts.desc())
        .limit(1)
    )
    row = session.execute(stmt).first()
    if row is None:
        return None
    chosen = row[0] if row[0] is not None else row[1]
    return _d(chosen) if chosen is not None else None


def compute_positions(session: Session, account_id: str) -> list[dict[str, Any]]:
    """Aggregate open lots per asset into a list of position dicts."""
    stmt = (
        select(Lot, Asset)
        .join(Transaction, Lot.open_transaction_id == Transaction.id)
        .join(Asset, Lot.asset_id == Asset.id)
        .where(
            Transaction.account_id == account_id,
            Lot.quantity_remaining > 0,
        )
    )
    by_asset: dict[str, dict[str, Any]] = {}
    for lot, asset in session.execute(stmt).all():
        qty = _d(lot.quantity_remaining)
        basis = _d(lot.cost_basis_per_unit)
        entry = by_asset.setdefault(
            asset.id,
            {
                "asset_id": asset.id,
                "symbol": asset.symbol,
                "asset_class": asset.asset_class,
                "currency": asset.currency,
                "quantity": Decimal("0"),
                "total_cost_basis": Decimal("0"),
                "lot_count": 0,
            },
        )
        entry["quantity"] += qty
        entry["total_cost_basis"] += qty * basis
        entry["lot_count"] += 1

    positions: list[dict[str, Any]] = []
    for e in by_asset.values():
        qty = e["quantity"]
        avg = (e["total_cost_basis"] / qty) if qty else Decimal("0")
        last = _latest_price(session, e["asset_id"])
        market_value = (qty * last) if last is not None else None
        unrealized = ((last - avg) * qty) if last is not None else None
        positions.append(
            {
                "asset_id": e["asset_id"],
                "symbol": e["symbol"],
                "asset_class": e["asset_class"],
                "currency": e["currency"],
                "quantity": qty,
                "avg_cost_basis": avg,
                "total_cost_basis": e["total_cost_basis"],
                "last_price": last,
                "market_value": market_value,
                "unrealized_pnl": unrealized,
                "lot_count": e["lot_count"],
            }
        )
    return positions


def compute_realized_pnl(session: Session, account_id: str) -> Decimal:
    """Sum realized_pnl across all lot_close rows belonging to account."""
    stmt = (
        select(func.coalesce(func.sum(LotClose.realized_pnl), 0))
        .join(Lot, LotClose.lot_id == Lot.id)
        .join(Transaction, Lot.open_transaction_id == Transaction.id)
        .where(Transaction.account_id == account_id)
    )
    return _d(session.execute(stmt).scalar())


def compute_pnl_summary(session: Session, account_id: str) -> dict[str, Any]:
    """High-level P&L snapshot for the portfolio summary / pnl endpoints."""
    positions = compute_positions(session, account_id)
    realized = compute_realized_pnl(session, account_id)

    unrealized_total = Decimal("0")
    has_unrealized = False
    market_value_total = Decimal("0")
    market_value_complete = True
    cost_basis_total = Decimal("0")

    for p in positions:
        cost_basis_total += p["total_cost_basis"]
        if p["unrealized_pnl"] is None:
            market_value_complete = False
        else:
            unrealized_total += p["unrealized_pnl"]
            has_unrealized = True
            market_value_total += p["market_value"]

    return {
        "account_id": account_id,
        "realized_pnl": realized,
        "unrealized_pnl": unrealized_total if has_unrealized else None,
        "unrealized_partial": has_unrealized and not market_value_complete,
        "total_market_value": market_value_total if market_value_complete else None,
        "total_cost_basis": cost_basis_total,
        "position_count": len(positions),
    }
