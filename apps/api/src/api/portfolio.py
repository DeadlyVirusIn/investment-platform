"""Portfolio API – real ledger-backed endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.db.models import Asset, Transaction
from apps.api.src.domain.ledger.account_service import (
    AccountCreate,
    as_jsonable,
    create_account,
    list_accounts,
)
from apps.api.src.domain.ledger.pnl_calculator import (
    compute_pnl_summary,
    compute_positions,
)
from apps.api.src.domain.ledger.transaction_service import (
    TransactionCreate,
    create_transaction,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, dict):
        return {k: _jsonable(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    return v


def _txn_to_dict(txn: Transaction, symbol: str | None) -> dict[str, Any]:
    return {
        "id": txn.id,
        "account_id": txn.account_id,
        "asset_id": txn.asset_id,
        "symbol": symbol,
        "ts": txn.ts.isoformat() if txn.ts else None,
        "action": txn.action,
        "quantity": str(txn.quantity) if txn.quantity is not None else None,
        "price": str(txn.price) if txn.price is not None else None,
        "fees": str(txn.fees) if txn.fees is not None else None,
        "currency": txn.currency,
        "notes": txn.notes,
    }


@router.get("/summary")
def get_portfolio_summary(
    account_id: str = Query(..., description="account uuid"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _jsonable(compute_pnl_summary(session, account_id))


@router.get("/positions")
def get_positions(
    account_id: str = Query(..., description="account uuid"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    positions = compute_positions(session, account_id)
    return _jsonable(
        {"account_id": account_id, "positions": positions, "count": len(positions)}
    )


@router.get("/transactions")
def list_transactions(
    account_id: str = Query(..., description="account uuid"),
    limit: int = Query(100, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    stmt = (
        select(Transaction, Asset.symbol)
        .join(Asset, Transaction.asset_id == Asset.id)
        .where(Transaction.account_id == account_id)
        .order_by(Transaction.ts.desc())
        .limit(limit)
    )
    rows = session.execute(stmt).all()
    return {
        "account_id": account_id,
        "transactions": [_txn_to_dict(t, s) for t, s in rows],
        "count": len(rows),
    }


@router.post("/transactions", status_code=201)
def post_transaction(
    payload: TransactionCreate,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        result = create_transaction(session, payload)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return result.model_dump(mode="json")


@router.get("/pnl")
def get_pnl(
    account_id: str = Query(..., description="account uuid"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _jsonable(compute_pnl_summary(session, account_id))


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


@router.get("/accounts")
def get_accounts(session: Session = Depends(get_session)) -> dict[str, Any]:
    accounts = [as_jsonable(a) for a in list_accounts(session)]
    return {"accounts": accounts, "count": len(accounts)}


@router.post("/accounts", status_code=201)
def post_account(
    payload: AccountCreate,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        out = create_account(session, payload)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return as_jsonable(out)
