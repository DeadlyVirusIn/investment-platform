"""Phase B2 — behavioral signal evaluation.

Pure evaluator. Reuses existing execution framework (sizing + regime) and
existing BehavioralSignal providers. Does NOT modify either.

Three strategies compared:
  1. model_only        — existing model-family primaries (Buy-only from HistoricalLabel)
  2. behavioral_only   — long behavioral signals converted to primaries
  3. combined          — simple concatenation of the above (per Task 1 spec)

Short-direction behavioral signals are NOT executed (long-only portfolio
infra). They are still counted in provider stats and convergence analysis.
"""

from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import fmean, pstdev

from dataclasses import replace

from apps.api.src.domain.behavioral.base import BehavioralSignal
from apps.api.src.domain.execution.discipline import (
    Candidate,
    ExecutionDisciplineConfig,
    PortfolioBook,
    apply_discipline,
    daily_return_from_book,
)
from apps.api.src.domain.execution.integrator import (
    PrimarySignal,
    execute_batch,
)
from apps.api.src.domain.execution.regime import (
    RegimeSignal,
    classify_regime,
)
from apps.api.src.domain.evaluation.accounting import (
    DailyReturnLookup,
    compute_mtm_daily_return,
)
from apps.api.src.domain.execution.shadow import (
    PrimaryWithReturn,
    _compute_daily_return,
)
from apps.api.src.domain.routing.signal_router import route_signals

TRADING_DAYS_PER_YEAR: int = 252
STRATEGIES: tuple[str, ...] = (
    "model_only", "behavioral_only", "combined", "regime_routed",
)
DIRECTION_LONG = "long"


# ---------------------------------------------------------------------------
# Behavioral -> Primary bridge
# ---------------------------------------------------------------------------


def behavioral_to_primary(
    sig: BehavioralSignal, realized_vol_annualized: float,
) -> PrimarySignal | None:
    """Map a BehavioralSignal to PrimarySignal usable by execution sizers.

    Returns None for short/neutral signals (long-only infra). Composite =
    signal_strength; confidence preserved; vol annualized comes from caller.
    """
    if sig.signal_direction != DIRECTION_LONG:
        return None
    return PrimarySignal(
        symbol=sig.symbol,
        composite_score=float(sig.signal_strength),
        confidence=float(sig.confidence),
        realized_vol_20d=float(realized_vol_annualized),
    )


# ---------------------------------------------------------------------------
# Per-day evaluation result
# ---------------------------------------------------------------------------


