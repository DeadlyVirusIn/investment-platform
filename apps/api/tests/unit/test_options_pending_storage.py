"""Unit tests for the options pending JSONL store.

Pure file-based — no DB, no env.
"""

from __future__ import annotations

import datetime as dt

import pytest

from apps.api.src.options.pending_storage import (
    PENDING_REASON, REPLAYED_SUFFIX,
    append_pending, collect_pending_dates, count_pending,
    read_pending_for_date, write_marker,
)


def _legs() -> list[dict]:
    return [{
        "option_symbol": "AAPL_C200_30D",
        "action": "buy", "type": "call",
        "strike": 200, "expiry": "2026-05-29",
        "bid": 1.95, "ask": 2.05,
    }]


def test_append_and_read_roundtrip(tmp_path):
    skips = tmp_path / "skips"
    submitted = dt.datetime(
        2026, 5, 1, 21, 0, tzinfo=dt.timezone.utc,
    )
    append_pending(
        as_of=dt.date(2026, 5, 1), underlying="AAPL",
        strategy="long_call", legs=_legs(),
        submitted_at=submitted, skips_dir=skips,
    )
    rows = read_pending_for_date(
        as_of=dt.date(2026, 5, 1), skips_dir=skips,
    )
    assert len(rows) == 1
    assert rows[0]["underlying"] == "AAPL"
    assert rows[0]["reason"] == PENDING_REASON
    assert rows[0]["submitted_at"] == submitted.isoformat()


def test_collect_pending_dates_excludes_today_and_future(tmp_path):
    skips = tmp_path / "skips"
    submitted = dt.datetime(
        2026, 5, 1, 21, 0, tzinfo=dt.timezone.utc,
    )
    for d in (
        dt.date(2026, 4, 28),
        dt.date(2026, 5, 1),
        dt.date(2026, 5, 5),    # = before — excluded
        dt.date(2026, 5, 6),    # > before — excluded
    ):
        append_pending(
            as_of=d, underlying="AAPL", strategy="long_call",
            legs=_legs(), submitted_at=submitted, skips_dir=skips,
        )
    out = collect_pending_dates(
        before=dt.date(2026, 5, 5), skips_dir=skips,
    )
    assert out == [dt.date(2026, 4, 28), dt.date(2026, 5, 1)]


def test_collect_respects_from_date(tmp_path):
    skips = tmp_path / "skips"
    submitted = dt.datetime(
        2026, 5, 1, 21, 0, tzinfo=dt.timezone.utc,
    )
    for d in (
        dt.date(2026, 4, 15),
        dt.date(2026, 4, 20),
        dt.date(2026, 5, 1),
    ):
        append_pending(
            as_of=d, underlying="A", strategy="long_call",
            legs=_legs(), submitted_at=submitted, skips_dir=skips,
        )
    out = collect_pending_dates(
        before=dt.date(2026, 5, 5),
        from_date=dt.date(2026, 4, 20),
        skips_dir=skips,
    )
    assert out == [dt.date(2026, 4, 20), dt.date(2026, 5, 1)]


def test_force_includes_marked(tmp_path):
    skips = tmp_path / "skips"
    submitted = dt.datetime(
        2026, 5, 1, 21, 0, tzinfo=dt.timezone.utc,
    )
    append_pending(
        as_of=dt.date(2026, 4, 25), underlying="A",
        strategy="long_call", legs=_legs(),
        submitted_at=submitted, skips_dir=skips,
    )
    write_marker(
        as_of=dt.date(2026, 4, 25), summary={}, skips_dir=skips,
    )
    append_pending(
        as_of=dt.date(2026, 5, 1), underlying="A",
        strategy="long_call", legs=_legs(),
        submitted_at=submitted, skips_dir=skips,
    )

    # Without force: marked date excluded.
    assert collect_pending_dates(
        before=dt.date(2026, 5, 5), skips_dir=skips,
    ) == [dt.date(2026, 5, 1)]

    # With force: re-included.
    assert collect_pending_dates(
        before=dt.date(2026, 5, 5),
        skips_dir=skips, force=True,
    ) == [dt.date(2026, 4, 25), dt.date(2026, 5, 1)]


def test_marker_files_ignored_as_data(tmp_path):
    """Marker files (`<date>.replayed.jsonl`) live in the same dir
    but their date stems would collide with pending files. The
    collector must skip them."""
    skips = tmp_path / "skips"
    write_marker(
        as_of=dt.date(2026, 4, 25), summary={}, skips_dir=skips,
    )
    out = collect_pending_dates(
        before=dt.date(2026, 5, 5), skips_dir=skips,
    )
    assert out == []


def test_collect_returns_empty_when_dir_missing(tmp_path):
    out = collect_pending_dates(
        before=dt.date(2026, 5, 5),
        skips_dir=tmp_path / "does_not_exist",
    )
    assert out == []


def test_count_pending(tmp_path):
    skips = tmp_path / "skips"
    submitted = dt.datetime(
        2026, 5, 1, 21, 0, tzinfo=dt.timezone.utc,
    )
    for _ in range(3):
        append_pending(
            as_of=dt.date(2026, 4, 28), underlying="A",
            strategy="long_call", legs=_legs(),
            submitted_at=submitted, skips_dir=skips,
        )
    append_pending(
        as_of=dt.date(2026, 5, 1), underlying="B",
        strategy="long_call", legs=_legs(),
        submitted_at=submitted, skips_dir=skips,
    )
    c = count_pending(skips_dir=skips)
    assert c["total"] == 4
    assert c["by_date"]["2026-04-28"] == 3
    assert c["by_date"]["2026-05-01"] == 1


def test_count_pending_filters_range(tmp_path):
    skips = tmp_path / "skips"
    submitted = dt.datetime(
        2026, 5, 1, 21, 0, tzinfo=dt.timezone.utc,
    )
    for d in (
        dt.date(2026, 4, 15),
        dt.date(2026, 4, 28),
        dt.date(2026, 5, 1),
    ):
        append_pending(
            as_of=d, underlying="A", strategy="long_call",
            legs=_legs(), submitted_at=submitted, skips_dir=skips,
        )
    c = count_pending(
        skips_dir=skips,
        from_date=dt.date(2026, 4, 20),
        before=dt.date(2026, 5, 5),
    )
    assert c["total"] == 2
    assert "2026-04-15" not in c["by_date"]
