"""Transaction orchestration: create txn row, open/close lots, return result."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from apps.api.src.db.models import Account, Asset, Transaction
from apps.api.src.domain.ledger.lot_tracker import close_fifo, open_lot

TxnAction = Literal["buy", "sell", "dividend", "fee", "transfer"]


class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    asset_id: str | None = None
    symbol: str | None = None
    ts: dt.datetime | None = None
    action: TxnAction
    quantity: Decimal
    price: Decimal
    fees: Decimal | None = None
    currency: str = "USD"
    notes: str | None = None


class TransactionResult(BaseModel):
    transaction_id: str
    account_id: str
    asset_id: str
    action: TxnAction
    ts: dt.datetime
    quantity: Decimal
    price: Decimal
    fees: Decimal | None = None
    lot_ids_opened: list[str] = []
    lot_close_ids: list[str] = []
    realized_pnl: Decimal = Decimal("0")


def _resolve_asset_id(session: Session, payload: TransactionCreate) -> str:
    if payload.asset_id is not None:
        if session.get(Asset, payload.asset_id) is None:
            raise ValueError(f"unknown asset_id: {payload.asset_id}")
        return payload.asset_id
    if payload.symbol is None:
        raise ValueError("asset_id or symbol required")
    asset = session.query(Asset).filter(Asset.symbol == payload.symbol).first()
    if asset is None:
        raise ValueError(f"unknown symbol: {payload.symbol}")
    return asset.id


def create_transaction(session: Session, payload: TransactionCreate) -> TransactionResult:
    """Create a transaction row and apply lot side-effects by action."""
    if session.get(Account, payload.account_id) is None:
        raise ValueError(f"unknown account_id: {payload.account_id}")
    asset_id = _resolve_asset_id(session, payload)
    ts = payload.ts or dt.datetime.now(dt.timezone.utc)

    txn = Transaction(
        account_id=payload.account_id,
        asset_id=asset_id,
        ts=ts,
        action=payload.action,
        quantity=payload.quantity,
        price=payload.price,
        fees=payload.fees,
        currency=payload.currency,
        notes=payload.notes,
    )
    session.add(txn)
    session.flush()

    lot_ids_opened: list[str] = []
    lot_close_ids: list[str] = []
    realized = Decimal("0")

    if payload.action == "buy":
        lot = open_lot(session, txn)
        lot_ids_opened = [lot.id]
    elif payload.action == "sell":
        closes = close_fifo(session, txn)
        lot_close_ids = [c.id for c in closes]
        realized = sum(
            (Decimal(str(c.realized_pnl)) for c in closes if c.realized_pnl is not None),
            Decimal("0"),
        )
    # dividend / fee / transfer: no lot side-effect in this batch

    return TransactionResult(
        transaction_id=txn.id,
        account_id=txn.account_id,
        asset_id=txn.asset_id,
        action=txn.action,  # type: ignore[arg-type]
        ts=txn.ts,
        quantity=payload.quantity,
        price=payload.price,
        fees=payload.fees,
        lot_ids_opened=lot_ids_opened,
        lot_close_ids=lot_close_ids,
        realized_pnl=realized,
    )
