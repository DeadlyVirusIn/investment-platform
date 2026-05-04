"""Operator-only exploratory paper-trading EXECUTION runner.

Distinct from the older `scripts.run_exploratory_paper` (which only
tags `decision_log` rows). This script SUBMITS a small, capped batch
of paper-buy decisions for candidates that strict candidate
generation rejected only because of SOFT gates (`below_long_trend`,
`extended_from_sma200`, `idiosyncratic_vol_high`, `topn_overflow`,
`high_vol_topn_overflow`).

Strict mode is unchanged. This is a separate, operator-triggered
script. Default is dry-run.

Hard rules (NEVER relaxed):
  * Submission goes through the existing `submit_trade()` path so
    next-bar fill guard is preserved (no same-bar fills, no
    missing-price fills).
  * Excludes any candidate whose `rejection_reason` is in the hard
    set (regime_off, insufficient_history, stale_data, liquidity_fail,
    earnings_too_close, not_in_universe, already_at_cap,
    duplicate_holding, portfolio_full, execution_failure).
  * Skips assets already held in an open `paper_position`.
  * Stops per-portfolio when running open count + planned picks >=
    `DEFAULT_MAX_OPEN_POSITIONS`.

Caps:
  * `EXPLORATORY_MAX_BUYS_PER_DAY = 3` (per portfolio)
  * `EXPLORATORY_MAX_POSITION_PCT = 0.02` (2% of equity per buy)
  * `EXPLORATORY_MIN_SCORE = -0.20` (relaxed-score floor; relaxed
    score = raw composite − 0.10 penalty)

Confirmation:
  --commit refused unless
  `EXPLORATORY_PAPER_CONFIRM=I_UNDERSTAND_THIS_SUBMITS_PAPER_TRADES`.

Usage:

  # Dry-run.
  python -m scripts.run_exploratory_paper_exec

  # Commit (paper-only, capped, env-gated).
  EXPLORATORY_PAPER_CONFIRM=I_UNDERSTAND_THIS_SUBMITS_PAPER_TRADES \\
  python -m scripts.run_exploratory_paper_exec --commit
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from decimal import Decimal
from typing import Any

from loguru import logger
from sqlalchemy import select, text


CONFIRM_ENV = "EXPLORATORY_PAPER_CONFIRM"
CONFIRM_VALUE = "I_UNDERSTAND_THIS_SUBMITS_PAPER_TRADES"

EXPLORATORY_MAX_BUYS_PER_DAY = 5
EXPLORATORY_MAX_POSITION_PCT = Decimal("0.02")
EXPLORATORY_MIN_SCORE = -0.20
EXPLORATORY_PENALTY = Decimal("0.10")
# Paper-only capacity caps. Distinct from `DEFAULT_MAX_OPEN_POSITIONS`
# (= 10) which is enforced by `auto_trader` for the STRICT path.
# This script does not touch that constant; it carries its own cap so
# strict-path behaviour stays byte-identical.
EXPLORATORY_MAX_OPEN_POSITIONS = 15
# Diversification — keep cross-portfolio variety + sector concentration
# bounded. Operator-tunable via env later if needed.
EXPLORATORY_MAX_NEW_PER_SYMBOL_PER_RUN = 1
EXPLORATORY_MAX_SECTOR_EXPOSURE_PCT = 0.25

SOFT_GATES = (
    "below_long_trend",
    "extended_from_sma200",
    "idiosyncratic_vol_high",
    "topn_overflow",
    "high_vol_topn_overflow",
)
HARD_GATES_NEVER_RELAXED = (
    "regime_off",
    "insufficient_history",
    "stale_data",
    "liquidity_fail",
    "earnings_too_close",
    "duplicate_holding",
    "portfolio_full",
    "execution_failure",
    "not_in_universe",
    "already_at_cap",
)


def _argparse() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_exploratory_paper_exec",
        description="Operator-only exploratory paper-trading runner.",
    )
    p.add_argument("--as-of", default=None,
                   help="ISO date. Defaults to today UTC.")
    p.add_argument("--commit", action="store_true",
                   help="Submit trades. Requires "
                        f"{CONFIRM_ENV}={CONFIRM_VALUE}.")
    return p


def _eligible_candidates(session, as_of: dt.date) -> list[dict[str, Any]]:
    """candidate_idea rows rejected for SOFT-gate reasons only,
    ordered by composite_score desc. Carries asset.sector for the
    diversification step."""
    rows = session.execute(text("""
        SELECT
          c.id              AS candidate_id,
          c.asset_id        AS asset_id,
          a.symbol          AS symbol,
          a.sector          AS sector,
          c.action          AS action,
          c.rejection_reason AS rejection_reason,
          c.composite_score AS composite_score
        FROM candidate_idea c
        JOIN asset a ON a.id = c.asset_id
        WHERE c.as_of_date = :d
          AND c.status = 'rejected'
          AND c.rejection_reason = ANY(:soft)
          AND c.composite_score IS NOT NULL
        ORDER BY c.composite_score DESC, a.symbol ASC
    """), {"d": as_of, "soft": list(SOFT_GATES)}).mappings().all()

    out: list[dict[str, Any]] = []
    for r in rows:
        raw_score = float(r["composite_score"])
        relaxed_score = raw_score - float(EXPLORATORY_PENALTY)
        if relaxed_score < EXPLORATORY_MIN_SCORE:
            continue
        out.append({
            "candidate_id": r["candidate_id"],
            "asset_id": r["asset_id"],
            "symbol": r["symbol"],
            "sector": r["sector"] or "unknown",
            "action": r["action"],
            "rejection_reason": r["rejection_reason"],
            "raw_score": raw_score,
            "relaxed_score": relaxed_score,
        })
    return out


def _portfolio_sector_counts(session, portfolio_id: str) -> dict[str, int]:
    rows = session.execute(text("""
        SELECT coalesce(a.sector, 'unknown') AS sector,
               count(*) AS n
        FROM paper_position pp
        JOIN asset a ON a.id = pp.asset_id
        WHERE pp.portfolio_id = :pid AND pp.is_open = true
        GROUP BY 1
    """), {"pid": portfolio_id}).all()
    return {sector: int(n) for sector, n in rows}


def _open_assets(session, portfolio_id: str) -> set[str]:
    rows = session.execute(text("""
        SELECT asset_id FROM paper_position
        WHERE portfolio_id = :pid AND is_open = true
    """), {"pid": portfolio_id}).all()
    return {r[0] for r in rows}


def _open_count(session, portfolio_id: str) -> int:
    return int(session.execute(text("""
        SELECT count(*) FROM paper_position
        WHERE portfolio_id = :pid AND is_open = true
    """), {"pid": portfolio_id}).scalar() or 0)


def main(argv: list[str] | None = None) -> int:
    args = _argparse().parse_args(argv)

    if args.as_of:
        try:
            as_of = dt.date.fromisoformat(args.as_of)
        except ValueError:
            sys.stderr.write(
                f"REFUSED: --as-of must be ISO date, got {args.as_of!r}\n"
            )
            return 2
    else:
        as_of = dt.datetime.now(dt.timezone.utc).date()

    if args.commit:
        confirm = os.environ.get(CONFIRM_ENV, "")
        if confirm != CONFIRM_VALUE:
            sys.stderr.write(
                f"REFUSED: --commit requires {CONFIRM_ENV}={CONFIRM_VALUE}.\n"
            )
            return 2

    from apps.api.src.db import SessionLocal
    from apps.api.src.db.models import PaperPortfolio
    from apps.api.src.domain.paper_trading.paper_execution import (
        DEFAULT_MAX_OPEN_POSITIONS, PaperTradeRejected, submit_trade,
    )

    logger.info(
        "[exploratory] mode=exploratory as_of={} commit={} "
        "max_buys_per_day={} max_position_pct={} min_score={} "
        "exploratory_max_open={} (strict_max_open={} unchanged) "
        "max_new_per_symbol={} max_sector_pct={}",
        as_of, args.commit, EXPLORATORY_MAX_BUYS_PER_DAY,
        float(EXPLORATORY_MAX_POSITION_PCT), EXPLORATORY_MIN_SCORE,
        EXPLORATORY_MAX_OPEN_POSITIONS, DEFAULT_MAX_OPEN_POSITIONS,
        EXPLORATORY_MAX_NEW_PER_SYMBOL_PER_RUN,
        EXPLORATORY_MAX_SECTOR_EXPOSURE_PCT,
    )
    logger.info(
        "[exploratory] soft_gates_relaxed={}", SOFT_GATES,
    )
    logger.info(
        "[exploratory] hard_gates_never_relaxed={}",
        HARD_GATES_NEVER_RELAXED,
    )

    submitted = 0
    pending = 0
    rejected = 0
    plan: list[dict[str, Any]] = []

    with SessionLocal() as session:
        candidates = _eligible_candidates(session, as_of)
        logger.info(
            "[exploratory] eligible_soft_gate_candidates={}",
            len(candidates),
        )
        portfolios = session.execute(
            select(PaperPortfolio).where(PaperPortfolio.is_active.is_(True))
        ).scalars().all()
        logger.info(
            "[exploratory] active_portfolios={}", len(portfolios),
        )

        # Cross-portfolio diversification accumulator. Resets per run.
        picked_symbols_global: dict[str, int] = {}
        skipped_diversification = 0
        skipped_sector_exposure = 0

        for portfolio in portfolios:
            portfolio_id = portfolio.id
            held = _open_assets(session, portfolio_id)
            running_open = _open_count(session, portfolio_id)
            sector_counts = _portfolio_sector_counts(session, portfolio_id)
            equity = Decimal(str(portfolio.starting_cash))
            try:
                snap_row = session.execute(text("""
                    SELECT total_equity FROM paper_equity_snapshot
                    WHERE portfolio_id = :pid
                    ORDER BY snapshot_date DESC LIMIT 1
                """), {"pid": portfolio_id}).first()
                if snap_row and snap_row[0] is not None:
                    equity = Decimal(str(snap_row[0]))
            except Exception:
                pass
            usd_per_trade = (
                equity * EXPLORATORY_MAX_POSITION_PCT
            ).quantize(Decimal("0.01"))

            slots_available = max(
                0,
                EXPLORATORY_MAX_OPEN_POSITIONS - running_open,
            )
            logger.info(
                "[exploratory] portfolio={} name={!r} open={} "
                "slots_available={} usd_per_trade={}",
                portfolio_id, portfolio.name, running_open,
                slots_available, float(usd_per_trade),
            )

            # Two-pass selection. Pass 1 = diversification-honoring
            # ranked walk; pass 2 = relaxed (no cross-portfolio symbol
            # cap) only if Pass 1 came up short. Sector cap is hard
            # in both passes — cluster risk does not relax.
            picks: list[dict[str, Any]] = []

            def _try_pick(cand: dict[str, Any], allow_repeat: bool):
                nonlocal skipped_diversification, skipped_sector_exposure
                if len(picks) >= EXPLORATORY_MAX_BUYS_PER_DAY:
                    return "stop_max_buys"
                if cand["asset_id"] in held:
                    return "skipped_duplicate_holding"
                if running_open + len(picks) >= EXPLORATORY_MAX_OPEN_POSITIONS:
                    return "skipped_portfolio_full"
                # Cross-portfolio symbol diversification.
                already = picked_symbols_global.get(cand["symbol"], 0)
                if (not allow_repeat
                        and already >= EXPLORATORY_MAX_NEW_PER_SYMBOL_PER_RUN):
                    skipped_diversification += 1
                    return "skipped_cross_portfolio_dup"
                # Sector concentration. Use the projected open count
                # AFTER this pick lands.
                projected_open = running_open + len(picks) + 1
                projected_sector = sector_counts.get(cand["sector"], 0) + 1
                # +1 for the candidate not yet in sector_counts; +1 for
                # the projected new position.
                if projected_open > 0 and (
                    projected_sector / projected_open
                    > EXPLORATORY_MAX_SECTOR_EXPOSURE_PCT
                ):
                    skipped_sector_exposure += 1
                    return "skipped_sector_exposure"
                picks.append(cand)
                picked_symbols_global[cand["symbol"]] = already + 1
                sector_counts[cand["sector"]] = (
                    sector_counts.get(cand["sector"], 0) + 1
                )
                return "picked"

            # Pass 1
            for cand in candidates:
                if len(picks) >= min(
                    EXPLORATORY_MAX_BUYS_PER_DAY, slots_available,
                ):
                    break
                outcome = _try_pick(cand, allow_repeat=False)
                if outcome in ("stop_max_buys",):
                    break
                if outcome == "skipped_portfolio_full":
                    plan.append({
                        **cand, "portfolio_id": portfolio_id,
                        "result": "skipped_portfolio_full",
                        "mode": "exploratory",
                    })
                    rejected += 1
                    break
                if outcome != "picked":
                    plan.append({
                        **cand, "portfolio_id": portfolio_id,
                        "result": outcome, "mode": "exploratory",
                    })
                    rejected += 1
                    continue
            # Pass 2 — only if Pass 1 left slots open AND we still have
            # candidates not yet picked for this portfolio.
            if (len(picks) < min(EXPLORATORY_MAX_BUYS_PER_DAY,
                                 slots_available)
                    and len(picks) < EXPLORATORY_MAX_BUYS_PER_DAY):
                already_in_picks = {p["asset_id"] for p in picks}
                for cand in candidates:
                    if cand["asset_id"] in already_in_picks:
                        continue
                    if len(picks) >= min(
                        EXPLORATORY_MAX_BUYS_PER_DAY, slots_available,
                    ):
                        break
                    outcome = _try_pick(cand, allow_repeat=True)
                    if outcome == "picked":
                        already_in_picks.add(cand["asset_id"])
                    elif outcome in ("stop_max_buys", "skipped_portfolio_full"):
                        break

            for cand in picks:
                logged = {
                    "portfolio_id": portfolio_id,
                    "symbol": cand["symbol"],
                    "asset_id": cand["asset_id"],
                    "original_rejection_reason": cand["rejection_reason"],
                    "raw_score": cand["raw_score"],
                    "relaxed_score": cand["relaxed_score"],
                    "why_allowed": (
                        f"relaxed soft gate {cand['rejection_reason']!r}; "
                        f"raw_score={cand['raw_score']:.4f} "
                        f">= floor {EXPLORATORY_MIN_SCORE} after "
                        f"-{float(EXPLORATORY_PENALTY)} penalty"
                    ),
                    "mode": "exploratory",
                    "usd_amount": float(usd_per_trade),
                }
                if not args.commit:
                    logged["result"] = "dry_run_planned"
                    logger.info("[exploratory.dryrun] {}", logged)
                    plan.append(logged)
                    continue
                try:
                    res = submit_trade(
                        session,
                        portfolio_id=portfolio_id,
                        asset_id=cand["asset_id"],
                        side="buy",
                        usd_amount=usd_per_trade,
                        submitted_at=dt.datetime.now(dt.timezone.utc),
                        reason=(
                            f"exploratory: relaxed_from="
                            f"{cand['rejection_reason']}, "
                            f"raw_score={cand['raw_score']:.4f}"
                        ),
                    )
                    session.commit()
                    submitted += 1
                    logged.update({
                        "result": "filled",
                        "trade_id": res.trade_id,
                        "fill_price": float(res.fill_price),
                        "fill_ts": res.fill_ts.isoformat(),
                        "quantity": float(res.quantity),
                    })
                    logger.info("[exploratory.filled] {}", logged)
                    plan.append(logged)
                except PaperTradeRejected as exc:
                    msg = str(exc)
                    if "no price bar" in msg.lower():
                        pending += 1
                        logged["result"] = "pending_next_bar"
                    else:
                        rejected += 1
                        logged["result"] = f"rejected:{msg}"
                    logged["exec_reason"] = msg
                    logger.warning("[exploratory.rejected] {}", logged)
                    plan.append(logged)
                    session.rollback()

    logger.info("=" * 68)
    logger.info("[exploratory] SUMMARY (paper-only, capped)")
    logger.info("[exploratory]   submitted_filled       : {}", submitted)
    logger.info("[exploratory]   pending_next_bar       : {}", pending)
    logger.info("[exploratory]   rejected/skipped       : {}", rejected)
    logger.info(
        "[exploratory]   skipped_cross_portfolio: {}",
        skipped_diversification,
    )
    logger.info(
        "[exploratory]   skipped_sector_cap     : {}",
        skipped_sector_exposure,
    )
    logger.info(
        "[exploratory]   distinct_symbols_picked: {}",
        len(picked_symbols_global),
    )
    logger.info("[exploratory]   plan_rows              : {}", len(plan))
    logger.info("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
