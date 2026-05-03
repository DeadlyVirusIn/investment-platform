"""Unit tests — behavioral base schema + helpers."""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from apps.api.src.domain.behavioral.base import (
    AssetHistory,
    Bar,
    BehavioralSignal,
    MarketContext,
    clip01,
    daily_returns,
    safe_mean,
    safe_std,
)


def _bar(day: int = 1, close: float = 100.0, volume: float = 1e6) -> Bar:
    d = dt.date(2026, 1, day)
    return Bar(ts=d, open=close, high=close * 1.01, low=close * 0.99,
               close=close, volume=volume)


class TestBehavioralSignalSchema:
    def _valid_kwargs(self) -> dict:
        return dict(
            symbol="AAPL",
            timestamp=dt.datetime(2026, 4, 21, 22, 0, tzinfo=dt.timezone.utc),
            strategy_id="volume_anomaly_v1",
            signal_direction="long",
            signal_strength=0.5,
            confidence=0.7,
            explanation="demo",
            metadata={"k": 1},
        )

    def test_valid_signal_constructs(self):
        s = BehavioralSignal(**self._valid_kwargs())
        assert s.source_type == "behavioral"
        assert s.timeframe == "1d"
        assert s.signal_strength == 0.5

    def test_strength_out_of_range_raises(self):
        kw = self._valid_kwargs()
        kw["signal_strength"] = 1.5
        with pytest.raises(ValidationError):
            BehavioralSignal(**kw)

    def test_confidence_negative_raises(self):
        kw = self._valid_kwargs()
        kw["confidence"] = -0.01
        with pytest.raises(ValidationError):
            BehavioralSignal(**kw)

    def test_frozen_immutable(self):
        s = BehavioralSignal(**self._valid_kwargs())
        with pytest.raises(ValidationError):
            s.symbol = "CHANGED"  # type: ignore

    def test_invalid_direction_rejected(self):
        kw = self._valid_kwargs()
        kw["signal_direction"] = "sideways"
        with pytest.raises(ValidationError):
            BehavioralSignal(**kw)

    def test_metadata_defaults_empty_dict(self):
        kw = self._valid_kwargs()
        del kw["metadata"]
        s = BehavioralSignal(**kw)
        assert s.metadata == {}

    def test_unique_signal_id_generated(self):
        a = BehavioralSignal(**self._valid_kwargs())
        b = BehavioralSignal(**self._valid_kwargs())
        assert a.signal_id != b.signal_id


class TestAssetHistory:
    def test_empty_latest_is_none(self):
        h = AssetHistory(symbol="X", asset_id="x", bars=[])
        assert h.latest is None

    def test_latest_returns_last_bar(self):
        bars = [_bar(1), _bar(2, close=101), _bar(3, close=102)]
        h = AssetHistory(symbol="X", asset_id="x", bars=bars)
        assert h.latest.close == 102

    def test_closes_slice(self):
        bars = [_bar(i) for i in range(1, 6)]
        h = AssetHistory(symbol="X", asset_id="x", bars=bars)
        assert len(h.closes(3)) == 3
        assert h.closes() == [b.close for b in bars]


class TestMarketContext:
    def test_defaults(self):
        ctx = MarketContext(as_of_date=dt.date(2026, 4, 21))
        assert ctx.pct_above_ma50 is None
        assert ctx.universe_size == 0


class TestHelpers:
    def test_safe_mean_empty_zero(self):
        assert safe_mean([]) == 0.0

    def test_safe_std_short_zero(self):
        assert safe_std([]) == 0.0
        assert safe_std([1.0]) == 0.0

    def test_safe_std_positive(self):
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert safe_std(vals) > 0

    def test_clip01_bounds(self):
        assert clip01(-0.5) == 0.0
        assert clip01(1.5) == 1.0
        assert clip01(0.3) == 0.3

    def test_daily_returns_length(self):
        closes = [100.0, 101.0, 103.0, 102.0]
        rets = daily_returns(closes)
        assert len(rets) == 3
        assert rets[0] == pytest.approx(0.01)

    def test_daily_returns_handles_zero(self):
        closes = [100.0, 0.0, 101.0]
        rets = daily_returns(closes)
        # Zero prev price is skipped
        assert len(rets) == 1
