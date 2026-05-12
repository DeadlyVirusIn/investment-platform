"""Phase 16 Phase 2 — derive_observation() + helpers pure-function tests.

The derivation must remain trivially testable in isolation (no DB, no
HTTP, no time mocks). The write_observation() UPSERT is an
integration concern verified separately.
"""

from __future__ import annotations

import datetime

import pytest

from apps.api.src.ml.intraday.observation_writer import (
    TIME_OF_DAY_BUCKETS,
    derive_observation,
    feature_hash,
    time_of_day_bucket,
    truncate_to_15min,
)


# ---------------------------------------------------------------------------
# truncate_to_15min
# ---------------------------------------------------------------------------


def test_truncate_floors_to_quarter_hour():
    ts = datetime.datetime(2026, 5, 12, 14, 23, 47, 123456,
                           tzinfo=datetime.timezone.utc)
    out = truncate_to_15min(ts)
    assert out.minute == 15
    assert out.second == 0
    assert out.microsecond == 0
    assert out.hour == 14


def test_truncate_naive_input_assumed_utc():
    ts = datetime.datetime(2026, 5, 12, 14, 7, 0)  # naive
    out = truncate_to_15min(ts)
    assert out.tzinfo == datetime.timezone.utc
    assert out.minute == 0


def test_truncate_quarter_hour_boundary_idempotent():
    ts = datetime.datetime(2026, 5, 12, 14, 15, 0,
                           tzinfo=datetime.timezone.utc)
    out = truncate_to_15min(ts)
    assert out == ts


# ---------------------------------------------------------------------------
# time_of_day_bucket
# ---------------------------------------------------------------------------


def _utc(year, month, day, hour, minute=0) -> datetime.datetime:
    return datetime.datetime(
        year, month, day, hour, minute,
        tzinfo=datetime.timezone.utc,
    )


def test_premarket_bucket_summer():
    # 05:00 ET in summer (May) = 09:00 UTC
    assert time_of_day_bucket(_utc(2026, 5, 12, 9, 0)) == "premarket"


def test_open30_bucket_summer():
    # 09:30 ET in summer = 13:30 UTC
    assert time_of_day_bucket(_utc(2026, 5, 12, 13, 30)) == "open30"


def test_morning_bucket_summer():
    # 11:00 ET in summer = 15:00 UTC
    assert time_of_day_bucket(_utc(2026, 5, 12, 15, 0)) == "morning"


def test_midday_bucket_summer():
    # 13:00 ET in summer = 17:00 UTC
    assert time_of_day_bucket(_utc(2026, 5, 12, 17, 0)) == "midday"


def test_close30_bucket_summer():
    # 15:45 ET in summer = 19:45 UTC
    assert time_of_day_bucket(_utc(2026, 5, 12, 19, 45)) == "close30"


def test_afterhours_bucket_summer():
    # 17:00 ET in summer = 21:00 UTC
    assert time_of_day_bucket(_utc(2026, 5, 12, 21, 0)) == "afterhours"


def test_off_bucket_overnight():
    # 03:00 ET in summer = 07:00 UTC
    assert time_of_day_bucket(_utc(2026, 5, 12, 7, 0)) == "off"


def test_off_bucket_weekend():
    # Sat 11:00 ET summer = Sat 15:00 UTC
    saturday = _utc(2026, 5, 16, 15, 0)
    assert time_of_day_bucket(saturday) == "off"


def test_winter_bucket_uses_est_offset():
    # 09:30 ET in winter (January) = 14:30 UTC (EST = UTC-5)
    assert time_of_day_bucket(_utc(2026, 1, 12, 14, 30)) == "open30"


def test_all_returned_bucket_names_are_known():
    """Defensive — sanity that no path returns an unexpected string."""
    for hour in range(0, 24):
        for minute in (0, 15, 30, 45):
            bucket = time_of_day_bucket(_utc(2026, 5, 12, hour, minute))
            assert bucket in TIME_OF_DAY_BUCKETS


# ---------------------------------------------------------------------------
# feature_hash
# ---------------------------------------------------------------------------


def test_hash_stable_across_key_order():
    a = feature_hash({"x": 1.0, "y": 2.0, "tod": "open30"})
    b = feature_hash({"tod": "open30", "y": 2.0, "x": 1.0})
    assert a == b
    assert len(a) == 32


def test_hash_treats_none_as_missing():
    a = feature_hash({"x": 1.0, "y": None})
    b = feature_hash({"x": 1.0})
    assert a == b


def test_hash_differs_on_value_change():
    a = feature_hash({"x": 1.0})
    b = feature_hash({"x": 1.0001})
    assert a != b


# ---------------------------------------------------------------------------
# derive_observation
# ---------------------------------------------------------------------------


