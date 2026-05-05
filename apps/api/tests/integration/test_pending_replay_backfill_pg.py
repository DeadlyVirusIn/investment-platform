"""Backfill mode tests for pending replay.

Verifies:
  * `from_date` lower bound excludes earlier dates.
  * `force=True` re-processes already-marked dates.
  * `force=True` without `from_date` is allowed at the API level
    but the orchestrator CLI requires both — orchestrator-level
    test in test_post_ingest_cycle_pg covers the CLI guard.
  * Backfill never touches `replay_recovery_manifest`.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.domain.paper_trading.pending_replay import (
    REPLAYED_SUFFIX, collect_pending_dates, replay_all_pending,
)


pytestmark = pytest.mark.integration


def _write_pending(skips_dir: Path, d: dt.date) -> None:
    skips_dir.mkdir(parents=True, exist_ok=True)
    path = skips_dir / f"{d.isoformat()}.jsonl"
    path.write_text(json.dumps({
        "as_of_date": d.isoformat(),
        "portfolio_id": "p-1",
        "asset_id": "a-1",
        "reason": "execution_failure",
        "detail": {
            "exec_reason":
                "no price bar available after submitted_at; cannot fill",
        },
    }) + "\n")


def _mark(skips_dir: Path, d: dt.date) -> None:
    skips_dir.mkdir(parents=True, exist_ok=True)
    (skips_dir / f"{d.isoformat()}{REPLAYED_SUFFIX}").write_text("{}\n")


def test_from_date_excludes_earlier(tmp_path):
    skips = tmp_path / "skips"
    _write_pending(skips, dt.date(2026, 4, 15))   # before from
    _write_pending(skips, dt.date(2026, 4, 20))   # at from
    _write_pending(skips, dt.date(2026, 4, 25))   # in range
    _write_pending(skips, dt.date(2026, 5, 4))    # in range
    _write_pending(skips, dt.date(2026, 5, 5))    # at before — excluded

    result = collect_pending_dates(
        before=dt.date(2026, 5, 5),
        from_date=dt.date(2026, 4, 20),
        skips_dir=skips,
    )
    assert result == [
        dt.date(2026, 4, 20),
        dt.date(2026, 4, 25),
        dt.date(2026, 5, 4),
    ]


def test_force_includes_marked_dates(tmp_path):
    skips = tmp_path / "skips"
    _write_pending(skips, dt.date(2026, 4, 25))
    _mark(skips, dt.date(2026, 4, 25))
    _write_pending(skips, dt.date(2026, 5, 1))

    # Without force: only unmarked
    assert collect_pending_dates(
        before=dt.date(2026, 5, 5), skips_dir=skips,
    ) == [dt.date(2026, 5, 1)]

    # With force: include marked
    assert collect_pending_dates(
        before=dt.date(2026, 5, 5), skips_dir=skips, force=True,
    ) == [dt.date(2026, 4, 25), dt.date(2026, 5, 1)]


def test_replay_all_pending_with_from_and_force(
    tmp_path, pg_engine,
):
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )
    skips = tmp_path / "skips"
    _write_pending(skips, dt.date(2026, 4, 15))   # before from
    _write_pending(skips, dt.date(2026, 4, 25))
    _mark(skips, dt.date(2026, 4, 25))             # marker; force should override
    _write_pending(skips, dt.date(2026, 5, 1))

    result = replay_all_pending(
        before=dt.date(2026, 5, 5),
        from_date=dt.date(2026, 4, 20),
        force=True,
        SessionFactory=SessionCls, skips_dir=skips,
    )
    assert result["dates_replayed"] == [
        "2026-04-25", "2026-05-01",
    ]
    assert result["from_date"] == "2026-04-20"
    assert result["force"] is True


def test_no_writes_to_replay_recovery_manifest(
    tmp_path, pg_session, pg_engine,
):
    """Critical safety: replay must NOT touch the audit manifest.

    The manifest table is created by a raw-SQL alembic migration
    (061), so testcontainer's `Base.metadata.create_all` does not
    build it. Bootstrap it here so the assertion is exercised in
    the same shape production sees."""
    from sqlalchemy import text
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )
    with pg_engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS replay_recovery_manifest ("
            "  id SERIAL PRIMARY KEY,"
            "  replay_run_id TEXT, source TEXT,"
            "  entity_type TEXT, entity_id TEXT"
            ")"
        ))
    skips = tmp_path / "skips"
    _write_pending(skips, dt.date(2026, 4, 25))

    n_before = pg_session.execute(text(
        "SELECT count(*) FROM replay_recovery_manifest"
    )).scalar() or 0
    replay_all_pending(
        before=dt.date(2026, 5, 5),
        from_date=dt.date(2026, 4, 20),
        SessionFactory=SessionCls, skips_dir=skips,
    )
    n_after = pg_session.execute(text(
        "SELECT count(*) FROM replay_recovery_manifest"
    )).scalar() or 0
    assert n_after == n_before
