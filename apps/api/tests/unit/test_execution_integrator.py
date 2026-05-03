"""Unit tests — execution integrator (end-to-end sizing + regime)."""

from __future__ import annotations

import pytest

from apps.api.src.domain.execution.integrator import (
    FinalAction,
    PrimarySignal,
    execute,
    execute_batch,
)


def _trend_prices(n: int = 80) -> list[float]:
    return [100.0 + 0.15 * i for i in range(n)]


def _flat_prices(n: int = 80) -> list[float]:
    return [100.0] * n


def _chaotic_tail(n_calm: int = 80, n_chaotic: int = 25) -> list[float]:
    out = [100.0 + 0.01 * (i % 3) for i in range(n_calm)]
    last = out[-1]
    for i in range(n_chaotic):
        last = last * (1.05 if i % 2 == 0 else 0.95)
        out.append(last)
    return out


class TestExecute:
    def test_output_shape(self):
        primary = PrimarySignal("AAPL", 0.8, 0.7, 0.02)
        action = execute(primary, _trend_prices())
        assert isinstance(action, FinalAction)
        assert action.symbol == "AAPL"
        assert 0 <= action.final_size <= 1.0

    def test_final_size_is_raw_times_multiplier(self):
        primary = PrimarySignal("X", 0.8, 0.8, 0.02)
        action = execute(primary, _trend_prices())
        expected = action.sizing.raw_size * action.regime.multiplier
        assert abs(action.final_size - min(expected, 1.0)) < 1e-9

    def test_high_vol_regime_shrinks_size(self):
        primary = PrimarySignal("X", 0.9, 0.9, 0.02)
        a_trend = execute(primary, _trend_prices())
        a_chaos = execute(primary, _chaotic_tail())
        # trend_up -> full; high_vol -> 0.25 -> chaos smaller
        assert a_chaos.final_size < a_trend.final_size

    def test_kelly_method_selectable(self):
        primary = PrimarySignal("X", 0.8, 0.8, 0.02)
        a_norm = execute(primary, _trend_prices(), method="normalized")
        a_kelly = execute(primary, _trend_prices(), method="kelly")
        assert a_norm.sizing.method == "normalized"
        assert a_kelly.sizing.method == "kelly"

    def test_invalid_method_raises(self):
        primary = PrimarySignal("X", 0.8, 0.8, 0.02)
        with pytest.raises(ValueError):
            execute(primary, _trend_prices(), method="bogus")

    def test_zero_composite_zero_final_size(self):
        primary = PrimarySignal("X", 0.0, 0.8, 0.02)
        action = execute(primary, _trend_prices())
        assert action.final_size == 0.0

    def test_insufficient_market_data_defaults_sideways(self):
        primary = PrimarySignal("X", 0.8, 0.8, 0.02)
        action = execute(primary, [100.0, 101.0])
        # sideways multiplier = 0.5
        assert action.regime.regime == "sideways"
        assert action.regime.multiplier == 0.5

    def test_respects_custom_max_size(self):
        primary = PrimarySignal("X", 1.0, 1.0, 0.005)  # max conviction, low vol
        action = execute(primary, _trend_prices(), max_size=0.3)
        assert action.final_size <= 0.3 + 1e-9

    def test_final_size_never_exceeds_max(self):
        primary = PrimarySignal("X", 1.0, 1.0, 1e-6)
        action = execute(primary, _trend_prices())
        assert action.final_size <= 1.0 + 1e-9


class TestExecuteBatch:
    def test_empty_input_returns_empty(self):
        out = execute_batch([], _trend_prices())
        assert out == []

    def test_batch_uses_same_regime(self):
        primaries = [
            PrimarySignal("A", 0.8, 0.8, 0.02),
            PrimarySignal("B", 0.7, 0.9, 0.03),
            PrimarySignal("C", 0.9, 0.6, 0.01),
        ]
        out = execute_batch(primaries, _trend_prices())
        # All candidates classified under same regime
        regimes = {a.regime.regime for a in out}
        assert len(regimes) == 1

    def test_batch_sizing_differs_per_candidate(self):
        primaries = [
            PrimarySignal("A", 0.8, 0.8, 0.02),
            PrimarySignal("B", 0.3, 0.9, 0.03),    # lower composite
            PrimarySignal("C", 0.9, 0.9, 0.02),    # higher composite
        ]
        out = execute_batch(primaries, _trend_prices())
        sizes = {a.symbol: a.final_size for a in out}
        assert sizes["B"] < sizes["A"] < sizes["C"]

    def test_batch_preserves_order(self):
        primaries = [PrimarySignal(f"S{i}", 0.5 + i * 0.1, 0.8, 0.02) for i in range(5)]
        out = execute_batch(primaries, _trend_prices())
        assert [a.symbol for a in out] == [p.symbol for p in primaries]

    def test_batch_kelly_method(self):
        primaries = [PrimarySignal("X", 0.9, 0.9, 0.02)]
        out = execute_batch(primaries, _trend_prices(), method="kelly")
        assert out[0].sizing.method == "kelly"
