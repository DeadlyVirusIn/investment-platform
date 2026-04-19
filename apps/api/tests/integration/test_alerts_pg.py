"""Integration tests for alert engine."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, PriceBar, Recommendation
from apps.api.src.domain.alerts.alert_engine import (
    AlertCreate,
    create_alert,
    evaluate_alerts,
)
from apps.api.src.domain.ledger.account_service import AccountCreate, create_account
from apps.api.src.domain.ledger.transaction_service import (
    TransactionCreate,
    create_transaction,
)

pytestmark = pytest.mark.integration


def _seed_price(pg_session, asset_id, value):
    now = dt.datetime.now(dt.timezone.utc)
    pg_session.add(PriceBar(
        asset_id=asset_id, timeframe="1d", ts=now,
        open=value, high=value + Decimal("0.5"), low=value - Decimal("0.5"),
        close=value, adjusted_close=value, volume=1_000_000, provider="test",
    ))
    pg_session.commit()


def test_price_above_fires_when_crossed(pg_session: Session) -> None:
    asset = Asset(symbol="ABV", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    _seed_price(pg_session, asset.id, Decimal("200"))

    create_alert(pg_session, AlertCreate(
        alert_type="price_above", asset_id=asset.id, threshold=Decimal("150"),
    ))
    pg_session.commit()

    fired = evaluate_alerts(pg_session)
    pg_session.commit()
    assert len(fired) == 1
    assert fired[0]["alert_type"] == "price_above"
    assert Decimal(fired[0]["detail"]["price"]) == Decimal("200")


def test_price_above_does_not_fire_below_threshold(pg_session: Session) -> None:
    asset = Asset(symbol="BEL", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    _seed_price(pg_session, asset.id, Decimal("120"))

    create_alert(pg_session, AlertCreate(
        alert_type="price_above", asset_id=asset.id, threshold=Decimal("150"),
    ))
    pg_session.commit()

    fired = evaluate_alerts(pg_session)
    pg_session.commit()
    assert fired == []


def test_24h_cooldown_blocks_reflring(pg_session: Session) -> None:
    asset = Asset(symbol="CD", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    _seed_price(pg_session, asset.id, Decimal("200"))

    create_alert(pg_session, AlertCreate(
        alert_type="price_above", asset_id=asset.id, threshold=Decimal("150"),
    ))
    pg_session.commit()

    first = evaluate_alerts(pg_session)
    pg_session.commit()
    assert len(first) == 1

    second = evaluate_alerts(pg_session)
    pg_session.commit()
    assert second == []  # cooldown prevents refire


def test_concentration_alert_fires(pg_session: Session) -> None:
    acct = create_account(pg_session, AccountCreate(name="Conc", kind="broker"))
    asset = Asset(symbol="CONC", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    _seed_price(pg_session, asset.id, Decimal("100"))
    create_transaction(pg_session, TransactionCreate(
        account_id=acct.id, asset_id=asset.id,
        ts=dt.datetime.now(dt.timezone.utc),
        action="buy", quantity=Decimal("10"), price=Decimal("100"),
    ))
    pg_session.commit()

    create_alert(pg_session, AlertCreate(
        alert_type="concentration", account_id=acct.id, threshold=Decimal("15"),
    ))
    pg_session.commit()

    fired = evaluate_alerts(pg_session)
    pg_session.commit()
    # 100% concentration in single asset → fires above 15% threshold
    assert len(fired) == 1
    assert fired[0]["alert_type"] == "concentration"


def test_recommendation_changed_fires_on_action_change(pg_session: Session) -> None:
    asset = Asset(symbol="RCH", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()

    # Seed two recommendations with different actions
    now = dt.datetime.now(dt.timezone.utc)
    pg_session.add(Recommendation(
        asset_id=asset.id, generated_at=now - dt.timedelta(hours=2),
        action="Hold", conviction=Decimal("0.2"),
        rationale='{"snapshot_hash":"a"}', model_version="0.1.0",
    ))
    pg_session.add(Recommendation(
        asset_id=asset.id, generated_at=now,
        action="Buy", conviction=Decimal("0.6"),
        rationale='{"snapshot_hash":"b"}', model_version="0.1.0",
    ))
    pg_session.commit()

    create_alert(pg_session, AlertCreate(
        alert_type="recommendation_changed", asset_id=asset.id,
    ))
    pg_session.commit()

    fired = evaluate_alerts(pg_session)
    pg_session.commit()
    assert len(fired) == 1
    assert fired[0]["detail"]["prior_action"] == "Hold"
    assert fired[0]["detail"]["latest_action"] == "Buy"


def test_invalid_alert_payload_raises(pg_session: Session) -> None:
    with pytest.raises(ValueError, match="requires asset_id"):
        create_alert(pg_session, AlertCreate(
            alert_type="price_above", threshold=Decimal("100"),
        ))
