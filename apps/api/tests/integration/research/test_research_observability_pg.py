"""Phase 11W (Phase D.3) — observability + multi-provider integration.

Drives a mix of mock + (mocked) gemini + (mocked) anthropic runs
into research_ro, then exercises the read-only observability
helpers. Asserts metadata-only outputs, correct aggregations, and
no public-table reads/writes.
"""

from __future__ import annotations

import datetime as dt
import importlib
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import text

from apps.api.src.config import settings as live_settings
from apps.api.src.research import manual_run as mr_module
from apps.api.src.research.manual_run import run_single_asset_context_note
from apps.api.src.research.observability import (
    get_provider_comparison,
    get_provider_metrics,
    get_recent_research_provider_runs,
)
from apps.api.src.research.providers.anthropic_provider import (
    AnthropicResearchProvider,
)
from apps.api.src.research.providers.gemini_provider import (
    GeminiResearchProvider,
)
from apps.api.src.research.providers.mock_provider import (
    SAFE_NEUTRAL_BODY,
)


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def research_schema(pg_engine):
    mod_b = importlib.import_module(
        "infra.alembic.versions.052_research_ro_init"
    )
    mod_d3 = importlib.import_module(
        "infra.alembic.versions.053_research_ro_provider_idempotency"
    )
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with pg_engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod_b.upgrade()
            mod_d3.upgrade()
    yield pg_engine
    # NOTE: tests insert multiple-provider rows that share the
    # narrow (Phase B) idempotency key. Calling mod_d3.downgrade()
    # would attempt to rebuild that narrow constraint and fail with
    # a duplicate-key error. Instead drop the whole schema via
    # mod_b.downgrade() (DROP SCHEMA CASCADE) — both constraints
    # and all data go away at once.
    with pg_engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod_b.downgrade()


@pytest.fixture
def session(research_schema, pg_session):
    return pg_session


# ---------------------------------------------------------------------------
# Fake SDK helpers (Gemini + Anthropic)
# ---------------------------------------------------------------------------


@dataclass
class _GeminiUsage:
    prompt_token_count: int
    candidates_token_count: int


@dataclass
class _GeminiResponse:
    text: str
    usage_metadata: _GeminiUsage | None


class _GeminiModel:
    def __init__(self, response):
        self._response = response

    def generate_content(self, prompt, **kwargs):
        return self._response


class _GeminiSDK:
    def __init__(self, response):
        self._response = response

    def configure(self, *, api_key: str) -> None:
        pass

    def GenerativeModel(self, model_id):
        return _GeminiModel(self._response)


@dataclass
class _AnthropicUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class _AnthropicTextBlock:
    text: str


@dataclass
class _AnthropicResponse:
    content: list[_AnthropicTextBlock]
    usage: _AnthropicUsage | None


class _AnthropicMessages:
    def __init__(self, response):
        self._response = response

    def create(self, **kwargs):
        return self._response


class _AnthropicClient:
    def __init__(self, response, **kwargs):
        self.messages = _AnthropicMessages(response)


class _AnthropicSDK:
    def __init__(self, response):
        self._response = response

    def Anthropic(self, **kwargs):
        return _AnthropicClient(self._response, **kwargs)


@pytest.fixture
def configure_real_providers(monkeypatch):
    def _setup(*, gemini_response, anthropic_response):
        # Gemini gates ON
        monkeypatch.setattr(
            live_settings, "RESEARCH_REAL_PROVIDER_ENABLED", True,
        )
        monkeypatch.setattr(
            live_settings, "RESEARCH_GEMINI_API_KEY", "gemini-key",
        )
        # Anthropic gates ON
        monkeypatch.setattr(
            live_settings, "RESEARCH_ANTHROPIC_ENABLED", True,
        )
        monkeypatch.setattr(
            live_settings, "RESEARCH_ANTHROPIC_API_KEY", "anthropic-key",
        )
        monkeypatch.setattr(
            live_settings,
            "RESEARCH_ANTHROPIC_MODEL",
            "claude-haiku-4-5",
        )
        original_resolver = mr_module._resolve_provider

        def patched_resolver(provider_name: str):
            if provider_name == "gemini":
                return GeminiResearchProvider(
                    api_key="gemini-key",
                    timeout_seconds=20,
                    max_output_tokens=500,
                    _sdk=_GeminiSDK(gemini_response),
                )
            if provider_name == "anthropic":
                return AnthropicResearchProvider(
                    api_key="anthropic-key",
                    model_id="claude-haiku-4-5",
                    timeout_seconds=20,
                    max_output_tokens=500,
                    _sdk=_AnthropicSDK(anthropic_response),
                )
            return original_resolver(provider_name)

        monkeypatch.setattr(
            mr_module, "_resolve_provider", patched_resolver,
        )

    return _setup


