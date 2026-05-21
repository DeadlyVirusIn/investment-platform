"""Phase B7.4 — event proximity helper.

Pure module. Given an underlying + a DTE window, returns the
earliest in-window macro event row (read from market_event_calendar).
Generator uses this to:
  * record catalyst metadata on every emitted strategy_candidate
  * emit event-bias adjuncts (LONG_STRADDLE) when an event falls
    inside the DTE window
  * surface catalyst language in the explainability fields

Deterministic. Same (run_date, underlying, DTE) → same event.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class CatalystEvent:
    event_type: str
    event_date: dt.date
    title: str
    importance: str
    explanation: str
    days_away: int


def earliest_event_in_window(
    session: Session,
    *,
    underlying: str,
    run_date: dt.date,
    expiry: dt.date,
) -> CatalystEvent | None:
    """Return earliest in-window macro event affecting `underlying`,
    or None when no event exists between (run_date, expiry] for it.

    Window is (run_date, expiry] — strictly after run_date and on
    or before expiry. Excludes the run_date itself because a same-day
    event has already happened by the time the engine evaluates.
    """
    if expiry <= run_date:
        return None
    row = session.execute(text(
        """
        SELECT event_type, event_date, title, importance, explanation
        FROM market_event_calendar
        WHERE event_date > :run_date
          AND event_date <= :expiry
          AND :underlying = ANY(affected_symbols)
        ORDER BY event_date ASC, importance DESC, id ASC
        LIMIT 1
        """
    ), {
        "run_date":   run_date,
        "expiry":     expiry,
        "underlying": underlying,
    }).mappings().first()
    if row is None:
        return None
    return CatalystEvent(
        event_type=str(row["event_type"]),
        event_date=row["event_date"],
        title=str(row["title"]),
        importance=str(row["importance"]),
        explanation=str(row["explanation"]),
        days_away=(row["event_date"] - run_date).days,
    )
