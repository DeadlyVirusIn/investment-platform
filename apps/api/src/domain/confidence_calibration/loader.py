"""Load latest calibration data from model_scorecard. Read-only.

Policy: pick the most recent 30-day scorecard row + the most recent 7-day
scorecard row for the given model_name. Missing rows → None → identity.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import ModelScorecard


def _latest_with_window(
    session: Session, model_name: str, window_days: int,
) -> ModelScorecard | None:
    target_span = dt.timedelta(days=window_days)
    # Tolerance of ±2 days to handle weekends / partial runs
    tol = dt.timedelta(days=2)
    stmt = (
        select(ModelScorecard)
        .where(ModelScorecard.model_name == model_name)
        .order_by(ModelScorecard.window_end.desc())
        .limit(50)
    )
    for row in session.scalars(stmt):
        span = row.window_end - row.window_start
        if abs(span - target_span) <= tol:
            return row
    return None


def load_calibration_inputs(
    session: Session, model_name: str,
) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]] | None]:
    """Return (calibration_30d, calibration_7d) ready for derive_factors()."""
    row30 = _latest_with_window(session, model_name, 30)
    row7 = _latest_with_window(session, model_name, 7)
    cal30 = row30.calibration if row30 else None
    cal7 = row7.calibration if row7 else None
    return cal30, cal7
