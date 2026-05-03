"""Phase 1 ranker tests."""

from __future__ import annotations

import datetime as dt
import math
from decimal import Decimal

import pytest

from packages.ensemble_ranker.scorer import _clamped, rank
from packages.signal_schema.signal import Signal


def _sig(symbol: str, strength, confidence, asset_id: str | None = None) -> Signal:
    return Signal(
        asset_id=asset_id or f"id-{symbol}",
        symbol=symbol,
        timestamp=dt.datetime(2026, 4, 21, tzinfo=dt.timezone.utc),
        as_of_date=dt.date(2026, 4, 21),
        strategy_id="det_v1", model_family="deterministic",
        model_version="x", features_version="v1",
        signal_direction="long",
        signal_strength=Decimal(str(strength)),
        confidence=Decimal(str(confidence)),
        holding_period_bars=10,
    )


class TestClamp:
    def test_positive_passes(self):
        assert _clamped(0.75) == 0.75
        assert _clamped(1.0) == 1.0

    def test_zero_returns_zero(self):
        assert _clamped(0) == 0.0

    def test_negative_clamped(self):
        assert _clamped(-0.5) == 0.0

    def test_nan_clamped(self):
        assert _clamped(float("nan")) == 0.0

    def test_none_clamped(self):
        assert _clamped(None) == 0.0

    def test_string_invalid_clamped(self):
        assert _clamped("bogus") == 0.0


class TestRank:
    def test_sorting_desc(self):
        a = _sig("A", 0.5, 0.5)
        b = _sig("B", 0.9, 0.9)
        c = _sig("C", 0.1, 0.1)
        out = rank([a, b, c])
        assert [r.symbol for r in out] == ["B", "A", "C"]

    def test_empty_input_empty_output(self):
        assert rank([]) == []

    def test_score_is_product(self):
        s = _sig("X", 0.6, 0.5)
        out = rank([s])
        assert out[0].score == pytest.approx(0.3, abs=1e-9)

    def test_zero_score_when_either_zero(self):
        a = _sig("A", 0, 0.9)
        b = _sig("B", 0.5, 0)
        out = rank([a, b])
        assert all(r.score == 0.0 for r in out)

    def test_contributing_populated(self):
        s = _sig("NVDA", 0.5, 0.5)
        out = rank([s])
        assert out[0].contributing == [s]

    def test_determinism(self):
        sigs = [_sig("A", 0.5, 0.5), _sig("B", 0.9, 0.9), _sig("C", 0.1, 0.1)]
        out1 = rank(sigs)
        out2 = rank(sigs)
        assert [r.symbol for r in out1] == [r.symbol for r in out2]
        assert [r.score for r in out1] == [r.score for r in out2]
