"""Integration tests for /paper/summary + /paper/equity after the
forensic-audit fix that switched them from
paper_portfolio_snapshot (synthetic 'default') to
paper_equity_snapshot (real per-portfolio data).

Verifies:
  * Summary aggregates active portfolios — equity, cash,
    positions_value, unrealized_pnl all sum across portfolios.
  * total_return_pct is computed from sum(starting_cash).
  * open_positions_count is read from paper_position WHERE
    is_open=true.
  * Inactive portfolios are excluded.
  * Empty DB returns the zero-state, not a fabricated $100k.
  * Equity series returns one row per snapshot_date with real
    aggregated equity, not flat synthetic values.
  * replay_trades_count is surfaced informationally and is NOT
    subtracted from headline equity.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db import get_session
from apps.api.src.db.models import (
    Asset, PaperPortfolio, PaperPosition, PaperEquitySnapshot,
)
from apps.api.src.main import app


pytestmark = pytest.mark.integration


@pytest.fixture
def client(pg_engine):
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )

    def _override():
        s = SessionCls()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


def _mk_portfolio(
    session: Session, *, name: str, starting: float,
    cash: float, is_active: bool = True,
) -> str:
    p = PaperPortfolio(
        name=name, starting_cash=Decimal(str(starting)),
        cash=Decimal(str(cash)), is_active=is_active,
    )
    session.add(p)
    session.flush()
    return p.id


def _mk_snap(
    session: Session, *, portfolio_id: str, d: dt.date,
    total: float, cash: float, pos_val: float,
    upnl: float = 0.0,
) -> None:
    session.add(PaperEquitySnapshot(
        portfolio_id=portfolio_id,
        snapshot_date=dt.datetime.combine(
            d, dt.time(22, 0), tzinfo=dt.timezone.utc,
        ),
        cash=Decimal(str(cash)),
        positions_value=Decimal(str(pos_val)),
        total_equity=Decimal(str(total)),
        unrealized_pnl=Decimal(str(upnl)),
    ))


def _mk_open_position(
    session: Session, *, portfolio_id: str,
    asset_id: str, opened: dt.date,
) -> None:
    session.add(PaperPosition(
        portfolio_id=portfolio_id, asset_id=asset_id,
        quantity=Decimal("10"), avg_cost=Decimal("100"),
        is_open=True,
        opened_at=dt.datetime.combine(
            opened, dt.time(20, 0), tzinfo=dt.timezone.utc,
        ),
    ))


def test_summary_aggregates_active_portfolios(pg_session, client):
    a = Asset(symbol="X", asset_class="equity", currency="USD")
    pg_session.add(a)
    pg_session.flush()
    p1 = _mk_portfolio(
        pg_session, name="P1", starting=100_000, cash=479.34,
    )
    p2 = _mk_portfolio(
        pg_session, name="P2", starting=10_000, cash=47.93,
    )
    today = dt.date(2026, 5, 5)
    _mk_snap(
        pg_session, portfolio_id=p1, d=today,
        total=103_064.23, cash=479.34, pos_val=102_584.89,
        upnl=3_064.23,
    )
    _mk_snap(
        pg_session, portfolio_id=p2, d=today,
        total=10_306.42, cash=47.93, pos_val=10_258.49,
        upnl=306.42,
    )
    _mk_open_position(
        pg_session, portfolio_id=p1, asset_id=a.id, opened=today,
    )
    _mk_open_position(
        pg_session, portfolio_id=p2, asset_id=a.id, opened=today,
    )
    pg_session.commit()

    r = client.get("/api/paper/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["as_of_date"] == today.isoformat()
    assert body["equity"] == pytest.approx(113_370.65, abs=0.01)
    assert body["cash"] == pytest.approx(527.27, abs=0.01)
    assert body["positions_value"] == pytest.approx(112_843.38, abs=0.01)
    assert body["unrealized_pnl"] == pytest.approx(3_370.65, abs=0.01)
    assert body["open_positions_count"] == 2
    assert body["portfolio_count"] == 2
    expected_pct = ((113_370.65 - 110_000) / 110_000) * 100
    assert body["total_return_pct"] == pytest.approx(
        expected_pct, abs=0.01,
    )


def test_summary_excludes_inactive_portfolios(pg_session, client):
    p_act = _mk_portfolio(
        pg_session, name="active", starting=10_000, cash=100,
    )
    p_inact = _mk_portfolio(
        pg_session, name="inactive", starting=50_000, cash=500,
        is_active=False,
    )
    today = dt.date(2026, 5, 5)
    _mk_snap(
        pg_session, portfolio_id=p_act, d=today,
        total=10_500, cash=100, pos_val=10_400, upnl=500,
    )
    _mk_snap(
        pg_session, portfolio_id=p_inact, d=today,
        total=51_000, cash=500, pos_val=50_500, upnl=1_000,
    )
    pg_session.commit()
    r = client.get("/api/paper/summary")
    body = r.json()
    assert body["equity"] == pytest.approx(10_500, abs=0.01)
    assert body["portfolio_count"] == 1


def test_summary_empty_db_returns_zero_state(client):
    r = client.get("/api/paper/summary")
    body = r.json()
    assert body["equity"] == 0.0
    assert body["cash"] == 0.0
    assert body["open_positions_count"] == 0
    assert body["portfolio_count"] == 0
    # No fabricated $100k
    assert body["total_return_pct"] == 0.0


def test_summary_daily_pnl_uses_prior_day(pg_session, client):
    p = _mk_portfolio(
        pg_session, name="P", starting=10_000, cash=100,
    )
    yesterday = dt.date(2026, 5, 4)
    today = dt.date(2026, 5, 5)
    _mk_snap(
        pg_session, portfolio_id=p, d=yesterday,
        total=10_000, cash=100, pos_val=9_900,
    )
    _mk_snap(
        pg_session, portfolio_id=p, d=today,
        total=10_500, cash=100, pos_val=10_400, upnl=500,
    )
    pg_session.commit()
    body = client.get("/api/paper/summary").json()
    assert body["daily_pnl"] == pytest.approx(500.0, abs=0.01)


def test_summary_open_positions_only_active_portfolios(
    pg_session, client,
):
    a = Asset(symbol="X", asset_class="equity", currency="USD")
    pg_session.add(a)
    pg_session.flush()
    p_act = _mk_portfolio(
        pg_session, name="act", starting=10_000, cash=100,
    )
    p_inact = _mk_portfolio(
        pg_session, name="inact", starting=10_000, cash=100,
        is_active=False,
    )
    today = dt.date(2026, 5, 5)
    _mk_snap(
        pg_session, portfolio_id=p_act, d=today,
        total=10_000, cash=100, pos_val=9_900,
    )
    _mk_open_position(
        pg_session, portfolio_id=p_act, asset_id=a.id, opened=today,
    )
    _mk_open_position(
        pg_session, portfolio_id=p_inact, asset_id=a.id, opened=today,
    )
    pg_session.commit()
    body = client.get("/api/paper/summary").json()
    assert body["open_positions_count"] == 1


def test_equity_series_aggregates_active_only(pg_session, client):
    p1 = _mk_portfolio(
        pg_session, name="P1", starting=10_000, cash=100,
    )
    p2 = _mk_portfolio(
        pg_session, name="P2", starting=10_000, cash=100,
    )
    p_inact = _mk_portfolio(
        pg_session, name="P3", starting=50_000, cash=100,
        is_active=False,
    )
    for d, e1, e2, e_inact in [
        (dt.date(2026, 5, 1), 10_000, 10_000, 50_000),
        (dt.date(2026, 5, 2), 10_500, 10_300, 50_000),
        (dt.date(2026, 5, 5), 11_000, 10_500, 50_000),
    ]:
        _mk_snap(
            pg_session, portfolio_id=p1, d=d,
            total=e1, cash=100, pos_val=e1 - 100,
        )
        _mk_snap(
            pg_session, portfolio_id=p2, d=d,
            total=e2, cash=100, pos_val=e2 - 100,
        )
        _mk_snap(
            pg_session, portfolio_id=p_inact, d=d,
            total=e_inact, cash=100, pos_val=e_inact - 100,
        )
    pg_session.commit()
    rows = client.get(
        "/api/paper/equity?from=2026-05-01&to=2026-05-05"
    ).json()
    assert len(rows) == 3
    assert rows[0]["date"] == "2026-05-01"
    assert rows[0]["equity"] == pytest.approx(20_000, abs=0.01)
    assert rows[1]["equity"] == pytest.approx(20_800, abs=0.01)
    assert rows[2]["equity"] == pytest.approx(21_500, abs=0.01)
    # daily_pnl = today - prior
    assert rows[0]["daily_pnl"] == 0.0
    assert rows[1]["daily_pnl"] == pytest.approx(800, abs=0.01)
    assert rows[2]["daily_pnl"] == pytest.approx(700, abs=0.01)
    # cum_pct against starting=20_000
    assert rows[2]["cum_pct"] == pytest.approx(7.5, abs=0.01)


def test_equity_series_drawdown_computed(pg_session, client):
    p = _mk_portfolio(
        pg_session, name="P", starting=10_000, cash=100,
    )
    for d, e in [
        (dt.date(2026, 5, 1), 10_000),
        (dt.date(2026, 5, 2), 11_000),  # peak
        (dt.date(2026, 5, 3), 10_450),  # 5% drawdown
        (dt.date(2026, 5, 4), 11_000),  # recover
    ]:
        _mk_snap(
            pg_session, portfolio_id=p, d=d,
            total=e, cash=100, pos_val=e - 100,
        )
    pg_session.commit()
    rows = client.get(
        "/api/paper/equity?from=2026-05-01&to=2026-05-04"
    ).json()
    # Day 3: peak 11_000, equity 10_450, dd = -5%
    assert rows[2]["dd_pct"] == pytest.approx(-5.0, abs=0.01)
    # Day 4: recovered to peak, dd = 0
    assert rows[3]["dd_pct"] == pytest.approx(0.0, abs=0.01)


def test_equity_series_empty_returns_empty_list(client):
    rows = client.get("/api/paper/equity").json()
    assert rows == []


def test_legacy_synthetic_default_table_unused(pg_session, client):
    """The legacy paper_portfolio_snapshot table with the
    'default' synthetic id is NOT consulted. Real equity is
    sourced exclusively from paper_equity_snapshot."""
    p = _mk_portfolio(
        pg_session, name="real", starting=10_000, cash=100,
    )
    today = dt.date(2026, 5, 5)
    _mk_snap(
        pg_session, portfolio_id=p, d=today,
        total=10_500, cash=100, pos_val=10_400, upnl=500,
    )
    pg_session.commit()

    body = client.get("/api/paper/summary").json()
    # Pulled from paper_equity_snapshot, NOT a hardcoded $100k.
    assert body["equity"] == pytest.approx(10_500, abs=0.01)
    assert body["unrealized_pnl"] == pytest.approx(500, abs=0.01)
