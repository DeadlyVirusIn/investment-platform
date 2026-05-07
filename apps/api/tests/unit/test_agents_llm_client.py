"""Unit tests for agents.llm_client.

Every test injects a fake Anthropic SDK shim (`sdk=` kwarg) so no
real network call is ever made. The fake records the kwargs passed
to `Anthropic(...)` and `messages.create(...)` so we can assert the
adapter passes through the cap / timeout / model / temperature
exactly as configured.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from apps.api.src.config import settings
from apps.api.src.domain.agents import llm_client
from apps.api.src.domain.agents.registry import AgentKind, BANNER


# ---------------------------------------------------------------------
# Fake Anthropic SDK
# ---------------------------------------------------------------------

@dataclass
class _FakeBlock:
    text: str


@dataclass
class _FakeUsage:
    input_tokens: int = 100
    output_tokens: int = 50


@dataclass
class _FakeResponse:
    content: list
    usage: Any = None


class _FakeMessages:
    def __init__(self, body: str, recorder: dict):
        self._body = body
        self._recorder = recorder

    def create(self, **kwargs):
        self._recorder["create_kwargs"] = kwargs
        return _FakeResponse(
            content=[_FakeBlock(text=self._body)],
            usage=_FakeUsage(),
        )


@dataclass
class _FakeClient:
    messages: _FakeMessages


@dataclass
class _FakeSDK:
    body: str
    recorder: dict = field(default_factory=dict)

    def Anthropic(self, **kwargs):
        self.recorder["client_kwargs"] = kwargs
        return _FakeClient(messages=_FakeMessages(self.body, self.recorder))


def _sdk_with_timeout_error() -> Any:
    class _Boom:
        class messages:  # noqa: N801
            @staticmethod
            def create(**kwargs):
                raise TimeoutError("simulated timeout")

    class _SDK:
        def Anthropic(self, **kwargs):
            return _Boom()

    return _SDK()


# ---------------------------------------------------------------------
# Common fixtures
# ---------------------------------------------------------------------

@pytest.fixture
def trade_quality_payload() -> dict:
    return {
        "score": 72,
        "grade": "B",
        "thesis": "winner_trim",
        "completeness": "full",
        "components": {
            "entry": 20, "return": 22,
            "hold": 15, "exit_or_status": 25,
            "completeness": 10,
        },
        "reasons": [
            "Entry: favorable fill.",
            "Return: 4 percent realized.",
        ],
    }


@pytest.fixture(autouse=True)
def _enable_flag(monkeypatch):
    """Default each test to enabled flag + dummy key. Tests that
    want to exercise the disabled path opt out with their own
    monkeypatch."""
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_MODEL", "claude-test")
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_MAX_TOKENS", 800)
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_TIMEOUT_SECONDS", 5.0)


# ---------------------------------------------------------------------
# is_enabled / disable paths
# ---------------------------------------------------------------------

def test_is_enabled_requires_flag_and_key():
    assert llm_client.is_enabled() is True


def test_disabled_when_flag_false(monkeypatch, trade_quality_payload):
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_ENABLED", False)

    class _ExplodingSDK:
        def Anthropic(self, **kwargs):
            raise AssertionError("SDK must not be touched when flag off")

    with pytest.raises(llm_client.InsightsDisabled):
        llm_client.generate_insight(
            AgentKind.TRADE_QUALITY, trade_quality_payload,
            sdk=_ExplodingSDK(),
        )


def test_disabled_when_api_key_empty(monkeypatch, trade_quality_payload):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    with pytest.raises(llm_client.InsightsDisabled):
        llm_client.generate_insight(
            AgentKind.TRADE_QUALITY, trade_quality_payload,
        )


def test_disabled_when_api_key_whitespace(
    monkeypatch, trade_quality_payload,
):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "   ")
    with pytest.raises(llm_client.InsightsDisabled):
        llm_client.generate_insight(
            AgentKind.TRADE_QUALITY, trade_quality_payload,
        )


# ---------------------------------------------------------------------
# Param pass-through
# ---------------------------------------------------------------------

def test_max_tokens_temperature_timeout_and_model_pass_through(
    trade_quality_payload,
):
    sdk = _FakeSDK(body=(
        f"{BANNER}\nScore is 72. Solid B-grade trade."
    ))
    result = llm_client.generate_insight(
        AgentKind.TRADE_QUALITY, trade_quality_payload, sdk=sdk,
    )
    assert sdk.recorder["client_kwargs"]["timeout"] == 5.0
    assert sdk.recorder["client_kwargs"]["api_key"] == "test-key"
    create_kwargs = sdk.recorder["create_kwargs"]
    assert create_kwargs["max_tokens"] == 800
    assert create_kwargs["temperature"] == 0.0
    assert create_kwargs["model"] == "claude-test"
    # One-shot single-message call.
    assert create_kwargs["messages"][0]["role"] == "user"
    assert len(create_kwargs["messages"]) == 1
    # Result echoes configured model and source endpoint.
    assert result.model == "claude-test"
    assert result.source_endpoint.endswith("/trade-quality")


def test_lower_max_tokens_setting_is_respected(
    monkeypatch, trade_quality_payload,
):
    monkeypatch.setattr(settings, "AGENT_INSIGHTS_MAX_TOKENS", 200)
    sdk = _FakeSDK(body=f"{BANNER}\nScore is 72.")
    llm_client.generate_insight(
        AgentKind.TRADE_QUALITY, trade_quality_payload, sdk=sdk,
    )
    assert sdk.recorder["create_kwargs"]["max_tokens"] == 200


# ---------------------------------------------------------------------
# Forbidden response phrases
# ---------------------------------------------------------------------

@pytest.mark.parametrize("dangerous", [
    "Operator should buy now at 72.",
    "Sell now at next close.",
    "Execute the order immediately.",
    "Override the next-bar guard.",
    "Rebalance the portfolio toward QQQ.",
    "Increase leverage to 2x.",
])
def test_forbidden_phrase_in_response_rejected(
    dangerous, trade_quality_payload,
):
    body = f"{BANNER}\n{dangerous}"
    sdk = _FakeSDK(body=body)
    with pytest.raises(llm_client.UnsafeResponseError):
        llm_client.generate_insight(
            AgentKind.TRADE_QUALITY, trade_quality_payload, sdk=sdk,
        )


def test_forbidden_phrase_check_is_case_insensitive(
    trade_quality_payload,
):
    sdk = _FakeSDK(body=f"{BANNER}\nBUY NOW.")
    with pytest.raises(llm_client.UnsafeResponseError):
        llm_client.generate_insight(
            AgentKind.TRADE_QUALITY, trade_quality_payload, sdk=sdk,
        )


# ---------------------------------------------------------------------
# Hallucinated numeric value
# ---------------------------------------------------------------------

def test_hallucinated_number_in_response_rejected(
    trade_quality_payload,
):
    body = (
        f"{BANNER}\n"
        "The score is 999, far higher than expected."
    )
    sdk = _FakeSDK(body=body)
    with pytest.raises(llm_client.UnsafeResponseError):
        llm_client.generate_insight(
            AgentKind.TRADE_QUALITY, trade_quality_payload, sdk=sdk,
        )


def test_payload_numbers_pass_hallucination_gate(
    trade_quality_payload,
):
    body = (
        f"{BANNER}\n"
        "Score is 72. Grade is B. Hold component held at 15. "
        "Out of 100 points possible."
    )
    sdk = _FakeSDK(body=body)
    result = llm_client.generate_insight(
        AgentKind.TRADE_QUALITY, trade_quality_payload, sdk=sdk,
    )
    assert "72" in result.content_markdown
    assert "15" in result.content_markdown


# ---------------------------------------------------------------------
# Code-fence rejection
# ---------------------------------------------------------------------

def test_code_fence_in_response_rejected(trade_quality_payload):
    body = (
        f"{BANNER}\n"
        "Here is the code:\n```python\nimport os\n```\n"
    )
    sdk = _FakeSDK(body=body)
    with pytest.raises(llm_client.UnsafeResponseError):
        llm_client.generate_insight(
            AgentKind.TRADE_QUALITY, trade_quality_payload, sdk=sdk,
        )


def test_inline_backtick_is_not_a_code_fence(trade_quality_payload):
    """Single-backtick ``code`` is not a triple-backtick fence; it
    must be allowed so the model can quote field names."""
    body = (
        f"{BANNER}\n"
        "The component named `entry` scored 20."
    )
    sdk = _FakeSDK(body=body)
    result = llm_client.generate_insight(
        AgentKind.TRADE_QUALITY, trade_quality_payload, sdk=sdk,
    )
    assert "`entry`" in result.content_markdown


# ---------------------------------------------------------------------
# Banner enforcement
# ---------------------------------------------------------------------

def test_banner_prepended_when_response_missing_it(
    trade_quality_payload,
):
    body = "Score is 72. Solid B-grade trade."
    sdk = _FakeSDK(body=body)
    result = llm_client.generate_insight(
        AgentKind.TRADE_QUALITY, trade_quality_payload, sdk=sdk,
    )
    assert result.content_markdown.startswith(BANNER)


def test_banner_kept_when_response_already_contains_it(
    trade_quality_payload,
):
    body = f"{BANNER}\nScore is 72."
    sdk = _FakeSDK(body=body)
    result = llm_client.generate_insight(
        AgentKind.TRADE_QUALITY, trade_quality_payload, sdk=sdk,
    )
    # Banner appears exactly once — adapter does not duplicate.
    assert result.content_markdown.count(BANNER) == 1


# ---------------------------------------------------------------------
# Empty / transport failure
# ---------------------------------------------------------------------

def test_empty_response_body_rejected(trade_quality_payload):
    sdk = _FakeSDK(body="")
    with pytest.raises(llm_client.UnsafeResponseError):
        llm_client.generate_insight(
            AgentKind.TRADE_QUALITY, trade_quality_payload, sdk=sdk,
        )


def test_timeout_error_surfaces_as_unsafe_response(
    trade_quality_payload,
):
    with pytest.raises(llm_client.UnsafeResponseError):
        llm_client.generate_insight(
            AgentKind.TRADE_QUALITY, trade_quality_payload,
            sdk=_sdk_with_timeout_error(),
        )


def test_generic_transport_error_surfaces_as_unsafe(
    trade_quality_payload,
):
    class _Boom:
        class messages:  # noqa: N801
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("connection refused")

    class _SDK:
        def Anthropic(self, **kwargs):
            return _Boom()

    with pytest.raises(llm_client.UnsafeResponseError):
        llm_client.generate_insight(
            AgentKind.TRADE_QUALITY, trade_quality_payload, sdk=_SDK(),
        )


# ---------------------------------------------------------------------
# Input contract
# ---------------------------------------------------------------------

def test_invalid_kind_rejected(trade_quality_payload):
    sdk = _FakeSDK(body="x")
    with pytest.raises(TypeError):
        llm_client.generate_insight(
            "trade_quality", trade_quality_payload, sdk=sdk,
        )


def test_invalid_payload_type_rejected():
    sdk = _FakeSDK(body="x")
    with pytest.raises(TypeError):
        llm_client.generate_insight(
            AgentKind.TRADE_QUALITY, [1, 2, 3], sdk=sdk,
        )


# ---------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------

def test_result_shape_includes_required_fields(trade_quality_payload):
    body = f"{BANNER}\nScore is 72. Grade is B."
    sdk = _FakeSDK(body=body)
    result = llm_client.generate_insight(
        AgentKind.TRADE_QUALITY, trade_quality_payload, sdk=sdk,
    )
    assert result.kind == AgentKind.TRADE_QUALITY
    assert result.model == "claude-test"
    assert result.banner == BANNER
    assert result.content_markdown.startswith(BANNER)
    assert result.generated_at  # ISO 8601 string, non-empty.
    assert result.source_endpoint.endswith("/trade-quality")


@pytest.mark.parametrize("kind", list(AgentKind))
def test_every_kind_has_allowed_constants_table(kind):
    """Sanity: the response-side constants table covers every kind.
    Missing kinds would trigger KeyError mid-validation."""
    assert kind in llm_client._RESPONSE_ALLOWED_CONSTANTS
