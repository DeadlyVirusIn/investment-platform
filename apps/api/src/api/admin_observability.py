"""Admin Observability aggregator — GET /api/admin/observability.

Single read-only pane for Ops: cron/job state, data freshness matrix,
worker liveness inference, DB migration head, and canary-dormancy
assertion. Designed for the V2 /v2/admin/observability surface.

Strict invariants (mirrors api/freshness.py):
  * READ-ONLY. Issues only SELECTs. No INSERT/UPDATE/DELETE, no DDL,
    no migration. Safe to call against production.
  * Defensive everywhere — a missing table / column / dead session
    yields ``status: "unknown"`` (or null) for that field and the
    endpoint still returns 200 with the full skeleton.
  * No fabricated timestamps. When a source has no usable column we
    return null + ``unknown`` — never ``now()``.
  * Reuses freshness._evaluate_channels so the channel SLA logic is
    not duplicated.
"""

from __future__ import annotations

import datetime as dt
import os
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from apps.api.src.build_provenance import get_build_provenance
from apps.api.src.config import settings
from apps.api.src.db import SessionLocal

# Reuse the freshness channel engine (DRY) — same six-channel logic the
# /api/freshness pane uses, plus its helpers.
from apps.api.src.api.freshness import (
    _aggregate_overall,
    _evaluate_channels,
    _human_age,
    _is_market_hours,
    _now_utc,
)

router = APIRouter(prefix="/admin", tags=["admin"])

def _derive_expected_db_head() -> str | None:
    """Expected DB head, derived from the Alembic migration scripts bundled
    in THIS image — auto-tracks every migration (no hardcoded constant to
    bump). None when underivable (e.g. tree absent or multiple heads), in
    which case drift is treated as 'unknown' rather than a false warning."""
    try:
        from pathlib import Path
        from alembic.script import ScriptDirectory
        # .../apps/api/src/api/admin_observability.py → parents[4] == repo root
        root = Path(__file__).resolve().parents[4]
        return ScriptDirectory(str(root / "infra" / "alembic")).get_current_head()
    except Exception:
        return None


# Surfaced so the page can flag genuine drift without hard-coding the
# expectation in the client. Computed once at import.
_EXPECTED_DB_HEAD = _derive_expected_db_head()

# Process-start marker (import time). Honest "api process uptime" — resets
# only if the api process restarts, which is exactly what we want to show.
_PROCESS_START = _now_utc()


# ---------------------------------------------------------------------------
# Low-level defensive readers
# ---------------------------------------------------------------------------


def _rollback(session: Session) -> None:
    """Clear an aborted transaction so the next read can run. Postgres
    aborts the whole tx on the first failed statement; without this a
    single bad query (e.g. a missing column) would cascade every
    subsequent reader to None."""
    try:
        session.rollback()
    except Exception:  # noqa: BLE001
        pass


def _safe_max_ts(session: Session, sql: str) -> dt.datetime | None:
    """SELECT MAX(...) defensively. Any failure → None."""
    try:
        row = session.execute(text(sql)).first()
    except (SQLAlchemyError, Exception):  # noqa: BLE001
        _rollback(session)
        return None
    if row is None or row[0] is None:
        return None
    val = row[0]
    if isinstance(val, dt.datetime):
        return val
    if isinstance(val, dt.date):
        return dt.datetime(val.year, val.month, val.day, tzinfo=dt.timezone.utc)
    return None


def _safe_count(session: Session, sql: str) -> int | None:
    try:
        row = session.execute(text(sql)).first()
    except (SQLAlchemyError, Exception):  # noqa: BLE001
        _rollback(session)
        return None
    if row is None or row[0] is None:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def _safe_scalar_str(session: Session, sql: str) -> str | None:
    try:
        row = session.execute(text(sql)).first()
    except (SQLAlchemyError, Exception):  # noqa: BLE001
        _rollback(session)
        return None
    if row is None or row[0] is None:
        return None
    return str(row[0])


def _safe_row(session: Session, sql: str) -> Any | None:
    """Return the first result row defensively. Any failure → None +
    rollback so the next reader survives the aborted transaction."""
    try:
        return session.execute(text(sql)).first()
    except (SQLAlchemyError, Exception):  # noqa: BLE001
        _rollback(session)
        return None