def _base_kwargs():
    """Common kwargs with sensible defaults — individual tests override
    only what they care about."""
    return dict(
        recommendation_id="rec-1",
        symbol="NVDA",
        observed_at=datetime.datetime(2026, 5, 12, 15, 0,
                                      tzinfo=datetime.timezone.utc),
        price=110.0,
        prev_close=100.0,
        day_open=108.0,
        day_high=112.0,
        day_low=107.0,
        spy_change_pct=2.0,
        qqq_change_pct=2.5,
        dia_change_pct=1.5,
        prior_eod_conviction=72.0,
        action_type="buy",
        position_state="open_long",
        entry_reference_price=100.0,
        atr_60d_pct=2.0,
        vol_60d_pct=30.0,
        sector_id="TECH",
        source="polygon",
        delay_minutes=15,
        quote_ts=datetime.datetime(2026, 5, 12, 14, 45,
                                   tzinfo=datetime.timezone.utc),
    )


def test_full_happy_path_quantitative_features():
    row = derive_observation(**_base_kwargs())
    assert row.intraday_change_pct == pytest.approx(10.0, abs=1e-6)
    assert row.vs_open_pct == pytest.approx(((110 - 108) / 108) * 100, abs=1e-6)
    assert row.vs_recommendation_entry_pct == pytest.approx(10.0, abs=1e-6)
    assert row.vs_macro_drift_pct == pytest.approx(10.0 - 2.0, abs=1e-6)
    assert row.intraday_range_pct == pytest.approx(((112 - 107) / 108) * 100, abs=1e-6)


def test_provenance_fields_carried_through():
    kw = _base_kwargs()
    row = derive_observation(**kw)
    assert row.recommendation_id == "rec-1"
    assert row.symbol == "NVDA"
    assert row.source == "polygon"
    assert row.delay_minutes == 15
    assert row.quote_ts == kw["quote_ts"]


def test_observed_at_floored_to_15min_slot():
    kw = _base_kwargs()
    kw["observed_at"] = datetime.datetime(
        2026, 5, 12, 15, 23, 47,
        tzinfo=datetime.timezone.utc,
    )
    row = derive_observation(**kw)
    assert row.observed_at_15min.minute == 15
    assert row.observed_at_15min.second == 0


def test_time_of_day_bucket_derived_from_slot():
    kw = _base_kwargs()
    # 15:00 UTC summer = 11:00 ET = morning
    kw["observed_at"] = datetime.datetime(
        2026, 5, 12, 15, 0,
        tzinfo=datetime.timezone.utc,
    )
    row = derive_observation(**kw)
    assert row.time_of_day_bucket == "morning"


def test_null_inputs_propagate_without_raising():
    kw = _base_kwargs()
    kw["price"] = None
    row = derive_observation(**kw)
    assert row.intraday_change_pct is None
    assert row.vs_open_pct is None
    assert row.vs_recommendation_entry_pct is None
    assert row.vs_macro_drift_pct is None
    assert row.intraday_range_pct == pytest.approx(((112 - 107) / 108) * 100)


def test_zero_prev_close_does_not_divide_by_zero():
    kw = _base_kwargs()
    kw["prev_close"] = 0.0
    row = derive_observation(**kw)
    assert row.intraday_change_pct is None
    # vs_macro_drift uses intraday_change which is now None
    assert row.vs_macro_drift_pct is None


def test_macro_drift_none_when_macro_pct_missing():
    kw = _base_kwargs()
    kw["spy_change_pct"] = None
    row = derive_observation(**kw)
    assert row.vs_macro_drift_pct is None


def test_intraday_range_none_when_high_low_missing():
    kw = _base_kwargs()
    kw["day_high"] = None
    row = derive_observation(**kw)
    assert row.intraday_range_pct is None


def test_feature_hash_is_32_hex_chars():
    row = derive_observation(**_base_kwargs())
    assert len(row.feature_hash) == 32
    int(row.feature_hash, 16)  # raises if non-hex


def test_feature_hash_stable_for_identical_inputs():
    row1 = derive_observation(**_base_kwargs())
    row2 = derive_observation(**_base_kwargs())
    assert row1.feature_hash == row2.feature_hash


def test_feature_hash_changes_on_meaningful_input_change():
    row1 = derive_observation(**_base_kwargs())
    kw = _base_kwargs()
    kw["price"] = 110.01  # tiny but real change
    row2 = derive_observation(**kw)
    assert row1.feature_hash != row2.feature_hash


def test_feature_hash_invariant_to_provenance_fields():
    """Provenance (source, delay_minutes, quote_ts) MUST NOT affect
    the hash — only feature values should."""
    row1 = derive_observation(**_base_kwargs())
    kw = _base_kwargs()
    kw["quote_ts"] = datetime.datetime(
        2099, 1, 1, tzinfo=datetime.timezone.utc,
    )
    kw["delay_minutes"] = 99
    row2 = derive_observation(**kw)
    assert row1.feature_hash == row2.feature_hash
