"""Execution lease with fencing — exactly-once across scheduler paths (P0-5).

A lease is keyed by a logical string, e.g. ``run_paper_trading:2026-07-11``
(job + trading date). Semantics:

  * ``acquire`` is atomic (INSERT .. ON CONFLICT DO UPDATE, updating only when
    the existing lease is RELEASED or EXPIRED). Concurrent callers collapse on
    the primary key — exactly one wins and receives a ``LeaseHandle`` carrying
    a monotonic ``fence`` (generation). A loser gets None.
  * **fencing** (the safety property): every steal bumps ``fence``. A holder
    proves current ownership with ``(holder, fence)`` — heartbeat, release, and
    ``verify_ownership`` all require the fence to match. When a slow holder's
    lease expires and another executor steals it, the fence increments, so the
    OLD holder's heartbeat/verify FAIL and it must stop before any further
    mutation. A stale former holder can never continue after ownership changes
    (Kleppmann fencing-token pattern).
  * bounded lease (``lease_seconds``) → crash recovery: a dead holder's expired
    lease is stolen by the next attempt at the next fence.
  * ``heartbeat`` extends a still-owned lease for long jobs; a failed heartbeat
    is the executor's fence signal to STOP.

No global worker lock: unrelated ``lease_key``s never contend. The unique
paper-trade constraint remains DEFENSE-IN-DEPTH only — this lease + fence is
the scheduler-level exactly-once guarantee.
"""

from __future__ import annotations

import dataclasses
import datetime as dt

from sqlalchemy import text
from sqlalchemy.orm import Session

DEFAULT_LEASE_SECONDS = 1800  # 30 min — bounds a stuck holder


@dataclasses.dataclass(frozen=True)
class LeaseHandle:
    """Proof of current ownership. Pass to heartbeat/release/verify_ownership.
    ``fence`` is the generation captured at acquire — the fencing token."""
    lease_key: str
    holder: str
    fence: int


def _holder_id(explicit: str | None = None) -> str:
    """Stable-ish per-process holder id. Explicit wins (tests); else a
    hostname:pid tag. Not auth — the fence is the ownership token; holder is
    for diagnostics + a first-line owner filter."""
    if explicit:
        return explicit[:64]
    import os
    import socket
    return f"{socket.gethostname()}:{os.getpid()}"[:64]


def acquire(
    db: Session, lease_key: str, *,
    holder: str | None = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> LeaseHandle | None:
    """Try to acquire ``lease_key``. Returns a LeaseHandle (with the fence) iff
    THIS caller now holds it (fresh insert, or steal of a released/expired
    lease); else None. Every steal increments the fence. Caller commits."""
    h = _holder_id(holder)
    row = db.execute(
        text(
            """
            INSERT INTO execution_lease
              (lease_key, holder, fence, acquired_at, expires_at, status)
            VALUES
              (:k, :h, 1, now(), now() + make_interval(secs => :sec), 'held')
            ON CONFLICT (lease_key) DO UPDATE
              SET holder = EXCLUDED.holder,
                  fence = execution_lease.fence + 1,
                  acquired_at = now(),
                  expires_at = EXCLUDED.expires_at,
                  status = 'held',
                  released_at = NULL
              WHERE execution_lease.status = 'released'
                 OR execution_lease.expires_at < now()
            RETURNING holder, fence
            """
        ),
        {"k": lease_key[:128], "h": h, "sec": float(int(lease_seconds))},
    ).first()
    if row is None or row[0] != h:
        return None
    return LeaseHandle(lease_key=lease_key[:128], holder=h, fence=int(row[1]))


def verify_ownership(db: Session, handle: LeaseHandle) -> bool:
    """True iff ``handle`` is STILL the live owner (holder+fence match, held,
    not expired). The executor MUST call this before each batch of mutations:
    a False result means the lease was stolen (higher fence) or expired — the
    holder must stop writing immediately."""
    row = db.execute(
        text(
            "SELECT 1 FROM execution_lease "
            "WHERE lease_key = :k AND holder = :h AND fence = :f "
            "AND status = 'held' AND expires_at > now()"
        ),
        {"k": handle.lease_key, "h": handle.holder, "f": handle.fence},
    ).first()
    return row is not None


def heartbeat(
    db: Session, handle: LeaseHandle, *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> bool:
    """Extend expiry for a lease this handle still owns (holder+fence, not yet
    expired). False when ownership was lost — the executor's signal to STOP
    before further mutations. Crucially requires ``expires_at > now()``: an
    already-expired lease cannot be heartbeated back to life (that window
    belongs to whoever steals it), so a stalled holder can never revive a lease
    another executor is about to take."""
    row = db.execute(
        text(
            "UPDATE execution_lease "
            "SET expires_at = now() + make_interval(secs => :sec) "
            "WHERE lease_key = :k AND holder = :h AND fence = :f "
            "AND status = 'held' AND expires_at > now() "
            "RETURNING fence"
        ),
        {"k": handle.lease_key, "h": handle.holder, "f": handle.fence,
         "sec": float(int(lease_seconds))},
    ).first()
    return row is not None


def release(db: Session, handle: LeaseHandle) -> bool:
    """Release a lease this handle owns (holder+fence-specific) so a later
    window reclaims it immediately. False if we no longer own it. Caller
    commits."""
    row = db.execute(
        text(
            "UPDATE execution_lease SET status = 'released', released_at = now() "
            "WHERE lease_key = :k AND holder = :h AND fence = :f AND status = 'held' "
            "RETURNING lease_key"
        ),
        {"k": handle.lease_key, "h": handle.holder, "f": handle.fence},
    ).first()
    return row is not None


def daily_key(job_name: str, as_of: dt.date | None = None) -> str:
    """Canonical lease key for a once-per-trading-day job."""
    d = as_of or dt.datetime.now(dt.timezone.utc).date()
    return f"{job_name}:{d.isoformat()}"
