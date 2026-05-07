"""Deterministic safety helpers for agent prompts.

Every helper is a pure function. No I/O, no DB, no network.
Tests assert this layer rejects: UUID leakage, forbidden
execution phrases, missing banner, fabricated numbers.
"""

from __future__ import annotations

import re
from typing import Any, Iterable


# Single canonical banner string (also exported by registry.BANNER).
# Duplicated here so safety can be tested standalone.
BANNER_TEXT = "AI research insight — not execution logic."


# Field names that always carry sensitive identifiers — redact
# verbatim regardless of the value's shape. Conservative: any
# match of these keys becomes "[redacted]".
SENSITIVE_FIELDS: tuple[str, ...] = (
    "portfolio_id", "trade_id", "position_id",
    "replay_run_id", "account_id", "user_id",
    "session_id", "asset_id", "id",
)


# Standard 8-4-4-4-12 hex UUID. Matches inside strings (e.g.,
# UUIDs embedded in reason text). Insensitive to case.
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


# Phrases that imply the model is being instructed (or has the
# authority) to act on the trading system. Detection is
# case-insensitive substring; templates and instructions must
# avoid them entirely.
FORBIDDEN_PHRASES: tuple[str, ...] = (
    "place trade",
    "execute order",
    "change threshold",
    "rebalance portfolio",
    "override guard",
    "bypass next-bar",
)


# Numeric token regex used by the hallucination check. Captures
# integers and decimals, with optional leading minus. NOT
# anchored — runs across the whole prompt narrative.
_NUMERIC_RE = re.compile(r"-?\d+(?:\.\d+)?")


# ---------------------------------------------------------------
# Scrubbers
# ---------------------------------------------------------------

def scrub_sensitive_ids(payload: Any) -> Any:
    """Return a deep copy with sensitive id fields redacted and
    UUID-shaped substrings replaced. Does not mutate input.

    * Dict keys in `SENSITIVE_FIELDS` → value becomes
      "[redacted]" regardless of original shape.
    * Other dict / list / str values are recursively scrubbed:
      strings have UUID-shaped tokens replaced by
      "[redacted-uuid]".
    * Numbers / bools / None pass through unchanged.
    """
    if isinstance(payload, dict):
        return {
            k: ("[redacted]" if k in SENSITIVE_FIELDS
                else scrub_sensitive_ids(v))
            for k, v in payload.items()
        }
    if isinstance(payload, list):
        return [scrub_sensitive_ids(x) for x in payload]
    if isinstance(payload, tuple):
        return tuple(scrub_sensitive_ids(x) for x in payload)
    if isinstance(payload, str):
        return UUID_RE.sub("[redacted-uuid]", payload)
    return payload


# ---------------------------------------------------------------
# Numeric extraction
# ---------------------------------------------------------------

def extract_numeric_facts(payload: Any) -> list[float | int]:
    """Walk the payload and return every numeric leaf in
    document order. Booleans are NOT returned (bool ⊂ int in
    Python, so the bool check must come first)."""
    out: list[float | int] = []

    def _walk(v: Any) -> None:
        if isinstance(v, dict):
            for x in v.values():
                _walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                _walk(x)
        elif isinstance(v, bool):
            return
        elif isinstance(v, (int, float)):
            out.append(v)

    _walk(payload)
    return out


# ---------------------------------------------------------------
# Validators
# ---------------------------------------------------------------

def validate_no_forbidden_terms(text: str) -> None:
    """Raise ValueError if any forbidden execution phrase appears
    in `text` (case-insensitive)."""
    low = text.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in low:
            raise ValueError(
                f"forbidden execution phrase in prompt: {phrase!r}"
            )


def assert_banner_present(text: str) -> None:
    """Raise AssertionError if the canonical banner is missing."""
    if BANNER_TEXT not in text:
        raise AssertionError(
            f"banner missing from prompt: {BANNER_TEXT!r}"
        )


def assert_no_hallucinated_numbers(
    text: str,
    payload: Any,
    *,
    allowed_constants: Iterable[float | int] = (),
) -> None:
    """Every numeric token in `text` must be either:
      - a number leaf in `payload` (any common formatting), OR
      - a member of `allowed_constants` (template-fixed values).
    Raises ValueError on any token that is not traceable.

    Date components like "2026-05-06" are NOT exempt by default;
    callers should run this check on the narrative body only,
    not on a JSON-rendered payload that contains date strings.
    """
    tokens = set(_NUMERIC_RE.findall(text))
    if not tokens:
        return
    payload_nums = extract_numeric_facts(payload)
    payload_strs: set[str] = set()
    for n in payload_nums:
        payload_strs.add(str(n))
        if isinstance(n, float):
            for fmt in ("{:.0f}", "{:.1f}", "{:.2f}", "{:.4f}",
                        "{:.6f}"):
                payload_strs.add(fmt.format(n))
            if n.is_integer():
                payload_strs.add(str(int(n)))
    allowed = {str(c) for c in allowed_constants} | payload_strs
    extra = tokens - allowed
    if extra:
        raise ValueError(
            "numeric tokens in prompt not in payload or "
            f"allowed_constants: {sorted(extra)}"
        )
