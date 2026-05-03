"""SQL-backed EarningsRepo.

Preserves Phase 9 semantics exactly: unique (asset_id, event_date);
UPSERT on conflict; get_event returns exactly the stored row or None.
"""

from __future__ import annotations

import datetime as dt
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import EarningsEventRow
from apps.api.src.domain.data.earnings.models import EarningsEvent
from apps.api.src.domain.data.time import EventTime


def _row_to_domain(row: EarningsEventRow) -> EarningsEvent:
    return EarningsEvent(
        symbol=row.symbol,
        asset_id=row.asset_id,
        event_date=row.event_date,
        event_time=EventTime(row.event_time),
        announcement_timestamp=row.announcement_timestamp,
        announcement_timestamp_raw=row.announcement_timestamp_raw,
        fiscal_period=row.fiscal_period,
        source=row.source,
    )


class SqlEarningsRepo:
    """SQLAlchemy session-backed repo."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_event(
        self, symbol: str, event_date: dt.date,
    ) -> EarningsEvent | None:
        row = self.session.execute(
            select(EarningsEventRow).where(
                EarningsEventRow.symbol == symbol,
                EarningsEventRow.event_date == event_date,
            )
        ).scalar_one_or_none()
        return _row_to_domain(row) if row else None

    def get_events_on(self, date: dt.date) -> list[EarningsEvent]:
        rows = self.session.execute(
            select(EarningsEventRow).where(
                EarningsEventRow.event_date == date,
            )
        ).scalars().all()
        return [_row_to_domain(r) for r in rows]

    def get_events_between(
        self, start: dt.date, end: dt.date,
    ) -> list[EarningsEvent]:
        if end < start:
            raise ValueError(f"end={end} < start={start}")
        rows = self.session.execute(
            select(EarningsEventRow).where(
                EarningsEventRow.event_date >= start,
                EarningsEventRow.event_date <= end,
            )
        ).scalars().all()
        return [_row_to_domain(r) for r in rows]

    def upsert(self, event: EarningsEvent) -> None:
        if not event.symbol or not event.asset_id:
            raise ValueError("symbol and asset_id required")
        existing = self.session.execute(
            select(EarningsEventRow).where(
                EarningsEventRow.asset_id == event.asset_id,
                EarningsEventRow.event_date == event.event_date,
            )
        ).scalar_one_or_none()
        if existing is None:
            row = EarningsEventRow(
                asset_id=event.asset_id,
                symbol=event.symbol,
                event_date=event.event_date,
                event_time=event.event_time.value,
                announcement_timestamp=event.announcement_timestamp,
                announcement_timestamp_raw=event.announcement_timestamp_raw,
                fiscal_period=event.fiscal_period,
                source=event.source,
            )
            self.session.add(row)
        else:
            existing.symbol = event.symbol
            existing.event_time = event.event_time.value
            existing.announcement_timestamp = event.announcement_timestamp
            existing.announcement_timestamp_raw = event.announcement_timestamp_raw
            existing.fiscal_period = event.fiscal_period
            existing.source = event.source
        self.session.flush()

    def bulk_upsert(self, events: Iterable[EarningsEvent]) -> None:
        for e in events:
            self.upsert(e)
