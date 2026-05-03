"""Phase 10 — TradingCalendar injectable seam tests."""

from __future__ import annotations

import datetime as dt

from apps.api.src.domain.data.calendar import (
    DEFAULT_CALENDAR,
    TradingCalendar,
    WeekendOnlyCalendar,
)
from apps.api.src.domain.data.time import (
    EventTime,
    derive_tradable_date,
    next_business_day,
)


class TestWeekendOnlyCalendar:
    def test_default_is_weekend_only(self):
        assert isinstance(DEFAULT_CALENDAR, WeekendOnlyCalendar)

    def test_is_trading_day(self):
        cal = WeekendOnlyCalendar()
        assert cal.is_trading_day(dt.date(2026, 4, 21))  # Tuesday
        assert not cal.is_trading_day(dt.date(2026, 4, 25))  # Sat
        assert not cal.is_trading_day(dt.date(2026, 4, 26))  # Sun
        assert cal.is_trading_day(dt.date(2026, 4, 27))  # Mon

    def test_next_trading_day_weekday(self):
        cal = WeekendOnlyCalendar()
        assert cal.next_trading_day(dt.date(2026, 4, 21)) == dt.date(2026, 4, 22)

    def test_next_trading_day_friday_rolls_monday(self):
        cal = WeekendOnlyCalendar()
        assert cal.next_trading_day(dt.date(2026, 4, 24)) == dt.date(2026, 4, 27)


class HolidayCalendar:
    """Fake calendar with specific holidays — demonstrates seam works."""
    HOLIDAYS = {dt.date(2026, 4, 22)}

    def is_trading_day(self, d: dt.date) -> bool:
        return d.weekday() < 5 and d not in self.HOLIDAYS

    def next_trading_day(self, d: dt.date) -> dt.date:
        nxt = d + dt.timedelta(days=1)
        while not self.is_trading_day(nxt):
            nxt += dt.timedelta(days=1)
        return nxt


class TestInjectableCalendar:
    def test_custom_calendar_used_by_next_business_day(self):
        """Inject a holiday calendar → tradable_date respects holidays."""
        cal = HolidayCalendar()
        # 4/21 is Tue; 4/22 is a holiday in our fake cal -> skip to 4/23
        assert next_business_day(dt.date(2026, 4, 21), calendar=cal) == dt.date(2026, 4, 23)

    def test_custom_calendar_used_by_derive_tradable_date(self):
        cal = HolidayCalendar()
        # After-close on Tuesday + Wed is holiday -> Thursday
        got = derive_tradable_date(
            dt.date(2026, 4, 21), EventTime.AFTER_CLOSE, calendar=cal,
        )
        assert got == dt.date(2026, 4, 23)

    def test_default_calendar_preserves_phase9_behavior(self):
        """With no calendar arg, Phase 9 weekend-only semantics hold."""
        assert (
            derive_tradable_date(dt.date(2026, 4, 21), EventTime.AFTER_CLOSE)
            == dt.date(2026, 4, 22)
        )
        assert (
            derive_tradable_date(dt.date(2026, 4, 24), EventTime.AFTER_CLOSE)
            == dt.date(2026, 4, 27)
        )
