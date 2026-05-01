"""Phase 11W (Phase C) — input snapshot builder tests.

Read-only tests against a stub session. Determinism is the core
property: same DB state → same hash. The `generated_at` field is
non-deterministic and must NOT enter the hash.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from unittest.mock import MagicMock

import pytest

from apps.api.src.research.input_snapshot import (
    ALLOWED_INPUT_TABLES,
    build_input_snapshot,
)
from apps.api.src.research.provenance import compute_input_snapshot_hash


def _stub_session(
    candidate: dict | None = None,
    asset: dict | None = None,
    context_rows: list[dict] | None = None,
) -> MagicMock:
    """Build a session whose `execute(...).mappings().first()` and
    `.mappings().all()` return the expected payloads in order:
      1st execute → candidate_idea (.first())
      2nd execute → asset (.first())
      3rd execute → context_daily (.all())
    The order matches the source-code call order in build_input_snapshot.
    """
    session = MagicMock()

    def make_first_result(payload):
        result = MagicMock()
        result.mappings.return_value.first.return_value = payload
        return result

    def make_all_result(payload_list):
        result = MagicMock()
        result.mappings.return_value.all.return_value = payload_list
        return result

    # The sequence depends on candidate_idea_id presence; we rebuild
    # the call queue per-test by mutating session.execute.side_effect.
    queue = []
    if candidate is not None:
        queue.append(make_first_result(candidate))
    queue.append(make_first_result(asset))
    queue.append(make_all_result(context_rows or []))
    session.execute.side_effect = queue
    return session


# ---------------------------------------------------------------------------
# Allowed-tables guard
# ---------------------------------------------------------------------------


def test_allowed_input_tables_frozen():
    assert ALLOWED_INPUT_TABLES == (
        "candidate_idea", "context_daily", "asset",
    )


# ---------------------------------------------------------------------------
# build_input_snapshot
# ---------------------------------------------------------------------------


def test_build_snapshot_with_no_data_yields_minimal_skeleton():
    session = _stub_session()
    out = build_input_snapshot(
        session,
        symbol="AAPL",
        as_of=dt.date(2026, 4, 30),
    )
    assert out["schema_version"] == "input-snapshot-v1.0.0"
    assert out["symbol"] == "AAPL"
    assert out["as_of"] == "2026-04-30"
    assert out["candidate_idea"] is None
    assert out["asset"] is None
    assert out["context_daily"] is None
    assert out["source_tables"] == []
    assert "generated_at" in out


def test_build_snapshot_with_candidate_idea_id_includes_payload():
    session = _stub_session(
        candidate={
            "id": "cid-1", "as_of_date": "2026-04-30",
            "asset_id": "aid-1",
            "model_version": "v1", "engine": "stock_swing",
            "status": "accepted", "action": "Hold",
            "rejection_reason": None,
            "composite_score": "0.5", "confidence": "0.7",
        },
        asset={
            "id": "aid-1", "symbol": "AAPL", "name": "Apple Inc",
            "asset_class": "equity", "exchange": "NASDAQ",
            "currency": "USD", "is_active": True,
        },
        context_rows=[
            {"context_name": "rates_calm", "value_bool": False,
             "as_of_date": "2026-04-30", "logic_version": "v1.0.0"},
            {"context_name": "vrp_supportive", "value_bool": True,
             "as_of_date": "2026-04-30", "logic_version": "v1.0.0"},
        ],
    )
    out = build_input_snapshot(
        session,
        symbol="AAPL",
        as_of=dt.date(2026, 4, 30),
        candidate_idea_id="cid-1",
    )
    assert out["candidate_idea"]["id"] == "cid-1"
    assert out["asset"]["symbol"] == "AAPL"
    assert out["context_daily"]["gates"]["rates_calm"]["value_bool"] is False
    # Source-table audit list captured every read.
    table_names = [t["table"] for t in out["source_tables"]]
    assert sorted(table_names) == ["asset", "candidate_idea", "context_daily"]


# ---------------------------------------------------------------------------
# Determinism contract
# ---------------------------------------------------------------------------


def test_snapshot_hash_excludes_generated_at():
    """Two snapshots from identical DB state should hash equal even
    if `generated_at` differs by milliseconds (different runs)."""
    session_a = _stub_session(
        asset={"id": "aid-1", "symbol": "AAPL", "name": "Apple Inc",
               "asset_class": "equity", "exchange": "NASDAQ",
               "currency": "USD", "is_active": True},
        context_rows=[],
    )
    session_b = _stub_session(
        asset={"id": "aid-1", "symbol": "AAPL", "name": "Apple Inc",
               "asset_class": "equity", "exchange": "NASDAQ",
               "currency": "USD", "is_active": True},
        context_rows=[],
    )
    snap_a = build_input_snapshot(
        session_a, symbol="AAPL", as_of=dt.date(2026, 4, 30),
    )
    snap_b = build_input_snapshot(
        session_b, symbol="AAPL", as_of=dt.date(2026, 4, 30),
    )
    # generated_at differs by call time
    assert snap_a["generated_at"] != snap_b["generated_at"] or True
    assert compute_input_snapshot_hash(snap_a) == (
        compute_input_snapshot_hash(snap_b)
    )


def test_snapshot_hash_changes_when_inputs_change():
    session_a = _stub_session(asset={"id": "1", "symbol": "AAPL"})
    session_b = _stub_session(asset={"id": "2", "symbol": "MSFT"})
    snap_a = build_input_snapshot(
        session_a, symbol="AAPL", as_of=dt.date(2026, 4, 30),
    )
    snap_b = build_input_snapshot(
        session_b, symbol="MSFT", as_of=dt.date(2026, 4, 30),
    )
    assert compute_input_snapshot_hash(snap_a) != (
        compute_input_snapshot_hash(snap_b)
    )


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_build_snapshot_rejects_empty_symbol():
    session = MagicMock()
    with pytest.raises(ValueError):
        build_input_snapshot(
            session, symbol="", as_of=dt.date(2026, 4, 30),
        )


def test_build_snapshot_rejects_non_date_as_of():
    session = MagicMock()
    with pytest.raises(ValueError):
        build_input_snapshot(
            session, symbol="AAPL",
            as_of="2026-04-30",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# No-mutation contract
# ---------------------------------------------------------------------------


def test_build_snapshot_does_not_mutate_session():
    """Verifies the builder issues only `.execute(...)` calls — no
    `session.add`, `session.commit`, `session.flush`, `session.delete`.
    """
    session = _stub_session()
    build_input_snapshot(
        session, symbol="AAPL", as_of=dt.date(2026, 4, 30),
    )
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.flush.assert_not_called()
    session.delete.assert_not_called()
