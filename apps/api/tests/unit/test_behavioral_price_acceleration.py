"""Unit tests — price_acceleration_v1."""

from __future__ import annotations

import datetime as dt

from apps.api.src.domain.behavioral.base import (
    AssetHistory,
    Bar,
    MarketContext,
)
from apps.api.src.domain.behavioral.price_acceleration import (
    Z_SCORE_MIN,
    PriceAccelerationV1,
)


def _build(closes: list[float], start=dt.date(2026, 1, 1)) -> AssetHistory:
    bars = []
    d = start
    for c in closes:
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        bars.append(Bar(ts=d, open=c, high=c, low=c, close=c, volume=1e6))
        d += dt.timedelta(days=1)
    return AssetHistory(symbol="X", asset_id="x", bars=bars)


def _ctx(date: dt.date) -> MarketContext:
    return MarketContext(as_of_date=date, universe_size=1)


class TestPriceAcceleration:
    def test_flat_series_no_signal(self):
        closes = [100.0] * 25
        asset = _build(closes)
        out = PriceAccelerationV1().generate(
            asset.bars[-1].ts, [asset], _ctx(asset.bars[-1].ts),
        )
        assert out == []

    def test_big_up_move_emits_long(self):
        """Small daily vol -> large z-score on 5% jump."""
        # Prior 20 days: oscillate +/-0.1% → low vol
        closes = [100.0 + 0.1 * ((-1) ** i) for i in range(20)]
        closes.append(closes[-1] * 1.05)  # +5% jump on bar 21
        asset = _build(closes)
        out = PriceAccelerationV1().generate(
            asset.bars[-1].ts, [asset], _ctx(asset.bars[-1].ts),
        )
        assert len(out) == 1
        s = out[0]
        assert s.signal_direction == "long"
        assert abs(s.metadata["return_zscore"]) >= Z_SCORE_MIN
        assert s.strategy_id == "price_acceleration_v1"

    def test_big_down_move_emits_short(self):
        closes = [100.0 + 0.1 * ((-1) ** i) for i in range(20)]
        closes.append(closes[-1] * 0.95)    # -5% down
        asset = _build(closes)
        out = PriceAccelerationV1().generate(
            asset.bars[-1].ts, [asset], _ctx(asset.bars[-1].ts),
        )
        assert len(out) == 1
        assert out[0].signal_direction == "short"

    def test_z_below_threshold_suppressed(self):
        # High vol baseline → even sizeable move has low z
        closes = [100.0 * (1.0 + 0.03 * ((-1) ** i)) for i in range(20)]
        closes.append(closes[-1] * 1.01)    # tiny move vs high vol
        asset = _build(closes)
        out = PriceAccelerationV1().generate(
            asset.bars[-1].ts, [asset], _ctx(asset.bars[-1].ts),
        )
        assert out == []

    def test_insufficient_history(self):
        closes = [100.0, 101.0]
        asset = _build(closes)
        out = PriceAccelerationV1().generate(
            asset.bars[-1].ts, [asset], _ctx(asset.bars[-1].ts),
        )
        assert out == []

    def test_empty_universe(self):
        out = PriceAccelerationV1().generate(
            dt.date(2026, 4, 21), [], _ctx(dt.date(2026, 4, 21)),
        )
        assert out == []

    def test_output_within_unit_interval(self):
        closes = [100.0 + 0.1 * ((-1) ** i) for i in range(20)]
        closes.append(closes[-1] * 1.10)    # huge move → extreme z
        asset = _build(closes)
        out = PriceAccelerationV1().generate(
            asset.bars[-1].ts, [asset], _ctx(asset.bars[-1].ts),
        )
        assert len(out) == 1
        s = out[0]
        assert 0 <= s.signal_strength <= 1
        assert 0 <= s.confidence <= 1

    def test_metadata_contains_zscore(self):
        closes = [100.0 + 0.1 * ((-1) ** i) for i in range(20)]
        closes.append(closes[-1] * 1.04)
        asset = _build(closes)
        out = PriceAccelerationV1().generate(
            asset.bars[-1].ts, [asset], _ctx(asset.bars[-1].ts),
        )
        assert len(out) == 1
        assert "return_zscore" in out[0].metadata
        assert "today_return_pct" in out[0].metadata
        assert "daily_vol_20d" in out[0].metadata
