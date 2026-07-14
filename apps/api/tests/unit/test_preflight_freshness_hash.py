"""pf-2 freshness-hash correctness (Wave 1B Phase 0).

The HIGH defect being pinned: pf-1 quantized the clock to a calendar date,
so a candidate could cross a sub-day policy boundary (provider ≤30h) while
keeping the same input hash and reuse a stale publishable verdict. pf-2
removes the clock from the hash entirely: identity = stored fact ids +
derived policy buckets, which change EXACTLY when a policy boundary is
crossed.
"""

from __future__ import annotations

import pytest

from apps.api.src.domain.publication import preflight as pf
from apps.api.tests.unit.test_publication_preflight import good_input

NOW = "2026-07-12T02:00:00+00:00"


def _at_provider_age(hours: float, **overrides):
    """Input whose ingest completed `hours` before NOW."""
    import datetime as dt
    now = dt.datetime.fromisoformat(NOW)
    fin = (now - dt.timedelta(hours=hours)).isoformat()
    return good_input(now=NOW, last_ingest_finished_at=fin, **overrides)


def _at_bar_age(days: float, **overrides):
    import datetime as dt
    now = dt.datetime.fromisoformat(NOW)
    ts = (now - dt.timedelta(days=days)).isoformat()
    return good_input(now=NOW, latest_bar_ts=ts, **overrides)


# ---------------------------------------------------------------------------
# provider 30h boundary
# ---------------------------------------------------------------------------

def test_29h59m_provider_age_is_publishable():
    res = pf.evaluate(_at_provider_age(29 + 59 / 60))
    assert res.verdict == "READY_WITH_LIMITATIONS"      # honest steady state
    assert next(c for c in res.checks
                if c.check_id == "provider_state").passed


def test_30h01m_provider_age_new_hash_and_hold():
    fresh_side = _at_provider_age(29 + 59 / 60)
    stale_side = _at_provider_age(30 + 1 / 60)
    assert fresh_side.input_hash() != stale_side.input_hash()
    assert pf.evaluate(stale_side).verdict == "HOLD"
    assert stale_side.buckets.provider_freshness == "stale"


def test_no_stale_publishable_verdict_survives_policy_state_change():
    # The publishable verdict's identity (hash) cannot be reused once the
    # provider bucket flips — the changed bucket changes the hash, so
    # ensure_current_verdict re-evaluates instead of reusing.
    a = _at_provider_age(29.0)
    b = _at_provider_age(31.0)
    assert pf.evaluate(a).verdict == "READY_WITH_LIMITATIONS"
    assert pf.evaluate(b).verdict == "HOLD"
    assert a.input_hash() != b.input_hash()


# ---------------------------------------------------------------------------
# midnight + day boundaries
# ---------------------------------------------------------------------------

def test_crossing_midnight_same_policy_state_is_idempotent():
    before = good_input(now="2026-07-12T23:30:00+00:00")
    after = good_input(now="2026-07-13T00:30:00+00:00")
    # Same facts, same buckets (bar still fresh, ingest still fresh) —
    # identical hash across midnight: no unnecessary history rows.
    assert before.buckets == after.buckets
    assert before.input_hash() == after.input_hash()


def test_crossing_five_day_price_boundary_changes_hash():
    inside = _at_bar_age(4.9)
    outside = _at_bar_age(5.1)
    assert inside.buckets.price_freshness == "fresh"
    assert outside.buckets.price_freshness == "stale"
    assert inside.input_hash() != outside.input_hash()
    assert pf.evaluate(outside).verdict == "HOLD"


# ---------------------------------------------------------------------------
# fact-identity changes
# ---------------------------------------------------------------------------

def test_new_provider_run_changes_hash():
    a = good_input(last_ingest_run_id="run-1")
    b = good_input(last_ingest_run_id="run-2")
    assert a.input_hash() != b.input_hash()


def test_new_provider_timestamp_changes_hash():
    a = _at_provider_age(2.0)
    b = _at_provider_age(3.0)
    # both fresh-bucket, but the stored fact (finished_at) differs
    assert a.buckets.provider_freshness == b.buckets.provider_freshness == "fresh"
    assert a.input_hash() != b.input_hash()


def test_new_price_bar_timestamp_changes_hash():
    a = _at_bar_age(0.5)
    b = _at_bar_age(1.5)
    assert a.buckets.price_freshness == b.buckets.price_freshness == "fresh"
    assert a.input_hash() != b.input_hash()


def test_posture_transition_changes_hash_and_verdict():
    normal = good_input(posture="NORMAL", posture_event_id="ev-1")
    safe = good_input(posture="SAFE", posture_event_id="ev-2")
    assert normal.input_hash() != safe.input_hash()
    assert pf.evaluate(safe).verdict == "HOLD"
    # even the event identity alone (same posture) invalidates
    normal2 = good_input(posture="NORMAL", posture_event_id="ev-3")
    assert normal.input_hash() != normal2.input_hash()


def test_same_facts_same_buckets_idempotent():
    a = good_input()
    b = good_input()
    assert a.input_hash() == b.input_hash()
    assert pf.evaluate(a).verdict == pf.evaluate(b).verdict


@pytest.mark.parametrize("field, values", [
    ("last_ingest_status", ("success", "failure")),
    ("newer_rec_id", (None, "rec-x")),
    ("snapshot_hash", ("a29f8f728b908128", "ffff000011112222")),
    ("engine_version", ("0.1.0", "0.2.0")),
])
def test_fact_identity_fields_are_hashed(field, values):
    a = good_input(**{field: values[0]})
    b = good_input(**{field: values[1]})
    assert a.input_hash() != b.input_hash()


def test_clock_itself_never_hashed():
    src = pf.PreflightInput.canonical_json.__doc__ or ""
    a = good_input(now="2026-07-12T02:00:00+00:00")
    b = good_input(now="2026-07-12T09:00:00+00:00")   # same buckets either way
    assert a.buckets == b.buckets
    assert a.input_hash() == b.input_hash()
