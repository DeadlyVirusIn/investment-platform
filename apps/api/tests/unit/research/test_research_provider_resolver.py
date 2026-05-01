"""Phase 11W (Phase D.2) — provider resolver gating tests."""

from __future__ import annotations

import pytest

from apps.api.src.config import settings as live_settings
from apps.api.src.research.manual_run import _resolve_provider
from apps.api.src.research.providers.anthropic_provider import (
    AnthropicResearchProvider,
)
from apps.api.src.research.providers.gemini_provider import (
    GeminiResearchProvider,
)
from apps.api.src.research.providers.mock_provider import (
    MockResearchProvider,
)


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch):
    """Restore Phase D.2 + D.3 defaults after each test so cross-test
    state cannot leak."""
    # Gemini (D.2)
    monkeypatch.setattr(
        live_settings, "RESEARCH_REAL_PROVIDER_ENABLED", False,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_GEMINI_API_KEY", None,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_PROVIDER_TIMEOUT_SECONDS", 20,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_PROVIDER_MAX_OUTPUT_TOKENS", 500,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_PROVIDER_MAX_COST_USD", 0.05,
    )
    # Anthropic (D.3)
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_ENABLED", False,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_API_KEY", None,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_MODEL", "claude-haiku-4-5",
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_TIMEOUT_SECONDS", 20,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_MAX_OUTPUT_TOKENS", 500,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_MAX_COST_USD", 0.05,
    )


# ---------------------------------------------------------------------------
# Defaults — flag false, key absent
# ---------------------------------------------------------------------------


def test_mock_resolves_when_real_provider_flag_false():
    p = _resolve_provider("mock")
    assert isinstance(p, MockResearchProvider)


def test_gemini_rejected_when_real_provider_flag_false(monkeypatch):
    # Even with key present, the flag MUST gate.
    monkeypatch.setattr(
        live_settings, "RESEARCH_GEMINI_API_KEY", "fake-key",
    )
    with pytest.raises(ValueError) as excinfo:
        _resolve_provider("gemini")
    assert "RESEARCH_REAL_PROVIDER_ENABLED" in str(excinfo.value)


def test_gemini_rejected_when_key_missing(monkeypatch):
    # Flag on but no key → still blocked.
    monkeypatch.setattr(
        live_settings, "RESEARCH_REAL_PROVIDER_ENABLED", True,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_GEMINI_API_KEY", None,
    )
    with pytest.raises(ValueError) as excinfo:
        _resolve_provider("gemini")
    assert "RESEARCH_GEMINI_API_KEY" in str(excinfo.value)


def test_gemini_rejected_when_key_empty_string(monkeypatch):
    monkeypatch.setattr(
        live_settings, "RESEARCH_REAL_PROVIDER_ENABLED", True,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_GEMINI_API_KEY", "",
    )
    with pytest.raises(ValueError):
        _resolve_provider("gemini")


# ---------------------------------------------------------------------------
# Happy path — flag on + key present
# ---------------------------------------------------------------------------


def test_gemini_resolves_when_flag_on_and_key_present(monkeypatch):
    monkeypatch.setattr(
        live_settings, "RESEARCH_REAL_PROVIDER_ENABLED", True,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_GEMINI_API_KEY", "real-key",
    )
    p = _resolve_provider("gemini")
    assert isinstance(p, GeminiResearchProvider)


# ---------------------------------------------------------------------------
# Unknown provider names always rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["openai", "anthropic", "claude", "gpt", "", "MOCK", "Gemini"],
)
def test_unknown_or_mistyped_names_raise(name, monkeypatch):
    # Even with the flag enabled and a key, only exact-string
    # 'mock' / 'gemini' resolve. Mistyped names fail-closed.
    monkeypatch.setattr(
        live_settings, "RESEARCH_REAL_PROVIDER_ENABLED", True,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_GEMINI_API_KEY", "k",
    )
    with pytest.raises(ValueError):
        _resolve_provider(name)


# ---------------------------------------------------------------------------
# Config defaults — frozen
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase D.3 — anthropic gating
# ---------------------------------------------------------------------------


def test_anthropic_rejected_when_anthropic_flag_false(monkeypatch):
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_API_KEY", "fake-key",
    )
    with pytest.raises(ValueError) as excinfo:
        _resolve_provider("anthropic")
    assert "RESEARCH_ANTHROPIC_ENABLED" in str(excinfo.value)


