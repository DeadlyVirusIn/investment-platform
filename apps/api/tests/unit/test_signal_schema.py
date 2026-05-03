"""Phase 1 Signal pydantic tests."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from pydantic import ValidationError

from packages.signal_schema.signal import Signal


def _valid_kwargs(**overrides):
    base = dict(
        asset_id="a-1", symbol="AAPL",
        timestamp=dt.datetime(2026, 4, 21, 15, tzinfo=dt.timezone.utc),
        as_of_date=dt.date(2026, 4, 21), timeframe="1d",
        strategy_id="det_v1", model_family="deterministic",
        model_version="test:abc", features_version="v1",
        signal_direction="long",
        signal_strength=Decimal("0.5"),
        confidence=Decimal("0.75"),
        holding_period_bars=20,
    )
    base.update(overrides)
    return base


def test_valid_signal_passes():
    s = Signal(**_valid_kwargs())
    assert s.symbol == "AAPL"
    assert s.signal_strength == Decimal("0.5")


def test_signal_strength_below_zero_fails():
    with pytest.raises(ValidationError):
        Signal(**_valid_kwargs(signal_strength=Decimal("-0.01")))


def test_signal_strength_above_one_fails():
    with pytest.raises(ValidationError):
        Signal(**_valid_kwargs(signal_strength=Decimal("1.01")))


def test_confidence_bounds():
    with pytest.raises(ValidationError):
        Signal(**_valid_kwargs(confidence=Decimal("-0.1")))
    with pytest.raises(ValidationError):
        Signal(**_valid_kwargs(confidence=Decimal("1.5")))


def test_edge_zero_and_one_pass():
    s0 = Signal(**_valid_kwargs(signal_strength=Decimal("0"), confidence=Decimal("0")))
    s1 = Signal(**_valid_kwargs(signal_strength=Decimal("1"), confidence=Decimal("1")))
    assert s0.signal_strength == Decimal("0")
    assert s1.signal_strength == Decimal("1")


def test_direction_enum_enforced():
    with pytest.raises(ValidationError):
        Signal(**_valid_kwargs(signal_direction="sideways"))


def test_model_family_enum_enforced():
    with pytest.raises(ValidationError):
        Signal(**_valid_kwargs(model_family="cosmic_ray_model"))


def test_holding_period_bars_must_be_positive():
    with pytest.raises(ValidationError):
        Signal(**_valid_kwargs(holding_period_bars=0))
    with pytest.raises(ValidationError):
        Signal(**_valid_kwargs(holding_period_bars=-3))


def test_risk_score_bounds_when_given():
    with pytest.raises(ValidationError):
        Signal(**_valid_kwargs(risk_score=Decimal("1.5")))
    # None is allowed
    Signal(**_valid_kwargs(risk_score=None))


def test_frozen_immutable():
    s = Signal(**_valid_kwargs())
    with pytest.raises(Exception):
        s.symbol = "MSFT"   # type: ignore[misc]


def test_extra_forbid():
    with pytest.raises(ValidationError):
        Signal(**_valid_kwargs(unknown_field="nope"))
