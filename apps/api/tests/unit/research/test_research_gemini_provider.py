"""Phase 11W (Phase D.2) — Gemini provider adapter tests.

NO real network call. The SDK is injected via the `_sdk`
constructor argument; tests pass a `FakeGenAI` module that returns
fixed responses. Boundary checks ensure the production import path
is lazy.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Any

import pytest

from apps.api.src.research.provider_base import ProviderError, ProviderResult
from apps.api.src.research.providers.gemini_provider import (
    CHARS_PER_TOKEN,
    GEMINI_MODEL_ID,
    GEMINI_MODEL_VERSION,
    GeminiResearchProvider,
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
# Fake SDK injected via constructor — covers happy + failure paths
# without touching the network.
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
    def __init__(self, response: _FakeResponse | Exception):
        self._response = response
        self.last_kwargs: dict[str, Any] = {}

    def generate_content(self, prompt, **kwargs):
        self.last_kwargs = {"prompt": prompt, **kwargs}
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _FakeGenAI:
    """Mimics the slice of google.generativeai we touch."""

    def __init__(self, response):
        self._response = response
        self.configured_with: str | None = None
        self.last_model: _FakeModel | None = None

    def configure(self, *, api_key: str) -> None:
        self.configured_with = api_key

    def GenerativeModel(self, model_id: str) -> _FakeModel:
        self.last_model = _FakeModel(self._response)
        return self.last_model


# ---------------------------------------------------------------------------
# Constructor invariants
# ---------------------------------------------------------------------------


def test_constructor_rejects_empty_api_key():
    with pytest.raises(ProviderError):
        GeminiResearchProvider(
            api_key="", timeout_seconds=20, max_output_tokens=500,
        )


def test_constructor_rejects_zero_timeout():
    with pytest.raises(ProviderError):
        GeminiResearchProvider(
            api_key="k", timeout_seconds=0, max_output_tokens=500,
        )


def test_constructor_rejects_zero_max_output_tokens():
    with pytest.raises(ProviderError):
        GeminiResearchProvider(
            api_key="k", timeout_seconds=20, max_output_tokens=0,
        )


def test_constructor_accepts_valid_args():
    p = GeminiResearchProvider(
        api_key="k", timeout_seconds=20, max_output_tokens=500,
    )
    assert p.name == "gemini"


# ---------------------------------------------------------------------------
# Cost estimation (pure-fn)
# ---------------------------------------------------------------------------


def test_estimate_cost_uses_min_tokens_floor_for_short_prompts():
    # Prompt of 10 chars → 2 tokens raw, but floor at MIN_PROMPT_TOKENS.
    cost = estimate_cost_usd(
        rendered_prompt="hi", max_output_tokens=500,
    )
    expected_in = MIN_PROMPT_TOKENS  # 100
    expected = (
        (expected_in / 1_000_000) * INPUT_COST_PER_MTOK_USD
        + (500 / 1_000_000) * OUTPUT_COST_PER_MTOK_USD
    )
    assert abs(cost - expected) < 1e-9


def test_estimate_cost_scales_with_long_prompt():
    long_prompt = "x" * 8000  # → 2000 tokens
    cost = estimate_cost_usd(
        rendered_prompt=long_prompt, max_output_tokens=500,
    )
    expected_in = 8000 // CHARS_PER_TOKEN  # 2000
    expected = (
        (expected_in / 1_000_000) * INPUT_COST_PER_MTOK_USD
        + (500 / 1_000_000) * OUTPUT_COST_PER_MTOK_USD
    )
    assert abs(cost - expected) < 1e-9


def test_estimate_cost_rejects_empty_prompt():
    with pytest.raises(ProviderError):
        estimate_cost_usd(
            rendered_prompt="", max_output_tokens=500,
        )


def test_estimate_cost_rejects_zero_max_output_tokens():
    with pytest.raises(ProviderError):
        estimate_cost_usd(
            rendered_prompt="ok", max_output_tokens=0,
        )


def test_estimate_cost_constants_are_frozen():
    # If anyone bumps these constants, downstream cost-cap math
    # breaks silently. Test pins them.
    assert GEMINI_MODEL_ID == "gemini-2.5-flash"
    assert GEMINI_MODEL_VERSION == "stable-2026-04"
    assert INPUT_COST_PER_MTOK_USD == 0.10
    assert OUTPUT_COST_PER_MTOK_USD == 0.40
    assert CHARS_PER_TOKEN == 4
    assert MIN_PROMPT_TOKENS == 100


# ---------------------------------------------------------------------------
# generate() — happy path with injected fake SDK
# ---------------------------------------------------------------------------


def test_generate_returns_provider_result_for_safe_response():
    fake = _FakeGenAI(
        response=_FakeResponse(
            text=SAFE_NEUTRAL_BODY,
            usage_metadata=_FakeUsage(
                prompt_token_count=120,
                candidates_token_count=42,
            ),
        ),
    )
    p = GeminiResearchProvider(
        api_key="k", timeout_seconds=20,
        max_output_tokens=500, _sdk=fake,
    )
    out = p.generate("hello prompt", {"k": "v"})
    assert isinstance(out, ProviderResult)
    assert out.body == SAFE_NEUTRAL_BODY
    assert out.provider == "google"
    assert out.model_id == GEMINI_MODEL_ID
    assert out.model_version == GEMINI_MODEL_VERSION
    assert out.tokens_in == 120
    assert out.tokens_out == 42
    assert out.cost_usd > 0
    assert out.latency_ms >= 0
    assert len(out.raw_response_hash) == 64
    # SDK was configured with the key + a model was constructed.
    assert fake.configured_with == "k"
    assert fake.last_model is not None
    # generation_config + request_options were forwarded.
    kwargs = fake.last_model.last_kwargs
    assert kwargs["generation_config"]["max_output_tokens"] == 500
    assert kwargs["generation_config"]["temperature"] == 0.0
    assert kwargs["request_options"]["timeout"] == 20


def test_generate_falls_back_when_usage_metadata_absent():
    fake = _FakeGenAI(
        response=_FakeResponse(text=SAFE_NEUTRAL_BODY, usage_metadata=None),
    )
    p = GeminiResearchProvider(
        api_key="k", timeout_seconds=20,
        max_output_tokens=500, _sdk=fake,
    )
    out = p.generate("a prompt", {})
    assert out.tokens_in == MIN_PROMPT_TOKENS
    assert out.tokens_out >= 1


def test_generated_body_is_safe_per_validator():
    fake = _FakeGenAI(
        response=_FakeResponse(
            text=SAFE_NEUTRAL_BODY,
            usage_metadata=_FakeUsage(50, 50),
        ),
    )
    p = GeminiResearchProvider(
        api_key="k", timeout_seconds=20,
        max_output_tokens=500, _sdk=fake,
    )
    out = p.generate("p", {})
    ok, _ = validate_research_text(out.body)
    assert ok is True


# ---------------------------------------------------------------------------
# generate() — failure paths
# ---------------------------------------------------------------------------


def test_generate_empty_body_raises_provider_error():
    fake = _FakeGenAI(
        response=_FakeResponse(text="", usage_metadata=None),
    )
    p = GeminiResearchProvider(
        api_key="k", timeout_seconds=20,
        max_output_tokens=500, _sdk=fake,
    )
    with pytest.raises(ProviderError) as excinfo:
        p.generate("p", {})
    assert "empty" in str(excinfo.value).lower()


def test_generate_whitespace_only_body_raises_provider_error():
    fake = _FakeGenAI(
        response=_FakeResponse(text="   \n\t   ", usage_metadata=None),
    )
    p = GeminiResearchProvider(
        api_key="k", timeout_seconds=20,
        max_output_tokens=500, _sdk=fake,
    )
    with pytest.raises(ProviderError):
        p.generate("p", {})


def test_generate_timeout_raises_provider_error():
    fake = _FakeGenAI(response=TimeoutError("simulated timeout"))
    p = GeminiResearchProvider(
        api_key="k", timeout_seconds=20,
        max_output_tokens=500, _sdk=fake,
    )
    with pytest.raises(ProviderError) as excinfo:
        p.generate("p", {})
    assert "timed out" in str(excinfo.value).lower() or "timeout" in str(
        excinfo.value
    ).lower()


def test_generate_network_failure_raises_provider_error():
    fake = _FakeGenAI(response=RuntimeError("network unreachable"))
    p = GeminiResearchProvider(
        api_key="k", timeout_seconds=20,
        max_output_tokens=500, _sdk=fake,
    )
    with pytest.raises(ProviderError):
        p.generate("p", {})


def test_generate_rejects_empty_prompt():
    fake = _FakeGenAI(
        response=_FakeResponse(text=SAFE_NEUTRAL_BODY, usage_metadata=None),
    )
    p = GeminiResearchProvider(
        api_key="k", timeout_seconds=20,
        max_output_tokens=500, _sdk=fake,
    )
    with pytest.raises(ProviderError):
        p.generate("", {})


def test_generate_rejects_negative_token_counts_from_provider():
    fake = _FakeGenAI(
        response=_FakeResponse(
            text=SAFE_NEUTRAL_BODY,
            usage_metadata=_FakeUsage(-1, 5),
        ),
    )
    p = GeminiResearchProvider(
        api_key="k", timeout_seconds=20,
        max_output_tokens=500, _sdk=fake,
    )
    with pytest.raises(ProviderError):
        p.generate("p", {})


# ---------------------------------------------------------------------------
# Network-isolation guard
# ---------------------------------------------------------------------------


def test_generate_does_not_attempt_real_network(monkeypatch):
    """If the lazy SDK import resolves to the real google.generativeai,
    we still want to confirm tests cannot reach the network. Patch
    socket.* to raise; with a fake SDK injected, no socket call
    should happen anyway."""

    def boom(*a, **kw):
        raise AssertionError("gemini provider attempted network call")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)

    fake = _FakeGenAI(
        response=_FakeResponse(
            text=SAFE_NEUTRAL_BODY,
            usage_metadata=_FakeUsage(50, 50),
        ),
    )
    p = GeminiResearchProvider(
        api_key="k", timeout_seconds=20,
        max_output_tokens=500, _sdk=fake,
    )
    out = p.generate("p", {})
    assert out.body == SAFE_NEUTRAL_BODY


# ---------------------------------------------------------------------------
# Source-level: SDK import is lazy + no langchain/langgraph imports
# ---------------------------------------------------------------------------


def test_gemini_provider_module_does_not_eager_import_sdk():
    from pathlib import Path

    src = Path(
        "apps/api/src/research/providers/gemini_provider.py"
    ).read_text(encoding="utf-8")
    # Top-level import statements only — split off function bodies.
    top_lines = []
    for line in src.splitlines():
        # An indented line is inside a function/class.
        if line.startswith(" ") or line.startswith("\t"):
            continue
        top_lines.append(line)
    top = "\n".join(top_lines)
    assert "import google.generativeai" not in top, (
        "google.generativeai must be lazily imported inside generate()"
    )
    assert "from google.generativeai" not in top


def test_gemini_provider_no_langchain_or_langgraph():
    from pathlib import Path

    src = Path(
        "apps/api/src/research/providers/gemini_provider.py"
    ).read_text(encoding="utf-8")
    for tok in (
        "import langchain", "from langchain",
        "import langgraph", "from langgraph",
        "import anthropic", "from anthropic",
        "import openai", "from openai",
    ):
        assert tok not in src, f"Forbidden import {tok!r} in gemini provider"
