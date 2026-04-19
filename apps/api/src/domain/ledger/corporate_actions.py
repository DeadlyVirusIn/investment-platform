"""Corporate-action handlers: splits and cash dividends. Decimal-only math."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    CorporateAction,
    Lot,
    Transaction,
)


def _d(v: object) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _existing_action(
    session: Session,
    asset_id: str,
    action_type: str,
    ex_date: dt.datetime,
    provider: str,
) -> CorporateAction | None:
    stmt = select(CorporateAction).where(
        CorporateAction.asset_id == asset_id,
        CorporateAction.action_type == action_type,
        CorporateAction.ex_date == ex_date,
        CorporateAction.provider == provider,
    )
    return session.execute(stmt).scalars().first()


def apply_split(
    session: Session,
    asset_id: str,
    ratio: Decimal | str | float | int,
    ex_date: dt.datetime,
    provider: str = "manual",
) -> dict[str, Any]:
    """Apply a split. ``ratio`` = new_shares_per_old_share.

    Forward 2:1  -> ratio = 2
    Reverse 1:10 -> ratio = 0.1

    Adjusts every open Lot for the asset:
        qty_opened   *= ratio
        qty_remaining *= ratio
        cost_basis_per_unit /= ratio
    Preserves total cost basis (qty * basis).
    Idempotent on (asset, 'split', ex_date, provider).
    """
    if session.get(Asset, asset_id) is None:
        raise ValueError(f"unknown asset_id: {asset_id}")

    r = _d(ratio)
    if r <= 0:
        raise ValueError(f"split ratio must be positive, got {r}")

    if _existing_action(session, asset_id, "split", ex_date, provider) is not None:
        return {"applied": False, "reason": "already applied", "lots_adjusted": 0}

    stmt = select(Lot).where(Lot.asset_id == asset_id, Lot.quantity_remaining > 0)
    lots = list(session.execute(stmt).scalars())

    for lot in lots:
        qty_opened = _d(lot.quantity_opened)
        qty_remaining = _d(lot.quantity_remaining)
        basis = _d(lot.cost_basis_per_unit)
        lot.quantity_opened = qty_opened * r
        lot.quantity_remaining = qty_remaining * r
        lot.cost_basis_per_unit = basis / r

    action = CorporateAction(
        asset_id=asset_id,
        action_type="split",
        ex_date=ex_date,
        ratio=r,
        amount=None,
        currency=None,
        provider=provider,
    )
    session.add(action)
    session.flush()

    return {
        "action_id": action.id,
        "applied": True,
        "lots_adjusted": len(lots),
        "ratio": r,
    }


def record_dividend(
    session: Session,
    account_id: str,
    asset_id: str,
    ex_date: dt.datetime,
    dividend_per_share: Decimal | str | float | int,
    provider: str = "manual",
) -> dict[str, Any]:
    """Record a cash dividend for the given account's holdings of asset.

    Writes a Transaction row (action='dividend', quantity=qty_held,
    price=dividend_per_share). No lot is opened or closed. Dividend cash
    contributes to realized P&L via compute_realized_pnl().

    Uses current open-lot qty for the (account, asset) pair. Caller should
    record dividends promptly after ex_date to avoid drift.

    Idempotent on (asset, 'dividend', ex_date, provider).
    """
    if session.get(Asset, asset_id) is None:
        raise ValueError(f"unknown asset_id: {asset_id}")

    dps = _d(dividend_per_share)
    if dps < 0:
        raise ValueError(f"dividend_per_share must be non-negative, got {dps}")

    if _existing_action(session, asset_id, "dividend", ex_date, provider) is not None:
        return {"applied": False, "reason": "already recorded"}

    stmt = (
        select(Lot)
        .join(Transaction, Lot.open_transaction_id == Transaction.id)
        .where(
            Transaction.account_id == account_id,
            Lot.asset_id == asset_id,
            Lot.quantity_remaining > 0,
        )
    )
    lots = list(session.execute(stmt).scalars())
    total_qty = sum((_d(lot.quantity_remaining) for lot in lots), Decimal("0"))
    cash = total_qty * dps

    txn = Transaction(
        account_id=account_id,
        asset_id=asset_id,
        ts=ex_date,
        action="dividend",
        quantity=total_qty,
        price=dps,
        fees=None,
        currency="USD",
        notes=f"Dividend ex_date={ex_date.date().isoformat()} provider={provider}",
    )
    session.add(txn)
    session.flush()

    action = CorporateAction(
        asset_id=asset_id,
        action_type="dividend",
        ex_date=ex_date,
        ratio=None,
        amount=dps,
        currency="USD",
        provider=provider,
    )
    session.add(action)
    session.flush()

    return {
        "action_id": action.id,
        "transaction_id": txn.id,
        "applied": True,
        "qty_held": total_qty,
        "dividend_per_share": dps,
        "cash_received": cash,
    }
