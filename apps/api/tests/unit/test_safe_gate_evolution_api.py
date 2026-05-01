"""Phase 11X — safe_gate_evolution API tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.src.api.safe_gate_evolution import (
    router as sge_router,
)


class _Mappings:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return _Mappings(self._rows)


class _StubSession:
    def __init__(self, plan):
        self._plan = plan

    def execute(self, sql, params=None):
        s = str(sql)
        for needle, payload in self._plan.items():
            if needle in s:
                return _Result(payload)
        return _Result([])


def _build(session) -> TestClient:
    from apps.api.src.db import get_session

    app = FastAPI()
    app.include_router(sge_router, prefix="/api")
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def test_summary_handles_empty_table():
    # Match each query by a substring unique to its FROM/GROUP BY.
    plan = {
        "days_evaluated": [{
            "days_evaluated": 0,
            "days_production_flat": 0,
            "days_shadow_eligible": 0,
            "days_zero_favorable": 0,
            "days_production_traded": 0,
            "avg_favorable": None,
            "avg_eligible_score": None,
            "min_eligible_score": None,
            "max_eligible_score": None,
        }],
        "GROUP BY symbol": [],
        "GROUP BY shadow_reason": [],
        "GROUP BY macro_favorable_count": [],
    }
    s = _StubSession(plan)
    client = _build(s)
    r = client.get("/api/safe-gate-evolution/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["days_evaluated"] == 0
    assert body["counts"]["days_shadow_eligible"] == 0
    assert "Shadow note" in body["notice"]
    assert body["top_symbols"] == []
    assert body["blocked_reasons"] == []
    assert body["favorable_distribution"] == []


def test_runs_endpoint_returns_metadata_only():
    import datetime as dt

    s = _StubSession({"FROM safe_gate_evolution_shadow": [{
        "id": "abc",
        "run_date": dt.date(2026, 4, 29),
        "symbol": None, "side": None,
        "composite_score": None, "confidence": None,
        "macro_favorable_count": 0,
        "failed_macro_gates": [
            "rates_calm", "vrp_supportive",
            "credit_stable", "liquidity_expanding",
        ],
        "price_regime": {"market_trend": "uptrend"},
        "original_selector_reason": "stress=True ...",
        "shadow_reason": "macro_favorable_count_zero",
        "hypothetical_size_multiplier": 0.25,
        "would_trade": False,
        "created_at": dt.datetime(2026, 5, 1, 12, 0, 0,
                                  tzinfo=dt.timezone.utc),
    }]})
    client = _build(s)
    r = client.get("/api/safe-gate-evolution/runs")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    row = body["rows"][0]
    assert row["would_trade"] is False
    assert row["shadow_reason"] == "macro_favorable_count_zero"
    # Banner present
    assert "Shadow note" in body["notice"]


def test_router_is_get_only():
    """Phase 11X must expose GET endpoints only."""
    forbidden = {"POST", "PUT", "PATCH", "DELETE"}
    for route in sge_router.routes:
        methods = getattr(route, "methods", set())
        assert forbidden.isdisjoint(methods), (
            f"forbidden non-GET method on {route.path}: {methods}"
        )


def test_no_recommendation_language_in_route_source():
    from pathlib import Path

    src = Path(
        "apps/api/src/api/safe_gate_evolution.py"
    ).read_text(encoding="utf-8")
    # NOTE: 'recommend' allowed in passing comment context if needed
    # but body strings, banner text, and JSON keys must NOT promote.
    forbidden = (
        "best_trade", "trade_now", "high_conviction",
        "recommend_buy", "recommended_action",
    )
    for tok in forbidden:
        assert tok not in src, f"forbidden token {tok!r} in route source"