# ---------------------------------------------------------------------------
# Drive a mix of runs across all 3 providers
# ---------------------------------------------------------------------------


def _drive_three_providers(
    session, *,
    symbol="AAPL", as_of=None,
    op_prefix="d3-mix",
    configure_real_providers=None,
):
    if as_of is None:
        as_of = dt.date(2026, 4, 30)
    configure_real_providers(
        gemini_response=_GeminiResponse(
            text=SAFE_NEUTRAL_BODY,
            usage_metadata=_GeminiUsage(
                prompt_token_count=120,
                candidates_token_count=42,
            ),
        ),
        anthropic_response=_AnthropicResponse(
            content=[_AnthropicTextBlock(text=SAFE_NEUTRAL_BODY)],
            usage=_AnthropicUsage(input_tokens=200, output_tokens=80),
        ),
    )
    out = {}
    for provider_name in ("mock", "gemini", "anthropic"):
        out[provider_name] = run_single_asset_context_note(
            session,
            symbol=symbol, as_of=as_of,
            provider_name=provider_name,
            operator_id=f"{op_prefix}-{provider_name}",
        )
    return out


# ---------------------------------------------------------------------------
# get_provider_metrics
# ---------------------------------------------------------------------------


def test_provider_metrics_aggregates_per_provider_model(
    session, configure_real_providers,
):
    results = _drive_three_providers(
        session,
        configure_real_providers=configure_real_providers,
    )
    assert all(r.status == "succeeded" for r in results.values())

    metrics = get_provider_metrics(
        session,
        start_date=dt.date(2026, 4, 1),
        end_date=dt.date(2026, 4, 30),
    )
    by_provider = {(m["provider"], m["model_id"]): m for m in metrics}
    assert ("mock", "research-mock-v1") in by_provider
    assert ("google", "gemini-2.5-flash") in by_provider
    assert ("anthropic", "claude-haiku-4-5") in by_provider

    mock_m = by_provider[("mock", "research-mock-v1")]
    assert mock_m["run_count"] == 1
    assert mock_m["succeeded_count"] == 1
    assert mock_m["failed_count"] == 0

    gemini_m = by_provider[("google", "gemini-2.5-flash")]
    assert gemini_m["run_count"] == 1
    assert gemini_m["total_tokens_in"] == 120
    assert gemini_m["total_tokens_out"] == 42
    assert gemini_m["total_cost_usd"] > 0
    assert gemini_m["avg_latency_ms"] >= 0

    anthropic_m = by_provider[("anthropic", "claude-haiku-4-5")]
    assert anthropic_m["run_count"] == 1
    assert anthropic_m["total_tokens_in"] == 200
    assert anthropic_m["total_tokens_out"] == 80
    assert anthropic_m["total_cost_usd"] > 0


def test_provider_metrics_returns_empty_when_no_rows_in_window(
    session,
):
    metrics = get_provider_metrics(
        session,
        start_date=dt.date(1999, 1, 1),
        end_date=dt.date(1999, 12, 31),
    )
    assert metrics == []


# ---------------------------------------------------------------------------
# get_provider_comparison
# ---------------------------------------------------------------------------


def test_provider_comparison_returns_metadata_only_for_symbol_as_of(
    session, configure_real_providers,
):
    _drive_three_providers(
        session,
        symbol="MSFT", as_of=dt.date(2026, 4, 29),
        configure_real_providers=configure_real_providers,
    )
    comp = get_provider_comparison(
        session, symbol="MSFT", as_of=dt.date(2026, 4, 29),
    )
    assert len(comp) == 3
    providers_seen = {row["provider"] for row in comp}
    assert providers_seen == {"mock", "google", "anthropic"}
    for row in comp:
        # Metadata-only — body text NEVER returned.
        assert "body" not in row
        assert "body_text" not in row
        # body_hash is metadata; OK.
        assert "body_hash" in row
        # Required provenance fields.
        assert row["prompt_hash"]
        assert row["input_snapshot_hash"]
        assert row["status"] == "succeeded"


def test_provider_comparison_empty_when_no_runs_for_symbol(session):
    comp = get_provider_comparison(
        session, symbol="ZZZNEVER", as_of=dt.date(2026, 4, 30),
    )
    assert comp == []


# ---------------------------------------------------------------------------
# get_recent_research_provider_runs
# ---------------------------------------------------------------------------


