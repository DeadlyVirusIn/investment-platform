"""Phase 11V - end-to-end T+1 fill simulation against Postgres.

Confirms that with `submitted_at = today 15:00 UTC`:
  * a same-day bar (`ts = today 00:00 UTC`) does NOT satisfy
    `find_next_open` (no same-day fill — T+1 invariant preserved).
  * a next-day bar (`ts = tomorrow 00:00 UTC`) DOES satisfy
    `find_next_open` (fill succeeds when next-day bar lands).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.domain.paper_trading.paper_execution import (
    find_next_open,
)


pytestmark = pytest.mark.integration


@pytest.fixture
def session_factory(pg_engine):
    return sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )


def _seed_asset_and_bars(
    pg_session: Session,
    *,
    symbol: str,
    bars: list[dt.datetime],
) -> str:
    asset_id = f"asset-{symbol.lower()}"
    pg_session.execute(text(
        """
        INSERT INTO asset
          (id, symbol, name, asset_class, exchange, currency,
           is_active, created_at, updated_at)
        VALUES
          (:id, :sym, :sym, 'equity', 'NASDAQ', 'USD',
           TRUE, now(), now())
        ON CONFLICT ON CONSTRAINT uq_asset_symbol_exchange DO NOTHING
        """
    ), {"id": asset_id, "sym": symbol})
    for ts in bars:
        pg_session.execute(text(
            """
            INSERT INTO price_bar
              (id, asset_id, timeframe, ts, open, high, low, close,
               adjusted_close, volume, provider, created_at)
            VALUES
              (gen_random_uuid()::text, :aid, '1d', :ts,
               :o, :o, :o, :o, :o, 1000000, 'tiingo', now())
            ON CONFLICT DO NOTHING
            """
        ), {"aid": asset_id, "ts": ts, "o": Decimal("100.00")})
    pg_session.commit()
    return asset_id


def test_t1_invariant_same_day_bar_does_not_qualify(
    pg_session, session_factory,
):
    """submitted_at = today 15:00 UTC; only today's 00:00 bar exists.
    Strict `ts > submitted_at` rejects same-day fill."""
    today = dt.date(2026, 4, 28)
    today_bar = dt.datetime.combine(
        today, dt.time(0, 0), tzinfo=dt.timezone.utc,
    )
    asset_id = _seed_asset_and_bars(
        pg_session, symbol="SPY", bars=[today_bar],
    )
    submitted_at = dt.datetime.combine(
        today, dt.time(15, 0), tzinfo=dt.timezone.utc,
    )
    out = find_next_open(pg_session, asset_id, submitted_at)
    assert out is None


def test_t1_anchor_next_day_bar_qualifies(
    pg_session, session_factory,
):
    """Anchored at today 15:00 UTC: when tomorrow's bar lands at
    `tomorrow 00:00 UTC`, `find_next_open` returns its open."""
    today = dt.date(2026, 4, 28)
    tomorrow = today + dt.timedelta(days=1)
    today_bar = dt.datetime.combine(
        today, dt.time(0, 0), tzinfo=dt.timezone.utc,
    )
    tomorrow_bar = dt.datetime.combine(
        tomorrow, dt.time(0, 0), tzinfo=dt.timezone.utc,
    )
    asset_id = _seed_asset_and_bars(
        pg_session, symbol="SPY",
        bars=[today_bar, tomorrow_bar],
    )
    submitted_at = dt.datetime.combine(
        today, dt.time(15, 0), tzinfo=dt.timezone.utc,
    )
    out = find_next_open(pg_session, asset_id, submitted_at)
    assert out is not None
    fill_ts, fill_price = out
    assert fill_ts == tomorrow_bar
    assert fill_price == Decimal("100.00")


def test_t1_anchor_returns_earliest_future_bar(
    pg_session, session_factory,
):
    """Multiple future bars exist → returns the earliest."""
    today = dt.date(2026, 4, 28)
    bars = [
        dt.datetime.combine(today, dt.time(0, 0),
                            tzinfo=dt.timezone.utc),
        dt.datetime.combine(today + dt.timedelta(days=1),
                            dt.time(0, 0), tzinfo=dt.timezone.utc),
        dt.datetime.combine(today + dt.timedelta(days=2),
                            dt.time(0, 0), tzinfo=dt.timezone.utc),
    ]
    asset_id = _seed_asset_and_bars(
        pg_session, symbol="SPY", bars=bars,
    )
    submitted_at = dt.datetime.combine(
        today, dt.time(15, 0), tzinfo=dt.timezone.utc,
    )
    out = find_next_open(pg_session, asset_id, submitted_at)
    assert out is not None
    fill_ts, _ = out
    assert fill_ts == bars[1]


def test_t1_anchor_none_when_only_past_bars(
    pg_session, session_factory,
):
    """All bars at or before submitted_at → None."""
    today = dt.date(2026, 4, 28)
    asset_id = _seed_asset_and_bars(
        pg_session, symbol="SPY",
        bars=[
            dt.datetime.combine(today - dt.timedelta(days=1),
                                dt.time(0, 0),
                                tzinfo=dt.timezone.utc),
            dt.datetime.combine(today, dt.time(0, 0),
                                tzinfo=dt.timezone.utc),
        ],
    )
    submitted_at = dt.datetime.combine(
        today, dt.time(15, 0), tzinfo=dt.timezone.utc,
    )
    out = find_next_open(pg_session, asset_id, submitted_at)
    assert out is None


def test_t1_anchor_strictly_greater_not_equal(
    pg_session, session_factory,
):
    """A bar at exactly submitted_at must NOT qualify (strict `>`)."""
    today = dt.date(2026, 4, 28)
    submitted_at = dt.datetime.combine(
        today, dt.time(15, 0), tzinfo=dt.timezone.utc,
    )
    asset_id = _seed_asset_and_bars(
        pg_session, symbol="SPY", bars=[submitted_at],
    )
    out = find_next_open(pg_session, asset_id, submitted_at)
    assert out is None


def test_run_time_anchor_would_have_blocked_fill_pg(
    pg_session, session_factory,
):
    """Documentation test: with the OLD anchor (run-time, e.g.
    today 03:30 UTC), a same-day cron run would never find a future
    bar even after tomorrow's 00:00 UTC bar lands. The fix restores
    fill flow."""
    today = dt.date(2026, 4, 28)
    tomorrow_bar = dt.datetime.combine(
        today + dt.timedelta(days=1), dt.time(0, 0),
        tzinfo=dt.timezone.utc,
    )
    asset_id = _seed_asset_and_bars(
        pg_session, symbol="SPY", bars=[tomorrow_bar],
    )
    # OLD broken anchor: tomorrow 03:30 UTC > tomorrow 00:00 UTC →
    # strict `>` fails.
    old_anchor = dt.datetime.combine(
        today + dt.timedelta(days=1), dt.time(3, 30),
        tzinfo=dt.timezone.utc,
    )
    assert find_next_open(pg_session, asset_id, old_anchor) is None
    # NEW anchor: today 15:00 UTC < tomorrow 00:00 UTC → fill OK.
    new_anchor = dt.datetime.combine(
        today, dt.time(15, 0), tzinfo=dt.timezone.utc,
    )
    out = find_next_open(pg_session, asset_id, new_anchor)
    assert out is not None
    fill_ts, _ = out
    assert fill_ts == tomorrow_bar
