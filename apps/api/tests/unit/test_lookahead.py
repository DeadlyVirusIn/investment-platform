"""QW1.1 — unit tests for the pure lookahead invariant. DB-free."""

from __future__ import annotations

import datetime as dt

from apps.api.src.analytics.lookahead import max_input_ts_le_decision

D = dt.datetime(2026, 6, 15, 14, 0, tzinfo=dt.timezone.utc)


def test_before_decision_ok():
    r = max_input_ts_le_decision(D, [D - dt.timedelta(hours=1), D - dt.timedelta(days=1)])
    assert r["ok"] is True
    assert r["violation"] is None
    assert r["latest_input"] == D - dt.timedelta(hours=1)


def test_equal_timestamp_ok():
    r = max_input_ts_le_decision(D, [D])
    assert r["ok"] is True
    assert r["violation"] is None


def test_after_decision_violation():
    after = D + dt.timedelta(minutes=30)
    r = max_input_ts_le_decision(D, [D - dt.timedelta(hours=2), after])
    assert r["ok"] is False
    assert r["latest_input"] == after
    assert r["violation"]["seconds_after"] == 1800.0


def test_empty_inputs_ok():
    r = max_input_ts_le_decision(D, [])
    assert r["ok"] is True
    assert r["latest_input"] is None
    assert r["violation"] is None


def test_all_none_ok():
    r = max_input_ts_le_decision(D, [None, None])
    assert r["ok"] is True
    assert r["latest_input"] is None


def test_naive_input_assumed_utc():
    naive_after = dt.datetime(2026, 6, 15, 14, 30)  # naive -> UTC -> after D
    r = max_input_ts_le_decision(D, [naive_after])
    assert r["ok"] is False
    assert r["latest_input"].tzinfo is not None  # coerced tz-aware


def test_timezone_conversion_before():
    tz5 = dt.timezone(dt.timedelta(hours=5))
    # 18:00+05:00 == 13:00 UTC < 14:00 UTC decision
    inp = dt.datetime(2026, 6, 15, 18, 0, tzinfo=tz5)
    r = max_input_ts_le_decision(D, [inp])
    assert r["ok"] is True
    assert r["latest_input"] == dt.datetime(2026, 6, 15, 13, 0, tzinfo=dt.timezone.utc)


def test_grace_seconds_tolerates_small_skew():
    after5 = D + dt.timedelta(seconds=5)
    assert max_input_ts_le_decision(D, [after5])["ok"] is False
    assert max_input_ts_le_decision(D, [after5], grace_seconds=10)["ok"] is True


def test_naive_decision_ts_coerced():
    naive_D = dt.datetime(2026, 6, 15, 14, 0)
    r = max_input_ts_le_decision(
        naive_D, [dt.datetime(2026, 6, 15, 15, 0, tzinfo=dt.timezone.utc)]
    )
    assert r["ok"] is False  # 15:00Z > 14:00 (naive decision assumed UTC)
