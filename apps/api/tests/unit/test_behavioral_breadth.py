"""Unit tests — breadth_v1."""

from __future__ import annotations

import datetime as dt

from apps.api.src.domain.behavioral.base import (
    AssetHistory,
    Bar,
    MarketContext,
)
from apps.api.src.domain.behavioral.breadth import (
    BREADTH_BEAR_THRESHOLD,
    BREADTH_BULL_THRESHOLD,
    SMA_WINDOW,
    BreadthV1,
)


def _build(closes: list[float], start=dt.date(2025, 11, 1)) -> AssetHistory:
    bars = []
    d = start
    for c in closes:
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        bars.append(Bar(ts=d, open=c, high=c, low=c, close=c, volume=1e6))
        d += dt.timedelta(days=1)
    return AssetHistory(symbol="X", asset_id="x", bars=bars)


class TestBreadth:
    def test_none_breadth_no_signal(self):
        asset = _build([100.0 + i * 0.5 for i in range(60)])
        ctx = MarketContext(
            as_of_date=asset.bars[-1].ts, pct_above_ma50=None, universe_size=50,
        )
        out = BreadthV1().generate(asset.bars[-1].ts, [asset], ctx)
        assert out == []

    def test_ambiguous_breadth_no_signal(self):
        asset = _build([100.0 + i * 0.5 for i in range(60)])
        ctx = MarketContext(
            as_of_date=asset.bars[-1].ts, pct_above_ma50=0.50, universe_size=50,
        )
        out = BreadthV1().generate(asset.bars[-1].ts, [asset], ctx)
        assert out == []

    def test_bullish_breadth_above_own_ma_long_signal(self):
        # Rising trend → last close above its own 50-SMA
        asset = _build([100.0 + i * 0.5 for i in range(60)])
        ctx = MarketContext(
            as_of_date=asset.bars[-1].ts,
            pct_above_ma50=0.75,   # > BREADTH_BULL_THRESHOLD
            universe_size=50,
        )
        out = BreadthV1().generate(asset.bars[-1].ts, [asset], ctx)
        assert len(out) == 1
        s = out[0]
        assert s.signal_direction == "long"
        assert s.strategy_id == "breadth_v1"
        assert s.metadata["breadth_pct_above_ma50"] == 0.75
        assert s.metadata["asset_close"] > s.metadata["asset_sma50"]

    def test_bearish_breadth_below_own_ma_short_signal(self):
        # Falling trend — last close below its own 50-SMA
        asset = _build([200.0 - i * 0.5 for i in range(60)])
        ctx = MarketContext(
            as_of_date=asset.bars[-1].ts,
            pct_above_ma50=0.25,   # < BREADTH_BEAR_THRESHOLD
            universe_size=50,
        )
        out = BreadthV1().generate(asset.bars[-1].ts, [asset], ctx)
        assert len(out) == 1
        assert out[0].signal_direction == "short"

    def test_bullish_breadth_but_stock_below_ma_no_signal(self):
        """Breadth disagrees with individual — no confirmation → skip."""
        asset = _build([200.0 - i * 0.5 for i in range(60)])
        ctx = MarketContext(
            as_of_date=asset.bars[-1].ts,
            pct_above_ma50=0.80,
            universe_size=50,
        )
        out = BreadthV1().generate(asset.bars[-1].ts, [asset], ctx)
        assert out == []

    def test_bearish_breadth_but_stock_above_ma_no_signal(self):
        asset = _build([100.0 + i * 0.5 for i in range(60)])
        ctx = MarketContext(
            as_of_date=asset.bars[-1].ts,
            pct_above_ma50=0.20,
            universe_size=50,
        )
        out = BreadthV1().generate(asset.bars[-1].ts, [asset], ctx)
        assert out == []

    def test_insufficient_history(self):
        asset = _build([100.0] * 30)
        ctx = MarketContext(
            as_of_date=asset.bars[-1].ts, pct_above_ma50=0.8, universe_size=50,
        )
        out = BreadthV1().generate(asset.bars[-1].ts, [asset], ctx)
        assert out == []

    def test_output_bounds(self):
        asset = _build([100.0 + i * 0.5 for i in range(60)])
        ctx = MarketContext(
            as_of_date=asset.bars[-1].ts, pct_above_ma50=0.90, universe_size=50,
        )
        out = BreadthV1().generate(asset.bars[-1].ts, [asset], ctx)
        assert len(out) == 1
        s = out[0]
        assert 0 <= s.signal_strength <= 1
        assert 0 <= s.confidence <= 1

    def test_sma_window_documented(self):
        assert SMA_WINDOW == 50

    def test_thresholds_documented(self):
        assert BREADTH_BULL_THRESHOLD > 0.5
        assert BREADTH_BEAR_THRESHOLD < 0.5
