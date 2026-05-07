"""Unit tests for the /api/insights/{kind} endpoint.

Mocked Anthropic SDK only — NO real network call. Verifies the
happy path, the explicit-payload path, and the unknown-kind path.
Feature-flag and source-level guarantees live in the integration
file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apps.api.src.config import settings
from apps.api.src.domain.agents import llm_client
from apps.api.src.domain.agents.registry import BANNER


# ---------------------------------------------------------------------
# Minimal fake Anthropic SDK
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


# ---------------------------------------------------------------------
# Test client + monkeypatched settings + injected SDK
# ---------------------------------------------------------------------

@pytest.fixture
def app_client(monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_MODEL", "claude-test")
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_TIMEOUT_SECONDS", 5.0)
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_MAX_TOKENS", 800)

    fake = _SDK(body=(
        f"{BANNER}\n"
        "Score is 72. Solid B-grade trade — entry component "
        "contributed the most at 18 of 20."
    ))
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: fake)

    from apps.api.src.main import app
    return TestClient(app)


# ---------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------

def test_endpoint_returns_200_with_full_shape(app_client):
    r = app_client.get("/api/insights/trade_quality")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "trade_quality"
    assert body["model"] == "claude-test"
    assert body["banner"] == BANNER
    assert body["llm_enabled"] is True
    assert body["source_endpoint"].endswith("/trade-quality")
    assert "generated_at" in body
    assert BANNER in body["content_markdown"]


@pytest.mark.parametrize("kind", [
    "trade_quality", "risk_commentary",
    "exit_review", "options_thesis",
])
def test_endpoint_works_for_every_kind(monkeypatch, kind):
    """All four kinds should round-trip through the fixture path."""
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_MODEL", "claude-test")
    fake = _SDK(body=(
        f"{BANNER}\n"
        "Plain narrative containing only payload-traceable numbers."
    ))
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: fake)

    from apps.api.src.main import app
    client = TestClient(app)
    r = client.get(f"/api/insights/{kind}")
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == kind


def test_explicit_payload_overrides_fixture(monkeypatch):
    """Body posted with the request must take precedence over the
    built-in fixture. Inject a fake SDK that echoes only numbers
    present in this payload so the post-call hallucination gate
    does not fire."""
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_MODEL", "claude-test")

    fake = _SDK(body=(
        f"{BANNER}\n"
        "Score is 99 — A grade. Return component scored 30."
    ))
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: fake)

    from apps.api.src.main import app
    client = TestClient(app)
    payload = {
        "score": 99,
        "grade": "A",
        "thesis": "winner_trim",
        "completeness": "full",
        "components": {
            "entry": 20, "return": 30,
            "hold": 15, "exit_or_status": 25,
            "completeness": 10,
        },
        "reasons": ["Entry: clean.", "Return: 5 percent realized."],
    }
    r = client.request(
        "GET", "/api/insights/trade_quality", json=payload,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "99" in body["content_markdown"]


# ---------------------------------------------------------------------
# Negative paths
# ---------------------------------------------------------------------

def test_unknown_kind_returns_404(app_client):
    r = app_client.get("/api/insights/not_a_real_kind")
    assert r.status_code == 404
    body = r.json()
    assert "error" in body
    assert "not_a_real_kind" in body["error"]


def test_unsafe_response_returns_502(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    bad = _SDK(body=f"{BANNER}\nOperator should buy now.")
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: bad)

    from apps.api.src.main import app
    client = TestClient(app)
    r = client.get("/api/insights/trade_quality")
    assert r.status_code == 502
    body = r.json()
    assert body["error"] == "insight rejected by safety layer"
    # Reason exists but does not echo the unsafe content verbatim.
    assert "buy now" in body["reason"]
    # The unsafe markdown body is NOT in the response.
    assert "Operator" not in body.get("content_markdown", "")


def test_response_is_deterministic_for_same_input(app_client):
    """Same fixture body → identical response shape on repeat calls.
    `generated_at` may differ, every other field must be equal."""
    a = app_client.get("/api/insights/trade_quality").json()
    b = app_client.get("/api/insights/trade_quality").json()
    for key in ("kind", "model", "banner", "content_markdown",
                "source_endpoint", "llm_enabled"):
        assert a[key] == b[key], f"field {key!r} not deterministic"
