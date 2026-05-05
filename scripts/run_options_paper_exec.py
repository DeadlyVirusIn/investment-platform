"""Operator-only controlled options paper-trading execution.

Submits up to N=2 options paper trades per run for the top-ranked
strategies from the strategy engine. Strict allow-list:

    LONG_CALL, BULL_CALL_SPREAD

Complex multi-leg strategies (iron_condor, credit spreads) are
explicitly blocked here. Live execution is impossible — every trade
is gated by `paper_only=TRUE` on `options_paper_trade` (DB-level
CHECK constraint).

Hard rules:
  * Default is dry-run.
  * `--commit` requires
    `OPTIONS_PAPER_EXEC_CONFIRM=I_UNDERSTAND_THIS_SUBMITS_OPTIONS_PAPER_TRADES`.
  * Next-bar fill model: a chain snapshot whose
    `snapshot_at_utc::date > submitted_at::date` must exist for the
    trade to fill. Otherwise → `pending_next_bar`, no DB write.
  * Liquidity gates inherited from the strategy endpoint (legs that
    failed liquidity were never offered as candidates).
  * Strategy whitelist enforced at submit time.
  * Max 2 trades per run regardless of top-N input.
  * `paper_only` flag is hard-coded `True`. Live execution flag
    `OPTIONS_LIVE_EXECUTION` does not exist and is never honored.

Usage:

    python -m scripts.run_options_paper_exec
    OPTIONS_PAPER_EXEC_CONFIRM=I_UNDERSTAND_THIS_SUBMITS_OPTIONS_PAPER_TRADES \\
      python -m scripts.run_options_paper_exec --commit

Exit codes:
  0  success
  2  refused (env confirmation, bad arg)
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from decimal import Decimal
from typing import Any

from loguru import logger
from sqlalchemy import text


CONFIRM_ENV = "OPTIONS_PAPER_EXEC_CONFIRM"
CONFIRM_VALUE = "I_UNDERSTAND_THIS_SUBMITS_OPTIONS_PAPER_TRADES"

# Hard caps — operator cannot override. paper-only invariant
# enforced at the DB CHECK level.
MAX_TRADES_PER_RUN = 2
DEFAULT_QTY_CONTRACTS = 1
ALLOWED_STRATEGIES = ("long_call", "bull_call_spread")
# Map shadow strategy names → DB CHECK enum names (added in
# alembic migration 062_opt_paper_strategy_ext).
DB_STRATEGY_NAME = {
    "long_call": "LONG_CALL",
    "bull_call_spread": "BULL_CALL_SPREAD",
}
STRATEGY_VERSION = "options-paper-exec-v1"
FILL_MODEL_VERSION = "next_bar_v1"


def _argparse() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_options_paper_exec",
        description="Operator-only controlled options paper-trading.",
    )
    p.add_argument("--limit", type=int, default=MAX_TRADES_PER_RUN,
                   help=f"Max trades to submit (capped at "
                        f"{MAX_TRADES_PER_RUN}).")
    p.add_argument("--qty", type=int, default=DEFAULT_QTY_CONTRACTS,
                   help="Contracts per leg (default 1).")
    p.add_argument("--commit", action="store_true",
                   help="Submit trades. Requires "
                        f"{CONFIRM_ENV}={CONFIRM_VALUE}.")
    return p


def _next_bar_chain_exists(session, underlying: str,
                           submitted_at: dt.datetime) -> bool:
    """Returns True iff `options_chain_snapshot` has a row for
    `underlying` whose `snapshot_at_utc::date` is strictly after
    `submitted_at::date`. Mirrors the next-bar fill guard used on
    stock side (`find_next_open`)."""
    row = session.execute(text("""
        SELECT 1 FROM options_chain_snapshot
        WHERE underlying = :u
          AND snapshot_at_utc::date > :d
        LIMIT 1
    """), {"u": underlying, "d": submitted_at.date()}).first()
    return row is not None


def _build_legs_payload(strategy: str, legs: list[dict[str, Any]],
                        qty: int) -> list[dict[str, Any]]:
    """Translate strategy-suggestion legs into options_paper_trade_leg
    rows. side stored as upper-case ('BUY' / 'SELL')."""
    out: list[dict[str, Any]] = []
    for i, leg in enumerate(legs):
        out.append({
            "leg_index": i,
            "option_symbol": leg["option_symbol"],
            "underlying": leg.get("underlying", ""),  # filled below
            "expiry": dt.date.fromisoformat(leg["expiry"]),
            "strike": Decimal(str(leg["strike"])),
            "option_type": leg["type"].upper(),
            "side": leg["action"].upper(),
            "qty": qty,
            "fill_price_dollars": Decimal(str(
                leg["ask"] if leg["action"] == "buy" else leg["bid"]
            )),
        })
    return out


def _compute_payoff(strategy: str, legs: list[dict[str, Any]],
                    qty: int) -> dict[str, Decimal]:
    """Compute entry_debit_or_credit, max_loss, max_profit, breakevens.

    Convention: `entry_credit_dollars` is signed net credit at entry.
    Long debit strategies → negative entry_credit. Credit spreads →
    positive entry_credit. (Schema accepts NULL too; we always set it.)
    """
    contracts_per = qty
    contract_multiplier = 100  # standard equity options multiplier

    if strategy == "long_call":
        leg = legs[0]
        ask = Decimal(str(leg["ask"]))
        strike = Decimal(str(leg["strike"]))
        debit = ask * contract_multiplier * contracts_per
        return {
            "entry_credit": -debit,            # debit paid → negative credit
            "max_loss": debit,                 # premium paid is max loss
            "max_profit": Decimal("9999999"),  # uncapped; sentinel
            "breakeven_lower": strike + ask,
            "breakeven_upper": None,
        }

    if strategy == "bull_call_spread":
        buy_leg = legs[0] if legs[0]["action"] == "buy" else legs[1]
        sell_leg = legs[1] if legs[0]["action"] == "buy" else legs[0]
        buy_ask = Decimal(str(buy_leg["ask"]))
        sell_bid = Decimal(str(sell_leg["bid"]))
        buy_strike = Decimal(str(buy_leg["strike"]))
        sell_strike = Decimal(str(sell_leg["strike"]))
        net_debit_per = buy_ask - sell_bid
        if net_debit_per <= 0:
            # Pathological data — refuse to fill.
            raise ValueError(
                f"bull_call_spread net_debit_per_share <= 0: "
                f"buy_ask={buy_ask} sell_bid={sell_bid}"
            )
        debit = net_debit_per * contract_multiplier * contracts_per
        max_profit_per = (sell_strike - buy_strike) - net_debit_per
        max_profit = max(
            Decimal("0"),
            max_profit_per * contract_multiplier * contracts_per,
        )
        return {
            "entry_credit": -debit,
            "max_loss": debit,
            "max_profit": max_profit,
            "breakeven_lower": buy_strike + net_debit_per,
            "breakeven_upper": None,
        }

    raise ValueError(f"unsupported strategy: {strategy}")


def _fetch_top_strategies(session) -> list[dict[str, Any]]:
    """Inline call into the suggestion logic via TestClient is heavy;
    instead, query the same source tables directly with the same
    filters: latest chain per natural key, joined to stock signal,
    filtered to allow-listed strategies, ranked by confidence."""
    from fastapi.testclient import TestClient
    from apps.api.src.main import app
    c = TestClient(app)
    r = c.get(
        "/api/performance/options/strategy-suggestions?limit=50"
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"strategy-suggestions failed: {r.status_code} {r.text[:200]}"
        )
    body = r.json()
    return body.get("items", [])


def main(argv: list[str] | None = None) -> int:
    args = _argparse().parse_args(argv)
    if args.limit < 1 or args.limit > MAX_TRADES_PER_RUN:
        sys.stderr.write(
            f"REFUSED: --limit must be 1..{MAX_TRADES_PER_RUN}\n"
        )
        return 2
    if args.qty < 1 or args.qty > 10:
        sys.stderr.write("REFUSED: --qty must be 1..10\n")
        return 2

    if args.commit:
        confirm = os.environ.get(CONFIRM_ENV, "")
        if confirm != CONFIRM_VALUE:
            sys.stderr.write(
                f"REFUSED: --commit requires {CONFIRM_ENV}={CONFIRM_VALUE}.\n"
            )
            return 2

    from apps.api.src.db import SessionLocal
    from apps.api.src.db.options_models import (
        OptionsPaperTrade, OptionsPaperTradeLeg,
    )

    logger.info(
        "[options-exec] mode=options_exploratory commit={} limit={} "
        "qty={} allowed_strategies={} max_per_run={} "
        "fill_model={} paper_only=True (DB CHECK enforced)",
        args.commit, args.limit, args.qty,
        ALLOWED_STRATEGIES, MAX_TRADES_PER_RUN, FILL_MODEL_VERSION,
    )

    candidates = _fetch_top_strategies(None)
    # Filter strict allow-list.
    candidates = [
        c for c in candidates
        if c.get("strategy") in ALLOWED_STRATEGIES
    ]
    candidates.sort(key=lambda c: -c.get("confidence", 0))
    candidates = candidates[: args.limit]

    if not candidates:
        logger.warning(
            "[options-exec] no allow-listed strategies in "
            "/strategy-suggestions output — nothing to do."
        )
        return 0

    submitted = 0
    pending = 0
    rejected = 0
    plan: list[dict[str, Any]] = []

    with SessionLocal() as session:
        now = dt.datetime.now(dt.timezone.utc)
        for cand in candidates:
            strategy = cand["strategy"]
            underlying = cand["underlying"]
            legs = cand["legs"]
            try:
                payoff = _compute_payoff(strategy, legs, args.qty)
            except ValueError as exc:
                logger.warning(
                    "[options-exec.rejected] {} {}: {}",
                    underlying, strategy, exc,
                )
                rejected += 1
                plan.append({
                    **cand, "result": f"rejected:{exc}",
                    "mode": "options_exploratory",
                })
                continue

            # Next-bar guard.
            has_next = _next_bar_chain_exists(session, underlying, now)
            if not has_next:
                logger.warning(
                    "[options-exec.pending] {} {} (conf={:.4f}) "
                    "→ pending_next_bar: no future chain snapshot for "
                    "{} after {} (paper-only, no fabrication)",
                    underlying, strategy, cand["confidence"],
                    underlying, now.date(),
                )
                pending += 1
                plan.append({
                    "underlying": underlying,
                    "strategy": strategy,
                    "confidence": cand["confidence"],
                    "legs_count": len(legs),
                    "reason": (
                        "no chain snapshot with "
                        "snapshot_at_utc::date > submitted_at::date"
                    ),
                    "result": "pending_next_bar",
                    "mode": "options_exploratory",
                })
                continue

            if not args.commit:
                logger.info(
                    "[options-exec.dryrun] would submit {} {} "
                    "(conf={:.4f}, max_loss=${} max_profit=${})",
                    underlying, strategy, cand["confidence"],
                    payoff["max_loss"], payoff["max_profit"],
                )
                plan.append({
                    "underlying": underlying,
                    "strategy": strategy,
                    "confidence": cand["confidence"],
                    "legs_count": len(legs),
                    "max_loss": float(payoff["max_loss"]),
                    "max_profit": float(payoff["max_profit"]),
                    "result": "dry_run_planned",
                    "mode": "options_exploratory",
                })
                continue

            # Commit path — INSERT options_paper_trade + legs.
            db_strategy_name = DB_STRATEGY_NAME[strategy]
            trade = OptionsPaperTrade(
                underlying=underlying,
                strategy_name=db_strategy_name,
                strategy_version=STRATEGY_VERSION,
                status="PROPOSED",
                opened_at=now,
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
            legs_payload = _build_legs_payload(strategy, legs, args.qty)
            for lp in legs_payload:
                lp["underlying"] = underlying
                session.add(OptionsPaperTradeLeg(
                    trade_id=trade.id, **lp,
                ))
            session.commit()
            submitted += 1
            logger.info(
                "[options-exec.submitted] trade_id={} {} {} "
                "(conf={:.4f}, max_loss=${} max_profit=${})",
                trade.id, underlying, db_strategy_name,
                cand["confidence"],
                payoff["max_loss"], payoff["max_profit"],
            )
            plan.append({
                "trade_id": trade.id,
                "underlying": underlying,
                "strategy": strategy,
                "confidence": cand["confidence"],
                "max_loss": float(payoff["max_loss"]),
                "max_profit": float(payoff["max_profit"]),
                "result": "submitted",
                "mode": "options_exploratory",
            })

    logger.info("=" * 68)
    logger.info("[options-exec] SUMMARY (paper-only, capped)")
    logger.info("[options-exec]   submitted        : {}", submitted)
    logger.info("[options-exec]   pending_next_bar : {}", pending)
    logger.info("[options-exec]   rejected         : {}", rejected)
    logger.info("[options-exec]   plan_rows        : {}", len(plan))
    logger.info("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
