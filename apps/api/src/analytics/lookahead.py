"""QW1.1 — pure lookahead-bias invariant (DB-free, timezone-safe).

A generator/replay step must never consume input data timestamped AFTER its
decision moment. This helper checks that invariant over a set of input
timestamps against a single decision timestamp. Pure + deterministic — no
DB, no strategy/query change. Detector only.

    res = max_input_ts_le_decision(decision_ts, input_timestamps)
    res["ok"]            -> bool (True = no lookahead)
    res["latest_input"]  -> the newest input (tz-aware UTC) or None
    res["decision_ts"]   -> the decision moment (tz-aware UTC)
    res["violation"]     -> None, or {latest_input, seconds_after}

`grace_seconds` tolerates benign skew (e.g. a quote stamped a few seconds
into the decision bar). Naive datetimes are assumed UTC.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Iterable


def _utc(ts: dt.datetime) -> dt.datetime:
    """Coerce to tz-aware UTC; naive is assumed UTC."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=dt.timezone.utc)
    return ts.astimezone(dt.timezone.utc)


def max_input_ts_le_decision(
    decision_ts: dt.datetime,
    input_timestamps: Iterable[dt.datetime | None],
    *,
    grace_seconds: float = 0.0,
) -> dict[str, Any]:
    """True iff no input timestamp exceeds decision_ts (+ grace).

    Empty/all-None inputs -> ok=True, latest_input=None (nothing to leak).
    """
    dts = _utc(decision_ts)
    cleaned = [_utc(t) for t in input_timestamps if t is not None]

    if not cleaned:
        return {
            "ok": True,
            "latest_input": None,
            "decision_ts": dts,
            "violation": None,
        }

    latest = max(cleaned)
    limit = dts + dt.timedelta(seconds=grace_seconds)
    ok = latest <= limit
    violation = None
    if not ok:
        violation = {
            "latest_input": latest,
            "seconds_after": (latest - dts).total_seconds(),
        }
    return {
        "ok": ok,
        "latest_input": latest,
        "decision_ts": dts,
        "violation": violation,
    }


__all__ = ["max_input_ts_le_decision"]
