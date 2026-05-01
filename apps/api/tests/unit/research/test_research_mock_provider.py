"""Phase 11W (Phase D.1) — mock provider tests."""

from __future__ import annotations

import socket

import pytest

from apps.api.src.research.provider_base import ProviderError
from apps.api.src.research.providers.mock_provider import (
    MockResearchProvider,
    SAFE_NEUTRAL_BODY,
    UNSAFE_BODY_FOR_TESTS,
)
from apps.api.src.research.safety import validate_research_text


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_mock_provider_is_deterministic():
    p = MockResearchProvider()
    a = p.generate("prompt-A", {"k": "v"})
    b = p.generate("prompt-A", {"k": "v"})
    assert a == b
    assert a.body == b.body
    assert a.raw_response_hash == b.raw_response_hash


def test_mock_provider_hash_changes_with_prompt():
    p = MockResearchProvider()
    a = p.generate("prompt-A", {})
    b = p.generate("prompt-B", {})
    # Same body, different raw_response_hash (hash includes prompt).
    assert a.body == b.body
    assert a.raw_response_hash != b.raw_response_hash


# ---------------------------------------------------------------------------
# Safety: returned body passes the forbidden-token validator
# ---------------------------------------------------------------------------


def test_mock_provider_safe_body_passes_safety_check():
    ok, matched = validate_research_text(SAFE_NEUTRAL_BODY)
    assert ok is True, f"SAFE_NEUTRAL_BODY matched {matched!r}"


def test_mock_provider_default_body_passes_safety_check():
    p = MockResearchProvider()
    out = p.generate("anything", {})
    ok, _ = validate_research_text(out.body)
    assert ok is True


# ---------------------------------------------------------------------------
# Provenance shape
# ---------------------------------------------------------------------------


def test_mock_provider_provides_full_provenance():
    p = MockResearchProvider()
    out = p.generate("prompt", {})
    assert out.provider == "mock"
    assert out.model_id == "research-mock-v1"
    assert out.model_version == "2026-04-30"
    assert out.tokens_in == 256
    assert out.tokens_out == 64
    assert out.cost_usd == 0.0
    assert out.latency_ms == 1
    assert out.raw_response_hash != ""
    assert len(out.raw_response_hash) == 64  # sha256 hex


# ---------------------------------------------------------------------------
# Failure mode (deterministic)
# ---------------------------------------------------------------------------


def test_mock_provider_force_failure_raises():
    p = MockResearchProvider(force_failure=True)
    with pytest.raises(ProviderError) as excinfo:
        p.generate("prompt", {})
    assert "forced failure" in str(excinfo.value).lower()


def test_mock_provider_force_failure_is_repeatable():
    p = MockResearchProvider(force_failure=True)
    with pytest.raises(ProviderError):
        p.generate("prompt-1", {})
    with pytest.raises(ProviderError):
        p.generate("prompt-2", {})


def test_mock_provider_unsafe_body_mode_returns_unsafe():
    p = MockResearchProvider(force_unsafe_body=True)
    out = p.generate("prompt", {})
    ok, matched = validate_research_text(out.body)
    assert ok is False
    assert matched is not None


def test_mock_provider_unsafe_body_constant_is_unsafe_by_design():
    ok, matched = validate_research_text(UNSAFE_BODY_FOR_TESTS)
    assert ok is False
    assert matched is not None


def test_mock_provider_force_failure_and_unsafe_mutually_exclusive():
    with pytest.raises(ProviderError):
        MockResearchProvider(
            force_failure=True, force_unsafe_body=True,
        )


# ---------------------------------------------------------------------------
# No network calls — defense in depth via socket monkeypatch
# ---------------------------------------------------------------------------


def test_mock_provider_makes_no_network_calls(monkeypatch):
    """Patch socket.socket and getaddrinfo to raise. If the mock
    attempts to connect, the test fails immediately."""

    def boom(*a, **kw):
        raise AssertionError("mock provider attempted a network call")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)

    p = MockResearchProvider()
    out = p.generate("prompt", {})
    assert out.body == SAFE_NEUTRAL_BODY


def test_mock_provider_does_not_import_llm_sdks():
    """Source-level: the mock module must not import anthropic / openai
    / langchain / langgraph / google.generativeai."""
    from pathlib import Path

    src = Path(
        "apps/api/src/research/providers/mock_provider.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "import anthropic", "from anthropic",
        "import openai", "from openai",
        "from google.generativeai",
        "import langchain", "from langchain",
        "import langgraph", "from langgraph",
    )
    for tok in forbidden:
        assert tok not in src, f"Forbidden import {tok!r} in mock provider"
