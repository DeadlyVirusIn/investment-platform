"""Phase 11X.2 — controlled paper-only pilot integration tests.

Covers every gating condition spelled out in the spec:
  * Flag off → no pilot trade.
  * Flag on + eligible → exactly one paper_trade row, sized at
    0.25× notional, reason tagged with `safe_gate_evolution_pilot`.
  * macro_favorable_count=0 → blocked.
  * unknown_count > 0 → blocked.
  * Price regime unfavorable → blocked.
  * Production trade already opened → blocked.
  * Pilot trade already opened today → blocked (idempotent).
  * Max 1 trade/day enforced.
  * Size multiplier honored.
  * Paper-only fields used (no broker / live columns).

No selector / engine A / engine B / candidate-scoring code is
imported here. The shadow row is seeded directly so we exercise
the pilot path in isolation.
"""

from __future__ import annotations

import datetime as dt
import importlib
import json
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Module-scoped fixture — apply migrations 054 and 055 + ensure
# context_daily, paper_trade, paper_portfolio, asset, price_bar exist.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pilot_schema(pg_engine):
    """Ensure every table the pilot path reads/writes exists in the
    integration testcontainer. ORM tables are already created by
    `Base.metadata.create_all` in conftest. We need to additionally
    create raw-SQL tables (`context_daily`, `safe_gate_evolution_shadow`)
    via their migrations."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with pg_engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS context_daily (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                as_of_date date NOT NULL,
                context_name text NOT NULL,
                status text NOT NULL,
                value_bool boolean,
                source_features text[] NOT NULL,
                logic_version text NOT NULL,
                logic_hash text NOT NULL,
                computed_at timestamptz NOT NULL DEFAULT now(),
                CONSTRAINT ux_context_daily_name_ver_date
                  UNIQUE (as_of_date, context_name, logic_version),
                CONSTRAINT ck_context_daily_status
                  CHECK (status IN ('production','candidate','diagnostic',
                                    'insufficient_data','missing_data','stale_data'))
            )
            """
        ))
    mod_054 = importlib.import_module(
        "infra.alembic.versions.054_safe_gate_evolution_shadow"
    )
    with pg_engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod_054.upgrade()

    yield pg_engine

    # Best-effort teardown (safe even on shared DB — DROP IF EXISTS).
    with pg_engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE IF EXISTS public.safe_gate_evolution_shadow"
        ))
        conn.execute(text(
            "DROP TABLE IF EXISTS context_daily CASCADE"
        ))


@pytest.fixture
def session(pilot_schema, pg_session):
    """Per-test isolated session — wipe pilot-relevant tables."""
    pg_session.execute(text(
        "TRUNCATE TABLE safe_gate_evolution_shadow"
    ))
    pg_session.execute(text("TRUNCATE TABLE context_daily"))
    pg_session.commit()
    yield pg_session


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_portfolio(s: Session) -> str:
    pid = "pf-pilot-test"
    s.execute(text(
        """
        INSERT INTO paper_portfolio
          (id, name, starting_cash, cash, is_active,
           created_at, updated_at)
        VALUES (:id, 'pilot-test', 100000, 100000, TRUE,
                now(), now())
        ON CONFLICT (id) DO NOTHING
        """
    ), {"id": pid})
    s.commit()
    return pid


def _seed_asset(s: Session, *, symbol: str) -> str:
    aid = f"asset-{symbol.lower()}"
    s.execute(text(
        """
        INSERT INTO asset
          (id, symbol, name, asset_class, exchange, currency,
           is_active, created_at, updated_at)
        VALUES (:id, :sym, :sym, 'equity', 'NASDAQ', 'USD',
                TRUE, now(), now())
        ON CONFLICT ON CONSTRAINT uq_asset_symbol_exchange DO NOTHING
        """
    ), {"id": aid, "sym": symbol})
    s.commit()
    return aid


