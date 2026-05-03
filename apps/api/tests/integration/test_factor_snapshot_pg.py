"""Integration: factor_snapshot job + /api/factors endpoints against Postgres."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    FactorSnapshot,
    PriceBar,
    UniverseMembership,
)
from apps.worker.src.jobs.compute_factor_snapshots import compute_factor_snapshots

pytestmark = pytest.mark.integration

UNIVERSE = "stock_swing_v1"


def _seed_asset(
    pg_session: Session, symbol: str, sector: str | None = None,
    asset_class: str = "equity",
) -> Asset:
    a = Asset(
        symbol=symbol, asset_class=asset_class, exchange="NASDAQ",
        currency="USD", sector=sector,
    )
    pg_session.add(a)
    pg_session.flush()
    pg_session.commit()
    return a


def _seed_bars(
    pg_session: Session, asset: Asset, n: int, last_date: dt.date,
    start_price: float = 100.0, step: float = 0.1,
) -> None:
    price = start_price
    for i in range(n):
        price += step
        ts = dt.datetime.combine(
            last_date - dt.timedelta(days=n - 1 - i),
            dt.time(0, 0, 0, tzinfo=dt.timezone.utc),
        )
        pg_session.add(PriceBar(
            asset_id=asset.id, timeframe="1d", ts=ts,
            open=Decimal(str(price)),
            high=Decimal(str(price * 1.01)),
            low=Decimal(str(price * 0.99)),
            close=Decimal(str(price)),
            adjusted_close=Decimal(str(price)),
            volume=1_000_000, provider="test",
        ))
    pg_session.commit()


def _add_member(pg_session: Session, asset: Asset, start: dt.date) -> None:
    pg_session.add(UniverseMembership(
        universe_name=UNIVERSE, asset_id=asset.id,
        start_date=start, reason="seeded",
    ))
    pg_session.commit()


async def test_job_writes_one_row_per_asset(pg_session: Session) -> None:
    as_of = dt.date(2026, 4, 19)
    start = dt.date(2024, 1, 1)

    spy = _seed_asset(pg_session, "SPY", asset_class="etf")
    _seed_bars(pg_session, spy, n=260, last_date=as_of - dt.timedelta(days=2))
    _add_member(pg_session, spy, start)

    a1 = _seed_asset(pg_session, "AAA", sector="tech")
    _seed_bars(pg_session, a1, n=260, last_date=as_of - dt.timedelta(days=2),
               step=0.3)  # stronger drift
    _add_member(pg_session, a1, start)

    a2 = _seed_asset(pg_session, "BBB", sector="tech")
    _seed_bars(pg_session, a2, n=260, last_date=as_of - dt.timedelta(days=2),
               step=0.05)  # weaker drift
    _add_member(pg_session, a2, start)

    await compute_factor_snapshots(as_of)

    pg_session.expire_all()
    rows = list(pg_session.query(FactorSnapshot).filter_by(as_of_date=as_of).all())
    assert len(rows) == 3
    by_asset = {r.asset_id: r for r in rows}
    # AAA outperformed BBB → higher residual_momentum_60d z-score
    assert by_asset[a1.id].residual_momentum_60d > by_asset[a2.id].residual_momentum_60d
    # SPY vs SPY residual is 0 → roughly mid, but still a valid Decimal
    assert by_asset[spy.id].enough_data is True


async def test_job_is_idempotent(pg_session: Session) -> None:
    as_of = dt.date(2026, 4, 19)
    spy = _seed_asset(pg_session, "SPY", asset_class="etf")
    _seed_bars(pg_session, spy, n=220, last_date=as_of - dt.timedelta(days=2))
    _add_member(pg_session, spy, dt.date(2024, 1, 1))

    await compute_factor_snapshots(as_of)
    await compute_factor_snapshots(as_of)

    pg_session.expire_all()
    rows = list(pg_session.query(FactorSnapshot).filter_by(as_of_date=as_of).all())
    assert len(rows) == 1


async def test_job_flags_insufficient_history(pg_session: Session) -> None:
    as_of = dt.date(2026, 4, 19)
    short_asset = _seed_asset(pg_session, "SHORT")
    _seed_bars(pg_session, short_asset, n=50, last_date=as_of - dt.timedelta(days=2))
    _add_member(pg_session, short_asset, dt.date(2024, 1, 1))

    # SPY benchmark needed so engine can attempt residuals
    spy = _seed_asset(pg_session, "SPY", asset_class="etf")
    _seed_bars(pg_session, spy, n=220, last_date=as_of - dt.timedelta(days=2))
    _add_member(pg_session, spy, dt.date(2024, 1, 1))

    await compute_factor_snapshots(as_of)

    pg_session.expire_all()
    rows = list(pg_session.query(FactorSnapshot).filter_by(as_of_date=as_of).all())
    by_asset = {r.asset_id: r for r in rows}
    assert by_asset[short_asset.id].enough_data is False
    assert by_asset[short_asset.id].price_vs_200sma is None
    # Cross-section fields NULL for ineligible rows
    assert by_asset[short_asset.id].residual_momentum_20d is None
    assert by_asset[short_asset.id].residual_momentum_60d is None
    assert by_asset[short_asset.id].sector_relative_rank is None


async def test_job_flags_stale_when_last_bar_too_old(pg_session: Session) -> None:
    as_of = dt.date(2026, 4, 19)
    a = _seed_asset(pg_session, "STALE_X")
    # Last bar 15 days before as_of → stale (>5 days)
    _seed_bars(pg_session, a, n=260, last_date=as_of - dt.timedelta(days=15))
    _add_member(pg_session, a, dt.date(2024, 1, 1))

    spy = _seed_asset(pg_session, "SPY", asset_class="etf")
    _seed_bars(pg_session, spy, n=260, last_date=as_of - dt.timedelta(days=2))
    _add_member(pg_session, spy, dt.date(2024, 1, 1))

    await compute_factor_snapshots(as_of)

    pg_session.expire_all()
    row = pg_session.scalar(
        pg_session.query(FactorSnapshot)
        .filter_by(as_of_date=as_of, asset_id=a.id)
        .statement
    ) if False else (
        pg_session.query(FactorSnapshot)
        .filter_by(as_of_date=as_of, asset_id=a.id)
        .first()
    )
    assert row is not None
    assert row.stale_data is True
    assert row.residual_momentum_60d is None


async def test_job_excludes_assets_outside_universe(pg_session: Session) -> None:
    as_of = dt.date(2026, 4, 19)
    spy = _seed_asset(pg_session, "SPY", asset_class="etf")
    _seed_bars(pg_session, spy, n=260, last_date=as_of - dt.timedelta(days=2))
    _add_member(pg_session, spy, dt.date(2024, 1, 1))

    outsider = _seed_asset(pg_session, "OUT")
    _seed_bars(pg_session, outsider, n=260, last_date=as_of - dt.timedelta(days=2))
    # No membership row on purpose

    await compute_factor_snapshots(as_of)

    pg_session.expire_all()
    rows = list(pg_session.query(FactorSnapshot).filter_by(as_of_date=as_of).all())
    assert all(r.asset_id != outsider.id for r in rows)


async def test_job_prevents_lookahead(pg_session: Session) -> None:
    as_of = dt.date(2026, 4, 19)
    a = _seed_asset(pg_session, "LA")
    # Bars on and after as_of → should be excluded by the job
    for i in range(210):
        ts = dt.datetime.combine(
            as_of - dt.timedelta(days=210 - i),  # last regular bar: as_of - 1
            dt.time(0, 0, 0, tzinfo=dt.timezone.utc),
        )
        price = 100.0 + i * 0.1
        pg_session.add(PriceBar(
            asset_id=a.id, timeframe="1d", ts=ts,
            open=Decimal(str(price)), high=Decimal(str(price * 1.01)),
            low=Decimal(str(price * 0.99)), close=Decimal(str(price)),
            adjusted_close=Decimal(str(price)), volume=1_000_000, provider="test",
        ))
    # Add one bar AT as_of with an extreme price — must NOT affect the result
    ts_today = dt.datetime.combine(
        as_of, dt.time(0, 0, 0, tzinfo=dt.timezone.utc)
    )
    pg_session.add(PriceBar(
        asset_id=a.id, timeframe="1d", ts=ts_today,
        open=Decimal("1"), high=Decimal("1"), low=Decimal("1"),
        close=Decimal("1"), adjusted_close=Decimal("1"),
        volume=1_000_000, provider="test",
    ))
    pg_session.commit()
    _add_member(pg_session, a, dt.date(2024, 1, 1))

    spy = _seed_asset(pg_session, "SPY", asset_class="etf")
    _seed_bars(pg_session, spy, n=210, last_date=as_of - dt.timedelta(days=1))
    _add_member(pg_session, spy, dt.date(2024, 1, 1))

    await compute_factor_snapshots(as_of)

    pg_session.expire_all()
    row = (
        pg_session.query(FactorSnapshot)
        .filter_by(as_of_date=as_of, asset_id=a.id)
        .first()
    )
    # If lookahead leaked, atr_percent would be huge (close=1 vs price~120).
    # Anti-lookahead: the as_of bar is excluded → atr_percent stays small.
    assert row is not None
    assert row.atr_percent_14 is not None
    assert row.atr_percent_14 < Decimal("0.1")


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


def test_snapshot_endpoint_returns_row_by_symbol(pg_session: Session) -> None:
    from apps.api.src.main import app

    a = _seed_asset(pg_session, "EPTF")
    pg_session.add(FactorSnapshot(
        as_of_date=dt.date(2026, 4, 17), asset_id=a.id,
        residual_momentum_60d=Decimal("1.25"),
        trend_strength_20d=Decimal("0.9"),
        price_vs_200sma=Decimal("0.03"),
        atr_percent_14=Decimal("0.02"),
        avg_dollar_volume_20d=Decimal("50000000"),
        feature_set_hash="deadbeef",
        enough_data=True, stale_data=False,
    ))
    pg_session.commit()

    client = TestClient(app)
    resp = client.get(f"/api/factors/snapshot?symbol={a.symbol}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "EPTF"
    assert data["as_of_date"] == "2026-04-17"
    assert Decimal(data["residual_momentum_60d"]) == Decimal("1.25")
    assert data["enough_data"] is True


def test_snapshot_endpoint_404_unknown_symbol(pg_session: Session) -> None:
    from apps.api.src.main import app
    client = TestClient(app)
    resp = client.get("/api/factors/snapshot?symbol=ZZZ")
    assert resp.status_code == 404


def test_snapshot_endpoint_404_no_snapshot_for_asset(pg_session: Session) -> None:
    from apps.api.src.main import app
    _seed_asset(pg_session, "NOFACT")
    client = TestClient(app)
    resp = client.get("/api/factors/snapshot?symbol=NOFACT")
    assert resp.status_code == 404


def test_snapshot_endpoint_respects_as_of(pg_session: Session) -> None:
    from apps.api.src.main import app

    a = _seed_asset(pg_session, "ASOF")
    pg_session.add(FactorSnapshot(
        as_of_date=dt.date(2026, 1, 15), asset_id=a.id,
        feature_set_hash="deadbeef", enough_data=True, stale_data=False,
    ))
    pg_session.add(FactorSnapshot(
        as_of_date=dt.date(2026, 4, 15), asset_id=a.id,
        feature_set_hash="deadbeef", enough_data=True, stale_data=False,
    ))
    pg_session.commit()

    client = TestClient(app)
    resp = client.get("/api/factors/snapshot?symbol=ASOF&as_of=2026-01-15")
    assert resp.json()["as_of_date"] == "2026-01-15"


def test_latest_endpoint_returns_most_recent_per_asset(
    pg_session: Session,
) -> None:
    from apps.api.src.main import app

    a1 = _seed_asset(pg_session, "LAAA")
    a2 = _seed_asset(pg_session, "LBBB")
    for d in (dt.date(2026, 4, 15), dt.date(2026, 4, 17)):
        pg_session.add(FactorSnapshot(
            as_of_date=d, asset_id=a1.id,
            feature_set_hash="h", enough_data=True, stale_data=False,
        ))
    pg_session.add(FactorSnapshot(
        as_of_date=dt.date(2026, 4, 10), asset_id=a2.id,
        feature_set_hash="h", enough_data=True, stale_data=False,
    ))
    pg_session.commit()

    client = TestClient(app)
    resp = client.get("/api/factors/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    by_symbol = {s["symbol"]: s for s in data["snapshots"]}
    assert by_symbol["LAAA"]["as_of_date"] == "2026-04-17"
    assert by_symbol["LBBB"]["as_of_date"] == "2026-04-10"


def test_latest_endpoint_empty_when_no_rows(pg_session: Session) -> None:
    from apps.api.src.main import app
    client = TestClient(app)
    resp = client.get("/api/factors/latest")
    assert resp.status_code == 200
    assert resp.json() == {"count": 0, "snapshots": []}
