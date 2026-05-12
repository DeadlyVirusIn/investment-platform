"""Phase 16 v1 — derive_intraday_context() pure-function tests.

The derivation must remain trivially testable in isolation (no DB, no
HTTP, no time mocks). All inputs are scalars; all behavior is
deterministic.
"""

from __future__ import annotations

import pytest

from apps.api.src.api.market import (
    OVERLAY_DRIFT_THRESHOLD_PCT,
    OVERLAY_QUIET_THRESHOLD_PCT,
    OVERLAY_STRESS_THRESHOLD_PCT,
    derive_intraday_context,
)


# ---------------------------------------------------------------------------
# Happy path — label classification
# ---------------------------------------------------------------------------


def test_aligned_label_when_symbol_within_drift_band_and_macro_present():
    """Symbol moved < ±0.5%, macro non-quiet -> aligned."""
    entry = derive_intraday_context(
        recommendation_id="rec-1",
        symbol="NVDA",
        price=100.20,
        prev_close=100.00,
        macro_intraday_pct=-0.4,  # SPY moving but macro not quiet
        quote_ts=1.0,
    )
    assert entry.context_label == "aligned"
    assert entry.intraday_change_pct == pytest.approx(0.20, abs=1e-6)
    assert entry.vs_recommendation_entry_pct == pytest.approx(0.20, abs=1e-6)
    assert entry.vs_macro_drift_pct == pytest.approx(0.6, abs=1e-6)


def test_drift_label_when_symbol_moved_between_drift_and_stress_thresholds():
    """Symbol +0.8% (above drift threshold, below stress) -> drift."""
    entry = derive_intraday_context(
        recommendation_id="rec-2",
        symbol="MSFT",
        price=100.80,
        prev_close=100.00,
        macro_intraday_pct=0.0,
        quote_ts=1.0,
    )
    assert entry.context_label == "drift"


def test_stress_label_when_symbol_below_stress_threshold():
    """Symbol -2.0% (worse than -1.5% stress threshold) -> stress."""
    entry = derive_intraday_context(
        recommendation_id="rec-3",
        symbol="TSLA",
        price=98.00,
        prev_close=100.00,
        macro_intraday_pct=-0.5,
        quote_ts=1.0,
    )
    assert entry.context_label == "stress"
    assert entry.vs_recommendation_entry_pct == pytest.approx(-2.0, abs=1e-6)
    assert entry.vs_macro_drift_pct == pytest.approx(-1.5, abs=1e-6)


def test_quiet_label_when_both_symbol_and_macro_moves_are_tiny():
    """|symbol| < 0.2% AND |macro| < 0.2% -> quiet."""
    entry = derive_intraday_context(
        recommendation_id="rec-4",
        symbol="AAPL",
        price=100.10,
        prev_close=100.00,
        macro_intraday_pct=0.05,
        quote_ts=1.0,
    )
    assert entry.context_label == "quiet"


def test_quiet_label_when_macro_is_none_but_symbol_is_quiet():
    """Symbol move < 0.2% AND no macro signal -> still quiet (no macro
    means we can't disprove quiet; default to quiet)."""
    entry = derive_intraday_context(
        recommendation_id="rec-5",
        symbol="AAPL",
        price=100.10,
        prev_close=100.00,
        macro_intraday_pct=None,
        quote_ts=1.0,
    )
    assert entry.context_label == "quiet"


# ---------------------------------------------------------------------------
# Edge cases — null/zero/missing inputs
# ---------------------------------------------------------------------------


def test_quiet_when_price_is_none():
    """No upstream price -> intraday_change_pct None -> quiet, all
    derived fields are None (no math performed)."""
    entry = derive_intraday_context(
        recommendation_id="rec-6",
        symbol="NVDA",
        price=None,
        prev_close=100.00,
        macro_intraday_pct=-0.5,
        quote_ts=1.0,
    )
    assert entry.context_label == "quiet"
    assert entry.intraday_change_pct is None
    assert entry.vs_recommendation_entry_pct is None
    assert entry.vs_macro_drift_pct is None


