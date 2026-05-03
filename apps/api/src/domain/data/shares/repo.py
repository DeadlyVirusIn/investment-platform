"""Shares-outstanding repository — protocol + in-memory impl."""

from __future__ import annotations

import datetime as dt
from typing import Iterable, Protocol

from apps.api.src.domain.data.shares.models import SharesOutstandingRecord


class SharesRepo(Protocol):
    def get_as_of(
        self, symbol: str, as_of: dt.date,
    ) -> SharesOutstandingRecord | None: ...

    def get_history(self, symbol: str) -> list[SharesOutstandingRecord]: ...

    def upsert(self, record: SharesOutstandingRecord) -> None: ...

    def bulk_upsert(self, records: Iterable[SharesOutstandingRecord]) -> None: ...


class InMemorySharesRepo:
    """PIT-correct reference impl.

    Lookup uses `filing_date <= as_of` (the trader's knowledge cutoff).
    Among eligible rows the LATEST `filing_date` wins; ties broken by
    latest `effective_date` (more recent measurement). No silent fallback.
    """

    def __init__(self) -> None:
        self._by_symbol: dict[str, list[SharesOutstandingRecord]] = {}

    def get_as_of(
        self, symbol: str, as_of: dt.date,
    ) -> SharesOutstandingRecord | None:
        records = self._by_symbol.get(symbol, [])
        eligible = [r for r in records if r.filing_date <= as_of]
        if not eligible:
            return None
        return max(eligible, key=lambda r: (r.filing_date, r.effective_date))

    def get_history(self, symbol: str) -> list[SharesOutstandingRecord]:
        return sorted(
            self._by_symbol.get(symbol, []),
            key=lambda r: (r.filing_date, r.effective_date),
        )

    def upsert(self, record: SharesOutstandingRecord) -> None:
        lst = self._by_symbol.setdefault(record.symbol, [])
        # Dedupe by (effective_date, source) — most common natural key
        lst[:] = [
            r for r in lst
            if not (
                r.effective_date == record.effective_date
                and r.source == record.source
            )
        ]
        lst.append(record)

    def bulk_upsert(self, records: Iterable[SharesOutstandingRecord]) -> None:
        for r in records:
            self.upsert(r)
