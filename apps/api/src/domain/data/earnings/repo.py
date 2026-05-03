"""Earnings repository — protocol + in-memory impl.

Protocol allows multiple backends (SQL, pandas, flat-file) without
changing domain logic. InMemoryEarningsRepo is both a test fixture and
a reference implementation of the PIT semantics.
"""

from __future__ import annotations

import datetime as dt
from typing import Iterable, Protocol

from apps.api.src.domain.data.earnings.models import EarningsEvent


class EarningsRepo(Protocol):
    """Read/write contract for earnings-calendar storage."""

    def get_event(
        self, symbol: str, event_date: dt.date,
    ) -> EarningsEvent | None: ...

    def get_events_on(self, date: dt.date) -> list[EarningsEvent]: ...

    def get_events_between(
        self, start: dt.date, end: dt.date,
    ) -> list[EarningsEvent]: ...

    def upsert(self, event: EarningsEvent) -> None: ...

    def bulk_upsert(self, events: Iterable[EarningsEvent]) -> None: ...


class InMemoryEarningsRepo:
    """Deterministic reference impl.

    Storage key: (symbol, event_date). If multiple sources publish the
    same (symbol, event_date), the LATEST upsert wins — callers are
    responsible for provenance/conflict handling at the ingestion layer.
    """

    def __init__(self) -> None:
        self._by_symbol_date: dict[tuple[str, dt.date], EarningsEvent] = {}

    def get_event(
        self, symbol: str, event_date: dt.date,
    ) -> EarningsEvent | None:
        return self._by_symbol_date.get((symbol, event_date))

    def get_events_on(self, date: dt.date) -> list[EarningsEvent]:
        return [
            e for (_sym, d), e in self._by_symbol_date.items() if d == date
        ]

    def get_events_between(
        self, start: dt.date, end: dt.date,
    ) -> list[EarningsEvent]:
        if end < start:
            raise ValueError(f"end={end} < start={start}")
        return [
            e for (_sym, d), e in self._by_symbol_date.items()
            if start <= d <= end
        ]

    def upsert(self, event: EarningsEvent) -> None:
        if not event.symbol or not event.asset_id:
            raise ValueError("symbol and asset_id required")
        self._by_symbol_date[(event.symbol, event.event_date)] = event

    def bulk_upsert(self, events: Iterable[EarningsEvent]) -> None:
        for e in events:
            self.upsert(e)
