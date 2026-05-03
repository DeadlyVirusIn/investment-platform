"""Earnings domain types.

No ORM. No DB. Pure value objects. Persistence is the repo layer's job.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from apps.api.src.domain.data.time import EventTime, derive_tradable_date


@dataclass(frozen=True)
class EarningsEvent:
    """One earnings announcement, point-in-time annotated.

    Invariants (enforced at construction by callers / repos):
      - `symbol` and `asset_id` non-empty
      - `event_date` is the calendar date of the announcement (NOT the
        tradable date)
      - `event_time` classifies the announcement relative to trading hours
      - `announcement_timestamp` is an exact UTC timestamp when available;
        if missing, `event_time` remains the source of truth for tradability
      - `fiscal_period` is a free-form tag (e.g. "Q1 2026"); not used for
        join logic, kept for provenance / display
      - `source` identifies the feed (e.g. "zacks", "earnings_whispers",
        "edgar")
    """

    symbol: str
    asset_id: str
    event_date: dt.date
    event_time: EventTime
    announcement_timestamp: dt.datetime | None = None
    announcement_timestamp_raw: str | None = None   # Phase 10: feed-original
    fiscal_period: str | None = None
    source: str = ""

    @property
    def tradable_date(self) -> dt.date:
        """First business date this event can be acted on without lookahead."""
        return derive_tradable_date(self.event_date, self.event_time)
