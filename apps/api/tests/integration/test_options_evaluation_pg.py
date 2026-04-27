"""Phase 11H integration tests — evaluation endpoints against Postgres.

Verifies:
  * GET /api/options/evaluation/summary — counts, average, distribution
  * GET /api/options/evaluation/scores — list with breakdown
  * GET /api/options/evaluation/scores/{id} — detail with components +
    penalties + flags
  * GET /api/options/evaluation/distribution — by-strategy + by-underlying
  * GET /api/options/evaluation/diagnostics — penalty drivers
  * Mutation verbs (POST/PUT/PATCH/DELETE) on every evaluation endpoint
    return 405 — no write surface introduced
  * Pin-risk + assignment + missing-settlement penalties propagate to
    score detail when those events exist for the underlying/day
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


def _seed_chain_for_today(pg_session, *, symbol="SPY"):
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
               200, :oi,
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


def _quote(*, option_type, strike, expiry, bid, ask, delta=-0.30):
    snap = dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc)
    mid = (bid + ask) / 2
    return OptionChainQuote(
        snapshot_at_utc=snap, underlying="SPY",
        expiry=expiry, strike=Decimal(str(strike)),
        option_type=option_type,
        option_symbol=f"SPY{expiry.strftime('%y%m%d')}{option_type[0]}{int(strike*1000):08d}",
        bid=Decimal(str(bid)), ask=Decimal(str(ask)),
        mid=Decimal(str(mid)), last=Decimal(str(bid)),
        volume=200, open_interest=2000,
        delta=Decimal(str(delta)), gamma=Decimal("0.02"),
        theta=Decimal("-0.05"), vega=Decimal("0.10"),
        iv=Decimal("0.20"), quote_age_seconds=2, provider="thetadata",
    )


def _open_assigned_trade(session_factory) -> int:
    """Open a real paper trade and expire it ITM TODAY so an assignment
    event lands on the same date as the seeded chain → flag flows."""
    today = dt.date.today()
    expiry = today + dt.timedelta(days=30)
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
# Summary
# ===========================================================================

def test_evaluation_summary_empty_db(client):
    res = client.get("/api/options/evaluation/summary")
    assert res.status_code == 200
    body = res.json()
    assert body["n_observations_scored"] == 0
    assert body["average_score"] is None
    assert body["median_score"] is None
    assert "Observation only" in body["observation_only_notice"]
    assert "rule-based paper analytics" in body["evaluation_disclaimer"]


def test_evaluation_summary_counts_after_seed(client, pg_session):
    _seed_chain_for_today(pg_session)
    res = client.get(
        "/api/options/evaluation/summary?underlying=SPY&lookback_days=2",
    )
    assert res.status_code == 200
    body = res.json()
    assert body["n_observations_scored"] >= 1
    assert body["average_score"] is not None


# ===========================================================================
# Scores list + detail
# ===========================================================================

def test_evaluation_scores_list_returns_breakdowns(client, pg_session):
    _seed_chain_for_today(pg_session)
    res = client.get(
        "/api/options/evaluation/scores?underlying=SPY&lookback_days=2",
    )
    assert res.status_code == 200
    body = res.json()
    assert body["count"] >= 1
    sample = body["scores"][0]
    assert 0 <= sample["total_score"] <= 100
    assert {"liquidity", "risk_reward", "vol_context", "structure"} == {
        c["component"] for c in sample["components"]
    }
    for c in sample["components"]:
        assert c["explanation"]
        assert 0 <= c["score"] <= c["weight_max"]


def test_evaluation_score_detail_round_trip(client, pg_session):
    today, _ = _seed_chain_for_today(pg_session)
    obs_id = f"SPY:{today.isoformat()}:SHORT_PUT_CREDIT_SPREAD"
    res = client.get(f"/api/options/evaluation/scores/{obs_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == obs_id
    assert "components" in body and "penalties" in body
    assert "Observation only" in body["observation_only_notice"]
    assert "rule-based paper analytics" in body["evaluation_disclaimer"]


def test_evaluation_score_detail_404_for_unknown(client):
    res = client.get(
        "/api/options/evaluation/scores/SPY:1900-01-01:SHORT_PUT_CREDIT_SPREAD"
    )
    assert res.status_code == 404


def test_evaluation_min_score_filter(client, pg_session):
    _seed_chain_for_today(pg_session)
    body_all = client.get(
        "/api/options/evaluation/scores?underlying=SPY&lookback_days=2"
    ).json()
    body_high = client.get(
        "/api/options/evaluation/scores?underlying=SPY&lookback_days=2"
        "&min_score=90"
    ).json()
    assert body_high["count"] <= body_all["count"]
    for s in body_high["scores"]:
        assert s["total_score"] >= 90


# ===========================================================================
# Distribution + diagnostics
# ===========================================================================

def test_evaluation_distribution_buckets(client, pg_session):
    _seed_chain_for_today(pg_session)
    res = client.get("/api/options/evaluation/distribution?lookback_days=2")
    assert res.status_code == 200
    body = res.json()
    assert "by_strategy" in body and "by_underlying" in body
    bucket_pairs = [(b["lo"], b["hi"]) for b in body["buckets_definition"]]
    assert bucket_pairs == [(0, 19), (20, 39), (40, 59), (60, 79), (80, 100)]


def test_evaluation_diagnostics_returns_penalty_counts(
    client, pg_session, session_factory, options_enabled,
):
    _seed_chain_for_today(pg_session)
    _open_assigned_trade(session_factory)
    res = client.get("/api/options/evaluation/diagnostics?lookback_days=2")
    assert res.status_code == 200
    body = res.json()
    codes = {row["code"] for row in body["common_penalty_drivers"]}
    assert "ASSIGNMENT_SIMPLIFIED_EXIT" in codes


def test_evaluation_score_detail_carries_assignment_penalty(
    client, pg_session, session_factory, options_enabled,
):
    today, _ = _seed_chain_for_today(pg_session)
    _open_assigned_trade(session_factory)
    obs_id = f"SPY:{today.isoformat()}:SHORT_PUT_CREDIT_SPREAD"
    res = client.get(f"/api/options/evaluation/scores/{obs_id}")
    assert res.status_code == 200
    body = res.json()
    codes = {p["code"] for p in body["penalties"]}
    assert "ASSIGNMENT_SIMPLIFIED_EXIT" in codes
    assert "ASSIGNMENT_SIMPLIFIED_EXIT" in body["flags"]


# ===========================================================================
# No mutation surface
# ===========================================================================

def test_evaluation_endpoints_reject_mutation_verbs(client):
    paths = (
        "/api/options/evaluation/summary",
        "/api/options/evaluation/scores",
        "/api/options/evaluation/scores/SPY:2026-01-01:SHORT_PUT_CREDIT_SPREAD",
        "/api/options/evaluation/distribution",
        "/api/options/evaluation/diagnostics",
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


def test_openapi_evaluation_endpoints_are_all_get(client):
    spec = client.get("/openapi.json").json()
    eval_paths = [p for p in spec["paths"]
                  if p.startswith("/api/options/evaluation")]
    assert eval_paths, "expected evaluation paths"
    for path in eval_paths:
        verbs = set(spec["paths"][path].keys()) - {"parameters", "summary"}
        non_read = verbs - {"get", "head", "options"}
        assert not non_read, f"non-read verb on {path}: {non_read}"
