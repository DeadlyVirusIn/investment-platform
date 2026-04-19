"""FIFO lot-tracker + realized P&L tests.

Uses an in-memory SQLite harness. Production DB is Postgres; SQLite is only
a fast unit-test harness. Numeric precision is sufficient for these scenarios.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db import Base
import apps.api.src.db.models  # noqa: F401 — registers ORM classes on Base.metadata
from apps.api.src.db.models import Account, Asset, Lot
from apps.api.src.domain.ledger.pnl_calculator import (
    compute_pnl_summary,
    compute_positions,
    compute_realized_pnl,
)
from apps.api.src.domain.ledger.transaction_service import (
    TransactionCreate,
    create_transaction,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionCls = sessionmaker(bind=engine, class_=Session)
    session = SessionCls()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seed(db: Session) -> dict[str, Account | Asset]:
    acct = Account(name="Test Brokerage", account_type="taxable", currency="USD")
    asset = Asset(symbol="AAPL", asset_class="equity", exchange="NASDAQ", currency="USD")
    db.add_all([acct, asset])
    db.flush()
    return {"account": acct, "asset": asset}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


BASE_TS = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def _buy(
    db: Session,
    seed: dict[str, Account | Asset],
    qty: object,
    price: object,
    ts_offset_days: int = 0,
    fees: object | None = None,
):
    payload = TransactionCreate(
        account_id=seed["account"].id,
        asset_id=seed["asset"].id,
        ts=BASE_TS + dt.timedelta(days=ts_offset_days),
        action="buy",
        quantity=Decimal(str(qty)),
        price=Decimal(str(price)),
        fees=Decimal(str(fees)) if fees is not None else None,
    )
    return create_transaction(db, payload)


def _sell(
    db: Session,
    seed: dict[str, Account | Asset],
    qty: object,
    price: object,
    ts_offset_days: int = 10,
    fees: object | None = None,
):
    payload = TransactionCreate(
        account_id=seed["account"].id,
        asset_id=seed["asset"].id,
        ts=BASE_TS + dt.timedelta(days=ts_offset_days),
        action="sell",
        quantity=Decimal(str(qty)),
        price=Decimal(str(price)),
        fees=Decimal(str(fees)) if fees is not None else None,
    )
    return create_transaction(db, payload)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_buy_opens_lot(db: Session, seed) -> None:
    res = _buy(db, seed, 100, 150)
    assert len(res.lot_ids_opened) == 1
    assert len(res.lot_close_ids) == 0
    assert res.realized_pnl == Decimal("0")

    lot = db.get(Lot, res.lot_ids_opened[0])
    assert Decimal(str(lot.quantity_opened)) == Decimal("100")
    assert Decimal(str(lot.quantity_remaining)) == Decimal("100")
    assert Decimal(str(lot.cost_basis_per_unit)) == Decimal("150")

    positions = compute_positions(db, seed["account"].id)
    assert len(positions) == 1
    p = positions[0]
    assert p["symbol"] == "AAPL"
    assert p["quantity"] == Decimal("100")
    assert p["avg_cost_basis"] == Decimal("150")
    assert p["lot_count"] == 1


def test_partial_sell(db: Session, seed) -> None:
    _buy(db, seed, 100, 150)
    res = _sell(db, seed, 40, 160)
    assert len(res.lot_close_ids) == 1
    # 40 * (160 - 150) = 400
    assert res.realized_pnl == Decimal("400")

    positions = compute_positions(db, seed["account"].id)
    assert len(positions) == 1
    assert positions[0]["quantity"] == Decimal("60")
    assert positions[0]["avg_cost_basis"] == Decimal("150")

    assert compute_realized_pnl(db, seed["account"].id) == Decimal("400")


def test_full_sell(db: Session, seed) -> None:
    _buy(db, seed, 100, 150)
    res = _sell(db, seed, 100, 160)
    assert len(res.lot_close_ids) == 1
    assert res.realized_pnl == Decimal("1000")  # 100 * 10

    positions = compute_positions(db, seed["account"].id)
    assert positions == []
    assert compute_realized_pnl(db, seed["account"].id) == Decimal("1000")


def test_split_lots_fifo(db: Session, seed) -> None:
    """FIFO consumes lot1 fully then eats into lot2."""
    _buy(db, seed, 50, 100, ts_offset_days=0)
    _buy(db, seed, 50, 200, ts_offset_days=1)
    res = _sell(db, seed, 80, 250, ts_offset_days=10)

    assert len(res.lot_close_ids) == 2
    # 50 * (250 - 100) + 30 * (250 - 200) = 7500 + 1500 = 9000
    assert res.realized_pnl == Decimal("9000")

    positions = compute_positions(db, seed["account"].id)
    assert len(positions) == 1
    p = positions[0]
    assert p["quantity"] == Decimal("20")
    # only lot2 remains at basis 200
    assert p["avg_cost_basis"] == Decimal("200")
    assert p["lot_count"] == 1


def test_oversell_raises(db: Session, seed) -> None:
    _buy(db, seed, 50, 100)
    with pytest.raises(ValueError, match="insufficient"):
        _sell(db, seed, 100, 120)


def test_pnl_summary_without_prices(db: Session, seed) -> None:
    _buy(db, seed, 100, 150)
    _sell(db, seed, 40, 160)
    s = compute_pnl_summary(db, seed["account"].id)

    assert s["realized_pnl"] == Decimal("400")
    assert s["position_count"] == 1
    # no price_bar rows → unrealized fields are None
    assert s["unrealized_pnl"] is None
    assert s["total_market_value"] is None
    # 60 remaining * 150 basis = 9000
    assert s["total_cost_basis"] == Decimal("9000")


def test_fees_absorbed_and_deducted(db: Session, seed) -> None:
    """Fees absorbed into basis on buy, deducted from proceeds on sell."""
    res_buy = _buy(db, seed, 100, 100, fees=10)
    lot = db.get(Lot, res_buy.lot_ids_opened[0])
    # basis = 100 + 10/100 = 100.1
    assert Decimal(str(lot.cost_basis_per_unit)) == Decimal("100.1")

    res_sell = _sell(db, seed, 100, 120, fees=5)
    # proceeds/unit = 120 - 5/100 = 119.95
    # realized = 100 * (119.95 - 100.1) = 100 * 19.85 = 1985
    assert res_sell.realized_pnl == Decimal("1985")
