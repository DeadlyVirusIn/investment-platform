"""Execution lease with fencing — exactly-once + fencing race tests (real PG).

Proves the P0-5 scheduler fix: atomic claim, crash recovery via bounded lease
expiry, exactly one executor under concurrency, holder+fence ownership, and —
the safety property — a stale former holder is FENCED OUT after its lease is
stolen (cannot heartbeat, cannot verify, cannot release, cannot continue
mutating). The unique trade constraint is only defense-in-depth.

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
    fence BIGINT NOT NULL DEFAULT 1,
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
    pg_session.execute(text("ALTER TABLE execution_lease "
                            "ADD COLUMN IF NOT EXISTS fence BIGINT NOT NULL DEFAULT 1"))
    pg_session.execute(text("TRUNCATE execution_lease"))
    pg_session.commit()
    return pg_session


def _expire(db, key):
    db.execute(text("UPDATE execution_lease SET expires_at = now() - "
                    "interval '1 second' WHERE lease_key = :k"), {"k": key})
    db.commit()


# --- basic acquire/ownership ----------------------------------------------
def test_single_acquire_then_second_blocked(db):
    h = lease.acquire(db, "job:2026-07-11", holder="A")
    db.commit()
    assert h is not None and h.fence == 1
    assert lease.acquire(db, "job:2026-07-11", holder="B") is None
    db.commit()


def test_concurrent_acquire_exactly_one_winner(pg_engine, db):
    sm = sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)
    key = "run_paper_trading:2026-07-11"
    wins: list[int] = []
    barrier = threading.Barrier(8)
    lock = threading.Lock()

    def contend(i):
        s = sm()
        try:
            barrier.wait()
            h = lease.acquire(s, key, holder=f"w{i}")
            s.commit()
            if h is not None:
                with lock:
                    wins.append(h.fence)
        finally:
            s.close()

    threads = [threading.Thread(target=contend, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(wins) == 1, wins
    assert db.execute(text("SELECT count(*) FROM execution_lease WHERE "
                           "lease_key=:k"), {"k": key}).scalar() == 1


# --- fencing: the safety property -----------------------------------------
def test_steal_bumps_fence_and_fences_out_old_holder(db):
    """Old holder's lease expires; new holder steals (fence++). The OLD handle
    can no longer verify, heartbeat, or release — it is fenced out."""
    old = lease.acquire(db, "job:x", holder="slow", lease_seconds=1)
    db.commit()
    assert old.fence == 1 and lease.verify_ownership(db, old) is True
    _expire(db, "job:x")
    new = lease.acquire(db, "job:x", holder="fast")
    db.commit()
    assert new is not None and new.fence == 2       # generation incremented
    # the NEW holder owns it
    assert lease.verify_ownership(db, new) is True
    # the OLD holder is fenced out on every ownership operation
    assert lease.verify_ownership(db, old) is False
    assert lease.heartbeat(db, old) is False
    assert lease.release(db, old) is False
    db.commit()
    # new holder still owns after old holder's failed attempts
    assert lease.verify_ownership(db, new) is True


def test_expired_holder_cannot_heartbeat_back_to_life(db):
    """A stalled holder whose lease already expired cannot revive it via
    heartbeat — that window belongs to whoever steals it next."""
    h = lease.acquire(db, "job:z", holder="A", lease_seconds=1)
    db.commit()
    _expire(db, "job:z")
    assert lease.heartbeat(db, h) is False          # expired → no revive


def test_heartbeat_extends_only_current_owner(db):
    h = lease.acquire(db, "job:hb", holder="A", lease_seconds=5)
    db.commit()
    exp1 = db.execute(text("SELECT expires_at FROM execution_lease WHERE "
                           "lease_key='job:hb'")).scalar()
    assert lease.heartbeat(db, h, lease_seconds=3600) is True
    db.commit()
    exp2 = db.execute(text("SELECT expires_at FROM execution_lease WHERE "
                           "lease_key='job:hb'")).scalar()
    assert exp2 > exp1


def test_long_run_heartbeat_prevents_second_executor(db):
    """Simulated long run: owner heartbeats before expiry → lease never
    becomes stealable, so a second executor is refused throughout."""
    h = lease.acquire(db, "job:long", holder="A", lease_seconds=2)
    db.commit()
    # a concurrent acquirer is refused while the lease is live
    assert lease.acquire(db, "job:long", holder="B") is None
    db.commit()
    # owner heartbeats (extends) — still owns, second executor still refused
    assert lease.heartbeat(db, h, lease_seconds=3600) is True
    db.commit()
    assert lease.acquire(db, "job:long", holder="B") is None
    db.commit()
    assert lease.verify_ownership(db, h) is True


def test_release_is_holder_and_fence_specific(db):
    a = lease.acquire(db, "job:r", holder="A")
    db.commit()
    assert lease.release(db, a) is True
    db.commit()
    b = lease.acquire(db, "job:r", holder="B")     # reclaim after release
    db.commit()
    assert b.fence == 2
    # A's stale handle cannot release B's lease
    assert lease.release(db, a) is False
    db.commit()
    assert lease.verify_ownership(db, b) is True


def test_release_allows_immediate_reclaim(db):
    a = lease.acquire(db, "job:y", holder="A")
    db.commit()
    assert lease.release(db, a) is True
    db.commit()
    assert lease.acquire(db, "job:y", holder="B") is not None
    db.commit()


# --- no lost jobs / no global lock ----------------------------------------
def test_delayed_job_distinct_day_key_not_blocked(db):
    assert lease.acquire(db, lease.daily_key("j", dt.date(2026, 7, 11)),
                         holder="A") is not None
    db.commit()
    assert lease.acquire(db, lease.daily_key("j", dt.date(2026, 7, 12)),
                         holder="A") is not None
    db.commit()


def test_no_global_lock_unrelated_keys_proceed(db):
    assert lease.acquire(db, "job_a:2026-07-11", holder="A") is not None
    db.commit()
    assert lease.acquire(db, "job_b:2026-07-11", holder="A") is not None
    db.commit()


def test_crash_recovery_expired_stolen(db):
    """Holder crashes (never releases); after expiry the next attempt steals
    with a fresh fence — recovery without a global lock."""
    dead = lease.acquire(db, "job:c", holder="dead", lease_seconds=1)
    db.commit()
    _expire(db, "job:c")
    fresh = lease.acquire(db, "job:c", holder="fresh")
    db.commit()
    assert fresh is not None and fresh.fence == 2
    assert lease.verify_ownership(db, dead) is False   # crashed holder fenced


def test_daily_key_shape():
    assert lease.daily_key("run_paper_trading", dt.date(2026, 7, 11)) == \
        "run_paper_trading:2026-07-11"
