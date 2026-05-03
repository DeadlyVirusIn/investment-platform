"""Unit tests — Phase B2 behavioral evaluation."""

from __future__ import annotations

import datetime as dt

import pytest

from apps.api.src.domain.behavioral.base import BehavioralSignal
from apps.api.src.domain.behavioral.evaluation import (
    STRATEGIES,
    ConvergenceBucket,
    EvaluationDay,
    ProviderStats,
    aggregate_all,
    aggregate_by_regime,
    aggregate_strategy,
    analyze_providers,
    behavioral_to_primary,
    run_evaluation_day,
)
from apps.api.src.domain.execution.integrator import PrimarySignal
from apps.api.src.domain.execution.shadow import PrimaryWithReturn


def _bs(
    symbol: str, sid: str = "volume_anomaly_v1",
    direction: str = "long", strength: float = 0.6, conf: float = 0.7,
) -> BehavioralSignal:
    return BehavioralSignal(
        symbol=symbol,
        timestamp=dt.datetime(2026, 3, 1, 22, 0, tzinfo=dt.timezone.utc),
        strategy_id=sid,
        signal_direction=direction,
        signal_strength=strength,
        confidence=conf,
        explanation="test",
        metadata={},
    )


def _pwr(symbol: str, composite: float = 0.8, fwd: float = 2.0) -> PrimaryWithReturn:
    return PrimaryWithReturn(
        primary=PrimarySignal(
            symbol=symbol, composite_score=composite,
            confidence=0.8, realized_vol_20d=0.25,
        ),
        forward_return_pct=fwd,
        barrier_n_bars=20,
    )


def _trend_prices(n: int = 80) -> list[float]:
    out = [100.0]
    for _ in range(n - 1):
        out.append(out[-1] * 1.003)
    return out


# ---------------------------------------------------------------------------
# behavioral_to_primary
# ---------------------------------------------------------------------------


class TestBehavioralToPrimary:
    def test_long_signal_maps_to_primary(self):
        p = behavioral_to_primary(_bs("AAA", direction="long"), 0.25)
        assert p is not None
        assert p.symbol == "AAA"
        assert p.composite_score == pytest.approx(0.6)
        assert p.confidence == pytest.approx(0.7)
        assert p.realized_vol_20d == 0.25

    def test_short_signal_returns_none(self):
        assert behavioral_to_primary(_bs("X", direction="short"), 0.25) is None

    def test_neutral_signal_returns_none(self):
        assert behavioral_to_primary(_bs("X", direction="neutral"), 0.25) is None


# ---------------------------------------------------------------------------
# run_evaluation_day
# ---------------------------------------------------------------------------


class TestRunEvaluationDay:
    def test_counts_populate_correctly(self):
        model = [_pwr("A"), _pwr("B")]
        behav = [_bs("C", direction="long"), _bs("D", direction="short")]
        vol = {"C": 0.25, "D": 0.25}
        fwd = {"C": (1.5, 20), "D": (0.5, 20)}
        day = run_evaluation_day(
            dt.date(2026, 3, 1), model, behav, vol, fwd, _trend_prices(),
        )
        assert day.n_model == 2
        assert day.n_behavioral_long == 1       # only C (D is short)
        assert day.n_behavioral_short_skipped == 1
        assert day.n_combined == 3              # model+behav_long

    def test_all_strategies_have_daily_return(self):
        day = run_evaluation_day(
            dt.date(2026, 3, 1),
            [_pwr("A")], [_bs("B", direction="long")],
            {"B": 0.25}, {"B": (2.0, 20)}, _trend_prices(),
        )
        for s in STRATEGIES:
            assert s in day.daily_return

    def test_behavioral_skipped_if_missing_vol_or_fwd(self):
        day = run_evaluation_day(
            dt.date(2026, 3, 1),
            [], [_bs("X", direction="long")],
            vol_by_symbol={},   # missing
            forward_return_by_symbol={},   # missing
            market_prices=_trend_prices(),
        )
        assert day.n_behavioral_long == 0

    def test_provider_counts_populated(self):
        behav = [
            _bs("A", sid="volume_anomaly_v1"),
            _bs("A", sid="price_acceleration_v1"),
            _bs("B", sid="volume_anomaly_v1"),
        ]
        day = run_evaluation_day(
            dt.date(2026, 3, 1),
            [], behav,
            {"A": 0.25, "B": 0.25}, {"A": (1.0, 20), "B": (-1.0, 20)},
            _trend_prices(),
        )
        assert day.behavioral_provider_counts["volume_anomaly_v1"] == 2
        assert day.behavioral_provider_counts["price_acceleration_v1"] == 1

    def test_symbol_providers_map_populated(self):
        behav = [
            _bs("A", sid="volume_anomaly_v1"),
            _bs("A", sid="breadth_v1"),
        ]
        day = run_evaluation_day(
            dt.date(2026, 3, 1), [], behav,
            {"A": 0.25}, {"A": (2.0, 20)}, _trend_prices(),
        )
        assert day.behavioral_symbol_providers["A"] == {
            "volume_anomaly_v1", "breadth_v1",
        }

    def test_combined_is_union(self):
        """combined count = n_model + n_behavioral_long (simple concatenation)."""
        model = [_pwr("A"), _pwr("B")]
        behav = [_bs("C", direction="long")]
        day = run_evaluation_day(
            dt.date(2026, 3, 1), model, behav,
            {"C": 0.25}, {"C": (1.0, 20)}, _trend_prices(),
        )
        assert day.n_combined == day.n_model + day.n_behavioral_long

    def test_regime_routed_trend_up_drops_behavioral(self):
        """Trend-up regime → router keeps model, drops behavioral."""
        model = [_pwr("A"), _pwr("B")]
        behav = [_bs("C", direction="long")]
        day = run_evaluation_day(
            dt.date(2026, 3, 1), model, behav,
            {"C": 0.25}, {"C": (1.0, 20)}, _trend_prices(),
        )
        # _trend_prices yields a trend_up regime
        assert day.regime.regime == "trend_up"
        assert day.routing_rule == "trend_up_model_only"
        assert day.n_regime_routed == day.n_model
        assert day.routing_exposure_multiplier == 1.0

    def test_regime_routed_daily_return_equals_model_in_trend_up(self):
        model = [_pwr("A", fwd=3.0), _pwr("B", fwd=2.0)]
        day = run_evaluation_day(
            dt.date(2026, 3, 1), model, [],
            {}, {}, _trend_prices(),
        )
        assert day.daily_return["model_only"] == day.daily_return["regime_routed"]


