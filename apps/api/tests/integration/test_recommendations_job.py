"""Integration: scheduled job runs recommendations for all accounts."""

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
from apps.worker.src.jobs.registry import run_recommendations_for_all_accounts

pytestmark = pytest.mark.integration


async def test_recommendations_job_generates_for_each_account(
    pg_session: Session,
) -> None:
    acct_a = create_account(pg_session, AccountCreate(name="A", kind="broker"))
    acct_b = create_account(pg_session, AccountCreate(name="B", kind="broker"))
    aapl = Asset(symbol="AAA", asset_class="equity", exchange="NASDAQ", currency="USD")
    msft = Asset(symbol="BBB", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add_all([aapl, msft])
    pg_session.flush()
    pg_session.commit()

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    for asset, base in [(aapl, Decimal("100")), (msft, Decimal("200"))]:
        for i in range(150):
            offset = 149 - i
            ts = now - dt.timedelta(days=offset)
            p = base + Decimal("0.5") * i
            pg_session.add(PriceBar(
                asset_id=asset.id, timeframe="1d", ts=ts,
                open=p, high=p + Decimal("0.5"), low=p - Decimal("0.5"),
                close=p, adjusted_close=p, volume=1_000_000, provider="test",
            ))
    pg_session.commit()

    # Each account holds one of the assets
    create_transaction(pg_session, TransactionCreate(
        account_id=acct_a.id, asset_id=aapl.id,
        ts=now - dt.timedelta(days=140),
        action="buy", quantity=Decimal("5"), price=Decimal("100"),
    ))
    create_transaction(pg_session, TransactionCreate(
        account_id=acct_b.id, asset_id=msft.id,
        ts=now - dt.timedelta(days=140),
        action="buy", quantity=Decimal("3"), price=Decimal("200"),
    ))
    pg_session.commit()

    await run_recommendations_for_all_accounts()

    pg_session.expire_all()
    recs = pg_session.scalars(select(Recommendation)).all()
    # One recommendation per held asset across the two accounts
    assert len(recs) == 2
    asset_ids = {r.asset_id for r in recs}
    assert asset_ids == {aapl.id, msft.id}


async def test_recommendations_job_is_idempotent(pg_session: Session) -> None:
    acct = create_account(pg_session, AccountCreate(name="Idem", kind="broker"))
    asset = Asset(symbol="IDEM", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    for i in range(120):
        offset = 119 - i
        p = Decimal("50") + Decimal("0.3") * i
        pg_session.add(PriceBar(
            asset_id=asset.id, timeframe="1d",
            ts=now - dt.timedelta(days=offset),
            open=p, high=p + Decimal("0.3"), low=p - Decimal("0.3"),
            close=p, adjusted_close=p, volume=500_000, provider="test",
        ))
    create_transaction(pg_session, TransactionCreate(
        account_id=acct.id, asset_id=asset.id,
        ts=now - dt.timedelta(days=110),
        action="buy", quantity=Decimal("4"), price=Decimal("50"),
    ))
    pg_session.commit()

    await run_recommendations_for_all_accounts()
    await run_recommendations_for_all_accounts()  # second run — should dedup

    pg_session.expire_all()
    recs = pg_session.scalars(select(Recommendation)).all()
    assert len(recs) == 1
