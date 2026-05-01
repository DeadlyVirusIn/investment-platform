"""Phase 11X — safe_gate_evolution_shadow integration tests against PG.

End-to-end: applies migration 054 to the testcontainer, seeds
candidate_idea + context_daily + regime_snapshot, runs the
evaluator, asserts:
  * One row inserted per (run_date) — UNIQUE enforced.
  * Re-running the same date is a no-op (idempotent).
  * favorable=0 → would_trade=False, summary-only row.
  * Eligible day → would_trade=True with symbol + score.
  * No production-table writes.
"""

from __future__ import annotations

import datetime as dt
import importlib
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.data.strategy.safe_gate_evolution_shadow import (
    evaluate, evaluate_and_persist,
)


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Module-scoped fixture: apply migration 054
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def shadow_table(pg_engine):
    mod = importlib.import_module(
        "infra.alembic.versions.054_safe_gate_evolution_shadow"
    )
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with pg_engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()
    yield pg_engine
    # Ensure table is dropped + recreated cleanly between sessions.
    with pg_engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE IF EXISTS public.safe_gate_evolution_shadow"
        ))


@pytest.fixture
def session(shadow_table, pg_session):
    # safe_gate_evolution_shadow is not in Base.metadata; conftest's
    # ORM-table TRUNCATE doesn't touch it. Clean per-test so each
    # case starts with an empty diagnostic table.
    pg_session.execute(text(
        "TRUNCATE TABLE public.safe_gate_evolution_shadow"
    ))
    pg_session.commit()
    yield pg_session


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_asset(s: Session, *, symbol: str) -> str:
    aid = f"asset-{symbol.lower()}"
    s.execute(text(
        """
        INSERT INTO asset
          (id, symbol, name, asset_class, exchange, currency,
           is_active, created_at, updated_at)
        VALUES
          (:id, :sym, :sym, 'equity', 'NASDAQ', 'USD',
           TRUE, now(), now())
        ON CONFLICT ON CONSTRAINT uq_asset_symbol_exchange
          DO NOTHING
        """
    ), {"id": aid, "sym": symbol})
    return aid


def _seed_candidate(
    s: Session, *,
    asset_id: str, as_of: dt.date,
    action: str, score: float, conf: float,
    status: str = "accepted",
):
    s.execute(text(
        """
        INSERT INTO candidate_idea
          (id, as_of_date, asset_id, model_version, engine,
           status, action, composite_score, confidence,
           factor_breakdown, regime_snapshot, created_at)
        VALUES
          (gen_random_uuid()::text, :d, :aid, 'stock_swing_v1',
           'stock_swing', :status, :act, :sc, :cf,
           '{}'::jsonb, '{}'::jsonb, now())
        ON CONFLICT DO NOTHING
        """
    ), {
        "d": as_of, "aid": asset_id, "status": status,
        "act": action, "sc": score, "cf": conf,
    })


def _seed_context(
    s: Session, *, as_of: dt.date, true_set: set[str],
):
    """context_daily ck_status only allows production/candidate/diagnostic."""
    for name in (
        "rates_calm", "vrp_supportive",
        "credit_stable", "liquidity_expanding",
    ):
        s.execute(text(
            """
            INSERT INTO context_daily
              (as_of_date, context_name, status, value_bool,
               source_features, logic_version, logic_hash)
            VALUES
              (:d, :n, 'production', :v,
               ARRAY['test'], 'v1.0.0', 'h')
            ON CONFLICT (as_of_date, context_name, logic_version)
              DO UPDATE SET value_bool = EXCLUDED.value_bool
            """
        ), {"d": as_of, "n": name, "v": (name in true_set)})


def _seed_regime(
    s: Session, *, as_of: dt.date,
    trend: str = "uptrend", vol: str = "low",
    sma_above: bool = True,
):
    s.execute(text(
        """
        INSERT INTO regime_snapshot
          (as_of_date, benchmark_symbol, market_trend, vol_regime,
           sma50_over_sma200, realized_vol_20d, atr_pctile_1y,
           created_at)
        VALUES
          (:d, 'SPY', :tr, :vr, :sma, 0.09, 0.20, now())
        ON CONFLICT (as_of_date) DO UPDATE
          SET market_trend = EXCLUDED.market_trend,
              vol_regime = EXCLUDED.vol_regime,
              sma50_over_sma200 = EXCLUDED.sma50_over_sma200
        """
    ), {"d": as_of, "tr": trend, "vr": vol, "sma": sma_above})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _public_table_counts(s: Session) -> dict[str, int]:
    # ORM-tracked tables only; paper_run_log + paper_trade_log are
    # raw-SQL tables not present in the testcontainer schema.
    return {
        t: s.execute(
            text(f"SELECT count(*) FROM public.{t}")
        ).scalar_one()
        for t in (
            "candidate_idea", "asset", "paper_trade",
            "paper_position",
        )
    }


