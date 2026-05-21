"""Phase 11V - end-to-end turnover diagnostic against Postgres.

Verifies that diagnose_portfolio + health_summary produce the
expected output shape from real DB rows. Read-only — these tests
fail if the diagnostic ever writes to the DB.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db.models import (
    Asset,
    PaperPortfolio,
    PaperPosition,
    PaperTrade,
    Recommendation,
)
from apps.api.src.ml.data_collection_health import health_summary
from apps.api.src.ml.turnover_diagnostic import (
    diagnose_all_portfolios,
    diagnose_portfolio,
    predict_next_cycle,
)


pytestmark = pytest.mark.integration


@pytest.fixture
def session_factory(pg_engine):
    return sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )


def _seed_asset(session: Session, *, symbol: str) -> str:
    asset_id = f"asset-{symbol.lower()}"
    session.execute(text(
        """
        INSERT INTO asset
          (id, symbol, name, asset_class, exchange, currency,
           is_active, created_at, updated_at)
        VALUES
          (:id, :sym, :sym, 'equity', 'NASDAQ', 'USD',
           TRUE, now(), now())
        ON CONFLICT ON CONSTRAINT uq_asset_symbol_exchange DO NOTHING
        """
    ), {"id": asset_id, "sym": symbol})
    return asset_id


def _seed_portfolio(
    session: Session, *,
    name: str = "main", config_json: str | None = None,
) -> str:
    pid = f"pid-{name}"
    session.execute(text(
        """
        INSERT INTO paper_portfolio
          (id, name, starting_cash, cash, config_json,
           is_active, created_at, updated_at)
        VALUES
          (:id, :name, 100000, 100000, :cfg,
           TRUE, now(), now())
        """
    ), {"id": pid, "name": name, "cfg": config_json})
    return pid


def _seed_position(
    session: Session, *,
    portfolio_id: str, asset_id: str,
    opened_at: dt.datetime, is_open: bool = True,
    closed_at: dt.datetime | None = None,
) -> None:
    session.execute(text(
        """
        INSERT INTO paper_position
          (id, portfolio_id, asset_id, quantity, avg_cost, is_open,
           opened_at, closed_at, updated_at)
        VALUES
          (gen_random_uuid()::text, :pid, :aid, 10, 100, :open,
           :oat, :cat, now())
        """
    ), {
        "pid": portfolio_id, "aid": asset_id,
        "open": is_open, "oat": opened_at, "cat": closed_at,
    })


def _seed_trade(
    session: Session, *,
    portfolio_id: str, asset_id: str, side: str,
    fill_ts: dt.datetime, realized_pnl: Decimal | None = None,
) -> None:
    session.execute(text(
        """
        INSERT INTO paper_trade
          (id, portfolio_id, asset_id, side, quantity, fill_price,
           fill_ts, submitted_at, realized_pnl, commission, created_at)
        VALUES
          (gen_random_uuid()::text, :pid, :aid, :side, 10, 100,
           :fts, :fts, :rpnl, 0, now())
        """
    ), {
        "pid": portfolio_id, "aid": asset_id, "side": side,
        "fts": fill_ts, "rpnl": realized_pnl,
    })


def _seed_recommendation(
    session: Session, *,
    asset_id: str, action: str, generated_at: dt.datetime,
) -> None:
    session.execute(text(
        """
        INSERT INTO recommendation
          (id, asset_id, generated_at, action, conviction,
           model_version, snapshot_hash, created_at)
        VALUES
          (gen_random_uuid()::text, :aid, :gat, :action, 70,
           'v1', md5(gen_random_uuid()::text), now())
        """
    ), {"aid": asset_id, "gat": generated_at, "action": action})


@pytest.fixture
def _ensure_context_daily(pg_engine, pg_session):
    """context_daily is created via raw SQL in the macro backfill,
    not via Base.metadata. Health-summary tests need it present.
    Setup-only; teardown intentionally absent to avoid deadlocking
    against the per-test pg_session that is still in-transaction
    when fixture finalization runs."""
    with pg_engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS context_daily (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                as_of_date date NOT NULL,
                context_name text NOT NULL,
                status text NOT NULL,
                value_bool boolean NOT NULL,
                source_features text[] NOT NULL,
                logic_version text NOT NULL,
                logic_hash text NOT NULL,
                computed_at timestamptz NOT NULL DEFAULT now(),
                UNIQUE (as_of_date, context_name, logic_version)
            );
            DELETE FROM context_daily;
            """
        ))


