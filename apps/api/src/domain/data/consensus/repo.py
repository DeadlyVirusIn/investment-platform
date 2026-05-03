"""Consensus repository — protocol + in-memory impl.

Point-in-time rules:
  - `get_consensus(sym, event_date, metric, as_of)` returns the latest
    row with estimate_type=CONSENSUS and `as_of_date < as_of` (STRICT
    less-than). Passing `as_of=event_date` yields the pre-announcement
    consensus.
  - `get_actual(sym, event_date, metric)` returns the latest row with
    estimate_type=ACTUAL. Actuals are assumed published on/after the
    event; strict PIT callers can use `get_actual_as_of`.
"""

from __future__ import annotations

import datetime as dt
from typing import Iterable, Protocol

from apps.api.src.domain.data.consensus.models import (
    ConsensusRecord,
    EstimateType,
    Metric,
)


class ConsensusRepo(Protocol):
    def get_consensus(
        self, symbol: str, event_date: dt.date,
        metric: Metric, as_of: dt.date,
    ) -> ConsensusRecord | None: ...

    def get_actual(
        self, symbol: str, event_date: dt.date, metric: Metric,
    ) -> ConsensusRecord | None: ...

    def get_actual_as_of(
        self, symbol: str, event_date: dt.date,
        metric: Metric, as_of: dt.date,
    ) -> ConsensusRecord | None: ...

    def upsert(self, record: ConsensusRecord) -> None: ...

    def bulk_upsert(self, records: Iterable[ConsensusRecord]) -> None: ...


class InMemoryConsensusRepo:
    def __init__(self) -> None:
        self._records: list[ConsensusRecord] = []

    def get_consensus(
        self, symbol: str, event_date: dt.date,
        metric: Metric, as_of: dt.date,
    ) -> ConsensusRecord | None:
        eligible = [
            r for r in self._records
            if r.symbol == symbol
            and r.event_date == event_date
            and r.metric == metric
            and r.estimate_type == EstimateType.CONSENSUS
            and r.as_of_date < as_of     # STRICT less-than for PIT
        ]
        if not eligible:
            return None
        return max(eligible, key=lambda r: r.as_of_date)

    def get_actual(
        self, symbol: str, event_date: dt.date, metric: Metric,
    ) -> ConsensusRecord | None:
        eligible = [
            r for r in self._records
            if r.symbol == symbol
            and r.event_date == event_date
            and r.metric == metric
            and r.estimate_type == EstimateType.ACTUAL
        ]
        if not eligible:
            return None
        return max(eligible, key=lambda r: r.as_of_date)

    def get_actual_as_of(
        self, symbol: str, event_date: dt.date,
        metric: Metric, as_of: dt.date,
    ) -> ConsensusRecord | None:
        eligible = [
            r for r in self._records
            if r.symbol == symbol
            and r.event_date == event_date
            and r.metric == metric
            and r.estimate_type == EstimateType.ACTUAL
            and r.as_of_date <= as_of   # ≤ because actual at as_of is OK
        ]
        if not eligible:
            return None
        return max(eligible, key=lambda r: r.as_of_date)

    def upsert(self, record: ConsensusRecord) -> None:
        key = (
            record.symbol, record.event_date, record.metric,
            record.estimate_type, record.as_of_date, record.source,
        )
        self._records = [
            r for r in self._records
            if (
                r.symbol, r.event_date, r.metric, r.estimate_type,
                r.as_of_date, r.source,
            ) != key
        ]
        self._records.append(record)

    def bulk_upsert(self, records: Iterable[ConsensusRecord]) -> None:
        for r in records:
            self.upsert(r)
