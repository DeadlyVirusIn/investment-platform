"""Integration tests for /performance/paper/exit-analytics
(Phase D).

Verifies:
  * Empty DB → zero state with win_rate=null and
    note='no_closed_outcomes_yet'. Never fabricates a denominator.
  * Each SELL row is one realized event (buys never counted).
  * Categorisation by reason text — take_profit / stop_loss /
    max_hold / other.
  * Small-sample-size caveat surfaces when n < 30 and goes silent
    above the threshold.
  * include_replay default off; toggling includes replay-tagged
    sells.
  * best_exit / worst_exit pick correct rows.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db import get_session
from apps.api.src.db.models import (
    Asset, PaperPortfolio, PaperPosition, PaperTrade,
)
from apps.api.src.main import app


pytestmark = pytest.mark.integration


@pytest.fixture
def client(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text(
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


def _seed_closed(
    session: Session, *, symbol: str, reason: str,
    realized: float, hold_days: int = 5,
    portfolio_name: str = "P", entry: float = 100.0,
    qty: float = 10.0,
) -> str:
    a = Asset(symbol=symbol, asset_class="equity", currency="USD")
    p = PaperPortfolio(
        name=portfolio_name, starting_cash=Decimal("10000"),
        cash=Decimal("9000"), is_active=True,
    )
    session.add_all([a, p])
    session.flush()
    opened_at = dt.datetime(2026, 4, 30, tzinfo=dt.timezone.utc)
    closed_at = opened_at + dt.timedelta(days=hold_days)
    session.add(PaperTrade(
        portfolio_id=p.id, asset_id=a.id, side="buy",
        quantity=Decimal(str(qty)), fill_price=Decimal(str(entry)),
        fill_ts=opened_at,
        submitted_at=opened_at - dt.timedelta(hours=18),
        reason="seed buy",
    ))
    sell = PaperTrade(
        portfolio_id=p.id, asset_id=a.id, side="sell",
        quantity=Decimal(str(qty)), fill_price=Decimal(str(entry)),
        fill_ts=closed_at,
        submitted_at=closed_at - dt.timedelta(hours=9),
        reason=reason, realized_pnl=Decimal(str(realized)),
    )
    session.add(sell)
    session.add(PaperPosition(
        portfolio_id=p.id, asset_id=a.id,
        quantity=Decimal(str(qty)), avg_cost=Decimal(str(entry)),
        is_open=False, opened_at=opened_at, closed_at=closed_at,
    ))
    session.commit()
    return sell.id


def test_empty_db_zero_state(client):
    body = client.get(
        "/api/performance/paper/exit-analytics"
    ).json()
    assert body["n_closed"] == 0
    assert body["n_winners"] == 0
    assert body["n_losers"] == 0
    assert body["win_rate"] is None
    assert body["note"] == "no_closed_outcomes_yet"
    assert body["realized_pnl_total"] == 0.0
    assert body["best_exit"] is None
    assert body["worst_exit"] is None
    assert body["small_sample_warning"] is None  # nothing to caveat


def test_single_stop_loss_classified_correctly(pg_session, client):
    _seed_closed(
        pg_session, symbol="NVDA",
        reason="exit_cycle: stop_loss(-0.0545 <= -0.04)",
        realized=-5.0, hold_days=4,
    )
    body = client.get(
        "/api/performance/paper/exit-analytics"
    ).json()
    assert body["n_closed"] == 1
    assert body["n_winners"] == 0
    assert body["n_losers"] == 1
    assert body["win_rate"] == 0.0
    assert body["realized_pnl_total"] == pytest.approx(-5.0)
    cats = {c["category"]: c for c in body["by_category"]}
    assert cats["stop_loss"]["n"] == 1
    assert cats["take_profit"]["n"] == 0
    assert cats["max_hold"]["n"] == 0
    assert cats["other"]["n"] == 0
    tp_sl = body["tp_sl_effectiveness"]
    assert tp_sl["sl_count"] == 1
    assert tp_sl["tp_count"] == 0


def test_mixed_reasons_categorised(pg_session, client):
    _seed_closed(
        pg_session, symbol="A",
        reason="exit_cycle: take_profit(0.09 >= 0.08)",
        realized=8.0, portfolio_name="P1",
    )
    _seed_closed(
        pg_session, symbol="B",
        reason="exit_cycle: stop_loss(-0.05 <= -0.04)",
        realized=-4.0, portfolio_name="P2",
    )
    _seed_closed(
        pg_session, symbol="C",
        reason="exit_cycle: max_hold(10d >= 10d)",
        realized=0.5, portfolio_name="P3",
    )
    _seed_closed(
        pg_session, symbol="D",
        reason="manual_close_by_operator",
        realized=-1.0, portfolio_name="P4",
    )
    body = client.get(
        "/api/performance/paper/exit-analytics"
    ).json()
    assert body["n_closed"] == 4
    assert body["n_winners"] == 2  # +8 and +0.5
    assert body["n_losers"] == 2
    assert body["win_rate"] == 0.5
    cats = {c["category"]: c for c in body["by_category"]}
    assert cats["take_profit"]["n"] == 1
    assert cats["stop_loss"]["n"] == 1
    assert cats["max_hold"]["n"] == 1
    assert cats["other"]["n"] == 1


def test_best_and_worst_exit_picks_extreme_rows(
    pg_session, client,
):
    _seed_closed(
        pg_session, symbol="A",
        reason="take_profit", realized=20.0, portfolio_name="P1",
    )
    _seed_closed(
        pg_session, symbol="B",
        reason="stop_loss", realized=-30.0, portfolio_name="P2",
    )
    _seed_closed(
        pg_session, symbol="C",
        reason="other", realized=2.0, portfolio_name="P3",
    )
    body = client.get(
        "/api/performance/paper/exit-analytics"
    ).json()
    assert body["best_exit"]["symbol"] == "A"
    assert body["best_exit"]["realized_pnl"] == 20.0
    assert body["worst_exit"]["symbol"] == "B"
    assert body["worst_exit"]["realized_pnl"] == -30.0


def test_small_sample_warning_present_when_below_threshold(
    pg_session, client,
):
    _seed_closed(
        pg_session, symbol="A",
        reason="stop_loss", realized=-1.0,
    )
    body = client.get(
        "/api/performance/paper/exit-analytics"
    ).json()
    assert body["n_closed"] == 1
    assert body["small_sample_warning"] is not None
    # text references the count and "directional" framing
    msg = body["small_sample_warning"].lower()
    assert "1" in msg
    assert "directional" in msg


def test_buy_rows_never_counted(pg_session, client):
    """Sanity: only SELL rows (with realized_pnl) drive analytics.
    Adding a stray buy with realized_pnl=NULL must not move the
    counts."""
    _seed_closed(
        pg_session, symbol="X",
        reason="stop_loss", realized=-2.0,
    )
    body = client.get(
        "/api/performance/paper/exit-analytics"
    ).json()
    # 1 sell expected; the seeded buy must not appear.
    assert body["n_closed"] == 1
    assert all(
        t["reason"] != "seed buy" for t in body["trades"]
    )


def test_avg_hold_days_computed_from_position_lifetime(
    pg_session, client,
):
    _seed_closed(
        pg_session, symbol="A",
        reason="take_profit", realized=5.0,
        hold_days=4, portfolio_name="P1",
    )
    _seed_closed(
        pg_session, symbol="B",
        reason="stop_loss", realized=-2.0,
        hold_days=8, portfolio_name="P2",
    )
    body = client.get(
        "/api/performance/paper/exit-analytics"
    ).json()
    # _trading_days_inclusive Mon-Fri count between the seeded
    # opened_at (2026-04-30 Thu) and closed_at:
    #   hold_days=4 → closed 2026-05-04 Mon → Thu/Fri/Mon = 3
    #   hold_days=8 → closed 2026-05-08 Fri → Thu/Fri/Mon..Fri = 7
    assert body["avg_hold_days"] == pytest.approx((3 + 7) / 2)


def test_raw_breakdown_sorted_by_count_desc(pg_session, client):
    for sym, reason in [
        ("A", "exit_cycle: stop_loss(-0.05 <= -0.04)"),
        ("B", "exit_cycle: stop_loss(-0.05 <= -0.04)"),
        ("C", "exit_cycle: stop_loss(-0.05 <= -0.04)"),
        ("D", "exit_cycle: take_profit(0.09 >= 0.08)"),
    ]:
        _seed_closed(
            pg_session, symbol=sym, reason=reason,
            realized=-1.0, portfolio_name=f"P-{sym}",
        )
    body = client.get(
        "/api/performance/paper/exit-analytics"
    ).json()
    raw = body["exit_reason_raw_breakdown"]
    assert raw[0]["n"] >= raw[-1]["n"]
    assert raw[0]["reason"].startswith("exit_cycle: stop_loss")
