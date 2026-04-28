"""Phase 11P.3 - exploratory_runner unit tests (pure-fn paths)."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from apps.api.src.data.strategy.exploratory_runner import (
    EXPLORATORY_RULE_VERSION,
    PRODUCTION_GATES,
    SOURCE_TAG,
    ExploratoryConfig,
    ExploratorySafetyError,
    assert_exploratory_enabled,
    days_in_window,
    evaluate_exploratory_rule,
)


# ---------------------------------------------------------------------------
# Config invariants
# ---------------------------------------------------------------------------

def test_config_dry_xor_commit():
    with pytest.raises(ValueError, match="mutually exclusive"):
        ExploratoryConfig(
            date=dt.date(2026, 4, 27),
            underlyings=("SPY",),
            backfill_from=None,
            dry_run=True, commit=True,
        )


def test_config_underlyings_required():
    with pytest.raises(ValueError, match="underlyings"):
        ExploratoryConfig(
            date=dt.date(2026, 4, 27),
            underlyings=(),
            backfill_from=None,
            dry_run=True, commit=False,
        )


def test_config_backfill_must_be_before_date():
    with pytest.raises(ValueError, match="backfill_from"):
        ExploratoryConfig(
            date=dt.date(2026, 4, 27),
            underlyings=("SPY",),
            backfill_from=dt.date(2026, 5, 1),
            dry_run=True, commit=False,
        )


# ---------------------------------------------------------------------------
# Safety gate
# ---------------------------------------------------------------------------

def test_assert_disabled_blocks_commit():
    s = SimpleNamespace(EQUITY_EXPLORATORY_ENABLED=False)
    with pytest.raises(ExploratorySafetyError):
        assert_exploratory_enabled(s)


def test_assert_enabled_passes():
    s = SimpleNamespace(EQUITY_EXPLORATORY_ENABLED=True)
    assert_exploratory_enabled(s)


# ---------------------------------------------------------------------------
# Days window
# ---------------------------------------------------------------------------

def test_days_in_window_business_days_only():
    cfg = ExploratoryConfig(
        date=dt.date(2026, 4, 27),         # Monday
        underlyings=("SPY",),
        backfill_from=dt.date(2026, 4, 24),  # Friday
        dry_run=True, commit=False,
    )
    days = days_in_window(cfg)
    # Friday + Monday only (Sat/Sun excluded)
    assert days == [dt.date(2026, 4, 24), dt.date(2026, 4, 27)]


def test_days_in_window_single_day():
    cfg = ExploratoryConfig(
        date=dt.date(2026, 4, 27),
        underlyings=("SPY",),
        backfill_from=None,
        dry_run=True, commit=False,
    )
    assert days_in_window(cfg) == [dt.date(2026, 4, 27)]


# ---------------------------------------------------------------------------
# Frozen rule evaluation
# ---------------------------------------------------------------------------

def test_evaluate_rule_fires_when_one_gate_true():
    d = evaluate_exploratory_rule(
        as_of=dt.date(2026, 4, 27), instrument="SPY",
        gates={"rates_calm": True, "vrp_supportive": False,
               "credit_stable": False, "liquidity_expanding": False},
    )
    assert d.fire is True
    assert d.strict_gates_passed is False
    assert "vrp_supportive" in d.failed_gates
    assert "rates_calm" not in d.failed_gates
    assert d.rule_id == EXPLORATORY_RULE_VERSION


def test_evaluate_rule_no_fire_all_false():
    d = evaluate_exploratory_rule(
        as_of=dt.date(2026, 4, 27), instrument="SPY",
        gates={g: False for g in PRODUCTION_GATES},
    )
    assert d.fire is False
    assert d.strict_gates_passed is False
    assert set(d.failed_gates) == set(PRODUCTION_GATES)


def test_evaluate_rule_no_fire_all_none():
    d = evaluate_exploratory_rule(
        as_of=dt.date(2026, 4, 27), instrument="SPY",
        gates={g: None for g in PRODUCTION_GATES},
    )
    assert d.fire is False
    assert d.strict_gates_passed is False


def test_evaluate_rule_strict_pass_when_all_true():
    d = evaluate_exploratory_rule(
        as_of=dt.date(2026, 4, 27), instrument="SPY",
        gates={g: True for g in PRODUCTION_GATES},
    )
    assert d.fire is True
    assert d.strict_gates_passed is True
    assert d.failed_gates == ()


def test_evaluate_rule_gate_snapshot_complete():
    d = evaluate_exploratory_rule(
        as_of=dt.date(2026, 4, 27), instrument="SPY",
        gates={"rates_calm": True, "vrp_supportive": True,
               "credit_stable": False, "liquidity_expanding": None},
    )
    assert set(d.gate_snapshot.keys()) == set(PRODUCTION_GATES)
    assert d.gate_snapshot["rates_calm"] is True
    assert d.gate_snapshot["liquidity_expanding"] is None


def test_evaluate_rule_reason_strings_avoid_recommendation_language():
    d = evaluate_exploratory_rule(
        as_of=dt.date(2026, 4, 27), instrument="SPY",
        gates={"rates_calm": True, "vrp_supportive": False,
               "credit_stable": False, "liquidity_expanding": False},
    )
    forbidden = (
        "recommend", "signal", "best", "top pick",
        "trade now", "place order", "promote",
    )
    for f in forbidden:
        assert f not in d.reason.lower()


def test_rule_version_constant_frozen():
    assert EXPLORATORY_RULE_VERSION == "EXPLORATORY_RULE_v1.0.0"


def test_source_tag_constant_frozen():
    assert SOURCE_TAG == "exploratory_paper"


def test_production_gates_tuple_frozen():
    assert PRODUCTION_GATES == (
        "rates_calm", "vrp_supportive",
        "credit_stable", "liquidity_expanding",
    )
