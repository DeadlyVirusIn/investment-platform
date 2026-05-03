"""Shared ingestion primitives — result container + quarantine helper."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from apps.api.src.db.models import EventQuarantine


@dataclass
class IngestionResult:
    """Deterministic summary of a single ingestion run."""
    source_type: str
    total_in: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    quarantined: int = 0
    quarantine_reasons: Counter = field(default_factory=Counter)
    raw_inserted: int = 0

    def as_dict(self) -> dict:
        return {
            "source_type": self.source_type,
            "total_in": self.total_in,
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "quarantined": self.quarantined,
            "quarantine_reasons": dict(self.quarantine_reasons),
            "raw_inserted": self.raw_inserted,
        }


def quarantine_row(
    session: Session,
    *,
    source_type: str,
    source: str,
    reason: str,
    reason_detail: str | None = None,
    raw_ingestion_id: str | None = None,
    payload: dict | None = None,
) -> EventQuarantine:
    """Insert a quarantine row. Never raises on payload encoding (best-effort
    JSON serialization; falls back to string repr)."""
    try:
        # Round-trip to confirm JSON-compatible
        json.dumps(payload, default=str)
        safe_payload = payload
    except (TypeError, ValueError):
        safe_payload = {"raw_repr": repr(payload)}
    row = EventQuarantine(
        source_type=source_type, source=source,
        raw_ingestion_id=raw_ingestion_id,
        reason=reason, reason_detail=reason_detail,
        payload=safe_payload,
    )
    session.add(row)
    session.flush()
    return row
