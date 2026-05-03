"""Refresh rate limit + dedupe helpers.

Cooldown enforced by querying alpha_rule_suggestion.created_at.
Dedupe by rule_id within ALPHA_RULE_DEDUPE_DAYS.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import text
from sqlalchemy.orm import Session


def refresh_allowed(
    session: Session, *,
    cooldown_hours: int = 24,
    force: bool = False,
) -> tuple[bool, str]:
    if force:
        return True, "force_override"
    row = session.execute(text("""
        SELECT MAX(created_at) AS last
        FROM alpha_rule_suggestion
    """)).mappings().first()
    if row is None or row.get("last") is None:
        return True, "no_prior_refresh"
    last = row["last"]
    now = dt.datetime.now(dt.timezone.utc)
    hours = (now - last).total_seconds() / 3600.0
    if hours >= cooldown_hours:
        return True, f"cooldown_passed_{hours:.1f}h"
    return False, (
        f"cooldown_active: last refresh {hours:.1f}h ago "
        f"(< {cooldown_hours}h)"
    )


def dedupe_existing_rule_ids(
    session: Session, rule_ids: list[str],
    *,
    within_days: int = 7,
) -> set[str]:
    """Return subset of rule_ids that already have a pending / applied /
    ignored row in the recent window — these will be skipped."""
    if not rule_ids:
        return set()
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=within_days)
    rows = session.execute(text("""
        SELECT DISTINCT rule_id FROM alpha_rule_suggestion
         WHERE rule_id = ANY(:ids)
           AND created_at >= :since
    """), {"ids": list(rule_ids), "since": since}).mappings().all()
    return {str(r["rule_id"]) for r in rows}