def _seed_price_bar(
    s: Session, *, asset_id: str, run_date: dt.date, close: float,
):
    s.execute(text(
        """
        INSERT INTO price_bar
          (id, asset_id, ts, timeframe, open, high, low,
           close, adjusted_close, volume, provider, created_at)
        VALUES (gen_random_uuid()::text, :aid,
                :ts, '1d',
                :px, :px, :px, :px, :px, 1000000, 'test', now())
        ON CONFLICT DO NOTHING
        """
    ), {"aid": asset_id, "ts": dt.datetime.combine(
        run_date, dt.time(20, 0), tzinfo=dt.timezone.utc,
    ), "px": close})
    s.commit()


def _seed_macro(
    s: Session, *, run_date: dt.date,
    favorable: int = 1, unknown: int = 0,
):
    """Seed 4 production gates. `favorable` of them = TRUE,
    `unknown` of them = `insufficient_data`+NULL, rest = FALSE."""
    names = list(["rates_calm", "vrp_supportive",
                  "credit_stable", "liquidity_expanding"])
    rows = []
    for i, n in enumerate(names):
        if i < favorable:
            rows.append((n, "production", True))
        elif i < favorable + unknown:
            rows.append((n, "insufficient_data", None))
        else:
            rows.append((n, "production", False))
    for name, status, val in rows:
        s.execute(text(
            """
            INSERT INTO context_daily
              (as_of_date, context_name, status, value_bool,
               source_features, logic_version, logic_hash)
            VALUES (:d, :n, :s, :v, ARRAY['t'], 'v1.0.0', 'h')
            ON CONFLICT (as_of_date, context_name, logic_version)
              DO UPDATE SET status = EXCLUDED.status,
                            value_bool = EXCLUDED.value_bool
            """
        ), {"d": run_date, "n": name, "s": status, "v": val})
    s.commit()


def _seed_shadow(
    s: Session, *, run_date: dt.date,
    would_trade: bool = True, symbol: str = "UNH",
    score: float = 0.535, conf: float = 76.75,
    macro_fav: int = 1,
    market_trend: str = "uptrend",
    vol_regime: str = "normal",
    sma50_above_sma200: bool = True,
    shadow_reason: str = "eligible_top_decile_buy_above_median_confidence",
):
    price_regime = json.dumps({
        "market_trend": market_trend,
        "vol_regime": vol_regime,
        "sma50_above_sma200": sma50_above_sma200,
    })
    s.execute(text(
        """
        INSERT INTO safe_gate_evolution_shadow
          (run_date, symbol, side, composite_score, confidence,
           macro_favorable_count, failed_macro_gates, price_regime,
           original_selector_reason, shadow_reason,
           hypothetical_size_multiplier, would_trade)
        VALUES (:d, :sym, 'Buy', :sc, :cf,
                :fav, '[]'::jsonb, CAST(:pr AS jsonb),
                NULL, :rsn,
                0.25, :wt)
        ON CONFLICT ON CONSTRAINT ux_safe_gate_evolution_shadow_run_date
          DO UPDATE SET would_trade = EXCLUDED.would_trade,
                        symbol = EXCLUDED.symbol,
                        composite_score = EXCLUDED.composite_score,
                        confidence = EXCLUDED.confidence,
                        macro_favorable_count = EXCLUDED.macro_favorable_count,
                        price_regime = EXCLUDED.price_regime,
                        shadow_reason = EXCLUDED.shadow_reason
        """
    ), {
        "d": run_date, "sym": symbol, "sc": score, "cf": conf,
        "fav": macro_fav, "pr": price_regime, "rsn": shadow_reason,
        "wt": would_trade,
    })
    s.commit()


def _setup_baseline(
    s: Session, *, run_date: dt.date,
) -> tuple[str, str]:
    pid = _seed_portfolio(s)
    aid = _seed_asset(s, symbol="UNH")
    _seed_price_bar(s, asset_id=aid, run_date=run_date, close=500.0)
    _seed_macro(s, run_date=run_date, favorable=1, unknown=0)
    _seed_shadow(s, run_date=run_date)
    return pid, aid


