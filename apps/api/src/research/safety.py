"""Phase 11W (Phase C) — research-text safety helpers.

Pure-fn token-blocking utilities used to validate research-artifact
text BEFORE any DB INSERT and BEFORE any UI render. Mirrors the DB
CHECK regex in `infra/alembic/versions/052_research_ro_init.py`.

Defense in depth: even if the DB CHECK is bypassed (e.g., direct
psql access), the application path runs body text through
`assert_no_action_language()` and refuses to persist. The DB CHECK
remains the authoritative final guard.

NEVER imports any execution / scoring / ML module. Verified by
`test_research_phase_c_boundaries.py`.
"""

from __future__ import annotations

import re
from typing import Final


# ---------------------------------------------------------------------------
# Forbidden token list — kept in sync with the DB CHECK regex.
# Word-boundary anchored to permit substrings like 'household',
# 'longitude', 'shortlist'.
# ---------------------------------------------------------------------------

_FORBIDDEN_WORDS: Final[tuple[str, ...]] = (
    # Action verbs
    "buy", "sell", "hold", "long", "short",
    # Recommendation family
    "recommend", "recommends", "recommended", "recommending",
    "recommendation", "recommendations",
    # Signal family
    "signal", "signals", "signaled", "signaling",
    # Allocation family
    "allocate", "allocates", "allocated", "allocating", "allocation",
    # Execution family
    "execute", "executes", "executed", "executing", "execution",
    # Position family
    "position", "positions", "entry", "exit",
    # Leverage family
    "leverage", "leveraged", "leveraging",
)

_FORBIDDEN_PHRASES: Final[tuple[str, ...]] = (
    "target price",
    "stop loss",
    "stop-loss",
    "take profit",
    "take-profit",
    "portfolio manager",
    "copy trade",
    "copy-trade",
)

# Compiled regexes (case-insensitive, word-boundary anchored).
_WORD_REGEX: Final[re.Pattern[str]] = re.compile(
    r"\b(" + "|".join(_FORBIDDEN_WORDS) + r")\b",
    re.IGNORECASE,
)
_PHRASE_REGEXES: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(re.escape(phrase).replace(r"\ ", r"\s+"),
               re.IGNORECASE)
    for phrase in _FORBIDDEN_PHRASES
)


class ResearchSafetyError(ValueError):
    """Raised when research text contains forbidden action language.

    The exception message includes the matched token for ops triage.
    Application code MUST treat this as a fail-closed condition: do
    not persist, do not render, do not retry with redaction.
    """


def validate_research_text(text: str) -> tuple[bool, str | None]:
    """Pure check. Returns (ok, matched_token_or_None).

    Empty / None text returns (True, None) — empty bodies are
    rejected at the DB layer via NOT NULL, not here.
    """
    if not text:
        return True, None
    word_match = _WORD_REGEX.search(text)
    if word_match is not None:
        return False, word_match.group(1).lower()
    for rx in _PHRASE_REGEXES:
        m = rx.search(text)
        if m is not None:
            return False, m.group(0).lower()
    return True, None


def assert_no_action_language(text: str) -> None:
    """Fail-closed guard: raises ResearchSafetyError if any forbidden
    token / phrase is present. The application path MUST call this
    before any INSERT into research_ro and before any UI serialization
    of body text."""
    ok, matched = validate_research_text(text)
    if not ok:
        raise ResearchSafetyError(
            f"forbidden action token in research text: {matched!r}"
        )


def sanitize_for_display(text: str) -> str:
    """Display-side fallback. If the text contains a forbidden token,
    replace the entire text with a standard fail-closed sentinel.
    NEVER attempts to redact only the offending substring — that would
    leak signal context. Returns the input unchanged when safe."""
    if not text:
        return ""
    ok, _ = validate_research_text(text)
    if ok:
        return text
    return "[Research note rejected — content failed safety check.]"


def forbidden_words() -> tuple[str, ...]:
    """Public accessor for the frozen forbidden-word list. Used by
    tests + CI lints to keep the DB CHECK and the Python path in
    sync."""
    return _FORBIDDEN_WORDS


def forbidden_phrases() -> tuple[str, ...]:
    """Public accessor for the frozen forbidden-phrase list."""
    return _FORBIDDEN_PHRASES
