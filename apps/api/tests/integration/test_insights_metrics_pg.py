"""Integration: F7 metrics through the live insights endpoint.

Exercises the full HTTP roundtrip across the disabled / cache-miss
/ cache-hit / unsafe / transport-failure paths, asserting each
counter increments at the right time and never at the wrong time.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.config import settings
from apps.api.src.db import get_session
from apps.api.src.db.models import AgentInsight
from apps.api.src.domain.agents import llm_client, metrics
from apps.api.src.domain.agents.registry import BANNER
from apps.api.src.main import app


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------
# Mock SDK shims
# ---------------------------------------------------------------------

@dataclass
class _Block:
    text: str


@dataclass
class _Resp:
    content: list


class _Messages:
    def __init__(self, body: str):
        self._body = body

    def create(self, **kwargs):
        return _Resp(content=[_Block(text=self._body)])


class _Client:
    def __init__(self, body: str):
        self.messages = _Messages(body)


class _SDK:
    def __init__(self, body: str):
        self._body = body

    def Anthropic(self, **kwargs):
        return _Client(self._body)


def _explode_timeout_sdk():
    class _Boom:
        class messages:  # noqa: N801
            @staticmethod
            def create(**kwargs):
                raise TimeoutError("simulated")

    class _S:
        def Anthropic(self, **kwargs):
            return _Boom()

    return _S()


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_metrics_each_test():
    metrics.reset()
    yield
    metrics.reset()


@pytest.fixture(autouse=True)
def _truncate_cache(pg_engine):
    from sqlalchemy import text as _text
    with pg_engine.begin() as conn:
        conn.execute(_text(
            "TRUNCATE TABLE agent_insight RESTART IDENTITY CASCADE",
        ))
    yield


@pytest.fixture
def client(pg_engine, monkeypatch):
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
        yield TestClient(app), SessionCls
    finally:
        app.dependency_overrides.pop(get_session, None)


def _enable(monkeypatch, model="claude-test"):
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_MODEL", model)


def _disable(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", False)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")


_PAYLOAD = {
    "score": 72, "grade": "B", "thesis": "winner_trim",
    "completeness": "full",
    "components": {
        "entry": 18, "return": 22,
        "hold": 12, "exit_or_status": 10,
        "completeness": 10,
    },
    "reasons": ["Entry: favorable.", "Return: 4 percent."],
}


_SAFE_BODY = (
    f"{BANNER}\n"
    "Score is 72. Solid B-grade trade — entry component "
    "contributed the most at 18 of 20."
)


# ---------------------------------------------------------------------
# Disabled — request + disabled, NO cache, NO LLM
# ---------------------------------------------------------------------

def test_disabled_increments_request_and_disabled_only(
    client, monkeypatch,
):
    test_client, _ = client
    _disable(monkeypatch)

    sdk = _SDK(_SAFE_BODY)
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: sdk)

    r = test_client.get("/api/insights/trade_quality")
    assert r.status_code == 503
    snap = metrics.snapshot()
    assert snap["requests_total"] == 1
    assert snap["disabled_total"] == 1
    assert snap["cache_hit_total"] == 0
    assert snap["cache_miss_total"] == 0
    assert snap["llm_calls_total"] == 0
    assert snap["safety_rejected_total"] == 0
    assert snap["transport_error_total"] == 0
    assert snap["estimated_cost_usd_total"] == 0.0


# ---------------------------------------------------------------------
# Enabled cache miss — request + miss + llm_calls + cost > 0
# ---------------------------------------------------------------------

def test_first_enabled_request_records_miss_and_llm_call(
    client, monkeypatch,
):
    test_client, _ = client
    _enable(monkeypatch)

    sdk = _SDK(_SAFE_BODY)
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: sdk)

    r = test_client.request(
        "GET", "/api/insights/trade_quality", json=_PAYLOAD,
    )
    assert r.status_code == 200, r.text
    assert r.json()["cache"] == "miss"
    snap = metrics.snapshot()
    assert snap["requests_total"] == 1
    assert snap["cache_miss_total"] == 1
    assert snap["llm_calls_total"] == 1
    assert snap["cache_hit_total"] == 0
    assert snap["disabled_total"] == 0
    assert snap["estimated_cost_usd_total"] > 0.0
    assert snap["last_call_at"] is not None


# ---------------------------------------------------------------------
# Cache hit — does NOT increment llm_calls
# ---------------------------------------------------------------------

def test_second_identical_request_increments_only_cache_hit(
    client, monkeypatch,
):
    test_client, _ = client
    _enable(monkeypatch)

    sdk = _SDK(_SAFE_BODY)
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: sdk)

    test_client.request(
        "GET", "/api/insights/trade_quality", json=_PAYLOAD,
    )
    snap1 = metrics.snapshot()

    r2 = test_client.request(
        "GET", "/api/insights/trade_quality", json=_PAYLOAD,
    )
    assert r2.status_code == 200
    assert r2.json()["cache"] == "hit"
    snap2 = metrics.snapshot()

    # llm_calls did not increase across the second request.
    assert snap2["llm_calls_total"] == snap1["llm_calls_total"] == 1
    assert snap2["cache_hit_total"] == 1
    assert snap2["cache_miss_total"] == 1   # unchanged from miss path
    assert snap2["requests_total"] == 2
    # Cost did not grow.
    assert (
        snap2["estimated_cost_usd_total"]
        == snap1["estimated_cost_usd_total"]
    )


# ---------------------------------------------------------------------
# Unsafe response — safety_rejected, NO cache write
# ---------------------------------------------------------------------

def test_unsafe_response_increments_safety_and_writes_no_cache(
    client, monkeypatch,
):
    test_client, SessionCls = client
    _enable(monkeypatch)

    bad = _SDK(f"{BANNER}\nOperator should buy now.")
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: bad)

    r = test_client.request(
        "GET", "/api/insights/trade_quality", json=_PAYLOAD,
    )
    assert r.status_code == 502
    snap = metrics.snapshot()
    assert snap["safety_rejected_total"] == 1
    assert snap["transport_error_total"] == 0
    # LLM was actually called (transport succeeded), but the body
    # was rejected.
    assert snap["llm_calls_total"] == 1
    # Cache miss recorded; no row landed in the table.
    assert snap["cache_miss_total"] == 1
    with SessionCls() as s:
        rows = s.execute(select(AgentInsight)).scalars().all()
        assert len(rows) == 0
    # last_error_reason describes the safety rejection.
    assert snap["last_error_reason"].startswith("safety:")


# ---------------------------------------------------------------------
# Transport failure — transport_error, NO cache write, no llm_calls
# ---------------------------------------------------------------------

def test_transport_error_increments_transport_only(
    client, monkeypatch,
):
    test_client, SessionCls = client
    _enable(monkeypatch)

    monkeypatch.setattr(
        llm_client, "_get_sdk", lambda: _explode_timeout_sdk(),
    )

    r = test_client.request(
        "GET", "/api/insights/trade_quality", json=_PAYLOAD,
    )
    assert r.status_code == 502
    snap = metrics.snapshot()
    assert snap["transport_error_total"] == 1
    assert snap["llm_calls_total"] == 0
    assert snap["safety_rejected_total"] == 0
    assert snap["cache_miss_total"] == 1
    with SessionCls() as s:
        rows = s.execute(select(AgentInsight)).scalars().all()
        assert len(rows) == 0
    assert snap["last_error_reason"].startswith("transport:")


# ---------------------------------------------------------------------
# Status endpoint exposes metrics + never the API key
# ---------------------------------------------------------------------

def test_status_exposes_metrics_block(client, monkeypatch):
    test_client, _ = client
    _enable(monkeypatch, model="claude-test")
    sdk = _SDK(_SAFE_BODY)
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: sdk)

    test_client.request(
        "GET", "/api/insights/trade_quality", json=_PAYLOAD,
    )

    r = test_client.get("/api/insights/status")
    assert r.status_code == 200
    body = r.json()
    assert "metrics" in body
    m = body["metrics"]
    assert m["requests_total"] >= 1
    assert m["llm_calls_total"] >= 1
    assert m["estimated_cost_usd_total"] >= 0.0


def test_status_never_exposes_api_key(client, monkeypatch):
    test_client, _ = client
    secret = "sk-ant-do-not-leak-this"
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", secret)

    r = test_client.get("/api/insights/status")
    assert r.status_code == 200
    assert secret not in r.text


def test_status_does_not_invoke_sdk(client, monkeypatch):
    test_client, _ = client
    _enable(monkeypatch)

    def _explode():
        raise AssertionError("status must not touch the SDK")

    monkeypatch.setattr(llm_client, "_get_sdk", _explode)
    r = test_client.get("/api/insights/status")
    assert r.status_code == 200


# ---------------------------------------------------------------------
# No execution-table writes
# ---------------------------------------------------------------------

def test_metrics_path_writes_no_execution_rows(
    client, pg_engine, monkeypatch,
):
    test_client, _ = client
    _enable(monkeypatch)
    sdk = _SDK(_SAFE_BODY)
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: sdk)

    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy import text as _text

    insp = sa_inspect(pg_engine)
    existing = set(insp.get_table_names())
    sample = [t for t in (
        "paper_trade", "paper_position", "paper_equity_snapshot",
        "decision_log", "recommendation",
    ) if t in existing]
    assert sample

    def _counts() -> dict[str, int]:
        with pg_engine.begin() as conn:
            return {
                t: int(conn.execute(_text(
                    f'SELECT count(*) FROM "{t}"'
                )).scalar() or 0)
                for t in sample
            }

    before = _counts()
    test_client.request(
        "GET", "/api/insights/trade_quality", json=_PAYLOAD,
    )
    test_client.get("/api/insights/status")
    after = _counts()
    assert before == after
