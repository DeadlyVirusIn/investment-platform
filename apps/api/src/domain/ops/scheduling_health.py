"""Scheduling + snapshot freshness health detection (dev-only, read-only).

Motivated by the 2026-07-11 findings: paper_equity_snapshot ~2 days stale
while freshness reported green, and P0-5C ordering (exits must complete before
entries; snapshots must follow trading). These are pure SQL detectors — they
READ job_schedule / job_run / paper_equity_snapshot and return structured
verdicts. They NEVER write, never create snapshots, never touch prod
schedules. Wire into an owner dashboard / alert, not a mutation path.

Each detector returns a dict with a `status` in
{ok, warn, alert, insufficient_data} plus evidence — the Trust Center honesty
discipline (below the gate, say so; never invent green).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def overdue_jobs(session: Session, *, grace_minutes: int = 120) -> list[dict[str, Any]]:
    """Enabled schedules whose next_run_at is more than grace past due — the
    claim predicate is `next_run_at <= now`, so an overdue row means the job
    is not firing (stuck cron, dead worker, NULL-heal gap). NULL next_run_at
    is reported separately as its own stuck signal."""
    rows = session.execute(text(
        """
        SELECT name,
               next_run_at,
               EXTRACT(EPOCH FROM (now() - next_run_at))/60.0 AS overdue_min
        FROM job_schedule
        WHERE enabled = true
          AND (next_run_at IS NULL
               OR next_run_at < now() - make_interval(mins => :g))
        ORDER BY next_run_at NULLS FIRST
        """
    ), {"g": int(grace_minutes)}).mappings().all()
    out = []
    for r in rows:
        if r["next_run_at"] is None:
            out.append({"name": r["name"], "status": "alert",
                        "reason": "next_run_at IS NULL (never fires)"})
        else:
            mins = float(r["overdue_min"] or 0)
            out.append({
                "name": r["name"],
                "status": "alert" if mins > 24 * 60 else "warn",
                "overdue_minutes": round(mins, 1),
                "next_run_at": r["next_run_at"].isoformat(),
            })
    return out


def snapshot_freshness(
    session: Session, *, now: dt.datetime | None = None,
    max_stale_weekdays: int = 2,
) -> dict[str, Any]:
    """Live paper_equity_snapshot freshness by weekday age (markets close on
    weekends, so calendar age over-reports). Separates engine (canonical) from
    per-user observe-only books. Derives status from the REAL max snapshot_date
    — never from a job's success flag (the incorrect-green trap)."""
    cur = now or dt.datetime.now(dt.timezone.utc)
    # NB: the pattern is a bind param — a literal 'user:%:stock' in text()
    # would parse `:stock` as a named bind.
    row = session.execute(text(
        """
        SELECT
          max(snapshot_date) FILTER (WHERE p.name LIKE :upat) AS user_max,
          max(snapshot_date) FILTER (WHERE p.name NOT LIKE :upat) AS engine_max,
          count(*) FILTER (WHERE p.name LIKE :upat) AS user_rows,
          count(*) FILTER (WHERE p.name NOT LIKE :upat) AS engine_rows
        FROM paper_equity_snapshot s
        JOIN paper_portfolio p ON p.id = s.portfolio_id
        WHERE s.source = 'live'
        """
    ), {"upat": "user:%:stock"}).mappings().one()

    def _weekday_age(d) -> int | None:
        if d is None:
            return None
        cur_d, age = d.date() if hasattr(d, "date") else d, 0
        while cur_d < cur.date():
            cur_d = cur_d + dt.timedelta(days=1)
            if cur_d.weekday() < 5:
                age += 1
        return age

    def _cell(max_date, rows) -> dict:
        if rows == 0:
            return {"status": "insufficient_data", "max_date": None, "rows": 0}
        age = _weekday_age(max_date)
        status = "ok" if age is not None and age <= max_stale_weekdays else "alert"
        return {"status": status, "max_date": max_date.isoformat() if max_date else None,
                "weekday_age": age, "rows": rows}

    engine = _cell(row["engine_max"], row["engine_rows"])
    user = _cell(row["user_max"], row["user_rows"])
    overall = "ok"
    for c in (engine, user):
        if c["status"] == "alert":
            overall = "alert"
        elif c["status"] != "ok" and overall == "ok":
            overall = c["status"]
    return {"overall": overall, "engine": engine, "user": user,
            "derived_from": "max(snapshot_date) — not job success flag"}


def job_success_but_zero_snapshots(
    session: Session, *, job_name: str = "run_paper_trading",
    within_hours: int = 40,
) -> dict[str, Any]:
    """Detect the silent-failure shape: a job reported success recently but no
    live snapshot landed after it started — success with zero expected output.
    Compares the newest successful run's started_at to the newest live snapshot
    created_at."""
    run = session.execute(text(
        """
        SELECT r.started_at, r.status
        FROM job_run r JOIN job_schedule s ON s.id = r.job_schedule_id
        WHERE s.name = :n AND r.started_at > now() - make_interval(hours => :h)
        ORDER BY r.started_at DESC LIMIT 1
        """
    ), {"n": job_name, "h": int(within_hours)}).mappings().first()
    if run is None:
        return {"status": "insufficient_data", "reason": "no recent run"}
    if str(run["status"]).lower() not in ("success", "completed", "ok", "succeeded"):
        return {"status": "ok", "reason": "last run not success — tracked elsewhere"}
    snap_after = session.execute(text(
        "SELECT count(*) FROM paper_equity_snapshot "
        "WHERE source='live' AND created_at >= :t"
    ), {"t": run["started_at"]}).scalar() or 0
    if snap_after == 0:
        return {"status": "alert", "reason": "job success but 0 live snapshots after it",
                "run_started_at": run["started_at"].isoformat()}
    return {"status": "ok", "snapshots_after_run": int(snap_after)}


def exit_before_entry(
    session: Session, *, day: dt.date | None = None,
) -> dict[str, Any]:
    """P0-5C ordering: the exit cycle must COMPLETE before the entry cycle
    STARTS for a trading day (exits free capital/slots before new buys), and
    snapshots must follow. Reports a violation when run_paper_trading started
    before run_paper_exit_cycle finished on the same day."""
    d = day or dt.datetime.now(dt.timezone.utc).date()
    rows = session.execute(text(
        """
        SELECT s.name, min(r.started_at) AS first_start, max(r.finished_at) AS last_finish
        FROM job_run r JOIN job_schedule s ON s.id = r.job_schedule_id
        WHERE s.name IN ('run_paper_exit_cycle','run_paper_trading')
          AND r.started_at::date = :d
        GROUP BY s.name
        """
    ), {"d": d}).mappings().all()
    by = {r["name"]: r for r in rows}
    exit_row, entry_row = by.get("run_paper_exit_cycle"), by.get("run_paper_trading")
    if entry_row is None:
        return {"status": "insufficient_data", "reason": "no entry run on day"}
    if exit_row is None or exit_row["last_finish"] is None:
        return {"status": "warn", "reason": "entry ran without a completed exit cycle",
                "day": d.isoformat()}
    ordered = exit_row["last_finish"] <= entry_row["first_start"]
    return {
        "status": "ok" if ordered else "alert",
        "day": d.isoformat(),
        "exit_finished": exit_row["last_finish"].isoformat(),
        "entry_started": entry_row["first_start"].isoformat(),
        "ordered_correctly": ordered,
    }
