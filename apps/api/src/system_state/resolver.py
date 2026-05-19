"""Phase L state-label resolver — trading-day-aware classifier.

Computes the current StateLabelSubstate per surface based on:
  * Latest live engine decision timestamp (paper_trade fill)
  * Trading-day awareness (weekend tolerance; holidays approx)
  * Surface kind (LIVE_* vs LEARNING vs EXPERIMENTAL)

Phase L commitment (L.4-F §V item 8): substate definitions explicit,
not heuristic.

This is the groundwork. The API endpoint
GET /v2/system-state?surface=<surface> lands in a subsequent task.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.system_state.substates import (
    StateLabelSubstate, SUBSTATE_LABELS,
)


SURFACE_LIVE = "live"
SURFACE_LEARNING = "learning"
SURFACE_EXPERIMENTAL = "experimental"

FRESH_TRADING_HOURS = 24
STALE_TRADING_HOURS = 72


@dataclass(frozen=True)
class ResolvedState:
    surface: str
    substate: StateLabelSubstate
    label: str
    latest_live_decision_ts: Optional[dt.datetime]
    trading_hours_since_decision: Optional[float]


def _is_weekend(d: dt.date) -> bool:
    return d.weekday() >= 5


def _trading_hours_between(
    earlier: dt.datetime, later: dt.datetime,
) -> float:
    """Approx count of trading hours between two timestamps.

    Heuristic: counts hours during weekdays only (Mon-Fri). Holidays
    not handled in MVP — over-counts trading hours by a few per month.
    Acceptable approximation for 24h/72h substate thresholds.
    """
    if later <= earlier:
        return 0.0
    cur = earlier
    total = 0.0
    while cur < later:
        if not _is_weekend(cur.date()):
            next_boundary = min(later, cur + dt.timedelta(hours=1))
            total += (next_boundary - cur).total_seconds() / 3600.0
            cur = next_boundary
        else:
            days_to_mon = (7 - cur.weekday()) % 7 or 1
            cur = dt.datetime.combine(
                cur.date() + dt.timedelta(days=days_to_mon),
                dt.time(0, 0, tzinfo=dt.timezone.utc),
            )
    return total


def _latest_live_decision(session: Session) -> Optional[dt.datetime]:
    """Latest live paper_trade fill across all portfolios.

    We anchor on trades (decisions), not equity snapshots. Snapshots
    run nightly even on quiet days; trades happen only when the engine
    decided to act.
    """
    row = session.execute(
        text(
            "SELECT MAX(fill_ts) FROM paper_trade "
            "WHERE fill_ts IS NOT NULL"
        )
    ).scalar()
    return row


def resolve_state(session: Session, surface: str) -> ResolvedState:
    """Compute current StateLabelSubstate for a given surface."""
    surface_kind = (
        SURFACE_LEARNING if surface in {"concepts", "playbooks"}
        else SURFACE_EXPERIMENTAL if surface in {"options_preview", "research_previews"}
        else SURFACE_LIVE
    )

    if surface_kind == SURFACE_LEARNING:
        sub = StateLabelSubstate.LEARNING
        return ResolvedState(
            surface=surface, substate=sub,
            label=SUBSTATE_LABELS[sub],
            latest_live_decision_ts=None,
            trading_hours_since_decision=None,
        )

    if surface_kind == SURFACE_EXPERIMENTAL:
        sub = StateLabelSubstate.EXPERIMENTAL
        return ResolvedState(
            surface=surface, substate=sub,
            label=SUBSTATE_LABELS[sub],
            latest_live_decision_ts=None,
            trading_hours_since_decision=None,
        )

    latest = _latest_live_decision(session)
    now = dt.datetime.now(dt.timezone.utc)

    if latest is None:
        sub = StateLabelSubstate.LIVE_DORMANT
        return ResolvedState(
            surface=surface, substate=sub,
            label=SUBSTATE_LABELS[sub],
            latest_live_decision_ts=None,
            trading_hours_since_decision=None,
        )

    # Normalize naive ts from DB to UTC-aware.
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=dt.timezone.utc)

    hrs = _trading_hours_between(latest, now)

    if hrs < FRESH_TRADING_HOURS:
        sub = StateLabelSubstate.LIVE_FRESH
    elif hrs < STALE_TRADING_HOURS:
        sub = StateLabelSubstate.LIVE_STALE
    else:
        if _is_weekend(now.date()):
            sub = StateLabelSubstate.LIVE_DORMANT
        else:
            sub = StateLabelSubstate.OBSERVING

    return ResolvedState(
        surface=surface, substate=sub,
        label=SUBSTATE_LABELS[sub],
        latest_live_decision_ts=latest,
        trading_hours_since_decision=hrs,
    )