@dataclass
class EvaluationDay:
    date: dt.date
    regime: RegimeSignal
    n_model: int
    n_behavioral_long: int
    n_behavioral_short_skipped: int
    n_combined: int
    n_regime_routed: int = 0
    routing_rule: str = ""
    routing_exposure_multiplier: float = 1.0
    # Daily returns per strategy
    daily_return: dict[str, float] = field(default_factory=dict)
    # Position bookkeeping per strategy (avg size + total exposure)
    avg_position_size: dict[str, float] = field(default_factory=dict)
    total_exposure: dict[str, float] = field(default_factory=dict)
    # Provider counts (behavioral only)
    behavioral_provider_counts: dict[str, int] = field(default_factory=dict)
    # Per-symbol provider hit map for convergence analysis: symbol -> set[strategy_id]
    behavioral_symbol_providers: dict[str, set[str]] = field(default_factory=dict)
    # Per-strategy per-symbol size map — used by cost model for position_delta
    sizes_by_symbol: dict[str, dict[str, float]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def _sharpe(daily_returns: list[float]) -> float:
    if len(daily_returns) < 5:
        return 0.0
    m = fmean(daily_returns)
    s = pstdev(daily_returns) if len(daily_returns) > 1 else 0.0
    if s == 0:
        return 0.0
    return (m / s) * math.sqrt(TRADING_DAYS_PER_YEAR)


def _cumulative(daily_returns: list[float]) -> float:
    eq = 1.0
    for r in daily_returns:
        eq *= 1.0 + r
    return eq - 1.0


def _max_dd(daily_returns: list[float]) -> float:
    if not daily_returns:
        return 0.0
    eq, peak, dd = 1.0, 1.0, 0.0
    for r in daily_returns:
        eq *= 1.0 + r
        peak = max(peak, eq)
        d = (eq - peak) / peak
        if d < dd:
            dd = d
    return dd * 100.0


def _turnover(days: list[EvaluationDay], strategy: str) -> float:
    if len(days) < 2:
        return 0.0
    exp_ = [d.total_exposure.get(strategy, 0.0) for d in days]
    delts = [abs(exp_[i] - exp_[i - 1]) for i in range(1, len(exp_))]
    avg = fmean(exp_) if exp_ else 0.0
    if avg <= 0:
        return 0.0
    return fmean(delts) / avg


@dataclass
class StrategyAgg:
    strategy: str
    n_days: int
    n_trades_total: int
    cumulative_return: float
    sharpe: float
    max_drawdown_pct: float
    turnover: float
    avg_position_size: float


def aggregate_strategy(
    days: list[EvaluationDay], strategy: str,
) -> StrategyAgg:
    rets = [d.daily_return.get(strategy, 0.0) for d in days]
    if strategy == "model_only":
        n_trades = sum(d.n_model for d in days)
    elif strategy == "behavioral_only":
        n_trades = sum(d.n_behavioral_long for d in days)
    elif strategy == "regime_routed":
        n_trades = sum(d.n_regime_routed for d in days)
    else:
        n_trades = sum(d.n_combined for d in days)
    sizes = [d.avg_position_size.get(strategy, 0.0) for d in days]
    return StrategyAgg(
        strategy=strategy,
        n_days=len(days),
        n_trades_total=n_trades,
        cumulative_return=round(_cumulative(rets), 6),
        sharpe=round(_sharpe(rets), 4),
        max_drawdown_pct=round(_max_dd(rets), 4),
        turnover=round(_turnover(days, strategy), 4),
        avg_position_size=round(fmean(sizes), 6) if sizes else 0.0,
    )


def aggregate_all(days: list[EvaluationDay]) -> dict[str, StrategyAgg]:
    return {s: aggregate_strategy(days, s) for s in STRATEGIES}


# ---------------------------------------------------------------------------
# Regime breakdown
# ---------------------------------------------------------------------------


def aggregate_by_regime(
    days: list[EvaluationDay],
) -> dict[str, dict[str, StrategyAgg]]:
    """Group days by regime and aggregate per strategy within each regime."""
    by_regime: dict[str, list[EvaluationDay]] = defaultdict(list)
    for d in days:
        by_regime[d.regime.regime].append(d)
    return {
        regime: {s: aggregate_strategy(ds, s) for s in STRATEGIES}
        for regime, ds in by_regime.items()
    }


# ---------------------------------------------------------------------------
# Provider + convergence analysis
# ---------------------------------------------------------------------------


@dataclass
class ProviderStats:
    strategy_id: str
    total_signals: int
    unique_symbol_days: int       # distinct (symbol, date) pairs
    direction_long: int
    direction_short: int


@dataclass
class ConvergenceBucket:
    bucket: str                   # "single_signal" | "multi_signal"
    n_events: int                 # count of (symbol, date) pairs in bucket
    mean_forward_return_pct: float
    hit_rate_positive: float      # fraction with forward_return > 0


@dataclass
class ProviderAnalysis:
    per_provider: dict[str, ProviderStats]
    convergence: dict[str, ConvergenceBucket]   # single / multi


def analyze_providers(
    days: list[EvaluationDay],
    behavioral_signals_by_day: dict[dt.date, list[BehavioralSignal]],
    forward_return_by_symbol_date: dict[tuple[str, dt.date], float],
) -> ProviderAnalysis:
    """Summarize behavioral providers + single vs multi-signal convergence.

    Uses the EvaluationDay.behavioral_symbol_providers map (populated in
    run_evaluation_day) + forward return lookup to split (symbol,date) pairs
    into single vs multi-signal, computing mean forward return + hit rate.
    """
    per_provider: dict[str, ProviderStats] = {}

    # Accumulate per-provider counts
    counts_total: dict[str, int] = defaultdict(int)
    symbol_day_seen: dict[str, set[tuple[str, dt.date]]] = defaultdict(set)
    long_counts: dict[str, int] = defaultdict(int)
    short_counts: dict[str, int] = defaultdict(int)

    for d, sigs in behavioral_signals_by_day.items():
        for s in sigs:
            counts_total[s.strategy_id] += 1
            symbol_day_seen[s.strategy_id].add((s.symbol, d))
            if s.signal_direction == "long":
                long_counts[s.strategy_id] += 1
            elif s.signal_direction == "short":
                short_counts[s.strategy_id] += 1

    for sid, total in counts_total.items():
        per_provider[sid] = ProviderStats(
            strategy_id=sid,
            total_signals=total,
            unique_symbol_days=len(symbol_day_seen[sid]),
            direction_long=long_counts[sid],
            direction_short=short_counts[sid],
        )

    # Convergence: per (symbol,date) count providers fired
    providers_per_symbol_day: dict[tuple[str, dt.date], set[str]] = defaultdict(set)
    for d, sigs in behavioral_signals_by_day.items():
        for s in sigs:
            providers_per_symbol_day[(s.symbol, d)].add(s.strategy_id)

    single: list[float] = []
    multi: list[float] = []
    for (sym, date), provs in providers_per_symbol_day.items():
        fwd = forward_return_by_symbol_date.get((sym, date))
        if fwd is None:
            continue
        if len(provs) == 1:
            single.append(fwd)
        else:
            multi.append(fwd)

    def _bucket(name: str, xs: list[float]) -> ConvergenceBucket:
        if not xs:
            return ConvergenceBucket(name, 0, 0.0, 0.0)
        return ConvergenceBucket(
            bucket=name,
            n_events=len(xs),
            mean_forward_return_pct=round(fmean(xs), 4),
            hit_rate_positive=round(
                sum(1 for x in xs if x > 0) / len(xs), 4,
            ),
        )

    return ProviderAnalysis(
        per_provider=per_provider,
        convergence={
            "single_signal": _bucket("single_signal", single),
            "multi_signal": _bucket("multi_signal", multi),
        },
    )


# ---------------------------------------------------------------------------
# Per-day orchestration
# ---------------------------------------------------------------------------


def run_evaluation_day(
    date: dt.date,
    model_primaries_with_returns: list[PrimaryWithReturn],
    behavioral_signals: list[BehavioralSignal],
    vol_by_symbol: dict[str, float],
    forward_return_by_symbol: dict[str, tuple[float, int]],
    market_prices: list[float],
    *,
    max_size: float = 1.0,
) -> EvaluationDay:
    """Compute all three strategies for one day.

    - `model_primaries_with_returns`: already-built PWRs for model-family signals
      (typically Buy rows from HistoricalLabel)
    - `behavioral_signals`: from generate_behavioral_signals
    - `vol_by_symbol`: annualized vol per symbol (for behavioral sizing)
    - `forward_return_by_symbol`: (forward_return_pct, n_bars) per symbol for
      attribution of behavioral PnL
    """
    regime = classify_regime(market_prices)

    # Strategy 1: model_only
    model_primaries = [p.primary for p in model_primaries_with_returns]

    # Strategy 2: behavioral_only — long signals only
    behavioral_pwrs: list[PrimaryWithReturn] = []
    short_skipped = 0
    provider_counts: dict[str, int] = defaultdict(int)
    symbol_providers: dict[str, set[str]] = defaultdict(set)
    for sig in behavioral_signals:
        provider_counts[sig.strategy_id] += 1
        symbol_providers[sig.symbol].add(sig.strategy_id)
        if sig.signal_direction != DIRECTION_LONG:
            short_skipped += 1
            continue
        vol = vol_by_symbol.get(sig.symbol)
        fwd_tuple = forward_return_by_symbol.get(sig.symbol)
        if vol is None or fwd_tuple is None:
            continue
        primary = behavioral_to_primary(sig, vol)
        if primary is None:
            continue
        fwd_ret_pct, n_bars = fwd_tuple
        behavioral_pwrs.append(PrimaryWithReturn(
            primary=primary, forward_return_pct=fwd_ret_pct, barrier_n_bars=n_bars,
        ))

    behavioral_primaries = [p.primary for p in behavioral_pwrs]

    # Strategy 3: combined — simple concatenation
    combined_pwrs = list(model_primaries_with_returns) + behavioral_pwrs
    combined_primaries = [p.primary for p in combined_pwrs]

    # Strategy 4: regime_routed — rule-based routing per Phase B3
    routed = route_signals(
        regime.regime, list(model_primaries_with_returns), behavioral_pwrs,
    )
    routed_pwrs = list(routed.model_signals) + list(routed.behavioral_signals)
    routed_primaries = [p.primary for p in routed_pwrs]

    # Run sizing
    model_acts = execute_batch(
        model_primaries, market_prices, method="normalized", max_size=max_size,
    )
    behav_acts = execute_batch(
        behavioral_primaries, market_prices, method="normalized", max_size=max_size,
    )
    comb_acts = execute_batch(
        combined_primaries, market_prices, method="normalized", max_size=max_size,
    )
    routed_acts = execute_batch(
        routed_primaries, market_prices, method="normalized", max_size=max_size,
    )

    model_sizes = [a.final_size for a in model_acts]
    behav_sizes = [a.final_size for a in behav_acts]
    comb_sizes = [a.final_size for a in comb_acts]
    # Apply routing exposure multiplier (e.g. sideways -> 0.5x)
    routed_sizes = [
        a.final_size * routed.exposure_multiplier for a in routed_acts
    ]

    model_ret = _compute_daily_return(model_primaries_with_returns, model_sizes)
    behav_ret = _compute_daily_return(behavioral_pwrs, behav_sizes)
    comb_ret = _compute_daily_return(combined_pwrs, comb_sizes)
    routed_ret = _compute_daily_return(routed_pwrs, routed_sizes)

    def _avg(xs: list[float]) -> float:
        return fmean(xs) if xs else 0.0

    def _sizes_map(pwrs, sizes):
        """symbol -> size (last write wins on duplicate symbols; aligned to
        position_delta accounting semantics)."""
        out: dict[str, float] = {}
        for pwr, sz in zip(pwrs, sizes):
            out[pwr.primary.symbol] = out.get(pwr.primary.symbol, 0.0) + sz
        return out

    return EvaluationDay(
        date=date,
        regime=regime,
        n_model=len(model_primaries_with_returns),
        n_behavioral_long=len(behavioral_pwrs),
        n_behavioral_short_skipped=short_skipped,
        n_combined=len(combined_pwrs),
        n_regime_routed=len(routed_pwrs),
        routing_rule=routed.rule_applied,
        routing_exposure_multiplier=routed.exposure_multiplier,
        daily_return={
            "model_only": model_ret,
            "behavioral_only": behav_ret,
            "combined": comb_ret,
            "regime_routed": routed_ret,
        },
        avg_position_size={
            "model_only": _avg(model_sizes),
            "behavioral_only": _avg(behav_sizes),
            "combined": _avg(comb_sizes),
            "regime_routed": _avg(routed_sizes),
        },
        total_exposure={
            "model_only": sum(model_sizes),
            "behavioral_only": sum(behav_sizes),
            "combined": sum(comb_sizes),
            "regime_routed": sum(routed_sizes),
        },
        behavioral_provider_counts=dict(provider_counts),
        behavioral_symbol_providers=dict(symbol_providers),
        sizes_by_symbol={
            "model_only": _sizes_map(model_primaries_with_returns, model_sizes),
            "behavioral_only": _sizes_map(behavioral_pwrs, behav_sizes),
            "combined": _sizes_map(combined_pwrs, comb_sizes),
            "regime_routed": _sizes_map(routed_pwrs, routed_sizes),
        },
    )


# ---------------------------------------------------------------------------
# Phase 6 — disciplined evaluator
# ---------------------------------------------------------------------------


def _pwrs_to_candidates(
    pwrs: list[PrimaryWithReturn],
    market_prices: list[float],
    max_size: float,
) -> list[Candidate]:
    """Run sizers on PWRs and convert to discipline-layer Candidates.

    Conviction = composite_score * confidence (both already ∈ [0, 1]).
    per_bar_return = amortized forward return over barrier_n_bars.
    """
    primaries = [p.primary for p in pwrs]
    acts = execute_batch(
        primaries, market_prices, method="normalized", max_size=max_size,
    )
    out: list[Candidate] = []
    for pwr, a in zip(pwrs, acts):
        n_bars = max(pwr.barrier_n_bars, 1)
        per_bar = (pwr.forward_return_pct / 100.0) / n_bars
        conviction = pwr.primary.composite_score * pwr.primary.confidence
        out.append(Candidate(
            symbol=pwr.primary.symbol,
            proposed_size=a.final_size,
            conviction=conviction,
            per_bar_return=per_bar,
            n_bars_forward=n_bars,
        ))
    return out


def run_evaluation_day_with_discipline(
    date: dt.date,
    model_primaries_with_returns: list[PrimaryWithReturn],
    behavioral_signals: list[BehavioralSignal],
    vol_by_symbol: dict[str, float],
    forward_return_by_symbol: dict[str, tuple[float, int]],
    market_prices: list[float],
    *,
    config: ExecutionDisciplineConfig,
    books: dict[str, PortfolioBook],
    max_size: float = 1.0,
) -> EvaluationDay:
    """Phase-6 disciplined variant of run_evaluation_day.

    Maintains a PortfolioBook per strategy across days (caller owns books
    dict). Applies hysteresis + thresholds + holding rules before computing
    the day's returns.

    Returns the same EvaluationDay shape so cost accounting + aggregation
    reuse applies unchanged.
    """
    regime = classify_regime(market_prices)

    # Build behavioral PWRs (same construction as run_evaluation_day)
    behavioral_pwrs: list[PrimaryWithReturn] = []
    short_skipped = 0
    provider_counts: dict[str, int] = defaultdict(int)
    symbol_providers: dict[str, set[str]] = defaultdict(set)
    for sig in behavioral_signals:
        provider_counts[sig.strategy_id] += 1
        symbol_providers[sig.symbol].add(sig.strategy_id)
        if sig.signal_direction != DIRECTION_LONG:
            short_skipped += 1
            continue
        vol = vol_by_symbol.get(sig.symbol)
        fwd_tuple = forward_return_by_symbol.get(sig.symbol)
        if vol is None or fwd_tuple is None:
            continue
        primary = behavioral_to_primary(sig, vol)
        if primary is None:
            continue
        fwd_ret_pct, n_bars = fwd_tuple
        behavioral_pwrs.append(PrimaryWithReturn(
            primary=primary, forward_return_pct=fwd_ret_pct, barrier_n_bars=n_bars,
        ))

    combined_pwrs = list(model_primaries_with_returns) + behavioral_pwrs
    routed = route_signals(
        regime.regime, list(model_primaries_with_returns), behavioral_pwrs,
    )
    routed_pwrs = list(routed.model_signals) + list(routed.behavioral_signals)

    strategy_pwrs = {
        "model_only": model_primaries_with_returns,
        "behavioral_only": behavioral_pwrs,
        "combined": combined_pwrs,
        "regime_routed": routed_pwrs,
    }

    daily_return: dict[str, float] = {}
    avg_position_size: dict[str, float] = {}
    total_exposure: dict[str, float] = {}
    sizes_by_symbol: dict[str, dict[str, float]] = {}

    for s in STRATEGIES:
        cands = _pwrs_to_candidates(strategy_pwrs[s], market_prices, max_size)
        # Apply router's exposure multiplier BEFORE discipline so hysteresis
        # and threshold gates see post-multiplier sizes consistently.
        if s == "regime_routed" and routed.exposure_multiplier != 1.0:
            cands = [
                replace(c, proposed_size=c.proposed_size * routed.exposure_multiplier)
                for c in cands
            ]
        actual_sizes = apply_discipline(
            books[s], cands, date, regime.regime, config,
        )
        daily_ret = daily_return_from_book(books[s], date, actual_sizes)
        daily_return[s] = daily_ret
        sizes_list = list(actual_sizes.values())
        avg_position_size[s] = (
            sum(sizes_list) / len(sizes_list) if sizes_list else 0.0
        )
        total_exposure[s] = sum(sizes_list)
        sizes_by_symbol[s] = dict(actual_sizes)

    return EvaluationDay(
        date=date,
        regime=regime,
        n_model=len(model_primaries_with_returns),
        n_behavioral_long=len(behavioral_pwrs),
        n_behavioral_short_skipped=short_skipped,
        n_combined=len(combined_pwrs),
        n_regime_routed=len(routed_pwrs),
        routing_rule=routed.rule_applied,
        routing_exposure_multiplier=routed.exposure_multiplier,
        daily_return=daily_return,
        avg_position_size=avg_position_size,
        total_exposure=total_exposure,
        behavioral_provider_counts=dict(provider_counts),
        behavioral_symbol_providers=dict(symbol_providers),
        sizes_by_symbol=sizes_by_symbol,
    )


# ---------------------------------------------------------------------------
# Phase 6.5 — MTM-accounting variants
# ---------------------------------------------------------------------------
# These share POSITION GENERATION with the existing functions above but
# compute `daily_return` via the standardized MTM engine in
# apps.api.src.domain.evaluation.accounting. Turnover / cost / routing /
# discipline / signal / regime logic is unchanged.


def _mtm_daily_returns_from_sizes(
    sizes_by_symbol: dict[str, dict[str, float]],
    returns: DailyReturnLookup,
    date: dt.date,
) -> dict[str, float]:
    return {
        s: compute_mtm_daily_return(sizes_by_symbol[s], returns, date)
        for s in STRATEGIES
    }


def run_evaluation_day_mtm(
    date: dt.date,
    model_primaries_with_returns: list[PrimaryWithReturn],
    behavioral_signals: list[BehavioralSignal],
    vol_by_symbol: dict[str, float],
    forward_return_by_symbol: dict[str, tuple[float, int]],
    market_prices: list[float],
    daily_return_lookup: DailyReturnLookup,
    *,
    max_size: float = 1.0,
) -> EvaluationDay:
    """Phase-5 semantics (no discipline) with MTM accounting.

    Positions come from the existing daily-fresh-basket generation; only
    the daily return is recomputed via close-to-close MTM.
    """
    day = run_evaluation_day(
        date, model_primaries_with_returns, behavioral_signals,
        vol_by_symbol, forward_return_by_symbol, market_prices,
        max_size=max_size,
    )
    day.daily_return = _mtm_daily_returns_from_sizes(
        day.sizes_by_symbol, daily_return_lookup, date,
    )
    return day


def run_evaluation_day_with_discipline_mtm(
    date: dt.date,
    model_primaries_with_returns: list[PrimaryWithReturn],
    behavioral_signals: list[BehavioralSignal],
    vol_by_symbol: dict[str, float],
    forward_return_by_symbol: dict[str, tuple[float, int]],
    market_prices: list[float],
    daily_return_lookup: DailyReturnLookup,
    *,
    config: "ExecutionDisciplineConfig",
    books: dict[str, "PortfolioBook"],
    max_size: float = 1.0,
) -> EvaluationDay:
    """Phase-6 semantics (discipline on) with MTM accounting.

    Positions come from the existing disciplined generation + PortfolioBook
    persistence; only the daily return is recomputed via close-to-close MTM.
    """
    day = run_evaluation_day_with_discipline(
        date, model_primaries_with_returns, behavioral_signals,
        vol_by_symbol, forward_return_by_symbol, market_prices,
        config=config, books=books, max_size=max_size,
    )
    day.daily_return = _mtm_daily_returns_from_sizes(
        day.sizes_by_symbol, daily_return_lookup, date,
    )
    return day