def test_quiet_when_prev_close_is_none():
    """No prev_close -> can't compute change pct -> quiet."""
    entry = derive_intraday_context(
        recommendation_id="rec-7",
        symbol="NVDA",
        price=100.00,
        prev_close=None,
        macro_intraday_pct=-0.5,
        quote_ts=1.0,
    )
    assert entry.context_label == "quiet"
    assert entry.intraday_change_pct is None


def test_quiet_when_prev_close_is_zero_division_safe():
    """prev_close=0 must not raise; returns None for change pct."""
    entry = derive_intraday_context(
        recommendation_id="rec-8",
        symbol="WEIRD",
        price=100.00,
        prev_close=0.0,
        macro_intraday_pct=-0.5,
        quote_ts=1.0,
    )
    assert entry.intraday_change_pct is None
    assert entry.context_label == "quiet"


def test_macro_drift_unset_when_macro_pct_is_none():
    """Symbol moved meaningfully but macro is None — vs_macro_drift_pct
    must be None, not a misleading value derived from a nil benchmark."""
    entry = derive_intraday_context(
        recommendation_id="rec-9",
        symbol="NVDA",
        price=101.00,  # +1.0% — drift band
        prev_close=100.00,
        macro_intraday_pct=None,
        quote_ts=1.0,
    )
    assert entry.vs_macro_drift_pct is None
    assert entry.context_label == "drift"


# ---------------------------------------------------------------------------
# Threshold boundary checks (ensure the published thresholds are
# enforced exactly — protects against accidental drift if someone
# tweaks the constants without updating tests)
# ---------------------------------------------------------------------------


def test_threshold_constants_match_arch_doc_v1():
    assert OVERLAY_DRIFT_THRESHOLD_PCT == 0.5
    assert OVERLAY_STRESS_THRESHOLD_PCT == 1.5
    assert OVERLAY_QUIET_THRESHOLD_PCT == 0.2


def test_aligned_at_exact_drift_threshold_minus_epsilon():
    """Symbol at exactly +0.499% is below drift threshold -> aligned."""
    entry = derive_intraday_context(
        recommendation_id="rec-b1",
        symbol="X",
        price=100.499,
        prev_close=100.000,
        macro_intraday_pct=-0.5,
        quote_ts=1.0,
    )
    assert entry.context_label == "aligned"


def test_drift_at_exact_drift_threshold():
    """Symbol at exactly +0.5% is AT the drift threshold -> drift."""
    entry = derive_intraday_context(
        recommendation_id="rec-b2",
        symbol="X",
        price=100.500,
        prev_close=100.000,
        macro_intraday_pct=-0.5,
        quote_ts=1.0,
    )
    assert entry.context_label == "drift"


def test_stress_only_when_strictly_below_negative_stress_threshold():
    """Symbol at exactly -1.5% is at the threshold but the rule uses
    `<`, so it should still be drift, not stress."""
    entry = derive_intraday_context(
        recommendation_id="rec-b3",
        symbol="X",
        price=98.500,
        prev_close=100.000,
        macro_intraday_pct=-0.5,
        quote_ts=1.0,
    )
    assert entry.context_label == "drift"

    # Just over the threshold -> stress
    entry2 = derive_intraday_context(
        recommendation_id="rec-b4",
        symbol="X",
        price=98.499,
        prev_close=100.000,
        macro_intraday_pct=-0.5,
        quote_ts=1.0,
    )
    assert entry2.context_label == "stress"


# ---------------------------------------------------------------------------
# Provenance fields are passed through unchanged
# ---------------------------------------------------------------------------


def test_provenance_fields_carried_through():
    entry = derive_intraday_context(
        recommendation_id="rec-prov",
        symbol="NVDA",
        price=100.50,
        prev_close=100.00,
        macro_intraday_pct=0.0,
        quote_ts=1234567890.0,
        source="polygon",
        delay_minutes=15,
        derived_at=2222222222.0,
    )
    assert entry.recommendation_id == "rec-prov"
    assert entry.symbol == "NVDA"
    assert entry.quote_ts == 1234567890.0
    assert entry.source == "polygon"
    assert entry.delay_minutes == 15
    assert entry.derived_at == 2222222222.0
