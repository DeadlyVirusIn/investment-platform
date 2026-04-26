"""Phase 8 — verify scheduler wiring + sample log emission.

Asserts:
  * REGISTRY contains "v2_promotion_snapshot"
  * Handler is async (coroutine fn) and takes no args
  * Calling the wrapper twice in the same ISO week:
      run 1 → status=inserted (with state + confidence + rollback_reason
              fields surfaced via INFO log)
      run 2 → status=noop_existing (idempotency holds; no second insert)
  * Sample log output captured + asserted on
"""

from __future__ import annotations

import asyncio
import datetime as dt
import inspect

import pytest
from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db.models import V2PromotionSnapshot
from apps.worker.src.jobs import v2_promotion_snapshot as job_module
from apps.worker.src.jobs.registry import REGISTRY
from apps.worker.src.jobs.v2_promotion_snapshot import (
    run_v2_promotion_snapshot_job,
)


pytestmark = pytest.mark.integration


_PAPER_SHADOW_DDL = text("""
CREATE TABLE IF NOT EXISTS paper_shadow_log (
    id              TEXT PRIMARY KEY,
    as_of_date      DATE NOT NULL,
    instrument      TEXT NOT NULL,
    source_strategy TEXT NOT NULL,
    signal          TEXT NOT NULL,
    fwd_return_1d   NUMERIC(12, 8),
    fwd_return_5d   NUMERIC(12, 8),
    regime_label    TEXT,
    trend_score     NUMERIC(12, 6)
)
""")


@pytest.fixture(autouse=True)
def _ensure_paper_shadow_log_exists(pg_engine):
    # DROP first so schema matches even if a prior test created the
    # table without the trend_score column.
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS paper_shadow_log"))
        conn.execute(_PAPER_SHADOW_DDL)
    yield


@pytest.fixture
def pg_factory(pg_engine):
    return sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)


def _seed(session: Session) -> None:
    base = dt.date(2026, 1, 5)  # Monday ISO 2026-W02
    for i in range(120):
        d = base + dt.timedelta(days=i)
        ret = [0.005, 0.003, -0.001, 0.004, 0.002][i % 5]
        for prefix, src, sig in [
            ("b2", "tsmom_60_no_stress", "LONG" if i % 3 == 0 else "FLAT"),
            ("v2", "tsmom_60_no_stress_v2_persist3",
             "LONG" if i % 2 == 0 else "FLAT"),
        ]:
            session.execute(
                text("INSERT INTO paper_shadow_log (id, as_of_date, "
                     "instrument, source_strategy, signal, fwd_return_1d, "
                     "fwd_return_5d, regime_label) VALUES "
                     "(:id, :d, :i, :s, :sig, :r, :r5, :rg)"),
                {"id": f"{prefix}-{i}", "d": d, "i": "SPY", "s": src,
                 "sig": sig, "r": ret, "r5": ret * 5, "rg": "DIRECTIONAL"},
            )
    session.commit()


# ===========================================================================
# Registry-shape assertions (Phase 8 contract)
# ===========================================================================

def test_registry_contains_v2_promotion_snapshot():
    assert "v2_promotion_snapshot" in REGISTRY


def test_registry_handler_is_async_no_arg():
    fn = REGISTRY["v2_promotion_snapshot"]
    assert inspect.iscoroutinefunction(fn)
    sig = inspect.signature(fn)
    assert list(sig.parameters) == []


# ===========================================================================
# Sample log output + idempotency on the wrapper itself
# ===========================================================================

def test_wrapper_logs_inserted_then_noop(monkeypatch, pg_factory, pg_session):
    _seed(pg_session)
    pg_session.commit()
    pg_session.close()  # release connection so wrapper sessions are fresh

    # Bind the underlying sync runner to the test session factory
    orig_run = job_module.run_v2_promotion_snapshot
    monkeypatch.setattr(
        job_module, "run_v2_promotion_snapshot",
        lambda **kw: orig_run(
            session_factory=pg_factory,
            as_of=dt.date(2026, 5, 18),  # ISO 2026-W21
            **kw,
        ),
    )

    captured: list[str] = []
    sink_id = logger.add(lambda m: captured.append(m), level="INFO")
    try:
        # Invocation 1 — should INSERT
        asyncio.run(run_v2_promotion_snapshot_job())
        # Invocation 2 — should be NO-OP
        asyncio.run(run_v2_promotion_snapshot_job())
    finally:
        logger.remove(sink_id)

    # DB invariant: exactly one row for ISO 2026-W21 — use fresh session
    with pg_factory() as s:
        n = s.scalar(
            text("SELECT COUNT(*) FROM v2_promotion_snapshot "
                 "WHERE iso_year=2026 AND iso_week=21")
        )
    assert n == 1, f"expected 1 snapshot, got {n}; logs:\n" + "\n".join(captured)

    log_text = "\n".join(captured)
    # Inserted invocation surfaces all 4 required fields
    assert "v2_promotion_snapshot job → status=inserted" in log_text
    assert "iso=2026-W21" in log_text
    assert "state=" in log_text
    assert "confidence=" in log_text
    assert "rollback_reason=" in log_text
    # Idempotent invocation surfaces noop_existing
    assert "v2_promotion_snapshot job → status=noop_existing" in log_text


def test_no_parallel_runs_within_same_week(monkeypatch, pg_factory, pg_session):
    """Two scheduler ticks firing the wrapper concurrently must yield
    exactly one row (race-safe via DB unique constraint)."""
    _seed(pg_session)
    pg_session.close()

    orig_run = job_module.run_v2_promotion_snapshot
    monkeypatch.setattr(
        job_module, "run_v2_promotion_snapshot",
        lambda **kw: orig_run(
            session_factory=pg_factory,
            as_of=dt.date(2026, 5, 18),
            **kw,
        ),
    )

    async def _both():
        await asyncio.gather(
            run_v2_promotion_snapshot_job(),
            run_v2_promotion_snapshot_job(),
        )

    asyncio.run(_both())
    with pg_factory() as s:
        n = s.scalar(
            text("SELECT COUNT(*) FROM v2_promotion_snapshot "
                 "WHERE iso_year=2026 AND iso_week=21")
        )
    assert n == 1