def _market_state(now: dt.datetime) -> dict[str, Any]:
    """Open / closed / weekend, reusing freshness._is_market_hours.
    Holidays are NOT detectable (no holiday calendar in the repo) — we
    expose is_holiday=None rather than guessing."""
    weekend = False
    try:
        from zoneinfo import ZoneInfo
        local = now.astimezone(ZoneInfo("America/New_York"))
        weekend = local.weekday() >= 5
    except Exception:  # noqa: BLE001
        weekend = False
    is_open = _is_market_hours(now)
    if is_open:
        label = "Market open"
    elif weekend:
        label = "Weekend — market closed"
    else:
        label = "Market closed"
    return {
        "is_open": is_open,
        "is_weekend": weekend,
        "is_holiday": None,  # not detectable — honest unknown
        "label": label,
    }


def _hours_since(ts: dt.datetime | None, now: dt.datetime) -> float | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return (now - ts).total_seconds() / 3600.0


def _iso(ts: dt.datetime | None) -> str | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return ts.isoformat()


# ---------------------------------------------------------------------------
# Freshness matrix — 9 rows the Ops page renders. Each row is classified by
# its own expected cadence (hours): fresh < cadence, degraded < 2x cadence,
# stale beyond, unknown when no timestamp.
# ---------------------------------------------------------------------------

# (key, label, expected_cadence_hours, source, reader_sql | None,
#  daily_settle_hour_utc | None)
#
# daily_settle_hour_utc — Opt-Obs-Fix2. When set, the row is a Mon-Fri
# post-close daily job and is classified WEEKEND-AWARE against the last
# expected scheduled run (see _classify_weekday_daily) instead of the raw
# wall-clock cadence. This clears the false 'stale' these rows showed
# every Monday pre-close (Friday data is legitimately ~65h old over a
# weekend, which exceeded the 2x raw cadence). It does NOT widen cadence:
# a genuine WEEKDAY stall still ages past the prior expected run and
# flags. The hour is the job's settle boundary in UTC (all four current
# daily writers complete by ~22:00-23:10 UTC; 22 is at/below every
# writer's completion time so a healthy same-day write reads fresh).
_MATRIX_SPEC: list[
    tuple[str, str, float | None, str, str | None, int | None]
] = [
    # RC1: market_prices freshness = last successful ingest_prices_daily
    # run, NOT MAX(price_bar.ts). Bar ts is stored at trading-day
    # midnight and EOD bars land ~02:00 UTC the next day, so a ts-age
    # classifier could never read 'fresh' (best case ~26h) and flagged
    # 'stale' on perfectly healthy data. Anchoring to the ingest job's
    # last success keeps a real ingest stall visible (the success ts
    # ages) while not penalising the midnight-ts storage convention.
    # Cadence 26h = daily run + grace. Weekend-aware (settle 22:00 UTC).
    ("market_prices", "Market prices", 26.0, "ingest_prices_daily (last success)",
     "SELECT MAX(jr.finished_at) FROM job_run jr "
     "JOIN job_schedule js ON js.id = jr.job_schedule_id "
     "WHERE js.name = 'ingest_prices_daily' AND jr.status = 'success'", 22),
    ("intraday_tape", "Intraday tape", 1.0, "price_bar (intraday)",
     "SELECT MAX(ts) FROM price_bar WHERE timeframe IN ('1m','5m','15m')", None),
    ("options_chains", "Options chains", 6.0, "options_chain_ingest_run",
     "SELECT MAX(finished_at) FROM options_chain_ingest_run", None),
    ("options_opportunities", "Options opportunities", 24.0,
     "options_strategy_candidate",
     "SELECT MAX(created_at) FROM options_strategy_candidate", None),
    ("news_events", "News / events", 6.0, "news_item",
     "SELECT MAX(ingested_at) FROM news_item", None),
    ("sec_filings", "SEC filings", None, "(no source table)", None, None),
    # RC3: use recorded_at (real valuation instant), not snapshot_date.
    # snapshot_date is a DATE → promoted to UTC midnight by _safe_max_ts,
    # inflating age up to +24h (a book valued 17:50 read as ~25h old).
    # Weekend-aware (run_paper_exit_cycle settles ~23:00 UTC Mon-Fri).
    ("paper_snapshots", "Paper snapshots", 24.0,
     "paper_equity_snapshot.recorded_at (live)",
     "SELECT MAX(recorded_at) FROM paper_equity_snapshot "
     "WHERE source = 'live'", 22),
    # RC4: align to the ~24h daily recommendation cadence + grace. The
    # prior 16h cadence flagged a healthy daily cycle 'degraded' for
    # ~8h every day. Weekend-aware (run_recommendations settles ~22:30).
    ("recommendations", "Recommendations", 26.0, "recommendation",
     "SELECT MAX(generated_at) FROM recommendation", 22),
    ("reasoning_envelopes", "Reasoning envelopes", 24.0,
     "envelope_generation_run",
     "SELECT MAX(created_at) FROM envelope_generation_run", 22),
]


