"""Event-time semantics + tradable-date derivation.

Pure logic. No DB. No mutation. No hidden state. The trading calendar is
injectable via the `TradingCalendar` protocol in `.calendar`; default is
weekend-only to preserve Phase 9 behavior exactly.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum

from apps.api.src.domain.data.calendar import (
    DEFAULT_CALENDAR,
    TradingCalendar,
)


class EventTime(str, Enum):
    """When an earnings announcement is made relative to the trading day.

    Values map directly to how the `tradable_date` is derived.
    """
    BEFORE_OPEN = "before_open"     # pre-market  (e.g. 7:00 AM ET)
    AFTER_CLOSE = "after_close"     # post-market (e.g. 4:15 PM ET)
    DURING_HOURS = "during_hours"   # mid-session (rare; treated conservatively)
    UNKNOWN = "unknown"             # reporting time unavailable -> conservative


def next_business_day(
    d: dt.date, calendar: TradingCalendar | None = None,
) -> dt.date:
    """Return the strict-next trading day after `d`.

    Default calendar is weekend-only (matches Phase 9). Pass a
    holiday-aware calendar to tighten PIT tradability.
    """
    cal = calendar or DEFAULT_CALENDAR
    return cal.next_trading_day(d)


def derive_tradable_date(
    event_date: dt.date, event_time: EventTime,
    calendar: TradingCalendar | None = None,
) -> dt.date:
    """Return the first date on which this event can be acted on.

    BEFORE_OPEN -> event_date itself (trader can execute on the open).
    AFTER_CLOSE / DURING_HOURS / UNKNOWN -> next trading day.
    """
    if not isinstance(event_time, EventTime):
        raise TypeError(
            f"event_time must be EventTime, got {type(event_time).__name__}"
        )
    if event_time == EventTime.BEFORE_OPEN:
        return event_date
    return next_business_day(event_date, calendar=calendar)
