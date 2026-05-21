"""Phase L catalyst substrate lookup — DB-side helper.

Resolves whether a paper trade's fill date is "proximate" to a real
catalyst event:

  * macro catalyst: any row in market_event_calendar with
    importance ∈ {high, medium} and event_date within
    PROXIMITY_TRADING_DAYS of fill_ts.
  * earnings catalyst: any row in earnings_event for the trade's
    asset_id with event_date within PROXIMITY_TRADING_DAYS of fill_ts.

Returns a CatalystSubstrate dataclass with two booleans. Consumed by
worker_integration to populate FeatureContext flags. The signal
extractor itself stays pure (no DB calls).

If either table is empty / absent, the respective flag is False —
honest absence. NEVER infer catalyst proximity from price action.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session


# Window for "proximate". Calendar days (not trading days) — simpler and
# the catalyst-anticipation skeleton has an INTRADAY thesis horizon so
# the window only needs to be small.
PROXIMITY_CALENDAR_DAYS = 3

# Importance levels considered material enough to drive skeleton selection.
_MATERIAL_IMPORTANCE = ("high", "medium")


@dataclass(frozen=True)
class CatalystSubstrate:
    proximate_macro: bool
    proximate_earnings: bool


def lookup_catalysts(
    session: Session,
    *,
    asset_id: str,
    as_of: dt.date,
) -> CatalystSubstrate:
    """Pure read. No mutations. Returns booleans only.

    If query raises (table missing, conn issue), returns
    CatalystSubstrate(False, False) — honest absence. The caller
    decides whether to log; here we never propagate.
    """
    proximate_macro = False
    proximate_earnings = False
    try:
        window_start = as_of - dt.timedelta(days=PROXIMITY_CALENDAR_DAYS)
        window_end = as_of + dt.timedelta(days=PROXIMITY_CALENDAR_DAYS)

        macro_row = session.execute(
            text(
                "SELECT 1 FROM market_event_calendar "
                "WHERE event_date BETWEEN :start AND :end "
                "  AND importance = ANY(:imp) "
                "LIMIT 1"
            ),
            {
                "start": window_start,
                "end": window_end,
                "imp": list(_MATERIAL_IMPORTANCE),
            },
        ).first()
        proximate_macro = macro_row is not None

        earn_row = session.execute(
            text(
                "SELECT 1 FROM earnings_event "
                "WHERE asset_id = :asset_id "
                "  AND event_date BETWEEN :start AND :end "
                "LIMIT 1"
            ),
            {
                "asset_id": asset_id,
                "start": window_start,
                "end": window_end,
            },
        ).first()
        proximate_earnings = earn_row is not None
    except Exception:
        # Honest absence on any error — never let catalyst lookup
        # damage the trade flow.
        return CatalystSubstrate(False, False)

    return CatalystSubstrate(
        proximate_macro=proximate_macro,
        proximate_earnings=proximate_earnings,
    )