def _classify_cadence(hours: float | None, cadence: float | None) -> str:
    if cadence is None or hours is None:
        return "unknown"
    if hours < cadence:
        return "fresh"
    if hours < cadence * 2:
        return "degraded"
    return "stale"


# ---------------------------------------------------------------------------
# Weekend-aware classifier for Mon-Fri post-close daily jobs (Opt-Obs-Fix2)
# ---------------------------------------------------------------------------


def _weekday_settle_on_or_before(
    now: dt.datetime, settle_hour: int,
) -> dt.datetime:
    """Latest datetime at ``settle_hour`` UTC that is (a) <= now and (b) a
    weekday (Mon-Fri). This is the most recent moment a Mon-Fri daily job
    was expected to have completed. Walks back over weekends."""
    cand = now.replace(
        hour=settle_hour, minute=0, second=0, microsecond=0,
    )
    for _ in range(10):
        if cand <= now and cand.weekday() < 5:
            return cand
        cand = (cand - dt.timedelta(days=1)).replace(
            hour=settle_hour, minute=0, second=0, microsecond=0,
        )
    return cand


def _prev_weekday_settle(
    expected: dt.datetime, settle_hour: int,
) -> dt.datetime:
    """The expected settle one weekday BEFORE ``expected`` (skip weekends)."""
    cand = (expected - dt.timedelta(days=1)).replace(
        hour=settle_hour, minute=0, second=0, microsecond=0,
    )
    for _ in range(10):
        if cand.weekday() < 5:
            return cand
        cand -= dt.timedelta(days=1)
    return cand


def _classify_weekday_daily(
    ts: dt.datetime | None, now: dt.datetime, settle_hour: int,
) -> str:
    """Weekend-aware freshness for Mon-Fri post-close daily jobs.

      * fresh    — data is at least as new as the last expected weekday
                   run (e.g. Monday 11:00 ET, the last run was Friday's;
                   Friday data is fresh, not stale).
      * degraded — data missed the latest expected run but is no older
                   than the one before it (one cycle behind).
      * stale    — older than two expected weekday runs → a genuine
                   weekday stall, still surfaced.
    """
    if ts is None:
        return "unknown"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    expected = _weekday_settle_on_or_before(now, settle_hour)
    prev = _prev_weekday_settle(expected, settle_hour)
    if ts >= expected:
        return "fresh"
    if ts >= prev:
        return "degraded"
    return "stale"


