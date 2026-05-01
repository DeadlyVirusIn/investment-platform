"""Phase 11W (incident fix) — options pipeline status diagnostic.

Verifies the new GET /options/pipeline-status endpoint reports
honest "not active" state when no daily options pipeline is wired."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.src.options.routes_readonly import router as options_router


class _StubMappings:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _StubResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return _StubMappings(self._row)


class _StubSession:
    def __init__(self, row):
        self._row = row

    def execute(self, *a, **kw):
        return _StubResult(self._row)


def _build_app(session) -> TestClient:
    """Mount the options router with the session dependency
    overridden to return our stub."""
    from apps.api.src.db import get_session

    app = FastAPI()
    app.include_router(options_router, prefix="/api")
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def test_options_pipeline_status_reports_inactive_when_empty():
    s = _StubSession({
        "chain_snapshots": 0,
        "chain_max_date": None,
        "features": 0,
        "feature_max_date": None,
        "paper_trades": 0,
        "paper_trade_max_date": None,
    })
    client = _build_app(s)
    r = client.get("/api/options/pipeline-status")
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is False
    assert body["last_run"] is None
    assert "not scheduled" in body["reason"].lower()
    assert body["options_paper_trade_count"] == 0
    assert body["options_feature_daily_count"] == 0
    assert "next_phase_required" in body


def test_options_pipeline_status_reports_inactive_with_seed_chain():
    """Even when options_chain_snapshot has manual seed rows, the
    pipeline is still inactive because no daily evaluator runs."""
    import datetime as dt

    s = _StubSession({
        "chain_snapshots": 8,
        "chain_max_date": dt.date(2026, 4, 27),
        "features": 0,
        "feature_max_date": None,
        "paper_trades": 0,
        "paper_trade_max_date": None,
    })
    client = _build_app(s)
    r = client.get("/api/options/pipeline-status")
    body = r.json()
    assert body["active"] is False
    assert body["options_chain_snapshot_count"] == 8
    assert body["options_chain_snapshot_max_date"] == "2026-04-27"
    assert body["options_paper_trade_count"] == 0
    assert body["options_feature_daily_count"] == 0


def test_options_pipeline_status_carries_paper_only_notice():
    s = _StubSession({
        "chain_snapshots": 0, "chain_max_date": None,
        "features": 0, "feature_max_date": None,
        "paper_trades": 0, "paper_trade_max_date": None,
    })
    client = _build_app(s)
    r = client.get("/api/options/pipeline-status")
    assert "paper" in r.json()["notice"].lower()
