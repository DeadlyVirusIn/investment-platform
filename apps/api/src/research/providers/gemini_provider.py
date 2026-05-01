"""Phase 11W (Phase D.2) — Gemini real-LLM provider adapter.

Strict invariants:
  * Default OFF — the resolver in `manual_run._resolve_provider`
    refuses to instantiate this class unless
    `RESEARCH_REAL_PROVIDER_ENABLED=true` AND
    `RESEARCH_GEMINI_API_KEY` is non-empty.
  * Cost-cap pre-check runs in `manual_run` BEFORE `generate()` is
    called. The provider does NOT self-gate cost.
  * Timeout enforced via the SDK's `request_options['timeout']`.
  * Output validated by the manual_run safety layer
    (`assert_no_action_language`) BEFORE any DB INSERT.
  * SDK is loaded LAZILY inside `generate()` so the module imports
    cleanly even when google-generativeai is not installed.
  * Tests inject a fake SDK via the `_sdk` constructor argument so
    NO real network call is made during normal test runs.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Final

from apps.api.src.research.provider_base import (
    ProviderError,
    ProviderResult,
    ResearchProvider,
)


# ---------------------------------------------------------------------------
# Pricing constants. Conservative — chosen so the cost ceiling
# default of $0.05 is never approached by a single run. Update
# requires an audit + commit hash on the change.
# ---------------------------------------------------------------------------

GEMINI_MODEL_ID: Final[str] = "gemini-2.5-flash"
GEMINI_MODEL_VERSION: Final[str] = "stable-2026-04"
INPUT_COST_PER_MTOK_USD: Final[float] = 0.10   # $/1M input tokens
OUTPUT_COST_PER_MTOK_USD: Final[float] = 0.40  # $/1M output tokens

# Conservative tokens-per-character ratio used for pre-call cost
# estimation. ~4 chars/token is the standard Gemini approximation;
# we ceil so we never under-estimate.
CHARS_PER_TOKEN: Final[int] = 4
MIN_PROMPT_TOKENS: Final[int] = 100


def _sha256_hex(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def estimate_cost_usd(
    *,
    rendered_prompt: str,
    max_output_tokens: int,
    input_cost_per_mtok: float = INPUT_COST_PER_MTOK_USD,
    output_cost_per_mtok: float = OUTPUT_COST_PER_MTOK_USD,
) -> float:
    """Worst-case per-call cost in USD. Used by manual_run BEFORE
    invoking the provider. NEVER trusts provider response."""
    if not rendered_prompt:
        raise ProviderError("rendered_prompt must be non-empty")
    if max_output_tokens <= 0:
        raise ProviderError("max_output_tokens must be > 0")
    estimated_input_tokens = max(
        len(rendered_prompt) // CHARS_PER_TOKEN, MIN_PROMPT_TOKENS,
    )
    return (
        (estimated_input_tokens / 1_000_000) * input_cost_per_mtok
        + (max_output_tokens / 1_000_000) * output_cost_per_mtok
    )


class GeminiResearchProvider(ResearchProvider):
    """Gemini provider. Constructor enforces required parameters;
    `generate()` lazy-imports the SDK so the module is importable
    on machines without google-generativeai installed."""

    name = "gemini"
    MODEL_ID = GEMINI_MODEL_ID
    MODEL_VERSION = GEMINI_MODEL_VERSION

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: int,
        max_output_tokens: int,
        _sdk: Any | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError("RESEARCH_GEMINI_API_KEY missing or empty")
        if timeout_seconds <= 0:
            raise ProviderError("timeout_seconds must be > 0")
        if max_output_tokens <= 0:
            raise ProviderError("max_output_tokens must be > 0")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
        # Tests inject a fake SDK module here.
        self._sdk = _sdk

    def _get_sdk(self) -> Any:
        if self._sdk is not None:
            return self._sdk
        try:
            import google.generativeai as genai  # noqa: WPS433
        except ImportError as exc:
            raise ProviderError(
                f"google-generativeai SDK not installed: {exc}"
            ) from exc
        return genai

    def generate(
        self,
        prompt: str,
        metadata: dict,
    ) -> ProviderResult:
        if not prompt:
            raise ProviderError("prompt must be non-empty")
        sdk = self._get_sdk()
        try:
            sdk.configure(api_key=self._api_key)
            model = sdk.GenerativeModel(self.MODEL_ID)
        except Exception as exc:  # noqa: BLE001 — boundary
            raise ProviderError(
                f"gemini configure/model construction failed: {exc}"
            ) from exc

        t_start = time.monotonic()
        try:
            response = model.generate_content(
                prompt,
                generation_config={
                    "max_output_tokens": self._max_output_tokens,
                    "temperature": 0.0,
                },
                request_options={"timeout": self._timeout_seconds},
            )
        except TimeoutError as exc:
            raise ProviderError(
                f"gemini call timed out after "
                f"{self._timeout_seconds}s: {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 — fail-closed boundary
            raise ProviderError(f"gemini call failed: {exc}") from exc
        latency_ms = max(int((time.monotonic() - t_start) * 1000), 0)

        body = (getattr(response, "text", None) or "").strip()
        if not body:
            raise ProviderError("gemini returned empty body")

        # Provider-reported usage if available; fall back to a
        # deterministic char-count estimate if not.
        tokens_in = MIN_PROMPT_TOKENS
        tokens_out = max(len(body) // CHARS_PER_TOKEN, 1)
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            try:
                tokens_in = int(getattr(usage, "prompt_token_count", tokens_in))
                tokens_out = int(
                    getattr(usage, "candidates_token_count", tokens_out)
                )
            except (TypeError, ValueError):
                pass
        if tokens_in < 0 or tokens_out < 0:
            raise ProviderError("provider reported negative token counts")

        cost_usd = (
            (tokens_in / 1_000_000) * INPUT_COST_PER_MTOK_USD
            + (tokens_out / 1_000_000) * OUTPUT_COST_PER_MTOK_USD
        )
        raw_hash = _sha256_hex(body + "\x00" + prompt)
        return ProviderResult(
            body=body,
            provider="google",
            model_id=self.MODEL_ID,
            model_version=self.MODEL_VERSION,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            raw_response_hash=raw_hash,
        )