def test_zero_favorable_inserts_summary_only_row(session):
    d = dt.date(2026, 4, 29)
    _seed_context(session, as_of=d, true_set=set())
    _seed_regime(session, as_of=d)
    session.commit()
    before = _public_table_counts(session)
    res, inserted = evaluate_and_persist(session, d)
    assert inserted is True
    assert res.would_trade is False
    assert res.macro_favorable_count == 0
    assert res.shadow_reason == "macro_favorable_count_zero"
    after = _public_table_counts(session)
    assert before == after


def test_eligible_day_inserts_would_trade_true(session):
    d = dt.date(2026, 4, 29)
    aid_unh = _seed_asset(session, symbol="UNH")
    aid_qqq = _seed_asset(session, symbol="QQQ")
    aid_amzn = _seed_asset(session, symbol="AMZN")
    _seed_candidate(
        session, asset_id=aid_unh, as_of=d,
        action="Buy", score=0.6, conf=80.0,
    )
    _seed_candidate(
        session, asset_id=aid_qqq, as_of=d,
        action="Buy", score=0.5, conf=70.0,
    )
    _seed_candidate(
        session, asset_id=aid_amzn, as_of=d,
        action="Buy", score=0.4, conf=60.0,
    )
    _seed_context(session, as_of=d, true_set={"rates_calm"})
    _seed_regime(
        session, as_of=d,
        trend="uptrend", vol="low", sma_above=True,
    )
    session.commit()

    res, inserted = evaluate_and_persist(session, d)
    assert inserted is True
    assert res.would_trade is True
    assert res.symbol == "UNH"
    assert res.composite_score == Decimal("0.600000")
    assert res.macro_favorable_count == 1
    assert res.hypothetical_size_multiplier == Decimal("0.2500")


def test_idempotent_rerun_does_not_double_insert(session):
    d = dt.date(2026, 4, 29)
    _seed_context(session, as_of=d, true_set=set())
    _seed_regime(session, as_of=d)
    session.commit()

    res1, ins1 = evaluate_and_persist(session, d)
    res2, ins2 = evaluate_and_persist(session, d)
    assert ins1 is True
    assert ins2 is False  # blocked by UNIQUE
    n = session.execute(
        text(
            "SELECT count(*) FROM safe_gate_evolution_shadow "
            "WHERE run_date = :d"
        ),
        {"d": d},
    ).scalar_one()
    assert n == 1


def test_max_one_row_per_day_constraint(session):
    """Even with manual INSERT bypassing the persister, the UNIQUE
    constraint enforces max-1-row-per-day."""
    d = dt.date(2026, 4, 29)
    _seed_context(session, as_of=d, true_set=set())
    _seed_regime(session, as_of=d)
    session.commit()
    res, _ = evaluate_and_persist(session, d)

    # Direct duplicate INSERT must fail.
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        session.execute(text(
            """
            INSERT INTO safe_gate_evolution_shadow
              (run_date, macro_favorable_count, shadow_reason,
               would_trade)
            VALUES (:d, 0, 'duplicate', FALSE)
            """
        ), {"d": d})
        session.flush()
    session.rollback()


def test_no_production_table_writes_during_evaluation(session):
    """The full evaluator path issues only SELECTs against execution
    tables. Snapshot before/after row counts on the production
    surface and assert no delta."""
    d = dt.date(2026, 4, 29)
    aid = _seed_asset(session, symbol="UNH")
    _seed_candidate(
        session, asset_id=aid, as_of=d,
        action="Buy", score=0.6, conf=80.0,
    )
    _seed_context(session, as_of=d, true_set={"credit_stable"})
    _seed_regime(session, as_of=d)
    session.commit()

    before = _public_table_counts(session)
    res = evaluate(session, d)
    after = _public_table_counts(session)
    assert before == after
    assert res.would_trade is True


def test_macro_count_check_constraint_blocks_invalid_value(session):
    """DB CHECK rejects favorable_count outside 0..4."""
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        session.execute(text(
            """
            INSERT INTO safe_gate_evolution_shadow
              (run_date, macro_favorable_count, shadow_reason,
               would_trade)
            VALUES ('2026-04-29', 5, 'invalid', FALSE)
            """
        ))
        session.flush()
    session.rollback()


def test_size_multiplier_check_constraint_blocks_out_of_range(session):
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        session.execute(text(
            """
            INSERT INTO safe_gate_evolution_shadow
              (run_date, macro_favorable_count, shadow_reason,
               would_trade, hypothetical_size_multiplier)
            VALUES ('2026-04-29', 0, 'oversize', FALSE, 1.5)
            """
        ))
        session.flush()
    session.rollback()
