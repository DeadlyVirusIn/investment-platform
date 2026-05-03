"""FallbackChain — production-safe provider cascade.

Tries providers in priority order. Each provider raises `ProviderError` /
`StaleData` / `MissingData` to signal degradation. Chain never propagates
exceptions out; always returns a ReliableValue (possibly `missing=True`).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

from loguru import logger

from apps.api.src.data.reliability.types import ReliableValue

T = TypeVar("T")


class ProviderError(Exception):
    """Provider totally failed (network, auth, unknown symbol, etc.)."""


class StaleData(ProviderError):
    """Provider returned data but it's beyond staleness tolerance."""


class MissingData(ProviderError):
    """Provider responded but the specific field wasn't present."""


@dataclass
class ProviderResult(Generic[T]):
    value: T
    as_of: dt.datetime | None
    confidence: float = 1.0


# A provider is any callable: () -> ProviderResult[T]. The chain catches all
# errors, so providers should signal failure by raising ProviderError (or
# subclass) instead of returning None.
Provider = Callable[[], ProviderResult[T]]


class FallbackChain(Generic[T]):
    """Try providers in order until one succeeds. Always returns ReliableValue.

    Usage:
        chain = FallbackChain("10y_yield", critical=False, max_age=timedelta(days=2))
        chain.add("yahoo",   lambda: ProviderResult(yahoo_fetch("^TNX"), now))
        chain.add("finnhub", lambda: ProviderResult(finnhub_fetch("TNX"), now))
        rv = chain.execute()
    """

    def __init__(
        self, name: str, *,
        critical: bool = False,
        max_age: dt.timedelta | None = None,
        stale_confidence_factor: float = 0.7,
    ):
        self.name = name
        self.critical = critical
        self.max_age = max_age
        self.stale_confidence_factor = stale_confidence_factor
        self._providers: list[tuple[str, Provider[T]]] = []

    def add(self, source: str, provider: Provider[T]) -> "FallbackChain[T]":
        self._providers.append((source, provider))
        return self

    def execute(self) -> ReliableValue[T]:
        now = dt.datetime.now(dt.timezone.utc)
        errors: list[str] = []

        for source, fn in self._providers:
            try:
                result = fn()
            except StaleData as e:
                errors.append(f"{source}:stale:{e}")
                continue
            except MissingData as e:
                errors.append(f"{source}:missing:{e}")
                continue
            except ProviderError as e:
                errors.append(f"{source}:err:{e}")
                continue
            except Exception as e:
                logger.warning(
                    "reliability: provider {} raised unexpected {} for {}",
                    source, type(e).__name__, self.name,
                )
                errors.append(f"{source}:crash:{type(e).__name__}")
                continue

            # Staleness check
            stale = False
            conf = result.confidence
            if self.max_age and result.as_of:
                age = now - result.as_of
                if age > self.max_age:
                    stale = True
                    conf = conf * self.stale_confidence_factor

            return ReliableValue(
                name=self.name,
                value=result.value,
                source=source,
                as_of=result.as_of,
                fetched_at=now,
                confidence=max(0.0, min(1.0, conf)),
                missing=False,
                stale=stale,
                error=None,
                critical=self.critical,
            )

        # Nothing worked
        logger.info(
            "reliability: all providers failed for {}: {}",
            self.name, "; ".join(errors),
        )
        return ReliableValue(
            name=self.name,
            value=None,
            source="none",
            as_of=None,
            fetched_at=now,
            confidence=0.0,
            missing=True,
            stale=False,
            error="; ".join(errors),
            critical=self.critical,
        )


def execute_many(chains: list[FallbackChain[Any]]) -> dict[str, ReliableValue[Any]]:
    """Run many chains sequentially. Returns name -> ReliableValue."""
    return {c.name: c.execute() for c in chains}
