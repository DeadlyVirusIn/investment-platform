"""Provider-agnostic adapter contract for options chain data.

Pure-fn dataclass. NEVER imports execution / V2 / equity / strategy modules.
Stdlib + dataclasses only.

Downstream code (chain ingest, feature engine, paper trading) consumes
the normalized `OptionChainQuote` shape and is provider-blind.
"""

from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal


# ---------------------------------------------------------------------------
# Normalized quote shape
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OptionChainQuote:
    """Normalized per-strike chain quote. Provider-agnostic.

    Provider adapters MUST yield this exact shape. Greeks/IV may be None
    if the provider does not supply them; the chain ingest layer fills
    them via stdlib BSM (or py_vollib if installed) before inserting
    into options_chain_snapshot.
    """
    snapshot_at_utc: datetime.datetime
    underlying: str
    expiry: datetime.date
    strike: Decimal
    option_type: str               # "CALL" | "PUT"
    option_symbol: str             # OCC
    bid: Decimal | None
    ask: Decimal | None
    mid: Decimal | None            # derived; mid = (bid+ask)/2
    last: Decimal | None           # informational only — NEVER used as fill
    volume: int | None
    open_interest: int | None
    delta: Decimal | None
    gamma: Decimal | None
    theta: Decimal | None
    vega: Decimal | None
    iv: Decimal | None
    quote_age_seconds: int
    provider: str                  # adapter name, e.g. "thetadata"
    provider_version: str | None = None
    underlying_price: Decimal | None = None    # used for Greeks fallback
    interest_rate: Decimal | None = None       # used for Greeks fallback
    dividend_yield: Decimal | None = None      # used for Greeks fallback


@dataclass(frozen=True)
class ChainSnapshotResult:
    """Output of a chain pull. Carries the normalized quotes plus
    metadata about partiality / staleness."""
    quotes: tuple[OptionChainQuote, ...]
    provider: str
    fetched_at_utc: datetime.datetime
    snapshot_at_utc: datetime.datetime
    partial: bool = False                      # provider returned partial chain
    partial_reason: str | None = None
    n_raw_quotes: int = 0                      # before any filter
    underlying_price: Decimal | None = None    # spot at snapshot time
    interest_rate: Decimal | None = None       # risk-free rate for Greeks
    dividend_yield: Decimal | None = None      # underlying div yield
    notes: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ProviderError(Exception):
    """Base provider error. Caught by ingest orchestrator → log + skip."""


class ProviderUnavailable(ProviderError):
    """Provider unreachable (HTTP 5xx, timeout, network error)."""


class PartialChainWarning(ProviderError):
    """Chain partially returned. Ingest may proceed but flags `partial=True`.

    Carries the partially-fetched ChainSnapshotResult so callers can
    use the rows that did come back without re-pulling the provider.
    """

    def __init__(self, message: str, *,
                 result: "ChainSnapshotResult | None" = None) -> None:
        super().__init__(message)
        self.result = result


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseOptionsAdapter(ABC):
    """Provider-agnostic adapter contract.

    Implementations MUST:
      * Convert provider-specific symbol → normalized OCC
      * Map provider-specific Greeks fields → standard names
      * Compute mid = (bid + ask) / 2 when not provided
      * Set quote_age_seconds from provider timestamp (REQUIRED)
      * NEVER expose provider-specific quirks downstream
      * NEVER write to any DB table
      * NEVER trigger any worker job
    """

    name: str = "base"

    @abstractmethod
    def get_chain_snapshot(
        self,
        *,
        symbol: str,
        timestamp: datetime.datetime,
    ) -> ChainSnapshotResult:
        """Return current chain snapshot for `symbol` at `timestamp`.

        Raises:
            ProviderUnavailable — provider cannot be reached
            ProviderError       — non-recoverable provider error
            PartialChainWarning — only some expirations / strikes returned
        """
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if provider responds; False otherwise.

        Pure observation; no side effects."""
        raise NotImplementedError
