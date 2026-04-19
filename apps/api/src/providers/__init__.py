"""Provider adapter protocol and rate-limit primitives."""

from __future__ import annotations

import asyncio
import datetime
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

@dataclass
class RateLimit:
    per_day: int | None = None
    per_minute: int | None = None  # stub – not enforced in Phase 0


class TokenBucket:
    """Simple per-day token bucket.  per_minute is tracked but not enforced."""

    def __init__(self, rate_limit: RateLimit) -> None:
        self._rate_limit = rate_limit
        self._day_key: str = ""
        self._day_used: int = 0
        self._lock: asyncio.Lock = asyncio.Lock()

    def _today_key(self) -> str:
        return datetime.date.today().isoformat()

    async def acquire(self) -> None:
        """Block or raise if daily quota is exhausted."""
        async with self._lock:
            today = self._today_key()
            if today != self._day_key:
                self._day_key = today
                self._day_used = 0
            if self._rate_limit.per_day is not None and self._day_used >= self._rate_limit.per_day:
                raise RuntimeError(
                    f"Daily rate limit of {self._rate_limit.per_day} requests exceeded."
                )
            self._day_used += 1

    @property
    def daily_remaining(self) -> int | None:
        if self._rate_limit.per_day is None:
            return None
        today = self._today_key()
        if today != self._day_key:
            return self._rate_limit.per_day
        return max(0, self._rate_limit.per_day - self._day_used)


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class ProviderAdapter(Protocol):
    async def fetch_prices(
        self,
        symbol: str,
        start: datetime.date,
        end: datetime.date,
    ) -> list[dict[str, Any]]:
        """Return list of normalised price-bar dicts."""
        ...

    async def fetch_corporate_actions(
        self,
        symbol: str,
        start: datetime.date,
        end: datetime.date,
    ) -> list[dict[str, Any]]:
        ...

    async def fetch_fundamentals(self, symbol: str) -> dict[str, Any]:
        ...

    async def fetch_macro_series(
        self,
        series_id: str,
        start: datetime.date,
        end: datetime.date,
    ) -> list[dict[str, Any]]:
        ...

    async def list_symbols(self) -> list[str]:
        ...
