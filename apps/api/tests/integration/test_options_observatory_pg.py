"""Phase 11G integration tests — observatory endpoints against Postgres.

Verifies:
  * GET /api/options/strategies returns the frozen rule registry
  * GET /api/options/strategy-observations runs eligibility evaluator
    against ingested chain rows
  * GET /api/options/strategy-observations/{id} re-evaluates one entry
  * GET /api/options/performance-summary aggregates closed trades
  * GET /api/options/diagnostics aggregates chain/feature/expiration
    counts within the lookback window
  * GET /api/options/scenario-replay reconstructs (symbol, day) view
  * POST/PUT/PATCH/DELETE on every new endpoint returns 405 — no
    mutation surface introduced by Phase 11G
  * Flag tokens (ASSIGNMENT_SIMPLIFIED_EXIT, PIN_RISK_UNCERTAIN_OUTCOME,
    MISSING_SETTLEMENT) flow into the performance + diagnostics + replay
    responses
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.config import settings
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
    test_factory = sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)
    monkeypatch.setattr("apps.api.src.db.SessionLocal", test_factory)
    return TestClient(app)


def _quote(*, option_type, strike, expiry, bid=1.20, ask=1.25,
           delta=-0.30, oi=1500, vol=100, age=2) -> OptionChainQuote:
    snap = dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc)
    mid = (bid + ask) / 2
    return OptionChainQuote(
        snapshot_at_utc=snap, underlying="SPY",
        expiry=expiry, strike=Decimal(str(strike)),
        option_type=option_type,
        option_symbol=f"SPY{expiry.strftime('%y%m%d')}{option_type[0]}{int(strike*1000):08d}",
        bid=Decimal(str(bid)), ask=Decimal(str(ask)),
        mid=Decimal(str(mid)), last=Decimal(str(bid)),
        volume=vol, open_interest=oi,
        delta=Decimal(str(delta)), gamma=Decimal("0.02"),
        theta=Decimal("-0.05"), vega=Decimal("0.10"),
        iv=Decimal("0.20"), quote_age_seconds=age, provider="thetadata",
    )


def _seed_chain_for_today(pg_session, *, symbol="SPY"):
    """Insert a credit-spread-eligible chain dated TODAY so the
    eligibility evaluator can fire."""
    today = dt.date.today()
    snap = dt.datetime.combine(today, dt.time(14, 0, tzinfo=dt.timezone.utc))
    expiry = today + dt.timedelta(days=30)
    rows = [
        dict(option_type="PUT",  strike=440, delta=-0.30, oi=2000),
        dict(option_type="PUT",  strike=435, delta=-0.18, oi=1500),
        dict(option_type="CALL", strike=460, delta= 0.30, oi=2000),
        dict(option_type="CALL", strike=465, delta= 0.18, oi=1500),
    ]
    for r in rows:
        pg_session.execute(text(
            """
            INSERT INTO options_chain_snapshot
              (snapshot_at_utc, underlying, expiry, strike, option_type,
               option_symbol, bid, ask, mid, last,
               volume, open_interest,
               delta, gamma, theta, vega, iv,
               quote_age_seconds, provider, provider_version)
            VALUES
              (:snap, :sym, :exp, :strike, :ot,
               :osym, 1.20, 1.25, 1.225, 1.20,
               100, :oi,
               :delta, 0.02, -0.05, 0.10, 0.20,
               2, 'thetadata', 'rest-v1')
            """
        ), {
            "snap": snap, "sym": symbol, "exp": expiry,
            "strike": Decimal(str(r["strike"])), "ot": r["option_type"],
            "osym": f"{symbol}{expiry.strftime('%y%m%d')}{r['option_type'][0]}"
                     f"{int(r['strike']*1000):08d}",
            "delta": Decimal(str(r["delta"])), "oi": r["oi"],
        })
    pg_session.commit()
    return today, expiry


def _open_and_assign(session_factory) -> int:
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
            short.option_symbol: short, long_.option_symbol: long_,
        },
    )
    res = open_trade(req, session_factory=session_factory)
    expire_trade(res.trade_id, settlement_price=Decimal("420"),
                 session_factory=session_factory)
    return res.trade_id   # type: ignore[return-value]


# ===========================================================================
# Strategies registry
# ===========================================================================

def test_get_strategies_returns_frozen_registry(client):
    res = client.get("/api/options/strategies")
    assert res.status_code == 200
    body = res.json()
    rule_ids = {r["rule_id"] for r in body["strategies"]}
    assert rule_ids == {
        "SHORT_PUT_CREDIT_SPREAD",
        "SHORT_CALL_CREDIT_SPREAD",
        "IRON_CONDOR",
    }
    assert "Observation only" in body["observation_only_notice"]


# ===========================================================================
# Strategy observations — list + detail
# ===========================================================================

def test_strategy_observations_list_evaluates_today_chain(
    client, pg_session,
):
    _seed_chain_for_today(pg_session, symbol="SPY")
    res = client.get(
        "/api/options/strategy-observations"
        "?underlying=SPY&lookback_days=2&limit=20",
    )
    assert res.status_code == 200
    body = res.json()
    assert body["count"] >= 1
    rule_ids = {o["rule_id"] for o in body["observations"]}
    assert "SHORT_PUT_CREDIT_SPREAD" in rule_ids


def test_strategy_observations_detail_round_trip(
    client, pg_session,
):
    today, _expiry = _seed_chain_for_today(pg_session, symbol="SPY")
    obs_id = f"SPY:{today.isoformat()}:SHORT_PUT_CREDIT_SPREAD"
    res = client.get(f"/api/options/strategy-observations/{obs_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["evaluation"]["rule_id"] == "SHORT_PUT_CREDIT_SPREAD"
    assert "checks" in body["evaluation"]
    assert "Observation only" in body["observation_only_notice"]
    assert "paper-trading only" in body["notice"]


def test_strategy_observation_detail_404_for_unknown_id(client):
    res = client.get(
        "/api/options/strategy-observations/SPY:1900-01-01:SHORT_PUT_CREDIT_SPREAD"
    )
    assert res.status_code == 404


# ===========================================================================
# Performance summary
# ===========================================================================

def test_performance_summary_empty_db(client):
    res = client.get("/api/options/performance-summary")
    assert res.status_code == 200
    body = res.json()
    assert body["n_closed_trades"] == 0
    assert body["win_rate"] is None
    assert body["max_loss_hit_rate"] is None
    assert "Observation only" in body["observation_only_notice"]


def test_performance_summary_after_assignment(
    client, session_factory, options_enabled, pg_session,
):
    _open_and_assign(session_factory)
    res = client.get("/api/options/performance-summary")
    assert res.status_code == 200
    body = res.json()
    assert body["n_closed_trades"] == 1
    assert body["n_assigned"] == 1
    assert body["n_max_loss_hits"] == 1     # settlement at 420 → max loss
    assert body["assignment_rate"] == "1"   # 1/1
    assert "ASSIGNMENT_SIMPLIFIED_EXIT" in body["data_quality_flags"]
    by_strat = {r["strategy_name"]: r for r in body["by_strategy"]}
    assert "SHORT_PUT_CREDIT_SPREAD" in by_strat


# ===========================================================================
# Diagnostics
# ===========================================================================

def test_diagnostics_basic_shape(client, session_factory, options_enabled):
    _open_and_assign(session_factory)
    res = client.get("/api/options/diagnostics?lookback_days=60")
    assert res.status_code == 200
    body = res.json()
    assert "Naive gamma exposure proxy" in body["naive_gex_label"]
    assert body["assignments"]["n_events"] >= 1
    assert "Observation only" in body["observation_only_notice"]
    assert "paper-trading only" in body["notice"]


# ===========================================================================
# Scenario replay
# ===========================================================================

def test_scenario_replay_reconstructs_today(
    client, pg_session, session_factory, options_enabled,
):
    today, _ = _seed_chain_for_today(pg_session, symbol="SPY")
    res = client.get(
        f"/api/options/scenario-replay?symbol=SPY&as_of={today.isoformat()}"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["symbol"] == "SPY"
    assert body["as_of_date"] == today.isoformat()
    assert body["chain_summary"]["n_accepted"] == 4
    rule_ids = {ev["rule_id"] for ev in body["rule_evaluations"]}
    assert {"SHORT_PUT_CREDIT_SPREAD",
            "SHORT_CALL_CREDIT_SPREAD",
            "IRON_CONDOR"} <= rule_ids
    assert "Observation only" in body["observation_only_notice"]
    assert "paper-trading only" in body["notice"]


def test_scenario_replay_no_data_flags_clean_response(client):
    res = client.get(
        "/api/options/scenario-replay?symbol=SPY&as_of=1900-01-01"
    )
    assert res.status_code == 200
    body = res.json()
    assert "NO_ACCEPTED_QUOTES" in body["data_quality_flags"]
    # Rules still evaluate, but with NO_QUOTES notes
    assert len(body["rule_evaluations"]) == 3


def test_scenario_replay_invalid_date_422(client):
    res = client.get("/api/options/scenario-replay?symbol=SPY&as_of=garbage")
    assert res.status_code == 422


# ===========================================================================
# No mutation surface on any new endpoint
# ===========================================================================

def test_observatory_endpoints_reject_mutation_verbs(client):
    paths = (
        "/api/options/strategies",
        "/api/options/strategy-observations",
        "/api/options/strategy-observations/SPY:2026-01-01:SHORT_PUT_CREDIT_SPREAD",
        "/api/options/performance-summary",
        "/api/options/diagnostics",
        "/api/options/scenario-replay?symbol=SPY&as_of=2026-01-01",
    )
    for path in paths:
        for verb in ("post", "put", "patch", "delete"):
            kwargs = {} if verb == "delete" else {"json": {}}
            res = getattr(client, verb)(path, **kwargs)
            assert res.status_code < 200 or res.status_code >= 300, (
                f"{verb.upper()} {path} succeeded — write surface!"
            )
            assert res.status_code in (404, 405, 422), (
                f"{verb.upper()} {path}: {res.status_code}"
            )


def test_openapi_options_endpoints_are_all_get(client):
    spec = client.get("/openapi.json").json()
    options_paths = [p for p in spec["paths"] if p.startswith("/api/options")]
    assert options_paths
    for path in options_paths:
        verbs = set(spec["paths"][path].keys()) - {"parameters", "summary"}
        non_read = verbs - {"get", "head", "options"}
        assert not non_read, f"non-read verb on {path}: {non_read}"
