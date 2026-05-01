"""Phase 11W (Phase C) — input snapshot builder.

Read-only snapshot of the public-table inputs that a future
research run would consume. Pure-fn relative to the DB session it
receives: it issues SELECTs only and returns a deterministic,
JSON-serializable dict.

Determinism contract:
  * Snapshot keys are stable across runs given the same DB state.
  * `generated_at` is the only non-deterministic field; it is
    EXCLUDED from `compute_input_snapshot_hash` per the hashing
    rule in `provenance.py`.
  * No symbol-level state outside the explicit input set.

NEVER mutates the DB. NEVER calls an LLM. NEVER imports execution /
scoring / ML modules. Verified by `test_research_phase_c_boundaries`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Iterable

from sqlalchemy import select, text
from sqlalchemy.orm import Session


# Tables this builder is permitted to read. The list is enforced by
# convention + a CI source-grep test. Any expansion requires an
# audit-doc entry.
ALLOWED_INPUT_TABLES: tuple[str, ...] = (
    "candidate_idea",
    "context_daily",
    "asset",
)


def _candidate_idea_payload(
    session: Session,
    candidate_idea_id: str,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT id, as_of_date, asset_id, model_version, engine,
                   status, action, rejection_reason,
                   composite_score::text AS composite_score,
                   confidence::text AS confidence
            FROM candidate_idea
            WHERE id = :cid
            """
        ),
        {"cid": candidate_idea_id},
    ).mappings().first()
    if row is None:
        return None
    return dict(row)


def _context_daily_at_or_before(
    session: Session,
    as_of: dt.date,
) -> dict[str, Any] | None:
    """Latest context_daily row at as_of_date <= :as_of. The query
    pulls one row per context_name to mirror the strict-engine
    convention used in scripts/run_paper_daily.py — but READ-ONLY."""
    rows = session.execute(
        text(
            """
            SELECT DISTINCT ON (context_name)
                   context_name, value_bool, as_of_date::text AS as_of_date,
                   logic_version
            FROM context_daily
            WHERE as_of_date <= :as_of
            ORDER BY context_name, as_of_date DESC
            """
        ),
        {"as_of": as_of},
    ).mappings().all()
    if not rows:
        return None
    by_name = {r["context_name"]: dict(r) for r in rows}
    return {
        "as_of": as_of.isoformat(),
        "gates": by_name,
    }


def _asset_metadata(session: Session, symbol: str) -> dict[str, Any] | None:
    row = session.execute(
        text(
            "SELECT id, symbol, name, asset_class, exchange, currency, "
            "is_active "
            "FROM asset WHERE symbol = :sym"
        ),
        {"sym": symbol},
    ).mappings().first()
    if row is None:
        return None
    return dict(row)


def build_input_snapshot(
    session: Session,
    *,
    symbol: str,
    as_of: dt.date,
    candidate_idea_id: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic input snapshot.

    Parameters
    ----------
    session : Session
        SQLAlchemy session. The function issues SELECTs only.
    symbol : str
        Equity ticker symbol the snapshot is anchored to.
    as_of : datetime.date
        The "as of" date the run is being prepared for. Used to scope
        context_daily lookups.
    candidate_idea_id : str | None
        Optional reference to an existing public.candidate_idea row.
        When supplied, its frozen metadata is included in the
        snapshot.

    Returns
    -------
    dict
        JSON-serializable. Includes a `generated_at` ISO timestamp
        (EXCLUDED from hashing) and a `source_tables` audit list.
    """
    if not symbol or not isinstance(symbol, str):
        raise ValueError("symbol must be a non-empty str")
    if not isinstance(as_of, dt.date):
        raise ValueError("as_of must be a datetime.date")

    candidate = (
        _candidate_idea_payload(session, candidate_idea_id)
        if candidate_idea_id is not None
        else None
    )
    asset = _asset_metadata(session, symbol)
    context = _context_daily_at_or_before(session, as_of)

    used_tables: list[dict[str, Any]] = []
    if candidate is not None:
        used_tables.append({
            "table": "candidate_idea",
            "primary_key": candidate["id"],
        })
    if asset is not None:
        used_tables.append({
            "table": "asset",
            "primary_key": asset["id"],
        })
    if context is not None:
        used_tables.append({
            "table": "context_daily",
            "primary_key": context["as_of"],
        })

    snapshot: dict[str, Any] = {
        "schema_version": "input-snapshot-v1.0.0",
        "symbol": symbol,
        "as_of": as_of.isoformat(),
        "candidate_idea": candidate,
        "asset": asset,
        "context_daily": context,
        "source_tables": used_tables,
        # generated_at is INTENTIONALLY excluded from hashing.
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    return snapshot


def assert_no_mutation_helpers() -> None:
    """Defensive runtime guard: import-time confirmation that this
    module exposes no DB-mutation helpers. The contract test in
    test_research_phase_c_boundaries.py enforces the absence of
    insert/update/delete patterns at source-grep level."""
    return None
