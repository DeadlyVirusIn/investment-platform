"""ET (America/New_York) earnings-feed adapter.

Used for US-equity earnings feeds that publish announcement timestamps
naive-in-ET (Zacks, Earnings Whispers, IR press-release scrapers).

Does NOT modify `event_date` or `event_time`. Only converts the
`announcement_timestamp` field when it is a naive datetime or a naive-ish
ISO-8601 string. Aware timestamps pass through unchanged.

Records flagged as already-aware (with tzinfo) are returned unchanged —
they already know their offset.
"""

from __future__ import annotations

import datetime as dt
from copy import deepcopy
from typing import Iterable
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def _normalize_one(rec: dict) -> dict:
    """Return a copy of rec with announcement_timestamp converted from
    naive-ET to aware-UTC when applicable. Preserves the original text in
    `announcement_timestamp_raw` (creates it if absent)."""
    out = deepcopy(rec)
    ts = out.get("announcement_timestamp")
    if ts is None:
        return out

    # Preserve original text
    if "announcement_timestamp_raw" not in out or not out["announcement_timestamp_raw"]:
        out["announcement_timestamp_raw"] = str(ts)

    if isinstance(ts, dt.datetime):
        if ts.tzinfo is None:
            aware = ts.replace(tzinfo=ET).astimezone(dt.timezone.utc)
            out["announcement_timestamp"] = aware
        # already aware → pass through
        return out

    if isinstance(ts, str):
        # Attempt to parse an ISO-8601 with/without tz
        s = ts.strip()
        # Normalize trailing Z
        s_parse = s.replace("Z", "+00:00")
        try:
            parsed = dt.datetime.fromisoformat(s_parse)
        except ValueError:
            # Leave unparseable strings to the core ingestion layer, which
            # will quarantine them with reason bad_announcement_timestamp.
            return out
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ET).astimezone(dt.timezone.utc)
        out["announcement_timestamp"] = parsed
    return out


def normalize_et_records(records: Iterable[dict]) -> list[dict]:
    """Batch form. Idempotent: re-applying to already-UTC records is a no-op."""
    return [_normalize_one(r) for r in records]
