"""Unit tests — volume_anomaly_v1."""

from __future__ import annotations

import datetime as dt

from apps.api.src.domain.behavioral.base import (
    AssetHistory,
    Bar,
    MarketContext,
)
from apps.api.src.domain.behavioral.volume_anomaly import (
    LOOKBACK_BARS,
    VOLUME_RATIO_MIN,
    VolumeAnomalyV1,
)


def _build(
    volumes: list[float], closes: list[float], start=dt.date(2026, 1, 1),
) -> AssetHistory:
    bars = []
    d = start
    for v, c in zip(volumes, closes):
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        bars.append(Bar(ts=d, open=c, high=c, low=c, close=c, volume=v))
        d += dt.timedelta(days=1)
    return AssetHistory(symbol="X", asset_id="x", bars=bars)


def _ctx(date: dt.date) -> MarketContext:
    return MarketContext(as_of_date=date, pct_above_ma50=None, universe_size=1)


class TestVolumeAnomaly:
    def test_flat_volume_no_signal(self):
        closes = [100.0] * 25
        volumes = [1e6] * 25
        asset = _build(volumes, closes)
        out = VolumeAnomalyV1().generate(
            asset.bars[-1].ts, [asset], _ctx(asset.bars[-1].ts),
        )
        assert out == []

    def test_volume_spike_with_up_move_emits_long(self):
        closes = [100.0] * 20 + [101.5]        # 1.5% up on bar 21
        volumes = [1e6] * 20 + [5e6]           # 5x volume spike
        asset = _build(volumes, closes)
        out = VolumeAnomalyV1().generate(
            asset.bars[-1].ts, [asset], _ctx(asset.bars[-1].ts),
        )
        assert len(out) == 1
        s = out[0]
        assert s.signal_direction == "long"
        assert s.strategy_id == "volume_anomaly_v1"
        assert s.source_type == "behavioral"
        assert 0 <= s.signal_strength <= 1
        assert 0 <= s.confidence <= 1
        assert "volume_ratio" in s.metadata
        assert s.metadata["volume_ratio"] >= VOLUME_RATIO_MIN

    def test_volume_spike_with_down_move_emits_short(self):
        closes = [100.0] * 20 + [98.0]         # -2% down on bar 21
        volumes = [1e6] * 20 + [5e6]
        asset = _build(volumes, closes)
        out = VolumeAnomalyV1().generate(
            asset.bars[-1].ts, [asset], _ctx(asset.bars[-1].ts),
        )
        assert len(out) == 1
        assert out[0].signal_direction == "short"

    def test_high_volume_but_flat_return_filtered(self):
        closes = [100.0] * 20 + [100.01]       # 0.01% — below MIN_ABS_RETURN
        volumes = [1e6] * 20 + [5e6]
        asset = _build(volumes, closes)
        out = VolumeAnomalyV1().generate(
            asset.bars[-1].ts, [asset], _ctx(asset.bars[-1].ts),
        )
        assert out == []

    def test_insufficient_history_yields_empty(self):
        closes = [100.0, 101.0, 102.0]
        volumes = [1e6] * 3
        asset = _build(volumes, closes)
        out = VolumeAnomalyV1().generate(
            asset.bars[-1].ts, [asset], _ctx(asset.bars[-1].ts),
        )
        assert out == []

    def test_empty_universe(self):
        out = VolumeAnomalyV1().generate(
            dt.date(2026, 4, 21), [], _ctx(dt.date(2026, 4, 21)),
        )
        assert out == []

    def test_explanation_and_metadata_present(self):
        closes = [100.0] * 20 + [102.0]
        volumes = [1e6] * 20 + [4e6]
        asset = _build(volumes, closes)
        out = VolumeAnomalyV1().generate(
            asset.bars[-1].ts, [asset], _ctx(asset.bars[-1].ts),
        )
        assert len(out) == 1
        s = out[0]
        assert "Volume" in s.explanation
        assert "thresholds" in s.metadata
        assert "lookback_bars" in s.metadata
        assert s.metadata["lookback_bars"] == LOOKBACK_BARS

    def test_zero_volume_history_skipped(self):
        closes = [100.0] * 20 + [105.0]
        volumes = [0.0] * 20 + [1e6]
        asset = _build(volumes, closes)
        out = VolumeAnomalyV1().generate(
            asset.bars[-1].ts, [asset], _ctx(asset.bars[-1].ts),
        )
        assert out == []