def test_anthropic_rejected_when_key_missing(monkeypatch):
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_ENABLED", True,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_API_KEY", None,
    )
    with pytest.raises(ValueError) as excinfo:
        _resolve_provider("anthropic")
    assert "RESEARCH_ANTHROPIC_API_KEY" in str(excinfo.value)


def test_anthropic_rejected_when_key_empty_string(monkeypatch):
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_ENABLED", True,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_API_KEY", "",
    )
    with pytest.raises(ValueError):
        _resolve_provider("anthropic")


def test_anthropic_resolves_when_flag_on_and_key_present(monkeypatch):
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_ENABLED", True,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_API_KEY", "real-key",
    )
    p = _resolve_provider("anthropic")
    assert isinstance(p, AnthropicResearchProvider)


def test_anthropic_independent_of_gemini_flags(monkeypatch):
    """Gemini flag MUST NOT affect anthropic gating; each provider
    has its own independent flag + key."""
    monkeypatch.setattr(
        live_settings, "RESEARCH_REAL_PROVIDER_ENABLED", True,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_GEMINI_API_KEY", "gemini-key",
    )
    # Anthropic flag still off → still blocked.
    with pytest.raises(ValueError) as excinfo:
        _resolve_provider("anthropic")
    assert "RESEARCH_ANTHROPIC_ENABLED" in str(excinfo.value)


def test_gemini_independent_of_anthropic_flags(monkeypatch):
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_ENABLED", True,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_API_KEY", "anthropic-key",
    )
    # Gemini flag still off → gemini still blocked.
    with pytest.raises(ValueError) as excinfo:
        _resolve_provider("gemini")
    assert "RESEARCH_REAL_PROVIDER_ENABLED" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Case sensitivity (D.3 spec — case-sensitive provider names)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["MOCK", "Mock", "GEMINI", "Gemini", "ANTHROPIC", "Anthropic", "AnThRoPiC"],
)
def test_provider_names_are_case_sensitive(name, monkeypatch):
    # Even with both real-provider stacks fully enabled with keys,
    # case-mismatched names must fail closed.
    monkeypatch.setattr(
        live_settings, "RESEARCH_REAL_PROVIDER_ENABLED", True,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_GEMINI_API_KEY", "k",
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_ENABLED", True,
    )
    monkeypatch.setattr(
        live_settings, "RESEARCH_ANTHROPIC_API_KEY", "k",
    )
    with pytest.raises(ValueError):
        _resolve_provider(name)


def test_real_provider_flag_default_false_in_settings_class():
    import os
    from apps.api.src.config import Settings

    saved = {
        k: os.environ.pop(k, None)
        for k in (
            "RESEARCH_REAL_PROVIDER_ENABLED",
            "RESEARCH_PROVIDER_NAME",
            "RESEARCH_GEMINI_API_KEY",
            "RESEARCH_PROVIDER_TIMEOUT_SECONDS",
            "RESEARCH_PROVIDER_MAX_OUTPUT_TOKENS",
            "RESEARCH_PROVIDER_MAX_COST_USD",
            "RESEARCH_ANTHROPIC_ENABLED",
            "RESEARCH_ANTHROPIC_API_KEY",
            "RESEARCH_ANTHROPIC_MODEL",
            "RESEARCH_ANTHROPIC_TIMEOUT_SECONDS",
            "RESEARCH_ANTHROPIC_MAX_OUTPUT_TOKENS",
            "RESEARCH_ANTHROPIC_MAX_COST_USD",
        )
    }
    try:
        s = Settings()
        assert s.RESEARCH_REAL_PROVIDER_ENABLED is False
        assert s.RESEARCH_PROVIDER_NAME == "mock"
        assert s.RESEARCH_GEMINI_API_KEY is None
        assert s.RESEARCH_PROVIDER_TIMEOUT_SECONDS == 20
        assert s.RESEARCH_PROVIDER_MAX_OUTPUT_TOKENS == 500
        assert s.RESEARCH_PROVIDER_MAX_COST_USD == 0.05
        # Phase D.3 anthropic defaults
        assert s.RESEARCH_ANTHROPIC_ENABLED is False
        assert s.RESEARCH_ANTHROPIC_API_KEY is None
        assert s.RESEARCH_ANTHROPIC_MODEL == "claude-haiku-4-5"
        assert s.RESEARCH_ANTHROPIC_TIMEOUT_SECONDS == 20
        assert s.RESEARCH_ANTHROPIC_MAX_OUTPUT_TOKENS == 500
        assert s.RESEARCH_ANTHROPIC_MAX_COST_USD == 0.05
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
