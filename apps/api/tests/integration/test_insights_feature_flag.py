"""Integration: feature-flag gating for /api/insights/{kind}.

This file lives in `tests/integration/` per the F2 spec but does NOT
need a database — every assertion uses TestClient + monkeypatched
settings + an injected fake SDK. It deliberately does NOT request
the `pg_session` fixture, so the integration conftest's Phase 11Z
TEST_DATABASE_URL guard never trips.

Covers:
  * Disabled flag → 503 with exact body shape.
  * Disabled when API key empty even if flag on.
  * Enabled + mocked SDK → 200.
  * Source-level absence of execution-module imports, DB writes,
    background-task hooks, and forbidden LLM-framework imports.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from apps.api.src.config import settings
from apps.api.src.db import get_session
from apps.api.src.domain.agents import llm_client
from apps.api.src.api import insights as insights_module
from apps.api.src.domain.agents.registry import BANNER


@pytest.fixture(autouse=True)
def _disable_db_cache():
    """Feature-flag tests do not need DB-backed caching. Override
    `get_session` to yield None so the F4 cache layer is a no-op."""
    from apps.api.src.main import app

    def _no_session():
        yield None

    app.dependency_overrides[get_session] = _no_session
    yield
    app.dependency_overrides.pop(get_session, None)


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
    def create(self, **kwargs):
        return _Resp(content=[_Block(text=(
            f"{BANNER}\n"
            "Score is 72. Solid B-grade trade — entry component "
            "contributed the most at 18 of 20."
        ))])


class _Client:
    messages = _Messages()


class _SDK:
    def Anthropic(self, **kwargs):
        return _Client()


# ---------------------------------------------------------------------
# Disabled paths
# ---------------------------------------------------------------------

def test_disabled_flag_returns_503_with_exact_shape(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", False)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")

    from apps.api.src.main import app
    client = TestClient(app)
    r = client.get("/api/insights/trade_quality")
    assert r.status_code == 503
    body = r.json()
    assert body["error"] == "agent insights disabled"
    # F4: response carries `cache: "disabled"` so the frontend chip
    # shows a consistent state machine without a separate flag.
    assert body["cache"] == "disabled"


def test_disabled_when_only_key_missing(monkeypatch):
    """Flag on but no key → still 503. Defends against a half-wired
    deployment where the secret was forgotten."""
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")

    from apps.api.src.main import app
    client = TestClient(app)
    r = client.get("/api/insights/trade_quality")
    assert r.status_code == 503
    body = r.json()
    assert body["error"] == "agent insights disabled"
    assert body["cache"] == "disabled"


@pytest.mark.parametrize("kind", [
    "trade_quality", "risk_commentary",
    "exit_review", "options_thesis",
])
def test_disabled_503_for_every_kind(monkeypatch, kind):
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", False)
    from apps.api.src.main import app
    client = TestClient(app)
    r = client.get(f"/api/insights/{kind}")
    assert r.status_code == 503


# ---------------------------------------------------------------------
# Enabled path
# ---------------------------------------------------------------------

def test_enabled_with_mocked_sdk_returns_200(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_MODEL", "claude-test")
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: _SDK())

    from apps.api.src.main import app
    client = TestClient(app)
    r = client.get("/api/insights/trade_quality")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["llm_enabled"] is True
    assert body["banner"] == BANNER
    assert "content_markdown" in body


def test_flag_toggle_within_session(monkeypatch):
    """Flip flag off mid-session → next call returns 503."""
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(llm_client, "_get_sdk", lambda: _SDK())

    from apps.api.src.main import app
    client = TestClient(app)

    r1 = client.get("/api/insights/trade_quality")
    assert r1.status_code == 200

    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", False)
    r2 = client.get("/api/insights/trade_quality")
    assert r2.status_code == 503


# ---------------------------------------------------------------------
# Source-level guarantees
# ---------------------------------------------------------------------

# Tokens that — if present in the F2 module sources — would break
# the read-only / no-execution / no-DB-write contract. Source
# matching is intentionally conservative; false positives are easy
# to fix by renaming locals, false negatives are not.
_FORBIDDEN_TOKENS: tuple[str, ...] = (
    # Execution paths
    "paper_trading.paper_execution",
    "paper_trading.paper_service",
    "options.paper.engine",
    "options.pending_replay",
    "scripts.run_paper_exit_cycle",
    "scripts.run_options_paper_exec",
    "submit_trade",
    "_build_legs_payload",
    "replay_recovery_manifest",
    # LLM agent frameworks NOT permitted by F2
    "import autogen",
    "from autogen",
    "import langchain",
    "from langchain",
    "finrobot",
    # Background tasks NOT permitted by F2
    "BackgroundTasks",
    # DB writes (pattern-level)
    "session.commit",
    "session.add(",
    "INSERT INTO",
    "UPDATE ",
    "DELETE FROM",
)


def test_insights_module_has_no_forbidden_tokens():
    src = inspect.getsource(insights_module)
    for tok in _FORBIDDEN_TOKENS:
        assert tok not in src, (
            f"insights.py must not reference {tok!r}"
        )


def test_llm_client_module_has_no_forbidden_tokens():
    src = inspect.getsource(llm_client)
    for tok in _FORBIDDEN_TOKENS:
        assert tok not in src, (
            f"llm_client.py must not reference {tok!r}"
        )


def test_insights_endpoint_only_writes_to_agent_insight():
    """F4 introduces a single DB dependency on the agent_insight
    cache table. Verify the endpoint does not reference any
    execution / paper / options / decision / replay table by name —
    the cache is the ONLY table this module is allowed to touch."""
    src = inspect.getsource(insights_module)
    forbidden_tables = (
        "paper_trade", "paper_position", "paper_equity_snapshot",
        "options_paper_trade", "options_paper_trade_leg",
        "decision_log", "recommendation",
        "replay_recovery_manifest",
    )
    for name in forbidden_tables:
        assert name not in src, (
            f"insights.py must not reference table {name!r}"
        )


def test_insights_endpoint_has_no_inline_sql_writes():
    """Even with cache wiring, the endpoint must NOT carry inline
    DML — all writes must go through `cache.store(...)`."""
    src = inspect.getsource(insights_module)
    for tok in ("INSERT INTO", "UPDATE ", "DELETE FROM",
                "session.commit", "session.add("):
        assert tok not in src, (
            f"insights.py must not contain inline DML: {tok!r}"
        )


def test_insights_router_only_declares_get():
    """No POST/PUT/PATCH/DELETE routes on the insights router."""
    methods_seen: set[str] = set()
    for route in insights_module.router.routes:
        methods_seen |= set(getattr(route, "methods", set()) or set())
    # `HEAD` is auto-added by FastAPI alongside GET.
    methods_seen.discard("HEAD")
    assert methods_seen == {"GET"}, (
        f"insights router must be GET-only; got {sorted(methods_seen)}"
    )
