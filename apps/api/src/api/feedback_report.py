"""M5A — demand-validation reporting (read-only aggregation; NO public API).

Pure aggregation (`aggregate_feedback`) + DB helpers (`load_signals`,
`trend_by_day`, `build_report`). The output is deliberately anonymized: no
email, no raw user_id, no session token — only counts, ratios, and capped
free-text samples. Used by scripts/report_feedback_signals.py.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

USEFUL, NOT_USEFUL = "trust_useful", "trust_not_useful"
AGAIN, NOT_AGAIN = "would_use_again", "would_not_use_again"


def _ratio(a: int, b: int) -> float | None:
    tot = a + b
    return round(a / tot, 4) if tot else None


def aggregate_feedback(rows: list[dict[str, Any]], *, sample_cap: int = 5, text_cap: int = 160) -> dict[str, Any]:
    """Pure aggregation. `rows` are signal dicts (user_id, session_or_device_id,
    surface, signal_type, value, created_at). Returns an anonymized summary."""
    total = len(rows)
    authed_users = {r["user_id"] for r in rows if r.get("user_id")}
    anon_ctx = {r["session_or_device_id"] for r in rows if not r.get("user_id") and r.get("session_or_device_id")}

    by_surface: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for r in rows:
        by_surface[r["surface"]] = by_surface.get(r["surface"], 0) + 1
        by_type[r["signal_type"]] = by_type.get(r["signal_type"], 0) + 1

    useful, not_useful = by_type.get(USEFUL, 0), by_type.get(NOT_USEFUL, 0)
    again, not_again = by_type.get(AGAIN, 0), by_type.get(NOT_AGAIN, 0)

    # Anonymized free-text samples: capped count + capped length, no identity.
    samples: list[str] = []
    for r in rows:
        if r["signal_type"] == "feedback_text" and r.get("value"):
            samples.append(str(r["value"])[:text_cap])
            if len(samples) >= sample_cap:
                break

    return {
        "total_signals": total,
        "authenticated_users": len(authed_users),
        "anonymous_contexts": len(anon_ctx),
        "by_surface": dict(sorted(by_surface.items())),
        "by_type": dict(sorted(by_type.items())),
        "useful": useful,
        "not_useful": not_useful,
        "useful_ratio": _ratio(useful, not_useful),
        "would_use_again": again,
        "would_not_use_again": not_again,
        "would_use_again_ratio": _ratio(again, not_again),
        "beta_interest": by_type.get("beta_interest", 0),
        "feedback_text_count": by_type.get("feedback_text", 0),
        "text_samples": samples,  # anonymized + capped
    }


def load_signals(db: Session, *, days: int | None = None) -> list[dict[str, Any]]:
    q = "SELECT user_id, session_or_device_id, surface, signal_type, value, created_at FROM user_feedback_signal"
    params: dict[str, Any] = {}
    if days is not None:
        q += " WHERE created_at > now() - make_interval(days => :d)"
        params["d"] = int(days)
    q += " ORDER BY created_at DESC"
    return [dict(r) for r in db.execute(text(q), params).mappings().all()]


def trend_by_day(db: Session, *, days: int = 7) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT (created_at AT TIME ZONE 'UTC')::date AS day, count(*) AS n
            FROM user_feedback_signal
            WHERE created_at > now() - make_interval(days => :d)
            GROUP BY 1 ORDER BY 1 DESC
            """
        ),
        {"d": int(days)},
    ).mappings().all()
    return [{"day": str(r["day"]), "count": int(r["n"])} for r in rows]


def build_report(db: Session, *, days: int | None = None) -> dict[str, Any]:
    rep = aggregate_feedback(load_signals(db, days=days))
    rep["window_days"] = days
    rep["trend_7d"] = trend_by_day(db, days=7)
    return rep
