"""Phase B2 — behavioral evaluation CLI.

Replays historical_label Buy rows + generates behavioral signals in parallel,
then compares model_only / behavioral_only / combined strategies using
existing execution framework.

Writes:
  - artifacts/behavioral_evaluation_days.jsonl   (per-day log)
  - artifacts/behavioral_evaluation_report.md    (aggregate + regime + convergence)

No DB writes. No auto-selection. Observation only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from loguru import logger
from sqlalchemy import select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import (
    Asset,
    HistoricalLabel,
    PriceBar,
    UniverseMembership,
)
from apps.api.src.domain.behavioral.base import (
    AssetHistory,
    Bar,
    MarketContext,
)
from apps.api.src.domain.behavioral.evaluation import (
    STRATEGIES,
    EvaluationDay,
    aggregate_all,
    aggregate_by_regime,
    analyze_providers,
    run_evaluation_day,
    run_evaluation_day_mtm,
    run_evaluation_day_with_discipline,
    run_evaluation_day_with_discipline_mtm,
)
from apps.api.src.domain.evaluation.accounting import (
    DailyReturnLookup,
    build_daily_return_lookup,
)
from apps.api.src.domain.execution.discipline import (
    ExecutionDisciplineConfig,
    PortfolioBook,
)
from apps.api.src.domain.behavioral.integrator import (
    compute_breadth_pct_above_ma50,
    generate_behavioral_signals,
)
from apps.api.src.domain.evaluation.costs import (
    DEFAULT_SCENARIOS,
    REALISTIC_COST,
    compute_scenarios,
    compute_scenarios_by_regime,
)
from apps.api.src.domain.execution.integrator import PrimarySignal
from apps.api.src.domain.execution.shadow import PrimaryWithReturn
from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION

ARTIFACTS_DIR = Path("artifacts")
DAYS_LOG = ARTIFACTS_DIR / "behavioral_evaluation_days.jsonl"
REPORT_PATH = ARTIFACTS_DIR / "behavioral_evaluation_report.md"
COST_REPORT_PATH = ARTIFACTS_DIR / "cost_aware_evaluation_report.md"
COST_DAYS_LOG = ARTIFACTS_DIR / "cost_aware_evaluation_days.jsonl"
PHASE6_REPORT_PATH = ARTIFACTS_DIR / "phase6_discipline_report.md"
PHASE65_REPORT_PATH = ARTIFACTS_DIR / "phase6_5_reconciled_report.md"

BAR_HISTORY_DAYS = 120           # lookback for per-asset bar history
FORWARD_LOOKAHEAD_BARS = 20      # forward return horizon (matches existing backfill)


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------


def _load_universe_symbols(session, as_of: dt.date) -> list[Asset]:
    return list(session.execute(
        select(Asset).join(
            UniverseMembership, UniverseMembership.asset_id == Asset.id,
        ).where(
            UniverseMembership.universe_name == "stock_swing_v1",
            UniverseMembership.start_date <= as_of,
            (
                UniverseMembership.end_date.is_(None)
                | (UniverseMembership.end_date >= as_of)
            ),
        )
    ).scalars().all())


def _load_bars_range(
    session, asset_id: str, start_ts: dt.datetime, end_ts: dt.datetime,
) -> list[Bar]:
    rows = session.execute(
        select(PriceBar).where(
            PriceBar.asset_id == asset_id,
            PriceBar.timeframe == "1d",
            PriceBar.ts >= start_ts,
            PriceBar.ts <= end_ts,
        ).order_by(PriceBar.ts.asc())
    ).scalars().all()
    return [
        Bar(
            ts=r.ts.date(), open=float(r.open or 0.0),
            high=float(r.high or 0.0), low=float(r.low or 0.0),
            close=float(r.close), volume=float(r.volume or 0.0),
        )
        for r in rows if r.close is not None
    ]


def _load_forward_returns(
    session, asset_ids: list[str], as_of: dt.date,
    lookahead_bars: int = FORWARD_LOOKAHEAD_BARS,
) -> dict[str, tuple[float, int]]:
    """For each asset_id, fetch forward-return from as_of's next bar to
    lookahead_bars later. Returns {asset_id: (pct, n_bars_actual)}.
    """
    out: dict[str, tuple[float, int]] = {}
    start_ts = dt.datetime.combine(as_of, dt.time(23, 59, 59))
    for aid in asset_ids:
        fwd_rows = session.execute(
            select(PriceBar).where(
                PriceBar.asset_id == aid,
                PriceBar.timeframe == "1d",
                PriceBar.ts > start_ts,
            ).order_by(PriceBar.ts.asc()).limit(lookahead_bars + 1)
        ).scalars().all()
        if len(fwd_rows) < 2:
            continue
        entry = fwd_rows[0]
        if entry.close is None or float(entry.close) <= 0:
            continue
        end = fwd_rows[-1]
        if end.close is None:
            continue
        entry_px = float(entry.close)
        end_px = float(end.close)
        n_bars = len(fwd_rows) - 1
        if n_bars <= 0:
            continue
        fwd_ret_pct = (end_px / entry_px - 1.0) * 100.0
        out[aid] = (fwd_ret_pct, n_bars)
    return out


def _load_spy_prices(
    session, as_of: dt.date, lookback_bars: int = 120,
) -> list[float]:
    asset = session.execute(
        select(Asset).where(Asset.symbol == "SPY"),
    ).scalar_one_or_none()
    if asset is None:
        return []
    rows = session.execute(
        select(PriceBar).where(
            PriceBar.asset_id == asset.id,
            PriceBar.timeframe == "1d",
            PriceBar.ts <= dt.datetime.combine(as_of, dt.time(23, 59, 59)),
        ).order_by(PriceBar.ts.desc()).limit(lookback_bars)
    ).scalars().all()
    return [float(r.close) for r in reversed(list(rows)) if r.close is not None]


def _build_model_pwrs(
    rows: list[HistoricalLabel],
    forward_by_asset: dict[str, tuple[float, int]],
) -> list[PrimaryWithReturn]:
    """Build PrimaryWithReturn for model_only strategy from Buy rows."""
    out: list[PrimaryWithReturn] = []
    for r in rows:
        primary = PrimarySignal.from_raw(
            symbol=r.symbol,
            composite_score=r.composite_score,
            confidence_raw=r.confidence,
            vol_raw=r.realized_vol_20d,
            vol_is_daily=False,
        )
        # Use the existing HistoricalLabel forward_return_pct if present,
        # else fall back to the common PriceBar-derived forward return.
        if r.forward_return_pct is not None:
            fwd_pct = float(r.forward_return_pct)
            n_bars = int(r.barrier_n_bars or 20)
        else:
            fwd = forward_by_asset.get(r.asset_id)
            if fwd is None:
                continue
            fwd_pct, n_bars = fwd
        out.append(PrimaryWithReturn(
            primary=primary, forward_return_pct=fwd_pct, barrier_n_bars=n_bars,
        ))
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-version", type=str, default=MODEL_VERSION)
    parser.add_argument("--days", type=int, default=0,
                        help="trailing business days to evaluate (0=all)")
    parser.add_argument("--max-days", type=int, default=0,
                        help="hard cap on days (0=no cap)")
    args = parser.parse_args()

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    DAYS_LOG.unlink(missing_ok=True)

    with SessionLocal() as session:
        # Enumerate distinct date range from HistoricalLabel for the engine_version
        rows = list(session.execute(
            select(HistoricalLabel).where(
                HistoricalLabel.engine_version == args.engine_version,
                HistoricalLabel.action == "Buy",
            ).order_by(HistoricalLabel.as_of_date.asc())
        ).scalars().all())
        by_day: dict[dt.date, list[HistoricalLabel]] = defaultdict(list)
        for r in rows:
            by_day[r.as_of_date].append(r)
        sorted_days = sorted(by_day.keys())
        if args.days > 0:
            sorted_days = sorted_days[-args.days:]
        if args.max_days > 0:
            sorted_days = sorted_days[: args.max_days]
        logger.info(
            "[b2.cli] engine_version={} days={} first={} last={}",
            args.engine_version, len(sorted_days),
            sorted_days[0] if sorted_days else None,
            sorted_days[-1] if sorted_days else None,
        )

        eval_days: list[EvaluationDay] = []
        phase6_days: list[EvaluationDay] = []
        phase5_mtm_days: list[EvaluationDay] = []
        phase6_mtm_days: list[EvaluationDay] = []
        behavioral_by_day: dict[dt.date, list] = {}
        forward_ret_by_symbol_date: dict[tuple[str, dt.date], float] = {}

        # Phase-6 config + per-strategy books (disciplined replay)
        phase6_config = ExecutionDisciplineConfig()
        phase6_books = {s: PortfolioBook() for s in STRATEGIES}
        # Separate books for MTM-accounted disciplined replay
        phase6_mtm_books = {s: PortfolioBook() for s in STRATEGIES}

        # ---------- Phase 6.5 reconciliation: bulk-load bars for MTM ----
        # Build DailyReturnLookup ONCE across the full window for all
        # universe symbols ever observed. Uniform accounting for all paths.
        all_asset_ids: set[str] = set()
        all_symbols: dict[str, str] = {}   # asset_id -> symbol
        for as_of in sorted_days:
            for a in _load_universe_symbols(session, as_of):
                all_asset_ids.add(a.id)
                all_symbols[a.id] = a.symbol
        logger.info(
            "[b65.cli] bulk-loading bars for {} symbols across window",
            len(all_asset_ids),
        )
        bulk_start = dt.datetime.combine(
            sorted_days[0] - dt.timedelta(days=BAR_HISTORY_DAYS), dt.time(0, 0),
        )
        bulk_end = dt.datetime.combine(
            sorted_days[-1] + dt.timedelta(days=FORWARD_LOOKAHEAD_BARS * 2),
            dt.time(23, 59, 59),
        )
        closes_by_symbol: dict[str, list[tuple[dt.date, float]]] = {}
        for aid in all_asset_ids:
            sym = all_symbols[aid]
            bars = _load_bars_range(session, aid, bulk_start, bulk_end)
            if not bars:
                continue
            closes_by_symbol[sym] = [(b.ts, b.close) for b in bars]
        mtm_lookup = build_daily_return_lookup(closes_by_symbol)
        logger.info(
            "[b65.cli] DailyReturnLookup built: {} (symbol,date) pairs",
            len(mtm_lookup),
        )

        for i, as_of in enumerate(sorted_days):
            # Universe symbols at as_of
            assets = _load_universe_symbols(session, as_of)
            if not assets:
                continue

            # Bar histories
            start_ts = dt.datetime.combine(
                as_of - dt.timedelta(days=BAR_HISTORY_DAYS), dt.time(0, 0),
            )
            end_ts = dt.datetime.combine(as_of, dt.time(23, 59, 59))
            universe: list[AssetHistory] = []
            for a in assets:
                bars = _load_bars_range(session, a.id, start_ts, end_ts)
                if len(bars) >= 51:
                    universe.append(AssetHistory(
                        symbol=a.symbol, asset_id=a.id, bars=bars,
                    ))
            if not universe:
                continue

            # Market context
            breadth = compute_breadth_pct_above_ma50(universe)
            ctx = MarketContext(
                as_of_date=as_of, pct_above_ma50=breadth,
                universe_size=len(universe),
            )

            # Forward returns for all universe assets (via PriceBar)
            asset_ids = [a.asset_id for a in universe]
            forward_by_asset = _load_forward_returns(session, asset_ids, as_of)

            # Symbol->vol (annualized): last bar's realized vol computed from closes
            # Use 20-day daily returns stdev * sqrt(252) (simple, deterministic)
            vol_by_symbol: dict[str, float] = {}
            forward_by_symbol: dict[str, tuple[float, int]] = {}
            for hist in universe:
                closes = hist.closes(21)
                if len(closes) < 21:
                    continue
                rets = [
                    (closes[k] - closes[k - 1]) / closes[k - 1]
                    for k in range(1, len(closes)) if closes[k - 1] > 0
                ]
                if len(rets) < 5:
                    continue
                mean_r = sum(rets) / len(rets)
                var = sum((r - mean_r) ** 2 for r in rets) / len(rets)
                daily_std = var ** 0.5
                ann_vol = daily_std * math.sqrt(252)
                if ann_vol <= 0:
                    continue
                vol_by_symbol[hist.symbol] = ann_vol
                fwd = forward_by_asset.get(hist.asset_id)
                if fwd is not None:
                    forward_by_symbol[hist.symbol] = fwd
                    forward_ret_by_symbol_date[(hist.symbol, as_of)] = fwd[0]

            # Behavioral signals
            bs = generate_behavioral_signals(as_of, universe, ctx)
            behavioral_by_day[as_of] = bs

            # Model primaries from HistoricalLabel
            model_pwrs = _build_model_pwrs(by_day[as_of], forward_by_asset)

            # SPY prices for regime
            spy_prices = _load_spy_prices(session, as_of)
            if not spy_prices:
                continue

            day = run_evaluation_day(
                as_of, model_pwrs, bs, vol_by_symbol, forward_by_symbol,
                spy_prices,
            )
            eval_days.append(day)

            # Parallel Phase-6 disciplined pass — same inputs, different
            # execution discipline. Books persist across days.
            phase6_day = run_evaluation_day_with_discipline(
                as_of, model_pwrs, bs, vol_by_symbol, forward_by_symbol,
                spy_prices,
                config=phase6_config, books=phase6_books,
            )
            phase6_days.append(phase6_day)

            # ---- Phase 6.5 reconciled runs (MTM accounting) ---------
            phase5_mtm_day = run_evaluation_day_mtm(
                as_of, model_pwrs, bs, vol_by_symbol, forward_by_symbol,
                spy_prices, daily_return_lookup=mtm_lookup,
            )
            phase5_mtm_days.append(phase5_mtm_day)

            phase6_mtm_day = run_evaluation_day_with_discipline_mtm(
                as_of, model_pwrs, bs, vol_by_symbol, forward_by_symbol,
                spy_prices, daily_return_lookup=mtm_lookup,
                config=phase6_config, books=phase6_mtm_books,
            )
            phase6_mtm_days.append(phase6_mtm_day)

            # Structured per-day log
            with DAYS_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "date": str(day.date),
                    "regime": day.regime.regime,
                    "routing_rule": day.routing_rule,
                    "routing_exposure_multiplier": day.routing_exposure_multiplier,
                    "n_model": day.n_model,
                    "n_behavioral_long": day.n_behavioral_long,
                    "n_behavioral_short_skipped": day.n_behavioral_short_skipped,
                    "n_combined": day.n_combined,
                    "n_regime_routed": day.n_regime_routed,
                    "behavioral_provider_counts": day.behavioral_provider_counts,
                    "daily_return": day.daily_return,
                    "avg_position_size": day.avg_position_size,
                    "total_exposure": day.total_exposure,
                }) + "\n")

            if (i + 1) % 50 == 0:
                logger.info(
                    "[b2.cli] progress {}/{} eval_days_so_far={}",
                    i + 1, len(sorted_days), len(eval_days),
                )

    if not eval_days:
        logger.error("[b2.cli] no eval days produced")
        return 1

    # Overall aggregation
    all_agg = aggregate_all(eval_days)

    # Per-regime aggregation
    per_regime = aggregate_by_regime(eval_days)

    # Provider analysis (convergence)
    analysis = analyze_providers(
        eval_days, behavioral_by_day, forward_ret_by_symbol_date,
    )

    # Build report
    def _strategy_row(a) -> str:
        return (
            f"| {a.strategy:<16s} | {a.n_days:>6d} | {a.n_trades_total:>8d} | "
            f"{a.cumulative_return:+.4f} | {a.sharpe:+.4f} | "
            f"{a.max_drawdown_pct:+.4f} | {a.turnover:.4f} | "
            f"{a.avg_position_size:.4f} |"
        )

    lines: list[str] = []
    lines.append("# Phase B2 — Behavioral Evaluation Report")
    lines.append("")
    lines.append(f"- engine_version: `{args.engine_version}`")
    lines.append(f"- days_replayed: {len(eval_days)}")
    lines.append(f"- first_date: {eval_days[0].date}")
    lines.append(f"- last_date: {eval_days[-1].date}")
    lines.append(f"- per_day_log: `{DAYS_LOG}`")
    lines.append("")

    # 1. Overall comparison
    lines.append("## 1. Overall comparison (3 strategies)")
    lines.append("")
    lines.append(
        "| strategy | n_days | n_trades | cumulative | sharpe | max_dd_pct | "
        "turnover | avg_size |"
    )
    lines.append(
        "|----------|--------|---------:|-----------:|-------:|-----------:|"
        "---------:|---------:|"
    )
    for s in STRATEGIES:
        lines.append(_strategy_row(all_agg[s]))
    lines.append("")

    # 2. Per-regime
    lines.append("## 2. Per-regime comparison")
    lines.append("")
    for regime in sorted(per_regime.keys()):
        lines.append(f"### Regime: `{regime}`")
        lines.append("")
        lines.append(
            "| strategy | n_days | n_trades | cumulative | sharpe | max_dd_pct | "
            "turnover | avg_size |"
        )
        lines.append(
            "|----------|--------|---------:|-----------:|-------:|-----------:|"
            "---------:|---------:|"
        )
        for s in STRATEGIES:
            lines.append(_strategy_row(per_regime[regime][s]))
        lines.append("")

    # 3. Behavioral provider breakdown
    lines.append("## 3. Behavioral provider breakdown")
    lines.append("")
    lines.append(
        "| provider | total | unique (sym,date) | direction_long | direction_short |"
    )
    lines.append("|----------|------:|------------------:|---------------:|----------------:|")
    for sid in sorted(analysis.per_provider):
        p = analysis.per_provider[sid]
        lines.append(
            f"| `{p.strategy_id}` | {p.total_signals} | "
            f"{p.unique_symbol_days} | {p.direction_long} | {p.direction_short} |"
        )
    lines.append("")

    # 4. Convergence
    lines.append("## 4. Multi-signal convergence analysis")
    lines.append("")
    lines.append(
        "| bucket | n_events | mean_fwd_return_pct | hit_rate_positive |"
    )
    lines.append("|--------|---------:|---------------------:|------------------:|")
    single = analysis.convergence["single_signal"]
    multi = analysis.convergence["multi_signal"]
    lines.append(
        f"| single_signal | {single.n_events} | "
        f"{single.mean_forward_return_pct:+.4f} | {single.hit_rate_positive:.4f} |"
    )
    lines.append(
        f"| multi_signal  | {multi.n_events} | "
        f"{multi.mean_forward_return_pct:+.4f} | {multi.hit_rate_positive:.4f} |"
    )
    lines.append("")

    # 5. Key observations (no conclusions)
    lines.append("## 5. Key observations (raw, no conclusions)")
    lines.append("")
    lines.append(
        f"- Forward-return attribution uses PriceBar {FORWARD_LOOKAHEAD_BARS}-bar "
        "lookahead close-to-close for behavioral signals; HistoricalLabel's own "
        "`forward_return_pct` used for model-only rows where present."
    )
    lines.append(
        "- `behavioral_only` excludes short-direction signals "
        "(long-only portfolio infra)."
    )
    lines.append(
        "- `combined` = simple concatenation (not re-ranked, not de-duplicated). "
        "Symbols appearing in both streams contribute two position entries."
    )
    # Regime distribution
    regime_counts: dict[str, int] = defaultdict(int)
    for d in eval_days:
        regime_counts[d.regime.regime] += 1
    lines.append("- Regime distribution over window:")
    for r in sorted(regime_counts):
        lines.append(f"  - {r}: {regime_counts[r]} days")
    lines.append("")
    lines.append("## Guardrails honored")
    lines.append("")
    lines.append("- No behavioral provider code modified.")
    lines.append("- No model signal generation modified.")
    lines.append("- No sizing / regime thresholds changed.")
    lines.append("- No ML. No weighting. No ranking change.")
    lines.append("- Pure observation; no best-strategy selection.")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    logger.info("[b2.cli] report written -> {}", REPORT_PATH)

    # Echo overall table to stdout
    print()
    print("Overall (gross, no cost):")
    print("  strategy          n_days  n_trades  cumulative     sharpe     dd_pct    turnover  avg_size")
    for s in STRATEGIES:
        a = all_agg[s]
        print(
            f"  {a.strategy:<16s}  {a.n_days:>6d}  {a.n_trades_total:>8d}  "
            f"{a.cumulative_return:+.4f}   {a.sharpe:+.4f}   "
            f"{a.max_drawdown_pct:+.4f}    {a.turnover:.4f}   {a.avg_position_size:.4f}"
        )
    print()

    # ---------- Cost-aware evaluation -----------------------------------
    cost_results = compute_scenarios(eval_days, STRATEGIES, DEFAULT_SCENARIOS)
    per_regime_real = compute_scenarios_by_regime(
        eval_days, STRATEGIES, REALISTIC_COST,
    )

    # Print cost-aware summary
    print("Cost-aware summary (delta vs zero_cost):")
    header = (
        f"  {'strategy':<16s}  {'scenario':<16s}  "
        f"{'cum':>9s}  {'sharpe':>8s}  "
        f"{'d_cum':>9s}  {'d_sharpe':>9s}  {'turnover':>8s}"
    )
    print(header)
    for s in STRATEGIES:
        for sc in DEFAULT_SCENARIOS:
            m = cost_results[(s, sc.name)]
            print(
                f"  {m.strategy:<16s}  {m.scenario:<16s}  "
                f"{m.cumulative_return:+8.4f}   {m.sharpe:+7.4f}   "
                f"{m.delta_cumulative_return:+8.4f}   "
                f"{m.delta_sharpe:+8.4f}   {m.turnover:.4f}"
            )

    # ---------- Cost-aware MD report ------------------------------------
    cost_lines: list[str] = []
    cost_lines.append("# Cost-Aware Behavioral Evaluation")
    cost_lines.append("")
    cost_lines.append(f"- engine_version: `{args.engine_version}`")
    cost_lines.append(f"- days_replayed: {len(eval_days)}")
    cost_lines.append(
        f"- window: {eval_days[0].date} -> {eval_days[-1].date}"
    )
    cost_lines.append(f"- strategies: {', '.join(STRATEGIES)}")
    cost_lines.append(
        f"- gross report: `{REPORT_PATH.name}` (reproducible zero-cost "
        "equivalent lives in `zero_cost` column below)"
    )
    cost_lines.append("")

    cost_lines.append("## Cost assumptions")
    cost_lines.append("")
    cost_lines.append("| scenario | commission_bps | slippage_bps | round_trip_bps | cost_rate |")
    cost_lines.append("|----------|---------------:|-------------:|---------------:|---------:|")
    for sc in DEFAULT_SCENARIOS:
        cost_lines.append(
            f"| `{sc.name}` | {sc.commission_bps:.1f} | {sc.slippage_bps:.1f} | "
            f"{sc.round_trip_bps:.1f} | {sc.cost_rate:.6f} |"
        )
    cost_lines.append("")
    cost_lines.append(
        "Cost model: `cost = position_delta × cost_rate_one_way`, where "
        "`position_delta = Σ |size_today[s] − size_yesterday[s]|` across the "
        "union of symbols per strategy. Deduction normalized by today's total "
        "exposure (per-dollar-deployed units) so it subtracts directly from "
        "daily_return. Zero-turnover days incur zero cost; full basket swap "
        "pays full round-trip."
    )
    cost_lines.append("")

    # A. Overall by strategy under each scenario
    cost_lines.append("## A. Overall results by strategy × scenario")
    cost_lines.append("")
    cost_lines.append(
        "| strategy | scenario | cumulative | sharpe | max_dd_pct | turnover | "
        "Δcumulative | Δsharpe |"
    )
    cost_lines.append(
        "|----------|----------|-----------:|-------:|-----------:|---------:|"
        "-----------:|--------:|"
    )
    for s in STRATEGIES:
        for sc in DEFAULT_SCENARIOS:
            m = cost_results[(s, sc.name)]
            cost_lines.append(
                f"| `{m.strategy}` | `{m.scenario}` | {m.cumulative_return:+.4f} | "
                f"{m.sharpe:+.4f} | {m.max_drawdown_pct:+.4f} | {m.turnover:.4f} | "
                f"{m.delta_cumulative_return:+.4f} | {m.delta_sharpe:+.4f} |"
            )
    cost_lines.append("")

    # B. Regime-specific under realistic_cost
    cost_lines.append("## B. Regime breakdown — `realistic_cost` (10 bps round-trip)")
    cost_lines.append("")
    for regime in sorted(per_regime_real.keys()):
        cost_lines.append(f"### Regime: `{regime}`")
        cost_lines.append("")
        cost_lines.append(
            "| strategy | n_days | n_trades | cumulative | sharpe | max_dd_pct | "
            "turnover |"
        )
        cost_lines.append(
            "|----------|-------:|---------:|-----------:|-------:|-----------:|"
            "---------:|"
        )
        for s in STRATEGIES:
            m = per_regime_real[regime][s]
            cost_lines.append(
                f"| `{m.strategy}` | {m.n_days} | {m.n_trades_total} | "
                f"{m.cumulative_return:+.4f} | {m.sharpe:+.4f} | "
                f"{m.max_drawdown_pct:+.4f} | {m.turnover:.4f} |"
            )
        cost_lines.append("")

    # C. Ranking changes (ordered by cumulative return within each scenario)
    cost_lines.append("## C. Ranking changes across scenarios")
    cost_lines.append("")
    cost_lines.append(
        "Strategies ordered by cumulative_return within each scenario "
        "(1 = best). Watch for reorderings as costs rise."
    )
    cost_lines.append("")
    cost_lines.append(
        "| rank | zero_cost | low_cost | realistic_cost | high_cost |"
    )
    cost_lines.append("|------|-----------|----------|----------------|-----------|")
    rankings: dict[str, list[str]] = {}
    for sc in DEFAULT_SCENARIOS:
        order = sorted(
            STRATEGIES,
            key=lambda s: cost_results[(s, sc.name)].cumulative_return,
            reverse=True,
        )
        rankings[sc.name] = order
    for rank in range(len(STRATEGIES)):
        row = [f"{rank + 1}"]
        for sc in DEFAULT_SCENARIOS:
            ord_list = rankings[sc.name]
            row.append(ord_list[rank])
        cost_lines.append("| " + " | ".join(row) + " |")
    cost_lines.append("")

    # Cost sensitivity — per-strategy degradation summary
    cost_lines.append("## Cost sensitivity summary")
    cost_lines.append("")
    cost_lines.append(
        "| strategy | zero_cum | realistic_cum | Δcum_realistic | zero_sharpe | "
        "realistic_sharpe | Δsharpe_realistic |"
    )
    cost_lines.append(
        "|----------|---------:|--------------:|---------------:|------------:|"
        "-----------------:|------------------:|"
    )
    for s in STRATEGIES:
        zc = cost_results[(s, "zero_cost")]
        rc = cost_results[(s, "realistic_cost")]
        cost_lines.append(
            f"| `{s}` | {zc.cumulative_return:+.4f} | "
            f"{rc.cumulative_return:+.4f} | {rc.delta_cumulative_return:+.4f} | "
            f"{zc.sharpe:+.4f} | {rc.sharpe:+.4f} | {rc.delta_sharpe:+.4f} |"
        )
    cost_lines.append("")

    cost_lines.append("## Guardrails honored")
    cost_lines.append("")
    cost_lines.append("- No signal generation modified.")
    cost_lines.append("- No behavioral providers modified.")
    cost_lines.append("- No routing rules modified.")
    cost_lines.append("- No regime classifier modified.")
    cost_lines.append("- No sizing formulas modified.")
    cost_lines.append("- Cost model applied post-hoc; strategy decisions unchanged.")
    cost_lines.append(
        "- Zero-cost path reproduces existing gross metrics exactly (test covered)."
    )

    COST_REPORT_PATH.write_text("\n".join(cost_lines), encoding="utf-8")
    logger.info("[cost] report written -> {}", COST_REPORT_PATH)

    # Per-scenario/day JSONL for machine-readable inspection
    COST_DAYS_LOG.unlink(missing_ok=True)
    with COST_DAYS_LOG.open("a", encoding="utf-8") as f:
        for key, m in cost_results.items():
            f.write(json.dumps({
                "strategy": m.strategy,
                "scenario": m.scenario,
                "n_days": m.n_days,
                "n_trades_total": m.n_trades_total,
                "cumulative_return": m.cumulative_return,
                "sharpe": m.sharpe,
                "max_drawdown_pct": m.max_drawdown_pct,
                "turnover": m.turnover,
                "avg_position_size": m.avg_position_size,
                "delta_cumulative_return": m.delta_cumulative_return,
                "delta_sharpe": m.delta_sharpe,
            }) + "\n")

    # ---------- Phase 6 — before / after comparison ---------------------
    p6_cost_results = compute_scenarios(phase6_days, STRATEGIES, DEFAULT_SCENARIOS)
    p6_all_agg = aggregate_all(phase6_days)
    p6_per_regime_real = compute_scenarios_by_regime(
        phase6_days, STRATEGIES, REALISTIC_COST,
    )

    p6_lines: list[str] = []
    p6_lines.append("# Phase 6 — Execution Discipline: Before vs After")
    p6_lines.append("")
    p6_lines.append(f"- engine_version: `{args.engine_version}`")
    p6_lines.append(f"- days_replayed: {len(eval_days)}")
    p6_lines.append(
        f"- window: {eval_days[0].date} -> {eval_days[-1].date}"
    )
    p6_lines.append("")
    p6_lines.append("## Discipline config (defaults)")
    p6_lines.append("")
    p6_lines.append(f"- `min_position_change` = {phase6_config.min_position_change}")
    p6_lines.append(f"- `min_hold_days` = {phase6_config.min_hold_days}")
    p6_lines.append(f"- `cooldown_days` = {phase6_config.cooldown_days}")
    p6_lines.append(
        f"- `override_conviction_gap` = {phase6_config.override_conviction_gap}"
    )
    p6_lines.append(
        f"- `min_open_conviction` = "
        f"{dict(phase6_config.min_open_conviction)}"
    )
    p6_lines.append(
        f"- `min_open_conviction_fallback` = "
        f"{phase6_config.min_open_conviction_fallback}"
    )
    p6_lines.append("")

    # Before vs After under each cost scenario
    p6_lines.append("## Before vs After — cumulative return, Sharpe, turnover")
    p6_lines.append("")
    p6_lines.append(
        "| scenario | strategy | pre_cum | post_cum | Δcum | pre_sharpe | "
        "post_sharpe | Δsharpe | pre_turnover | post_turnover |"
    )
    p6_lines.append(
        "|----------|----------|--------:|---------:|-----:|-----------:|"
        "------------:|--------:|-------------:|--------------:|"
    )
    for sc in DEFAULT_SCENARIOS:
        for s in STRATEGIES:
            pre = cost_results[(s, sc.name)]
            post = p6_cost_results[(s, sc.name)]
            p6_lines.append(
                f"| `{sc.name}` | `{s}` | {pre.cumulative_return:+.4f} | "
                f"{post.cumulative_return:+.4f} | "
                f"{post.cumulative_return - pre.cumulative_return:+.4f} | "
                f"{pre.sharpe:+.4f} | {post.sharpe:+.4f} | "
                f"{post.sharpe - pre.sharpe:+.4f} | "
                f"{pre.turnover:.4f} | {post.turnover:.4f} |"
            )
    p6_lines.append("")

    # Regime breakdown under realistic cost
    p6_lines.append("## Regime breakdown @ realistic_cost (10 bps)")
    p6_lines.append("")
    p6_lines.append("### Before Phase 6")
    p6_lines.append("")
    p6_lines.append(
        "| regime | strategy | cumulative | sharpe | max_dd | turnover |"
    )
    p6_lines.append(
        "|--------|----------|-----------:|-------:|-------:|---------:|"
    )
    for regime in sorted(per_regime_real.keys()):
        for s in STRATEGIES:
            m = per_regime_real[regime][s]
            p6_lines.append(
                f"| `{regime}` | `{s}` | {m.cumulative_return:+.4f} | "
                f"{m.sharpe:+.4f} | {m.max_drawdown_pct:+.4f} | "
                f"{m.turnover:.4f} |"
            )
    p6_lines.append("")
    p6_lines.append("### After Phase 6")
    p6_lines.append("")
    p6_lines.append(
        "| regime | strategy | cumulative | sharpe | max_dd | turnover |"
    )
    p6_lines.append(
        "|--------|----------|-----------:|-------:|-------:|---------:|"
    )
    for regime in sorted(p6_per_regime_real.keys()):
        for s in STRATEGIES:
            m = p6_per_regime_real[regime][s]
            p6_lines.append(
                f"| `{regime}` | `{s}` | {m.cumulative_return:+.4f} | "
                f"{m.sharpe:+.4f} | {m.max_drawdown_pct:+.4f} | "
                f"{m.turnover:.4f} |"
            )
    p6_lines.append("")

    # Success criteria summary
    p6_lines.append("## Success-criteria summary")
    p6_lines.append("")
    pre_rr = cost_results[("regime_routed", "realistic_cost")]
    post_rr = p6_cost_results[("regime_routed", "realistic_cost")]
    pre_m = cost_results[("model_only", "realistic_cost")]
    post_m = p6_cost_results[("model_only", "realistic_cost")]
    p6_lines.append(
        f"- regime_routed turnover: {pre_rr.turnover:.4f} -> "
        f"{post_rr.turnover:.4f} "
        f"(delta{post_rr.turnover - pre_rr.turnover:+.4f})"
    )
    p6_lines.append(
        f"- regime_routed realistic-cost cumulative: "
        f"{pre_rr.cumulative_return:+.4f} -> {post_rr.cumulative_return:+.4f} "
        f"(delta{post_rr.cumulative_return - pre_rr.cumulative_return:+.4f})"
    )
    p6_lines.append(
        f"- regime_routed realistic-cost Sharpe: "
        f"{pre_rr.sharpe:+.4f} -> {post_rr.sharpe:+.4f} "
        f"(delta{post_rr.sharpe - pre_rr.sharpe:+.4f})"
    )
    p6_lines.append(
        f"- model_only realistic-cost cumulative: "
        f"{pre_m.cumulative_return:+.4f} -> {post_m.cumulative_return:+.4f} "
        f"(delta{post_m.cumulative_return - pre_m.cumulative_return:+.4f})"
    )
    p6_lines.append("")
    p6_lines.append("## Guardrails honored")
    p6_lines.append("")
    p6_lines.append("- No signal generation modified.")
    p6_lines.append("- No behavioral providers modified.")
    p6_lines.append("- No routing rules modified.")
    p6_lines.append("- No regime classifier modified.")
    p6_lines.append("- No sizing formulas modified.")
    p6_lines.append("- Phase-6 logic is opt-in via ExecutionDisciplineConfig.enabled.")

    PHASE6_REPORT_PATH.write_text("\n".join(p6_lines), encoding="utf-8")
    logger.info("[phase6] report written -> {}", PHASE6_REPORT_PATH)

    # ---------- Phase 6.5 reconciled report -----------------------------
    p5_mtm_cost = compute_scenarios(phase5_mtm_days, STRATEGIES, DEFAULT_SCENARIOS)
    p6_mtm_cost = compute_scenarios(phase6_mtm_days, STRATEGIES, DEFAULT_SCENARIOS)
    p5_mtm_regime = compute_scenarios_by_regime(
        phase5_mtm_days, STRATEGIES, REALISTIC_COST,
    )
    p6_mtm_regime = compute_scenarios_by_regime(
        phase6_mtm_days, STRATEGIES, REALISTIC_COST,
    )

    p65_lines: list[str] = []
    p65_lines.append("# Phase 6.5 — Accounting Reconciliation")
    p65_lines.append("")
    p65_lines.append(f"- engine_version: `{args.engine_version}`")
    p65_lines.append(f"- days_replayed: {len(eval_days)}")
    p65_lines.append(
        f"- window: {eval_days[0].date} -> {eval_days[-1].date}"
    )
    p65_lines.append(
        f"- MTM lookup pairs: {len(mtm_lookup)} (symbol,date) close-to-close"
    )
    p65_lines.append("")
    p65_lines.append("## Accounting standard")
    p65_lines.append("")
    p65_lines.append(
        "`daily_return_t = Σ(size_t[sym] × r_{sym,t}) / Σ(size_t)`  "
        "where `r_{sym,t} = (close_{t+1} − close_t) / close_t`."
    )
    p65_lines.append("")
    p65_lines.append(
        "- Applied identically to Phase 5 (daily-fresh-basket) and Phase 6 "
        "(disciplined persistent positions)."
    )
    p65_lines.append(
        "- Held positions are repriced at THAT day's close-to-close return, "
        "NOT at entry-day cached forward attribution."
    )
    p65_lines.append(
        "- Turnover and cost model unchanged (operate on sizes_by_symbol "
        "position deltas)."
    )
    p65_lines.append("")

    # Section 1: legacy vs MTM for each phase
    p65_lines.append("## 1. Legacy accounting vs MTM — cumulative return")
    p65_lines.append("")
    p65_lines.append(
        "| phase | strategy | legacy_cum | mtm_cum | Δ(mtm-legacy) |"
    )
    p65_lines.append(
        "|-------|----------|-----------:|--------:|--------------:|"
    )
    for s in STRATEGIES:
        legacy5 = cost_results[(s, "zero_cost")].cumulative_return
        mtm5 = p5_mtm_cost[(s, "zero_cost")].cumulative_return
        p65_lines.append(
            f"| Phase 5 | `{s}` | {legacy5:+.4f} | {mtm5:+.4f} | "
            f"{mtm5 - legacy5:+.4f} |"
        )
    for s in STRATEGIES:
        legacy6 = p6_cost_results[(s, "zero_cost")].cumulative_return
        mtm6 = p6_mtm_cost[(s, "zero_cost")].cumulative_return
        p65_lines.append(
            f"| Phase 6 | `{s}` | {legacy6:+.4f} | {mtm6:+.4f} | "
            f"{mtm6 - legacy6:+.4f} |"
        )
    p65_lines.append("")

    # Section 2: apples-to-apples — Phase 5 MTM vs Phase 6 MTM under each scenario
    p65_lines.append("## 2. Phase 5 (MTM) vs Phase 6 (MTM) — apples-to-apples")
    p65_lines.append("")
    p65_lines.append(
        "| scenario | strategy | phase5_cum | phase6_cum | Δcum | "
        "phase5_sharpe | phase6_sharpe | Δsharpe | phase5_turn | phase6_turn |"
    )
    p65_lines.append(
        "|----------|----------|-----------:|-----------:|-----:|"
        "--------------:|--------------:|--------:|------------:|------------:|"
    )
    for sc in DEFAULT_SCENARIOS:
        for s in STRATEGIES:
            p5 = p5_mtm_cost[(s, sc.name)]
            p6 = p6_mtm_cost[(s, sc.name)]
            p65_lines.append(
                f"| `{sc.name}` | `{s}` | {p5.cumulative_return:+.4f} | "
                f"{p6.cumulative_return:+.4f} | "
                f"{p6.cumulative_return - p5.cumulative_return:+.4f} | "
                f"{p5.sharpe:+.4f} | {p6.sharpe:+.4f} | "
                f"{p6.sharpe - p5.sharpe:+.4f} | "
                f"{p5.turnover:.4f} | {p6.turnover:.4f} |"
            )
    p65_lines.append("")

    # Section 3: regime breakdown under MTM@realistic
    p65_lines.append("## 3. Regime breakdown under MTM @ realistic_cost")
    p65_lines.append("")
    for regime in sorted(p5_mtm_regime.keys()):
        p65_lines.append(f"### Regime: `{regime}`")
        p65_lines.append("")
        p65_lines.append(
            "| strategy | phase5_cum | phase6_cum | phase5_sharpe | "
            "phase6_sharpe | phase5_turn | phase6_turn |"
        )
        p65_lines.append(
            "|----------|-----------:|-----------:|--------------:|"
            "--------------:|------------:|------------:|"
        )
        for s in STRATEGIES:
            p5 = p5_mtm_regime[regime][s]
            p6 = p6_mtm_regime[regime].get(s)
            if p6 is None:
                continue
            p65_lines.append(
                f"| `{s}` | {p5.cumulative_return:+.4f} | "
                f"{p6.cumulative_return:+.4f} | {p5.sharpe:+.4f} | "
                f"{p6.sharpe:+.4f} | {p5.turnover:.4f} | "
                f"{p6.turnover:.4f} |"
            )
        p65_lines.append("")

    # Section 4: ranking changes
    p65_lines.append("## 4. Ranking — Phase 6 (MTM) across cost scenarios")
    p65_lines.append("")
    p65_lines.append(
        "| rank | zero_cost | low_cost | realistic_cost | high_cost |"
    )
    p65_lines.append("|------|-----------|----------|----------------|-----------|")
    ranks_p6m: dict[str, list[str]] = {}
    for sc in DEFAULT_SCENARIOS:
        ranks_p6m[sc.name] = sorted(
            STRATEGIES,
            key=lambda s: p6_mtm_cost[(s, sc.name)].cumulative_return,
            reverse=True,
        )
    for r in range(len(STRATEGIES)):
        row = [str(r + 1)]
        for sc in DEFAULT_SCENARIOS:
            row.append(ranks_p6m[sc.name][r])
        p65_lines.append("| " + " | ".join(row) + " |")
    p65_lines.append("")

    # Honesty check
    p65_lines.append("## 5. Honesty check")
    p65_lines.append("")
    p65_lines.append("**Changed:**")
    p65_lines.append("")
    p65_lines.append(
        "- Return attribution across all strategies now uses a single "
        "mark-to-market formula (close-to-close), driven by a shared "
        "DailyReturnLookup built from PriceBar."
    )
    p65_lines.append(
        "- Pre-Phase-6 path's per-bar amortization of 20-bar forward return "
        "is REPLACED with daily close-to-close when using the `_mtm` variant."
    )
    p65_lines.append(
        "- Phase-6 path's entry-day cached per_bar_return replay is REPLACED "
        "with daily close-to-close when using the `_mtm` variant."
    )
    p65_lines.append("")
    p65_lines.append("**Did NOT change:**")
    p65_lines.append("")
    p65_lines.append(
        "- Signal generation, routing rules, regime classifier, sizing "
        "formulas, execution-discipline rules/config, cost model, ranking "
        "logic, portfolio construction — all bitwise-identical."
    )
    p65_lines.append(
        "- Legacy accounting paths remain available for audit "
        "(`run_evaluation_day`, `run_evaluation_day_with_discipline`)."
    )
    p65_lines.append("")
    # Ranking shift narrative — compute & report
    pre_rr_mtm = p5_mtm_cost[("regime_routed", "realistic_cost")]
    post_rr_mtm = p6_mtm_cost[("regime_routed", "realistic_cost")]
    pre_m_mtm = p5_mtm_cost[("model_only", "realistic_cost")]
    post_m_mtm = p6_mtm_cost[("model_only", "realistic_cost")]
    p65_lines.append(f"**Key reconciled numbers @ realistic_cost (10 bps):**")
    p65_lines.append("")
    p65_lines.append(
        f"- regime_routed Phase5→Phase6 cumulative: "
        f"{pre_rr_mtm.cumulative_return:+.4f} -> "
        f"{post_rr_mtm.cumulative_return:+.4f}"
    )
    p65_lines.append(
        f"- regime_routed Phase5→Phase6 Sharpe: "
        f"{pre_rr_mtm.sharpe:+.4f} -> {post_rr_mtm.sharpe:+.4f}"
    )
    p65_lines.append(
        f"- regime_routed Phase5→Phase6 turnover: "
        f"{pre_rr_mtm.turnover:.4f} -> {post_rr_mtm.turnover:.4f}"
    )
    p65_lines.append(
        f"- model_only Phase5→Phase6 cumulative: "
        f"{pre_m_mtm.cumulative_return:+.4f} -> "
        f"{post_m_mtm.cumulative_return:+.4f}"
    )
    p65_lines.append("")

    PHASE65_REPORT_PATH.write_text("\n".join(p65_lines), encoding="utf-8")
    logger.info("[phase6_5] report written -> {}", PHASE65_REPORT_PATH)
    print()
    print("Phase 6.5 reconciled @ realistic_cost (MTM accounting):")
    print(f"  model_only      Phase5 {pre_m_mtm.cumulative_return:+.4f} -> Phase6 {post_m_mtm.cumulative_return:+.4f}")
    print(f"  regime_routed   Phase5 {pre_rr_mtm.cumulative_return:+.4f} -> Phase6 {post_rr_mtm.cumulative_return:+.4f}")
    print(f"  regime_routed   turnover {pre_rr_mtm.turnover:.4f} -> {post_rr_mtm.turnover:.4f}")

    # Print short summary
    print()
    print("Phase 6 — key realistic_cost deltas:")
    print(f"  regime_routed  cum  {pre_rr.cumulative_return:+.4f} -> {post_rr.cumulative_return:+.4f}  (delta{post_rr.cumulative_return - pre_rr.cumulative_return:+.4f})")
    print(f"  regime_routed  shp  {pre_rr.sharpe:+.4f} -> {post_rr.sharpe:+.4f}  (delta{post_rr.sharpe - pre_rr.sharpe:+.4f})")
    print(f"  regime_routed  trn  {pre_rr.turnover:.4f} -> {post_rr.turnover:.4f}")
    print(f"  model_only     cum  {pre_m.cumulative_return:+.4f} -> {post_m.cumulative_return:+.4f}")
    print(f"  model_only     trn  {pre_m.turnover:.4f} -> {post_m.turnover:.4f}")

    print()
    print(f"Per-day log      -> {DAYS_LOG}")
    print(f"Gross report     -> {REPORT_PATH}")
    print(f"Cost report      -> {COST_REPORT_PATH}")
    print(f"Cost per-pair    -> {COST_DAYS_LOG}")
    print(f"Phase-6 report   -> {PHASE6_REPORT_PATH}")
    print(f"Phase-6.5 report -> {PHASE65_REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
