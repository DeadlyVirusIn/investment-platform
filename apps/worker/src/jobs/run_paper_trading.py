"""Scheduled job: run the paper-trading auto-trader over active portfolios.

For each active PaperPortfolio:
    1. Generate decisions via auto_trader (sells evaluated first, then buys)
    2. Execute via submit_trade (next-day-open fill)
    3. Snapshot equity

Per-portfolio try/except — one failure does not abort the batch. Idempotent:
re-running on the same day reuses the existing daily equity snapshot row
(UPSERT) and skips decisions whose fills cannot be satisfied.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from loguru import logger
from sqlalchemy import func, select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import PaperPortfolio, PaperPosition, PriceBar
from apps.api.src.domain.paper_trading.auto_trader import (
    AutoTradeConfig,
    auto_trade_portfolio,
)
from apps.api.src.domain.paper_trading.paper_service import snapshot_equity_now
from apps.api.src.reasoning.audit import record_envelope
from apps.api.src.reasoning.worker_integration import (
    generate_envelope_for_paper_trade,
)
from sqlalchemy import text as _sql_text
import json as _json
# Phase 2 stock fix Phase 4 — execution funnel telemetry.
from apps.api.src.domain.paper_trading.funnel import (
    PaperFunnelCounts,
    PaperFunnelSnapshot,
    counts_from_buy_skips,
    upsert_funnel_row,
)
from apps.api.src.domain.paper_trading.paper_execution import (
    DEFAULT_MAX_OPEN_POSITIONS,
    _compute_current_equity,
    _d,
)
from sqlalchemy import select as _select

SKIPS_DIR = Path("artifacts/paper_trading_skips")


async def run_paper_trading(as_of: dt.date | None = None) -> None:
    """Run the auto-trader for every active paper portfolio.

    When ``as_of`` is supplied, the run is replayed *as of* that historical
    date: signals come from candidate_idea rows for that date, and trade
    submission timestamps are anchored to 15:00 UTC on as_of so next-bar
    fills land on the correct historical open.
    """
    if as_of is not None:
        now = dt.datetime.combine(as_of, dt.time(15, 0), tzinfo=dt.timezone.utc)
    else:
        # Live submitted_at anchor (2026-05-19 forensic-audit fix).
        #
        # The previous Phase 11V design anchored submitted_at at today
        # 15:00 UTC and assumed "tomorrow's bar at 00:00 UTC > today's
        # 15:00 UTC" would satisfy the strict `bar.ts > submitted_at`
        # rule. That assumption is wrong: bars use a start-of-trading-
        # day ts convention (00:00 UTC) and only materialize for
        # COMPLETED trading days. The latest available bar at any
        # moment has ts EARLIER than wall-clock, so anchoring
        # submitted_at at today 15:00 UTC made every live fill
        # impossible. Result: 0 live paper_trades ever produced via
        # cron.
        #
        # Fix: anchor submitted_at one second BEFORE the latest
        # available 1d bar's ts. This makes the latest available bar
        # the "next bar after submission" — fill semantics work
        # synchronously without a deferred queue. Fills represent the
        # most recently completed trading day's open price (the
        # maximum fidelity the data supports for a live run).
        #
        # PRESERVED:
        #   * strict `bar.ts > submitted_at` condition in find_next_open
        #   * price_bar schema
        #   * cron schedule
        #   * replay path (as_of branch above)
        #   * cash / max_open / min_notional safety checks
        #   * Phase L reasoning pipeline
        with SessionLocal() as _anchor_session:
            latest_bar_ts = _anchor_session.execute(
                select(func.max(PriceBar.ts)).where(
                    PriceBar.timeframe == "1d",
                )
            ).scalar()

        if latest_bar_ts is None:
            logger.warning(
                "run_paper_trading: no 1d price_bar data available; "
                "submission anchor unresolvable. Aborting run.",
            )
            return

        if latest_bar_ts.tzinfo is None:
            latest_bar_ts = latest_bar_ts.replace(tzinfo=dt.timezone.utc)

        now = latest_bar_ts - dt.timedelta(seconds=1)
        logger.info(
            "live-anchor: submitted_at={} (latest_bar_ts={} - 1s)",
            now.isoformat(), latest_bar_ts.isoformat(),
        )
    total_decisions = 0
    total_executed = 0
    total_rejected = 0

    with SessionLocal() as session:
        portfolio_ids = [
            p.id for p in session.scalars(
                select(PaperPortfolio).where(PaperPortfolio.is_active.is_(True))
            )
        ]

    for portfolio_id in portfolio_ids:
        try:
            with SessionLocal() as session:
                portfolio = session.get(PaperPortfolio, portfolio_id)
                if portfolio is None:
                    continue
                # Phase 2 fix Phase 4 — capture saturation snapshot
                # BEFORE auto_trade so funnel row reflects entry state.
                _open_at_start = session.execute(
                    _select(PaperPosition).where(
                        PaperPosition.portfolio_id == portfolio.id,
                        PaperPosition.is_open.is_(True),
                    )
                ).scalars().all()
                _config_blob = json.loads(portfolio.config_json or "{}")
                _max_open = int(
                    _config_blob.get(
                        "max_open_positions", DEFAULT_MAX_OPEN_POSITIONS,
                    )
                )
                _cash_at_start = _d(portfolio.cash)
                _equity_at_start = _compute_current_equity(session, portfolio)

                result = auto_trade_portfolio(
                    session, portfolio, AutoTradeConfig(),
                    now=now, as_of=as_of,
                )
                # Persist buy_skips for observability / alert classification
                if result.buy_skips:
                    SKIPS_DIR.mkdir(parents=True, exist_ok=True)
                    skip_date = (as_of or now.date()).isoformat()
                    path = SKIPS_DIR / f"{skip_date}.jsonl"
                    with path.open("a", encoding="utf-8") as f:
                        for s in result.buy_skips:
                            f.write(json.dumps({
                                "as_of_date": skip_date,
                                "portfolio_id": portfolio_id,
                                **s,
                            }) + "\n")

                # Phase 2 fix Phase 4 — funnel rollup row.
                # Idempotent on (run_date, portfolio_id).
                _skip_counts = counts_from_buy_skips(result.buy_skips)
                _buy_decisions = sum(
                    1 for d in result.decisions if d.kind == "open_buy"
                )
                _sell_decisions = sum(
                    1 for d in result.decisions if d.kind == "close_sell"
                )
                _buy_rejected = sum(
                    1 for r in result.rejected
                    if r.get("kind") == "open_buy"
                )
                _sell_rejected = sum(
                    1 for r in result.rejected
                    if r.get("kind") == "close_sell"
                )
                _funnel_counts = PaperFunnelCounts(
                    # Top of funnel = decisions surfaced AS open_buy
                    # PLUS pre-decision skips recorded by auto_trader.
                    buy_candidates_total=_buy_decisions + sum(_skip_counts.values()),
                    buys_executed=max(0, _buy_decisions - _buy_rejected),
                    sells_executed=max(0, _sell_decisions - _sell_rejected),
                    skip_portfolio_full=_skip_counts.get("portfolio_full", 0),
                    skip_duplicate_holding=_skip_counts.get("duplicate_holding", 0),
                    skip_pending_sell_same_asset=_skip_counts.get("pending_sell_same_asset", 0),
                    skip_sizing_below_threshold=_skip_counts.get("sizing_below_threshold", 0),
                    skip_position_too_small=_skip_counts.get("position_too_small", 0),
                    skip_cash_constraint=_skip_counts.get("cash_constraint", 0),
                    skip_execution_failure=_skip_counts.get("execution_failure", 0),
                    skip_unknown_reason=_skip_counts.get("unknown_reason", 0),
                )
                upsert_funnel_row(
                    session,
                    run_date=(as_of or now.date()),
                    portfolio_id=portfolio_id,
                    counts=_funnel_counts,
                    snapshot=PaperFunnelSnapshot(
                        open_positions_at_start=len(_open_at_start),
                        max_open_positions=_max_open,
                        cash_at_start=_cash_at_start,
                        equity_at_start=_equity_at_start,
                    ),
                    details={
                        "n_decisions_total": len(result.decisions),
                        "n_executed_total": len(result.executed),
                        "n_rejected_exec": len(result.rejected),
                    },
                )
                # Anchor snapshot at 22:00 UTC on the date (end-of-session feel)
                snapshot_at = (
                    dt.datetime.combine(as_of, dt.time(22, 0), tzinfo=dt.timezone.utc)
                    if as_of is not None else now
                )
                # Phase L M079: when as_of supplied, this is a replay run;
                # otherwise it is the live scheduled job. Distinguish accordingly.
                _snap_source = "replay" if as_of is not None else "live"
                snapshot_equity_now(
                    session, portfolio,
                    as_of=snapshot_at,
                    source=_snap_source,
                )
                session.commit()

                # Phase L D4.6 + D5.6: attach reasoning envelopes to
                # executed trades and persist per-run telemetry.
                _envelope_attached = 0
                _skip_features = 0
                _skip_min_signals = 0
                _skip_no_skeleton = 0
                _skip_empty_slots = 0
                _skip_other = 0
                _skip_exception = 0
                _skeleton_dist: dict[str, int] = {}
                for _tid in result.executed:
                    try:
                        envelope, _src_kind, _reason = (
                            generate_envelope_for_paper_trade(
                                session, _tid, as_of=as_of,
                            )
                        )
                        if envelope is not None:
                            record_envelope(
                                session, envelope, paper_trade_id=_tid,
                            )
                            _envelope_attached += 1
                            _sk = envelope.skeleton_id.value
                            _skeleton_dist[_sk] = _skeleton_dist.get(_sk, 0) + 1
                        else:
                            if _reason == "features_unavailable":
                                _skip_features += 1
                            elif _reason == "min_signals_not_met":
                                _skip_min_signals += 1
                            elif _reason == "no_skeleton_match":
                                _skip_no_skeleton += 1
                            elif _reason == "empty_slot_fills":
                                _skip_empty_slots += 1
                            elif _reason and _reason.startswith("exception:"):
                                _skip_exception += 1
                            else:
                                _skip_other += 1
                            logger.debug(
                                "envelope skipped trade={} src={} reason={}",
                                _tid, _src_kind, _reason,
                            )
                    except Exception as _env_exc:  # noqa: BLE001
                        _skip_exception += 1
                        logger.warning(
                            "envelope attach failed for trade {}: {}",
                            _tid, _env_exc,
                        )

                _trades_exec = len(result.executed)
                if _trades_exec > 0:
                    _skip_gen_none_total = (
                        _skip_min_signals + _skip_no_skeleton + _skip_empty_slots
                    )
                    session.execute(
                        _sql_text(
                            "INSERT INTO envelope_generation_run "
                            "  (portfolio_id, as_of_date, trades_executed, "
                            "   envelopes_attached, skip_features_unavailable, "
                            "   skip_generator_returned_none, skip_exception, "
                            "   skip_min_signals, skip_no_skeleton_match, "
                            "   skip_empty_slot_fills, skeleton_distribution) "
                            "VALUES "
                            "  (:pid, :as_of, :te, :ea, :sf, :sg, :sx, "
                            "   :sm, :sn, :se, :sd)"
                        ),
                        {
                            "pid": portfolio_id,
                            "as_of": as_of,
                            "te": _trades_exec,
                            "ea": _envelope_attached,
                            "sf": _skip_features,
                            "sg": _skip_gen_none_total + _skip_other,
                            "sx": _skip_exception,
                            "sm": _skip_min_signals,
                            "sn": _skip_no_skeleton,
                            "se": _skip_empty_slots,
                            "sd": _json.dumps(_skeleton_dist),
                        },
                    )
                    logger.info(
                        "envelopes portfolio={} attached={}/{} "
                        "skip_features={} skip_min_sigs={} skip_no_skel={} "
                        "skip_empty_slots={} skip_exc={} dist={}",
                        portfolio_id, _envelope_attached, _trades_exec,
                        _skip_features, _skip_min_signals, _skip_no_skeleton,
                        _skip_empty_slots, _skip_exception, _skeleton_dist,
                    )
                session.commit()
                total_decisions += len(result.decisions)
                total_executed += len(result.executed)
                total_rejected += len(result.rejected)
                logger.info(
                    "paper_trading portfolio={} decisions={} executed={} rejected={}",
                    portfolio_id,
                    len(result.decisions),
                    len(result.executed),
                    len(result.rejected),
                )
        except Exception as exc:  # noqa: BLE001 — one portfolio must not kill the job
            logger.error("run_paper_trading failed for {}: {}", portfolio_id, exc)

    logger.info(
        "run_paper_trading complete: decisions={} executed={} rejected={}",
        total_decisions, total_executed, total_rejected,
    )
