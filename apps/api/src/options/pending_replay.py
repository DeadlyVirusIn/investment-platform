"""Options pending-replay — fill prior days' stuck strategy
decisions once a future chain snapshot exists.

Mirrors the stock-side `paper_trading.pending_replay`.

Strict invariants:
  * Same-bar fills forbidden — uses the runner's existing
    `find_next_open` equivalent (`_next_bar_chain_exists`) which
    requires `snapshot_at_utc::date > submitted_at::date`.
  * Original submitted_at is preserved verbatim.
  * Liquidity / freshness gates inherited from the runner.
  * No fabricated chain quotes — fills only when a real later
    snapshot is present.
  * `replay_recovery_manifest` never touched.
  * Marker `<date>.replayed.jsonl` written even on zero-fill so
    the same date is not re-scanned forever.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from loguru import logger

from apps.api.src.options.pending_storage import (
    REPLAYED_SUFFIX, SKIPS_DIR, PENDING_REASON,
    collect_pending_dates, read_pending_for_date, write_marker,
)


def _replay_one_date(
    *, original_date: dt.date,
    SessionFactory,
    skips_dir: Path = SKIPS_DIR,
) -> dict[str, Any]:
    """Re-attempt every pending strategy entry for `original_date`.
    Each entry is fed back through the existing options paper-exec
    fill path with the ORIGINAL submitted_at preserved."""
    rows = read_pending_for_date(
        as_of=original_date, skips_dir=skips_dir,
    )
    pending_rows = [
        r for r in rows if r.get("reason") == PENDING_REASON
    ]
    if not pending_rows:
        return {"attempted": 0, "filled": 0, "still_pending": 0}

    from apps.api.src.db.options_models import (
        OptionsPaperTrade, OptionsPaperTradeLeg,
    )
    from scripts.run_options_paper_exec import (
        _compute_payoff, _build_legs_payload, _next_bar_chain_exists,
        DB_STRATEGY_NAME, ALLOWED_STRATEGIES,
        STRATEGY_VERSION, FILL_MODEL_VERSION,
    )

    attempted = 0
    filled = 0
    still_pending = 0
    rejected = 0
    fills: list[dict[str, Any]] = []

    for row in pending_rows:
        strategy = row.get("strategy")
        if strategy not in ALLOWED_STRATEGIES:
            rejected += 1
            continue
        underlying = row["underlying"]
        legs = row.get("legs") or []
        try:
            submitted_at = dt.datetime.fromisoformat(
                row["submitted_at"]
            )
        except (KeyError, ValueError):
            rejected += 1
            continue

        attempted += 1
        with SessionFactory() as session:
            if not _next_bar_chain_exists(
                session, underlying, submitted_at,
            ):
                still_pending += 1
                continue
            try:
                payoff = _compute_payoff(strategy, legs, qty=1)
            except ValueError as exc:
                logger.warning(
                    "[opt-pending-replay] payoff failed for {} {}: {}",
                    underlying, strategy, exc,
                )
                rejected += 1
                continue

            db_strategy_name = DB_STRATEGY_NAME[strategy]
            trade = OptionsPaperTrade(
                underlying=underlying,
                strategy_name=db_strategy_name,
                strategy_version=STRATEGY_VERSION,
                status="PROPOSED",
                opened_at=submitted_at,
                entry_credit_dollars=payoff["entry_credit"],
                max_loss_dollars=payoff["max_loss"],
                max_profit_dollars=payoff["max_profit"],
                breakeven_lower=payoff["breakeven_lower"],
                breakeven_upper=payoff["breakeven_upper"],
                fees_total_dollars=Decimal("0"),
                fill_model_version=FILL_MODEL_VERSION,
                paper_only=True,
            )
            session.add(trade)
            session.flush()
            try:
                legs_payload = _build_legs_payload(
                    strategy, legs, qty=1,
                    entry_quote_at_utc=submitted_at,
                )
            except ValueError as exc:
                session.rollback()
                logger.warning(
                    "[opt-pending-replay.rejected] {} {} legs build "
                    "failed: {}", underlying, strategy, exc,
                )
                rejected += 1
                continue
            for lp in legs_payload:
                lp["underlying"] = underlying
                session.add(OptionsPaperTradeLeg(
                    trade_id=trade.id, **lp,
                ))
            session.commit()
            filled += 1
            fills.append({
                "trade_id": trade.id, "underlying": underlying,
                "strategy": db_strategy_name,
                "submitted_at": submitted_at.isoformat(),
            })
            logger.info(
                "[opt-pending-replay.filled] D={} trade_id={} "
                "{}/{} submitted_at={}",
                original_date, trade.id, underlying,
                db_strategy_name, submitted_at.isoformat(),
            )

    summary = {
        "attempted": attempted, "filled": filled,
        "still_pending": still_pending, "rejected": rejected,
        "fills": fills,
    }
    write_marker(
        as_of=original_date, summary=summary,
        skips_dir=skips_dir,
    )
    return summary


def replay_all_options_pending(
    *, before: dt.date,
    SessionFactory,
    skips_dir: Path = SKIPS_DIR,
    from_date: dt.date | None = None,
    force: bool = False,
    max_dates: int = 30,
) -> dict[str, Any]:
    dates = collect_pending_dates(
        before=before, skips_dir=skips_dir,
        from_date=from_date, force=force,
    )[:max_dates]
    logger.info(
        "[opt-pending-replay] candidate dates from={} before={} "
        "force={} : {}",
        from_date, before, force,
        [d.isoformat() for d in dates],
    )
    per_date = []
    total_attempted = 0
    total_filled = 0
    total_still_pending = 0
    total_rejected = 0
    for d in dates:
        s = _replay_one_date(
            original_date=d, SessionFactory=SessionFactory,
            skips_dir=skips_dir,
        )
        per_date.append({"date": d.isoformat(), **s})
        total_attempted += s["attempted"]
        total_filled += s["filled"]
        total_still_pending += s["still_pending"]
        total_rejected += s.get("rejected", 0)
    return {
        "dates_replayed": [d.isoformat() for d in dates],
        "attempted_total": total_attempted,
        "filled_total": total_filled,
        "still_pending_total": total_still_pending,
        "rejected_total": total_rejected,
        "per_date": per_date,
        "from_date": from_date.isoformat() if from_date else None,
        "before": before.isoformat(),
        "force": force,
    }
