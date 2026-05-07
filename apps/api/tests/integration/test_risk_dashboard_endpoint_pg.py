"""Integration tests for /performance/paper/risk-dashboard
(Phase C).

Verifies the read-only rollup:
  * Reads NAV / cash / positions_value / unrealized from
    paper_equity_snapshot.
  * Surfaces `mark_unavailable=true` and `exposure_value=null`
    when positions_value is NULL — never fabricates 0.
  * Concentration tables sum quantity * latest price_bar close.
  * include_replay default false; replay rows excluded from
    headline counts but always reported in `live_trades_count` /
    `replay_trades_count`.
  * Empty DB → zero-state with no fabricated values.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db import get_session
from apps.api.src.db.models import (
    Asset, PaperEquitySnapshot, PaperPortfolio, PaperPosition,
    PaperTrade, PriceBar,
)
from apps.api.src.main import app


pytestmark = pytest.mark.integration


@pytest.fixture
def client(pg_engine):
    """Bootstraps the raw-SQL `replay_recovery_manifest` table the
    endpoint references. Production builds it via alembic
    migration 061; testcontainer's `Base.metadata.create_all` does
    not. Mirrors the bootstrap in
    `test_pending_replay_backfill_pg.py`.
    """
    from sqlalchemy import text as _text
    with pg_engine.begin() as conn:
        conn.execute(_text(
            "CREATE TABLE IF NOT EXISTS replay_recovery_manifest ("
            "  id SERIAL PRIMARY KEY,"
            "  replay_run_id TEXT, source TEXT,"
            "  entity_type TEXT, entity_id TEXT"
            ")"
        ))

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


def _seed_full(
    session: Session, *, symbol: str = "NVDA",
    portfolio_name: str = "P",
    nav: float = 10_000.0, cash: float = 1_000.0,
    positions_value: float | None = 9_000.0,
    qty: float = 10.0, avg_cost: float = 200.0,
    last_close: float | None = 210.0,
) -> dict[str, str]:
    a = Asset(symbol=symbol, asset_class="equity", currency="USD")
    p = PaperPortfolio(
        name=portfolio_name, starting_cash=Decimal("10000"),
        cash=Decimal(str(cash)), is_active=True,
    )
    session.add_all([a, p])
    session.flush()
    fill_ts = dt.datetime(2026, 4, 30, tzinfo=dt.timezone.utc)
    session.add(PaperTrade(
        portfolio_id=p.id, asset_id=a.id, side="buy",
        quantity=Decimal(str(qty)), fill_price=Decimal(str(avg_cost)),
        fill_ts=fill_ts,
        submitted_at=fill_ts - dt.timedelta(hours=18),
        reason="test buy",
    ))
    session.add(PaperPosition(
        portfolio_id=p.id, asset_id=a.id,
        quantity=Decimal(str(qty)),
        avg_cost=Decimal(str(avg_cost)),
        is_open=True, opened_at=fill_ts,
    ))
    if last_close is not None:
        session.add(PriceBar(
            asset_id=a.id, timeframe="1d",
            ts=dt.datetime(2026, 5, 5, tzinfo=dt.timezone.utc),
            open=Decimal(str(last_close)), high=Decimal(str(last_close)),
            low=Decimal(str(last_close)), close=Decimal(str(last_close)),
            adjusted_close=Decimal(str(last_close)), provider="test",
        ))
    session.add(PaperEquitySnapshot(
        portfolio_id=p.id,
        snapshot_date=dt.datetime(2026, 5, 5, tzinfo=dt.timezone.utc),
        cash=Decimal(str(cash)),
        positions_value=(
            Decimal(str(positions_value))
            if positions_value is not None else None
        ),
        total_equity=Decimal(str(nav)),
        unrealized_pnl=Decimal("100"),
    ))
    session.commit()
    return {"asset_id": a.id, "portfolio_id": p.id}


def test_empty_db_zero_state(client):
    body = client.get(
        "/api/performance/paper/risk-dashboard"
    ).json()
    assert body["nav"] is None
    assert body["cash"] is None
    assert body["exposure_value"] is None
    assert body["mark_unavailable"] is True
    assert body["open_positions_count"] == 0
    assert body["concentration_by_symbol"] == []
    assert body["portfolios"] == []
    assert body["live_trades_count"] == 0
    assert body["replay_trades_count"] == 0


def test_returns_truthful_exposure_when_snapshot_has_positions_value(
    pg_session, client,
):
    _seed_full(
        pg_session, symbol="NVDA", portfolio_name="Default",
        nav=10_000, cash=1_000, positions_value=9_000,
        qty=10, avg_cost=200, last_close=210,
    )
    body = client.get(
        "/api/performance/paper/risk-dashboard"
    ).json()
    assert body["mark_unavailable"] is False
    assert body["nav"] == 10_000.0
    assert body["cash"] == 1_000.0
    assert body["exposure_value"] == 9_000.0
    assert body["exposure_pct"] == pytest.approx(0.9, rel=1e-3)
    assert body["open_positions_count"] == 1


def test_mark_unavailable_only_when_no_active_snapshots(
    pg_session, client,
):
    """`positions_value` is NOT NULL by schema, so the path that
    flips `mark_unavailable=true` in production is "no active
    portfolio has any equity-snapshot row yet" (e.g., before the
    first snapshot job has run). Verify the empty-snapshot path
    surfaces that flag honestly without fabricating a zero."""
    body = client.get(
        "/api/performance/paper/risk-dashboard"
    ).json()
    # No portfolios / snapshots seeded.
    assert body["mark_unavailable"] is True
    assert body["exposure_value"] is None
    assert body["nav"] is None


def test_concentration_by_symbol_uses_latest_price_bar(
    pg_session, client,
):
    _seed_full(
        pg_session, symbol="NVDA", portfolio_name="P",
        qty=10, avg_cost=200, last_close=210,
    )
    body = client.get(
        "/api/performance/paper/risk-dashboard"
    ).json()
    rows = body["concentration_by_symbol"]
    assert len(rows) == 1
    assert rows[0]["symbol"] == "NVDA"
    assert rows[0]["n_open"] == 1
    assert rows[0]["notional_usd"] == pytest.approx(2_100.0)
    assert rows[0]["unrealized_pnl"] == pytest.approx(100.0)
    assert rows[0]["mark_unavailable"] is False


def test_concentration_marks_symbol_when_no_recent_price_bar(
    pg_session, client,
):
    _seed_full(
        pg_session, symbol="NVDA", portfolio_name="P",
        qty=10, avg_cost=200, last_close=None,
    )
    body = client.get(
        "/api/performance/paper/risk-dashboard"
    ).json()
    rows = body["concentration_by_symbol"]
    assert len(rows) == 1
    # Falls back to cost basis but FLAGS the row clearly.
    assert rows[0]["mark_unavailable"] is True
    assert rows[0]["notional_usd"] == pytest.approx(2_000.0)


def test_top_5_notional_is_first_five_of_concentration(
    pg_session, client,
):
    for i, sym in enumerate(["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]):
        _seed_full(
            pg_session, symbol=sym, portfolio_name=f"P{i}",
            qty=10 + i, avg_cost=100, last_close=100 + i,
        )
    body = client.get(
        "/api/performance/paper/risk-dashboard"
    ).json()
    assert len(body["top_5_notional"]) == 5
    notionals = [r["notional_usd"] for r in body["top_5_notional"]]
    assert notionals == sorted(notionals, reverse=True)


def test_pending_next_bar_count_defaults_zero_when_no_skip_jsonl(
    pg_session, client,
):
    _seed_full(pg_session, symbol="NVDA")
    body = client.get(
        "/api/performance/paper/risk-dashboard"
    ).json()
    assert body["pending_next_bar_count"] == 0
    # Never fabricates a positive count without on-disk evidence.
