"""Unit tests — behavioral integrator."""

from __future__ import annotations

import datetime as dt

from apps.api.src.domain.behavioral.base import (
    AssetHistory,
    Bar,
    BehavioralSignal,
    BehavioralSignalProvider,
    MarketContext,
)
from apps.api.src.domain.behavioral.integrator import (
    DEFAULT_PROVIDERS,
    compute_breadth_pct_above_ma50,
    generate_behavioral_signals,
)


def _build(closes: list[float], volumes: list[float] | None = None,
           symbol: str = "X", start: dt.date = dt.date(2025, 10, 1)) -> AssetHistory:
    bars = []
    d = start
    for i, c in enumerate(closes):
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        v = volumes[i] if volumes else 1e6
        bars.append(Bar(ts=d, open=c, high=c, low=c, close=c, volume=v))
        d += dt.timedelta(days=1)
    return AssetHistory(symbol=symbol, asset_id=symbol.lower(), bars=bars)


class TestIntegrator:
    def test_default_providers_has_three(self):
        assert len(DEFAULT_PROVIDERS) == 3
        strategies = {p.strategy_id for p in DEFAULT_PROVIDERS}
        assert strategies == {
            "volume_anomaly_v1", "price_acceleration_v1", "breadth_v1",
        }

    def test_all_signals_are_behavioral_source_type(self):
        closes = [100.0 + i * 0.5 for i in range(60)]
        closes.append(closes[-1] * 1.05)
        volumes = [1e6] * 60 + [5e6]
        assets = [
            _build(closes, volumes, symbol=f"S{i}", start=dt.date(2025, 10, 1))
            for i in range(25)
        ]
        breadth = compute_breadth_pct_above_ma50(assets)
        ctx = MarketContext(
            as_of_date=assets[0].bars[-1].ts, pct_above_ma50=breadth,
            universe_size=len(assets),
        )
        sigs = generate_behavioral_signals(assets[0].bars[-1].ts, assets, ctx)
        assert len(sigs) > 0
        for s in sigs:
            assert s.source_type == "behavioral"
            assert s.strategy_id in {
                "volume_anomaly_v1", "price_acceleration_v1", "breadth_v1",
            }

    def test_empty_universe_returns_empty(self):
        ctx = MarketContext(as_of_date=dt.date(2026, 4, 21))
        sigs = generate_behavioral_signals(ctx.as_of_date, [], ctx)
        assert sigs == []

    def test_provider_exception_does_not_crash(self):
        class Boom(BehavioralSignalProvider):
            strategy_id = "boom_v1"

            def generate(self, as_of_date, universe, market_context):
                raise RuntimeError("intentional")

        class Good(BehavioralSignalProvider):
            strategy_id = "good_v1"

            def generate(self, as_of_date, universe, market_context):
                return [BehavioralSignal(
                    symbol="AAA",
                    timestamp=dt.datetime.combine(
                        as_of_date, dt.time(22, 0), dt.timezone.utc,
                    ),
                    strategy_id=self.strategy_id,
                    signal_direction="long",
                    signal_strength=0.5,
                    confidence=0.5,
                    explanation="fine",
                )]

        ctx = MarketContext(as_of_date=dt.date(2026, 4, 21))
        out = generate_behavioral_signals(
            ctx.as_of_date, [], ctx,
            providers=(Boom(), Good()),
        )
        assert len(out) == 1
        assert out[0].strategy_id == "good_v1"

    def test_merged_list_preserves_all_signals(self):
        # Prior 60 bars: rising trend with ±0.3 noise → non-zero daily vol
        # Last bar: big +6% jump + 5x volume → triggers all three providers.
        prior = [
            100.0 + i * 0.5 + (0.3 if i % 2 == 0 else -0.3)
            for i in range(60)
        ]
        closes_template = prior + [prior[-1] * 1.06]
        volumes = [1e6] * 60 + [5e6]
        assets_up = [
            _build(
                closes_template, volumes, symbol=f"U{i}",
                start=dt.date(2025, 10, 1),
            )
            for i in range(25)
        ]
        breadth = compute_breadth_pct_above_ma50(assets_up)
        ctx = MarketContext(
            as_of_date=assets_up[0].bars[-1].ts,
            pct_above_ma50=breadth,
            universe_size=len(assets_up),
        )
        sigs = generate_behavioral_signals(assets_up[0].bars[-1].ts, assets_up, ctx)
        grouped: dict[str, int] = {}
        for s in sigs:
            grouped[s.strategy_id] = grouped.get(s.strategy_id, 0) + 1
        # All three providers should have contributed
        assert "volume_anomaly_v1" in grouped
        assert "price_acceleration_v1" in grouped
        assert "breadth_v1" in grouped


class TestComputeBreadth:
    def test_small_universe_returns_none(self):
        assets = [_build([100.0 + i * 0.5 for i in range(60)], symbol=f"X{i}") for i in range(10)]
        assert compute_breadth_pct_above_ma50(assets) is None

    def test_all_above_ma_returns_high(self):
        assets = [
            _build([100.0 + i * 0.5 for i in range(60)], symbol=f"U{i}")
            for i in range(25)
        ]
        b = compute_breadth_pct_above_ma50(assets)
        assert b is not None
        assert b == 1.0

    def test_all_below_ma_returns_low(self):
        assets = [
            _build([200.0 - i * 0.5 for i in range(60)], symbol=f"D{i}")
            for i in range(25)
        ]
        b = compute_breadth_pct_above_ma50(assets)
        assert b is not None
        # All below own SMA → breadth ~ 0
        assert b == 0.0

    def test_mixed_universe_roughly_correct(self):
        up = [_build([100.0 + i * 0.5 for i in range(60)], symbol=f"U{i}") for i in range(15)]
        down = [_build([200.0 - i * 0.5 for i in range(60)], symbol=f"D{i}") for i in range(10)]
        b = compute_breadth_pct_above_ma50(up + down)
        assert b is not None
        # 15 up / 25 total = 0.60
        assert 0.55 <= b <= 0.65
