"""BACKTEST-PAPER-2 — stock recommendation as_of seam.

Proves the optional ``as_of`` threaded through compute_for_asset removes the
last blocking now()-anchor in stock generation:
  * _is_stale(as_of=T) measures age against the decision day, not wall clock.
  * compute_for_asset(as_of=T) bounds the price series to T (future bars
    excluded) and is recompute-stable when later bars are appended.
  * default (no as_of) preserves legacy now()/unbounded behaviour.

Unit tests for _is_stale are pure (no DB); the compute_for_asset tests use
the Postgres fixture.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, PriceBar
from apps.api.src.domain.ledger.account_service import AccountCreate, create_account
from apps.api.src.domain.recommendations.recommendation_engine import (
    Series,
    _is_stale,
    compute_for_asset,
    load_engine_config,
)

pytestmark = pytest.mark.integration

T = dt.date(2026, 6, 15)


# --------------------------------------------------------------------------
# Unit — _is_stale (pure, no DB)
# --------------------------------------------------------------------------

def _series_with_latest(latest: dt.datetime) -> Series:
    return Series(ts=[latest], close=[Decimal("100")],
                  high=[Decimal("101")], low=[Decimal("99")])


def test_is_stale_as_of_bar_on_decision_day_not_stale() -> None:
    s = _series_with_latest(dt.datetime(T.year, T.month, T.day, 14, 0,
                                        tzinfo=dt.timezone.utc))
    assert _is_stale(s, as_of=T) is False


def test_is_stale_as_of_old_bar_is_stale() -> None:
    old = dt.datetime(T.year, T.month, T.day, 14, 0,
                      tzinfo=dt.timezone.utc) - dt.timedelta(days=10)
    s = _series_with_latest(old)
    assert _is_stale(s, as_of=T) is True


def test_is_stale_default_uses_now() -> None:
    """No as_of -> legacy now() reference: a bar years in the past is stale."""
    s = _series_with_latest(dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc))
    assert _is_stale(s) is True
    assert _is_stale(s, as_of=None) is True


# --------------------------------------------------------------------------
# Integration — compute_for_asset(as_of=...)
# --------------------------------------------------------------------------

def _seed_account_and_asset(pg_session: Session, symbol: str) -> tuple[str, str]:
    acct = create_account(pg_session, AccountCreate(name="BP2", kind="broker"))
    asset = Asset(symbol=symbol, asset_class="equity", exchange="NASDAQ",
                  currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    return acct.id, asset.id


def _seed_bars(pg_session: Session, asset_id: str, end: dt.date, n: int,
               start_price: Decimal = Decimal("100"),
               step: Decimal = Decimal("0.5")) -> None:
    """n daily bars ending on ``end`` (ascending), oldest first."""
    for i in range(n):
        d = end - dt.timedelta(days=n - 1 - i)
        price = start_price + step * Decimal(i)
        pg_session.add(PriceBar(
            asset_id=asset_id, timeframe="1d",
            ts=dt.datetime(d.year, d.month, d.day, 14, 0, tzinfo=dt.timezone.utc),
            open=price, high=price + Decimal("0.5"), low=price - Decimal("0.5"),
            close=price, adjusted_close=price, volume=1_000_000, provider="bp2",
        ))


def test_compute_for_asset_as_of_bounded_and_recompute_stable(
    pg_session: Session,
) -> None:
    """as_of=T: not stale, enough data, and the decision is unchanged when
    strictly-later bars are appended (future excluded via load_series)."""
    account_id, asset_id = _seed_account_and_asset(pg_session, "BP2A")
    _seed_bars(pg_session, asset_id, end=T, n=210)
    pg_session.commit()

    cfg = load_engine_config()
    v1 = compute_for_asset(pg_session, account_id=account_id, asset_id=asset_id,
                           config=cfg, as_of=T)
    assert v1.enough_data is True
    assert "stale-data" not in v1.tags        # decision-day staleness, not now()

    # Append strictly-later bars (T+1, T+5) — must not change the as_of=T row.
    _seed_bars(pg_session, asset_id, end=T + dt.timedelta(days=5), n=5,
               start_price=Decimal("999"), step=Decimal("1"))
    pg_session.commit()

    v2 = compute_for_asset(pg_session, account_id=account_id, asset_id=asset_id,
                           config=cfg, as_of=T)
    assert v2.snapshot_hash == v1.snapshot_hash      # no repaint / future excluded
    assert v2.composite_score == v1.composite_score


def test_default_no_as_of_includes_future_bar(pg_session: Session) -> None:
    """Default (no as_of) is unbounded: with later bars present the decision
    differs from the as_of=T-bounded one -> legacy behaviour preserved."""
    account_id, asset_id = _seed_account_and_asset(pg_session, "BP2B")
    _seed_bars(pg_session, asset_id, end=T, n=210)
    _seed_bars(pg_session, asset_id, end=T + dt.timedelta(days=5), n=5,
               start_price=Decimal("999"), step=Decimal("1"))
    pg_session.commit()

    cfg = load_engine_config()
    bounded = compute_for_asset(pg_session, account_id=account_id,
                                asset_id=asset_id, config=cfg, as_of=T)
    default = compute_for_asset(pg_session, account_id=account_id,
                                asset_id=asset_id, config=cfg)   # no as_of
    # default sees the T+5 bar -> different inputs -> different snapshot
    assert default.snapshot_hash != bounded.snapshot_hash
