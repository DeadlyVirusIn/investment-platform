"""Raw-data ingestion helpers.

Provides:
  * content-hash generation (SHA-1 over canonical payload)
  * PIT-safe observation retrieval
  * published_at / as_of_date discipline

Every raw-layer ingest MUST use these helpers; no module bypasses them.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def canonical_hash(*parts: Any) -> str:
    """Stable SHA-1 hash of canonical JSON-serialized parts."""
    serialized = json.dumps(parts, sort_keys=True, default=str,
                            separators=(",", ":"))
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()


def observation_hash(
    source: str, series_id: str, as_of_date: dt.date, value: Any,
) -> str:
    return canonical_hash(source, series_id, str(as_of_date), value)


@dataclass(frozen=True)
class PITWindow:
    """Point-in-time window for feature computation at a decision cutoff."""
    decision_cutoff: dt.datetime

    def is_available(self, published_at: dt.datetime | None,
                     as_of_date: dt.date | None) -> bool:
        """True if observation is safe to use (no lookahead)."""
        if published_at is not None:
            return published_at <= self.decision_cutoff
        if as_of_date is not None:
            # Fallback: assume end-of-day of observation_date
            return dt.datetime.combine(
                as_of_date, dt.time(23, 59, 59),
                tzinfo=dt.timezone.utc,
            ) <= self.decision_cutoff
        return False


def get_latest_available_observation(
    session: Session, table: str, series_id: str,
    cutoff: PITWindow, *,
    source_filter: str | None = None,
) -> dict | None:
    """Return latest observation for series_id that is PIT-safe at cutoff."""
    sql = f"""
      SELECT observation_date, value, source, published_at, as_of_date
      FROM {table}
      WHERE series_id = :sid
        AND ( (published_at IS NOT NULL AND published_at <= :cut)
           OR (published_at IS NULL AND as_of_date <= :cut_date) )
        {"AND source = :src" if source_filter else ""}
      ORDER BY observation_date DESC
      LIMIT 1
    """
    params: dict[str, Any] = {
        "sid": series_id,
        "cut": cutoff.decision_cutoff,
        "cut_date": cutoff.decision_cutoff.date(),
    }
    if source_filter:
        params["src"] = source_filter
    row = session.execute(text(sql), params).fetchone()
    if row is None:
        return None
    return {
        "observation_date": row[0], "value": float(row[1]),
        "source": row[2], "published_at": row[3], "as_of_date": row[4],
    }


def enforce_pit_window(
    observations: list[dict], cutoff: PITWindow,
) -> list[dict]:
    """Filter list of observation dicts to PIT-safe rows only."""
    out = []
    for o in observations:
        if cutoff.is_available(
            o.get("published_at"), o.get("as_of_date"),
        ):
            out.append(o)
    return out


class PITViolation(Exception):
    """Raised when a feature computation attempts to use future data."""


def require_pit_safe(
    observation: dict | None, feature_name: str, cutoff: PITWindow,
) -> dict:
    if observation is None:
        raise PITViolation(f"{feature_name}: no PIT-safe observation at cutoff {cutoff.decision_cutoff}")
    if not cutoff.is_available(
        observation.get("published_at"), observation.get("as_of_date"),
    ):
        raise PITViolation(
            f"{feature_name}: observation not PIT-safe "
            f"(published_at={observation.get('published_at')}, "
            f"as_of_date={observation.get('as_of_date')}, cutoff={cutoff.decision_cutoff})"
        )
    return observation
