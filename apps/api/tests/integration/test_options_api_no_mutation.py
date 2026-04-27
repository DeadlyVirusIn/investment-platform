"""Phase 11F integration tests — options read-only API end-to-end.

Verifies:
  * GET endpoints return well-shaped JSON
  * POST/PUT/PATCH/DELETE on /api/options/* return 405 Method Not Allowed
  * Flags (ASSIGNMENT_SIMPLIFIED_EXIT, PIN_RISK_UNCERTAIN_OUTCOME,
    MISSING_SETTLEMENT) flow from engine → DB → API response
  * Trade detail aggregates lifecycle/expiration/assignment flags
  * Risk summary includes flags + naive-Greeks-proxy label
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.db.options_models import (  # noqa: F401 — register on Base
    OptionsAssignmentEvent,
    OptionsChainSnapshot,
    OptionsExpirationEvent,
    OptionsFeatureDaily,
    OptionsPaperTrade,
    OptionsPaperTradeLeg,
    OptionsTradeLifecycleEvent,
)
from apps.api.src.main import app
from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.paper.engine import (
    TradeRequest,
    expire_trade,
    open_trade,
)
from apps.api.src.options.paper.strategies import (
    LegSpec,
    STRATEGY_SHORT_PUT_CREDIT_SPREAD,
)


pytestmark = pytest.mark.integration


@pytest.fixture
def session_factory(pg_engine):
    return sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)


@pytest.fixture
def options_enabled(monkeypatch):
    monkeypatch.setattr(settings, "OPTIONS_ENABLED", True)
    monkeypatch.setattr(settings, "OPTIONS_PAPER_ONLY", True)


@pytest.fixture
def client(pg_engine, monkeypatch):
    """TestClient that routes ALL ORM/raw queries via the test engine.
    We override SessionLocal so DB-bound deps in the app see the
    testcontainer engine, not the production-config engine.
    """
    test_factory = sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)
    monkeypatch.setattr(
        "apps.api.src.db.SessionLocal", test_factory,
    )
    # get_session in apps.api.src.db reads SessionLocal at call-time
    return TestClient(app)


def _quote(*, option_type, strike, expiry, bid, ask,
           delta=-0.20, oi=1000, age=2) -> OptionChainQuote:
    snap = dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc)
    mid = (bid + ask) / 2
    return OptionChainQuote(
        snapshot_at_utc=snap, underlying="SPY",
        expiry=expiry, strike=Decimal(str(strike)),
        option_type=option_type,
        option_symbol=f"SPY{expiry.strftime('%y%m%d')}{option_type[0]}{int(strike*1000):08d}",
        bid=Decimal(str(bid)), ask=Decimal(str(ask)),
        mid=Decimal(str(mid)), last=Decimal(str(bid)),
        volume=100, open_interest=oi,
        delta=Decimal(str(delta)), gamma=Decimal("0.02"),
        theta=Decimal("-0.05"), vega=Decimal("0.10"),
        iv=Decimal("0.20"), quote_age_seconds=age, provider="thetadata",
    )


def _open_a_spread(session_factory) -> int:
    expiry = dt.date(2026, 6, 18)
    short = _quote(option_type="PUT", strike=440, expiry=expiry,
                   bid=1.20, ask=1.25, delta=-0.30)
    long_ = _quote(option_type="PUT", strike=435, expiry=expiry,
                   bid=0.50, ask=0.55, delta=-0.18)
    req = TradeRequest(
        underlying="SPY",
        strategy_name=STRATEGY_SHORT_PUT_CREDIT_SPREAD,
        strategy_version="v1.0",
        legs=(
            LegSpec(side="SELL", option_type="PUT",
                    strike=Decimal("440"), expiry=expiry, qty=1,
                    option_symbol=short.option_symbol),
            LegSpec(side="BUY",  option_type="PUT",
                    strike=Decimal("435"), expiry=expiry, qty=1,
                    option_symbol=long_.option_symbol),
        ),
        quotes_by_symbol={
            short.option_symbol: short,
            long_.option_symbol:  long_,
        },
    )
    res = open_trade(req, session_factory=session_factory)
    assert res.accepted is True
    return res.trade_id   # type: ignore[return-value]


# ===========================================================================
# Mutation-method enumeration — every options route is GET
# ===========================================================================

def test_options_routes_are_all_get(client):
    """Walk OpenAPI; ensure no /api/options/* path supports a write verb."""
    spec = client.get("/openapi.json").json()
    options_paths = [p for p in spec["paths"] if p.startswith("/api/options")]
    assert options_paths, "expected at least one /api/options/* path"
    for path in options_paths:
        verbs = set(spec["paths"][path].keys()) - {"parameters", "summary"}
        non_read = verbs - {"get", "head", "options"}
        assert not non_read, f"non-read verb on {path}: {non_read}"


def test_post_to_options_returns_405(client):
    for path in (
        "/api/options/symbols",
        "/api/options/chain",
        "/api/options/features",
        "/api/options/paper-trades",
        "/api/options/paper-trades/1",
        "/api/options/risk-summary",
    ):
        for verb in ("post", "put", "patch", "delete"):
            kwargs = {} if verb == "delete" else {"json": {}}
            res = getattr(client, verb)(path, **kwargs)
            # Critical: NEVER 2xx for a write verb
            assert res.status_code < 200 or res.status_code >= 300, (
                f"{verb.upper()} {path} succeeded (2xx) — write surface exists!"
            )
            assert res.status_code in (404, 405, 422), (
                f"{verb.upper()} {path} returned {res.status_code} "
                f"(expected 404/405/422)"
            )


# ===========================================================================
# Health + symbols
# ===========================================================================

def test_options_health_paper_only(client):
    res = client.get("/api/options/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["paper_only"] is True
    assert body["ml_can_affect_trades"] is False
    assert "paper-trading only" in body["notice"].lower()


def test_options_symbols_returns_default_universe_when_empty(client):
    res = client.get("/api/options/symbols")
    assert res.status_code == 200
    body = res.json()
    assert "SPY" in body["symbols"]
    assert body["notice"]


# ===========================================================================
# Flag passthrough — ASSIGNED + ASSIGNMENT_SIMPLIFIED_EXIT
# ===========================================================================

def test_assignment_flag_flows_to_api(
    client, session_factory, options_enabled,
):
    trade_id = _open_a_spread(session_factory)
    expire_trade(
        trade_id, settlement_price=Decimal("420"),
        session_factory=session_factory,
    )
    detail = client.get(f"/api/options/paper-trades/{trade_id}").json()
    assert detail["status"] == "ASSIGNED"
    assert "ASSIGNMENT_SIMPLIFIED_EXIT" in detail["data_quality_flags"]
    # Lifecycle terminal event carries the flag in payload
    terminal_events = [
        e for e in detail["lifecycle_events"]
        if e["event_type"] in ("ASSIGNED", "EXPIRED")
    ]
    assert any(
        "ASSIGNMENT_SIMPLIFIED_EXIT" in (e["payload"].get("flags") or [])
        for e in terminal_events
    )
    # Assignment-event notes carry the explicit token too
    assert any(
        "ASSIGNMENT_SIMPLIFIED_EXIT" in (a["notes"] or "")
        for a in detail["assignment_events"]
    )


def test_pin_risk_flag_flows_to_api(
    client, session_factory, options_enabled,
):
    trade_id = _open_a_spread(session_factory)
    expire_trade(
        trade_id, settlement_price=Decimal("440.02"),
        session_factory=session_factory,
    )
    detail = client.get(f"/api/options/paper-trades/{trade_id}").json()
    assert "PIN_RISK_UNCERTAIN_OUTCOME" in detail["data_quality_flags"]


def test_missing_settlement_flag_flows_to_api(
    client, session_factory, options_enabled,
):
    trade_id = _open_a_spread(session_factory)
    expire_trade(
        trade_id, settlement_price=None,
        session_factory=session_factory,
    )
    detail = client.get(f"/api/options/paper-trades/{trade_id}").json()
    assert "MISSING_SETTLEMENT" in detail["data_quality_flags"]


# ===========================================================================
# Risk summary — flags + naive-Greeks-proxy label
# ===========================================================================

def test_risk_summary_carries_flags_and_label(
    client, session_factory, options_enabled,
):
    trade_id = _open_a_spread(session_factory)
    expire_trade(
        trade_id, settlement_price=Decimal("420"),
        session_factory=session_factory,
    )
    summary = client.get("/api/options/risk-summary").json()
    assert "ASSIGNMENT_SIMPLIFIED_EXIT" in summary["data_quality_flags"]
    assert "Naive entry-time Greeks proxy" in summary["greeks_source_label"]
    assert summary["notice"]


# ===========================================================================
# Features endpoint — gamma exposure label included even when null
# ===========================================================================

def test_features_endpoint_includes_naive_gex_label(client):
    res = client.get("/api/options/features?symbol=SPY")
    assert res.status_code == 200
    body = res.json()
    assert "Naive gamma exposure proxy" in body["gamma_exposure_label"]


# ===========================================================================
# Trade-list filter pass-through
# ===========================================================================

def test_paper_trades_filter_by_status(
    client, session_factory, options_enabled,
):
    trade_id = _open_a_spread(session_factory)
    body = client.get("/api/options/paper-trades?status=open").json()
    assert body["count"] >= 1
    assert any(t["id"] == trade_id for t in body["trades"])
    # close it via expire and re-filter
    expire_trade(
        trade_id, settlement_price=Decimal("450"),
        session_factory=session_factory,
    )
    body_open = client.get("/api/options/paper-trades?status=open").json()
    assert all(t["id"] != trade_id for t in body_open["trades"])
    body_expired = client.get("/api/options/paper-trades?status=expired").json()
    assert any(t["id"] == trade_id for t in body_expired["trades"])
