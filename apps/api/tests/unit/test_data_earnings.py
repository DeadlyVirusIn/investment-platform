"""Phase 9 — EarningsEvent + InMemoryEarningsRepo tests."""

from __future__ import annotations

import datetime as dt

import pytest

from apps.api.src.domain.data.earnings.models import EarningsEvent
from apps.api.src.domain.data.earnings.repo import InMemoryEarningsRepo
from apps.api.src.domain.data.time import EventTime


def _event(
    symbol: str = "AAPL", event_date: dt.date | None = None,
    event_time: EventTime = EventTime.AFTER_CLOSE,
    source: str = "zacks",
) -> EarningsEvent:
    return EarningsEvent(
        symbol=symbol,
        asset_id=symbol.lower() + "_id",
        event_date=event_date or dt.date(2026, 4, 21),
        event_time=event_time,
        fiscal_period="Q2 2026",
        source=source,
    )


class TestEarningsEvent:
    def test_tradable_date_before_open(self):
        e = _event(event_time=EventTime.BEFORE_OPEN)
        assert e.tradable_date == e.event_date

    def test_tradable_date_after_close(self):
        e = _event(event_date=dt.date(2026, 4, 21), event_time=EventTime.AFTER_CLOSE)
        assert e.tradable_date == dt.date(2026, 4, 22)


class TestInMemoryRepo:
    def test_upsert_and_get_event(self):
        r = InMemoryEarningsRepo()
        e = _event()
        r.upsert(e)
        assert r.get_event("AAPL", dt.date(2026, 4, 21)) == e

    def test_missing_event_returns_none(self):
        r = InMemoryEarningsRepo()
        assert r.get_event("NONE", dt.date(2026, 4, 21)) is None

    def test_get_events_on_date(self):
        r = InMemoryEarningsRepo()
        r.upsert(_event(symbol="AAPL"))
        r.upsert(_event(symbol="MSFT"))
        r.upsert(_event(symbol="NVDA", event_date=dt.date(2026, 4, 22)))
        on = r.get_events_on(dt.date(2026, 4, 21))
        syms = {e.symbol for e in on}
        assert syms == {"AAPL", "MSFT"}

    def test_upsert_replaces_existing(self):
        r = InMemoryEarningsRepo()
        r.upsert(_event(event_time=EventTime.BEFORE_OPEN, source="zacks"))
        r.upsert(_event(event_time=EventTime.AFTER_CLOSE, source="whispers"))
        # Latest upsert wins on key (symbol, event_date)
        e = r.get_event("AAPL", dt.date(2026, 4, 21))
        assert e.event_time == EventTime.AFTER_CLOSE
        assert e.source == "whispers"

    def test_get_events_between_inclusive(self):
        r = InMemoryEarningsRepo()
        r.upsert(_event(symbol="A", event_date=dt.date(2026, 4, 20)))
        r.upsert(_event(symbol="B", event_date=dt.date(2026, 4, 21)))
        r.upsert(_event(symbol="C", event_date=dt.date(2026, 4, 22)))
        r.upsert(_event(symbol="D", event_date=dt.date(2026, 4, 23)))
        got = r.get_events_between(dt.date(2026, 4, 21), dt.date(2026, 4, 22))
        assert {e.symbol for e in got} == {"B", "C"}

    def test_get_events_between_reversed_range_raises(self):
        r = InMemoryEarningsRepo()
        with pytest.raises(ValueError):
            r.get_events_between(dt.date(2026, 4, 22), dt.date(2026, 4, 21))

    def test_empty_symbol_rejected(self):
        r = InMemoryEarningsRepo()
        with pytest.raises(ValueError):
            r.upsert(EarningsEvent(
                symbol="", asset_id="x",
                event_date=dt.date(2026, 4, 21),
                event_time=EventTime.AFTER_CLOSE,
            ))
