"""Unit tests — Opt-Obs-Fix2 weekend-aware freshness classifier.

Proves the Monday-pre-close false 'stale' clears for Mon-Fri post-close
daily jobs, WHILE a genuine weekday stall still surfaces as stale.
Pure datetime logic — no DB, no real clock.

Calendar anchors (all UTC):
  Fri 2026-05-29, Sat 2026-05-30, Sun 2026-05-31,
  Mon 2026-06-01, Tue 2026-06-02, Wed 2026-06-03.
"""

from __future__ import annotations

import datetime as dt

from apps.api.src.api.admin_observability import (
    _classify_cadence,
    _classify_weekday_daily,
    _weekday_settle_on_or_before,
)

_SETTLE = 22  # UTC settle hour used by the four daily rows


def _utc(y, m, d, h=0, mi=0):
    return dt.datetime(y, m, d, h, mi, tzinfo=dt.timezone.utc)


# --- _weekday_settle_on_or_before --------------------------------------

def test_monday_morning_expected_run_is_friday():
    # Monday 11:09 ET (15:09 UTC), before today's 22:00 slot → last
    # expected run is FRIDAY's, skipping the weekend.
    now = _utc(2026, 6, 1, 15, 9)
    expected = _weekday_settle_on_or_before(now, _SETTLE)
    assert expected == _utc(2026, 5, 29, 22)


def test_saturday_expected_run_is_friday():
    now = _utc(2026, 5, 30, 12)
    assert _weekday_settle_on_or_before(now, _SETTLE) == _utc(2026, 5, 29, 22)


# --- _classify_weekday_daily: FALSE-POSITIVE CLEARANCE ------------------

def test_monday_preclose_friday_data_is_fresh_not_stale():
    # The exact production scenario: Friday-dated data, Monday 15:09 UTC.
    now = _utc(2026, 6, 1, 15, 9)
    for ts in (
        _utc(2026, 5, 29, 22, 4),    # market_prices ingest success
        _utc(2026, 5, 29, 22, 30),   # recommendations generated_at
        _utc(2026, 5, 29, 23, 0),    # paper_snapshots / envelopes
    ):
        assert _classify_weekday_daily(ts, now, _SETTLE) == "fresh"


def test_weekend_friday_data_is_fresh():
    now = _utc(2026, 5, 31, 18)  # Sunday
    ts = _utc(2026, 5, 29, 23, 0)
    assert _classify_weekday_daily(ts, now, _SETTLE) == "fresh"


# --- _classify_weekday_daily: REAL STALL STILL ALERTS ------------------

def test_weekday_stall_two_runs_behind_is_stale():
    # Wednesday after settle; data last written Monday → Tuesday's AND
    # Wednesday's expected runs both missed → genuine stall → STALE.
    now = _utc(2026, 6, 3, 23, 0)
    ts = _utc(2026, 6, 1, 22, 4)
    assert _classify_weekday_daily(ts, now, _SETTLE) == "stale"


def test_weekday_one_run_behind_is_degraded():
    # Tuesday after settle; data last written Monday → exactly one
    # expected run missed → degraded (not yet stale).
    now = _utc(2026, 6, 2, 22, 30)
    ts = _utc(2026, 6, 1, 22, 4)
    assert _classify_weekday_daily(ts, now, _SETTLE) == "degraded"


def test_same_weekday_after_run_is_fresh():
    now = _utc(2026, 6, 2, 23, 30)
    ts = _utc(2026, 6, 2, 22, 5)
    assert _classify_weekday_daily(ts, now, _SETTLE) == "fresh"


def test_none_timestamp_is_unknown():
    assert _classify_weekday_daily(None, _utc(2026, 6, 1, 15), _SETTLE) \
        == "unknown"


def test_naive_timestamp_treated_as_utc():
    now = _utc(2026, 6, 1, 15, 9)
    ts_naive = dt.datetime(2026, 5, 29, 22, 4)
    assert _classify_weekday_daily(ts_naive, now, _SETTLE) == "fresh"


# --- raw cadence classifier untouched for non-daily rows ---------------

def test_raw_cadence_classifier_unchanged():
    assert _classify_cadence(2.0, 6.0) == "fresh"
    assert _classify_cadence(9.0, 6.0) == "degraded"
    assert _classify_cadence(13.0, 6.0) == "stale"
    assert _classify_cadence(None, 6.0) == "unknown"
