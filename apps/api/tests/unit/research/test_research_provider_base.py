"""Phase 11W (Phase D.1) — provider interface tests."""

from __future__ import annotations

import pytest

from apps.api.src.research.provider_base import (
    ProviderError,
    ProviderResult,
    ResearchProvider,
)


# ---------------------------------------------------------------------------
# ProviderResult validation (constructor enforces invariants)
# ---------------------------------------------------------------------------


def _ok_result(**override) -> dict:
    base = {
        "body": "neutral text",
        "provider": "mock",
        "model_id": "mock-v1",
        "model_version": "2026-04-30",
        "tokens_in": 10,
        "tokens_out": 5,
        "cost_usd": 0.0,
        "latency_ms": 1,
        "raw_response_hash": "deadbeef",
    }
    base.update(override)
    return base


def test_provider_result_accepts_valid_payload():
    r = ProviderResult(**_ok_result())
    assert r.provider == "mock"
    assert r.tokens_in == 10
    assert r.cost_usd == 0.0


def test_provider_result_is_frozen():
    r = ProviderResult(**_ok_result())
    with pytest.raises(Exception):
        r.body = "mutated"  # type: ignore[misc]


def test_provider_result_rejects_negative_tokens():
    with pytest.raises(ProviderError):
        ProviderResult(**_ok_result(tokens_in=-1))
    with pytest.raises(ProviderError):
        ProviderResult(**_ok_result(tokens_out=-1))


def test_provider_result_rejects_negative_cost():
    with pytest.raises(ProviderError):
        ProviderResult(**_ok_result(cost_usd=-0.01))


def test_provider_result_rejects_negative_latency():
    with pytest.raises(ProviderError):
        ProviderResult(**_ok_result(latency_ms=-1))


@pytest.mark.parametrize("field", [
    "body", "provider", "model_id", "model_version",
    "raw_response_hash",
])
def test_provider_result_rejects_empty_required_field(field):
    with pytest.raises(ProviderError):
        ProviderResult(**_ok_result(**{field: ""}))


# ---------------------------------------------------------------------------
# ResearchProvider abstract contract
# ---------------------------------------------------------------------------


def test_research_provider_is_abstract():
    with pytest.raises(TypeError):
        ResearchProvider()  # type: ignore[abstract]


def test_research_provider_subclass_must_implement_generate():
    class Incomplete(ResearchProvider):
        name = "incomplete"

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]


def test_research_provider_subclass_works_when_complete():
    class Tiny(ResearchProvider):
        name = "tiny"

        def generate(self, prompt: str, metadata: dict) -> ProviderResult:
            return ProviderResult(**_ok_result(body=prompt[:20] or "x"))

    p = Tiny()
    out = p.generate("hello world", {})
    assert isinstance(out, ProviderResult)
    assert out.body == "hello world"


# ---------------------------------------------------------------------------
# ProviderError surface
# ---------------------------------------------------------------------------


def test_provider_error_is_runtimeerror_subclass():
    assert issubclass(ProviderError, RuntimeError)