# ---------------------------------------------------------------------------
# diagnose_portfolio
# ---------------------------------------------------------------------------

def test_diagnose_empty_portfolio_returns_zero_open(
    pg_session, session_factory,
):
    pid = _seed_portfolio(pg_session)
    pg_session.commit()
    portfolio = pg_session.get(PaperPortfolio, pid)
    as_of = dt.datetime(2026, 4, 29, 15, 0, tzinfo=dt.timezone.utc)
    out = diagnose_portfolio(
        pg_session, portfolio,
        as_of=as_of, lookback_days=30,
    )
    assert out["open_positions_count"] == 0
    assert out["max_open_positions"] == 30
    assert out["free_slots"] == 30
    assert out["pending_exits_count"] == 0
    assert out["expected_slots_after_next_run"] == 30
    assert out["blocked_buys_reason"] is None


def test_diagnose_full_portfolio_blocks_buys(
    pg_session, session_factory,
):
    # Pin max_open_positions=10 via override so 10 seeded positions
    # saturate. Default rose 10→30; this test asserts saturation
    # semantics, not the default value.
    pid = _seed_portfolio(
        pg_session, config_json='{"max_open_positions": 10}',
    )
    as_of = dt.datetime(2026, 4, 29, 15, 0, tzinfo=dt.timezone.utc)
    opened = as_of - dt.timedelta(days=5)
    for i in range(10):
        aid = _seed_asset(pg_session, symbol=f"S{i}")
        _seed_position(
            pg_session,
            portfolio_id=pid, asset_id=aid, opened_at=opened,
        )
    pg_session.commit()
    portfolio = pg_session.get(PaperPortfolio, pid)
    out = diagnose_portfolio(
        pg_session, portfolio,
        as_of=as_of, lookback_days=30,
    )
    assert out["open_positions_count"] == 10
    assert out["free_slots"] == 0
    assert out["blocked_buys_reason"] == "portfolio_full"


def test_diagnose_pending_exit_via_max_holding(
    pg_session, session_factory,
):
    pid = _seed_portfolio(pg_session)
    as_of = dt.datetime(2026, 4, 29, 15, 0, tzinfo=dt.timezone.utc)
    aid = _seed_asset(pg_session, symbol="OLD")
    # opened 45 days ago — exceeds default max_holding_days=30
    _seed_position(
        pg_session,
        portfolio_id=pid, asset_id=aid,
        opened_at=as_of - dt.timedelta(days=45),
    )
    pg_session.commit()
    portfolio = pg_session.get(PaperPortfolio, pid)
    out = diagnose_portfolio(
        pg_session, portfolio,
        as_of=as_of, lookback_days=30,
    )
    assert out["pending_exits_count"] == 1
    assert out["pending_exits"][0]["reason"] == "max_holding"
    assert out["pending_exits"][0]["age_days"] >= 30
    pred = predict_next_cycle(out)
    assert pred["will_close_old_positions"] is True
    assert pred["close_count"] == 1


def test_diagnose_pending_exit_via_rec_flip(
    pg_session, session_factory,
):
    pid = _seed_portfolio(pg_session)
    as_of = dt.datetime(2026, 4, 29, 15, 0, tzinfo=dt.timezone.utc)
    aid = _seed_asset(pg_session, symbol="FLIP")
    _seed_position(
        pg_session,
        portfolio_id=pid, asset_id=aid,
        opened_at=as_of - dt.timedelta(days=5),
    )
    _seed_recommendation(
        pg_session,
        asset_id=aid, action="Sell",
        generated_at=as_of - dt.timedelta(hours=4),
    )
    pg_session.commit()
    portfolio = pg_session.get(PaperPortfolio, pid)
    out = diagnose_portfolio(
        pg_session, portfolio,
        as_of=as_of, lookback_days=30,
    )
    assert out["pending_exits_count"] == 1
    assert out["pending_exits"][0]["reason"] == "rec_flip"
    assert out["pending_exits"][0]["latest_action"] == "Sell"


