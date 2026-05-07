"""Phase F5 unit tests for `/api/insights/status`.

The status endpoint is read-only, never calls the LLM, and never
reads from any table other than `agent_insight`. These tests
exercise the disabled-by-default behavior, the API-key
non-disclosure, and the SDK / table isolation invariants.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.src.config import settings
from apps.api.src.db import get_session
from apps.api.src.domain.agents import llm_client
from apps.api.src.domain.agents.registry import BANNER


@pytest.fixture(autouse=True)
def _disable_db_cache():
    """Status endpoint must work even with no DB. Override
    `get_session` to yield None so the cache-row count returns 0
    without attempting a connection."""
    from apps.api.src.main import app

    def _no_session():
        yield None

    app.dependency_overrides[get_session] = _no_session
    yield
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture
def client() -> TestClient:
    from apps.api.src.main import app
    return TestClient(app)


# ---------------------------------------------------------------------
# Disabled-by-default
# ---------------------------------------------------------------------

def test_status_default_state_is_disabled(monkeypatch, client):
    """Production default: flag off, no key. Status MUST report
    enabled=false and llm_configured=false."""
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", False)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")

    r = client.get("/api/insights/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["enabled"] is False
    assert body["llm_configured"] is False
    assert body["execution_linked"] is False
    assert body["banner"] == BANNER
    assert body["cache_enabled"] is True
    assert body["cache_rows"] == 0
    assert "model" in body


def test_status_flag_off_with_key_present_still_disabled(
    monkeypatch, client,
):
    """Flag off but key configured → status MUST still report
    enabled=false. The flag is the master gate."""
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", False)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-secret")

    r = client.get("/api/insights/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    # Key configured but flag off → llm_configured reports presence,
    # not effective state. The frontend chooses what to render based
    # on `enabled`, not `llm_configured`.
    assert body["llm_configured"] is True


def test_status_enabled_with_key_reports_both_true(
    monkeypatch, client,
):
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-secret")

    r = client.get("/api/insights/status")
    body = r.json()
    assert body["enabled"] is True
    assert body["llm_configured"] is True


# ---------------------------------------------------------------------
# API key non-disclosure
# ---------------------------------------------------------------------

def test_status_never_exposes_api_key_value(monkeypatch, client):
    secret = "sk-ant-do-not-leak-this-anywhere"
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", secret)

    r = client.get("/api/insights/status")
    assert secret not in r.text, (
        "/api/insights/status response leaked the raw API key"
    )


@pytest.mark.parametrize("whitespace_key", [" ", "   ", "\t\t"])
def test_status_treats_whitespace_key_as_unconfigured(
    monkeypatch, client, whitespace_key,
):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", whitespace_key)
    r = client.get("/api/insights/status")
    assert r.json()["llm_configured"] is False


# ---------------------------------------------------------------------
# Status MUST NOT call the LLM
# ---------------------------------------------------------------------

def test_status_does_not_invoke_sdk(monkeypatch, client):
    """An exploding SDK would surface as a 500 if the endpoint
    accidentally invoked it."""

    def _explode():
        raise AssertionError("SDK must not be touched by /status")

    monkeypatch.setattr(llm_client, "_get_sdk", _explode)
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-x")

    r = client.get("/api/insights/status")
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------
# Source-level: status handler does not reference execution tables
# ---------------------------------------------------------------------

def test_status_handler_does_not_reference_execution_tables():
    import inspect

    from apps.api.src.api import insights as insights_module

    src = inspect.getsource(insights_module.get_status)
    forbidden = (
        "paper_trade", "paper_position", "paper_equity_snapshot",
        "options_paper_trade", "options_paper_trade_leg",
        "decision_log", "recommendation",
        "replay_recovery_manifest",
    )
    for name in forbidden:
        assert name not in src, (
            f"get_status must not reference {name!r}"
        )
