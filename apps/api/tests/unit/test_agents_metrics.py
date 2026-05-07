"""Unit tests for `agents.metrics`.

Pure-module coverage: counter monotonicity, cost-estimate
non-negativity, snapshot shape, last_*_reason recording, and
the test-only reset hook.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.api.src.domain.agents import metrics


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics.reset()
    yield
    metrics.reset()


# ---------------------------------------------------------------------
# Snapshot shape + zero-state
# ---------------------------------------------------------------------

def test_snapshot_zero_state_has_all_keys():
    snap = metrics.snapshot()
    expected = {
        "requests_total", "disabled_total",
        "cache_hit_total", "cache_miss_total",
        "llm_calls_total", "safety_rejected_total",
        "transport_error_total", "cost_guard_blocked_total",
        "estimated_cost_usd_total",
        "last_call_at", "last_error_reason",
    }
    assert set(snap.keys()) == expected
    # Numeric counters all zero, last_* fields null.
    for k in expected:
        if k in ("last_call_at", "last_error_reason"):
            assert snap[k] is None, f"{k} not None"
        else:
            assert snap[k] == 0 or snap[k] == 0.0, f"{k} non-zero"


# ---------------------------------------------------------------------
# Counter monotonicity
# ---------------------------------------------------------------------

def test_request_counter_increments():
    metrics.record_request()
    metrics.record_request()
    assert metrics.snapshot()["requests_total"] == 2


def test_disabled_counter_increments():
    metrics.record_disabled()
    assert metrics.snapshot()["disabled_total"] == 1


def test_cache_counters_independent():
    metrics.record_cache_hit()
    metrics.record_cache_hit()
    metrics.record_cache_miss()
    snap = metrics.snapshot()
    assert snap["cache_hit_total"] == 2
    assert snap["cache_miss_total"] == 1


def test_safety_rejection_records_last_reason():
    metrics.record_safety_rejection("forbidden phrase: 'buy now'")
    snap = metrics.snapshot()
    assert snap["safety_rejected_total"] == 1
    assert snap["last_error_reason"].startswith("safety:")
    assert "buy now" in snap["last_error_reason"]


def test_transport_error_records_last_reason():
    metrics.record_transport_error("timeout:5s")
    snap = metrics.snapshot()
    assert snap["transport_error_total"] == 1
    assert snap["last_error_reason"].startswith("transport:")


def test_last_error_reason_caps_length():
    long = "x" * 1024
    metrics.record_transport_error(long)
    snap = metrics.snapshot()
    # Reason field is bounded.
    assert len(snap["last_error_reason"]) <= 256


# ---------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------

def test_record_llm_call_with_usage_uses_provider_tokens():
    metrics.record_llm_call(
        prompt="ignored when usage is present",
        body="ignored",
        usage=SimpleNamespace(input_tokens=10_000, output_tokens=5_000),
    )
    snap = metrics.snapshot()
    assert snap["llm_calls_total"] == 1
    # 10k input × $1/M  + 5k output × $5/M = $0.01 + $0.025 = $0.035
    assert snap["estimated_cost_usd_total"] == pytest.approx(
        0.035, abs=1e-9,
    )
    assert snap["last_call_at"] is not None


def test_record_llm_call_without_usage_uses_char_fallback():
    prompt = "x" * 4000   # ~1000 input tokens
    body = "y" * 400      # ~100 output tokens
    metrics.record_llm_call(prompt=prompt, body=body, usage=None)
    snap = metrics.snapshot()
    assert snap["llm_calls_total"] == 1
    # 1000/M × 1 + 100/M × 5 = 0.001 + 0.0005 = 0.0015
    assert snap["estimated_cost_usd_total"] == pytest.approx(
        0.0015, abs=1e-9,
    )


def test_cost_estimate_is_non_negative_for_garbage_usage():
    metrics.record_llm_call(
        prompt="",
        body="",
        usage=SimpleNamespace(input_tokens=-10, output_tokens=-20),
    )
    snap = metrics.snapshot()
    assert snap["estimated_cost_usd_total"] >= 0.0


def test_record_llm_call_does_not_raise_on_invalid_usage():
    """Bad object as `usage` must NOT propagate — accounting is
    decorative, must never block the response path."""
    class _BadUsage:
        @property
        def input_tokens(self):
            raise RuntimeError("boom")

    metrics.record_llm_call(prompt="p", body="b", usage=_BadUsage())
    snap = metrics.snapshot()
    assert snap["llm_calls_total"] == 1
    assert snap["estimated_cost_usd_total"] >= 0.0


# ---------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------

def test_reset_clears_all_counters():
    metrics.record_request()
    metrics.record_cache_hit()
    metrics.record_llm_call(prompt="p", body="b")
    metrics.record_safety_rejection("r")
    metrics.record_cost_guard_blocked(guard_usd=5.0)
    metrics.reset()
    snap = metrics.snapshot()
    assert snap["requests_total"] == 0
    assert snap["cache_hit_total"] == 0
    assert snap["llm_calls_total"] == 0
    assert snap["safety_rejected_total"] == 0
    assert snap["cost_guard_blocked_total"] == 0
    assert snap["last_call_at"] is None
    assert snap["last_error_reason"] is None


# ---------------------------------------------------------------------
# F8 — cost guard
# ---------------------------------------------------------------------

def test_is_cost_guard_reached_false_at_zero_cost():
    assert metrics.is_cost_guard_reached(5.0) is False


def test_is_cost_guard_reached_true_when_total_meets_guard():
    # Spend ~$0.05 by claiming 50_000 tokens of $1/M input.
    metrics.record_llm_call(
        prompt="p", body="b",
        usage=SimpleNamespace(input_tokens=50_000, output_tokens=0),
    )
    snap = metrics.snapshot()
    assert snap["estimated_cost_usd_total"] == pytest.approx(0.05)
    assert metrics.is_cost_guard_reached(0.05) is True
    assert metrics.is_cost_guard_reached(0.10) is False


def test_is_cost_guard_reached_strict_inequality_at_exact_match():
    """`>=` semantics: total exactly equal to guard counts as
    reached. Operator dashboards rely on this so the very first
    block fires at the threshold, not one cent past it."""
    metrics.record_llm_call(
        prompt="p", body="b",
        usage=SimpleNamespace(input_tokens=1_000_000, output_tokens=0),
    )
    snap = metrics.snapshot()
    assert snap["estimated_cost_usd_total"] == pytest.approx(1.0)
    assert metrics.is_cost_guard_reached(1.0) is True


@pytest.mark.parametrize("guard", [0.0, -1.0, -1e9])
def test_guard_disabled_when_value_non_positive(guard):
    """Guard <= 0 means unlimited; reached is always False even
    when actual cost has accrued."""
    metrics.record_llm_call(
        prompt="p", body="b",
        usage=SimpleNamespace(input_tokens=1_000_000, output_tokens=0),
    )
    assert metrics.is_cost_guard_reached(guard) is False


def test_record_cost_guard_blocked_increments_and_records_reason():
    metrics.record_cost_guard_blocked(guard_usd=5.0)
    metrics.record_cost_guard_blocked(guard_usd=5.0)
    snap = metrics.snapshot()
    assert snap["cost_guard_blocked_total"] == 2
    assert snap["last_error_reason"].startswith("guard:cost_blocked")
    assert "5.000000" in snap["last_error_reason"]


def test_is_cost_guard_reached_handles_garbage_input():
    """Garbage guard values must not raise — observability layer
    is fail-soft."""
    assert metrics.is_cost_guard_reached(None) is False  # type: ignore[arg-type]
    assert metrics.is_cost_guard_reached("nope") is False  # type: ignore[arg-type]
