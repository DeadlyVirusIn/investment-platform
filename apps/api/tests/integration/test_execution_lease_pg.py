"""Execution lease — exactly-once guard race tests (real PostgreSQL).

Proves the P0-5 scheduler fix: atomic claim, crash recovery via bounded
lease expiry, exactly one executor under concurrency, clean release/reclaim,
no global lock (per-key), and that the unique trade constraint is only
defense-in-depth (the lease is the scheduler-level guarantee).

execution_lease is migration-118 (PROPOSED); ensured idempotently here.
"""

from __future__ import annotations

import datetime as dt
import threading

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.domain.scheduling import execution_lease as lease

pytestmark = pytest.mark.integration

_DDL = """
CREATE TABLE IF NOT EXISTS execution_lease (
    lease_key VARCHAR(128) PRIMARY KEY,
    holder VARCHAR(64) NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    released_at TIMESTAMPTZ,
    status VARCHAR(16) NOT NULL DEFAULT 'held',
    CONSTRAINT ck_execution_lease_status CHECK (status IN ('held','released'))
);
"""


@pytest.fixture
def db(pg_session: Session):
    pg_session.execute(text(_DDL))
    pg_session.execute(text("TRUNCATE execution_lease"))
    pg_session.commit()
    return pg_session


def test_single_acquire_then_second_blocked(db):
    assert lease.acquire(db, "job:2026-07-11", holder="A") is True
    db.commit()
    # a different holder cannot acquire a live lease
    assert lease.acquire(db, "job:2026-07-11", holder="B") is False
    db.commit()


def test_concurrent_acquire_exactly_one_winner(pg_engine, db):
    """Cron + tickloop racing simultaneously → exactly one holds the lease."""
    sm = sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)
    key = "run_paper_trading:2026-07-11"
    wins: list[str] = []
    barrier = threading.Barrier(8)
    lock = threading.Lock()

    def contend(i):
        s = sm()
        try:
            barrier.wait()
            if lease.acquire(s, key, holder=f"w{i}"):
                s.commit()
                with lock:
                    wins.append(f"w{i}")
            else:
                s.commit()
        finally:
            s.close()

    threads = [threading.Thread(target=contend, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(wins) == 1, wins
    n = db.execute(text("SELECT count(*) FROM execution_lease WHERE lease_key=:k"),
                   {"k": key}).scalar()
    assert n == 1


def test_expired_lease_is_stolen_crash_recovery(db):
    """Holder crashes mid-run (lease not released); after expiry the next
    attempt steals it — crash recovery without a global lock."""
    assert lease.acquire(db, "job:x", holder="dead", lease_seconds=1) is True
    db.commit()
    # force expiry
    db.execute(text("UPDATE execution_lease SET expires_at = now() - interval "
                    "'1 second' WHERE lease_key='job:x'"))
    db.commit()
    assert lease.acquire(db, "job:x", holder="fresh") is True
    db.commit()
    holder = db.execute(text("SELECT holder FROM execution_lease WHERE "
                             "lease_key='job:x'")).scalar()
    assert holder == "fresh"


def test_release_allows_immediate_reclaim(db):
    assert lease.acquire(db, "job:y", holder="A") is True
    db.commit()
    assert lease.release(db, "job:y", holder="A") is True
    db.commit()
    # released → a new window reclaims without waiting for expiry
    assert lease.acquire(db, "job:y", holder="B") is True
    db.commit()
    # A can no longer release B's lease
    assert lease.release(db, "job:y", holder="A") is False
    db.commit()


def test_heartbeat_extends_only_own_lease(db):
    assert lease.acquire(db, "job:z", holder="A", lease_seconds=5) is True
    db.commit()
    exp1 = db.execute(text("SELECT expires_at FROM execution_lease WHERE "
                           "lease_key='job:z'")).scalar()
    assert lease.heartbeat(db, "job:z", holder="A", lease_seconds=3600) is True
    db.commit()
    exp2 = db.execute(text("SELECT expires_at FROM execution_lease WHERE "
                           "lease_key='job:z'")).scalar()
    assert exp2 > exp1
    # a non-owner heartbeat is refused
    assert lease.heartbeat(db, "job:z", holder="B") is False


def test_delayed_job_not_lost_different_day_key(db):
    """A future/delayed window has a distinct key — never blocked by today's
    lease (no lost jobs)."""
    assert lease.acquire(db, lease.daily_key("j", dt.date(2026, 7, 11)),
                         holder="A") is True
    db.commit()
    assert lease.acquire(db, lease.daily_key("j", dt.date(2026, 7, 12)),
                         holder="A") is True   # next day is independent
    db.commit()


def test_no_global_lock_unrelated_keys_proceed(db):
    assert lease.acquire(db, "job_a:2026-07-11", holder="A") is True
    db.commit()
    # a DIFFERENT job on the same day is unaffected
    assert lease.acquire(db, "job_b:2026-07-11", holder="A") is True
    db.commit()


def test_reacquire_by_same_holder_after_release(db):
    assert lease.acquire(db, "job:r", holder="A") is True
    db.commit()
    lease.release(db, "job:r", holder="A")
    db.commit()
    # same holder reacquires the released lease
    assert lease.acquire(db, "job:r", holder="A") is True
    db.commit()


def test_daily_key_shape():
    assert lease.daily_key("run_paper_trading", dt.date(2026, 7, 11)) == \
        "run_paper_trading:2026-07-11"
