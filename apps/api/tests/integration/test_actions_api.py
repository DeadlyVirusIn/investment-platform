"""Integration tests for /actions router — full contract coverage."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    ActionItem,
    Asset,
    PaperPortfolio,
    PaperTrade,
    PriceBar,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_asset(session: Session, symbol: str, sector: str = "tech") -> Asset:
    asset = Asset(
        id=str(uuid.uuid4()), symbol=symbol,
        asset_class="equity", sector=sector, exchange="NASDAQ",
    )
    session.add(asset)
    session.commit()
    return asset


def _seed_portfolio(session: Session) -> PaperPortfolio:
    pf = PaperPortfolio(
        id=str(uuid.uuid4()), name="TestPaper",
        starting_cash=Decimal("10000.00"),
        cash=Decimal("10000.00"),
        is_active=True,
        config_json='{"sizing_pct_of_equity": "0.10", "max_open_positions": 10}',
    )
    session.add(pf)
    session.commit()
    return pf


def _seed_price(
    session: Session, asset_id: str, as_of: dt.date, close: Decimal,
) -> None:
    ts = dt.datetime.combine(as_of, dt.time(20, 0), tzinfo=dt.timezone.utc)
    session.add(PriceBar(
        id=str(uuid.uuid4()), asset_id=asset_id, timeframe="1d", ts=ts,
        open=close, high=close, low=close, close=close, adjusted_close=close,
        volume=1_000_000, provider="test",
    ))
    session.commit()


def _seed_action(
    session: Session, *, asset: Asset, kind: str = "BUY",
    priority: Decimal = Decimal("82.00"), status: str = "pending",
    as_of: dt.date | None = None,
) -> ActionItem:
    as_of = as_of or dt.date.today()
    a = ActionItem(
        id=str(uuid.uuid4()),
        as_of_date=as_of, kind=kind,
        asset_id=asset.id, symbol=asset.symbol, sector=asset.sector,
        candidate_id=None,
        priority=priority, priority_tier="CRT" if priority >= 75 else "HIGH",
        urgency="today", confidence=Decimal("75"),
        composite_score=Decimal("0.42"),
        rationale_short=f"{kind} {asset.symbol} test",
        factor_top=[],
        impact_estimate={"position_delta_pct": 10.0},
        decay_at=None,
        dependencies={"conflicts_with": []},
        origin="engine",
        status=status,
    )
    session.add(a)
    session.commit()
    return a


def _client():
    from fastapi.testclient import TestClient
    from apps.api.src.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /actions
# ---------------------------------------------------------------------------


def test_list_pending_returns_only_pending_sorted_desc(pg_session: Session):
    a1 = _seed_asset(pg_session, "AAPL")
    a2 = _seed_asset(pg_session, "MSFT")
    a3 = _seed_asset(pg_session, "NVDA")
    _seed_action(pg_session, asset=a1, kind="BUY", priority=Decimal("55.00"))
    _seed_action(pg_session, asset=a2, kind="BUY", priority=Decimal("82.00"))
    _seed_action(pg_session, asset=a3, kind="BUY", priority=Decimal("40.00"), status="dismissed")

    r = _client().get("/api/actions")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "pending"
    assert data["count"] == 2
    symbols = [a["symbol"] for a in data["actions"]]
    assert symbols == ["MSFT", "AAPL"]   # priority desc


def test_list_filters_by_status(pg_session: Session):
    a1 = _seed_asset(pg_session, "TSLA")
    a2 = _seed_asset(pg_session, "GOOG")
    _seed_action(pg_session, asset=a1, status="acted")
    _seed_action(pg_session, asset=a2, status="dismissed")

    r = _client().get("/api/actions?status=acted")
    assert r.status_code == 200
    assert r.json()["count"] == 1
    assert r.json()["actions"][0]["symbol"] == "TSLA"


def test_list_bogus_status_returns_400(pg_session: Session):
    r = _client().get("/api/actions?status=bogus")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /actions/{id}
# ---------------------------------------------------------------------------


def test_get_by_id_reflects_status_after_transition(pg_session: Session):
    asset = _seed_asset(pg_session, "AMD")
    a = _seed_action(pg_session, asset=asset)
    r1 = _client().get(f"/api/actions/{a.id}")
    assert r1.status_code == 200
    assert r1.json()["status"] == "pending"

    # manually dismiss
    pg_session.get(ActionItem, a.id).status = "dismissed"
    pg_session.get(ActionItem, a.id).dismiss_reason = "manual"
    pg_session.commit()

    r2 = _client().get(f"/api/actions/{a.id}")
    assert r2.status_code == 200
    assert r2.json()["status"] == "dismissed"
    assert r2.json()["dismiss_reason"] == "manual"


def test_get_unknown_id_returns_404(pg_session: Session):
    r = _client().get(f"/api/actions/{uuid.uuid4()}")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /actions/{id}/act
# ---------------------------------------------------------------------------


def test_act_on_buy_creates_exactly_one_trade(pg_session: Session):
    today = dt.date.today()
    asset = _seed_asset(pg_session, "INTC")
    _seed_portfolio(pg_session)
    # Need a forward-dated price bar because submit_trade calls find_next_open
    _seed_price(pg_session, asset.id, today + dt.timedelta(days=1), Decimal("50.00"))
    action = _seed_action(pg_session, asset=asset, kind="BUY", as_of=today)

    trades_before = pg_session.query(PaperTrade).count()
    r = _client().post(f"/api/actions/{action.id}/act")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["action_id"] == action.id
    assert body["trade_id"]

    trades_after = pg_session.query(PaperTrade).count()
    assert trades_after - trades_before == 1

    pg_session.expire_all()
    post = pg_session.get(ActionItem, action.id)
    assert post.status == "acted"
    assert post.acted_trade_id == body["trade_id"]
    assert post.acted_at is not None


def test_act_twice_second_returns_409(pg_session: Session):
    today = dt.date.today()
    asset = _seed_asset(pg_session, "CSCO")
    _seed_portfolio(pg_session)
    _seed_price(pg_session, asset.id, today + dt.timedelta(days=1), Decimal("55.00"))
    action = _seed_action(pg_session, asset=asset, kind="BUY", as_of=today)

    client = _client()
    r1 = client.post(f"/api/actions/{action.id}/act")
    assert r1.status_code == 200
    r2 = client.post(f"/api/actions/{action.id}/act")
    assert r2.status_code == 409
    assert "acted" in r2.json()["detail"].lower()


def test_act_unknown_returns_404(pg_session: Session):
    r = _client().post(f"/api/actions/{uuid.uuid4()}/act")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /actions/{id}/dismiss
# ---------------------------------------------------------------------------


def test_dismiss_pending_ok(pg_session: Session):
    asset = _seed_asset(pg_session, "QCOM")
    action = _seed_action(pg_session, asset=asset)
    r = _client().post(
        f"/api/actions/{action.id}/dismiss",
        json={"reason": "user_test"},
    )
    assert r.status_code == 200
    pg_session.expire_all()
    post = pg_session.get(ActionItem, action.id)
    assert post.status == "dismissed"
    assert post.dismiss_reason == "user_test"


def test_dismiss_already_acted_returns_409(pg_session: Session):
    asset = _seed_asset(pg_session, "TXN")
    a = _seed_action(pg_session, asset=asset, status="acted")
    r = _client().post(
        f"/api/actions/{a.id}/dismiss", json={"reason": "late_dismiss"},
    )
    assert r.status_code == 409
    assert "dismissable" in r.json()["detail"] or "acted" in r.json()["detail"]


def test_dismiss_already_dismissed_returns_409(pg_session: Session):
    asset = _seed_asset(pg_session, "AVGO")
    a = _seed_action(pg_session, asset=asset, status="dismissed")
    r = _client().post(f"/api/actions/{a.id}/dismiss", json={})
    assert r.status_code == 409


def test_dismiss_unknown_returns_404(pg_session: Session):
    r = _client().post(f"/api/actions/{uuid.uuid4()}/dismiss", json={})
    assert r.status_code == 404
