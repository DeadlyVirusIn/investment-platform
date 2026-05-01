"""Phase 11W (Phase D.2) — manual run with cost cap + gemini path.

Integration tests against the testcontainer Postgres. The Gemini
provider is invoked through a fake-SDK injection so NO real network
call is made. Cost-cap pre-check is verified to write
status='cost_exceeded' without invoking the provider at all.
"""

from __future__ import annotations

import datetime as dt
import importlib
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings as live_settings
from apps.api.src.research import manual_run as mr_module
from apps.api.src.research.manual_run import (
    run_single_asset_context_note,
)
from apps.api.src.research.providers.gemini_provider import (
    GeminiResearchProvider,
)
from apps.api.src.research.providers.mock_provider import (
    SAFE_NEUTRAL_BODY,
    UNSAFE_BODY_FOR_TESTS,
)


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Apply the research_ro migration once per module.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def research_schema(pg_engine):
    mod = importlib.import_module(
        "infra.alembic.versions.052_research_ro_init"
    )
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with pg_engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()
    yield pg_engine
    with pg_engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.downgrade()


@pytest.fixture
def session(research_schema, pg_session):
    return pg_session


# ---------------------------------------------------------------------------
# Fake Gemini SDK
# ---------------------------------------------------------------------------


@dataclass
class _FakeUsage:
    prompt_token_count: int
    candidates_token_count: int


@dataclass
class _FakeResponse:
    text: str
    usage_metadata: _FakeUsage | None


class _FakeModel:
    def __init__(self, response):
        self._response = response

    def generate_content(self, prompt, **kwargs):
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _FakeGenAI:
    def __init__(self, response):
        self._response = response

    def configure(self, *, api_key: str) -> None:
        pass

    def GenerativeModel(self, model_id: str) -> _FakeModel:
        return _FakeModel(self._response)


@pytest.fixture
def configure_gemini(monkeypatch):
    """Helper that flips the live settings to enable Gemini and
    returns a function the test can call to install a fake SDK."""

    def _setup(
        *,
        response,
        max_output_tokens: int = 500,
        max_cost_usd: float = 0.05,
    ):
        monkeypatch.setattr(
            live_settings, "RESEARCH_REAL_PROVIDER_ENABLED", True,
        )
        monkeypatch.setattr(
            live_settings, "RESEARCH_GEMINI_API_KEY", "fake-test-key",
        )
        monkeypatch.setattr(
            live_settings, "RESEARCH_PROVIDER_TIMEOUT_SECONDS", 5,
        )
        monkeypatch.setattr(
            live_settings,
            "RESEARCH_PROVIDER_MAX_OUTPUT_TOKENS",
            max_output_tokens,
        )
        monkeypatch.setattr(
            live_settings,
            "RESEARCH_PROVIDER_MAX_COST_USD",
            max_cost_usd,
        )
        # Patch the resolver to inject the fake SDK into the provider.
        original_resolver = mr_module._resolve_provider

        def patched_resolver(provider_name: str):
            if provider_name == "gemini":
                return GeminiResearchProvider(
                    api_key=live_settings.RESEARCH_GEMINI_API_KEY,
                    timeout_seconds=(
                        live_settings.RESEARCH_PROVIDER_TIMEOUT_SECONDS
                    ),
                    max_output_tokens=(
                        live_settings.RESEARCH_PROVIDER_MAX_OUTPUT_TOKENS
                    ),
                    _sdk=_FakeGenAI(response),
                )
            return original_resolver(provider_name)

        monkeypatch.setattr(
            mr_module, "_resolve_provider", patched_resolver,
        )

    return _setup


def _public_table_counts(session: Session) -> dict[str, int]:
    return {
        t: session.execute(
            text(f"SELECT count(*) FROM public.{t}")
        ).scalar_one()
        for t in ("candidate_idea", "asset", "alert")
    }


# ---------------------------------------------------------------------------
# Test 19 — provider_name='mock' behavior unchanged
# ---------------------------------------------------------------------------


def test_mock_provider_behavior_unchanged_after_d2(session):
    res = run_single_asset_context_note(
        session,
        symbol="AAPL", as_of=dt.date(2026, 4, 30),
        provider_name="mock", operator_id="op-d2-1",
    )
    assert res.status == "succeeded"
    assert res.agent_output_id is not None
    n_run = session.execute(
        text("SELECT count(*) FROM research_ro.research_run")
    ).scalar_one()
    n_out = session.execute(
        text("SELECT count(*) FROM research_ro.research_agent_output")
    ).scalar_one()
    assert n_run == 1
    assert n_out == 1


# ---------------------------------------------------------------------------
# Test 20 — gemini safe response inserts 1 + 1
# ---------------------------------------------------------------------------


def test_gemini_safe_response_inserts_one_run_and_one_output(
    session, configure_gemini,
):
    configure_gemini(
        response=_FakeResponse(
            text=SAFE_NEUTRAL_BODY,
            usage_metadata=_FakeUsage(
                prompt_token_count=120,
                candidates_token_count=42,
            ),
        ),
    )
    before = _public_table_counts(session)
    res = run_single_asset_context_note(
        session,
        symbol="MSFT", as_of=dt.date(2026, 4, 30),
        provider_name="gemini", operator_id="op-d2-2",
    )
    assert res.status == "succeeded"
    assert res.agent_output_id is not None
    after = _public_table_counts(session)
    assert before == after  # NO public table writes

    row = session.execute(
        text(
            """
            SELECT provider, model_id, status, tokens_in, tokens_out,
                   cost_usd
            FROM research_ro.research_run WHERE id = :id
            """
        ),
        {"id": res.run_id},
    ).mappings().first()
    assert row["provider"] == "google"
    assert row["model_id"] == "gemini-2.5-flash"
    assert row["status"] == "succeeded"
    assert row["tokens_in"] == 120
    assert row["tokens_out"] == 42
    assert row["cost_usd"] > 0


