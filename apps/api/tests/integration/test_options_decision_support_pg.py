"""Phase 11I integration tests — decision support endpoints.

Verifies:
  * GET /api/options/decision-support/summary — bucket counts
  * GET /api/options/decision-support/review-queue — ranked rows with
    bucket label, ranking explanation, tie-breakers
  * GET /api/options/decision-support/review-queue/{id} — detail with
    breakdown + flags + penalties + ranking explanation
  * GET /api/options/decision-support/buckets — grouped view
  * GET /api/options/decision-support/diagnostics — exclusion drivers
  * exclude_severe_flags filter removes severe-flagged rows
  * Mutation verbs reject (405); no write surface
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

def test_summary_empty_db(client):
    res = client.get("/api/options/decision-support/summary")
    assert res.status_code == 200
    body = res.json()
    assert body["n_total"] == 0
    assert "Review queues are for human inspection only" in body["decision_support_disclaimer"]
    assert body["tie_breakers"] == [
        "evaluation_score DESC",
        "severe_flag_count ASC",
        "liquidity_component_score DESC",
        "as_of_date DESC",
        "observation_id ASC",
    ]


def test_summary_buckets_after_seed(client, pg_session):
    _seed_chain_for_today(pg_session)
    res = client.get(
        "/api/options/decision-support/summary?lookback_days=2",
    )
    assert res.status_code == 200
    body = res.json()
    assert body["n_total"] >= 1
    bucket_tokens = {row["bucket"] for row in body["by_bucket"]}
    assert "HIGH_REVIEW_PRIORITY" in bucket_tokens or \
        "NEUTRAL_NEEDS_REVIEW" in bucket_tokens or \
        "EXCLUDED_BY_REVIEW_RULES" in bucket_tokens


# ===========================================================================
# Review queue list + detail
# ===========================================================================

def test_review_queue_returns_ranked_rows(client, pg_session):
    _seed_chain_for_today(pg_session)
    res = client.get(
        "/api/options/decision-support/review-queue?lookback_days=2"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["count"] >= 1
    rq = body["review_queue"]
    # Each row must have rank_position + ranking_explanation + tie_breakers
    for r in rq:
        assert "rank_position" in r
        assert "ranking_explanation" in r
        assert "tie_breakers" in r
        assert "bucket" in r and "bucket_label" in r
        assert "inclusion_reason" in r


def test_review_queue_ordering_is_score_desc(client, pg_session):
    _seed_chain_for_today(pg_session)
    body = client.get(
        "/api/options/decision-support/review-queue?lookback_days=2"
    ).json()
    rq = body["review_queue"]
    if len(rq) >= 2:
        scores = [r["total_score"] for r in rq]
        assert scores == sorted(scores, reverse=True)


def test_review_queue_detail_round_trip(client, pg_session):
    today, _ = _seed_chain_for_today(pg_session)
    obs_id = f"SPY:{today.isoformat()}:SHORT_PUT_CREDIT_SPREAD"
    res = client.get(f"/api/options/decision-support/review-queue/{obs_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == obs_id
    # Score breakdown carried through
    assert "components" in body and "penalties" in body
    # Decision-support specific fields
    assert "ranking_explanation" in body
    assert "tie_breakers" in body
    assert "bucket" in body and "bucket_label" in body
    assert "inclusion_reason" in body
    assert "Human review required" in body["human_review_note"]


def test_review_queue_detail_404_for_unknown(client):
    res = client.get(
        "/api/options/decision-support/review-queue/SPY:1900-01-01:SHORT_PUT_CREDIT_SPREAD"
    )
    assert res.status_code == 404


# ===========================================================================
# Severe-flag filter
# ===========================================================================

def test_exclude_severe_flags_removes_severe_rows(
    client, pg_session, session_factory, options_enabled,
):
    _seed_chain_for_today(pg_session)
    _open_assigned_trade(session_factory)
    # Without filter: row has ASSIGNMENT_SIMPLIFIED_EXIT in flags
    body_all = client.get(
        "/api/options/decision-support/review-queue?lookback_days=2"
    ).json()
    has_severe = any(
        "ASSIGNMENT_SIMPLIFIED_EXIT" in (r.get("flags") or [])
        for r in body_all["review_queue"]
    )
    assert has_severe

    # With filter: severe-flagged row dropped
    body_filtered = client.get(
        "/api/options/decision-support/review-queue?lookback_days=2"
        "&exclude_severe_flags=true"
    ).json()
    for r in body_filtered["review_queue"]:
        assert "ASSIGNMENT_SIMPLIFIED_EXIT" not in (r.get("flags") or [])


def test_min_score_filter(client, pg_session):
    _seed_chain_for_today(pg_session)
    body_all = client.get(
        "/api/options/decision-support/review-queue?lookback_days=2"
    ).json()
    body_high = client.get(
        "/api/options/decision-support/review-queue?lookback_days=2&min_score=80"
    ).json()
    assert body_high["count"] <= body_all["count"]
    for r in body_high["review_queue"]:
        assert r["total_score"] >= 80


# ===========================================================================
# Buckets endpoint
# ===========================================================================

def test_buckets_returns_grouped_rows(client, pg_session):
    _seed_chain_for_today(pg_session)
    res = client.get("/api/options/decision-support/buckets?lookback_days=2")
    assert res.status_code == 200
    body = res.json()
    bucket_tokens = [g["bucket"] for g in body["groups"]]
    assert bucket_tokens == [
        "HIGH_REVIEW_PRIORITY",
        "NEEDS_REVIEW_DATA_QUALITY",
        "NEEDS_REVIEW_MODEL_LIMITATION",
        "NEUTRAL_NEEDS_REVIEW",
        "EXCLUDED_BY_REVIEW_RULES",
    ]
    for g in body["groups"]:
        assert g["count"] == len(g["rows"])
        for row in g["rows"]:
            assert "rank_position" in row
            assert "ranking_explanation" in row


# ===========================================================================
# Diagnostics
# ===========================================================================

def test_diagnostics_returns_exclusion_drivers(client, pg_session):
    _seed_chain_for_today(pg_session)
    res = client.get(
        "/api/options/decision-support/diagnostics?lookback_days=2"
    )
    assert res.status_code == 200
    body = res.json()
    assert "by_bucket" in body
    assert "exclusion_drivers" in body
    drivers = body["exclusion_drivers"]
    for k in ("low_score", "unqualified_no_severe",
              "severe_combined_with_unqualified_or_low_score"):
        assert k in drivers


# ===========================================================================
# No mutation surface
# ===========================================================================

def test_decision_support_endpoints_reject_mutation_verbs(client):
    paths = (
        "/api/options/decision-support/summary",
        "/api/options/decision-support/review-queue",
        "/api/options/decision-support/review-queue/SPY:2026-01-01:SHORT_PUT_CREDIT_SPREAD",
        "/api/options/decision-support/buckets",
        "/api/options/decision-support/diagnostics",
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


def test_openapi_decision_support_endpoints_are_all_get(client):
    spec = client.get("/openapi.json").json()
    ds_paths = [p for p in spec["paths"]
                if p.startswith("/api/options/decision-support")]
    assert ds_paths
    for path in ds_paths:
        verbs = set(spec["paths"][path].keys()) - {"parameters", "summary"}
        non_read = verbs - {"get", "head", "options"}
        assert not non_read, f"non-read verb on {path}: {non_read}"
