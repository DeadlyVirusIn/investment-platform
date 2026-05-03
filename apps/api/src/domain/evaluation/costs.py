"""Transaction cost model + cost-aware metric recomputation.

MODEL (simple, explicit, turnover-driven):

    position_delta_today = sum_{sym ∈ union} | size_today[sym] − size_yest[sym] |

    cost_paid_today     = position_delta_today × cost_rate_one_way
                        = position_delta_today × (round_trip_bps / 2) / 10000

    cost_on_return_today = cost_paid_today / total_exposure_today

    net_daily_return    = gross_daily_return − cost_on_return_today

Intuition: each unit of position CHANGE (open OR close) pays the one-way
rate; a full round-trip (open + close of size 1) pays round_trip_bps / 10000
= cost_rate in return-space. Costs scale with turnover; a zero-turnover day
has zero cost; a full-replacement day (swap entire basket) pays full
round-trip × 2.

Units:
  - `commission_bps` / `slippage_bps` are basis points (1 bp = 0.01%).
  - `cost_rate` ∈ [0, ∞) = (commission_bps + slippage_bps) / 10000
  - `cost_rate_one_way` = cost_rate / 2

No tuning, no optimization. Cost model is applied after-the-fact; it
never modifies the original strategy decisions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean, pstdev

TRADING_DAYS_PER_YEAR: int = 252
EPS: float = 1e-12


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostScenario:
    """Static cost configuration.

    Total round-trip cost = commission_bps + slippage_bps. Decomposed here
    only for auditability — the math uses the sum.
    """

    name: str
    commission_bps: float
    slippage_bps: float

    @property
    def round_trip_bps(self) -> float:
        return self.commission_bps + self.slippage_bps

    @property
    def cost_rate(self) -> float:
        """Round-trip cost expressed as return fraction (e.g. 10 bps -> 0.001)."""
        return self.round_trip_bps / 10000.0

    @property
    def cost_rate_one_way(self) -> float:
        return self.cost_rate / 2.0


ZERO_COST = CostScenario("zero_cost", 0.0, 0.0)
LOW_COST = CostScenario("low_cost", 2.5, 2.5)           # 5  bps round-trip
REALISTIC_COST = CostScenario("realistic_cost", 5.0, 5.0)   # 10 bps round-trip
HIGH_COST = CostScenario("high_cost", 10.0, 10.0)           # 20 bps round-trip

DEFAULT_SCENARIOS: tuple[CostScenario, ...] = (
    ZERO_COST, LOW_COST, REALISTIC_COST, HIGH_COST,
)


# ---------------------------------------------------------------------------
# Core cost computation — pure, stateless
# ---------------------------------------------------------------------------


def compute_position_delta(
    sizes_today: dict[str, float],
    sizes_yesterday: dict[str, float],
) -> float:
    """Sum of absolute position changes across the union of symbols.

    Opening size 0.2 in a new name -> delta 0.2
    Closing size 0.1 in an old name -> delta 0.1
    Holding size 0.15 unchanged    -> delta 0.0
    Full replacement of a 1.0-notional basket -> delta 2.0
    """
    if not sizes_today and not sizes_yesterday:
        return 0.0
    syms = set(sizes_today) | set(sizes_yesterday)
    return sum(
        abs(sizes_today.get(s, 0.0) - sizes_yesterday.get(s, 0.0))
        for s in syms
    )


def compute_cost_deduction_return(
    position_delta: float,
    total_exposure_today: float,
    scenario: CostScenario,
) -> float:
    """Return the cost deduction as a return-fraction (same scale as
    daily_return). Normalizes by total exposure so the deduction is in
    per-dollar-deployed units.
    """
    if total_exposure_today <= EPS:
        return 0.0
    cost_paid = position_delta * scenario.cost_rate_one_way
    return cost_paid / total_exposure_today


def net_returns_for_strategy(
    days: list,           # list[EvaluationDay] — forward declaration to avoid cycle
    strategy: str,
    scenario: CostScenario,
) -> list[float]:
    """Recompute daily returns net of transaction costs for one strategy.

    Requires `day.sizes_by_symbol[strategy]` to be populated. If absent
    (older days), falls back to zero-turnover (no cost) for those days.
    """
    out: list[float] = []
    prev_sizes: dict[str, float] = {}
    for d in days:
        gross = d.daily_return.get(strategy, 0.0)
        sizes_today = d.sizes_by_symbol.get(strategy, {}) if hasattr(d, "sizes_by_symbol") else {}
        total_exp = d.total_exposure.get(strategy, 0.0)
        delta = compute_position_delta(sizes_today, prev_sizes)
        deduction = compute_cost_deduction_return(delta, total_exp, scenario)
        out.append(gross - deduction)
        prev_sizes = sizes_today
    return out


def position_delta_series(
    days: list, strategy: str,
) -> list[float]:
    """Per-day absolute position change (informational)."""
    out: list[float] = []
    prev: dict[str, float] = {}
    for d in days:
        today = d.sizes_by_symbol.get(strategy, {}) if hasattr(d, "sizes_by_symbol") else {}
        out.append(compute_position_delta(today, prev))
        prev = today
    return out


# ---------------------------------------------------------------------------
# Cost-aware metrics (aggregate)
# ---------------------------------------------------------------------------


@dataclass
class CostAwareMetrics:
    strategy: str
    scenario: str
    n_days: int
    n_trades_total: int
    cumulative_return: float
    sharpe: float
    max_drawdown_pct: float
    turnover: float                     # from original gross metrics
    avg_position_size: float
    delta_cumulative_return: float = 0.0   # vs zero_cost baseline
    delta_sharpe: float = 0.0              # vs zero_cost baseline


def _sharpe(daily_returns: list[float]) -> float:
    if len(daily_returns) < 5:
        return 0.0
    m = fmean(daily_returns)
    s = pstdev(daily_returns) if len(daily_returns) > 1 else 0.0
    if s == 0:
        return 0.0
    return (m / s) * math.sqrt(TRADING_DAYS_PER_YEAR)


def _cumulative(rets: list[float]) -> float:
    eq = 1.0
    for r in rets:
        eq *= 1.0 + r
    return eq - 1.0


def _max_dd(rets: list[float]) -> float:
    if not rets:
        return 0.0
    eq, peak, mdd = 1.0, 1.0, 0.0
    for r in rets:
        eq *= 1.0 + r
        peak = max(peak, eq)
        d = (eq - peak) / peak
        if d < mdd:
            mdd = d
    return mdd * 100.0


def compute_cost_aware_metrics(
    days: list, strategy: str, scenario: CostScenario,
) -> CostAwareMetrics:
    """Compute aggregate metrics under `scenario` for `strategy`."""
    rets = net_returns_for_strategy(days, strategy, scenario)
    sizes = [d.avg_position_size.get(strategy, 0.0) for d in days]
    if strategy == "model_only":
        n_trades = sum(d.n_model for d in days)
    elif strategy == "behavioral_only":
        n_trades = sum(d.n_behavioral_long for d in days)
    elif strategy == "regime_routed":
        n_trades = sum(d.n_regime_routed for d in days)
    else:
        n_trades = sum(d.n_combined for d in days)

    # Recompute turnover from position deltas (same for all scenarios)
    deltas = position_delta_series(days, strategy)
    avg_exp = fmean([d.total_exposure.get(strategy, 0.0) for d in days]) or 0.0
    turnover = (fmean(deltas) / avg_exp) if avg_exp > 0 else 0.0

    return CostAwareMetrics(
        strategy=strategy,
        scenario=scenario.name,
        n_days=len(days),
        n_trades_total=n_trades,
        cumulative_return=round(_cumulative(rets), 6),
        sharpe=round(_sharpe(rets), 4),
        max_drawdown_pct=round(_max_dd(rets), 4),
        turnover=round(turnover, 4),
        avg_position_size=round(fmean(sizes) if sizes else 0.0, 6),
    )


def compute_scenarios(
    days: list, strategies: tuple[str, ...],
    scenarios: tuple[CostScenario, ...] = DEFAULT_SCENARIOS,
) -> dict[tuple[str, str], CostAwareMetrics]:
    """Compute metrics for all (strategy, scenario) pairs.

    Fills delta_cumulative_return and delta_sharpe vs each strategy's
    zero_cost baseline.
    """
    out: dict[tuple[str, str], CostAwareMetrics] = {}
    # First pass
    for sc in scenarios:
        for strat in strategies:
            out[(strat, sc.name)] = compute_cost_aware_metrics(days, strat, sc)
    # Deltas vs zero_cost
    for strat in strategies:
        zc_key = (strat, "zero_cost")
        if zc_key not in out:
            continue
        zc = out[zc_key]
        for sc in scenarios:
            m = out[(strat, sc.name)]
            m.delta_cumulative_return = round(
                m.cumulative_return - zc.cumulative_return, 6,
            )
            m.delta_sharpe = round(m.sharpe - zc.sharpe, 4)
    return out


# ---------------------------------------------------------------------------
# Regime-sliced cost analysis
# ---------------------------------------------------------------------------


def compute_scenarios_by_regime(
    days: list,
    strategies: tuple[str, ...],
    scenario: CostScenario,
) -> dict[str, dict[str, CostAwareMetrics]]:
    """Group by regime and compute cost-aware metrics per strategy."""
    by_regime: dict[str, list] = {}
    for d in days:
        by_regime.setdefault(d.regime.regime, []).append(d)

    out: dict[str, dict[str, CostAwareMetrics]] = {}
    for regime, ds in by_regime.items():
        out[regime] = {
            s: compute_cost_aware_metrics(ds, s, scenario) for s in strategies
        }
    return out
