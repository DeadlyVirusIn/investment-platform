"""Injectable trading-calendar seam.

Default implementation is WeekendOnlyCalendar (weekdays tradable, weekends
skipped — matches Phase 9 behavior exactly). A production holiday-aware
calendar can be swapped in without changing call sites.
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol


class TradingCalendar(Protocol):
    """Contract for a trading calendar. Implementations MUST be deterministic."""

    def is_trading_day(self, d: dt.date) -> bool: ...

    def next_trading_day(self, d: dt.date) -> dt.date:
        """Return the strict-next trading day after `d`."""


class WeekendOnlyCalendar:
    """Monday–Friday tradable. No holiday awareness. Default for Phase 10.

    Semantics identical to the Phase 9 `next_business_day` helper so
    Phase 10 SQL-backed repos preserve tradable_date behavior exactly.
    """

    def is_trading_day(self, d: dt.date) -> bool:
        return d.weekday() < 5

    def next_trading_day(self, d: dt.date) -> dt.date:
        nxt = d + dt.timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += dt.timedelta(days=1)
        return nxt


DEFAULT_CALENDAR: TradingCalendar = WeekendOnlyCalendar()
