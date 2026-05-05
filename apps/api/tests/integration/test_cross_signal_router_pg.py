"""Cross-signal auto-router — read-only, gated, paper-only.

Verifies:
  * Pure routing logic for every branch (low confidence → IDS,
    edge ≥ +0.5% with chain+liq → prefer_options, edge ≤ -0.5%
    → prefer_stock, missing-chain → watchlist_only, etc.).
  * Caps downgrade surplus routes to watchlist_only with
    blocked_reason set.
  * mark_executable only flips execution_allowed when gate_open=True
    AND route_hint is prefer_stock/options.
  * Endpoint /route-candidates contract: counts, caps, gate (always
    closed via API), would_execute, actual_executed=0.
  * Operator script:
      - default dry-run writes artifact, gate closed.
      - --apply refused without both env flags.
      - --apply with both env flags writes artifact with
        execution_gate_open=True, would_execute >= 0,
        actual_executed=0 (v1 never auto-dispatches).
      - No options_paper_trade or paper_trade rows are written.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db import get_session
from apps.api.src.db.models import (
    Asset, CandidateIdea, PriceBar, RegimeSnapshot,
)
from apps.api.src.db.options_models import (
    OptionsFeatureDaily, OptionsStrategyOutcome,
)
from apps.api.src.domain.cross_signal.router import (
    RoutingThresholds, RoutingCaps, RouteCandidate,
    decide_route, apply_caps, mark_executable,
    build_route_candidates, candidate_to_dict,
)
from apps.api.src.main import app


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(pg_engine):
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )

    def _override():
        s = SessionCls()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


def _candidate(
    *, underlying: str, hint: str = "prefer_options",
) -> RouteCandidate:
    return RouteCandidate(
        underlying=underlying,
        stock_score=0.4, stock_status="trade_ready",
        best_options_strategy="bull_call_spread",
        cross_signal_confidence="medium",
        relative_edge_pct=0.02,
        stock_avg_return_pct=0.01,
        options_avg_return_pct=0.03,
        sample_count=25,
        iv_bucket="medium_iv", trend_bucket="uptrend",
        route_hint=hint, reason="seeded",
    )


# ---------------------------------------------------------------------------
# Pure routing
# ---------------------------------------------------------------------------

def test_decide_route_low_confidence_blocks_execution():
    h, r = decide_route(
        confidence="low", relative_edge_pct=0.05,
        stock_status="trade_ready",
        best_options_strategy="bull_call_spread",
    )
    assert h == "insufficient_data"
    assert "confidence" in r.lower() or "evidence" in r.lower()


def test_decide_route_no_edge_blocks_execution():
    h, _ = decide_route(
        confidence="medium", relative_edge_pct=None,
        stock_status="trade_ready",
        best_options_strategy="bull_call_spread",
    )
    assert h == "insufficient_data"


def test_decide_route_prefer_options_when_edge_positive():
    h, r = decide_route(
        confidence="medium", relative_edge_pct=0.02,
        stock_status="trade_ready",
        best_options_strategy="bull_call_spread",
    )
    assert h == "prefer_options"
    assert "+0.0200" in r


def test_decide_route_prefer_stock_when_edge_negative():
    h, _ = decide_route(
        confidence="medium", relative_edge_pct=-0.02,
        stock_status="trade_ready",
        best_options_strategy="bull_call_spread",
    )
    assert h == "prefer_stock"


def test_decide_route_watchlist_when_edge_below_threshold():
    h, _ = decide_route(
        confidence="medium", relative_edge_pct=0.001,
        stock_status="trade_ready",
        best_options_strategy="bull_call_spread",
    )
    assert h == "watchlist_only"


def test_decide_route_watchlist_when_chain_missing():
    h, r = decide_route(
        confidence="medium", relative_edge_pct=0.02,
        stock_status="trade_ready",
        best_options_strategy="bull_call_spread",
        options_chain_available=False,
    )
    assert h == "watchlist_only"
    assert "chain" in r.lower()


def test_decide_route_watchlist_when_liquidity_fails():
    h, r = decide_route(
        confidence="medium", relative_edge_pct=0.02,
        stock_status="trade_ready",
        best_options_strategy="long_call",
        options_liquidity_ok=False,
    )
    assert h == "watchlist_only"
    assert "liquidity" in r.lower()


def test_decide_route_watchlist_when_no_strategy_match():
    h, r = decide_route(
        confidence="medium", relative_edge_pct=0.02,
        stock_status="trade_ready",
        best_options_strategy=None,
    )
    assert h == "watchlist_only"
    assert "no matching strategy" in r.lower()


def test_decide_route_watchlist_when_stock_not_trade_ready_for_stock():
    h, _ = decide_route(
        confidence="medium", relative_edge_pct=-0.02,
        stock_status="watchlist_candidate",
        best_options_strategy="bull_call_spread",
    )
    assert h == "watchlist_only"


# ---------------------------------------------------------------------------
# Caps
# ---------------------------------------------------------------------------

def test_caps_max_options_per_day():
    cands = [_candidate(underlying=f"OPT{i}") for i in range(5)]
    out = apply_caps(cands, RoutingCaps())
    options_kept = sum(1 for c in out if c.route_hint == "prefer_options")
    blocked = [c for c in out if c.blocked_reason]
    assert options_kept == 2
    assert any(
        "max_options_per_day" in (c.blocked_reason or "")
        for c in blocked
    )


def test_caps_max_stock_per_day():
    cands = [
        _candidate(underlying=f"STK{i}", hint="prefer_stock")
        for i in range(5)
    ]
    out = apply_caps(cands, RoutingCaps())
    stock_kept = sum(1 for c in out if c.route_hint == "prefer_stock")
    assert stock_kept == 3


def test_caps_per_underlying():
    cands = [
        _candidate(underlying="DUP", hint="prefer_stock"),
        _candidate(underlying="DUP", hint="prefer_options"),
    ]
    out = apply_caps(cands, RoutingCaps())
    kept = [
        c for c in out
        if c.route_hint in ("prefer_stock", "prefer_options")
    ]
    assert len(kept) == 1
    blocked = [c for c in out if c.blocked_reason]
    assert blocked[0].blocked_reason
    assert "per_underlying_cap" in blocked[0].blocked_reason


def test_caps_max_total():
    cands = (
        [
            _candidate(underlying=f"S{i}", hint="prefer_stock")
            for i in range(3)
        ]
        + [
            _candidate(underlying=f"O{i}", hint="prefer_options")
            for i in range(3)
        ]
    )
    out = apply_caps(cands, RoutingCaps())
    actionable = sum(
        1 for c in out
        if c.route_hint in ("prefer_stock", "prefer_options")
    )
    assert actionable == 5  # max_routed_per_day


# ---------------------------------------------------------------------------
# mark_executable
# ---------------------------------------------------------------------------

def test_mark_executable_gate_closed_keeps_all_false():
    cs = [
        _candidate(underlying="A", hint="prefer_options"),
        _candidate(underlying="B", hint="prefer_stock"),
        _candidate(underlying="C", hint="watchlist_only"),
    ]
    out = mark_executable(cs, gate_open=False)
    assert all(c.execution_allowed is False for c in out)


def test_mark_executable_gate_open_only_action_hints():
    cs = [
        _candidate(underlying="A", hint="prefer_options"),
        _candidate(underlying="B", hint="prefer_stock"),
        _candidate(underlying="C", hint="watchlist_only"),
        _candidate(underlying="D", hint="insufficient_data"),
    ]
    out = mark_executable(cs, gate_open=True)
    by = {c.underlying: c.execution_allowed for c in out}
    assert by["A"] is True
    assert by["B"] is True
    assert by["C"] is False
    assert by["D"] is False


# ---------------------------------------------------------------------------
# Build pipeline (using today-assistant-shaped dicts)
# ---------------------------------------------------------------------------

def test_build_route_candidates_chain_oracle_blocks_options():
    items = [{
        "underlying": "AMZN",
        "stock_score": 0.6, "stock_status": "trade_ready",
        "best_options_strategy": "bull_call_spread",
        "iv_bucket": "medium_iv", "trend_bucket": "uptrend",
        "historical_edge": {
            "sample_count": 25,
            "stock_avg_return_pct": 0.01,
            "options_avg_return_pct": 0.03,
            "relative_edge_pct": 0.02,
            "confidence": "medium",
        },
    }]
    cands = build_route_candidates(
        items,
        options_chain_available_for=lambda _u: False,
        gate_open=True,
    )
    assert cands[0].route_hint == "watchlist_only"
    assert cands[0].execution_allowed is False


def test_build_route_candidates_full_path():
    items = [{
        "underlying": "AMZN",
        "stock_score": 0.6, "stock_status": "trade_ready",
        "best_options_strategy": "bull_call_spread",
        "iv_bucket": "medium_iv", "trend_bucket": "uptrend",
        "historical_edge": {
            "sample_count": 30,
            "stock_avg_return_pct": 0.01,
            "options_avg_return_pct": 0.03,
            "relative_edge_pct": 0.02,
            "confidence": "medium",
        },
    }]
    cands = build_route_candidates(
        items,
        options_chain_available_for=lambda _u: True,
        gate_open=True,
    )
    c = cands[0]
    assert c.route_hint == "prefer_options"
    assert c.execution_allowed is True
    assert c.blocked_reason is None


# ---------------------------------------------------------------------------
# Endpoint contract
# ---------------------------------------------------------------------------

def test_endpoint_route_candidates_shape(client):
    resp = client.get(
        "/api/performance/cross-signal/route-candidates"
        "?as_of=2026-04-30&limit=5"
    )
    assert resp.status_code == 200
    body = resp.json()
    for k in (
        "as_of_date", "items", "counts_by_hint",
        "would_execute", "actual_executed",
        "thresholds", "caps", "execution_gate", "notice",
    ):
        assert k in body
    assert body["execution_gate"]["open"] is False
    assert body["actual_executed"] == 0


# ---------------------------------------------------------------------------
# Operator script
# ---------------------------------------------------------------------------

def _seed_minimal_history(session: Session, as_of: dt.date) -> None:
    """Seed enough rows so build_today_assistant has at least one
    actionable candidate. Keeps options confidence at low (no
    opt outcomes) so router refuses execution by default — that's
    the expected dry-run state."""
    session.add(RegimeSnapshot(
        as_of_date=as_of, benchmark_symbol="SPY",
        market_trend="uptrend", vol_regime="normal",
        breadth_regime="ok", sma50_over_sma200=True,
        realized_vol_20d=Decimal("0.15"),
        atr_pctile_1y=Decimal("0.40"),
    ))
    a = Asset(
        symbol="ZRT", name="ZRT", asset_class="equity",
        sector="tech", currency="USD", is_active=True,
    )
    session.add(a)
    session.flush()
    session.add(CandidateIdea(
        as_of_date=as_of, asset_id=a.id,
        model_version="test", engine="stock_swing",
        status="accepted", action="Buy",
        composite_score=Decimal("0.40"),
        confidence=Decimal("0.6"),
    ))
    session.commit()


def test_script_default_dry_run_writes_artifact_no_dispatch(
    pg_session, tmp_path, monkeypatch,
):
    monkeypatch.delenv("AUTO_ROUTE_STOCK_OPTIONS_ENABLED", raising=False)
    monkeypatch.delenv("AUTO_ROUTE_EXECUTION_ENABLED", raising=False)
    as_of = dt.date(2026, 4, 30)
    _seed_minimal_history(pg_session, as_of)
    monkeypatch.chdir(tmp_path)
    from scripts.run_cross_signal_router import main
    rc = main(["--dry-run", "--as-of", as_of.isoformat(), "--limit", "5"])
    assert rc == 0
    out = tmp_path / "artifacts/cross_signal_routing"
    files = list(out.glob("route_eval_*.json"))
    assert files
    artifact = json.loads(files[0].read_text())
    assert artifact["execution_gate_open"] is False
    assert artifact["actual_executed"] == 0
    # Nothing dispatched: no paper_trade / options_paper_trade rows.
    assert pg_session.execute(
        text("SELECT count(*) FROM paper_trade")
    ).scalar() == 0
    assert pg_session.execute(
        text("SELECT count(*) FROM options_paper_trade")
    ).scalar() == 0


def test_script_apply_refused_without_env(monkeypatch):
    monkeypatch.delenv("AUTO_ROUTE_STOCK_OPTIONS_ENABLED", raising=False)
    monkeypatch.delenv("AUTO_ROUTE_EXECUTION_ENABLED", raising=False)
    from scripts.run_cross_signal_router import main
    rc = main(["--apply"])
    assert rc == 2


def test_script_apply_refused_with_only_one_flag(monkeypatch):
    monkeypatch.setenv("AUTO_ROUTE_STOCK_OPTIONS_ENABLED", "true")
    monkeypatch.delenv("AUTO_ROUTE_EXECUTION_ENABLED", raising=False)
    from scripts.run_cross_signal_router import main
    rc = main(["--apply"])
    assert rc == 2


def test_script_apply_with_both_flags_opens_gate_no_dispatch(
    pg_session, tmp_path, monkeypatch,
):
    monkeypatch.setenv("AUTO_ROUTE_STOCK_OPTIONS_ENABLED", "true")
    monkeypatch.setenv("AUTO_ROUTE_EXECUTION_ENABLED", "true")
    as_of = dt.date(2026, 4, 30)
    _seed_minimal_history(pg_session, as_of)
    monkeypatch.chdir(tmp_path)
    from scripts.run_cross_signal_router import main
    rc = main(["--apply", "--as-of", as_of.isoformat(), "--limit", "5"])
    assert rc == 0
    out = tmp_path / "artifacts/cross_signal_routing"
    artifact = json.loads(
        next(out.glob("route_eval_*.json")).read_text()
    )
    assert artifact["execution_gate_open"] is True
    # v1 never auto-dispatches — actual_executed always 0.
    assert artifact["actual_executed"] == 0
    # Confirm: no rows written by router.
    assert pg_session.execute(
        text("SELECT count(*) FROM paper_trade")
    ).scalar() == 0
    assert pg_session.execute(
        text("SELECT count(*) FROM options_paper_trade")
    ).scalar() == 0


def test_script_apply_bad_as_of_refuses(monkeypatch):
    monkeypatch.setenv("AUTO_ROUTE_STOCK_OPTIONS_ENABLED", "true")
    monkeypatch.setenv("AUTO_ROUTE_EXECUTION_ENABLED", "true")
    from scripts.run_cross_signal_router import main
    rc = main(["--apply", "--as-of", "not-a-date"])
    assert rc == 2
