"""Unit tests for the SignalValidationAgent's pure check logic.

Covers `_check_signal` independent of the DB so each rule is
exercised against a constructed ORM object.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.api.src.domain.agent_workflows.agents.signal_validation import (
    _check_signal,
)


def _signal(**overrides):
    """Construct a stand-in for `Signal`. Uses SimpleNamespace
    rather than the ORM class so we don't need to set every
    nullable column."""
    base = dict(
        signal_id="s1",
        as_of_date=dt.date(2026, 5, 1),
        symbol="NVDA",
        strategy_id="strat1",
        signal_direction="long",
        signal_strength=Decimal("0.75"),
        confidence=Decimal("0.80"),
        holding_period_bars=5,
        regime_tag="bull",
        generated_at=dt.datetime(2026, 5, 1, 12,
                                 tzinfo=dt.timezone.utc),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _check(s, **kw):
    return _check_signal(
        s,
        confidence_floor=kw.get("confidence_floor", 0.5),
        max_age_days=kw.get("max_age_days", 30),
    )


# ---------------------------------------------------------------------
# Aligned signal returns no warnings
# ---------------------------------------------------------------------

def test_clean_signal_returns_no_warnings():
    assert _check(_signal()) == []


# ---------------------------------------------------------------------
# Rule R1 — confidence floor
# ---------------------------------------------------------------------

def test_low_confidence_flags():
    out = _check(_signal(confidence=Decimal("0.40")))
    assert any(w.startswith("low_confidence") for w in out)


def test_confidence_at_floor_passes():
    out = _check(_signal(confidence=Decimal("0.50")))
    assert all(not w.startswith("low_confidence") for w in out)


# ---------------------------------------------------------------------
# Rule R2 — strength/direction alignment
# ---------------------------------------------------------------------

def test_long_with_negative_strength_flags_mismatch():
    out = _check(_signal(
        signal_direction="long",
        signal_strength=Decimal("-0.5"),
    ))
    assert any("strength_direction_mismatch:long_negative" in w
               for w in out)


def test_short_with_positive_strength_flags_mismatch():
    out = _check(_signal(
        signal_direction="short",
        signal_strength=Decimal("0.5"),
    ))
    assert any("strength_direction_mismatch:short_positive" in w
               for w in out)


def test_zero_strength_flags_ambiguous():
    out = _check(_signal(signal_strength=Decimal("0")))
    assert "ambiguous_strength_zero" in out


def test_buy_alias_treated_as_long():
    """`signal_direction` may be either 'long'/'short' or
    'buy'/'sell'. The agent normalizes so a positive strength
    on a buy/long row passes."""
    out = _check(_signal(
        signal_direction="buy",
        signal_strength=Decimal("0.4"),
    ))
    assert all("strength_direction_mismatch" not in w for w in out)


# ---------------------------------------------------------------------
# Rule R3 — holding period
# ---------------------------------------------------------------------

def test_zero_holding_period_flags():
    out = _check(_signal(holding_period_bars=0))
    assert "holding_period_nonpositive" in out


# ---------------------------------------------------------------------
# Rule R4 — regime tag presence
# ---------------------------------------------------------------------

@pytest.mark.parametrize("regime", [None, "", "   "])
def test_missing_regime_flags(regime):
    out = _check(_signal(regime_tag=regime))
    assert "regime_tag_missing" in out


# ---------------------------------------------------------------------
# Rule R5 — freshness
# ---------------------------------------------------------------------

def test_stale_generated_at_flags():
    out = _check(_signal(
        as_of_date=dt.date(2026, 5, 1),
        generated_at=dt.datetime(2026, 1, 1, 12,
                                 tzinfo=dt.timezone.utc),
    ))
    assert any(w.startswith("stale") for w in out)


def test_fresh_generated_at_passes():
    out = _check(_signal(
        as_of_date=dt.date(2026, 5, 1),
        generated_at=dt.datetime(2026, 5, 2, 12,
                                 tzinfo=dt.timezone.utc),
    ))
    assert all(not w.startswith("stale") for w in out)


# ---------------------------------------------------------------------
# Multiple violations all fire
# ---------------------------------------------------------------------

def test_multiple_rule_violations_all_fire():
    out = _check(_signal(
        confidence=Decimal("0.10"),
        signal_strength=Decimal("0"),
        holding_period_bars=0,
        regime_tag=None,
    ))
    rule_prefixes = {w.split(":", 1)[0] for w in out}
    assert "low_confidence" in rule_prefixes
    assert "ambiguous_strength_zero" in rule_prefixes
    assert "holding_period_nonpositive" in rule_prefixes
    assert "regime_tag_missing" in rule_prefixes
