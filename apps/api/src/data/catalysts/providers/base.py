"""Provider protocol — all catalyst adapters conform."""

from __future__ import annotations

from typing import Protocol

from apps.api.src.data.catalysts.types import Headline, UpcomingEvent


class CatalystProvider(Protocol):
    """A catalyst data source. Each method may raise reliability.ProviderError."""

    name: str

    def fetch_next_event(self, symbol: str) -> UpcomingEvent | None:
        ...

    def fetch_recent_headlines(
        self, symbol: str, *, limit: int = 3,
    ) -> list[Headline]:
        ...
