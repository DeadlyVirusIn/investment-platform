"""Integration tests for daily briefing."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, PriceBar
from apps.api.src.domain.briefing.briefing_service import build_briefing
from apps.api.src.domain.ledger.account_service import AccountCreate, create_account
from apps.api.src.domain.ledger.transaction_service import (
    TransactionCreate,
    create_transaction,
)
from apps.api.src.domain.recommendations.recommendation_engine import run_for_account

pytestmark = pytest.mark.integration


def test_briefing_structure_when_empty(pg_session: Session) -> None:
    acct = create_account(pg_session, AccountCreate(name="Empty", kind="broker"))
    pg_session.commit()

    out = build_briefing(pg_session, acct.id)
    assert out["account_id"] == acct.id
    assert "date" in out
    assert "generated_at" in out
    assert "portfolio_summary" in out
    assert out["top_actions"] == []
    assert out["stale_data"] == []
    assert "text_summary" in out


def test_briefing_with_position_and_recs(pg_session: Session) -> None:
    acct = create_account(pg_session, AccountCreate(name="Full", kind="broker"))
    asset = Asset(symbol="BRF", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    for i in range(160):
        offset = 159 - i
        p = Decimal("100") + Decimal("0.5") * i
        pg_session.add(PriceBar(
            asset_id=asset.id, timeframe="1d",
            ts=now - dt.timedelta(days=offset),
            open=p, high=p + Decimal("0.5"), low=p - Decimal("0.5"),
            close=p, adjusted_close=p, volume=1_000_000, provider="test",
        ))
    create_transaction(pg_session, TransactionCreate(
        account_id=acct.id, asset_id=asset.id,
        ts=now - dt.timedelta(days=150),
        action="buy", quantity=Decimal("10"), price=Decimal("100"),
    ))
    pg_session.commit()

    run_for_account(pg_session, acct.id)
    pg_session.commit()

    out = build_briefing(pg_session, acct.id)
    assert out["portfolio_summary"]["position_count"] == 1
    # top_actions may be empty if engine lands on Hold; text_summary present
    assert "text_summary" in out
    assert out["stale_data"] == []


def test_briefing_flags_stale_data(pg_session: Session) -> None:
    acct = create_account(pg_session, AccountCreate(name="Stale", kind="broker"))
    asset = Asset(symbol="OLD", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    old_bar = now - dt.timedelta(days=10)
    pg_session.add(PriceBar(
        asset_id=asset.id, timeframe="1d", ts=old_bar,
        open=Decimal("50"), high=Decimal("51"), low=Decimal("49"),
        close=Decimal("50"), adjusted_close=Decimal("50"),
        volume=100_000, provider="test",
    ))
    create_transaction(pg_session, TransactionCreate(
        account_id=acct.id, asset_id=asset.id, ts=old_bar,
        action="buy", quantity=Decimal("1"), price=Decimal("50"),
    ))
    pg_session.commit()

    out = build_briefing(pg_session, acct.id)
    assert len(out["stale_data"]) == 1
    assert out["stale_data"][0]["symbol"] == "OLD"
    assert "stale" in out["text_summary"].lower()
