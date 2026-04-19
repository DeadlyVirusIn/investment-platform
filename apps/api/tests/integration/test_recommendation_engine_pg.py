"""Integration tests: recommendation engine end-to-end with Postgres."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    PriceBar,
    Recommendation,
    RecommendationEvidence,
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

BASE_TS = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def _seed_account_and_asset(
    pg_session: Session, symbol: str = "AAPL"
) -> tuple[str, str]:
    acct = create_account(pg_session, AccountCreate(name="E2E", kind="broker"))
    asset = Asset(symbol=symbol, asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()
    return acct.id, asset.id


def _seed_price_series(
    pg_session: Session,
    asset_id: str,
    n: int,
    start_price: Decimal = Decimal("100"),
    step: Decimal = Decimal("0.5"),
) -> None:
    """Seed n daily price_bar rows ending today, ascending by `step`."""
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    for i in range(n):
        # oldest first, ending on the most recent day
        offset = n - 1 - i
        ts = now - dt.timedelta(days=offset)
        price = start_price + step * Decimal(i)
        pg_session.add(PriceBar(
            asset_id=asset_id,
            timeframe="1d",
            ts=ts,
            open=price,
            high=price + Decimal("0.5"),
            low=price - Decimal("0.5"),
            close=price,
            adjusted_close=price,
            volume=1_000_000,
            provider="test",
        ))
    pg_session.commit()


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


def test_uptrend_produces_positive_trend_signal(pg_session: Session) -> None:
    """Monotonic uptrend must produce a bullish trend_momentum family score
    and a non-bearish action. Composite may land in Buy or Hold depending
    on RSI saturation; both are valid engine outputs."""
    account_id, asset_id = _seed_account_and_asset(pg_session)
    _seed_price_series(pg_session, asset_id, n=250)  # 250-day uptrend
    # No holdings → exposure neutral; isolates trend/vol signal effect.

    cfg = load_engine_config()
    result = compute_for_asset(
        pg_session, account_id=account_id, asset_id=asset_id, config=cfg
    )

    assert result.enough_data is True
    # Trend family bullish on monotonic uptrend
    assert result.family_scores["trend_momentum"] > Decimal("0")
    # Engine picks a non-bearish action
    assert result.action in ("Buy", "Hold")
    assert "equity" in result.tags
    assert result.snapshot_hash and len(result.snapshot_hash) == 16
    assert result.signals

    fam_keys = {s["family"] for s in result.signals}
    assert "trend_momentum" in fam_keys
    assert "volatility_risk" in fam_keys
    assert "exposure" in fam_keys


def test_downtrend_produces_sell_or_trim(pg_session: Session) -> None:
    account_id, asset_id = _seed_account_and_asset(pg_session, symbol="BAD")
    # Strong downtrend
    _seed_price_series(
        pg_session, asset_id, n=250,
        start_price=Decimal("200"), step=Decimal("-0.5"),
    )
    _buy(pg_session, account_id, asset_id, qty=10, price=200)

    cfg = load_engine_config()
    result = compute_for_asset(
        pg_session, account_id=account_id, asset_id=asset_id, config=cfg
    )

    assert result.enough_data is True
    assert result.composite_score < Decimal("0")
    assert result.action in ("Trim", "Sell")


def test_insufficient_data_forces_watch(pg_session: Session) -> None:
    account_id, asset_id = _seed_account_and_asset(pg_session, symbol="THIN")
    # Only 30 bars — below equity price_bars_min (90)
    _seed_price_series(pg_session, asset_id, n=30)
    _buy(pg_session, account_id, asset_id, qty=5, price=100)

    cfg = load_engine_config()
    result = compute_for_asset(
        pg_session, account_id=account_id, asset_id=asset_id, config=cfg
    )

    assert result.enough_data is False
    assert result.action == "Watch"
    assert result.confidence == Decimal("0")
    assert "Insufficient data" in result.thesis


def test_persist_and_list_via_storage(pg_session: Session) -> None:
    account_id, asset_id = _seed_account_and_asset(pg_session)
    _seed_price_series(pg_session, asset_id, n=150)
    _buy(pg_session, account_id, asset_id, qty=10, price=100)

    results = run_for_account(pg_session, account_id)
    pg_session.commit()

    assert len(results) == 1
    r = results[0]
    assert r.recommendation_id is not None

    rec = pg_session.get(Recommendation, r.recommendation_id)
    assert rec is not None
    assert rec.action == r.action
    assert rec.model_version == r.engine_version

    evs = pg_session.scalars(
        select(RecommendationEvidence).where(
            RecommendationEvidence.recommendation_id == rec.id
        )
    ).all()
    # At least one per family that was computable
    assert len(evs) >= 3


def test_reproducible_same_inputs(pg_session: Session) -> None:
    account_id, asset_id = _seed_account_and_asset(pg_session)
    _seed_price_series(pg_session, asset_id, n=200)
    _buy(pg_session, account_id, asset_id, qty=10, price=100)

    cfg = load_engine_config()
    r1 = compute_for_asset(
        pg_session, account_id=account_id, asset_id=asset_id, config=cfg
    )
    r2 = compute_for_asset(
        pg_session, account_id=account_id, asset_id=asset_id, config=cfg
    )

    assert r1.snapshot_hash == r2.snapshot_hash
    assert r1.action == r2.action
    assert r1.composite_score == r2.composite_score
    assert r1.family_scores == r2.family_scores
