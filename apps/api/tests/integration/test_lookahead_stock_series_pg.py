"""QW2-A — stock price-series (load_series) lookahead detector + fix proof.

The recommendation engine's only price input is
domain/features/feature_engine.py::load_series. Historically it had a
LOWER bound only (ts >= now()-days) and NO upper bound, so a replay for a
past decision date would pull bars stamped AFTER that date -> lookahead,
and the trailing window was anchored to wall-clock now() rather than the
decision date.

QW2-A adds an optional, keyword-only ``as_of``:
  * as_of=None (default)  -> exact legacy behaviour (live no-op).
  * as_of=T               -> window anchored to T (since = T-days) AND an
                             upper bound ts < start-of-(T+1) so no bar dated
                             after T is ever returned.

Three tests:
  * default-unbounded regression guard — proves the legacy/default path
    still returns the post-decision bar (live behaviour unchanged).
  * bounded invariant — as_of=T returns no ts > T (reuses
    max_input_ts_le_decision).
  * window anchor — bars older than as_of-days are excluded.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from apps.api.src.db.models import Asset, PriceBar
from apps.api.src.domain.features.feature_engine import load_series
from apps.api.src.analytics.lookahead import max_input_ts_le_decision

pytestmark = pytest.mark.integration

T = dt.date(2026, 6, 15)
# Decision boundary = end of the decision day (UTC).
T_DECISION = dt.datetime(2026, 6, 15, 23, 59, 59, tzinfo=dt.timezone.utc)


def _bar_at(asset_id: str, on_date: dt.date, *, close: str = "100") -> PriceBar:
    return PriceBar(
        asset_id=asset_id, timeframe="1d",
        ts=dt.datetime(on_date.year, on_date.month, on_date.day, 14, 0,
                       tzinfo=dt.timezone.utc),
        open=Decimal(close), high=Decimal(close), low=Decimal(close),
        close=Decimal(close), adjusted_close=Decimal(close),
        volume=1000, provider="qw2-test",
    )


def _seed_asset(pg_session) -> str:
    a = Asset(symbol="QW2A", asset_class="equity", exchange="TEST")
    pg_session.add(a)
    pg_session.flush()        # populate a.id
    return a.id


def test_unbounded_default_would_leak(pg_session) -> None:
    """Regression guard: the DEFAULT (no as_of) path still returns the bar
    dated AFTER the decision date -> proves the upper bound is opt-in and
    live behaviour is unchanged."""
    aid = _seed_asset(pg_session)
    pg_session.add(_bar_at(aid, T - dt.timedelta(days=1)))
    pg_session.add(_bar_at(aid, T))
    pg_session.add(_bar_at(aid, T + dt.timedelta(days=1)))   # AFTER decision
    pg_session.commit()

    series = load_series(pg_session, aid)        # no as_of = legacy
    assert series is not None
    dates = {ts.date() for ts in series.ts}
    assert (T + dt.timedelta(days=1)) in dates   # future bar present -> leak
    assert max_input_ts_le_decision(T_DECISION, series.ts)["ok"] is False


def test_series_bounded_by_as_of(pg_session) -> None:
    """QW2-A: load_series(as_of=T) returns no bar stamped after T."""
    aid = _seed_asset(pg_session)
    pg_session.add(_bar_at(aid, T - dt.timedelta(days=1)))
    pg_session.add(_bar_at(aid, T))
    pg_session.add(_bar_at(aid, T + dt.timedelta(days=1)))   # AFTER decision
    pg_session.commit()

    series = load_series(pg_session, aid, as_of=T)
    assert series is not None
    dates = {ts.date() for ts in series.ts}
    assert (T + dt.timedelta(days=1)) not in dates           # future excluded
    assert max(series.ts).date() <= T
    assert max_input_ts_le_decision(T_DECISION, series.ts)["ok"] is True
    # ascending order preserved
    assert series.ts == sorted(series.ts)


def test_window_anchored_to_as_of(pg_session) -> None:
    """QW2-A: the trailing window is anchored to as_of (since = as_of-days),
    so a bar older than that window is excluded even though it is <= as_of."""
    aid = _seed_asset(pg_session)
    old = T - dt.timedelta(days=500)              # outside a 400-day window
    mid = T - dt.timedelta(days=100)              # inside the window
    pg_session.add(_bar_at(aid, old))
    pg_session.add(_bar_at(aid, mid))
    pg_session.add(_bar_at(aid, T))
    pg_session.commit()

    series = load_series(pg_session, aid, days=400, as_of=T)
    assert series is not None
    dates = {ts.date() for ts in series.ts}
    assert old not in dates                       # pre-window bar excluded
    assert mid in dates and T in dates
    assert min(series.ts).date() >= T - dt.timedelta(days=400)
