"""Scheduling + snapshot freshness health detectors (real PostgreSQL).

Proves the 2026-07-11 findings are now DETECTABLE: overdue/NULL schedules,
stale engine + user snapshots (weekday-aware), job-success-but-zero-output,
and P0-5C exit-before-entry ordering. Read-only detectors; no prod writes.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset, JobRun, JobSchedule, PaperEquitySnapshot, PaperPortfolio,
)
from apps.api.src.domain.ops import scheduling_health as sh

pytestmark = pytest.mark.integration


@pytest.fixture
def db(pg_session: Session):
    return pg_session


def _sched(db, name, next_run):
    s = JobSchedule(name=name, cron_expr="0 22 * * *", enabled=True,
                    next_run_at=next_run)
    db.add(s); db.flush()
    return s


def _book(db, name):
    p = PaperPortfolio(name=name, starting_cash=Decimal("100000"),
                       cash=Decimal("100000"))
    db.add(p); db.flush()
    return p


def _snap(db, pid, date, created_at=None):
    db.add(PaperEquitySnapshot(
        portfolio_id=pid, snapshot_date=date, cash=Decimal("100000"),
        positions_value=Decimal("0"), total_equity=Decimal("100000"),
    ))
    db.flush()
    if created_at is not None:
        db.execute(text("UPDATE paper_equity_snapshot SET created_at=:c "
                        "WHERE portfolio_id=:p AND snapshot_date=:d"),
                   {"c": created_at, "p": pid, "d": date})


# --- overdue jobs ----------------------------------------------------------
def test_overdue_and_null_schedules_flagged(db):
    now = dt.datetime.now(dt.timezone.utc)
    _sched(db, "healthy", now + dt.timedelta(hours=1))
    _sched(db, "overdue_warn", now - dt.timedelta(hours=3))
    _sched(db, "overdue_alert", now - dt.timedelta(days=3))
    _sched(db, "null_stuck", None)
    db.commit()
    out = {r["name"]: r for r in sh.overdue_jobs(db, grace_minutes=120)}
    assert "healthy" not in out
    assert out["overdue_warn"]["status"] == "warn"
    assert out["overdue_alert"]["status"] == "alert"
    assert out["null_stuck"]["status"] == "alert"
    assert "NULL" in out["null_stuck"]["reason"]


# --- snapshot freshness ----------------------------------------------------
def test_snapshot_freshness_weekday_aware(db):
    # "now" = Sat 2026-07-11; engine snap Thu 07-09 → 1 weekday age (Fri) → ok
    now = dt.datetime(2026, 7, 11, 21, tzinfo=dt.timezone.utc)
    eng = _book(db, "Engine Canonical")
    usr = _book(db, "user:abc:stock")
    _snap(db, eng.id, dt.datetime(2026, 7, 9, tzinfo=dt.timezone.utc))
    _snap(db, usr.id, dt.datetime(2026, 7, 9, tzinfo=dt.timezone.utc))
    db.commit()
    out = sh.snapshot_freshness(db, now=now, max_stale_weekdays=2)
    assert out["engine"]["status"] == "ok" and out["engine"]["weekday_age"] == 1
    assert out["user"]["status"] == "ok"
    assert out["overall"] == "ok"
    assert "not job success" in out["derived_from"]


def test_snapshot_staleness_alerts(db):
    now = dt.datetime(2026, 7, 11, 21, tzinfo=dt.timezone.utc)
    eng = _book(db, "Engine Canonical")
    _snap(db, eng.id, dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc))  # ~7 wd old
    db.commit()
    out = sh.snapshot_freshness(db, now=now, max_stale_weekdays=2)
    assert out["engine"]["status"] == "alert"
    assert out["overall"] == "alert"
    # user side has no rows → insufficient_data, not falsely green
    assert out["user"]["status"] == "insufficient_data"


# --- job success but zero snapshots ---------------------------------------
def test_success_with_zero_snapshots_detected(db):
    now = dt.datetime.now(dt.timezone.utc)
    s = _sched(db, "run_paper_trading", now + dt.timedelta(hours=1))
    db.add(JobRun(job_schedule_id=s.id, started_at=now - dt.timedelta(minutes=30),
                  finished_at=now - dt.timedelta(minutes=25), status="success"))
    db.commit()
    out = sh.job_success_but_zero_snapshots(db)
    assert out["status"] == "alert" and "0 live snapshots" in out["reason"]


def test_success_with_snapshots_ok(db):
    now = dt.datetime.now(dt.timezone.utc)
    s = _sched(db, "run_paper_trading", now + dt.timedelta(hours=1))
    started = now - dt.timedelta(minutes=30)
    db.add(JobRun(job_schedule_id=s.id, started_at=started,
                  finished_at=now - dt.timedelta(minutes=25), status="success"))
    book = _book(db, "Engine Canonical")
    db.flush()
    _snap(db, book.id, now, created_at=now - dt.timedelta(minutes=24))
    db.commit()
    out = sh.job_success_but_zero_snapshots(db)
    assert out["status"] == "ok"


# --- P0-5C exit-before-entry ordering -------------------------------------
def test_exit_before_entry_ok(db):
    day = dt.date(2026, 7, 10)
    base = dt.datetime(2026, 7, 10, 23, tzinfo=dt.timezone.utc)
    ex = _sched(db, "run_paper_exit_cycle", base)
    en = _sched(db, "run_paper_trading", base)
    db.add(JobRun(job_schedule_id=ex.id, started_at=base,
                  finished_at=base + dt.timedelta(minutes=5), status="success"))
    db.add(JobRun(job_schedule_id=en.id,
                  started_at=base + dt.timedelta(minutes=30),
                  finished_at=base + dt.timedelta(minutes=35), status="success"))
    db.commit()
    out = sh.exit_before_entry(db, day=day)
    assert out["status"] == "ok" and out["ordered_correctly"] is True


def test_exit_after_entry_violation_alerts(db):
    day = dt.date(2026, 7, 10)
    base = dt.datetime(2026, 7, 10, 23, tzinfo=dt.timezone.utc)
    ex = _sched(db, "run_paper_exit_cycle", base)
    en = _sched(db, "run_paper_trading", base)
    # entry STARTS before exit FINISHES → ordering violation
    db.add(JobRun(job_schedule_id=en.id, started_at=base,
                  finished_at=base + dt.timedelta(minutes=5), status="success"))
    db.add(JobRun(job_schedule_id=ex.id,
                  started_at=base + dt.timedelta(minutes=10),
                  finished_at=base + dt.timedelta(minutes=15), status="success"))
    db.commit()
    out = sh.exit_before_entry(db, day=day)
    assert out["status"] == "alert" and out["ordered_correctly"] is False


def test_entry_without_exit_warns(db):
    day = dt.date(2026, 7, 10)
    base = dt.datetime(2026, 7, 10, 23, tzinfo=dt.timezone.utc)
    en = _sched(db, "run_paper_trading", base)
    db.add(JobRun(job_schedule_id=en.id, started_at=base,
                  finished_at=base + dt.timedelta(minutes=5), status="success"))
    db.commit()
    out = sh.exit_before_entry(db, day=day)
    assert out["status"] == "warn"
