"""Integration test: scheduler tick executes due jobs end-to-end."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import JobRun, JobSchedule

pytestmark = pytest.mark.integration


@pytest.fixture
def bind_worker_sessionlocal(pg_engine, monkeypatch):
    """Point the scheduler's module-level SessionLocal at the ISOLATED test
    engine. `_tick` opens its own `apps.api.src.db.SessionLocal` (bound to
    DATABASE_URL, i.e. localhost) rather than the injected pg_session — without
    this rebind the test connects to a non-existent localhost:5432. Rebinding
    makes the test hermetic against the same TEST_DATABASE_URL the rest of the
    suite uses. (Root cause of the two prior 'connection refused' failures.)"""
    from sqlalchemy.orm import Session as _S
    from sqlalchemy.orm import sessionmaker

    import apps.api.src.db as db_mod
    test_sm = sessionmaker(bind=pg_engine, class_=_S, expire_on_commit=False)
    monkeypatch.setattr(db_mod, "SessionLocal", test_sm)
    # tick_loop imported SessionLocal by name at module load — rebind there too
    import apps.worker.src.scheduler.tick_loop as tl
    monkeypatch.setattr(tl, "SessionLocal", test_sm)
    return test_sm


async def test_scheduler_runs_due_job_and_updates_schedule(
    pg_session: Session, bind_worker_sessionlocal, monkeypatch: pytest.MonkeyPatch
) -> None:
    from apps.api.src.config import settings
    from apps.worker.src.scheduler.tick_loop import _tick

    # Make tiingo job a no-op (missing key path) so we test the scheduler,
    # not the provider.
    monkeypatch.setattr(settings, "TIINGO_API_KEY", "")

    now = dt.datetime.now(dt.timezone.utc)
    sched = JobSchedule(
        name="tiingo_backfill_eod",
        cron_expr="0 22 * * 1-5",
        enabled=True,
        next_run_at=now - dt.timedelta(minutes=1),
    )
    pg_session.add(sched)
    pg_session.commit()
    sched_id = sched.id

    await _tick()

    pg_session.expire_all()
    runs = pg_session.scalars(
        select(JobRun).where(JobRun.job_schedule_id == sched_id)
    ).all()
    assert len(runs) == 1
    run = runs[0]
    assert run.status == "success"
    assert run.finished_at is not None
    assert run.duration_seconds is not None
    assert Decimal(str(run.duration_seconds)) >= Decimal("0")

    sched_after = pg_session.get(JobSchedule, sched_id)
    assert sched_after.last_run_at is not None
    assert sched_after.next_run_at is not None
    assert sched_after.next_run_at > now


async def test_scheduler_skips_future_jobs(
    pg_session: Session, bind_worker_sessionlocal
) -> None:
    from apps.worker.src.scheduler.tick_loop import _tick

    now = dt.datetime.now(dt.timezone.utc)
    sched = JobSchedule(
        name="tiingo_backfill_eod",
        cron_expr="0 22 * * 1-5",
        enabled=True,
        next_run_at=now + dt.timedelta(hours=1),  # future
    )
    pg_session.add(sched)
    pg_session.commit()
    sched_id = sched.id

    await _tick()

    pg_session.expire_all()
    runs = pg_session.scalars(
        select(JobRun).where(JobRun.job_schedule_id == sched_id)
    ).all()
    assert len(runs) == 0
