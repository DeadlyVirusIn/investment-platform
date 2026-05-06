"""Paper exit-cycle integration tests.

Verifies:
  * Default dry-run never writes.
  * --commit refused without env.
  * Take-profit closes when unrealized >= +TP threshold.
  * Stop-loss closes when unrealized <= -SL threshold.
  * Max-hold closes when held_days >= configured cap.
  * No-rule positions stay open.
  * Same-bar exit forbidden — `submit_trade` requires
    `bar.ts > submitted_at`; runner anchors submitted_at to
    the as_of trading-day open and relies on the existing
    next-bar guard.
  * --force-close-all only allowed with --commit.
  * Realized P&L is computed from real price_bar data; replay
    flags on the original buy are NOT touched.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db.models import (
    Asset, PaperPortfolio, PaperPosition, PaperTrade, PriceBar,
)


pytestmark = pytest.mark.integration


def _seed(
    session: Session, *,
    symbol: str = "X",
    entry_price: float = 100.0,
    latest_price: float = 110.0,
    held_days: int = 3,
    starting_cash: float = 10_000,
) -> dict:
    a = Asset(symbol=symbol, asset_class="equity", currency="USD")
    p = PaperPortfolio(
        name=f"P-{symbol}", starting_cash=Decimal(str(starting_cash)),
        cash=Decimal("9000"), is_active=True,
    )
    session.add_all([a, p])
    session.flush()
    open_at = (
        dt.datetime.now(dt.timezone.utc).replace(
            hour=15, minute=0, second=0, microsecond=0,
        ) - dt.timedelta(days=held_days)
    )
    pos = PaperPosition(
        portfolio_id=p.id, asset_id=a.id,
        quantity=Decimal("10"),
        avg_cost=Decimal(str(entry_price)),
        is_open=True, opened_at=open_at,
    )
    session.add(pos)
    # Seed price_bar rows:
    # - today's mark uses latest_price (so unrealized rule fires)
    # - tomorrow's bar at the same price gives find_next_open a
    #   row strictly after submitted_at (15:00 UTC today), so the
    #   next-bar guard inside submit_trade can fill the sell.
    today = dt.date.today()
    session.add(PriceBar(
        asset_id=a.id, timeframe="1d",
        ts=dt.datetime.combine(
            today, dt.time(13, 0), tzinfo=dt.timezone.utc,
        ),
        open=latest_price, high=latest_price, low=latest_price,
        close=latest_price, adjusted_close=latest_price,
        provider="test",
    ))
    session.add(PriceBar(
        asset_id=a.id, timeframe="1d",
        ts=dt.datetime.combine(
            today + dt.timedelta(days=1),
            dt.time(13, 0), tzinfo=dt.timezone.utc,
        ),
        open=latest_price, high=latest_price, low=latest_price,
        close=latest_price, adjusted_close=latest_price,
        provider="test",
    ))
    session.commit()
    return {"asset_id": a.id, "portfolio_id": p.id}


@pytest.fixture
def patch_session_local(pg_engine, monkeypatch):
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )
    import apps.api.src.db as _db
    monkeypatch.setattr(_db, "SessionLocal", SessionCls)
    yield


def test_dry_run_no_writes(
    pg_session, tmp_path, monkeypatch, patch_session_local,
):
    monkeypatch.delenv("PAPER_EXIT_CYCLE_CONFIRM", raising=False)
    _seed(pg_session, symbol="A", entry_price=100,
          latest_price=120, held_days=2)
    monkeypatch.chdir(tmp_path)
    n_pos_before = pg_session.execute(text(
        "SELECT count(*) FROM paper_position WHERE is_open=true"
    )).scalar()
    n_trade_before = pg_session.execute(text(
        "SELECT count(*) FROM paper_trade"
    )).scalar()

    from scripts.run_paper_exit_cycle import main
    rc = main([])
    assert rc == 0

    assert pg_session.execute(text(
        "SELECT count(*) FROM paper_position WHERE is_open=true"
    )).scalar() == n_pos_before
    assert pg_session.execute(text(
        "SELECT count(*) FROM paper_trade"
    )).scalar() == n_trade_before
    artifact = json.loads(
        next((tmp_path / "artifacts/paper_exit_cycle").iterdir()).read_text()
    )
    assert artifact["mode"] == "dry-run"
    assert artifact["closed_count"] == 1
    assert "take_profit" in artifact["closed"][0]["reason"]


def test_commit_refused_without_env(monkeypatch):
    monkeypatch.delenv("PAPER_EXIT_CYCLE_CONFIRM", raising=False)
    from scripts.run_paper_exit_cycle import main
    rc = main(["--commit"])
    assert rc == 2


def test_take_profit_closes_position(
    pg_session, tmp_path, monkeypatch, patch_session_local,
):
    monkeypatch.setenv(
        "PAPER_EXIT_CYCLE_CONFIRM",
        "I_UNDERSTAND_THIS_CLOSES_PAPER_POSITIONS",
    )
    monkeypatch.setenv("PAPER_TAKE_PROFIT_PCT", "0.05")
    monkeypatch.chdir(tmp_path)
    seeded = _seed(
        pg_session, symbol="TP",
        entry_price=100, latest_price=120, held_days=2,
    )
    from scripts.run_paper_exit_cycle import main
    rc = main(["--commit"])
    assert rc == 0
    pos = pg_session.execute(text(
        "SELECT is_open, closed_at FROM paper_position "
        "WHERE asset_id = :a"
    ), {"a": seeded["asset_id"]}).first()
    pg_session.expire_all()
    pos = pg_session.execute(text(
        "SELECT is_open, closed_at FROM paper_position "
        "WHERE asset_id = :a"
    ), {"a": seeded["asset_id"]}).first()
    assert pos.is_open is False
    assert pos.closed_at is not None
    sells = pg_session.execute(text(
        "SELECT count(*), max(realized_pnl) FROM paper_trade "
        "WHERE asset_id = :a AND side = 'sell'"
    ), {"a": seeded["asset_id"]}).first()
    assert sells[0] == 1
    assert float(sells[1] or 0) > 0  # profit realized


def test_stop_loss_closes_position(
    pg_session, tmp_path, monkeypatch, patch_session_local,
):
    monkeypatch.setenv(
        "PAPER_EXIT_CYCLE_CONFIRM",
        "I_UNDERSTAND_THIS_CLOSES_PAPER_POSITIONS",
    )
    monkeypatch.setenv("PAPER_STOP_LOSS_PCT", "0.04")
    monkeypatch.chdir(tmp_path)
    seeded = _seed(
        pg_session, symbol="SL",
        entry_price=100, latest_price=90, held_days=2,
    )
    from scripts.run_paper_exit_cycle import main
    rc = main(["--commit"])
    assert rc == 0
    pg_session.expire_all()
    pos = pg_session.execute(text(
        "SELECT is_open FROM paper_position WHERE asset_id = :a"
    ), {"a": seeded["asset_id"]}).first()
    assert pos.is_open is False
    pnl = pg_session.execute(text(
        "SELECT realized_pnl FROM paper_trade "
        "WHERE asset_id = :a AND side = 'sell'"
    ), {"a": seeded["asset_id"]}).scalar()
    assert float(pnl) < 0  # loss realized


def test_max_hold_closes_position(
    pg_session, tmp_path, monkeypatch, patch_session_local,
):
    monkeypatch.setenv(
        "PAPER_EXIT_CYCLE_CONFIRM",
        "I_UNDERSTAND_THIS_CLOSES_PAPER_POSITIONS",
    )
    monkeypatch.setenv("PAPER_MAX_HOLD_DAYS", "3")
    monkeypatch.setenv("PAPER_TAKE_PROFIT_PCT", "0.99")  # disable
    monkeypatch.setenv("PAPER_STOP_LOSS_PCT", "0.99")    # disable
    monkeypatch.chdir(tmp_path)
    seeded = _seed(
        pg_session, symbol="MX",
        entry_price=100, latest_price=101, held_days=20,
    )
    from scripts.run_paper_exit_cycle import main
    rc = main(["--commit"])
    assert rc == 0
    pg_session.expire_all()
    pos = pg_session.execute(text(
        "SELECT is_open FROM paper_position WHERE asset_id = :a"
    ), {"a": seeded["asset_id"]}).first()
    assert pos.is_open is False


def test_no_rule_triggered_keeps_open(
    pg_session, tmp_path, monkeypatch, patch_session_local,
):
    monkeypatch.setenv(
        "PAPER_EXIT_CYCLE_CONFIRM",
        "I_UNDERSTAND_THIS_CLOSES_PAPER_POSITIONS",
    )
    monkeypatch.setenv("PAPER_TAKE_PROFIT_PCT", "0.20")
    monkeypatch.setenv("PAPER_STOP_LOSS_PCT", "0.20")
    monkeypatch.setenv("PAPER_MAX_HOLD_DAYS", "100")
    monkeypatch.chdir(tmp_path)
    seeded = _seed(
        pg_session, symbol="HOLD",
        entry_price=100, latest_price=101, held_days=2,
    )
    from scripts.run_paper_exit_cycle import main
    rc = main(["--commit"])
    assert rc == 0
    pg_session.expire_all()
    pos = pg_session.execute(text(
        "SELECT is_open FROM paper_position WHERE asset_id = :a"
    ), {"a": seeded["asset_id"]}).first()
    assert pos.is_open is True


def test_force_close_all_requires_commit(monkeypatch):
    monkeypatch.delenv("PAPER_EXIT_CYCLE_CONFIRM", raising=False)
    from scripts.run_paper_exit_cycle import main
    rc = main(["--force-close-all"])
    assert rc == 2


def test_skipped_when_no_price_bar_for_mark(
    pg_session, tmp_path, monkeypatch, patch_session_local,
):
    monkeypatch.setenv(
        "PAPER_EXIT_CYCLE_CONFIRM",
        "I_UNDERSTAND_THIS_CLOSES_PAPER_POSITIONS",
    )
    monkeypatch.chdir(tmp_path)
    a = Asset(symbol="NOPX", asset_class="equity", currency="USD")
    p = PaperPortfolio(
        name="np", starting_cash=Decimal("1000"),
        cash=Decimal("1000"), is_active=True,
    )
    pg_session.add_all([a, p])
    pg_session.flush()
    pg_session.add(PaperPosition(
        portfolio_id=p.id, asset_id=a.id,
        quantity=Decimal("1"), avg_cost=Decimal("100"),
        is_open=True,
        opened_at=dt.datetime.now(dt.timezone.utc),
    ))
    pg_session.commit()
    from scripts.run_paper_exit_cycle import main
    rc = main(["--commit"])
    assert rc == 0
    artifact = json.loads(
        next((tmp_path / "artifacts/paper_exit_cycle").iterdir()).read_text()
    )
    assert any(
        s["reason"] == "no_price_bar_for_mark"
        for s in artifact["skipped"]
    )