def test_recent_runs_returns_metadata_only(
    session, configure_real_providers,
):
    _drive_three_providers(
        session,
        symbol="NVDA", as_of=dt.date(2026, 4, 28),
        configure_real_providers=configure_real_providers,
    )
    rows = get_recent_research_provider_runs(session, limit=10)
    assert len(rows) >= 3
    for row in rows:
        # Metadata only.
        assert "body" not in row
        assert "body_text" not in row
        # Required keys.
        for key in (
            "id", "symbol", "as_of", "provider", "model_id",
            "model_version", "status", "prompt_hash",
            "input_snapshot_hash", "tokens_in", "tokens_out",
            "cost_usd", "triggered_by", "operator_id",
            "started_at",
        ):
            assert key in row, f"missing key {key!r}"


def test_recent_runs_caps_limit_at_500(session, configure_real_providers):
    """Even if caller asks for more, at most 500 rows return."""
    rows = get_recent_research_provider_runs(session, limit=10000)
    assert len(rows) <= 500


# ---------------------------------------------------------------------------
# Boundary — observability does NOT mutate the DB
# ---------------------------------------------------------------------------


def _public_table_counts(session) -> dict[str, int]:
    return {
        t: session.execute(
            text(f"SELECT count(*) FROM public.{t}")
        ).scalar_one()
        for t in ("candidate_idea", "asset", "alert")
    }


def _research_table_counts(session) -> dict[str, int]:
    return {
        t: session.execute(
            text(f"SELECT count(*) FROM research_ro.{t}")
        ).scalar_one()
        for t in ("research_run", "research_agent_output")
    }


def test_observability_calls_do_not_mutate_db(
    session, configure_real_providers,
):
    _drive_three_providers(
        session,
        symbol="VZ", as_of=dt.date(2026, 4, 27),
        op_prefix="d3-noop",
        configure_real_providers=configure_real_providers,
    )
    pub_before = _public_table_counts(session)
    res_before = _research_table_counts(session)
    # Run all three observability calls.
    get_provider_metrics(
        session,
        start_date=dt.date(2026, 4, 1),
        end_date=dt.date(2026, 4, 30),
    )
    get_provider_comparison(
        session, symbol="VZ", as_of=dt.date(2026, 4, 27),
    )
    get_recent_research_provider_runs(session, limit=50)
    pub_after = _public_table_counts(session)
    res_after = _research_table_counts(session)
    assert pub_before == pub_after
    assert res_before == res_after


# ---------------------------------------------------------------------------
# Cost cap applies to anthropic too
# ---------------------------------------------------------------------------


def test_anthropic_cost_cap_blocks_provider_call(
    session, monkeypatch,
):
    """Set $0.000000001 anthropic cap; a raising fake SDK proves
    the provider was never invoked."""
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_ENABLED", True,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_API_KEY", "key",
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_MODEL", "claude-haiku-4-5",
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_TIMEOUT_SECONDS", 5,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_MAX_OUTPUT_TOKENS", 500,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_MAX_COST_USD", 0.000000001,
    )

    class _MustNotBeCalled(Exception):
        pass

    original_resolver = mr_module._resolve_provider

    def patched_resolver(provider_name: str):
        if provider_name == "anthropic":
            return AnthropicResearchProvider(
                api_key="key",
                model_id="claude-haiku-4-5",
                timeout_seconds=5,
                max_output_tokens=500,
                _sdk=_AnthropicSDK(_MustNotBeCalled("never invoke me")),
            )
        return original_resolver(provider_name)

    monkeypatch.setattr(
        mr_module, "_resolve_provider", patched_resolver,
    )

    res = run_single_asset_context_note(
        session,
        symbol="HON", as_of=dt.date(2026, 4, 26),
        provider_name="anthropic",
        operator_id="d3-cost-cap",
    )
    assert res.status == "cost_exceeded"
    assert res.agent_output_id is None
    row = session.execute(
        text(
            """
            SELECT status, error_code, model_id, provider
            FROM research_ro.research_run WHERE id = :id
            """
        ),
        {"id": res.run_id},
    ).mappings().first()
    assert row["status"] == "cost_exceeded"
    assert row["error_code"] == "cost_exceeded"
    assert row["model_id"] == "claude-haiku-4-5"
    assert row["provider"] == "anthropic"


# ---------------------------------------------------------------------------
# Mock + Gemini behaviour unchanged from D.2
# ---------------------------------------------------------------------------


def test_mock_provider_unchanged(session):
    res = run_single_asset_context_note(
        session,
        symbol="LIN", as_of=dt.date(2026, 4, 25),
        provider_name="mock",
        operator_id="d3-mock",
    )
    assert res.status == "succeeded"
    assert res.agent_output_id is not None
