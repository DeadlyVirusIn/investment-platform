"""QW2-C — recursive (repaint) + as_of-exclusion detector for factor_snapshot.

stock_factor_engine reads every bar day-bounded (``ts < midnight(as_of)``)
and is now()-free, so the factor row computed for as_of=T must:
  1. NOT change when strictly-later bars (T+1, T+2) are appended (no repaint).
  2. NOT be influenced by a bar stamped ON the as_of day (strict ``<``).

Detector only — no engine change expected (audit found the engine already
as_of-correct). Compares the SnapshotRow objects returned by
compute_universe_snapshots field-by-field (Decimal tolerant, None-equal).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from apps.api.src.db.models import Asset, PriceBar, UniverseMembership
from apps.api.src.domain.features.stock_factor_engine import (
    compute_universe_snapshots,
)

pytestmark = pytest.mark.integration

UNI = "qw2c_uni"
T = dt.date(2026, 6, 15)
N_BARS = 205   # > MIN_BARS_ENOUGH (200) so enough_data=True + cross-section runs

_NUM_FIELDS = (
    "residual_momentum_20d", "residual_momentum_60d", "sector_relative_rank",
    "trend_strength_20d", "price_vs_200sma", "atr_percent_14",
    "avg_dollar_volume_20d",
)


def _add_asset(pg_session, symbol: str) -> str:
    a = Asset(symbol=symbol, asset_class="equity", exchange="TEST")
    pg_session.add(a)
    pg_session.flush()
    return a.id


def _add_bars(pg_session, asset_id: str, start: dt.date, n: int,
              base: float, slope: float) -> None:
    for i in range(n):
        d = start + dt.timedelta(days=i)
        close = Decimal(str(round(base + slope * i, 4)))
        pg_session.add(PriceBar(
            asset_id=asset_id, timeframe="1d",
            ts=dt.datetime(d.year, d.month, d.day, 14, 0, tzinfo=dt.timezone.utc),
            open=close, high=close + Decimal("1"), low=close - Decimal("1"),
            close=close, adjusted_close=close, volume=1_000_000,
            provider="qw2c-test",
        ))


def _seed_universe(pg_session) -> None:
    """2 universe assets + SPY benchmark, each with N_BARS daily bars ending
    at T-1 (so all are < midnight(T) and counted for as_of=T)."""
    start = T - dt.timedelta(days=N_BARS)   # bars span [T-205 .. T-1]
    specs = [("AAA", 100.0, 0.5), ("BBB", 200.0, 0.3), ("SPY", 400.0, 0.2)]
    for sym, base, slope in specs:
        aid = _add_asset(pg_session, sym)
        _add_bars(pg_session, aid, start, N_BARS, base, slope)
        if sym != "SPY":
            pg_session.add(UniverseMembership(
                universe_name=UNI, asset_id=aid,
                start_date=start, end_date=None,
            ))
    pg_session.flush()


def _by_asset(rows):
    return {r.asset_id: r for r in rows}


def _assert_rows_equal(rows_a, rows_b, *, tol=Decimal("0.000001")) -> None:
    a, b = _by_asset(rows_a), _by_asset(rows_b)
    assert set(a) == set(b), f"asset set drift {set(a)} vs {set(b)}"
    for aid in a:
        ra, rb = a[aid], b[aid]
        assert ra.enough_data == rb.enough_data, f"{aid} enough_data drift"
        assert ra.stale_data == rb.stale_data, f"{aid} stale_data drift"
        assert ra.feature_set_hash == rb.feature_set_hash, f"{aid} hash drift"
        for f in _NUM_FIELDS:
            va, vb = getattr(ra, f), getattr(rb, f)
            if va is None or vb is None:
                assert va is None and vb is None, f"{aid}.{f} NULL drift {va!r} vs {vb!r}"
            else:
                assert abs(Decimal(str(va)) - Decimal(str(vb))) <= tol, \
                    f"{aid}.{f} repaint {va!r} -> {vb!r}"


def test_factor_row_recompute_stable(pg_session) -> None:
    """The as_of=T factor rows must not change when strictly-later bars
    (T+1, T+2) are appended (no repaint)."""
    _seed_universe(pg_session)
    pg_session.commit()

    v1 = compute_universe_snapshots(pg_session, UNI, T)
    assert v1, "expected non-empty universe rows"
    # at least one asset must exercise cross-section fields
    assert any(r.enough_data and not r.stale_data for r in v1)
    assert any(r.residual_momentum_20d is not None for r in v1)

    # Append STRICTLY-LATER bars (dates T+1, T+2) to every asset.
    for a in pg_session.query(Asset).all():
        _add_bars(pg_session, a.id, T + dt.timedelta(days=1), 2, 999.0, 1.0)
    pg_session.commit()

    v2 = compute_universe_snapshots(pg_session, UNI, T)
    _assert_rows_equal(v1, v2)


def test_as_of_day_bar_excluded(pg_session) -> None:
    """A bar stamped ON the as_of day must not enter the T computation
    (strict ts < midnight(as_of))."""
    _seed_universe(pg_session)
    pg_session.commit()

    v1 = compute_universe_snapshots(pg_session, UNI, T)

    # Add a bar dated exactly T (any time on T) to every asset.
    for a in pg_session.query(Asset).all():
        pg_session.add(PriceBar(
            asset_id=a.id, timeframe="1d",
            ts=dt.datetime(T.year, T.month, T.day, 14, 0, tzinfo=dt.timezone.utc),
            open=Decimal("9999"), high=Decimal("10000"), low=Decimal("9998"),
            close=Decimal("9999"), adjusted_close=Decimal("9999"),
            volume=1_000_000, provider="qw2c-test",
        ))
    pg_session.commit()

    v2 = compute_universe_snapshots(pg_session, UNI, T)
    _assert_rows_equal(v1, v2)   # identical => T-day bar excluded
