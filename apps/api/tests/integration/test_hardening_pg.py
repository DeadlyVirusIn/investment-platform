"""Integration tests for Phase 1.5 hardening: snapshot unique, stale forces
Watch, outcome row created, performance API."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    PriceBar,
    Recommendation,
    RecommendationOutcome,
)
from apps.api.src.domain.ledger.account_service import AccountCreate, create_account
from apps.api.src.domain.ledger.transaction_service import (
    TransactionCreate,
    create_transaction,
)
from apps.api.src.domain.recommendations.recommendation_engine import (
    compute_for_asset,
    load_engine_config,
    run_for_account,
)

pytestmark = pytest.mark.integration


def _seed_asset_and_prices(
    pg_session: Session,
    symbol: str = "HDN",
    n: int = 160,
    end_offset_days: int = 0,
    step: Decimal = Decimal("0.5"),
    start: Decimal = Decimal("100"),
) -> str:
    asset = Asset(symbol=symbol, asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    for i in range(n):
        offset = n - 1 - i + end_offset_days
        ts = now - dt.timedelta(days=offset)
        p = start + step * Decimal(i)
        pg_session.add(PriceBar(
            asset_id=asset.id, timeframe="1d", ts=ts,
            open=p, high=p + Decimal("0.5"), low=p - Decimal("0.5"),
            close=p, adjusted_close=p, volume=1_000_000, provider="test",
        ))
    pg_session.commit()
    return asset.id


# ---------------------------------------------------------------------------
# A. Snapshot hash uniqueness
# ---------------------------------------------------------------------------


def test_snapshot_hash_unique_constraint_blocks_duplicate(pg_session: Session) -> None:
    asset_id = _seed_asset_and_prices(pg_session, symbol="UNQ")
    # Manual insert of two rows with same (asset, version, snapshot)
    pg_session.add(Recommendation(
        asset_id=asset_id, action="Hold", model_version="0.1.0",
        snapshot_hash="abc123", rationale="{}",
    ))
    pg_session.commit()

    pg_session.add(Recommendation(
        asset_id=asset_id, action="Buy", model_version="0.1.0",
        snapshot_hash="abc123", rationale="{}",
    ))
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


def test_persist_uses_direct_lookup_no_duplicate(pg_session: Session) -> None:
    acct = create_account(pg_session, AccountCreate(name="Dir", kind="broker"))
    asset_id = _seed_asset_and_prices(pg_session, symbol="DIR")
    create_transaction(pg_session, TransactionCreate(
        account_id=acct.id, asset_id=asset_id,
        ts=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=120),
        action="buy", quantity=Decimal("5"), price=Decimal("100"),
    ))
    pg_session.commit()

    cfg = load_engine_config()
    first = run_for_account(pg_session, acct.id, config=cfg)
    pg_session.commit()
    second = run_for_account(pg_session, acct.id, config=cfg)
    pg_session.commit()

    assert first[0].recommendation_id == second[0].recommendation_id
    rows = pg_session.scalars(select(Recommendation)).all()
    assert len(rows) == 1
    # snapshot_hash populated on the dedicated column
    assert rows[0].snapshot_hash == first[0].snapshot_hash


# ---------------------------------------------------------------------------
# D. Stale data
# ---------------------------------------------------------------------------


def test_stale_prices_force_watch(pg_session: Session) -> None:
    acct = create_account(pg_session, AccountCreate(name="Stale", kind="broker"))
    # Seed series ending 10 days ago → stale
    asset_id = _seed_asset_and_prices(
        pg_session, symbol="STA", n=160, end_offset_days=10,
    )
    create_transaction(pg_session, TransactionCreate(
        account_id=acct.id, asset_id=asset_id,
        ts=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=150),
        action="buy", quantity=Decimal("5"), price=Decimal("100"),
    ))
    pg_session.commit()

    cfg = load_engine_config()
    result = compute_for_asset(
        pg_session, account_id=acct.id, asset_id=asset_id, config=cfg
    )
    assert result.stale_data is True
    assert result.enough_data is False
    assert result.action == "Watch"
    assert result.confidence == Decimal("0")
    assert "stale-data" in result.tags


# ---------------------------------------------------------------------------
# E. Outcome row
# ---------------------------------------------------------------------------


def test_outcome_row_created_on_persist(pg_session: Session) -> None:
    acct = create_account(pg_session, AccountCreate(name="Out", kind="broker"))
    asset_id = _seed_asset_and_prices(pg_session, symbol="OUT")
    create_transaction(pg_session, TransactionCreate(
        account_id=acct.id, asset_id=asset_id,
        ts=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=150),
        action="buy", quantity=Decimal("5"), price=Decimal("100"),
    ))
    pg_session.commit()

    results = run_for_account(pg_session, acct.id)
    pg_session.commit()
    rec_id = results[0].recommendation_id

    outcomes = pg_session.scalars(
        select(RecommendationOutcome).where(
            RecommendationOutcome.recommendation_id == rec_id
        )
    ).all()
    assert len(outcomes) == 1
    assert outcomes[0].price_at_recommendation is not None
    assert outcomes[0].price_after_30d is None   # stub
    assert outcomes[0].realized_30d_return is None


# ---------------------------------------------------------------------------
# B. Confidence (integration)
# ---------------------------------------------------------------------------


def test_confidence_label_present_on_persisted_rec(pg_session: Session) -> None:
    acct = create_account(pg_session, AccountCreate(name="Conf", kind="broker"))
    asset_id = _seed_asset_and_prices(pg_session, symbol="CNF")
    create_transaction(pg_session, TransactionCreate(
        account_id=acct.id, asset_id=asset_id,
        ts=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=150),
        action="buy", quantity=Decimal("5"), price=Decimal("100"),
    ))
    pg_session.commit()

    results = run_for_account(pg_session, acct.id)
    pg_session.commit()

    assert results[0].confidence_label in ("Low", "Medium", "High")
    # Confidence is on a 0..100 scale now
    assert Decimal("0") <= results[0].confidence <= Decimal("100")


# ---------------------------------------------------------------------------
# C. RSI override (integration ensures thesis reflects it)
# ---------------------------------------------------------------------------


def test_uptrend_no_longer_forces_negative_composite(pg_session: Session) -> None:
    acct = create_account(pg_session, AccountCreate(name="Up", kind="broker"))
    asset_id = _seed_asset_and_prices(pg_session, symbol="UPT")
    # No holdings → no exposure penalty
    cfg = load_engine_config()
    result = compute_for_asset(
        pg_session, account_id=acct.id, asset_id=asset_id, config=cfg,
    )
    assert result.enough_data is True
    assert result.family_scores["trend_momentum"] > Decimal("0.3")
    # With RSI override + trend_strength, composite clearly bullish:
    assert result.composite_score > Decimal("0.2")
