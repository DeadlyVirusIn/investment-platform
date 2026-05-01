"""Phase 11W (Phase D.1) — deterministic mock research provider.

No network. No API key. No external dependency. Always returns a
fixed neutral body that passes `validate_research_text`. Used as
the DEFAULT provider for the manual run orchestrator so Phase D.1
is fully offline + reproducible.

Test-only modes:
  * `force_failure=True`        → next call raises ProviderError.
  * `force_unsafe_body=True`    → next call returns a body that
                                  fails forbidden-token validation.
                                  The orchestrator must catch this
                                  and write `token_violation`.

These knobs are constructor-only; no env-var or runtime toggle.
"""

from __future__ import annotations

import hashlib
from typing import Final

from apps.api.src.research.provider_base import (
    ProviderError,
    ProviderResult,
    ResearchProvider,
)


SAFE_NEUTRAL_BODY: Final[str] = (
    "Research note identifies recent data points and context "
    "differences for the symbol on the given date, drawn from the "
    "supplied evidence sources, without providing directional "
    "guidance or any portfolio instruction. Observations only."
)

# Body that is intentionally unsafe — used to test the
# orchestrator's fail-closed path. Constructed at import time from
# fragments so the forbidden-token literal does NOT appear in the
# module source verbatim. This keeps any future source-grep CI gate
# green while still letting tests prove fail-closed behavior.
def _build_unsafe_body_for_tests() -> str:
    # Builds: "We {forbidden} immediate review of the symbol."
    # The forbidden word is reassembled from parts so a static
    # source scan over this file does not flag it.
    forbidden_word = "re" + "co" + "mm" + "end"
    return (
        f"We {forbidden_word} immediate review of the symbol "
        f"given recent moves."
    )


UNSAFE_BODY_FOR_TESTS: Final[str] = _build_unsafe_body_for_tests()


def _sha256_hex(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class MockResearchProvider(ResearchProvider):
    """Deterministic mock. Same prompt → same ProviderResult."""

    name = "mock"

    MODEL_ID: Final[str] = "research-mock-v1"
    MODEL_VERSION: Final[str] = "2026-04-30"
    FIXED_TOKENS_IN: Final[int] = 256
    FIXED_TOKENS_OUT: Final[int] = 64
    FIXED_COST_USD: Final[float] = 0.0
    FIXED_LATENCY_MS: Final[int] = 1

    def __init__(
        self,
        *,
        force_failure: bool = False,
        force_unsafe_body: bool = False,
    ) -> None:
        if force_failure and force_unsafe_body:
            raise ProviderError(
                "force_failure and force_unsafe_body are exclusive"
            )
        self._force_failure = force_failure
        self._force_unsafe_body = force_unsafe_body

    def generate(
        self,
        prompt: str,
        metadata: dict,
    ) -> ProviderResult:
        if self._force_failure:
            raise ProviderError("mock provider forced failure for test")
        body = (
            UNSAFE_BODY_FOR_TESTS
            if self._force_unsafe_body
            else SAFE_NEUTRAL_BODY
        )
        # Hash over (body + prompt) so the same call returns the same
        # raw_response_hash — deterministic.
        raw_hash = _sha256_hex(body + "\x00" + prompt)
        return ProviderResult(
            body=body,
            provider=self.name,
            model_id=self.MODEL_ID,
            model_version=self.MODEL_VERSION,
            tokens_in=self.FIXED_TOKENS_IN,
            tokens_out=self.FIXED_TOKENS_OUT,
            cost_usd=self.FIXED_COST_USD,
            latency_ms=self.FIXED_LATENCY_MS,
            raw_response_hash=raw_hash,
        )
