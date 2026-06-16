"""QW2-B — options moneyness spot (_latest_price_bar_close) lookahead detector.

The options-feature job sources its moneyness ``spot`` from
worker/jobs/compute_options_features.py::_latest_price_bar_close, which
historically did an UNBOUNDED ``ORDER BY ts DESC LIMIT 1`` — so a replay for
a past decision date would pick a bar stamped AFTER that date as the spot,
which feeds persisted moneyness/ATM/strike-distance fields -> repaint.

QW2-B adds optional, keyword-only ``session`` (for injection/testing) and
``as_of``:
  * as_of=None (default)  -> legacy unbounded newest-bar (live no-op).
  * as_of=T               -> upper bound (ts date <= T) so no bar after T.

Proof is by VALUE: bars are seeded with distinct closes per date, so the
returned Decimal identifies exactly which bar was selected.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from apps.api.src.db.models import Asset, PriceBar
from apps.worker.src.jobs.compute_options_features import _latest_price_bar_close

pytestmark = pytest.mark.integration

SYM = "QW2BSPOT"
T = dt.date(2026, 6, 15)
C_PREV = Decimal("100")   # T-1
C_T = Decimal("110")      # T
C_NEXT = Decimal("120")   # T+1


def _bar(asset_id: str, on_date: dt.date, close: Decimal) -> PriceBar:
    return PriceBar(
        asset_id=asset_id, timeframe="1d",
        ts=dt.datetime(on_date.year, on_date.month, on_date.day, 14, 0,
                       tzinfo=dt.timezone.utc),
        open=close, high=close, low=close, close=close, adjusted_close=close,
        volume=1000, provider="qw2b-test",
    )


def _seed_asset(pg_session) -> str:
    a = Asset(symbol=SYM, asset_class="equity", exchange="TEST")
    pg_session.add(a)
    pg_session.flush()
    return a.id


def test_unbounded_default_returns_future(pg_session) -> None:
    """Regression guard: default (no as_of) returns the bar dated AFTER the
    decision date -> proves the upper bound is opt-in and live is unchanged."""
    aid = _seed_asset(pg_session)
    pg_session.add(_bar(aid, T - dt.timedelta(days=1), C_PREV))
    pg_session.add(_bar(aid, T, C_T))
    pg_session.add(_bar(aid, T + dt.timedelta(days=1), C_NEXT))
    pg_session.commit()

    spot = _latest_price_bar_close(SYM, session=pg_session)
    assert spot == C_NEXT   # future bar selected (legacy newest-wins)


def test_spot_bounded_by_as_of(pg_session) -> None:
    """QW2-B: as_of=T excludes the post-T bar; the T bar is selected."""
    aid = _seed_asset(pg_session)
    pg_session.add(_bar(aid, T - dt.timedelta(days=1), C_PREV))
    pg_session.add(_bar(aid, T, C_T))
    pg_session.add(_bar(aid, T + dt.timedelta(days=1), C_NEXT))
    pg_session.commit()

    spot = _latest_price_bar_close(SYM, session=pg_session, as_of=T)
    assert spot == C_T      # on-or-before, not the future bar


def test_returns_latest_on_or_before(pg_session) -> None:
    """QW2-B: with only T-1 and T+1 bars, as_of=T returns the T-1 close
    (latest on-or-before), never the future T+1 bar."""
    aid = _seed_asset(pg_session)
    pg_session.add(_bar(aid, T - dt.timedelta(days=1), C_PREV))
    pg_session.add(_bar(aid, T + dt.timedelta(days=1), C_NEXT))
    pg_session.commit()

    spot = _latest_price_bar_close(SYM, session=pg_session, as_of=T)
    assert spot == C_PREV   # latest <= T
