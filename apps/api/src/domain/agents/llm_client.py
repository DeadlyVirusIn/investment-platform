"""Phase F2 — minimal Anthropic Messages-API adapter for agent insights.

Hard rules:
  * Default OFF. `is_enabled()` requires both
    `AGENT_INSIGHTS_ENABLED=true` and a non-empty `ANTHROPIC_API_KEY`.
  * One-shot Messages call only. NO streaming, NO retries, NO tool
    calls, NO conversation memory, NO web access, NO code execution.
  * Pre-call safety runs through `narrator.build_prompt`, which
    enforces UUID redaction, banner presence, forbidden-term
    rejection, and hallucinated-number rejection on the prompt.
  * Post-call safety rejects forbidden response phrases, invented
    numeric values, and code fences. Banner is prepended if the LLM
    forgot to echo it. Failures raise UnsafeResponseError; the
    endpoint converts that to a safe HTTP error.
  * NO DB writes. NO persistence. NO caching. NO background tasks.
  * SDK is loaded LAZILY inside `_get_sdk()` so the module imports
    cleanly even when the `anthropic` package is not installed; tests
    inject a fake SDK via the `sdk=` keyword argument.

This module deliberately imports nothing from execution, paper-trading,
options-execution, or replay-recovery code paths. A source-level test
in `test_insights_feature_flag.py` enforces that.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from apps.api.src.config import settings
from apps.api.src.domain.agents import safety
from apps.api.src.domain.agents.narrator import build_prompt
from apps.api.src.domain.agents.registry import (
    AgentKind, BANNER, REGISTRY,
)


# ---------------------------------------------------------------------
# Post-call response safety
# ---------------------------------------------------------------------

# Phrases that imply the model is asserting trading authority. These
# are stricter than the narrator's prompt-side `FORBIDDEN_PHRASES`
# because they target *outputs* directed at the operator. Detection
# is case-insensitive substring match.
RESPONSE_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "buy now",
    "sell now",
    "execute",
    "override",
    "rebalance",
    "increase leverage",
)

# Triple-backtick fence — any presence rejected. Insight output is
# meant to be plain markdown narrative, not embedded code.
_CODE_FENCE = "```"

# Numeric constants whose appearance in the *response* is acceptable
# even if the payload doesn't list them — e.g., template-fixed
# percent bases or grade ladder thresholds. Mirrors and slightly
# loosens the narrator's `_TEMPLATE_CONSTANTS` because the LLM may
# legitimately echo "out of 100" or "0%" while summarizing.
_RESPONSE_ALLOWED_CONSTANTS: dict[AgentKind, tuple[int, ...]] = {
    AgentKind.TRADE_QUALITY: (
        100, 85, 70, 55, 40,        # grade ladder
        20, 30, 15, 25, 10,         # component caps
        0, 1,                       # sentinel values
    ),
    AgentKind.RISK_COMMENTARY: (5, 0, 1, 100),
    AgentKind.EXIT_REVIEW: (0, 1, 100),
    AgentKind.OPTIONS_THESIS: (0, 1, 100),
}


class InsightsDisabled(RuntimeError):
    """Raised when the feature flag is off, the API key is missing,
    or the SDK cannot be imported. The endpoint converts this into
    HTTP 503 `{"error": "agent insights disabled"}`."""


class UnsafeResponseError(RuntimeError):
    """Raised when the LLM response violates a safety guardrail.
    The endpoint converts this into HTTP 502 with a redacted reason
    field. NEVER returns the unsafe content."""


@dataclass(frozen=True)
class LLMResult:
    kind: AgentKind
    model: str
    content_markdown: str
    generated_at: str
    source_endpoint: str
    banner: str = BANNER


# ---------------------------------------------------------------------
# Feature-flag gate
# ---------------------------------------------------------------------

def is_enabled() -> bool:
    """Both the flag AND a non-empty API key are required. The key
    check defends against accidental enablement in environments
    where the secret was never wired."""
    if not getattr(settings, "AGENT_INSIGHTS_ENABLED", False):
        return False
    key = getattr(settings, "ANTHROPIC_API_KEY", "") or ""
    if not key.strip():
        return False
    return True


# ---------------------------------------------------------------------
# SDK loader (lazy, replaceable)
# ---------------------------------------------------------------------

def _get_sdk() -> Any:
    """Lazy import of the `anthropic` SDK. Tests monkeypatch this
    module attribute or pass `sdk=` directly to skip the import."""
    try:
        import anthropic  # noqa: WPS433  — intentional lazy import
    except ImportError as exc:
        raise InsightsDisabled(
            f"anthropic SDK not installed: {exc}"
        ) from exc
    return anthropic


def _extract_text(response: Any) -> str:
    """Best-effort extraction of textual content from a Messages
    response. Mirrors the shape used by `anthropic.types.Message`:
    `response.content` is a list of blocks; each block may carry a
    `text` attribute. Anything else is ignored — this is deliberate
    since F2 does not handle tool-use blocks."""
    content = getattr(response, "content", None) or []
    parts: list[str] = []
    for block in content:
        txt = getattr(block, "text", None)
        if isinstance(txt, str):
            parts.append(txt)
    return "".join(parts).strip()


# ---------------------------------------------------------------------
# Post-call validators
# ---------------------------------------------------------------------

def _reject_response_forbidden_phrases(text: str) -> None:
    low = text.lower()
    for phrase in RESPONSE_FORBIDDEN_PHRASES:
        if phrase in low:
            raise UnsafeResponseError(
                f"response contains forbidden phrase: {phrase!r}"
            )


def _reject_code_fence(text: str) -> None:
    if _CODE_FENCE in text:
        raise UnsafeResponseError(
            "response contains a code fence; executable code blocks "
            "are not permitted in research insights"
        )


def _validate_response(
    text: str, payload: dict, *, kind: AgentKind,
) -> None:
    """Run every post-call gate. Order matters — cheaper string
    checks first; numeric trace last. `safety.*` helpers raise
    `ValueError`; we re-wrap as `UnsafeResponseError` so the
    endpoint sees a single failure type."""
    _reject_response_forbidden_phrases(text)
    _reject_code_fence(text)
    try:
        safety.validate_no_forbidden_terms(text)
    except ValueError as exc:
        raise UnsafeResponseError(str(exc)) from exc
    try:
        safety.assert_no_hallucinated_numbers(
            text, payload,
            allowed_constants=_RESPONSE_ALLOWED_CONSTANTS[kind],
        )
    except ValueError as exc:
        raise UnsafeResponseError(str(exc)) from exc


def _ensure_banner(text: str) -> str:
    """Prepend the canonical banner if the model omitted it."""
    if BANNER in text:
        return text
    return f"{BANNER}\n\n{text}"


# ---------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------

def generate_insight(
    kind: AgentKind,
    payload: dict,
    *,
    sdk: Any | None = None,
) -> LLMResult:
    """Run a single safe LLM call and return a vetted `LLMResult`.

    Raises
    ------
    InsightsDisabled
        When the feature flag is off, the key is missing, or the SDK
        import fails. The endpoint maps this to HTTP 503.
    UnsafeResponseError
        When any post-call gate (forbidden phrase, code fence,
        hallucinated number, empty body, transport timeout, transport
        error) fires. The endpoint maps this to HTTP 502 — the
        unsafe content is NEVER returned to the caller.
    TypeError
        When `kind` or `payload` have the wrong type.
    """
    if not is_enabled():
        raise InsightsDisabled("AGENT_INSIGHTS_ENABLED is false")
    if not isinstance(kind, AgentKind):
        raise TypeError(
            f"kind must be AgentKind, got {type(kind).__name__}"
        )
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")

    meta = REGISTRY[kind]

    # Pre-call: narrator runs scrub_sensitive_ids, validate_no_
    # forbidden_terms, assert_banner_present, and assert_no_
    # hallucinated_numbers on the assembled prompt. If any of these
    # fail, build_prompt itself raises and we never touch the SDK.
    prompt = build_prompt(kind, payload)

    real_sdk = sdk if sdk is not None else _get_sdk()
    try:
        client = real_sdk.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=float(settings.AGENT_INSIGHTS_TIMEOUT_SECONDS),
        )
    except Exception as exc:  # noqa: BLE001 — boundary
        raise InsightsDisabled(
            f"anthropic client construction failed: {exc}"
        ) from exc

    try:
        response = client.messages.create(
            model=settings.AGENT_INSIGHTS_MODEL,
            max_tokens=int(settings.AGENT_INSIGHTS_MAX_TOKENS),
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
    except TimeoutError as exc:
        raise UnsafeResponseError(
            f"insight call timed out after "
            f"{settings.AGENT_INSIGHTS_TIMEOUT_SECONDS}s: {exc}"
        ) from exc
    except Exception as exc:  # noqa: BLE001 — fail-closed boundary
        raise UnsafeResponseError(f"insight call failed: {exc}") from exc

    body = _extract_text(response)
    if not body:
        raise UnsafeResponseError("empty response body")

    _validate_response(body, payload, kind=kind)
    body = _ensure_banner(body)

    return LLMResult(
        kind=kind,
        model=settings.AGENT_INSIGHTS_MODEL,
        content_markdown=body,
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        source_endpoint=meta.source_endpoint,
    )
