"""Phase 9 — EventTime + tradable_date unit tests."""

from __future__ import annotations

import datetime as dt

import pytest

from apps.api.src.domain.data.time import (
    EventTime,
    derive_tradable_date,
    next_business_day,
)


class TestNextBusinessDay:
    def test_weekday_to_next_weekday(self):
        # Tuesday -> Wednesday
        assert next_business_day(dt.date(2026, 4, 21)) == dt.date(2026, 4, 22)

    def test_friday_skips_weekend(self):
        # Friday -> next Monday
        assert next_business_day(dt.date(2026, 4, 24)) == dt.date(2026, 4, 27)

    def test_saturday_goes_to_monday(self):
        assert next_business_day(dt.date(2026, 4, 25)) == dt.date(2026, 4, 27)

    def test_sunday_goes_to_monday(self):
        assert next_business_day(dt.date(2026, 4, 26)) == dt.date(2026, 4, 27)


class TestDeriveTradableDate:
    def test_before_open_same_day(self):
        """BEFORE_OPEN: trader can act same day on the open."""
        d = dt.date(2026, 4, 21)
        assert derive_tradable_date(d, EventTime.BEFORE_OPEN) == d

    def test_after_close_next_business_day(self):
        d = dt.date(2026, 4, 21)   # Tuesday
        assert (
            derive_tradable_date(d, EventTime.AFTER_CLOSE) == dt.date(2026, 4, 22)
        )

    def test_after_close_friday_rolls_to_monday(self):
        d = dt.date(2026, 4, 24)   # Friday
        assert (
            derive_tradable_date(d, EventTime.AFTER_CLOSE) == dt.date(2026, 4, 27)
        )

    def test_during_hours_is_conservative_next_bd(self):
        d = dt.date(2026, 4, 21)
        assert (
            derive_tradable_date(d, EventTime.DURING_HOURS) == dt.date(2026, 4, 22)
        )

    def test_unknown_is_conservative_next_bd(self):
        """UNKNOWN must never allow same-day trading (no lookahead)."""
        d = dt.date(2026, 4, 21)
        assert (
            derive_tradable_date(d, EventTime.UNKNOWN) == dt.date(2026, 4, 22)
        )

    def test_non_enum_event_time_raises(self):
        with pytest.raises(TypeError):
            derive_tradable_date(dt.date(2026, 4, 21), "before_open")  # type: ignore