def test_diagnose_lookback_window_counts_buys_and_sells(
    pg_session, session_factory,
):
    pid = _seed_portfolio(pg_session)
    as_of = dt.datetime(2026, 4, 29, 15, 0, tzinfo=dt.timezone.utc)
    aid = _seed_asset(pg_session, symbol="W")
    # 3 buys + 2 sells inside window
    for i in range(3):
        _seed_trade(
            pg_session,
            portfolio_id=pid, asset_id=aid, side="buy",
            fill_ts=as_of - dt.timedelta(days=i + 1),
        )
    for i in range(2):
        _seed_trade(
            pg_session,
            portfolio_id=pid, asset_id=aid, side="sell",
            fill_ts=as_of - dt.timedelta(days=i + 1),
            realized_pnl=Decimal("50.00"),
        )
    # 1 buy outside window — must NOT be counted
    _seed_trade(
        pg_session,
        portfolio_id=pid, asset_id=aid, side="buy",
        fill_ts=as_of - dt.timedelta(days=60),
    )
    pg_session.commit()
    portfolio = pg_session.get(PaperPortfolio, pid)
    out = diagnose_portfolio(
        pg_session, portfolio,
        as_of=as_of, lookback_days=30,
    )
    lw = out["lookback_window"]
    assert lw["buys_count"] == 3
    assert lw["sells_count"] == 2
    assert lw["fill_count"] == 5
    assert Decimal(lw["realized_pnl_total"]) == Decimal("100.00")


def test_diagnose_uses_portfolio_config_max_open(
    pg_session, session_factory,
):
    pid = _seed_portfolio(
        pg_session,
        config_json=json.dumps({"max_open_positions": 25}),
    )
    pg_session.commit()
    portfolio = pg_session.get(PaperPortfolio, pid)
    as_of = dt.datetime(2026, 4, 29, 15, 0, tzinfo=dt.timezone.utc)
    out = diagnose_portfolio(
        pg_session, portfolio,
        as_of=as_of, lookback_days=30,
    )
    assert out["max_open_positions"] == 25
    assert out["free_slots"] == 25


def test_diagnose_all_portfolios_skips_inactive(
    pg_session, session_factory,
):
    _seed_portfolio(pg_session, name="active")
    pid_inactive = _seed_portfolio(pg_session, name="inactive")
    pg_session.execute(text(
        "UPDATE paper_portfolio SET is_active = FALSE WHERE id = :id"
    ), {"id": pid_inactive})
    pg_session.commit()
    as_of = dt.datetime(2026, 4, 29, 15, 0, tzinfo=dt.timezone.utc)
    out = diagnose_all_portfolios(
        pg_session, as_of=as_of, lookback_days=30,
    )
    names = {p["portfolio_name"] for p in out}
    assert names == {"active"}


def test_diagnose_does_not_mutate_db(
    pg_session, session_factory,
):
    pid = _seed_portfolio(pg_session)
    as_of = dt.datetime(2026, 4, 29, 15, 0, tzinfo=dt.timezone.utc)
    aid = _seed_asset(pg_session, symbol="STILL")
    _seed_position(
        pg_session,
        portfolio_id=pid, asset_id=aid,
        opened_at=as_of - dt.timedelta(days=5),
    )
    pg_session.commit()

    counts_before = {
        t: pg_session.scalar(
            text(f"SELECT count(*) FROM {t}")
        )
        for t in (
            "paper_portfolio", "paper_position",
            "paper_trade", "recommendation",
        )
    }
    portfolio = pg_session.get(PaperPortfolio, pid)
    diagnose_portfolio(
        pg_session, portfolio,
        as_of=as_of, lookback_days=30,
    )
    counts_after = {
        t: pg_session.scalar(
            text(f"SELECT count(*) FROM {t}")
        )
        for t in counts_before
    }
    assert counts_before == counts_after


# ---------------------------------------------------------------------------
# health_summary
# ---------------------------------------------------------------------------

def test_health_summary_top_level_keys(
    pg_session, session_factory, _ensure_context_daily,
):
    as_of = dt.datetime(2026, 4, 29, 15, 0, tzinfo=dt.timezone.utc)
    out = health_summary(
        pg_session, as_of=as_of, lookback_days=30,
    )
    for key in (
        "report_version", "as_of", "lookback_days",
        "price_bar", "context_daily",
        "recommendations", "candidate_ideas", "job_runs",
    ):
        assert key in out


def test_health_summary_missing_gates_when_empty(
    pg_session, session_factory, _ensure_context_daily,
):
    as_of = dt.datetime(2026, 4, 29, 15, 0, tzinfo=dt.timezone.utc)
    out = health_summary(
        pg_session, as_of=as_of, lookback_days=30,
    )
    cd = out["context_daily"]
    assert cd["all_present"] is False
    assert sorted(cd["missing_gates"]) == sorted([
        "rates_calm", "vrp_supportive",
        "credit_stable", "liquidity_expanding",
    ])
