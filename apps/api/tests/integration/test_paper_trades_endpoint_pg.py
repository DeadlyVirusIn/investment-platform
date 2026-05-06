"""Integration tests for /paper/trades after the legacy table swap.

Verifies:
  * Reads from `paper_trade` joined to `paper_position` instead of
    the empty legacy `paper_trade_log`.
  * Returns real rows with shape compatible with the existing
    operator UI (entry_date, entry_price, status, etc.).
  * Status filter accepts 'open' / 'closed'.
  * `is_replay` flag surfaces replay-recovered trades when the
    manifest table exists; falls back to False when missing
    (testcontainer-friendly).
  * No fabricated rows: empty DB returns [].
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


def _seed(session: Session, *, symbol="NVDA", is_open=True) -> dict:
    """Seed one buy + (when closed) one matching sell + paper_position.

    Mirrors the real lifecycle: a closed position has BOTH a buy
    paper_trade row and a sell paper_trade row. Earlier the
    fixture only seeded a buy, which masked the dedup bug fixed
    in this phase (buys + sells both got status='closed').
    """
    a = Asset(symbol=symbol, asset_class="equity", currency="USD")
    session.add(a)
    p = PaperPortfolio(
        name=f"P-{symbol}", starting_cash=Decimal("10000"),
        cash=Decimal("9000"), is_active=True,
    )
    session.add(p)
    session.flush()
    fill_ts = dt.datetime(2026, 4, 30, 0, tzinfo=dt.timezone.utc)
    buy = PaperTrade(
        portfolio_id=p.id, asset_id=a.id, side="buy",
        quantity=Decimal("0.5"), fill_price=Decimal("210"),
        fill_ts=fill_ts,
        submitted_at=dt.datetime(
            2026, 4, 29, 21, tzinfo=dt.timezone.utc,
        ),
        reason="auto_trader: Buy rec",
    )
    session.add(buy)
    sell_id: str | None = None
    if not is_open:
        sell_ts = fill_ts + dt.timedelta(days=2)
        sell = PaperTrade(
            portfolio_id=p.id, asset_id=a.id, side="sell",
            quantity=Decimal("0.5"), fill_price=Decimal("200"),
            fill_ts=sell_ts,
            submitted_at=sell_ts - dt.timedelta(hours=9),
            reason="exit_cycle: stop_loss",
            realized_pnl=Decimal("-5.00"),
        )
        session.add(sell)
        session.flush()
        sell_id = sell.id
    session.flush()
    pos = PaperPosition(
        portfolio_id=p.id, asset_id=a.id,
        quantity=Decimal("0.5"), avg_cost=Decimal("210"),
        is_open=is_open, opened_at=fill_ts,
        closed_at=(
            None if is_open
            else fill_ts + dt.timedelta(days=2)
        ),
    )
    session.add(pos)
    session.commit()
    return {
        "trade_id": buy.id, "sell_trade_id": sell_id,
        "asset_id": a.id, "portfolio_id": p.id,
    }


def test_returns_real_paper_trade_rows(pg_session, client):
    _seed(pg_session, symbol="NVDA", is_open=True)
    body = client.get("/api/paper/trades").json()
    assert len(body) == 1
    row = body[0]
    assert row["instrument"] == "NVDA"
    assert row["entry_date"] == "2026-04-30"
    assert row["entry_price"] == 210.0
    assert row["status"] == "open"
    assert row["engine"] == "paper"
    assert row["is_replay"] is False
    assert row["quantity"] == 0.5


def test_status_open_filter(pg_session, client):
    _seed(pg_session, symbol="NVDA", is_open=True)
    _seed(pg_session, symbol="AMZN", is_open=False)
    open_rows = client.get("/api/paper/trades?status=open").json()
    closed_rows = client.get("/api/paper/trades?status=closed").json()
    assert {r["instrument"] for r in open_rows} == {"NVDA"}
    assert {r["instrument"] for r in closed_rows} == {"AMZN"}
    # Side semantics:
    #   open rows are BUYs of currently-open positions;
    #   closed rows are SELLs (realized events).
    assert all(r.get("side") == "buy" for r in open_rows)
    assert all(r.get("side") == "sell" for r in closed_rows)


def test_no_duplicate_closed_rows_for_buy_plus_sell(pg_session, client):
    """Regression: a closed position must emit exactly ONE
    'closed' row (the sell), not also surface its companion buy
    as a duplicate 'closed' row. Reproduces the
    Realized-History-shows-4-instead-of-2 bug."""
    _seed(pg_session, symbol="NVDA", is_open=False)
    closed_rows = client.get("/api/paper/trades?status=closed").json()
    assert len(closed_rows) == 1, closed_rows
    assert closed_rows[0]["side"] == "sell"
    assert closed_rows[0]["instrument"] == "NVDA"
    assert closed_rows[0]["reason"].startswith("exit_cycle")
    # Realized pnl is preserved on the sell row.
    assert closed_rows[0]["pnl_dollar"] == -5.00
    # The full feed contains both trade events (buy + sell) since
    # nothing is deleted from paper_trade — the buy just shows as
    # status='open' is filtered out (is_open=FALSE), so the buy
    # row should NOT appear at all in the unfiltered list.
    full_rows = client.get("/api/paper/trades").json()
    sides = sorted(r["side"] for r in full_rows)
    assert sides == ["sell"], (
        "closed-position buy must not be re-emitted alongside its "
        f"sell row; got sides={sides}"
    )


def test_empty_db_returns_empty_list(client):
    body = client.get("/api/paper/trades").json()
    assert body == []


def test_is_replay_flag_falls_back_when_manifest_missing(
    pg_session, client,
):
    """testcontainer doesn't create replay_recovery_manifest;
    endpoint must not 500 — should return is_replay=False for
    every row."""
    _seed(pg_session, symbol="NVDA", is_open=True)
    body = client.get("/api/paper/trades").json()
    assert all(r["is_replay"] is False for r in body)


def test_reason_field_preserved(pg_session, client):
    _seed(pg_session, symbol="NVDA", is_open=True)
    body = client.get("/api/paper/trades").json()
    assert body[0]["reason"] == "auto_trader: Buy rec"


def test_does_not_read_paper_trade_log(pg_session, client):
    """Sanity: even if the legacy paper_trade_log table is
    missing, the endpoint still returns rows from paper_trade."""
    _seed(pg_session, symbol="NVDA", is_open=True)
    # Drop the legacy table to prove the endpoint does not
    # consult it. Re-create empty so other tests in the same
    # session still work.
    pg_session.execute(text(
        "DROP TABLE IF EXISTS paper_trade_log CASCADE"
    ))
    pg_session.commit()
    body = client.get("/api/paper/trades").json()
    assert len(body) == 1
    assert body[0]["instrument"] == "NVDA"
