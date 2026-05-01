"""Phase 11W (Phase D.3) — Anthropic provider adapter tests.

NO real network call. SDK injected via `_sdk` constructor argument.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Any

import pytest

from apps.api.src.research.provider_base import ProviderError, ProviderResult
from apps.api.src.research.providers.anthropic_provider import (
    ANTHROPIC_DEFAULT_MODEL_ID,
    ANTHROPIC_MODEL_VERSION,
    AnthropicResearchProvider,
    CHARS_PER_TOKEN,
    INPUT_COST_PER_MTOK_USD,
    MIN_PROMPT_TOKENS,
    OUTPUT_COST_PER_MTOK_USD,
    estimate_cost_usd,
)
from apps.api.src.research.providers.mock_provider import (
    SAFE_NEUTRAL_BODY,
)
from apps.api.src.research.safety import validate_research_text


# ---------------------------------------------------------------------------
# Fake Anthropic SDK
# ---------------------------------------------------------------------------


@dataclass
class _FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class _FakeTextBlock:
    text: str


@dataclass
class _FakeResponse:
    content: list[_FakeTextBlock]
    usage: _FakeUsage | None


class _FakeMessages:
    def __init__(self, response):
        self._response = response
        self.last_kwargs: dict[str, Any] = {}

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _FakeAnthropicClient:
    def __init__(self, response, *, api_key=None, timeout=None):
        self.api_key = api_key
        self.timeout = timeout
        self.messages = _FakeMessages(response)


class _FakeAnthropicSDK:
    def __init__(self, response):
        self._response = response
        self.constructed_with: dict[str, Any] | None = None

    def Anthropic(self, **kwargs):
        self.constructed_with = kwargs
        return _FakeAnthropicClient(self._response, **kwargs)


# ---------------------------------------------------------------------------
# Constructor invariants
# ---------------------------------------------------------------------------


def test_constructor_rejects_empty_api_key():
    with pytest.raises(ProviderError):
        AnthropicResearchProvider(
            api_key="", model_id="claude-haiku-4-5",
            timeout_seconds=20, max_output_tokens=500,
        )


def test_constructor_rejects_empty_model_id():
    with pytest.raises(ProviderError):
        AnthropicResearchProvider(
            api_key="k", model_id="",
            timeout_seconds=20, max_output_tokens=500,
        )


def test_constructor_rejects_zero_timeout():
    with pytest.raises(ProviderError):
        AnthropicResearchProvider(
            api_key="k", model_id="m",
            timeout_seconds=0, max_output_tokens=500,
        )


def test_constructor_rejects_zero_max_output_tokens():
    with pytest.raises(ProviderError):
        AnthropicResearchProvider(
            api_key="k", model_id="m",
            timeout_seconds=20, max_output_tokens=0,
        )


def test_constructor_accepts_valid_args():
    p = AnthropicResearchProvider(
        api_key="k", model_id="claude-haiku-4-5",
        timeout_seconds=20, max_output_tokens=500,
    )
    assert p.name == "anthropic"
    assert p.model_id == "claude-haiku-4-5"


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------


def test_estimate_cost_floor_for_short_prompts():
    cost = estimate_cost_usd(
        rendered_prompt="hi", max_output_tokens=500,
    )
    expected = (
        (MIN_PROMPT_TOKENS / 1_000_000) * INPUT_COST_PER_MTOK_USD
        + (500 / 1_000_000) * OUTPUT_COST_PER_MTOK_USD
    )
    assert abs(cost - expected) < 1e-9


def test_estimate_cost_scales_with_long_prompt():
    long_prompt = "x" * 8000  # → 2000 tokens
    cost = estimate_cost_usd(
        rendered_prompt=long_prompt, max_output_tokens=500,
    )
    expected_in = 8000 // CHARS_PER_TOKEN
    expected = (
        (expected_in / 1_000_000) * INPUT_COST_PER_MTOK_USD
        + (500 / 1_000_000) * OUTPUT_COST_PER_MTOK_USD
    )
    assert abs(cost - expected) < 1e-9


def test_estimate_cost_rejects_empty_prompt():
    with pytest.raises(ProviderError):
        estimate_cost_usd(rendered_prompt="", max_output_tokens=500)


def test_estimate_cost_rejects_zero_max_output_tokens():
    with pytest.raises(ProviderError):
        estimate_cost_usd(rendered_prompt="ok", max_output_tokens=0)


def test_anthropic_pricing_constants_are_frozen():
    assert ANTHROPIC_DEFAULT_MODEL_ID == "claude-haiku-4-5"
    assert ANTHROPIC_MODEL_VERSION == "stable-2026-04"
    assert INPUT_COST_PER_MTOK_USD == 1.00
    assert OUTPUT_COST_PER_MTOK_USD == 5.00
    assert CHARS_PER_TOKEN == 4
    assert MIN_PROMPT_TOKENS == 100


# ---------------------------------------------------------------------------
# generate() — happy + failure paths
# ---------------------------------------------------------------------------


def _safe_response(input_tokens=120, output_tokens=42, body=SAFE_NEUTRAL_BODY):
    return _FakeResponse(
        content=[_FakeTextBlock(text=body)],
        usage=_FakeUsage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def test_generate_returns_provider_result_for_safe_response():
    fake = _FakeAnthropicSDK(response=_safe_response())
    p = AnthropicResearchProvider(
        api_key="k", model_id="claude-haiku-4-5",
        timeout_seconds=20, max_output_tokens=500, _sdk=fake,
    )
    out = p.generate("hello prompt", {"k": "v"})
    assert isinstance(out, ProviderResult)
    assert out.body == SAFE_NEUTRAL_BODY
    assert out.provider == "anthropic"
    assert out.model_id == "claude-haiku-4-5"
    assert out.model_version == ANTHROPIC_MODEL_VERSION
    assert out.tokens_in == 120
    assert out.tokens_out == 42
    assert out.cost_usd > 0
    assert out.latency_ms >= 0
    assert len(out.raw_response_hash) == 64
    assert fake.constructed_with["api_key"] == "k"
    assert fake.constructed_with["timeout"] == 20


def test_generate_falls_back_when_usage_absent():
    fake = _FakeAnthropicSDK(
        response=_FakeResponse(
            content=[_FakeTextBlock(text=SAFE_NEUTRAL_BODY)],
            usage=None,
        ),
    )
    p = AnthropicResearchProvider(
        api_key="k", model_id="m",
        timeout_seconds=20, max_output_tokens=500, _sdk=fake,
    )
    out = p.generate("p", {})
    assert out.tokens_in == MIN_PROMPT_TOKENS
    assert out.tokens_out >= 1


def test_generated_body_is_safe_per_validator():
    fake = _FakeAnthropicSDK(response=_safe_response())
    p = AnthropicResearchProvider(
        api_key="k", model_id="m",
        timeout_seconds=20, max_output_tokens=500, _sdk=fake,
    )
    out = p.generate("p", {})
    ok, _ = validate_research_text(out.body)
    assert ok is True


def test_generate_empty_body_raises_provider_error():
    fake = _FakeAnthropicSDK(
        response=_FakeResponse(content=[], usage=None),
    )
    p = AnthropicResearchProvider(
        api_key="k", model_id="m",
        timeout_seconds=20, max_output_tokens=500, _sdk=fake,
    )
    with pytest.raises(ProviderError) as excinfo:
        p.generate("p", {})
    assert "empty" in str(excinfo.value).lower()


def test_generate_whitespace_only_body_raises_provider_error():
    fake = _FakeAnthropicSDK(
        response=_FakeResponse(
            content=[_FakeTextBlock(text="   \n\t   ")],
            usage=None,
        ),
    )
    p = AnthropicResearchProvider(
        api_key="k", model_id="m",
        timeout_seconds=20, max_output_tokens=500, _sdk=fake,
    )
    with pytest.raises(ProviderError):
        p.generate("p", {})


def test_generate_timeout_raises_provider_error():
    fake = _FakeAnthropicSDK(response=TimeoutError("simulated timeout"))
    p = AnthropicResearchProvider(
        api_key="k", model_id="m",
        timeout_seconds=20, max_output_tokens=500, _sdk=fake,
    )
    with pytest.raises(ProviderError) as excinfo:
        p.generate("p", {})
    assert "timed out" in str(excinfo.value).lower() or "timeout" in str(
        excinfo.value
    ).lower()


def test_generate_network_failure_raises_provider_error():
    fake = _FakeAnthropicSDK(response=RuntimeError("network unreachable"))
    p = AnthropicResearchProvider(
        api_key="k", model_id="m",
        timeout_seconds=20, max_output_tokens=500, _sdk=fake,
    )
    with pytest.raises(ProviderError):
        p.generate("p", {})


def test_generate_rejects_empty_prompt():
    fake = _FakeAnthropicSDK(response=_safe_response())
    p = AnthropicResearchProvider(
        api_key="k", model_id="m",
        timeout_seconds=20, max_output_tokens=500, _sdk=fake,
    )
    with pytest.raises(ProviderError):
        p.generate("", {})


def test_generate_rejects_negative_token_counts():
    fake = _FakeAnthropicSDK(
        response=_FakeResponse(
            content=[_FakeTextBlock(text=SAFE_NEUTRAL_BODY)],
            usage=_FakeUsage(input_tokens=-1, output_tokens=5),
        ),
    )
    p = AnthropicResearchProvider(
        api_key="k", model_id="m",
        timeout_seconds=20, max_output_tokens=500, _sdk=fake,
    )
    with pytest.raises(ProviderError):
        p.generate("p", {})


# ---------------------------------------------------------------------------
# Network isolation guard
# ---------------------------------------------------------------------------


def test_generate_does_not_attempt_real_network(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError(
            "anthropic provider attempted a real network call"
        )

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    fake = _FakeAnthropicSDK(response=_safe_response())
    p = AnthropicResearchProvider(
        api_key="k", model_id="m",
        timeout_seconds=20, max_output_tokens=500, _sdk=fake,
    )
    out = p.generate("p", {})
    assert out.body == SAFE_NEUTRAL_BODY


# ---------------------------------------------------------------------------
# Source-level: SDK import is lazy + no langchain/langgraph imports
# ---------------------------------------------------------------------------


def test_anthropic_provider_module_does_not_eager_import_sdk():
    from pathlib import Path

    src = Path(
        "apps/api/src/research/providers/anthropic_provider.py"
    ).read_text(encoding="utf-8")
    top_lines = []
    for line in src.splitlines():
        if line.startswith(" ") or line.startswith("\t"):
            continue
        top_lines.append(line)
    top = "\n".join(top_lines)
    assert "import anthropic" not in top, (
        "anthropic SDK must be lazily imported inside generate()"
    )
    assert "from anthropic" not in top


def test_anthropic_provider_no_langchain_or_langgraph_or_other_llms():
    from pathlib import Path

    src = Path(
        "apps/api/src/research/providers/anthropic_provider.py"
    ).read_text(encoding="utf-8")
    for tok in (
        "import langchain", "from langchain",
        "import langgraph", "from langgraph",
        "import openai", "from openai",
        "from google.generativeai", "import google.generativeai",
    ):
        assert tok not in src, (
            f"Forbidden import {tok!r} in anthropic provider"
        )
