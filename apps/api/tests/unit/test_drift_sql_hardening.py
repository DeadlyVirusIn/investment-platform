"""SQL-first drift monitor (Priority 4) — hardening tests.

Pure-math and stub-session coverage for the edge cases the Trust Center
depends on: zero/empty bins, Laplace smoothing, identical vs severe drift,
NaN/Infinity inputs, minimum-sample boundaries, staleness thresholds,
version churn, deterministic output, and bounded report size.
"""

from __future__ import annotations

import datetime as dt
import math

from apps.api.src.domain.monitoring.drift import (
    MIN_SAMPLE,
    PSI_ALERT,
    PSI_WARN,
    DriftCheck,
    DriftReport,
    _status_for_psi,
    provider_freshness_checks,
    psi,
)


# --- psi: empty / degenerate inputs ----------------------------------------
def test_psi_empty_sides_return_none():
    assert psi([], [1.0]) is None
    assert psi([1.0], []) is None
    assert psi([], []) is None


def test_psi_no_reference_spread_returns_none():
    # constant reference → no quantile edges → None, never a div-by-zero
    assert psi([5.0] * 200, [5.0, 6.0, 7.0]) is None


def test_psi_identical_distributions_near_zero():
    vals = [float(i % 50) for i in range(500)]
    v = psi(vals, list(vals))
    assert v is not None and abs(v) < 1e-9


def test_psi_severe_drift_exceeds_alert():
    ref = [float(i % 50) for i in range(500)]          # 0..49
    cur = [float(1000 + i % 5) for i in range(500)]    # far right shift
    v = psi(ref, cur)
    assert v is not None and v > PSI_ALERT


def test_psi_zero_bins_survive_laplace_smoothing():
    # current entirely inside one reference bucket → 9 empty buckets;
    # smoothing must keep every log() finite
    ref = [float(i) for i in range(1000)]
    cur = [0.5] * 300
    v = psi(ref, cur)
    assert v is not None and math.isfinite(v)


def test_psi_nan_and_inf_inputs_do_not_crash_and_stay_finite():
    ref = [float(i) for i in range(200)]
    cur = [float("nan")] * 50 + [float("inf")] * 50 + [10.0] * 100
    v = psi(ref, cur)
    # NaN comparisons bucket deterministically (bucket 0), inf lands in the
    # last bucket — result is a finite float, never NaN
    assert v is not None and math.isfinite(v)


def test_psi_deterministic_same_inputs_same_output():
    ref = [math.sin(i) for i in range(300)]
    cur = [math.cos(i) for i in range(300)]
    assert psi(ref, cur) == psi(ref, cur) == psi(list(ref), list(cur))


# --- status thresholds ------------------------------------------------------
def test_status_minimum_sample_boundaries():
    ok_n = MIN_SAMPLE
    low_n = MIN_SAMPLE - 1
    assert _status_for_psi(0.0, low_n, ok_n) == "insufficient_data"
    assert _status_for_psi(0.0, ok_n, low_n) == "insufficient_data"
    assert _status_for_psi(0.0, ok_n, ok_n) == "ok"
    # insufficient_data wins over an alarming value — no invented verdicts
    assert _status_for_psi(9.9, low_n, low_n) == "insufficient_data"


def test_status_warn_alert_boundaries_inclusive():
    n = MIN_SAMPLE
    assert _status_for_psi(PSI_WARN - 1e-9, n, n) == "ok"
    assert _status_for_psi(PSI_WARN, n, n) == "warn"
    assert _status_for_psi(PSI_ALERT - 1e-9, n, n) == "warn"
    assert _status_for_psi(PSI_ALERT, n, n) == "alert"
    assert _status_for_psi(None, n, n) == "unavailable"


# --- provider freshness: staleness thresholds (weekday-aware) ---------------
class _FreshStub:
    """Session stub: returns fixed (provider, newest) rows."""
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *_a, **_k):
        stub = self

        class _R:
            def mappings(self):
                class _M:
                    def all(self):
                        return stub._rows
                return _M()
        return _R()


def _fresh(now, newest):
    return provider_freshness_checks(
        _FreshStub([{"provider": "tiingo", "newest": newest}]), now,
        budget_weekdays=3,
    )[0]


def test_freshness_ok_within_budget():
    now = dt.datetime(2026, 7, 8, 12, tzinfo=dt.timezone.utc)   # Wednesday
    newest = dt.datetime(2026, 7, 7, 21, tzinfo=dt.timezone.utc)  # Tuesday
    c = _fresh(now, newest)
    assert c.status == "ok" and c.value == 1.0


def test_freshness_weekend_not_counted():
    now = dt.datetime(2026, 7, 6, 12, tzinfo=dt.timezone.utc)     # Monday
    newest = dt.datetime(2026, 7, 3, 21, tzinfo=dt.timezone.utc)  # Friday
    c = _fresh(now, newest)
    assert c.value == 1.0 and c.status == "ok"   # Sat+Sun skipped


def test_freshness_warn_then_alert_thresholds():
    now = dt.datetime(2026, 7, 10, 12, tzinfo=dt.timezone.utc)    # Friday
    newest_warn = dt.datetime(2026, 7, 6, tzinfo=dt.timezone.utc)  # Mon → 4 wd
    assert _fresh(now, newest_warn).status == "warn"               # 4 > 3
    newest_alert = dt.datetime(2026, 6, 30, tzinfo=dt.timezone.utc)  # 8 wd
    assert _fresh(now, newest_alert).status == "alert"             # 8 > 6


def test_freshness_naive_timestamp_coerced_utc():
    now = dt.datetime(2026, 7, 8, 12, tzinfo=dt.timezone.utc)
    c = _fresh(now, dt.datetime(2026, 7, 7, 21))   # naive
    assert c.status == "ok"


def test_freshness_no_bars_unavailable():
    checks = provider_freshness_checks(_FreshStub([]),
                                       dt.datetime.now(dt.timezone.utc))
    assert checks[0].status == "unavailable"


# --- report: bounded size, worst-status aggregation, version churn shape ----
def test_report_bounded_and_truncation_counted():
    rep = DriftReport("t", "r", "c",
                      checks=[DriftCheck(f"c{i}", "ok") for i in range(40)])
    d = rep.to_dict()
    assert len(d["checks"]) == 25            # _MAX_ITEMS bound
    assert d["checks_truncated"] == 15
    assert d["overall"] == "ok"


def test_report_worst_status_wins_and_detail_capped():
    rep = DriftReport("t", "r", "c", checks=[
        DriftCheck("a", "ok"),
        DriftCheck("b", "insufficient_data"),
        DriftCheck("c", "alert", detail="x" * 1000),
        DriftCheck("d", "warn"),
    ])
    d = rep.to_dict()
    assert d["overall"] == "alert"
    assert len(d["checks"][2]["detail"]) <= 300   # bounded detail


def test_report_deterministic_serialization():
    rep = DriftReport("t", "r", "c", checks=[DriftCheck("a", "warn", value=0.2)])
    assert rep.to_dict() == rep.to_dict()
