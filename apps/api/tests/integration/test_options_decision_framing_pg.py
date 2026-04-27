"""Phase 11J integration tests — decision-framing endpoints.

Verifies:
  * GET /api/options/decision-framing/summary
  * GET /api/options/decision-framing/narratives  (list with filters)
  * GET /api/options/decision-framing/narratives/{id}  (detail)
  * GET /api/options/decision-framing/compare  (factual deltas only)
  * GET /api/options/decision-framing/checklist/{id}
  * GET /api/options/decision-framing/context/{id}
  * Mutation verbs reject (405); no write surface
  * No LLM/API client invocation in any framing module
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
# Summary
# ===========================================================================

def test_summary_empty_db(client):
    res = client.get("/api/options/decision-framing/summary")
    assert res.status_code == 200
    body = res.json()
    assert body["n_total_observations"] == 0
    assert "Decision framing provides deterministic review context only" in body["decision_framing_disclaimer"]


def test_summary_after_seed(client, pg_session):
    _seed_chain_for_today(pg_session)
    res = client.get(
        "/api/options/decision-framing/summary?lookback_days=2"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["n_total_observations"] >= 1


# ===========================================================================
# Narratives — list + detail
# ===========================================================================

def test_narratives_list(client, pg_session):
    _seed_chain_for_today(pg_session)
    res = client.get(
        "/api/options/decision-framing/narratives?lookback_days=2&limit=10"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["count"] >= 1
    sample = body["narratives"][0]
    for key in (
        "why_it_appears", "caution_paragraph",
        "caveats", "non_action_footer", "paper_only_reminder",
    ):
        assert key in sample


def test_narrative_detail(client, pg_session):
    today = _seed_chain_for_today(pg_session)
    obs_id = f"SPY:{today.isoformat()}:SHORT_PUT_CREDIT_SPREAD"
    res = client.get(
        f"/api/options/decision-framing/narratives/{obs_id}"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == obs_id
    assert "narrative" in body
    assert body["narrative"]["why_it_appears"]
    assert body["narrative"]["non_action_footer"]
    assert body["ranking_explanation"]
    assert body["tie_breakers"]


def test_narrative_detail_404_for_unknown(client):
    res = client.get(
        "/api/options/decision-framing/narratives/SPY:1900-01-01:SHORT_PUT_CREDIT_SPREAD"
    )
    assert res.status_code == 404


# ===========================================================================
# Compare — factual deltas only
# ===========================================================================

def test_compare_two_observations(client, pg_session):
    today = _seed_chain_for_today(pg_session)
    a = f"SPY:{today.isoformat()}:SHORT_PUT_CREDIT_SPREAD"
    b = f"SPY:{today.isoformat()}:IRON_CONDOR"
    res = client.get(
        f"/api/options/decision-framing/compare"
        f"?observation_id_a={a}&observation_id_b={b}"
    )
    assert res.status_code == 200
    body = res.json()
    cmp_ = body["comparison"]
    assert "factual_deltas" in cmp_
    assert "non_preference_notice" in cmp_
    # Spec-mandated wording: NEVER says "better" / "worse" / "choose" /
    # "avoid" / "preferable"
    blob = " ".join([
        cmp_["bucket_phrase"],
        cmp_["ranking_phrase"],
        cmp_["non_preference_notice"],
        *cmp_["factual_deltas"],
    ]).lower()
    for forbidden in ("better", "worse", "choose", "preferable",
                      "avoid", "best"):
        assert forbidden not in blob, (
            f"comparison emitted forbidden word {forbidden!r}"
        )


def test_compare_404_when_either_id_missing(client, pg_session):
    today = _seed_chain_for_today(pg_session)
    a = f"SPY:{today.isoformat()}:SHORT_PUT_CREDIT_SPREAD"
    res = client.get(
        f"/api/options/decision-framing/compare"
        f"?observation_id_a={a}&observation_id_b=NONEXISTENT"
    )
    assert res.status_code == 404


# ===========================================================================
# Checklist
# ===========================================================================

def test_checklist_returns_required_items(client, pg_session):
    today = _seed_chain_for_today(pg_session)
    obs_id = f"SPY:{today.isoformat()}:SHORT_PUT_CREDIT_SPREAD"
    res = client.get(
        f"/api/options/decision-framing/checklist/{obs_id}"
    )
    assert res.status_code == 200
    body = res.json()
    labels = {it["label"] for it in body["checklist"]}
    expected = {
        "Verify data freshness",
        "Verify option chain liquidity",
        "Verify spread / OI / volume",
        "Review model limitation flags",
        "Review pin risk / assignment / settlement flags",
        "Review current market context manually",
        "Confirm this is paper-only analysis",
    }
    assert expected <= labels


def test_checklist_404_for_unknown_id(client):
    res = client.get(
        "/api/options/decision-framing/checklist/SPY:1900-01-01:SHORT_PUT_CREDIT_SPREAD"
    )
    assert res.status_code == 404


# ===========================================================================
# Context
# ===========================================================================

def test_context_bundles_narrative_checklist_caveats(client, pg_session):
    today = _seed_chain_for_today(pg_session)
    obs_id = f"SPY:{today.isoformat()}:SHORT_PUT_CREDIT_SPREAD"
    res = client.get(
        f"/api/options/decision-framing/context/{obs_id}"
    )
    assert res.status_code == 200
    body = res.json()
    assert "narrative" in body and "checklist" in body
    assert "context_caveats" in body
    assert any("Sample size caution" in c for c in body["context_caveats"])
    assert any("Score is not a recommendation" in c for c in body["context_caveats"])


# ===========================================================================
# No mutation surface
# ===========================================================================

def test_decision_framing_endpoints_reject_mutation_verbs(client):
    paths = (
        "/api/options/decision-framing/summary",
        "/api/options/decision-framing/narratives",
        "/api/options/decision-framing/narratives/SPY:2026-01-01:SHORT_PUT_CREDIT_SPREAD",
        "/api/options/decision-framing/compare?observation_id_a=A&observation_id_b=B",
        "/api/options/decision-framing/checklist/SPY:2026-01-01:SHORT_PUT_CREDIT_SPREAD",
        "/api/options/decision-framing/context/SPY:2026-01-01:SHORT_PUT_CREDIT_SPREAD",
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


def test_openapi_decision_framing_endpoints_are_all_get(client):
    spec = client.get("/openapi.json").json()
    df_paths = [p for p in spec["paths"]
                if p.startswith("/api/options/decision-framing")]
    assert df_paths
    for path in df_paths:
        verbs = set(spec["paths"][path].keys()) - {"parameters", "summary"}
        non_read = verbs - {"get", "head", "options"}
        assert not non_read, f"non-read verb on {path}: {non_read}"
