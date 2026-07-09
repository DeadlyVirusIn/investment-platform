"""P0-5A/P0-5B — scheduler exactly-once claim + NULL next_run_at self-heal.

Pins:
  1. Two schedulers racing one due job → exactly one winner (atomic
     guarded UPDATE claim; the loser matches 0 rows and must not execute,
     so no duplicate job_run / trades can be produced by the loser).
  2. Enabled NULL row with a valid cron is healed to its NEXT cron slot
     (never "now" — no immediate mass-fire).
  3. Enabled NULL row with a malformed cron stays NULL (stuck, visible,
     never claimed/executed).
  4. Disabled NULL rows are never healed.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from croniter import croniter
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db.models import JobSchedule
from apps.worker.src.scheduler import tick_loop

pytestmark = pytest.mark.integration


@pytest.fixture()
def bind_tick_loop(pg_session: Session, monkeypatch: pytest.MonkeyPatch):
    """Point the tick-loop's module-level SessionLocal at the test DB."""
    factory = sessionmaker(
        bind=pg_session.get_bind(), autocommit=False, autoflush=False, class_=Session
    )
    monkeypatch.setattr(tick_loop, "SessionLocal", factory)
    return factory


def _mk_schedule(
    pg_session: Session, name: str, *, cron: str = "0 23 * * 1-5",
    enabled: bool = True, next_run_at: dt.datetime | None = None,
) -> JobSchedule:
    s = JobSchedule(
        id=str(uuid.uuid4()), name=name, cron_expr=cron,
        enabled=enabled, next_run_at=next_run_at,
    )
    pg_session.add(s)
    pg_session.commit()
    return s


def test_concurrent_claim_has_exactly_one_winner(
    pg_session: Session, bind_tick_loop,
) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    sched = _mk_schedule(
        pg_session, "p05-claim-race", next_run_at=now - dt.timedelta(minutes=5),
    )
    first = tick_loop._claim_due_job(sched, now)
    second = tick_loop._claim_due_job(sched, now)  # racing sibling
    assert first is True
    assert second is False  # loser skips → cannot open a job_run or trade

    pg_session.expire_all()
    row = pg_session.get(JobSchedule, sched.id)
    assert row.next_run_at > now  # advanced to the next slot at claim time


def test_heal_null_reconstructs_next_cron_slot(
    pg_session: Session, bind_tick_loop,
) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    sched = _mk_schedule(pg_session, "p05-heal-valid", next_run_at=None)

    healed = tick_loop._heal_null_schedules(now)
    assert healed >= 1

    pg_session.expire_all()
    row = pg_session.get(JobSchedule, sched.id)
    expected = croniter(sched.cron_expr, now).get_next(dt.datetime)
    assert row.next_run_at is not None
    assert row.next_run_at == expected  # cadence-derived, NOT "now"
    assert row.next_run_at > now

    # Healing is race-safe/idempotent: a second pass finds nothing NULL.
    assert tick_loop._heal_null_schedules(now) == 0


def test_heal_invalid_cron_left_stuck_and_unclaimed(
    pg_session: Session, bind_tick_loop,
) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    sched = _mk_schedule(
        pg_session, "p05-heal-broken", cron="definitely not cron", next_run_at=None,
    )

    tick_loop._heal_null_schedules(now)

    pg_session.expire_all()
    row = pg_session.get(JobSchedule, sched.id)
    assert row.next_run_at is None            # stays stuck, visibly
    assert tick_loop._claim_due_job(row, now) is False  # never executed


def test_heal_never_touches_disabled_rows(
    pg_session: Session, bind_tick_loop,
) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    sched = _mk_schedule(
        pg_session, "p05-heal-disabled", enabled=False, next_run_at=None,
    )

    tick_loop._heal_null_schedules(now)

    pg_session.expire_all()
    row = pg_session.get(JobSchedule, sched.id)
    assert row.next_run_at is None
    assert row.enabled is False
