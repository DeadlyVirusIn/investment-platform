"""Owner admin console — read-only aggregates (Admin-1).

GET /api/admin/overview, GET /api/admin/feedback. Owner-only — ``require_owner``
is attached to the router, so every endpoint here is guarded (404 for anyone
but the owner). READ-ONLY: SELECTs only, never a write.

Privacy: returns ONLY safe aggregates. Never serializes password_hash, session
tokens, provider keys, env values, or raw IDs beyond the owner's own audit
context. Feedback is the anonymized ``build_report`` (counts + capped text).
"""

from __future__ import annotations

import datetime as dt
import os
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.api.admin_guard import require_owner
from apps.api.src.api.feedback_report import build_report
from apps.api.src.config import settings
from apps.api.src.db import get_session

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_owner)])

# Heuristic markers separating QA/test accounts from real testers. Not a hard
# classification — surfaced as an estimate the owner can sanity-check.
_QA_EMAIL_MARKERS = ("@ex.com", "@example.com", "browsercheck", "+test")


@router.get("/overview")
def overview(db: Session = Depends(get_session)) -> dict[str, Any]:
    def scalar(q: str, **p: Any) -> Any:
        return db.execute(text(q), p).scalar()

    total_users = int(scalar("SELECT count(*) FROM app_user") or 0)

    qa_clause = " OR ".join(f"lower(email) LIKE :m{i}" for i in range(len(_QA_EMAIL_MARKERS)))
    qa_params = {f"m{i}": f"%{m}%" for i, m in enumerate(_QA_EMAIL_MARKERS)}
    qa_users = int(scalar(f"SELECT count(*) FROM app_user WHERE {qa_clause}", **qa_params) or 0)

    new_24h = int(scalar("SELECT count(*) FROM app_user WHERE created_at > now() - interval '24 hours'") or 0)
    new_7d = int(scalar("SELECT count(*) FROM app_user WHERE created_at > now() - interval '7 days'") or 0)

    signups_by_day = [
        {"day": str(r[0]), "count": int(r[1])}
        for r in db.execute(text(
            "SELECT created_at::date AS d, count(*) FROM app_user "
            "GROUP BY 1 ORDER BY 1 DESC LIMIT 14"
        )).all()
    ]

    profiles_started = int(scalar("SELECT count(*) FROM user_profile") or 0)
    feedback_total = int(scalar("SELECT count(*) FROM user_feedback_signal") or 0)
    price_bar = scalar("SELECT max(ts)::date FROM price_bar")
    rec_latest = scalar("SELECT max(generated_at) FROM recommendation")

    return {
        "users": {
            "total": total_users,
            "qa_estimated": qa_users,
            "real_estimated": max(total_users - qa_users, 0),
            "new_24h": new_24h,
            "new_7d": new_7d,
            "profiles_started": profiles_started,
            "signups_by_day": signups_by_day,
        },
        "feedback": {"signals_total": feedback_total},
        "data": {
            "price_bar_date": str(price_bar) if price_bar else None,
            "recommendation_latest": rec_latest.isoformat() if rec_latest else None,
        },
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


@router.get("/feedback")
def feedback(db: Session = Depends(get_session)) -> dict[str, Any]:
    """Anonymized feedback report — counts, ratios, and capped text samples.

    Reuses ``feedback_report.build_report``: no user_id, no email, no session
    token; free text is length-capped and identity-stripped.
    """
    return build_report(db, days=None)


_ERR_CAP = 240  # max chars of any error message surfaced (redaction cap)


@router.get("/jobs")
def jobs(db: Session = Depends(get_session)) -> dict[str, Any]:
    """Scheduler state — job_schedule + recent job_run. Read-only. Error text
    is length-capped; no secrets are stored in these columns."""
    schedule = [
        {
            "name": r["name"], "enabled": bool(r["enabled"]),
            "cron": r["cron_expr"],
            "last_run_at": r["last_run_at"].isoformat() if r["last_run_at"] else None,
            "next_run_at": r["next_run_at"].isoformat() if r["next_run_at"] else None,
        }
        for r in db.execute(text(
            "SELECT name, enabled, cron_expr, last_run_at, next_run_at "
            "FROM job_schedule ORDER BY name"
        )).mappings().all()
    ]
    recent = [
        {
            "name": r["name"], "status": r["status"],
            "started_at": r["started_at"].isoformat() if r["started_at"] else None,
            "duration_seconds": (
                round(float(r["duration_seconds"]), 1) if r["duration_seconds"] is not None else None
            ),
            "error": (str(r["error_message"])[:_ERR_CAP] if r["error_message"] else None),
        }
        for r in db.execute(text(
            "SELECT js.name, jr.status, jr.started_at, jr.duration_seconds, jr.error_message "
            "FROM job_run jr JOIN job_schedule js ON js.id = jr.job_schedule_id "
            "ORDER BY jr.started_at DESC LIMIT 25"
        )).mappings().all()
    ]
    # Stale = enabled job whose newest successful run is > 26h old (or never).
    stale = [
        r["name"] for r in db.execute(text(
            "SELECT js.name, max(jr.started_at) FILTER (WHERE jr.status = 'success') AS ok "
            "FROM job_schedule js LEFT JOIN job_run jr ON jr.job_schedule_id = js.id "
            "WHERE js.enabled GROUP BY js.name "
            "HAVING max(jr.started_at) FILTER (WHERE jr.status = 'success') IS NULL "
            "   OR max(jr.started_at) FILTER (WHERE jr.status = 'success') < now() - interval '26 hours'"
        )).mappings().all()
    ]
    failed_recent = sum(1 for r in recent if r["status"] not in ("success", "running", None))
    return {
        "schedule": schedule,
        "recent_runs": recent,
        "summary": {
            "scheduled": len(schedule),
            "stale": stale,
            "failed_in_recent": failed_recent,
        },
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


# Host-emitted health JSON, bind-mounted read-only into the api container by the
# healthcheck script. Avoids a docker-socket mount and any request-path shell-out.
_HEALTH_JSON_PATH = os.getenv("ARTHOS_HEALTH_JSON", "/var/health/status.json")
_HEALTH_STALE_SECONDS = 30 * 60  # healthcheck runs every 15m; >30m = stale


@router.get("/system")
def system(db: Session = Depends(get_session)) -> dict[str, Any]:
    """VM/system health from the healthcheck JSON (read-only) + a live DB ping.
    Degrades gracefully when the JSON is missing or stale — never shells out,
    never reads the docker socket, never returns secrets."""
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    health: dict[str, Any] = {"available": False, "fields": {}}
    try:
        import json
        with open(_HEALTH_JSON_PATH, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        ts = raw.get("ts")
        age = None
        if ts:
            try:
                age = (
                    dt.datetime.now(dt.timezone.utc)
                    - dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                ).total_seconds()
            except Exception:
                age = None
        # Allowlist the safe fields only — never echo arbitrary keys.
        safe_keys = (
            "site", "api_health", "tunnel", "bot", "worker_cron", "worker_tickloop",
            "disk_pct", "mem_avail_mb", "swap_free_mb", "job_age_h", "ts",
        )
        health = {
            "available": True,
            "stale": (age is not None and age > _HEALTH_STALE_SECONDS),
            "age_seconds": round(age) if age is not None else None,
            "fields": {k: raw.get(k) for k in safe_keys if k in raw},
        }
    except FileNotFoundError:
        health = {"available": False, "reason": "no healthcheck JSON yet", "fields": {}}
    except Exception:
        health = {"available": False, "reason": "unreadable healthcheck JSON", "fields": {}}

    return {
        "db_connectivity": db_ok,
        "app_version": settings.APP_VERSION,
        "health": health,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
