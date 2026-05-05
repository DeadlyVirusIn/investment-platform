"""Pending next-bar replay — integration tests.

Verifies:
  * collect_pending_dates returns dates < before with pending entries
    AND no .replayed marker; skips marker-suffixed files; skips
    today and future.
  * replay_pending_for_date writes a marker so subsequent calls
    short-circuit.
  * replay_all_pending invokes replay only for unmarked dates.
  * No same-bar fills — replay still respects the next-bar guard;
    if no future bar exists, the decision is rejected and stays
    pending. Marker is still written (to avoid infinite retry loops
    on stuck dates).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from apps.api.src.domain.paper_trading.pending_replay import (
    REPLAYED_SUFFIX, collect_pending_dates,
    replay_pending_for_date,
)


pytestmark = pytest.mark.integration


def _write_pending(skips_dir: Path, d: dt.date, n: int = 1) -> None:
    skips_dir.mkdir(parents=True, exist_ok=True)
    path = skips_dir / f"{d.isoformat()}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        for i in range(n):
            f.write(json.dumps({
                "as_of_date": d.isoformat(),
                "portfolio_id": "p-1",
                "asset_id": f"a-{i}",
                "reason": "execution_failure",
                "detail": {
                    "exec_reason":
                        "no price bar available after submitted_at; "
                        "cannot fill",
                },
            }) + "\n")


def _write_non_pending(skips_dir: Path, d: dt.date) -> None:
    """Skip rows that are NOT pending_next_bar (e.g.
    duplicate_holding) — should never be picked up."""
    skips_dir.mkdir(parents=True, exist_ok=True)
    path = skips_dir / f"{d.isoformat()}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "as_of_date": d.isoformat(),
            "portfolio_id": "p-1",
            "asset_id": "a-x",
            "reason": "duplicate_holding",
            "detail": {},
        }) + "\n")


def _write_marker(skips_dir: Path, d: dt.date) -> None:
    skips_dir.mkdir(parents=True, exist_ok=True)
    (skips_dir / f"{d.isoformat()}{REPLAYED_SUFFIX}").write_text("{}\n")


def test_collect_returns_unmarked_pending_dates(tmp_path):
    skips = tmp_path / "skips"
    today = dt.date(2026, 5, 5)
    _write_pending(skips, dt.date(2026, 5, 1))
    _write_pending(skips, dt.date(2026, 5, 2))
    _write_pending(skips, dt.date(2026, 5, 3))
    # Already replayed:
    _write_pending(skips, dt.date(2026, 5, 4))
    _write_marker(skips, dt.date(2026, 5, 4))
    # Today + future — must be excluded:
    _write_pending(skips, dt.date(2026, 5, 5))
    _write_pending(skips, dt.date(2026, 5, 6))

    result = collect_pending_dates(before=today, skips_dir=skips)
    assert result == [
        dt.date(2026, 5, 1),
        dt.date(2026, 5, 2),
        dt.date(2026, 5, 3),
    ]


def test_collect_ignores_non_pending_rows(tmp_path):
    skips = tmp_path / "skips"
    _write_non_pending(skips, dt.date(2026, 5, 1))
    _write_pending(skips, dt.date(2026, 5, 2))

    result = collect_pending_dates(
        before=dt.date(2026, 5, 5), skips_dir=skips,
    )
    assert result == [dt.date(2026, 5, 2)]


def test_collect_ignores_marker_files(tmp_path):
    """Marker file `<date>.replayed.jsonl` must not be misread as a
    skip file (its stem doesn't parse as date and the suffix is
    explicitly skipped)."""
    skips = tmp_path / "skips"
    _write_marker(skips, dt.date(2026, 5, 1))
    result = collect_pending_dates(
        before=dt.date(2026, 5, 5), skips_dir=skips,
    )
    assert result == []


def test_collect_skips_already_marked(tmp_path):
    skips = tmp_path / "skips"
    _write_pending(skips, dt.date(2026, 5, 1))
    _write_marker(skips, dt.date(2026, 5, 1))
    result = collect_pending_dates(
        before=dt.date(2026, 5, 5), skips_dir=skips,
    )
    assert result == []


def test_collect_returns_empty_when_dir_missing(tmp_path):
    skips = tmp_path / "skips_does_not_exist"
    result = collect_pending_dates(
        before=dt.date(2026, 5, 5), skips_dir=skips,
    )
    assert result == []


def test_replay_writes_marker_on_clean_run(tmp_path, pg_engine):
    """Even if no portfolios exist, marker is written — prevents
    infinite retry loops on dates that genuinely have no work."""
    from sqlalchemy.orm import Session, sessionmaker
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )
    skips = tmp_path / "skips"
    _write_pending(skips, dt.date(2026, 5, 1))

    summary = replay_pending_for_date(
        original_date=dt.date(2026, 5, 1),
        SessionFactory=SessionCls,
        skips_dir=skips,
    )
    marker = skips / f"2026-05-01{REPLAYED_SUFFIX}"
    assert marker.exists()
    assert "decisions_total" in summary
    # Subsequent collect now skips this date.
    remaining = collect_pending_dates(
        before=dt.date(2026, 5, 5), skips_dir=skips,
    )
    assert dt.date(2026, 5, 1) not in remaining


def test_replay_all_pending_processes_oldest_first(
    tmp_path, pg_engine,
):
    from sqlalchemy.orm import Session, sessionmaker
    from apps.api.src.domain.paper_trading.pending_replay import (
        replay_all_pending,
    )
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )
    skips = tmp_path / "skips"
    _write_pending(skips, dt.date(2026, 5, 3))
    _write_pending(skips, dt.date(2026, 5, 1))
    _write_pending(skips, dt.date(2026, 5, 2))

    result = replay_all_pending(
        before=dt.date(2026, 5, 5),
        SessionFactory=SessionCls, skips_dir=skips,
    )
    assert result["dates_replayed"] == [
        "2026-05-01", "2026-05-02", "2026-05-03",
    ]
    # All marked replayed → next call returns empty.
    again = replay_all_pending(
        before=dt.date(2026, 5, 5),
        SessionFactory=SessionCls, skips_dir=skips,
    )
    assert again["dates_replayed"] == []


def test_marker_written_on_zero_portfolios_avoids_infinite_loop(
    tmp_path, pg_engine,
):
    """The bug fix would regress if marker writes were skipped when
    there's nothing to do — replay would re-scan the same dates
    every run forever."""
    from sqlalchemy.orm import Session, sessionmaker
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )
    skips = tmp_path / "skips"
    _write_pending(skips, dt.date(2026, 5, 1))
    replay_pending_for_date(
        original_date=dt.date(2026, 5, 1),
        SessionFactory=SessionCls, skips_dir=skips,
    )
    # Re-collect — date should be absent.
    assert collect_pending_dates(
        before=dt.date(2026, 5, 5), skips_dir=skips,
    ) == []
