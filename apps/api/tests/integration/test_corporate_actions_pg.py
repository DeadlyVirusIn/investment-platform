"""Integration tests for splits + dividends (Postgres)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, CorporateAction, Lot, Transaction
from apps.api.src.domain.ledger.account_service import AccountCreate, create_account
from apps.api.src.domain.ledger.corporate_actions import apply_split, record_dividend
from apps.api.src.domain.ledger.pnl_calculator import (
    compute_pnl_summary,
    compute_positions,
    compute_realized_pnl,
)
from apps.api.src.domain.ledger.transaction_service import (
    TransactionCreate,
    create_transaction,
)

pytestmark = pytest.mark.integration

BASE_TS = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def _seed(pg_session: Session, symbol: str = "AAPL") -> tuple[str, str]:
    acct = create_account(pg_session, AccountCreate(name="T", kind="broker"))
    asset = Asset(symbol=symbol, asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()
    return acct.id, asset.id


def _buy(pg_session, account_id, asset_id, qty, price, offset_days=0):
    res = create_transaction(
        pg_session,
        TransactionCreate(
            account_id=account_id,
            asset_id=asset_id,
            ts=BASE_TS + dt.timedelta(days=offset_days),
            action="buy",
            quantity=Decimal(str(qty)),
            price=Decimal(str(price)),
        ),
    )
    pg_session.commit()
    return res


def test_forward_split_2_for_1(pg_session: Session) -> None:
    account_id, asset_id = _seed(pg_session)
    _buy(pg_session, account_id, asset_id, 100, 150)

    result = apply_split(
        pg_session,
        asset_id=asset_id,
        ratio=Decimal("2"),
        ex_date=BASE_TS + dt.timedelta(days=30),
    )
    pg_session.commit()

    assert result["applied"] is True
    assert result["lots_adjusted"] == 1

    pg_session.expire_all()
    lot = pg_session.scalars(select(Lot).where(Lot.asset_id == asset_id)).first()
    assert Decimal(str(lot.quantity_remaining)) == Decimal("200")
    assert Decimal(str(lot.quantity_opened)) == Decimal("200")
    assert Decimal(str(lot.cost_basis_per_unit)) == Decimal("75")

    # Total cost basis preserved: 100 * 150 = 200 * 75 = 15000
    summary = compute_pnl_summary(pg_session, account_id)
    assert summary["total_cost_basis"] == Decimal("15000")


def test_reverse_split_1_for_10(pg_session: Session) -> None:
    account_id, asset_id = _seed(pg_session, symbol="XYZ")
    _buy(pg_session, account_id, asset_id, 100, Decimal("1.50"))

    result = apply_split(
        pg_session,
        asset_id=asset_id,
        ratio=Decimal("0.1"),
        ex_date=BASE_TS + dt.timedelta(days=30),
    )
    pg_session.commit()

    assert result["applied"] is True
    pg_session.expire_all()
    lot = pg_session.scalars(select(Lot).where(Lot.asset_id == asset_id)).first()
    assert Decimal(str(lot.quantity_remaining)) == Decimal("10")
    assert Decimal(str(lot.cost_basis_per_unit)) == Decimal("15")


def test_split_idempotent(pg_session: Session) -> None:
    account_id, asset_id = _seed(pg_session)
    _buy(pg_session, account_id, asset_id, 100, 150)
    ex = BASE_TS + dt.timedelta(days=30)

    r1 = apply_split(pg_session, asset_id=asset_id, ratio=2, ex_date=ex)
    pg_session.commit()
    r2 = apply_split(pg_session, asset_id=asset_id, ratio=2, ex_date=ex)
    pg_session.commit()

    assert r1["applied"] is True
    assert r2["applied"] is False
    assert r2["reason"] == "already applied"

    pg_session.expire_all()
    lot = pg_session.scalars(select(Lot).where(Lot.asset_id == asset_id)).first()
    # Still 200 — not doubled again.
    assert Decimal(str(lot.quantity_remaining)) == Decimal("200")


def test_split_preserves_multi_lot_total_basis(pg_session: Session) -> None:
    account_id, asset_id = _seed(pg_session)
    _buy(pg_session, account_id, asset_id, 50, 100, offset_days=0)
    _buy(pg_session, account_id, asset_id, 50, 200, offset_days=1)

    apply_split(
        pg_session,
        asset_id=asset_id,
        ratio=Decimal("2"),
        ex_date=BASE_TS + dt.timedelta(days=10),
    )
    pg_session.commit()

    pg_session.expire_all()
    positions = compute_positions(pg_session, account_id)
    assert len(positions) == 1
    assert positions[0]["quantity"] == Decimal("200")  # (50+50) * 2
    # Total cost basis preserved: 50*100 + 50*200 = 15000
    assert positions[0]["total_cost_basis"] == Decimal("15000")


def test_dividend_creates_txn_and_updates_realized(pg_session: Session) -> None:
    account_id, asset_id = _seed(pg_session)
    _buy(pg_session, account_id, asset_id, 100, 150)

    result = record_dividend(
        pg_session,
        account_id=account_id,
        asset_id=asset_id,
        ex_date=BASE_TS + dt.timedelta(days=30),
        dividend_per_share=Decimal("0.50"),
    )
    pg_session.commit()

    assert result["applied"] is True
    assert result["qty_held"] == Decimal("100")
    assert result["cash_received"] == Decimal("50.00")

    # Transaction row recorded with action='dividend'
    div_txns = pg_session.scalars(
        select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.action == "dividend",
        )
    ).all()
    assert len(div_txns) == 1

    # Realized P&L includes dividend
    assert compute_realized_pnl(pg_session, account_id) == Decimal("50.00")

    # No lots opened or closed by the dividend
    lots = pg_session.scalars(select(Lot).where(Lot.asset_id == asset_id)).all()
    assert len(lots) == 1
    assert Decimal(str(lots[0].quantity_remaining)) == Decimal("100")


def test_dividend_idempotent(pg_session: Session) -> None:
    account_id, asset_id = _seed(pg_session)
    _buy(pg_session, account_id, asset_id, 100, 150)
    ex = BASE_TS + dt.timedelta(days=30)

    r1 = record_dividend(pg_session, account_id, asset_id, ex, Decimal("0.5"))
    pg_session.commit()
    r2 = record_dividend(pg_session, account_id, asset_id, ex, Decimal("0.5"))
    pg_session.commit()

    assert r1["applied"] is True
    assert r2["applied"] is False

    # Only one CorporateAction row + one dividend Transaction
    actions = pg_session.scalars(
        select(CorporateAction).where(
            CorporateAction.asset_id == asset_id,
            CorporateAction.action_type == "dividend",
        )
    ).all()
    assert len(actions) == 1

    div_txns = pg_session.scalars(
        select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.action == "dividend",
        )
    ).all()
    assert len(div_txns) == 1
