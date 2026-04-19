"""Integration tests for asset creation + listing."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from apps.api.src.domain.assets.asset_service import (
    AssetCreate,
    create_asset,
    list_assets,
)

pytestmark = pytest.mark.integration


def test_create_asset_persists(pg_session: Session) -> None:
    out = create_asset(
        pg_session,
        AssetCreate(symbol="AAPL", name="Apple Inc.", asset_class="equity", exchange="NASDAQ"),
    )
    pg_session.commit()

    assert out.id
    assert out.symbol == "AAPL"
    assert out.asset_class == "equity"
    assert out.exchange == "NASDAQ"
    assert out.currency == "USD"
    assert out.is_active is True


def test_asset_duplicate_raises(pg_session: Session) -> None:
    create_asset(pg_session, AssetCreate(symbol="AAPL", asset_class="equity", exchange="NASDAQ"))
    pg_session.commit()
    with pytest.raises(ValueError, match="already exists"):
        create_asset(
            pg_session, AssetCreate(symbol="AAPL", asset_class="equity", exchange="NASDAQ")
        )


def test_asset_list_ordered_by_symbol(pg_session: Session) -> None:
    for sym in ("TSLA", "AAPL", "MSFT"):
        create_asset(pg_session, AssetCreate(symbol=sym, asset_class="equity", exchange="NASDAQ"))
    pg_session.commit()

    listed = list_assets(pg_session)
    assert [a.symbol for a in listed] == ["AAPL", "MSFT", "TSLA"]


def test_asset_same_symbol_different_exchange_allowed(pg_session: Session) -> None:
    create_asset(pg_session, AssetCreate(symbol="BRK", asset_class="equity", exchange="NYSE"))
    pg_session.commit()
    create_asset(pg_session, AssetCreate(symbol="BRK", asset_class="equity", exchange="OTC"))
    pg_session.commit()
    assert len(list_assets(pg_session)) == 2
