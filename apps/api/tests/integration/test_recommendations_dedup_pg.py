"""Integration: recommendation dedup via snapshot_hash."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, PriceBar, Recommendation
from apps.api.src.domain.ledger.account_service import AccountCreate, create_account
from apps.api.src.domain.ledger.transaction_service import (
    TransactionCreate,
    create_transaction,
)
from apps.api.src.domain.recommendations.recommendation_engine import (
    load_engine_config,
    run_for_account,
)

pytestmark = pytest.mark.integration


def _seed(pg_session: Session) -> str:
    acct = create_account(pg_session, AccountCreate(name="Dedup", kind="broker"))
    asset = Asset(symbol="DUP", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    for i in range(150):
        offset = 149 - i
        ts = now - dt.timedelta(days=offset)
        p = Decimal("100") + Decimal("0.5") * i
        pg_session.add(PriceBar(
            asset_id=asset.id, timeframe="1d", ts=ts,
            open=p, high=p + Decimal("0.5"), low=p - Decimal("0.5"),
            close=p, adjusted_close=p, volume=1_000_000, provider="test",
        ))
    pg_session.commit()

    create_transaction(pg_session, TransactionCreate(
        account_id=acct.id, asset_id=asset.id,
        ts=now - dt.timedelta(days=140),
        action="buy", quantity=Decimal("10"), price=Decimal("100"),
    ))
    pg_session.commit()
    return acct.id


def test_dedup_same_snapshot_writes_once(pg_session: Session) -> None:
    account_id = _seed(pg_session)
    cfg = load_engine_config()

    first = run_for_account(pg_session, account_id, config=cfg)
    pg_session.commit()
    second = run_for_account(pg_session, account_id, config=cfg)
    pg_session.commit()

    assert len(first) == 1
    assert len(second) == 1
    # Same id returned on dedup
    assert first[0].recommendation_id == second[0].recommendation_id
    assert first[0].snapshot_hash == second[0].snapshot_hash

    # Exactly one row in DB
    rows = pg_session.scalars(select(Recommendation)).all()
    assert len(rows) == 1


def test_dedup_creates_new_row_when_price_changes(pg_session: Session) -> None:
    account_id = _seed(pg_session)
    cfg = load_engine_config()

    first = run_for_account(pg_session, account_id, config=cfg)
    pg_session.commit()

    # Add one more price bar → changes last_price_ts → different snapshot_hash
    asset = pg_session.scalars(select(Asset).where(Asset.symbol == "DUP")).first()
    new_ts = dt.datetime.now(dt.timezone.utc).replace(microsecond=0) + dt.timedelta(days=1)
    pg_session.add(PriceBar(
        asset_id=asset.id, timeframe="1d", ts=new_ts,
        open=Decimal("250"), high=Decimal("251"), low=Decimal("249"),
        close=Decimal("250"), adjusted_close=Decimal("250"),
        volume=1_000_000, provider="test",
    ))
    pg_session.commit()

    second = run_for_account(pg_session, account_id, config=cfg)
    pg_session.commit()

    assert first[0].snapshot_hash != second[0].snapshot_hash
    assert first[0].recommendation_id != second[0].recommendation_id

    rows = pg_session.scalars(select(Recommendation)).all()
    assert len(rows) == 2
