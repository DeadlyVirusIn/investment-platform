"""Replay/recovery provenance helpers (Phase 11Z migration 061).

Read-only utilities. Never inserts into manifest — only the replay
script does that. Callers that need to filter live data from
replay-generated data should use `ProvenanceFilter` or the SQL
fragment from `replay_exclusion_clause`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session


REPLAY_SOURCES = frozenset({"replay", "test"})


@dataclass(frozen=True)
class ProvenanceFilter:
    """Decision object returned by API helpers.

    `include_replay=True` means the caller explicitly opted in
    (e.g. an audit dashboard) — replay rows are kept.
    `include_replay=False` (default) means strip replay rows."""
    include_replay: bool = False

    def __bool__(self) -> bool:
        return not self.include_replay  # truthy = "exclude replay"


def is_replay_entity(
    session: Session, *, entity_type: str, entity_id: str,
) -> bool:
    """One-row lookup. Returns True if the manifest tags this row
    with source IN ('replay','test'). Returns False for live/dev."""
    try:
        row = session.execute(
            text("""
                SELECT source FROM replay_recovery_manifest
                WHERE entity_type = :et AND entity_id = :eid
                LIMIT 1
            """),
            {"et": entity_type, "eid": str(entity_id)},
        ).first()
    except Exception:
        # Migration not applied yet → treat as live.
        return False
    if not row:
        return False
    return row[0] in REPLAY_SOURCES


def list_replay_ids(
    session: Session, *, entity_type: str,
) -> set[str]:
    """All entity_ids of `entity_type` tagged as replay/test."""
    try:
        rows = session.execute(
            text("""
                SELECT entity_id FROM replay_recovery_manifest
                WHERE entity_type = :et AND source = ANY(:srcs)
            """),
            {"et": entity_type, "srcs": list(REPLAY_SOURCES)},
        ).all()
    except Exception:
        return set()
    return {r[0] for r in rows}


def replay_exclusion_clause(
    *, entity_type: str, alias: str,
) -> str:
    """Returns a SQL fragment to NOT-EXISTS-exclude replay rows.

    Usage:
        sql = (
            f"SELECT * FROM paper_trade pt "
            f"WHERE 1=1 AND {replay_exclusion_clause("
            f"  entity_type='paper_trade', alias='pt')}"
        )

    The fragment is parameterised on `entity_type` (literal — caller
    must pass a known constant from the manifest's CHECK list).
    Never accept user input here."""
    safe_types = {
        "account", "paper_portfolio", "paper_trade", "paper_position",
        "recommendation", "recommendation_evidence",
        "paper_equity_snapshot",
    }
    if entity_type not in safe_types:
        raise ValueError(
            f"entity_type {entity_type!r} not in allowed manifest types"
        )
    # alias is a SQL identifier — restrict to alphanumeric + underscore.
    if not (alias and all(c.isalnum() or c == "_" for c in alias)):
        raise ValueError(f"alias {alias!r} must be alphanumeric/underscore")
    return (
        f"NOT EXISTS (SELECT 1 FROM replay_recovery_manifest m "
        f"WHERE m.entity_type = '{entity_type}' "
        f"AND m.entity_id = {alias}.id::text "
        f"AND m.source IN ('replay','test'))"
    )


def filter_iterable(
    rows: Iterable, *, replay_ids: set[str], id_attr: str = "id",
):
    """Generic in-Python filter for ORM/dataclass results.

    Faster than per-row DB lookups when you already have the ID set
    from `list_replay_ids`."""
    for r in rows:
        rid = getattr(r, id_attr, None)
        if rid is None or str(rid) not in replay_ids:
            yield r