def _paper_trade_count(s: Session, *, pilot_only: bool = False) -> int:
    if pilot_only:
        return int(s.execute(text(
            "SELECT count(*) FROM paper_trade "
            "WHERE COALESCE(reason,'') LIKE 'safe_gate_evolution_pilot%'"
        )).scalar_one() or 0)
    return int(s.execute(text(
        "SELECT count(*) FROM paper_trade"
    )).scalar_one() or 0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_flag_off_does_not_open_trade(session):
    from apps.api.src.data.strategy.safe_gate_evolution_pilot import (
        evaluate_and_execute_pilot,
    )
    d = dt.date(2026, 4, 29)
    _setup_baseline(session, run_date=d)
    res = evaluate_and_execute_pilot(session, d, flag_override=False)
    assert res.flag_enabled is False
    assert res.opened is False
    assert res.reason == "pilot_flag_off"
    assert _paper_trade_count(session) == 0


def test_flag_on_eligible_opens_one_trade(session):
    from apps.api.src.data.strategy.safe_gate_evolution_pilot import (
        evaluate_and_execute_pilot,
    )
    d = dt.date(2026, 4, 29)
    _setup_baseline(session, run_date=d)
    res = evaluate_and_execute_pilot(session, d, flag_override=True)
    assert res.opened is True
    assert res.symbol == "UNH"
    assert res.side == "buy"
    assert res.size_multiplier == Decimal("0.25")
    assert _paper_trade_count(session, pilot_only=True) == 1


def test_paper_trade_row_is_correctly_tagged(session):
    from apps.api.src.data.strategy.safe_gate_evolution_pilot import (
        evaluate_and_execute_pilot,
    )
    d = dt.date(2026, 4, 29)
    _setup_baseline(session, run_date=d)
    evaluate_and_execute_pilot(session, d, flag_override=True)
    row = session.execute(text(
        "SELECT side, quantity, fill_price, reason, "
        "       recommendation_id, slippage_bps, realized_pnl "
        "FROM paper_trade ORDER BY created_at DESC LIMIT 1"
    )).mappings().first()
    assert row is not None
    assert row["side"] == "buy"
    assert row["reason"].startswith("safe_gate_evolution_pilot")
    assert "size_mult=0.25" in row["reason"]
    # Paper-only — broker / recommendation-tracking fields stay NULL.
    assert row["recommendation_id"] is None
    assert row["slippage_bps"] is None
    assert row["realized_pnl"] is None


def test_size_multiplier_applied_to_quantity(session):
    """qty = (notional_usd × multiplier) / fill_price."""
    from apps.api.src.config import settings
    from apps.api.src.data.strategy.safe_gate_evolution_pilot import (
        evaluate_and_execute_pilot,
    )
    d = dt.date(2026, 4, 29)
    _setup_baseline(session, run_date=d)
    res = evaluate_and_execute_pilot(session, d, flag_override=True)
    expected_notional = (
        Decimal(str(settings.SAFE_GATE_EVOLUTION_PILOT_NOTIONAL_USD))
        * Decimal("0.25")
    )
    expected_qty = (expected_notional / Decimal("500.0")).quantize(
        Decimal("0.0000000001")
    )
    assert res.notional_usd == expected_notional.quantize(Decimal("0.01"))
    assert res.quantity == expected_qty


def test_macro_zero_favorable_blocks(session):
    from apps.api.src.data.strategy.safe_gate_evolution_pilot import (
        evaluate_and_execute_pilot,
    )
    d = dt.date(2026, 4, 29)
    _setup_baseline(session, run_date=d)
    # Override macro to 0 favorable.
    _seed_macro(session, run_date=d, favorable=0, unknown=0)
    res = evaluate_and_execute_pilot(session, d, flag_override=True)
    assert res.opened is False
    assert "macro_favorable<" in res.reason
    assert _paper_trade_count(session) == 0


def test_unknown_macro_gates_block(session):
    from apps.api.src.data.strategy.safe_gate_evolution_pilot import (
        evaluate_and_execute_pilot,
    )
    d = dt.date(2026, 4, 29)
    _setup_baseline(session, run_date=d)
    _seed_macro(session, run_date=d, favorable=1, unknown=1)
    res = evaluate_and_execute_pilot(session, d, flag_override=True)
    assert res.opened is False
    assert res.reason.startswith("not_eligible:unknown_macro_gates_present")
    assert _paper_trade_count(session) == 0


def test_price_regime_unfavorable_blocks(session):
    from apps.api.src.data.strategy.safe_gate_evolution_pilot import (
        evaluate_and_execute_pilot,
    )
    d = dt.date(2026, 4, 29)
    _setup_baseline(session, run_date=d)
    _seed_shadow(
        session, run_date=d,
        would_trade=True, vol_regime="high",
    )
    res = evaluate_and_execute_pilot(session, d, flag_override=True)
    assert res.opened is False
    assert "price_regime_unfavorable" in res.reason
    assert _paper_trade_count(session) == 0


def test_shadow_would_trade_false_blocks(session):
    from apps.api.src.data.strategy.safe_gate_evolution_pilot import (
        evaluate_and_execute_pilot,
    )
    d = dt.date(2026, 4, 29)
    _setup_baseline(session, run_date=d)
    _seed_shadow(
        session, run_date=d, would_trade=False,
        shadow_reason="no_eligible_buy",
    )
    res = evaluate_and_execute_pilot(session, d, flag_override=True)
    assert res.opened is False
    assert res.reason.startswith("not_eligible:shadow_blocked")
    assert _paper_trade_count(session) == 0


def test_production_trade_already_opened_blocks(session):
    """Insert a non-pilot paper_trade for the day, then ask the
    pilot evaluator to consider that day. Must refuse."""
    from apps.api.src.data.strategy.safe_gate_evolution_pilot import (
        evaluate_and_execute_pilot,
    )
    d = dt.date(2026, 4, 29)
    pid, aid = _setup_baseline(session, run_date=d)
    session.execute(text(
        """
        INSERT INTO paper_trade
          (id, portfolio_id, asset_id, side, quantity,
           fill_price, fill_ts, submitted_at, reason,
           commission, created_at)
        VALUES (gen_random_uuid()::text, :pid, :aid, 'buy', 1.0,
                100, :ts, :ts, 'production_trade',
                0, now())
        """
    ), {"pid": pid, "aid": aid, "ts": dt.datetime.combine(
        d, dt.time(20, 0), tzinfo=dt.timezone.utc,
    )})
    session.commit()
    res = evaluate_and_execute_pilot(session, d, flag_override=True)
    assert res.opened is False
    assert "production_trade_already_opened" in res.reason
    assert _paper_trade_count(session, pilot_only=True) == 0


def test_pilot_idempotent_does_not_double_open(session):
    from apps.api.src.data.strategy.safe_gate_evolution_pilot import (
        evaluate_and_execute_pilot,
    )
    d = dt.date(2026, 4, 29)
    _setup_baseline(session, run_date=d)
    res1 = evaluate_and_execute_pilot(session, d, flag_override=True)
    res2 = evaluate_and_execute_pilot(session, d, flag_override=True)
    assert res1.opened is True
    assert res2.opened is False
    assert "pilot_trade_already_opened" in res2.reason
    assert _paper_trade_count(session, pilot_only=True) == 1


def test_max_one_trade_per_day_enforced(session):
    """Even three back-to-back calls produce exactly one row."""
    from apps.api.src.data.strategy.safe_gate_evolution_pilot import (
        evaluate_and_execute_pilot,
    )
    d = dt.date(2026, 4, 29)
    _setup_baseline(session, run_date=d)
    for _ in range(3):
        evaluate_and_execute_pilot(session, d, flag_override=True)
    assert _paper_trade_count(session, pilot_only=True) == 1


def test_no_paper_position_directly_mutated(session):
    """The pilot path must never write paper_position directly."""
    from apps.api.src.data.strategy.safe_gate_evolution_pilot import (
        evaluate_and_execute_pilot,
    )
    d = dt.date(2026, 4, 29)
    _setup_baseline(session, run_date=d)
    n_before = int(session.execute(text(
        "SELECT count(*) FROM paper_position"
    )).scalar_one() or 0)
    evaluate_and_execute_pilot(session, d, flag_override=True)
    n_after = int(session.execute(text(
        "SELECT count(*) FROM paper_position"
    )).scalar_one() or 0)
    assert n_before == n_after
