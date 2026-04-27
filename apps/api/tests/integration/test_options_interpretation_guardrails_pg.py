"""Phase 11K integration tests — guardrail endpoints.

Verifies:
  * GET /api/options/interpretation-guardrails/score/{id}
  * GET /api/options/interpretation-guardrails/bucket/{id}
  * GET /api/options/interpretation-guardrails/ranking/{id}
  * GET /api/options/interpretation-guardrails/page-context
  * Response payloads contain the spec-mandated guardrail copy
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


pytestmark = pytest.mark.integration


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
    return today


# ===========================================================================
# Page context — static, no DB read required
# ===========================================================================

def test_page_context_endpoint_returns_universal_block(client):
    res = client.get("/api/options/interpretation-guardrails/page-context")
    assert res.status_code == 200
    body = res.json()
    pc = body["page_context"]
    assert "Options are paper-trading only" in pc["notice_paper_only"]
    assert "Observation only" in pc["notice_observation_only"]
    assert "rule-based paper analytics" in pc["notice_evaluation"]
    assert "Review queues are for human inspection only" in pc["notice_decision_support"]
    assert "deterministic review context only" in pc["notice_decision_framing"]
    assert "Interpretation guardrails" in pc["notice_interpretation_guardrails"]
    wtdn = pc["what_this_does_not_mean"]
    assert "expected profitability" in wtdn["not_expected_profitability"]
    assert "probability of trade success" in wtdn["not_probability_of_success"]
    assert "suitability" in wtdn["not_suitability_for_trading"]
    assert "instruction to act" in wtdn["not_instruction_to_act"]
    assert "live-market signal" in wtdn["not_live_market_signal"]
    assert "Viewing only a subset of observations may create selection bias" in (
        pc["selection_bias_banner_default_text"]
    )


# ===========================================================================
# Score / Bucket / Ranking interpretation
# ===========================================================================

def test_score_interpretation_endpoint(client, pg_session):
    today = _seed_chain_for_today(pg_session)
    obs_id = f"SPY:{today.isoformat()}:SHORT_PUT_CREDIT_SPREAD"
    res = client.get(
        f"/api/options/interpretation-guardrails/score/{obs_id}"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == obs_id
    si = body["score_interpretation"]
    assert "deterministic" in si["headline"]
    assert any("forecast" in n for n in si["is_not_what"])
    assert "review context only" in si["review_only_footer"]


def test_bucket_interpretation_endpoint(client, pg_session):
    today = _seed_chain_for_today(pg_session)
    obs_id = f"SPY:{today.isoformat()}:SHORT_PUT_CREDIT_SPREAD"
    res = client.get(
        f"/api/options/interpretation-guardrails/bucket/{obs_id}"
    )
    assert res.status_code == 200
    body = res.json()
    bi = body["bucket_interpretation"]
    assert bi["bucket"] == body["bucket"]
    # is_what carries the universal "deterministic classification cascade" phrase
    assert "deterministic classification cascade" in bi["is_what"]
    # is_not_what asserts the universal "not selected/rejected" stance
    blob = " ".join(bi["is_not_what"]).lower()
    assert "selected" in blob or "rejected" in blob
    assert "favourable" in blob or "actionable" in blob


def test_ranking_interpretation_endpoint(client, pg_session):
    today = _seed_chain_for_today(pg_session)
    obs_id = f"SPY:{today.isoformat()}:SHORT_PUT_CREDIT_SPREAD"
    res = client.get(
        f"/api/options/interpretation-guardrails/ranking/{obs_id}"
    )
    assert res.status_code == 200
    body = res.json()
    ri = body["ranking_interpretation"]
    # Required spec phrase
    assert "appears earlier under deterministic ordering rules" in (
        ri["deterministic_ordering_phrase"]
    )
    # Forbidden ranking words absent
    blob = " ".join([
        ri["headline"],
        ri["is_what"],
        *ri["is_not_what"],
        ri["review_only_footer"],
    ]).lower()
    import re
    for forbidden in (r"\bbetter\b", r"\bworse\b",
                      r"\bprefer\b", r"\bchoose\b"):
        assert not re.search(forbidden, blob), (
            f"ranking endpoint emitted forbidden word {forbidden!r}"
        )


# ===========================================================================
# 404 paths
# ===========================================================================

def test_score_interpretation_404_for_unknown(client):
    res = client.get(
        "/api/options/interpretation-guardrails/score/SPY:1900-01-01:X"
    )
    assert res.status_code == 404


def test_bucket_interpretation_404_for_unknown(client):
    res = client.get(
        "/api/options/interpretation-guardrails/bucket/SPY:1900-01-01:X"
    )
    assert res.status_code == 404


def test_ranking_interpretation_404_for_unknown(client):
    res = client.get(
        "/api/options/interpretation-guardrails/ranking/SPY:1900-01-01:X"
    )
    assert res.status_code == 404


# ===========================================================================
# Mutation surface
# ===========================================================================

def test_guardrail_endpoints_reject_mutation_verbs(client):
    paths = (
        "/api/options/interpretation-guardrails/score/SPY:2026-01-01:X",
        "/api/options/interpretation-guardrails/bucket/SPY:2026-01-01:X",
        "/api/options/interpretation-guardrails/ranking/SPY:2026-01-01:X",
        "/api/options/interpretation-guardrails/page-context",
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


def test_openapi_guardrail_endpoints_are_all_get(client):
    spec = client.get("/openapi.json").json()
    ig_paths = [p for p in spec["paths"]
                if p.startswith("/api/options/interpretation-guardrails")]
    assert ig_paths
    for path in ig_paths:
        verbs = set(spec["paths"][path].keys()) - {"parameters", "summary"}
        non_read = verbs - {"get", "head", "options"}
        assert not non_read, f"non-read verb on {path}: {non_read}"