# ---------------------------------------------------------------------------
# Test 21 — provider error inserts 1 + 0
# ---------------------------------------------------------------------------


def test_gemini_provider_error_inserts_run_only(
    session, configure_gemini,
):
    configure_gemini(response=RuntimeError("simulated network failure"))
    res = run_single_asset_context_note(
        session,
        symbol="NVDA", as_of=dt.date(2026, 4, 30),
        provider_name="gemini", operator_id="op-d2-3",
    )
    assert res.status == "provider_error"
    assert res.agent_output_id is None

    out_count = session.execute(
        text(
            "SELECT count(*) FROM research_ro.research_agent_output "
            "WHERE run_id = :id"
        ),
        {"id": res.run_id},
    ).scalar_one()
    assert out_count == 0


def test_gemini_timeout_inserts_provider_error_only(
    session, configure_gemini,
):
    configure_gemini(response=TimeoutError("simulated timeout"))
    res = run_single_asset_context_note(
        session,
        symbol="GOOGL", as_of=dt.date(2026, 4, 30),
        provider_name="gemini", operator_id="op-d2-4",
    )
    assert res.status == "provider_error"
    assert res.agent_output_id is None
    err = session.execute(
        text(
            "SELECT error_code FROM research_ro.research_run "
            "WHERE id = :id"
        ),
        {"id": res.run_id},
    ).scalar_one()
    assert err == "provider_error"


# ---------------------------------------------------------------------------
# Test 22 — token violation inserts 1 + 0
# ---------------------------------------------------------------------------


def test_gemini_unsafe_body_inserts_token_violation_only(
    session, configure_gemini,
):
    configure_gemini(
        response=_FakeResponse(
            text=UNSAFE_BODY_FOR_TESTS,
            usage_metadata=_FakeUsage(50, 50),
        ),
    )
    res = run_single_asset_context_note(
        session,
        symbol="META", as_of=dt.date(2026, 4, 30),
        provider_name="gemini", operator_id="op-d2-5",
    )
    assert res.status == "token_violation"
    assert res.agent_output_id is None
    out_count = session.execute(
        text(
            "SELECT count(*) FROM research_ro.research_agent_output "
            "WHERE run_id = :id"
        ),
        {"id": res.run_id},
    ).scalar_one()
    assert out_count == 0


# ---------------------------------------------------------------------------
# Test 23 — cost exceeded inserts 1 + 0
# ---------------------------------------------------------------------------


def test_gemini_cost_exceeded_inserts_run_only_and_does_not_call_provider(
    session, configure_gemini,
):
    """Set a $0.000000001 cap → estimated cost will exceed it.
    The fake SDK is wired to RAISE if called — so this also proves
    the provider was never invoked (cost cap is pre-flight)."""

    class _MustNotBeCalled(Exception):
        pass

    configure_gemini(
        response=_MustNotBeCalled("provider should not be invoked"),
        max_cost_usd=0.000000001,
    )
    res = run_single_asset_context_note(
        session,
        symbol="TSLA", as_of=dt.date(2026, 4, 30),
        provider_name="gemini", operator_id="op-d2-6",
    )
    assert res.status == "cost_exceeded"
    assert res.agent_output_id is None
    row = session.execute(
        text(
            """
            SELECT status, error_code, cost_usd, model_id, provider
            FROM research_ro.research_run WHERE id = :id
            """
        ),
        {"id": res.run_id},
    ).mappings().first()
    assert row["status"] == "cost_exceeded"
    assert row["error_code"] == "cost_exceeded"
    assert row["cost_usd"] > 0  # estimated cost recorded
    assert row["model_id"] == "gemini-2.5-flash"
    assert row["provider"] == "gemini"
    out_count = session.execute(
        text(
            "SELECT count(*) FROM research_ro.research_agent_output "
            "WHERE run_id = :id"
        ),
        {"id": res.run_id},
    ).scalar_one()
    assert out_count == 0


def test_under_cap_allows_provider_call(session, configure_gemini):
    configure_gemini(
        response=_FakeResponse(
            text=SAFE_NEUTRAL_BODY,
            usage_metadata=_FakeUsage(120, 42),
        ),
        max_cost_usd=1.0,  # high cap
    )
    res = run_single_asset_context_note(
        session,
        symbol="HON", as_of=dt.date(2026, 4, 30),
        provider_name="gemini", operator_id="op-d2-7",
    )
    assert res.status == "succeeded"


# ---------------------------------------------------------------------------
# Test 13 (D.2 spec) — cost_usd persisted from estimate or usage
# ---------------------------------------------------------------------------


def test_cost_usd_from_provider_usage_when_under_cap(
    session, configure_gemini,
):
    configure_gemini(
        response=_FakeResponse(
            text=SAFE_NEUTRAL_BODY,
            usage_metadata=_FakeUsage(120, 42),
        ),
        max_cost_usd=1.0,
    )
    res = run_single_asset_context_note(
        session,
        symbol="LIN", as_of=dt.date(2026, 4, 30),
        provider_name="gemini", operator_id="op-d2-8",
    )
    cost = session.execute(
        text(
            "SELECT cost_usd FROM research_ro.research_run "
            "WHERE id = :id"
        ),
        {"id": res.run_id},
    ).scalar_one()
    # Expected from provider tokens 120 in / 42 out at frozen prices.
    expected = (
        (120 / 1_000_000) * 0.10 + (42 / 1_000_000) * 0.40
    )
    # DB stores numeric(12,6) — round to 6 decimals before compare.
    assert abs(float(cost) - expected) < 1e-6