# ---------------------------------------------------------------------------
# aggregate_strategy
# ---------------------------------------------------------------------------


class TestAggregate:
    def _series(self, n_days: int = 10) -> list[EvaluationDay]:
        days = []
        for i in range(n_days):
            d = dt.date(2026, 1, 1) + dt.timedelta(days=i)
            days.append(run_evaluation_day(
                d, [_pwr("A")], [_bs("B", direction="long")],
                {"B": 0.25}, {"B": (2.0, 20)}, _trend_prices(),
            ))
        return days

    def test_strategy_agg_has_all_fields(self):
        days = self._series(6)
        agg = aggregate_strategy(days, "model_only")
        assert agg.strategy == "model_only"
        assert agg.n_days == 6
        assert agg.n_trades_total == 6

    def test_aggregate_all_returns_three(self):
        days = self._series(10)
        all_agg = aggregate_all(days)
        assert set(all_agg.keys()) == set(STRATEGIES)

    def test_aggregate_by_regime_splits(self):
        days = self._series(10)
        # All our synthetic days should fall under the same regime
        per_regime = aggregate_by_regime(days)
        assert len(per_regime) >= 1
        # Every regime has all 3 strategies
        for regime, aggs in per_regime.items():
            assert set(aggs.keys()) == set(STRATEGIES)


# ---------------------------------------------------------------------------
# analyze_providers (convergence)
# ---------------------------------------------------------------------------


class TestAnalyzeProviders:
    def test_single_vs_multi_convergence(self):
        d1 = dt.date(2026, 1, 5)
        d2 = dt.date(2026, 1, 6)
        # A fires 2 providers on d1 → multi; B fires 1 provider on d1 → single
        # C fires 1 provider on d2 → single
        bs_by_day = {
            d1: [
                _bs("A", sid="volume_anomaly_v1"),
                _bs("A", sid="price_acceleration_v1"),
                _bs("B", sid="breadth_v1"),
            ],
            d2: [_bs("C", sid="volume_anomaly_v1")],
        }
        fwd = {
            ("A", d1): 3.0, ("B", d1): -1.0, ("C", d2): 0.5,
        }
        analysis = analyze_providers([], bs_by_day, fwd)

        # Providers
        assert set(analysis.per_provider.keys()) == {
            "volume_anomaly_v1", "price_acceleration_v1", "breadth_v1",
        }
        assert analysis.per_provider["volume_anomaly_v1"].total_signals == 2
        assert analysis.per_provider["breadth_v1"].total_signals == 1

        # Convergence
        single = analysis.convergence["single_signal"]
        multi = analysis.convergence["multi_signal"]
        assert single.n_events == 2
        assert multi.n_events == 1
        # Multi: A on d1 had fwd_ret = 3.0 -> mean 3.0, hit_rate 1.0
        assert multi.mean_forward_return_pct == pytest.approx(3.0)
        assert multi.hit_rate_positive == 1.0
        # Single: mean of [-1.0, 0.5] = -0.25, 1/2 positive → 0.5
        assert single.mean_forward_return_pct == pytest.approx(-0.25)
        assert single.hit_rate_positive == 0.5

    def test_empty_inputs_safe(self):
        analysis = analyze_providers([], {}, {})
        assert analysis.per_provider == {}
        assert analysis.convergence["single_signal"].n_events == 0
        assert analysis.convergence["multi_signal"].n_events == 0

    def test_missing_fwd_return_skips(self):
        d1 = dt.date(2026, 1, 5)
        bs_by_day = {d1: [_bs("NoFwd", sid="volume_anomaly_v1")]}
        fwd = {}   # missing
        analysis = analyze_providers([], bs_by_day, fwd)
        assert analysis.convergence["single_signal"].n_events == 0
