"""FIFO tax-lot open/close engine. Pure DB logic over a session."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import Lot, LotClose, Transaction


def _d(v: object) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def open_lot(session: Session, txn: Transaction) -> Lot:
    """Open a new tax lot from a BUY transaction. Fees absorbed into basis."""
    qty = _d(txn.quantity)
    price = _d(txn.price)
    fees = _d(txn.fees)
    if qty <= 0:
        raise ValueError("buy transaction quantity must be positive")
    basis_per_unit = price + (fees / qty if fees else Decimal("0"))
    lot = Lot(
        open_transaction_id=txn.id,
        asset_id=txn.asset_id,
        quantity_opened=qty,
        quantity_remaining=qty,
        cost_basis_per_unit=basis_per_unit,
        currency=txn.currency,
    )
    session.add(lot)
    session.flush()
    return lot


def close_fifo(session: Session, txn: Transaction) -> list[LotClose]:
    """Close open lots FIFO for a SELL transaction. Fees reduce proceeds."""
    sell_qty = _d(txn.quantity)
    sell_price = _d(txn.price)
    fees = _d(txn.fees)
    if sell_qty <= 0:
        raise ValueError("sell transaction quantity must be positive")
    proceeds_per_unit = sell_price - (fees / sell_qty if fees else Decimal("0"))

    stmt = (
        select(Lot)
        .join(Transaction, Lot.open_transaction_id == Transaction.id)
        .where(
            Transaction.account_id == txn.account_id,
            Lot.asset_id == txn.asset_id,
            Lot.quantity_remaining > 0,
        )
        .order_by(Transaction.ts.asc(), Lot.created_at.asc())
    )
    lots = list(session.execute(stmt).scalars())
    available = sum((_d(lot.quantity_remaining) for lot in lots), Decimal("0"))
    if available < sell_qty:
        raise ValueError(
            f"insufficient quantity to sell: have {available}, want {sell_qty}"
        )

    remaining = sell_qty
    closes: list[LotClose] = []
    for lot in lots:
        if remaining <= 0:
            break
        lot_remaining = _d(lot.quantity_remaining)
        qty_to_close = min(lot_remaining, remaining)
        basis = _d(lot.cost_basis_per_unit)
        realized = qty_to_close * (proceeds_per_unit - basis)
        close = LotClose(
            lot_id=lot.id,
            close_transaction_id=txn.id,
            quantity_closed=qty_to_close,
            proceeds_per_unit=proceeds_per_unit,
            realized_pnl=realized,
        )
        session.add(close)
        lot.quantity_remaining = lot_remaining - qty_to_close
        remaining -= qty_to_close
        closes.append(close)

    session.flush()
    return closes
