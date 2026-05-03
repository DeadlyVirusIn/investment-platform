"""Unit tests — cost model + cost-aware metrics."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from apps.api.src.domain.evaluation.costs import (
    DEFAULT_SCENARIOS,
    HIGH_COST,
    LOW_COST,
    REALISTIC_COST,
    ZERO_COST,
    CostAwareMetrics,
    CostScenario,
    compute_cost_aware_metrics,
    compute_cost_deduction_return,
    compute_position_delta,
    compute_scenarios,
    compute_scenarios_by_regime,
    net_returns_for_strategy,
)


# ---------------------------------------------------------------------------
# Mock EvaluationDay (avoid heavy construction)
# ---------------------------------------------------------------------------


@dataclass
class MockEval:
    date: dt.date
    regime: object                          # has .regime attr
    n_model: int = 0
    n_behavioral_long: int = 0
    n_behavioral_short_skipped: int = 0
    n_combined: int = 0
    n_regime_routed: int = 0
    routing_rule: str = ""
    routing_exposure_multiplier: float = 1.0
    daily_return: dict = field(default_factory=dict)
    avg_position_size: dict = field(default_factory=dict)
    total_exposure: dict = field(default_factory=dict)
    behavioral_provider_counts: dict = field(default_factory=dict)
    behavioral_symbol_providers: dict = field(default_factory=dict)
    sizes_by_symbol: dict = field(default_factory=dict)


def _day(
    date: dt.date, regime_label: str = "trend_up",
    strat_sizes: dict | None = None,
    strat_returns: dict | None = None,
    n_model: int = 0, n_behav: int = 0, n_combined: int = 0, n_routed: int = 0,
) -> MockEval:
    strat_sizes = strat_sizes or {}
    strat_returns = strat_returns or {}
    total_exp = {s: sum(d.values()) for s, d in strat_sizes.items()}
    avg_size = {s: (sum(d.values()) / max(len(d), 1)) for s, d in strat_sizes.items()}
    return MockEval(
        date=date,
        regime=SimpleNamespace(regime=regime_label),
        n_model=n_model, n_behavioral_long=n_behav,
        n_combined=n_combined, n_regime_routed=n_routed,
        daily_return=strat_returns,
        avg_position_size=avg_size,
        total_exposure=total_exp,
        sizes_by_symbol=strat_sizes,
    )


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


class TestScenarios:
    def test_zero_cost_rate(self):
        assert ZERO_COST.cost_rate == 0.0
        assert ZERO_COST.round_trip_bps == 0.0

    def test_low_cost_round_trip_5_bps(self):
        assert LOW_COST.round_trip_bps == 5.0
        assert LOW_COST.cost_rate == pytest.approx(0.0005)

    def test_realistic_cost_round_trip_10_bps(self):
        assert REALISTIC_COST.round_trip_bps == 10.0
        assert REALISTIC_COST.cost_rate == pytest.approx(0.001)

    def test_high_cost_round_trip_20_bps(self):
        assert HIGH_COST.round_trip_bps == 20.0

    def test_default_scenarios_count(self):
        assert len(DEFAULT_SCENARIOS) == 4

    def test_custom_scenario(self):
        s = CostScenario("custom", 3.0, 7.0)
        assert s.round_trip_bps == 10.0
        assert s.cost_rate_one_way == pytest.approx(0.0005)


# ---------------------------------------------------------------------------
# position_delta
# ---------------------------------------------------------------------------


class TestPositionDelta:
    def test_empty_to_new_position(self):
        """Opening a 0.5 position counts as 0.5 delta."""
        assert compute_position_delta({"A": 0.5}, {}) == 0.5

    def test_full_close(self):
        assert compute_position_delta({}, {"A": 0.3}) == 0.3

    def test_hold_unchanged_zero_delta(self):
        assert compute_position_delta({"A": 0.5}, {"A": 0.5}) == 0.0

    def test_partial_change(self):
        assert compute_position_delta({"A": 0.8}, {"A": 0.5}) == pytest.approx(0.3)

    def test_full_swap(self):
        """Swap A -> B: close 0.5 of A (delta 0.5) + open 0.5 of B (delta 0.5) = 1.0."""
        delta = compute_position_delta({"B": 0.5}, {"A": 0.5})
        assert delta == 1.0

    def test_both_empty(self):
        assert compute_position_delta({}, {}) == 0.0


# ---------------------------------------------------------------------------
# Zero-cost path preserves returns exactly
# ---------------------------------------------------------------------------


class TestZeroCostPath:
    def test_zero_scenario_net_equals_gross(self):
        days = [
            _day(dt.date(2026, 1, 5), strat_sizes={"s": {"A": 0.3}},
                 strat_returns={"s": 0.002}),
            _day(dt.date(2026, 1, 6), strat_sizes={"s": {"A": 0.3, "B": 0.2}},
                 strat_returns={"s": -0.001}),
        ]
        rets = net_returns_for_strategy(days, "s", ZERO_COST)
        assert rets == [0.002, -0.001]

    def test_cost_aware_metrics_zero_cost_no_degradation(self):
        days = [
            _day(dt.date(2026, 1, i + 5), strat_sizes={"s": {"A": 0.3}},
                 strat_returns={"s": 0.001},
                 n_model=1, n_combined=1, n_routed=1)
            for i in range(10)
        ]
        m = compute_cost_aware_metrics(days, "s", ZERO_COST)
        # Zero cost path should yield same cumulative as raw compounding
        expected = (1.001 ** 10) - 1.0
        assert m.cumulative_return == pytest.approx(expected, rel=1e-4)


# ---------------------------------------------------------------------------
# Positive costs reduce returns monotonically
# ---------------------------------------------------------------------------


class TestPositiveCostsReduceReturns:
    def _build(self, n_days: int = 20):
        # Full replacement every day -> maximal turnover. Use varying
        # returns so zero-cost stdev > 0 (else Sharpe is degenerate 0).
        days = []
        for i in range(n_days):
            today_sym = f"S{i}"
            # Alternate small positive / negative to ensure stdev > 0
            gross = 0.003 if i % 2 == 0 else 0.001
            days.append(_day(
                dt.date(2026, 1, i + 1),
                strat_sizes={"s": {today_sym: 0.5}},
                strat_returns={"s": gross},
                n_model=1, n_combined=1, n_routed=1,
            ))
        return days

    def test_higher_cost_lower_cumulative(self):
        days = self._build(20)
        c_zero = compute_cost_aware_metrics(days, "s", ZERO_COST).cumulative_return
        c_low = compute_cost_aware_metrics(days, "s", LOW_COST).cumulative_return
        c_real = compute_cost_aware_metrics(days, "s", REALISTIC_COST).cumulative_return
        c_high = compute_cost_aware_metrics(days, "s", HIGH_COST).cumulative_return
        assert c_zero > c_low > c_real > c_high

    def test_higher_cost_lower_sharpe(self):
        days = self._build(20)
        s_zero = compute_cost_aware_metrics(days, "s", ZERO_COST).sharpe
        s_low = compute_cost_aware_metrics(days, "s", LOW_COST).sharpe
        s_real = compute_cost_aware_metrics(days, "s", REALISTIC_COST).sharpe
        # Sharpe should decline (or stay equal) as costs rise
        assert s_zero >= s_low >= s_real

    def test_delta_cumulative_is_negative_for_positive_cost(self):
        days = self._build(15)
        results = compute_scenarios(days, ("s",), DEFAULT_SCENARIOS)
        assert results[("s", "zero_cost")].delta_cumulative_return == 0.0
        assert results[("s", "low_cost")].delta_cumulative_return < 0
        assert results[("s", "realistic_cost")].delta_cumulative_return < 0
        assert results[("s", "high_cost")].delta_cumulative_return < 0


# ---------------------------------------------------------------------------
# High turnover penalized more
# ---------------------------------------------------------------------------


class TestHighTurnoverPenalty:
    def test_replacing_basket_costs_more_than_holding(self):
        # Strategy A: holds 0.5 in symbol X every day
        # Strategy B: swaps symbol every day (full replacement)
        n = 10
        hold_days = [_day(
            dt.date(2026, 1, i + 1),
            strat_sizes={"A": {"X": 0.5}, "B": {f"S{i}": 0.5}},
            strat_returns={"A": 0.001, "B": 0.001},
            n_model=1,
        ) for i in range(n)]
        a_real = compute_cost_aware_metrics(hold_days, "A", REALISTIC_COST)
        b_real = compute_cost_aware_metrics(hold_days, "B", REALISTIC_COST)
        # B should have much lower net cumulative due to turnover
        assert b_real.cumulative_return < a_real.cumulative_return

    def test_cost_deduction_scales_with_delta(self):
        d1 = compute_cost_deduction_return(0.5, 1.0, REALISTIC_COST)
        d2 = compute_cost_deduction_return(1.0, 1.0, REALISTIC_COST)
        assert d2 == 2 * d1

    def test_zero_exposure_returns_zero_deduction(self):
        assert compute_cost_deduction_return(0.5, 0.0, REALISTIC_COST) == 0.0


# ---------------------------------------------------------------------------
# Cost-aware metrics container
# ---------------------------------------------------------------------------


class TestCostAwareMetricsContainer:
    def test_cost_aware_metrics_fields(self):
        days = [
            _day(dt.date(2026, 1, i + 1),
                 strat_sizes={"s": {"X": 0.5}},
                 strat_returns={"s": 0.001},
                 n_model=1, n_combined=1, n_routed=1)
            for i in range(6)
        ]
        m = compute_cost_aware_metrics(days, "s", LOW_COST)
        assert isinstance(m, CostAwareMetrics)
        assert m.strategy == "s"
        assert m.scenario == "low_cost"
        assert m.n_days == 6
        assert m.turnover >= 0.0

    def test_compute_scenarios_all_combinations(self):
        days = [
            _day(dt.date(2026, 1, i + 1),
                 strat_sizes={"a": {"X": 0.3}, "b": {"Y": 0.3}},
                 strat_returns={"a": 0.001, "b": -0.0005},
                 n_model=1, n_combined=1, n_routed=1)
            for i in range(6)
        ]
        res = compute_scenarios(days, ("a", "b"), DEFAULT_SCENARIOS)
        assert len(res) == 2 * 4
        for strat in ("a", "b"):
            for sc in DEFAULT_SCENARIOS:
                assert (strat, sc.name) in res


# ---------------------------------------------------------------------------
# Regime breakdown
# ---------------------------------------------------------------------------


class TestRegimeBreakdown:
    def test_compute_by_regime(self):
        days = []
        for i, r in enumerate(["trend_up", "trend_up", "sideways", "low_vol"]):
            days.append(_day(
                dt.date(2026, 1, i + 1),
                regime_label=r,
                strat_sizes={"s": {"X": 0.5}},
                strat_returns={"s": 0.001},
                n_model=1, n_combined=1, n_routed=1,
            ))
        res = compute_scenarios_by_regime(
            days, ("s",), REALISTIC_COST,
        )
        assert "trend_up" in res
        assert "sideways" in res
        assert "low_vol" in res
