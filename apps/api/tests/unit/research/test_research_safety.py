"""Phase 11W (Phase C) — safety helper tests."""

from __future__ import annotations

import pytest

from apps.api.src.research.safety import (
    ResearchSafetyError,
    assert_no_action_language,
    forbidden_phrases,
    forbidden_words,
    sanitize_for_display,
    validate_research_text,
)


# ---------------------------------------------------------------------------
# validate_research_text
# ---------------------------------------------------------------------------


def test_validate_empty_text_passes():
    ok, matched = validate_research_text("")
    assert ok is True
    assert matched is None


def test_validate_safe_narrative_passes():
    ok, matched = validate_research_text(
        "Narrative analysis of the firm's operating environment."
    )
    assert ok is True
    assert matched is None


@pytest.mark.parametrize("token", [
    "buy", "sell", "hold", "long", "short",
    "recommend", "recommendation", "signal",
    "allocate", "execute", "execution",
    "position", "entry", "exit", "leverage",
])
def test_validate_rejects_each_forbidden_word(token):
    body = f"The team thinks we should {token} this name now."
    ok, matched = validate_research_text(body)
    assert ok is False
    assert matched is not None
    assert token in matched


@pytest.mark.parametrize("phrase", [
    "target price", "stop loss", "stop-loss",
    "take profit", "take-profit", "portfolio manager",
    "copy trade", "copy-trade",
])
def test_validate_rejects_each_forbidden_phrase(phrase):
    body = f"Discussion mentions {phrase} as a relevant concept."
    ok, matched = validate_research_text(body)
    assert ok is False


@pytest.mark.parametrize("safe", [
    "household income trends are stable",
    "longitude of the asset basket spans EU",
    "shortlist of candidate tickers worth research",
    "the longshoreman strike disrupted shipping",
])
def test_validate_allows_substring_falsepositives(safe):
    ok, matched = validate_research_text(safe)
    assert ok is True, f"unexpectedly matched {matched!r} in {safe!r}"


# ---------------------------------------------------------------------------
# assert_no_action_language
# ---------------------------------------------------------------------------


def test_assert_passes_for_safe_text():
    assert_no_action_language("Pure narrative analysis text.")


def test_assert_raises_for_forbidden_word():
    with pytest.raises(ResearchSafetyError) as excinfo:
        assert_no_action_language("we recommend exiting this name")
    assert "recommend" in str(excinfo.value).lower()


def test_assert_raises_for_forbidden_phrase():
    with pytest.raises(ResearchSafetyError):
        assert_no_action_language("set a stop loss at 95")


def test_assert_passes_for_empty_text():
    # Empty text is a separate concern (NOT NULL at DB layer).
    assert_no_action_language("")


# ---------------------------------------------------------------------------
# sanitize_for_display
# ---------------------------------------------------------------------------


def test_sanitize_passes_safe_text_unchanged():
    out = sanitize_for_display("Narrative observation only.")
    assert out == "Narrative observation only."


def test_sanitize_replaces_unsafe_text_with_sentinel():
    out = sanitize_for_display("we recommend you buy this asset")
    assert "rejected" in out.lower()
    assert "safety check" in out.lower()
    # Critically: sentinel must NOT contain the original tokens.
    assert "buy" not in out.lower()
    assert "recommend" not in out.lower()


def test_sanitize_handles_empty_input():
    assert sanitize_for_display("") == ""


# ---------------------------------------------------------------------------
# Frozen-list accessors
# ---------------------------------------------------------------------------


def test_forbidden_words_is_tuple_and_immutable():
    words = forbidden_words()
    assert isinstance(words, tuple)
    assert "buy" in words
    assert "recommend" in words
    assert "execute" in words


def test_forbidden_phrases_includes_known_phrases():
    phrases = forbidden_phrases()
    assert "target price" in phrases
    assert "portfolio manager" in phrases
    assert "copy trade" in phrases
