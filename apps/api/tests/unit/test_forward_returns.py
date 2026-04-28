"""Phase 11P.5 - forward_returns pure-fn tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.src.labeling.forward_returns import (
    DEFAULT_THRESHOLD_PCT,
    LABEL_VERSION,
    classify_outcome,
    compute_horizon_returns,
    compute_label_confidence,
    compute_mae_mfe,
    compute_return_h,
    label_for_observation,
)


D = Decimal


# ---------------------------------------------------------------------------
# compute_return_h
# ---------------------------------------------------------------------------

def test_compute_return_h_positive():
    assert compute_return_h(D("100"), D("105")) == D("0.05")


def test_compute_return_h_negative():
    assert compute_return_h(D("100"), D("95")) == D("-0.05")


def test_compute_return_h_zero():
    assert compute_return_h(D("100"), D("100")) == D("0")


def test_compute_return_h_returns_none_when_entry_missing():
    assert compute_return_h(None, D("100")) is None


def test_compute_return_h_returns_none_when_exit_missing():
    assert compute_return_h(D("100"), None) is None


def test_compute_return_h_returns_none_when_entry_zero():
    assert compute_return_h(D("0"), D("100")) is None


def test_compute_return_h_deterministic():
    a = compute_return_h(D("100"), D("110"))
    b = compute_return_h(D("100"), D("110"))
    assert a == b


# ---------------------------------------------------------------------------
# compute_mae_mfe
# ---------------------------------------------------------------------------

def test_compute_mae_mfe_window():
    e = compute_mae_mfe(
        D("100"),
        [D("102"), D("99"), D("105"), D("97"), D("103")],
    )
    assert e.mae == D("-0.03")
    assert e.mfe == D("0.05")


def test_compute_mae_mfe_empty_window():
    e = compute_mae_mfe(D("100"), [])
    assert e.mae is None
    assert e.mfe is None


def test_compute_mae_mfe_none_entry():
    e = compute_mae_mfe(None, [D("100")])
    assert e.mae is None
    assert e.mfe is None


def test_compute_mae_mfe_zero_entry():
    e = compute_mae_mfe(D("0"), [D("100")])
    assert e.mae is None
    assert e.mfe is None


def test_compute_mae_mfe_deterministic():
    e1 = compute_mae_mfe(D("100"), [D("105"), D("95")])
    e2 = compute_mae_mfe(D("100"), [D("105"), D("95")])
    assert e1 == e2


# ---------------------------------------------------------------------------
# classify_outcome
# ---------------------------------------------------------------------------

def test_classify_positive():
    assert classify_outcome(D("0.02")) == "positive"


def test_classify_negative():
    assert classify_outcome(D("-0.02")) == "negative"


def test_classify_neutral_above_zero():
    assert classify_outcome(D("0.001")) == "neutral"


def test_classify_neutral_below_zero():
    assert classify_outcome(D("-0.001")) == "neutral"


def test_classify_neutral_at_threshold():
    assert classify_outcome(D("0.005")) == "neutral"


def test_classify_none():
    assert classify_outcome(None) is None


def test_classify_custom_threshold():
    assert classify_outcome(D("0.01"), D("0.02")) == "neutral"
    assert classify_outcome(D("0.025"), D("0.02")) == "positive"


# ---------------------------------------------------------------------------
# compute_label_confidence
# ---------------------------------------------------------------------------

def test_label_confidence_clipped_to_one():
    c = compute_label_confidence(D("0.05"), D("0.005"))
    assert c == D("1")


def test_label_confidence_proportional():
    c = compute_label_confidence(D("0.0025"), D("0.005"))
    assert c == D("0.5")


def test_label_confidence_negative_return():
    c = compute_label_confidence(D("-0.0025"), D("0.005"))
    assert c == D("0.5")


def test_label_confidence_none_input():
    assert compute_label_confidence(None) is None


# ---------------------------------------------------------------------------
# compute_horizon_returns
# ---------------------------------------------------------------------------

def test_compute_horizon_returns_all_present():
    h = compute_horizon_returns(
        D("100"),
        {1: D("101"), 3: D("102"), 5: D("103"),
         10: D("110"), 20: D("105")},
    )
    assert h.return_1d  == D("0.01")
    assert h.return_5d  == D("0.03")
    assert h.return_20d == D("0.05")


def test_compute_horizon_returns_partial():
    h = compute_horizon_returns(
        D("100"), {1: D("101"), 3: D("102")},
    )
    assert h.return_1d  == D("0.01")
    assert h.return_5d  is None
    assert h.return_20d is None


# ---------------------------------------------------------------------------
# label_for_observation
# ---------------------------------------------------------------------------

def test_label_for_observation_full():
    label = label_for_observation(
        entry_price=D("100"),
        prices_by_horizon={
            1: D("101"), 3: D("102"), 5: D("103"),
            10: D("110"), 20: D("108"),
        },
        prices_full_window=[
            D("101"), D("99"), D("104"), D("110"),
            D("106"), D("108"),
        ],
        threshold_pct=D("0.005"),
    )
    assert label["return_20d"] == D("0.08")
    assert label["outcome_class"] == "positive"
    assert label["label_confidence"] == D("1")
    assert label["max_adverse_excursion"] == D("-0.01")
    assert label["max_favorable_excursion"] == D("0.10")
    assert label["label_version"] == LABEL_VERSION


def test_label_for_observation_provisional_when_horizon_missing():
    label = label_for_observation(
        entry_price=D("100"),
        prices_by_horizon={1: D("101"), 3: D("102")},
        prices_full_window=[D("101"), D("99")],
    )
    # primary 20d horizon missing → outcome_class None
    assert label["return_20d"] is None
    assert label["outcome_class"] is None


def test_label_version_constant_is_frozen():
    assert LABEL_VERSION == "label-v1.0.0"


def test_default_threshold_is_50bps():
    assert DEFAULT_THRESHOLD_PCT == D("0.005")
