"""Phase 11W (Phase D.3) — Anthropic real-LLM provider adapter.

Same discipline as the Phase D.2 Gemini adapter:
  * Default OFF — the resolver in `manual_run._resolve_provider`
    refuses to instantiate this class unless
    `RESEARCH_ANTHROPIC_ENABLED=true` AND
    `RESEARCH_ANTHROPIC_API_KEY` is non-empty.
  * Cost-cap pre-check runs in `manual_run` BEFORE `generate()` is
    called.
  * Timeout enforced via the SDK's per-call `timeout=` argument.
  * Output validated by the manual_run safety layer
    (`assert_no_action_language`) BEFORE any DB INSERT.
  * SDK is loaded LAZILY inside `generate()` so the module imports
    cleanly even when anthropic is not installed.
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
# Pricing constants. Conservative — per-Mtok rates for the smallest
# Claude Haiku tier. Bumping requires an audit + commit hash on the
# change. Frozen by `test_anthropic_pricing_constants_are_frozen`.
# ---------------------------------------------------------------------------

ANTHROPIC_DEFAULT_MODEL_ID: Final[str] = "claude-haiku-4-5"
ANTHROPIC_MODEL_VERSION: Final[str] = "stable-2026-04"
INPUT_COST_PER_MTOK_USD: Final[float] = 1.00   # $/1M input tokens
OUTPUT_COST_PER_MTOK_USD: Final[float] = 5.00  # $/1M output tokens

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


class AnthropicResearchProvider(ResearchProvider):
    """Anthropic provider. Constructor enforces required parameters;
    `generate()` lazy-imports the SDK so the module is importable
    on machines without anthropic installed."""

    name = "anthropic"
    MODEL_VERSION = ANTHROPIC_MODEL_VERSION

    def __init__(
        self,
        *,
        api_key: str,
        model_id: str,
        timeout_seconds: int,
        max_output_tokens: int,
        _sdk: Any | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError(
                "RESEARCH_ANTHROPIC_API_KEY missing or empty"
            )
        if not model_id:
            raise ProviderError("model_id must be non-empty")
        if timeout_seconds <= 0:
            raise ProviderError("timeout_seconds must be > 0")
        if max_output_tokens <= 0:
            raise ProviderError("max_output_tokens must be > 0")
        self._api_key = api_key
        self._model_id = model_id
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
        self._sdk = _sdk

    @property
    def model_id(self) -> str:
        return self._model_id

    def _get_sdk(self) -> Any:
        if self._sdk is not None:
            return self._sdk
        try:
            import anthropic  # noqa: WPS433
        except ImportError as exc:
            raise ProviderError(
                f"anthropic SDK not installed: {exc}"
            ) from exc
        return anthropic

    def generate(
        self,
        prompt: str,
        metadata: dict,
    ) -> ProviderResult:
        if not prompt:
            raise ProviderError("prompt must be non-empty")
        sdk = self._get_sdk()
        try:
            client = sdk.Anthropic(
                api_key=self._api_key,
                timeout=self._timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 — boundary
            raise ProviderError(
                f"anthropic client construction failed: {exc}"
            ) from exc

        t_start = time.monotonic()
        try:
            response = client.messages.create(
                model=self._model_id,
                max_tokens=self._max_output_tokens,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )
        except TimeoutError as exc:
            raise ProviderError(
                f"anthropic call timed out after "
                f"{self._timeout_seconds}s: {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 — fail-closed boundary
            raise ProviderError(f"anthropic call failed: {exc}") from exc
        latency_ms = max(int((time.monotonic() - t_start) * 1000), 0)

        # Anthropic SDK returns response.content = [TextBlock(text=...)]
        body = ""
        try:
            content = getattr(response, "content", None) or []
            parts: list[str] = []
            for block in content:
                txt = getattr(block, "text", None)
                if isinstance(txt, str):
                    parts.append(txt)
            body = "".join(parts).strip()
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                f"anthropic response parse failed: {exc}"
            ) from exc

        if not body:
            raise ProviderError("anthropic returned empty body")

        # Provider-reported usage if available; fall back to a
        # deterministic char-count estimate.
        tokens_in = MIN_PROMPT_TOKENS
        tokens_out = max(len(body) // CHARS_PER_TOKEN, 1)
        usage = getattr(response, "usage", None)
        if usage is not None:
            try:
                tokens_in = int(getattr(usage, "input_tokens", tokens_in))
                tokens_out = int(getattr(usage, "output_tokens", tokens_out))
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
            provider="anthropic",
            model_id=self._model_id,
            model_version=self.MODEL_VERSION,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            raw_response_hash=raw_hash,
        )
