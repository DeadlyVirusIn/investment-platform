"""Market-aware options-chain freshness (observability fix).

Pure: no DB. Verifies that market-hours staleness still degrades health
while overnight/weekend ageing of a last-session snapshot does not falsely
penalize.
"""

from __future__ import annotations

import datetime as dt

from apps.api.src.api.freshness import (
    _classify_options,
    _is_market_hours,
    _hours_since_last_close,
)

# 2026-06-03 is a Wednesday; 15:00 UTC == 11:00 ET → market open.
WED_OPEN = dt.datetime(2026, 6, 3, 15, 0, tzinfo=dt.timezone.utc)
# 2026-06-06 is a Saturday → market closed.
SAT_CLOSED = dt.datetime(2026, 6, 6, 12, 0, tzinfo=dt.timezone.utc)


def test_market_hours_staleness_still_degrades():
    assert _is_market_hours(WED_OPEN) is True
    assert _classify_options(3.0, WED_OPEN) == "fresh"
    assert _classify_options(8.0, WED_OPEN) == "degraded"
    assert _classify_options(13.0, WED_OPEN) == "stale"


def test_overnight_weekend_not_falsely_penalized():
    assert _is_market_hours(SAT_CLOSED) is False
    # Friday-session snapshot (~21h old on Sat) reads fresh, not degraded.
    assert _classify_options(21.0, SAT_CLOSED) == "fresh"
    # Older than ~two sessions → genuinely stale.
    assert _classify_options(100.0, SAT_CLOSED) == "stale"


def test_hours_since_last_close_walks_back_weekend():
    h = _hours_since_last_close(SAT_CLOSED)
    assert h is not None and 15.0 <= h <= 17.0   # Fri 16:00 ET → Sat 08:00 ET


def test_none_hours_is_unknown():
    assert _classify_options(None, WED_OPEN) == "unknown"
