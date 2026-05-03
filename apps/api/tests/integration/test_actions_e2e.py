"""Day-5 E2E: full /actions act flow — API → repo → submit_trade → verify."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    ActionItem,
    Asset,
    PaperPortfolio,
    PaperPosition,
    PaperTrade,
    PriceBar,
)

pytestmark = pytest.mark.integration


def _seed_all(session: Session, symbol: str = "NVDA") -> tuple[Asset, ActionItem]:
    today = dt.date.today()
    asset = Asset(
        id=str(uuid.uuid4()), symbol=symbol,
        asset_class="equity", sector="tech", exchange="NASDAQ",
    )
    session.add(asset)
    session.commit()

    portfolio = PaperPortfolio(
        id=str(uuid.uuid4()), name="E2E",
        starting_cash=Decimal("10000.00"),
        cash=Decimal("10000.00"),
        is_active=True,
        config_json='{"sizing_pct_of_equity": "0.10", "max_open_positions": 10}',
    )
    session.add(portfolio)
    ts = dt.datetime.combine(today + dt.timedelta(days=1), dt.time(20, 0), tzinfo=dt.timezone.utc)
    session.add(PriceBar(
        id=str(uuid.uuid4()), asset_id=asset.id, timeframe="1d", ts=ts,
        open=Decimal("100.00"), high=Decimal("100.00"),
        low=Decimal("100.00"), close=Decimal("100.00"),
        adjusted_close=Decimal("100.00"),
        volume=1_000_000, provider="test",
    ))
    session.commit()

    action = ActionItem(
        id=str(uuid.uuid4()),
        as_of_date=today, kind="BUY",
        asset_id=asset.id, symbol=asset.symbol, sector=asset.sector,
        candidate_id=None,
        priority=Decimal("82.00"), priority_tier="CRT",
        urgency="today", confidence=Decimal("75"),
        composite_score=Decimal("0.42"),
        rationale_short=f"BUY {symbol} e2e",
        factor_top=[{"key": "rm60", "contribution": 0.18, "value": 1.45}],
        impact_estimate={"position_delta_pct": 10.0, "portfolio_weight_after": 0.10},
        decay_at=None, dependencies={"conflicts_with": []},
        origin="engine", status="pending",
    )
    session.add(action)
    session.commit()
    return asset, action


def test_full_act_flow_creates_position_and_trade(pg_session: Session):
    """End-to-end: GET list → POST act → GET by id → verify position + trade."""
    from apps.api.src.main import app

    asset, action = _seed_all(pg_session, "NVDA")
    client = TestClient(app)

    # 1. List pending — action appears
    list_resp = client.get("/api/actions")
    assert list_resp.status_code == 200
    ids = [a["id"] for a in list_resp.json()["actions"]]
    assert action.id in ids

    # 2. Fetch single — matches list
    detail_before = client.get(f"/api/actions/{action.id}").json()
    assert detail_before["status"] == "pending"
    assert detail_before["factor_top"][0]["key"] == "rm60"

    # 3. Act
    act_resp = client.post(f"/api/actions/{action.id}/act")
    assert act_resp.status_code == 200, act_resp.text
    body = act_resp.json()
    assert body["action_id"] == action.id
    assert body["trade_id"]
    trade_id = body["trade_id"]

    # 4. Re-fetch action — shows acted + trade_id
    detail_after = client.get(f"/api/actions/{action.id}").json()
    assert detail_after["status"] == "acted"
    assert detail_after["acted_trade_id"] == trade_id
    assert detail_after["acted_at"] is not None

    # 5. Verify paper_trade row exists in DB
    pg_session.expire_all()
    trade = pg_session.get(PaperTrade, trade_id)
    assert trade is not None
    assert trade.side == "buy"
    assert trade.asset_id == asset.id
    assert float(trade.quantity) > 0

    # 6. Verify paper_position row exists
    pos = pg_session.query(PaperPosition).filter(
        PaperPosition.asset_id == asset.id,
        PaperPosition.is_open.is_(True),
    ).first()
    assert pos is not None
    assert float(pos.quantity) > 0

    # 7. List pending — acted action no longer present
    list_after = client.get("/api/actions").json()
    remaining = [a["id"] for a in list_after["actions"]]
    assert action.id not in remaining

    # 8. List with status=acted includes this one
    list_acted = client.get("/api/actions?status=acted").json()
    assert action.id in [a["id"] for a in list_acted["actions"]]


def test_act_then_dismiss_rejected(pg_session: Session):
    """Acting moves to acted; subsequent dismiss must 409 (not no-op silent)."""
    from apps.api.src.main import app

    asset, action = _seed_all(pg_session, "AMD")
    client = TestClient(app)

    act = client.post(f"/api/actions/{action.id}/act")
    assert act.status_code == 200

    dismiss = client.post(
        f"/api/actions/{action.id}/dismiss", json={"reason": "post_act"},
    )
    assert dismiss.status_code == 409


def test_dismiss_then_act_rejected(pg_session: Session):
    """Dismiss first; act must 409."""
    from apps.api.src.main import app

    asset, action = _seed_all(pg_session, "AVGO")
    client = TestClient(app)

    dis = client.post(f"/api/actions/{action.id}/dismiss", json={"reason": "first"})
    assert dis.status_code == 200

    act = client.post(f"/api/actions/{action.id}/act")
    assert act.status_code == 409
