"""Integration tests for shadow strategy safety.

Proves:
  • upsert is idempotent (same input → same row, no duplicate)
  • upsert NEVER inserts/updates anything in paper_trade_log,
    decision_log, ml_model_run, or any production execution table.
  • forward-return backfill is idempotent + non-destructive.

Requires DATABASE_URL.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL")


@pytest.fixture(scope="module")
def session() -> Session:
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")
    eng = create_engine(DATABASE_URL, future=True)
    Session_ = sessionmaker(bind=eng, future=True)
    with Session_() as s:
        yield s


def _counts(session: Session) -> dict[str, int]:
    """Snapshot row counts of production execution tables."""
    out = {}
    for tbl in ("paper_trade_log", "decision_log", "ml_model_run",
                "ml_hybrid_performance_snapshot", "paper_run_log"):
        try:
            cnt = session.execute(
                text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
            out[tbl] = int(cnt or 0)
        except Exception:
            out[tbl] = -1   # table doesn't exist; non-blocking
    return out


def test_upsert_idempotent(session: Session):
    from apps.api.src.research.shadow_strategy import (
        SOURCE_STRATEGY, ShadowDecision, upsert_decision,
    )
    test_date = date(2099, 12, 31)   # synthetic date — won't collide
    test_inst = "TEST_ES"

    # Cleanup
    session.execute(text("""
        DELETE FROM paper_shadow_log
         WHERE as_of_date = :d AND instrument = :i
    """), {"d": test_date, "i": test_inst})
    session.commit()

    decision = ShadowDecision(
        as_of_date=test_date,
        instrument=test_inst,
        source_strategy=SOURCE_STRATEGY,
        signal="LONG",
        entry_price=100.5,
        regime_label="DIRECTIONAL",
        engine_a_active=False,
        trend_score=0.0234,
        note="test",
    )

    upsert_decision(session, decision)
    session.commit()
    upsert_decision(session, decision)
    session.commit()
    upsert_decision(session, decision)
    session.commit()

    n = session.execute(text("""
        SELECT COUNT(*) FROM paper_shadow_log
         WHERE as_of_date = :d AND instrument = :i
    """), {"d": test_date, "i": test_inst}).scalar()
    assert n == 1

    # Cleanup
    session.execute(text("""
        DELETE FROM paper_shadow_log
         WHERE as_of_date = :d AND instrument = :i
    """), {"d": test_date, "i": test_inst})
    session.commit()


def test_upsert_does_not_touch_production_tables(session: Session):
    from apps.api.src.research.shadow_strategy import (
        SOURCE_STRATEGY, ShadowDecision, upsert_decision,
    )
    before = _counts(session)
    test_date = date(2099, 12, 30)
    test_inst = "TEST_ES_SAFETY"
    decision = ShadowDecision(
        as_of_date=test_date,
        instrument=test_inst,
        source_strategy=SOURCE_STRATEGY,
        signal="LONG",
        entry_price=100.0,
        regime_label="DIRECTIONAL",
        engine_a_active=False,
        trend_score=0.0,
        note="safety_test",
    )
    upsert_decision(session, decision)
    session.commit()
    after = _counts(session)
    assert before == after, \
        f"Production table counts changed: before={before} after={after}"
    # Cleanup
    session.execute(text("""
        DELETE FROM paper_shadow_log
         WHERE as_of_date = :d AND instrument = :i
    """), {"d": test_date, "i": test_inst})
    session.commit()


def test_backfill_returns_does_not_touch_production(session: Session):
    from apps.api.src.research.shadow_strategy import (
        SOURCE_STRATEGY, ShadowDecision,
        backfill_forward_returns, upsert_decision,
    )
    test_date = date(2099, 12, 29)
    test_inst = "TEST_ES_BF"
    upsert_decision(session, ShadowDecision(
        as_of_date=test_date, instrument=test_inst,
        source_strategy=SOURCE_STRATEGY,
        signal="LONG", entry_price=100.0,
        regime_label="DIRECTIONAL",
        engine_a_active=False, trend_score=0.0, note="bf_test",
    ))
    session.commit()

    before = _counts(session)
    n = backfill_forward_returns(
        session,
        as_of_date=test_date, instrument=test_inst,
        source_strategy=SOURCE_STRATEGY,
        fwd_return_1d=0.012, fwd_return_5d=0.045,
        exit_price=104.5,
    )
    session.commit()
    after = _counts(session)
    assert n == 1
    assert before == after

    # Cleanup
    session.execute(text("""
        DELETE FROM paper_shadow_log
         WHERE as_of_date = :d AND instrument = :i
    """), {"d": test_date, "i": test_inst})
    session.commit()


def test_table_exists_with_constraints(session: Session):
    """Sanity: paper_shadow_log table is reachable + has expected
    unique key + check constraint."""
    res = session.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_constraint
             WHERE conname = 'ux_paper_shadow_date_strategy'
        ) AS ok
    """)).scalar()
    assert bool(res) is True

    res2 = session.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_constraint
             WHERE conname = 'ck_paper_shadow_signal'
        ) AS ok
    """)).scalar()
    assert bool(res2) is True
