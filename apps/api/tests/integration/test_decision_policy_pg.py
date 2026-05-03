"""Integration: decision policy stored in rationale + surfaced via API."""

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
    RecommendationOutcome,
)
from apps.api.src.domain.ledger.account_service import AccountCreate, create_account
from apps.api.src.domain.ledger.transaction_service import (
    TransactionCreate,
    create_transaction,
)
from apps.api.src.domain.recommendations.decision_policy import (
    PolicyContext,
    build_policy_context_from_db,
)
from apps.api.src.domain.recommendations.recommendation_engine import (
    load_engine_config,
    run_for_account,
)

pytestmark = pytest.mark.integration


def _seed_asset_with_uptrend_prices(
    pg_session: Session,
    symbol: str,
    n_bars: int = 160,
    step: Decimal = Decimal("0.5"),
) -> str:
    asset = Asset(symbol=symbol, asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    base = Decimal("100")
    for i in range(n_bars):
        price = base + step * Decimal(i)
        pg_session.add(PriceBar(
            asset_id=asset.id, timeframe="1d",
            ts=now - dt.timedelta(days=n_bars - 1 - i),
            open=price, high=price + Decimal("0.5"), low=price - Decimal("0.5"),
            close=price, adjusted_close=price, volume=1_000_000, provider="test",
        ))
    pg_session.commit()
    return asset.id


def test_run_for_account_applies_policy_when_context_suppresses(pg_session: Session) -> None:
    acct = create_account(pg_session, AccountCreate(name="Policy", kind="broker"))
    asset_id = _seed_asset_with_uptrend_prices(pg_session, "POL")
    create_transaction(pg_session, TransactionCreate(
        account_id=acct.id, asset_id=asset_id,
        ts=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=150),
        action="buy", quantity=Decimal("1"), price=Decimal("100"),
    ))
    pg_session.commit()

    # Explicit context that aggressively suppresses uptrend + caps confidence.
    ctx = PolicyContext(
        enabled=True,
        suppress_regimes=frozenset({("trend", "uptrend")}),
        confidence_inversion=True,
        suppressed_regime_factor=Decimal("0.5"),
        confidence_inversion_cap=Decimal("30"),
    )
    results = run_for_account(pg_session, acct.id, policy_context=ctx)
    pg_session.commit()

    assert len(results) == 1
    rec_id = results[0].recommendation_id
    rec = pg_session.get(Recommendation, rec_id)
    import json
    rationale = json.loads(rec.rationale)
    assert "policy" in rationale
    p = rationale["policy"]
    assert p["original_action"] in ("Buy", "Hold")
    # At least one adjustment must have been applied (suppression or cap)
    assert len(p["adjustments"]) >= 1


def test_run_for_account_policy_disabled_no_policy_block(pg_session: Session) -> None:
    acct = create_account(pg_session, AccountCreate(name="Off", kind="broker"))
    asset_id = _seed_asset_with_uptrend_prices(pg_session, "OFF")
    create_transaction(pg_session, TransactionCreate(
        account_id=acct.id, asset_id=asset_id,
        ts=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=150),
        action="buy", quantity=Decimal("1"), price=Decimal("100"),
    ))
    pg_session.commit()

    ctx = PolicyContext(enabled=False)
    results = run_for_account(pg_session, acct.id, policy_context=ctx)
    pg_session.commit()

    rec = pg_session.get(Recommendation, results[0].recommendation_id)
    import json
    rationale = json.loads(rec.rationale)
    # Disabled policy → no policy block stored (passthrough has no adjustments)
    assert "policy" not in rationale


def test_api_exposes_policy_fields(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    # Manually seed a recommendation row with a policy block to test API serialization
    import json
    asset = Asset(symbol="APIPOL", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    rec = Recommendation(
        asset_id=asset.id, action="Buy", conviction=Decimal("80"),
        model_version="0.1.0", snapshot_hash="policy-snap",
        rationale=json.dumps({
            "thesis": "test",
            "snapshot_hash": "policy-snap",
            "policy": {
                "original_action": "Buy",
                "original_composite_score": "0.40",
                "original_confidence": "80",
                "adjusted_action": "Hold",
                "adjusted_composite_score": "0.20",
                "adjusted_confidence": "50",
                "adjustments": [
                    {"rule": "high_volatility_damping", "factor": "0.5",
                     "reason": "test"},
                ],
            },
        }),
    )
    pg_session.add(rec)
    pg_session.commit()

    client = TestClient(app)
    resp = client.get("/api/recommendations")
    assert resp.status_code == 200
    data = resp.json()
    matching = [r for r in data["recommendations"] if r["id"] == rec.id]
    assert len(matching) == 1
    r = matching[0]
    assert r["action"] == "Buy"  # original unchanged
    assert r["adjusted_action"] == "Hold"
    assert r["adjusted_confidence"] == "50"
    assert r["policy"] is not None
    assert len(r["policy_adjustments"]) == 1


def test_build_policy_context_from_empty_db(pg_session: Session) -> None:
    ctx = build_policy_context_from_db(pg_session, enabled=True)
    assert ctx.enabled is True
    assert ctx.suppress_regimes == frozenset()
    assert ctx.confidence_inversion is False


def test_build_policy_context_disabled_passthrough(pg_session: Session) -> None:
    ctx = build_policy_context_from_db(pg_session, enabled=False)
    assert ctx.enabled is False
