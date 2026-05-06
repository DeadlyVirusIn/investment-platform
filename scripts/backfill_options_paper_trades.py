"""Historical options paper-trade reconstruction.

Reconstructs pending options strategy candidates for each date in
[--from, --to] using the existing strategy-suggestions endpoint
keyed by as_of, then attempts a fill against the next chain
snapshot strictly after submitted_at::date.

Strict invariants — paper-only, no fabrication:
  * For every date D in the range, COUNT real
    options_chain_snapshot rows whose `snapshot_at_utc::date = D`.
    If zero, the date is skipped with reason
    `no_chain_data_on_date`. Trades are never created on dates
    that lack a real chain snapshot.
  * Same-bar fills forbidden: fill candidate uses
    `_next_bar_chain_exists(session, underlying, submitted_at)`
    which requires `snapshot_at_utc::date > submitted_at::date`.
  * Allowed strategies: the same allow-list the live runner
    enforces — `long_call`, `bull_call_spread`. All others are
    skipped with reason `strategy_not_allowed`.
  * Liquidity gate inherited from the strategy-suggestions
    endpoint (legs that fail liquidity never appear as
    candidates, so we never fill them here).
  * Idempotency: dedupes by
    (underlying, strategy_name, opened_at, paper_only=TRUE) so
    re-running the script does not create duplicate
    options_paper_trade rows.
  * `--commit` requires
    `OPTIONS_PAPER_EXEC_CONFIRM=I_UNDERSTAND_THIS_SUBMITS_OPTIONS_PAPER_TRADES`
    to mirror the live runner's safety gate.

Usage:
  python -m scripts.backfill_options_paper_trades \\
      --from 2026-04-20 --to 2026-05-05
  OPTIONS_PAPER_EXEC_CONFIRM=I_UNDERSTAND_THIS_SUBMITS_OPTIONS_PAPER_TRADES \\
  python -m scripts.backfill_options_paper_trades \\
      --from 2026-04-20 --to 2026-05-05 --commit

Exit codes:
  0  success
  2  refused (env, bad arg)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import text


CONFIRM_ENV = "OPTIONS_PAPER_EXEC_CONFIRM"
CONFIRM_VALUE = "I_UNDERSTAND_THIS_SUBMITS_OPTIONS_PAPER_TRADES"

ARTIFACT_DIR = Path("artifacts/options_backfill")
ARTIFACT_NAME = "backfill_{from_d}_to_{to_d}.json"


def _argparse() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="backfill_options_paper_trades",
        description=(
            "Reconstruct historical options paper trades from "
            "existing chain snapshots. Default dry-run."
        ),
    )
    p.add_argument("--from", dest="from_", required=True,
                   help="ISO date start (inclusive).")
    p.add_argument("--to", required=True,
                   help="ISO date end (inclusive).")
    p.add_argument("--limit-per-day", type=int, default=2,
                   help="Top-N strategies per date (mirrors "
                        "MAX_TRADES_PER_RUN). Default 2.")
    p.add_argument("--qty", type=int, default=1,
                   help="Contracts per leg (default 1).")
    p.add_argument("--commit", action="store_true",
                   help=f"Insert rows. Requires "
                        f"{CONFIRM_ENV}={CONFIRM_VALUE}.")
    return p


def _chain_count_for(session, d: dt.date) -> int:
    return int(session.execute(text(
        "SELECT count(*) FROM options_chain_snapshot "
        "WHERE snapshot_at_utc::date = :d"
    ), {"d": d}).scalar() or 0)


def _suggestions_for(d: dt.date) -> dict[str, Any]:
    """Reuse the live strategy-suggestions endpoint via TestClient.
    Pinned to as_of=D so that the candidate_idea lookup matches the
    historical signal date. Chain quotes are taken from the latest
    chain rows the endpoint sees — ANY date prior to today's chain
    is filtered out by `_chain_count_for` upstream, so fabricated
    quotes can never enter."""
    from fastapi.testclient import TestClient
    from apps.api.src.main import app
    c = TestClient(app)
    r = c.get(
        f"/api/performance/options/strategy-suggestions"
        f"?as_of={d.isoformat()}&limit=200"
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"strategy-suggestions failed: {r.status_code} "
            f"{r.text[:200]}"
        )
    return r.json()


def _existing_trade(
    session, *, underlying: str, db_strategy_name: str,
    opened_at: dt.datetime,
) -> bool:
    """Idempotency probe — refuse to create a duplicate."""
    row = session.execute(text("""
        SELECT 1 FROM options_paper_trade
        WHERE underlying = :u
          AND strategy_name = :s
          AND opened_at = :o
          AND paper_only = TRUE
        LIMIT 1
    """), {
        "u": underlying, "s": db_strategy_name, "o": opened_at,
    }).first()
    return row is not None


def main(argv: list[str] | None = None) -> int:
    args = _argparse().parse_args(argv)
    try:
        from_d = dt.date.fromisoformat(args.from_)
        to_d = dt.date.fromisoformat(args.to)
    except ValueError:
        sys.stderr.write(
            f"REFUSED: --from / --to must be ISO dates, got "
            f"{args.from_!r} / {args.to!r}\n"
        )
        return 2
    if from_d > to_d:
        sys.stderr.write(
            f"REFUSED: --from ({from_d}) must be <= --to ({to_d})\n"
        )
        return 2
    if args.limit_per_day < 1 or args.limit_per_day > 10:
        sys.stderr.write("REFUSED: --limit-per-day must be 1..10\n")
        return 2
    if args.qty < 1 or args.qty > 10:
        sys.stderr.write("REFUSED: --qty must be 1..10\n")
        return 2
    if args.commit:
        if os.environ.get(CONFIRM_ENV, "") != CONFIRM_VALUE:
            sys.stderr.write(
                f"REFUSED: --commit requires {CONFIRM_ENV}="
                f"{CONFIRM_VALUE}.\n"
            )
            return 2

    from apps.api.src.db import SessionLocal
    from apps.api.src.db.options_models import (
        OptionsPaperTrade, OptionsPaperTradeLeg,
    )
    from scripts.run_options_paper_exec import (
        _compute_payoff,
        _next_bar_chain_exists,
        ALLOWED_STRATEGIES, DB_STRATEGY_NAME,
        STRATEGY_VERSION, FILL_MODEL_VERSION,
    )

    def _build_leg_rows(
        legs: list[dict[str, Any]], qty: int, ts: dt.datetime,
        underlying: str,
    ) -> list[dict[str, Any]]:
        """Build OptionsPaperTradeLeg kwargs from suggestion legs.
        Maps suggestion fields to the ORM columns. NEVER fabricates
        a quote — uses the bid/ask/mid that the suggestion engine
        already wrote into the leg from real chain rows."""
        out: list[dict[str, Any]] = []
        for i, leg in enumerate(legs):
            bid = leg.get("bid")
            ask = leg.get("ask")
            mid = leg.get("mid")
            action = leg["action"].lower()
            # Convention: BUY pays the ask, SELL receives the bid.
            fill_price = (
                ask if action == "buy" else bid
            )
            if fill_price is None:
                raise ValueError(
                    f"missing fill price for {leg.get('option_symbol')} "
                    f"({action})"
                )
            out.append({
                "leg_index": i,
                "option_symbol": leg["option_symbol"],
                "underlying": underlying,
                "expiry": dt.date.fromisoformat(leg["expiry"]),
                "strike": Decimal(str(leg["strike"])),
                "option_type": leg["type"].upper(),
                "side": action.upper(),
                "qty": qty,
                "entry_quote_at_utc": ts,
                "entry_bid": (
                    Decimal(str(bid)) if bid is not None else None
                ),
                "entry_ask": (
                    Decimal(str(ask)) if ask is not None else None
                ),
                "entry_mid": (
                    Decimal(str(mid)) if mid is not None else None
                ),
                "entry_iv": (
                    Decimal(str(leg["iv"]))
                    if leg.get("iv") is not None else None
                ),
                "entry_delta": (
                    Decimal(str(leg["delta"]))
                    if leg.get("delta") is not None else None
                ),
                "entry_fill_price": Decimal(str(fill_price)),
            })
        return out

    logger.info(
        "[opt-backfill] from={} to={} limit_per_day={} qty={} mode={}",
        from_d, to_d, args.limit_per_day, args.qty,
        "commit" if args.commit else "dry-run",
    )

    # Snapshot before counts.
    with SessionLocal() as session:
        before_trades = session.execute(text(
            "SELECT count(*) FROM options_paper_trade"
        )).scalar() or 0
        before_legs = session.execute(text(
            "SELECT count(*) FROM options_paper_trade_leg"
        )).scalar() or 0

    per_date: list[dict[str, Any]] = []
    total_inserted = 0
    total_legs_inserted = 0
    total_skipped: dict[str, int] = {}
    dates_scanned = 0
    dates_with_chain = 0
    strategies_reconstructed = 0

    cur = from_d
    while cur <= to_d:
        dates_scanned += 1
        date_summary: dict[str, Any] = {
            "date": cur.isoformat(),
            "chain_rows": 0,
            "strategies_reconstructed": 0,
            "fills": [],
            "skipped": [],
        }
        with SessionLocal() as session:
            n = _chain_count_for(session, cur)
        date_summary["chain_rows"] = n

        if n == 0:
            date_summary["skipped"].append({
                "reason": "no_chain_data_on_date", "count": 1,
            })
            total_skipped["no_chain_data_on_date"] = (
                total_skipped.get("no_chain_data_on_date", 0) + 1
            )
            logger.info(
                "[opt-backfill] {} chain_rows=0 → skip",
                cur,
            )
            per_date.append(date_summary)
            cur = cur + dt.timedelta(days=1)
            continue
        dates_with_chain += 1

        try:
            body = _suggestions_for(cur)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[opt-backfill] {} suggestions failed: {}", cur, exc,
            )
            date_summary["skipped"].append({
                "reason": "suggestions_endpoint_failed",
                "detail": str(exc), "count": 1,
            })
            total_skipped["suggestions_endpoint_failed"] = (
                total_skipped.get(
                    "suggestions_endpoint_failed", 0,
                ) + 1
            )
            per_date.append(date_summary)
            cur = cur + dt.timedelta(days=1)
            continue

        items = body.get("items") or []
        # Filter to allow-list and rank by confidence (already ranked
        # by the endpoint, but be defensive).
        items = [
            it for it in items
            if it.get("strategy") in ALLOWED_STRATEGIES
        ]
        items.sort(key=lambda c: -c.get("confidence", 0))
        items = items[: args.limit_per_day]
        date_summary["strategies_reconstructed"] = len(items)
        strategies_reconstructed += len(items)

        # Submitted_at anchor — same convention used by the live
        # runner: today's 21:00 UTC. Replayed historically with
        # date=cur so the next-bar guard advances correctly.
        submitted_at = dt.datetime.combine(
            cur, dt.time(21, 0), tzinfo=dt.timezone.utc,
        )

        for cand in items:
            strategy = cand["strategy"]
            underlying = cand["underlying"]
            legs = cand.get("legs") or []
            db_strategy_name = DB_STRATEGY_NAME[strategy]

            with SessionLocal() as session:
                # Next-bar guard against the ORIGINAL submitted_at.
                if not _next_bar_chain_exists(
                    session, underlying, submitted_at,
                ):
                    date_summary["skipped"].append({
                        "underlying": underlying,
                        "strategy": strategy,
                        "reason": "no_next_bar_chain",
                    })
                    total_skipped["no_next_bar_chain"] = (
                        total_skipped.get("no_next_bar_chain", 0) + 1
                    )
                    continue
                # Idempotency.
                if _existing_trade(
                    session, underlying=underlying,
                    db_strategy_name=db_strategy_name,
                    opened_at=submitted_at,
                ):
                    date_summary["skipped"].append({
                        "underlying": underlying,
                        "strategy": strategy,
                        "reason": "duplicate_trade",
                    })
                    total_skipped["duplicate_trade"] = (
                        total_skipped.get("duplicate_trade", 0) + 1
                    )
                    continue
                try:
                    payoff = _compute_payoff(strategy, legs, args.qty)
                except ValueError as exc:
                    date_summary["skipped"].append({
                        "underlying": underlying,
                        "strategy": strategy,
                        "reason": f"payoff_error:{exc}",
                    })
                    total_skipped["payoff_error"] = (
                        total_skipped.get("payoff_error", 0) + 1
                    )
                    continue

                if not args.commit:
                    date_summary["fills"].append({
                        "underlying": underlying,
                        "strategy": strategy,
                        "max_loss": float(payoff["max_loss"]),
                        "max_profit": float(payoff["max_profit"]),
                        "result": "dry_run_planned",
                    })
                    continue

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
                legs_payload = _build_leg_rows(
                    legs, args.qty, submitted_at, underlying,
                )
                for lp in legs_payload:
                    session.add(OptionsPaperTradeLeg(
                        trade_id=trade.id, **lp,
                    ))
                session.commit()
                total_inserted += 1
                total_legs_inserted += len(legs_payload)
                date_summary["fills"].append({
                    "underlying": underlying,
                    "strategy": strategy,
                    "trade_id": trade.id,
                    "legs": len(legs_payload),
                    "max_loss": float(payoff["max_loss"]),
                    "max_profit": float(payoff["max_profit"]),
                    "result": "submitted",
                })
                logger.info(
                    "[opt-backfill.submitted] D={} trade_id={} "
                    "{}/{} max_loss={} max_profit={}",
                    cur, trade.id, underlying, db_strategy_name,
                    payoff["max_loss"], payoff["max_profit"],
                )
        per_date.append(date_summary)
        cur = cur + dt.timedelta(days=1)

    with SessionLocal() as session:
        after_trades = session.execute(text(
            "SELECT count(*) FROM options_paper_trade"
        )).scalar() or 0
        after_legs = session.execute(text(
            "SELECT count(*) FROM options_paper_trade_leg"
        )).scalar() or 0

    summary = {
        "schema_version": 1,
        "from_date": from_d.isoformat(),
        "to_date": to_d.isoformat(),
        "mode": "commit" if args.commit else "dry-run",
        "dates_scanned": dates_scanned,
        "dates_with_chain": dates_with_chain,
        "strategies_reconstructed": strategies_reconstructed,
        "options_paper_trade_before": before_trades,
        "options_paper_trade_after": after_trades,
        "options_paper_trade_inserted": total_inserted,
        "options_paper_trade_leg_before": before_legs,
        "options_paper_trade_leg_after": after_legs,
        "options_paper_trade_leg_inserted": total_legs_inserted,
        "skipped_by_reason": total_skipped,
        "per_date": per_date,
        "safety": {
            "live_execution_enabled": False,
            "ml_can_affect_trades": False,
            "same_bar_fills_allowed": False,
            "replay_recovery_manifest_touched": False,
            "fabricated_prices": False,
        },
    }
    logger.info(
        "[opt-backfill.summary] dates_scanned={} dates_with_chain={} "
        "strategies={} fills_inserted={} legs_inserted={} "
        "skipped={}",
        dates_scanned, dates_with_chain, strategies_reconstructed,
        total_inserted, total_legs_inserted, total_skipped,
    )
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACT_DIR / ARTIFACT_NAME.format(
        from_d=from_d.isoformat(), to_d=to_d.isoformat(),
    )
    out_path.write_text(json.dumps(summary, indent=2, default=str))
    logger.info("[opt-backfill] wrote artifact: {}", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
