"""Integration tests: FIFO lot tracking against real Postgres (NUMERIC + tz)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, Lot, LotClose, PriceBar, Transaction
from apps.api.src.domain.ledger.account_service import AccountCreate, create_account
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


def _seed_account_asset(
    pg_session: Session, symbol: str = "AAPL", asset_class: str = "equity"
) -> tuple[str, str]:
    acct = create_account(pg_session, AccountCreate(name="IntTest", kind="broker"))
    asset = Asset(symbol=symbol, asset_class=asset_class, exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()
    return acct.id, asset.id


def _buy(pg_session, account_id, asset_id, qty, price, offset_days=0, fees=None):
    payload = TransactionCreate(
        account_id=account_id,
        asset_id=asset_id,
        ts=BASE_TS + dt.timedelta(days=offset_days),
        action="buy",
        quantity=Decimal(str(qty)),
        price=Decimal(str(price)),
        fees=Decimal(str(fees)) if fees is not None else None,
    )
    res = create_transaction(pg_session, payload)
    pg_session.commit()
    return res


def _sell(pg_session, account_id, asset_id, qty, price, offset_days=10, fees=None):
    payload = TransactionCreate(
        account_id=account_id,
        asset_id=asset_id,
        ts=BASE_TS + dt.timedelta(days=offset_days),
        action="sell",
        quantity=Decimal(str(qty)),
        price=Decimal(str(price)),
        fees=Decimal(str(fees)) if fees is not None else None,
    )
    res = create_transaction(pg_session, payload)
    pg_session.commit()
    return res


def test_buy_creates_open_lot(pg_session: Session) -> None:
    account_id, asset_id = _seed_account_asset(pg_session)
    res = _buy(pg_session, account_id, asset_id, 100, 150)

    assert len(res.lot_ids_opened) == 1
    lot = pg_session.get(Lot, res.lot_ids_opened[0])
    assert Decimal(str(lot.quantity_remaining)) == Decimal("100")
    assert Decimal(str(lot.cost_basis_per_unit)) == Decimal("150")


def test_sell_fifo_closes_lots_and_persists_realized(pg_session: Session) -> None:
    account_id, asset_id = _seed_account_asset(pg_session)
    _buy(pg_session, account_id, asset_id, 50, 100, offset_days=0)
    _buy(pg_session, account_id, asset_id, 50, 200, offset_days=1)
    res = _sell(pg_session, account_id, asset_id, 80, 250, offset_days=10)

    assert len(res.lot_close_ids) == 2
    assert res.realized_pnl == Decimal("9000")

    # Re-read from DB in a fresh query to prove persistence, not just in-memory state
    pg_session.expire_all()
    closes = pg_session.query(LotClose).all()
    assert len(closes) == 2
    total_persisted = sum(
        (Decimal(str(c.realized_pnl)) for c in closes if c.realized_pnl is not None),
        Decimal("0"),
    )
    assert total_persisted == Decimal("9000")
    assert compute_realized_pnl(pg_session, account_id) == Decimal("9000")

    positions = compute_positions(pg_session, account_id)
    assert len(positions) == 1
    assert positions[0]["quantity"] == Decimal("20")
    assert positions[0]["avg_cost_basis"] == Decimal("200")


def test_unrealized_uses_latest_adjusted_close(pg_session: Session) -> None:
    account_id, asset_id = _seed_account_asset(pg_session)
    _buy(pg_session, account_id, asset_id, 100, 150)

    # Seed a price_bar row as if Tiingo ingestion had already run
    bar = PriceBar(
        asset_id=asset_id,
        timeframe="1d",
        ts=BASE_TS + dt.timedelta(days=5),
        open=Decimal("160"),
        high=Decimal("165"),
        low=Decimal("158"),
        close=Decimal("162"),
        adjusted_close=Decimal("162"),
        volume=1_000_000,
        provider="tiingo",
    )
    pg_session.add(bar)
    pg_session.commit()

    summary = compute_pnl_summary(pg_session, account_id)
    # 100 * (162 - 150) = 1200
    assert summary["unrealized_pnl"] == Decimal("1200")
    assert summary["total_market_value"] == Decimal("16200")
    assert summary["total_cost_basis"] == Decimal("15000")


def test_crypto_numeric_precision_roundtrip(pg_session: Session) -> None:
    account_id, asset_id = _seed_account_asset(pg_session, symbol="BTC", asset_class="crypto")
    # 0.0000000123 BTC ≈ 12.3 sat — within NUMERIC(28,10) headroom (10 decimals)
    tiny_qty = Decimal("0.0000000123")
    res = _buy(pg_session, account_id, asset_id, tiny_qty, 50000)

    pg_session.expire_all()
    lot = pg_session.get(Lot, res.lot_ids_opened[0])
    assert Decimal(str(lot.quantity_remaining)) == tiny_qty


def test_timezone_aware_ts_roundtrip(pg_session: Session) -> None:
    account_id, asset_id = _seed_account_asset(pg_session)
    ts = dt.datetime(2026, 3, 14, 9, 30, tzinfo=dt.timezone.utc)
    payload = TransactionCreate(
        account_id=account_id,
        asset_id=asset_id,
        ts=ts,
        action="buy",
        quantity=Decimal("10"),
        price=Decimal("100"),
    )
    res = create_transaction(pg_session, payload)
    pg_session.commit()

    pg_session.expire_all()
    txn = pg_session.get(Transaction, res.transaction_id)
    assert txn.ts.tzinfo is not None
    assert txn.ts.astimezone(dt.timezone.utc) == ts
