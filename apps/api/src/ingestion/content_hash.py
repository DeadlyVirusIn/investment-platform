"""Content-hash utility for idempotent dedupe when external_id is NULL.

Deterministic SHA-1 hash over a stable, canonical serialization of the
semantic fields of a record. Excludes volatile fields (ingest timestamps,
auto-generated IDs). Reproducible across runs, platforms, and Python
processes.

Format of canonical string (pipe-delimited, all str(...), whitespace
normalized):

    source | symbol_lower | date1_iso | key2 | key3 | value_str | unit

Callers provide the exact tuple for their source type via helpers below.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any


def _stringify(v: Any) -> str:
    """Canonical str form. dt.date/dt.datetime → isoformat. None → ''."""
    if v is None:
        return ""
    if isinstance(v, dt.datetime):
        # ensure UTC isoformat if aware
        if v.tzinfo is not None:
            v = v.astimezone(dt.timezone.utc)
        return v.isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, float):
        # Normalized to stable string form; 6 decimals matches Numeric(20,6)
        return f"{v:.6f}"
    return str(v).strip()


def canonical_hash(parts: list[Any]) -> str:
    """SHA-1 of `|`-joined canonical parts. 40-char hex string."""
    canonical = "|".join(_stringify(p) for p in parts)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


def payload_content_hash(source: str, payload: dict) -> str:
    """Raw-table content hash: deterministic SHA-1 over the full ingested
    payload dict + source. Used for idempotent raw-level dedupe. Stable
    across runs because keys are sorted; values rendered with default=str."""
    import json
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha1(
        (source + "|" + canonical).encode("utf-8"),
    ).hexdigest()


# ---------------------------------------------------------------------------
# Per-source-type builders (keep semantic-field choice explicit + audited)
# ---------------------------------------------------------------------------


def earnings_content_hash(
    *, source: str, symbol: str, event_date: dt.date,
    event_time: str, fiscal_period: str | None,
    announcement_timestamp_utc: dt.datetime | None,
) -> str:
    """Semantic fields that identify an earnings record:
    source + symbol + event_date + event_time + (fiscal_period | '') +
    announcement_timestamp_utc.
    """
    return canonical_hash([
        source, (symbol or "").upper(), event_date, event_time,
        fiscal_period, announcement_timestamp_utc,
    ])


def shares_content_hash(
    *, source: str, symbol: str, effective_date: dt.date,
    filing_date: dt.date, shares_outstanding: int,
) -> str:
    return canonical_hash([
        source, (symbol or "").upper(), effective_date, filing_date,
        shares_outstanding,
    ])


def consensus_content_hash(
    *, source: str, symbol: str, event_date: dt.date,
    metric: str, estimate_type: str,
    as_of_date: dt.date, normalized_value: float, value_unit: str,
) -> str:
    """Semantic fields for a consensus/actual record. Uses the NORMALIZED
    value (canonical unit) so two feeds that agree semantically but disagree
    on presentation (millions vs raw) produce the SAME hash. Prevents
    false-distinct duplicates across sources that publish same number.
    """
    return canonical_hash([
        source, (symbol or "").upper(), event_date, metric, estimate_type,
        as_of_date, normalized_value, value_unit,
    ])