def _build_matrix(session: Session | None,
                  now: dt.datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, label, cadence, source, sql, settle_hour in _MATRIX_SPEC:
        ts = (
            _safe_max_ts(session, sql)
            if (session is not None and sql is not None)
            else None
        )
        hours = _hours_since(ts, now)
        # Opt-Obs-Fix2 — Mon-Fri post-close daily rows use the weekend-aware
        # classifier; all others keep the raw wall-clock cadence classifier.
        if key == "options_chains":
            # Intraday, market-aware. Reuse the single source of truth in
            # freshness.py: during market hours genuine staleness still
            # degrades (fresh <6h / degraded 6-12h / stale >12h); when the
            # market is closed a last-session snapshot reads fresh (no false
            # overnight/weekend degradation).
            from apps.api.src.api.freshness import _classify_options
            status = _classify_options(hours, now)
        elif settle_hour is not None:
            status = _classify_weekday_daily(ts, now, settle_hour)
        else:
            status = _classify_cadence(hours, cadence)
        rows.append({
            "key": key,
            "label": label,
            "latest": _iso(ts),
            "age_hours": round(hours, 2) if hours is not None else None,
            "age_human": _human_age(hours) if hours is not None else None,
            "expected_cadence_hours": cadence,
            "status": status,
            "source": source,
        })
    return rows


# ---------------------------------------------------------------------------
# Jobs — schedule + latest run + explicit last-success / last-failure.
# ---------------------------------------------------------------------------


def _build_jobs(session: Session) -> list[dict[str, Any]]:
    try:
        rows = session.execute(text("""
            SELECT
                js.name, js.cron_expr, js.enabled,
                js.last_run_at, js.next_run_at,
                (SELECT jr.status FROM job_run jr
                   WHERE jr.job_schedule_id = js.id
                   ORDER BY jr.started_at DESC LIMIT 1) AS last_status,
                (SELECT jr.error_message FROM job_run jr
                   WHERE jr.job_schedule_id = js.id
                   ORDER BY jr.started_at DESC LIMIT 1) AS last_error,
                (SELECT jr.duration_seconds FROM job_run jr
                   WHERE jr.job_schedule_id = js.id
                   ORDER BY jr.started_at DESC LIMIT 1) AS last_duration,
                (SELECT MAX(jr.finished_at) FROM job_run jr
                   WHERE jr.job_schedule_id = js.id
                   AND jr.status = 'success') AS last_success_at,
                (SELECT MAX(jr.started_at) FROM job_run jr
                   WHERE jr.job_schedule_id = js.id
                   AND jr.status = 'error') AS last_failure_at
            FROM job_schedule js
            ORDER BY js.name
        """)).mappings().all()
    except (SQLAlchemyError, Exception):  # noqa: BLE001
        _rollback(session)
        return []

    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({
            "name": r["name"],
            "cron": r["cron_expr"],
            "enabled": bool(r["enabled"]),
            "last_run_at": _iso(r["last_run_at"]),
            "next_run_at": _iso(r["next_run_at"]),
            "last_status": r["last_status"],
            "last_success_at": _iso(r["last_success_at"]),
            "last_failure_at": _iso(r["last_failure_at"]),
            "last_duration_seconds": (
                str(r["last_duration"]) if r["last_duration"] is not None
                else None
            ),
            "last_error": r["last_error"],
        })
    return out


def _most_recent_run_at(session: Session) -> dt.datetime | None:
    return _safe_max_ts(session, "SELECT MAX(started_at) FROM job_run")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/observability")
def observability() -> dict[str, Any]:
    """Read-only operational snapshot for the Ops page."""
    now = _now_utc()

    session: Session | None = None
    db_reachable = False
    try:
        session = SessionLocal()
        # cheap probe
        session.execute(text("SELECT 1"))
        db_reachable = True
    except Exception:  # noqa: BLE001
        session = None

    # --- DB head + postmaster uptime (read-only) ---
    db_head = (
        _safe_scalar_str(session, "SELECT version_num FROM alembic_version")
        if session is not None else None
    )
    pg_start = (
        _safe_max_ts(session, "SELECT pg_postmaster_start_time()")
        if session is not None else None
    )
    db_uptime_seconds = (
        int((now - pg_start).total_seconds()) if pg_start is not None else None
    )

    # --- channels (reuse freshness engine) + matrix ---
    channels = _evaluate_channels(session, now) if session is not None else {}
    overall = _aggregate_overall(channels) if channels else "unknown"
    matrix = _build_matrix(session, now)

    # --- jobs ---
    jobs = _build_jobs(session) if session is not None else []

    # --- worker liveness inference (no process uptime in DB) ---
    last_run = _most_recent_run_at(session) if session is not None else None
    last_run_hours = _hours_since(last_run, now)
    if last_run_hours is None:
        tickloop_alive: bool | None = None
        worker_note = "No job_run history — worker liveness unknown."
    elif last_run_hours <= 26:
        tickloop_alive = True
        worker_note = f"Last job run {_human_age(last_run_hours)} ago."
    else:
        tickloop_alive = False
        worker_note = (
            f"No job run in {_human_age(last_run_hours)} — "
            f"worker may be stalled."
        )

    # --- canary dormancy assertion ---
    canary_count = (
        _safe_count(session, "SELECT COUNT(*) FROM options_canary_lifecycle_run")
        if session is not None else None
    )
    candidate_count = (
        _safe_count(session, "SELECT COUNT(*) FROM options_strategy_candidate")
        if session is not None else None
    )
    canary_status = (
        "dormant" if canary_count == 0
        else "active" if (canary_count or 0) > 0
        else "unknown"
    )

    # --- counts ---
    counts = {
        "assets": _safe_count(session, "SELECT COUNT(*) FROM asset")
        if session is not None else None,
        "price_bars": _safe_count(session, "SELECT COUNT(*) FROM price_bar")
        if session is not None else None,
        "recommendations": _safe_count(
            session, "SELECT COUNT(*) FROM recommendation")
        if session is not None else None,
    }

    # --- market status (reuse freshness heuristic; no DB) ---
    market = _market_state(now)

    # --- error counts last 24h (job_run) ---
    err_row = (
        _safe_row(session, """
            SELECT
              count(*) FILTER (WHERE status='error'
                               AND started_at > now() - interval '24 hours'),
              count(*) FILTER (WHERE status='success'
                               AND started_at > now() - interval '24 hours'),
              count(*) FILTER (WHERE started_at > now() - interval '24 hours')
            FROM job_run
        """) if session is not None else None
    )
    if err_row is not None:
        fail24 = int(err_row[0] or 0)
        ok24 = int(err_row[1] or 0)
        tot24 = int(err_row[2] or 0)
        errors_24h = {
            "failures": fail24,
            "successes": ok24,
            "total": tot24,
            "failure_rate_pct": round(100.0 * fail24 / tot24, 1) if tot24 else 0.0,
        }
    else:
        errors_24h = {
            "failures": None, "successes": None,
            "total": None, "failure_rate_pct": None,
        }

    # --- slowest jobs (top 5 by max duration) ---
    slowest_jobs: list[dict[str, Any]] = []
    if session is not None:
        try:
            rows = session.execute(text("""
                SELECT js.name,
                       max(jr.duration_seconds) AS max_d,
                       avg(jr.duration_seconds) AS avg_d,
                       max(jr.started_at)       AS last_run
                FROM job_run jr
                JOIN job_schedule js ON js.id = jr.job_schedule_id
                WHERE jr.duration_seconds IS NOT NULL
                GROUP BY js.name
                ORDER BY max_d DESC NULLS LAST
                LIMIT 5
            """)).mappings().all()
            for r in rows:
                slowest_jobs.append({
                    "name": r["name"],
                    "max_duration_seconds": (
                        round(float(r["max_d"]), 2) if r["max_d"] is not None else None
                    ),
                    "avg_duration_seconds": (
                        round(float(r["avg_d"]), 2) if r["avg_d"] is not None else None
                    ),
                    "last_run_at": _iso(r["last_run"]),
                })
        except (SQLAlchemyError, Exception):  # noqa: BLE001
            _rollback(session)
            slowest_jobs = []

    # --- DB connection health (pg_stat_activity vs max_connections) ---
    conn_row = (
        _safe_row(session, """
            SELECT
              count(*) FILTER (WHERE state = 'active'),
              count(*) FILTER (WHERE state = 'idle'),
              count(*),
              (SELECT setting::int FROM pg_settings
                 WHERE name = 'max_connections')
            FROM pg_stat_activity
        """) if session is not None else None
    )
    if conn_row is not None:
        c_active = int(conn_row[0] or 0)
        c_idle = int(conn_row[1] or 0)
        c_total = int(conn_row[2] or 0)
        c_max = int(conn_row[3]) if conn_row[3] is not None else None
        c_util = round(100.0 * c_total / c_max, 1) if c_max else None
        if c_util is None:
            c_status = "unknown"
        elif c_util < 70:
            c_status = "healthy"
        elif c_util < 90:
            c_status = "warning"
        else:
            c_status = "critical"
        db_connections = {
            "active": c_active, "idle": c_idle, "total": c_total,
            "max_connections": c_max, "utilization_pct": c_util,
            "status": c_status,
        }
    else:
        db_connections = {
            "active": None, "idle": None, "total": None,
            "max_connections": None, "utilization_pct": None,
            "status": "unknown",
        }

    if session is not None:
        try:
            session.close()
        except Exception:  # noqa: BLE001
            pass

    # --- alerts (derived; never fabricated) ---
    alerts: list[dict[str, str]] = []
    for j in jobs:
        if j["last_status"] == "error":
            alerts.append({
                "severity": "failed",
                "area": f"job:{j['name']}",
                "message": f"Last run of {j['name']} failed.",
            })
    for m in matrix:
        if m["status"] == "stale":
            alerts.append({
                "severity": "stale",
                "area": f"data:{m['key']}",
                "message": f"{m['label']} is stale ({m['age_human']} old).",
            })
    if tickloop_alive is False:
        alerts.append({
            "severity": "warning",
            "area": "worker:tickloop",
            "message": worker_note,
        })
    if (canary_count or 0) > 0:
        alerts.append({
            "severity": "failed",
            "area": "canary",
            "message": (
                f"Canary lifecycle has {canary_count} run(s) — "
                f"expected 0 (canary engine is not active)."
            ),
        })
    if db_head and _EXPECTED_DB_HEAD and db_head != _EXPECTED_DB_HEAD:
        alerts.append({
            "severity": "warning",
            "area": "db",
            "message": f"DB head {db_head} != expected {_EXPECTED_DB_HEAD}.",
        })

    # --- overall system status (worst-of) ---
    if not db_reachable:
        system_status = "failed"
    elif any(a["severity"] == "failed" for a in alerts):
        system_status = "failed"
    elif any(a["severity"] in ("stale", "warning") for a in alerts):
        system_status = "degraded"
    else:
        system_status = "healthy"

    failed_jobs = sum(1 for j in jobs if j["last_status"] == "error")
    stale_count = sum(1 for m in matrix if m["status"] == "stale")

    return {
        "as_of": now.isoformat(),
        "system_status": system_status,
        "api": {
            "status": "ok",
            "version": settings.APP_VERSION,
            "uptime_seconds": int((now - _PROCESS_START).total_seconds()),
            # P0-4 — build provenance (image <-> git traceability). NOTE:
            # this is the API container's provenance; worker provenance is
            # in the worker boot log ("build-provenance ..." line).
            "provenance": get_build_provenance(),
        },
        "db": {
            "reachable": db_reachable,
            "head": db_head,
            "expected_head": _EXPECTED_DB_HEAD,
            "head_matches": (
                (db_head == _EXPECTED_DB_HEAD)
                if (db_head and _EXPECTED_DB_HEAD)
                else (None if not db_head else True)
            ),
            "postmaster_start_time": _iso(pg_start),
            "uptime_seconds": db_uptime_seconds,
        },
        "deploy": {
            "app_version": settings.APP_VERSION,
            # Optional build-provenance env — honest null when unset.
            "git_sha": (
                os.environ.get("GIT_SHA")
                or os.environ.get("VCS_REF")
                or os.environ.get("SOURCE_COMMIT")
            ),
            "image_tag": (
                os.environ.get("IMAGE_TAG")
                or os.environ.get("API_IMAGE_TAG")
            ),
            "build_time": os.environ.get("BUILD_TIME"),
            "db_head": db_head,
            "expected_head": _EXPECTED_DB_HEAD,
        },
        "workers": {
            "tickloop_alive": tickloop_alive,
            "last_job_run_at": _iso(last_run),
            "note": worker_note,
        },
        "canary": {
            "lifecycle_run_count": canary_count,
            "strategy_candidate_count": candidate_count,
            "status": canary_status,
        },
        "freshness": {
            "overall": overall,
            "last_successful_cycle_at": (
                channels.get("recommendations", {}).get("as_of")
                if channels else None
            ),
            "channels": channels,
            "matrix": matrix,
            "stale_count": stale_count,
        },
        "jobs": jobs,
        "failed_jobs_count": failed_jobs,
        "slowest_jobs": slowest_jobs,
        "errors_24h": errors_24h,
        "market": market,
        "db_connections": db_connections,
        "counts": counts,
        "alerts": alerts,
    }
