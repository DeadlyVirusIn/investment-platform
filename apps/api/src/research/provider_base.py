"""Phase 11W (Phase D.1) — research provider interface.

Pure-fn ABC + result dataclass. No network, no DB, no LLM SDK
imports. Concrete providers live under
`apps.api.src.research.providers.*` and implement
`ResearchProvider.generate()`.

The result returned by `generate()` MUST carry full provenance:
provider, model_id, model_version, tokens_in, tokens_out, cost_usd,
latency_ms, raw_response_hash. The body is validated separately by
the manual_run orchestrator before any DB INSERT — never trust a
provider to self-validate.

Defense-in-depth: even if a provider misbehaves, the safety layer
(apps/api/src/research/safety.py) refuses to persist a body
containing forbidden tokens.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ProviderError(RuntimeError):
    """Raised by a ResearchProvider on any failure path. The
    orchestrator catches this and writes a `provider_error` row to
    research_run; no agent_output is persisted."""


@dataclass(frozen=True)
class ProviderResult:
    """Frozen, hashable carrier for a single provider call.

    All fields required. Hash equality is structural — same inputs
    + same provider must produce the same ProviderResult."""

    body: str
    provider: str
    model_id: str
    model_version: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    raw_response_hash: str

    def __post_init__(self) -> None:
        if self.tokens_in < 0 or self.tokens_out < 0:
            raise ProviderError(
                f"tokens_in / tokens_out must be >= 0, got "
                f"{self.tokens_in}/{self.tokens_out}"
            )
        if self.cost_usd < 0:
            raise ProviderError(
                f"cost_usd must be >= 0, got {self.cost_usd}"
            )
        if self.latency_ms < 0:
            raise ProviderError(
                f"latency_ms must be >= 0, got {self.latency_ms}"
            )
        for required in (
            "body", "provider", "model_id", "model_version",
            "raw_response_hash",
        ):
            if not getattr(self, required):
                raise ProviderError(
                    f"ProviderResult.{required} must be non-empty"
                )


class ResearchProvider(ABC):
    """Abstract base class for all research providers.

    Subclasses MUST be deterministic given identical (prompt,
    metadata). Real-LLM providers are NOT permitted in Phase D.1 —
    the orchestrator will only resolve `provider_name='mock'` by
    default. Future phases may register additional providers behind
    explicit env flags + cost ceilings.
    """

    name: str = "abstract"

    @abstractmethod
    def generate(
        self,
        prompt: str,
        metadata: dict,
    ) -> ProviderResult:
        """Produce a ProviderResult for the rendered prompt.

        The provider MUST raise ProviderError on any failure; it MUST
        NOT return a partial result."""
        raise NotImplementedError
