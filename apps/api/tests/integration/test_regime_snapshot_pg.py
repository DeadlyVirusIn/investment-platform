"""Integration: regime_snapshot job + /api/regime endpoints against Postgres."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, PriceBar, RegimeSnapshot
from apps.worker.src.jobs.compute_regime_snapshot import compute_regime_snapshot

pytestmark = pytest.mark.integration


def _seed_spy_series(pg_session: Session, n_bars: int, drift: float = 0.0008) -> None:
    """Seed n_bars daily SPY bars ending on 2026-04-17 with small drift."""
    asset = Asset(
        symbol="SPY", asset_class="etf", exchange="NYSE", currency="USD",
    )
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()

    last_date = dt.date(2026, 4, 17)
    price = 400.0
    bars: list[PriceBar] = []
    for i in range(n_bars):
        shock = 0.005 if i % 2 == 0 else -0.003
        price *= 1 + drift + shock
        ts = dt.datetime.combine(
            last_date - dt.timedelta(days=n_bars - 1 - i),
            dt.time(0, 0, 0, tzinfo=dt.timezone.utc),
        )
        bars.append(PriceBar(
            asset_id=asset.id, timeframe="1d", ts=ts,
            open=Decimal(str(price)), close=Decimal(str(price)),
            high=Decimal(str(price * 1.005)), low=Decimal(str(price * 0.995)),
            adjusted_close=Decimal(str(price)), volume=1_000_000, provider="test",
        ))
    pg_session.add_all(bars)
    pg_session.commit()


async def test_compute_regime_snapshot_writes_row(pg_session: Session) -> None:
    _seed_spy_series(pg_session, n_bars=280, drift=0.0008)
    target = dt.date(2026, 4, 17)

    await compute_regime_snapshot(target)

    pg_session.expire_all()
    row = pg_session.get(RegimeSnapshot, target)
    assert row is not None
    assert row.benchmark_symbol == "SPY"
    assert row.market_trend in ("uptrend", "downtrend", "sideways")
    assert row.vol_regime in ("low", "normal", "high")
    assert row.breadth_regime is None
    assert row.realized_vol_20d > 0
    assert 0 <= row.atr_pctile_1y <= 1


async def test_compute_regime_snapshot_idempotent(pg_session: Session) -> None:
    _seed_spy_series(pg_session, n_bars=280, drift=0.0010)
    target = dt.date(2026, 4, 17)

    await compute_regime_snapshot(target)
    await compute_regime_snapshot(target)  # second call must not duplicate

    pg_session.expire_all()
    rows = list(
        pg_session.query(RegimeSnapshot).filter_by(as_of_date=target).all()
    )
    assert len(rows) == 1


async def test_compute_regime_snapshot_skips_when_short_history(
    pg_session: Session,
) -> None:
    _seed_spy_series(pg_session, n_bars=100)  # < MIN_SMA_LONG (200)
    target = dt.date(2026, 4, 17)

    await compute_regime_snapshot(target)

    pg_session.expire_all()
    assert pg_session.get(RegimeSnapshot, target) is None


async def test_compute_regime_snapshot_respects_anti_lookahead(
    pg_session: Session,
) -> None:
    _seed_spy_series(pg_session, n_bars=280)
    earlier = dt.date(2026, 3, 1)
    latest = dt.date(2026, 4, 17)

    await compute_regime_snapshot(earlier)
    await compute_regime_snapshot(latest)

    pg_session.expire_all()
    r_early = pg_session.get(RegimeSnapshot, earlier)
    r_late = pg_session.get(RegimeSnapshot, latest)
    assert r_early is not None
    assert r_late is not None
    assert r_early.as_of_date == earlier
    assert r_late.as_of_date == latest


# ---------------------------------------------------------------------------
# /api/regime endpoints
# ---------------------------------------------------------------------------


def test_regime_current_404_when_no_rows(pg_session: Session) -> None:
    from apps.api.src.main import app
    client = TestClient(app)
    resp = client.get("/api/regime/current")
    assert resp.status_code == 404


def test_regime_current_returns_latest(pg_session: Session) -> None:
    from apps.api.src.main import app

    pg_session.add(RegimeSnapshot(
        as_of_date=dt.date(2026, 4, 15), benchmark_symbol="SPY",
        market_trend="sideways", vol_regime="normal", breadth_regime=None,
        sma50_over_sma200=True, realized_vol_20d=Decimal("0.14"),
        atr_pctile_1y=Decimal("0.40"),
    ))
    pg_session.add(RegimeSnapshot(
        as_of_date=dt.date(2026, 4, 17), benchmark_symbol="SPY",
        market_trend="uptrend", vol_regime="low", breadth_regime=None,
        sma50_over_sma200=True, realized_vol_20d=Decimal("0.10"),
        atr_pctile_1y=Decimal("0.15"),
    ))
    pg_session.commit()

    client = TestClient(app)
    resp = client.get("/api/regime/current")
    assert resp.status_code == 200
    data = resp.json()
    assert data["as_of_date"] == "2026-04-17"
    assert data["market_trend"] == "uptrend"
    assert data["vol_regime"] == "low"
    assert data["sma50_over_sma200"] is True
    assert Decimal(data["realized_vol_20d"]) == Decimal("0.10")


def test_regime_history_filters_and_sorts(pg_session: Session) -> None:
    from apps.api.src.main import app

    for d, trend in [
        (dt.date(2026, 1, 1), "sideways"),
        (dt.date(2026, 2, 1), "uptrend"),
        (dt.date(2026, 3, 1), "downtrend"),
        (dt.date(2026, 4, 1), "sideways"),
    ]:
        pg_session.add(RegimeSnapshot(
            as_of_date=d, benchmark_symbol="SPY",
            market_trend=trend, vol_regime="normal", breadth_regime=None,
            sma50_over_sma200=True, realized_vol_20d=Decimal("0.15"),
            atr_pctile_1y=Decimal("0.50"),
        ))
    pg_session.commit()

    client = TestClient(app)
    resp = client.get("/api/regime/history?from=2026-02-01&to=2026-03-31")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    trends = [s["market_trend"] for s in data["snapshots"]]
    assert trends == ["uptrend", "downtrend"]


def test_regime_history_rejects_inverted_range(pg_session: Session) -> None:
    from apps.api.src.main import app
    client = TestClient(app)
    resp = client.get("/api/regime/history?from=2026-04-01&to=2026-01-01")
    assert resp.status_code == 400


def test_regime_history_default_window_returns_empty_list_when_none(
    pg_session: Session,
) -> None:
    from apps.api.src.main import app
    client = TestClient(app)
    resp = client.get("/api/regime/history")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0
