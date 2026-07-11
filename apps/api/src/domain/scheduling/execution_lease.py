"""Execution lease — exactly-once across independent scheduler paths (P0-5).

A lease is keyed by a logical string, e.g. ``run_paper_trading:2026-07-11``
(job + trading date). Semantics:

  * ``acquire`` is atomic: INSERT .. ON CONFLICT DO UPDATE, where the UPDATE
    only fires when the existing lease is RELEASED or EXPIRED. Concurrent
    callers collapse on the primary key — exactly one wins. The winner's
    ``holder`` comes back via RETURNING; a loser gets no row.
  * bounded lease (``lease_seconds``): a holder that crashes mid-run leaves an
    expired lease that the next attempt steals — crash recovery without a
    global lock.
  * ``heartbeat`` extends a still-running holder's expiry (long jobs).
  * ``release`` marks the lease released so a later window can reclaim it
    immediately (also used at clean shutdown).

No global worker lock: unrelated ``lease_key``s never contend. The unique paper
-trade constraint remains DEFENSE-IN-DEPTH only — this lease is the scheduler
-level exactly-once guarantee.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import text
from sqlalchemy.orm import Session

DEFAULT_LEASE_SECONDS = 1800  # 30 min — bounds a stuck holder


def _holder_id(explicit: str | None = None) -> str:
    """Stable-ish per-process holder id. Explicit wins (tests); else a
    hostname:pid style tag. Never used for auth — only for release-ownership
    and diagnostics."""
    if explicit:
        return explicit[:64]
    import os
    import socket
    return f"{socket.gethostname()}:{os.getpid()}"[:64]


def acquire(
    db: Session, lease_key: str, *,
    holder: str | None = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> bool:
    """Try to acquire ``lease_key``. Returns True iff THIS caller now holds it
    (fresh insert, or steal of a released/expired lease). Caller commits."""
    h = _holder_id(holder)
    row = db.execute(
        text(
            """
            INSERT INTO execution_lease
              (lease_key, holder, acquired_at, expires_at, status)
            VALUES
              (:k, :h, now(), now() + make_interval(secs => :sec), 'held')
            ON CONFLICT (lease_key) DO UPDATE
              SET holder = EXCLUDED.holder,
                  acquired_at = now(),
                  expires_at = EXCLUDED.expires_at,
                  status = 'held',
                  released_at = NULL
              WHERE execution_lease.status = 'released'
                 OR execution_lease.expires_at < now()
            RETURNING holder
            """
        ),
        {"k": lease_key[:128], "h": h, "sec": float(int(lease_seconds))},
    ).first()
    # RETURNING yields our holder only when the INSERT or the conditional
    # UPDATE actually wrote our row; a live foreign lease yields no row.
    return row is not None and row[0] == h


def heartbeat(
    db: Session, lease_key: str, *, holder: str | None = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> bool:
    """Extend expiry for a lease this holder still owns. False if we no longer
    own it (stolen after expiry)."""
    h = _holder_id(holder)
    row = db.execute(
        text(
            "UPDATE execution_lease "
            "SET expires_at = now() + make_interval(secs => :sec) "
            "WHERE lease_key = :k AND holder = :h AND status = 'held' "
            "RETURNING holder"
        ),
        {"k": lease_key[:128], "h": h, "sec": float(int(lease_seconds))},
    ).first()
    return row is not None


def release(db: Session, lease_key: str, *, holder: str | None = None) -> bool:
    """Release a lease this holder owns so a later window can reclaim it
    immediately. Idempotent: releasing a non-owned/absent lease returns False.
    Caller commits."""
    h = _holder_id(holder)
    row = db.execute(
        text(
            "UPDATE execution_lease SET status = 'released', released_at = now() "
            "WHERE lease_key = :k AND holder = :h AND status = 'held' "
            "RETURNING lease_key"
        ),
        {"k": lease_key[:128], "h": h},
    ).first()
    return row is not None


def daily_key(job_name: str, as_of: dt.date | None = None) -> str:
    """Canonical lease key for a once-per-trading-day job."""
    d = as_of or dt.datetime.now(dt.timezone.utc).date()
    return f"{job_name}:{d.isoformat()}"
