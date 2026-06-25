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
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.api.admin_guard import require_owner
from apps.api.src.api.feedback_report import build_report
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
