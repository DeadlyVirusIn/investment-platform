"""Operator-triggered post-ingest paper cycle (one-shot, idempotent).

After fresh price bars + factor/regime snapshots + (optionally) chain
snapshots have landed for `--as-of`, run the existing paper runners
ONCE so eligible pending_next_bar trades convert into paper_trade /
options_paper_trade rows.

Strict invariants (never bypassed):
  * Paper-only — paper_only=TRUE on every options trade row;
    same-bar fills are forbidden by the runners themselves
    (`find_next_open` / `snapshot_at_utc::date > submitted_at::date`).
  * No live execution. No ML execution. No replay touch.
  * No continuous loop. Single shot, exits cleanly.
  * Each downstream runner enforces its own confirmation env
    (`EXPLORATORY_PAPER_CONFIRM`, `OPTIONS_PAPER_EXEC_CONFIRM`).
    The orchestrator never sets them — operator must pre-set them
    or the runner refuses with exit 2 and the orchestrator surfaces
    that as `skipped`.

Default env behaviour:
  RUN_STOCK_AFTER_INGEST=true            (strict paper, paper-only)
  RUN_EXPLORATORY_AFTER_INGEST=false
  RUN_OPTIONS_AFTER_INGEST=false
  RUN_OPTIONS_PROMOTION_EVAL_AFTER_INGEST=true   (dry-run only)

Usage:
  python -m scripts.run_post_ingest_paper_cycle
  python -m scripts.run_post_ingest_paper_cycle --as-of 2026-05-05 --commit
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import text


STOCK_ENV = "RUN_STOCK_AFTER_INGEST"
EXPL_ENV = "RUN_EXPLORATORY_AFTER_INGEST"
OPT_ENV = "RUN_OPTIONS_AFTER_INGEST"
PROMO_ENV = "RUN_OPTIONS_PROMOTION_EVAL_AFTER_INGEST"

EXPL_CONFIRM = "EXPLORATORY_PAPER_CONFIRM"
EXPL_CONFIRM_VALUE = "I_UNDERSTAND_THIS_SUBMITS_PAPER_TRADES"
OPT_CONFIRM = "OPTIONS_PAPER_EXEC_CONFIRM"
OPT_CONFIRM_VALUE = "I_UNDERSTAND_THIS_SUBMITS_OPTIONS_PAPER_TRADES"

ARTIFACT_DIR = Path("artifacts/post_ingest_cycle")
ARTIFACT_NAME = "cycle_{date}.json"


def _env_true(name: str, default: bool = False) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if not v:
        return default
    return v == "true"


def _argparse() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_post_ingest_paper_cycle",
        description=(
            "One-shot post-ingest paper cycle. Default dry-run. "
            "Strict stock execution may run in --commit; "
            "exploratory/options require explicit env opt-ins + "
            "the runner's own confirmation env."
        ),
    )
    p.add_argument("--as-of", default=None,
                   help="ISO date. Defaults to today UTC.")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="Default. No runners called.")
    p.add_argument("--commit", action="store_true",
                   help="Invoke the gated runners. Each runner still "
                        "enforces its own safety gates.")
    return p


def _row_counts(session) -> dict[str, int]:
    return {
        "paper_trade": session.execute(
            text("SELECT count(*) FROM paper_trade")
        ).scalar() or 0,
        "options_paper_trade": session.execute(
            text("SELECT count(*) FROM options_paper_trade")
        ).scalar() or 0,
        "options_strategy_outcome": session.execute(
            text("SELECT count(*) FROM options_strategy_outcome")
        ).scalar() or 0,
    }


def _readiness(session, as_of: dt.date) -> dict[str, Any]:
    pb = session.execute(text("""
        SELECT count(*) FROM price_bar
        WHERE timeframe = '1d' AND ts::date = :d
    """), {"d": as_of}).scalar() or 0
    pb_latest = session.execute(text(
        "SELECT max(ts::date) FROM price_bar WHERE timeframe = '1d'"
    )).scalar()
    fs = session.execute(text(
        "SELECT count(*) FROM factor_snapshot WHERE as_of_date = :d"
    ), {"d": as_of}).scalar() or 0
    rs = session.execute(text(
        "SELECT count(*) FROM regime_snapshot WHERE as_of_date = :d"
    ), {"d": as_of}).scalar() or 0
    chain = session.execute(text("""
        SELECT count(*) FROM options_chain_snapshot
        WHERE snapshot_at_utc::date = :d
    """), {"d": as_of}).scalar() or 0
    return {
        "as_of": as_of.isoformat(),
        "price_bar_count_today": pb,
        "price_bar_latest_date": (
            pb_latest.isoformat() if pb_latest else None
        ),
        "factor_snapshot_count_today": fs,
        "regime_snapshot_today": rs > 0,
        "options_chain_snapshot_count_today": chain,
    }


_PENDING_REASON = "execution_failure"
_PENDING_MARKER = "no price bar available after submitted_at"


def _pending_count(session, as_of: dt.date) -> int:
    """Count pending-next-bar entries in `run_paper_trading` skip
    JSONL. Matches the filter used by `/performance/paper/
    pending-fills`: reason='execution_failure' AND
    detail.exec_reason contains the next-bar marker."""
    skips_dir = Path("artifacts/paper_trading_skips")
    path = skips_dir / f"{as_of.isoformat()}.jsonl"
    if not path.exists():
        return 0
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("reason") != _PENDING_REASON:
            continue
        detail = row.get("detail") or {}
        exec_reason = (detail.get("exec_reason") or "").lower()
        if _PENDING_MARKER.lower() in exec_reason:
            n += 1
    return n


def _run_safe_stock(as_of: dt.date) -> dict[str, Any]:
    """Invoke run_paper_daily_safe.main() with --as-of."""
    from scripts.run_paper_daily_safe import main as safe_main
    rc = safe_main(["--as-of", as_of.isoformat()])
    return {"runner": "run_paper_daily_safe", "exit_code": rc}


def _run_exploratory(as_of: dt.date) -> dict[str, Any]:
    if os.environ.get(EXPL_CONFIRM, "") != EXPL_CONFIRM_VALUE:
        return {
            "runner": "run_exploratory_paper_exec",
            "skipped": True,
            "reason": (
                f"{EXPL_CONFIRM} not set to {EXPL_CONFIRM_VALUE}; "
                f"runner would refuse."
            ),
        }
    from scripts.run_exploratory_paper_exec import main as expl_main
    rc = expl_main(["--commit"])
    return {"runner": "run_exploratory_paper_exec", "exit_code": rc}


def _run_options(as_of: dt.date) -> dict[str, Any]:
    if os.environ.get(OPT_CONFIRM, "") != OPT_CONFIRM_VALUE:
        return {
            "runner": "run_options_paper_exec",
            "skipped": True,
            "reason": (
                f"{OPT_CONFIRM} not set to {OPT_CONFIRM_VALUE}; "
                f"runner would refuse."
            ),
        }
    from scripts.run_options_paper_exec import main as opt_main
    rc = opt_main(["--commit"])
    return {"runner": "run_options_paper_exec", "exit_code": rc}


def _run_outcomes(as_of: dt.date) -> dict[str, Any]:
    """Compute options strategy outcomes for as_of (write-only into
    options_strategy_outcome). NEVER touches paper trades."""
    from scripts.compute_options_strategy_outcomes import main as oc_main
    rc = oc_main(["--as-of", as_of.isoformat()])
    return {"runner": "compute_options_strategy_outcomes", "exit_code": rc}


def _run_promotion_eval(as_of: dt.date) -> dict[str, Any]:
    """Promotion eval is dry-run only here. Does not pass --apply."""
    from scripts.run_options_promotion_eval import main as promo_main
    rc = promo_main(["--dry-run", "--horizon", "5D",
                     "--unit", "strategy_name"])
    return {"runner": "run_options_promotion_eval", "exit_code": rc}


def main(argv: list[str] | None = None) -> int:
    args = _argparse().parse_args(argv)
    if args.as_of:
        try:
            as_of = dt.date.fromisoformat(args.as_of)
        except ValueError:
            sys.stderr.write(
                f"REFUSED: --as-of must be ISO date, got "
                f"{args.as_of!r}\n",
            )
            return 2
    else:
        as_of = dt.datetime.now(dt.timezone.utc).date()

    stock_on = _env_true(STOCK_ENV, default=True)
    expl_on = _env_true(EXPL_ENV, default=False)
    opt_on = _env_true(OPT_ENV, default=False)
    promo_on = _env_true(PROMO_ENV, default=True)

    logger.info(
        "[cycle] as_of={} mode={} stock={} expl={} opt={} promo_eval={}",
        as_of, "commit" if args.commit else "dry-run",
        stock_on, expl_on, opt_on, promo_on,
    )

    from apps.api.src.db import SessionLocal
    with SessionLocal() as session:
        before_counts = _row_counts(session)
        readiness = _readiness(session, as_of)
        pending_before = _pending_count(session, as_of)

    logger.info("[cycle.readiness] {}", readiness)
    logger.info(
        "[cycle.pending_before] count={} (paper_trade={}, "
        "options_paper_trade={})",
        pending_before, before_counts["paper_trade"],
        before_counts["options_paper_trade"],
    )

    plan: list[dict[str, Any]] = []
    if stock_on:
        plan.append({"step": "safe_stock_paper", "gated_by": STOCK_ENV})
    if expl_on:
        plan.append({"step": "exploratory_paper", "gated_by": EXPL_ENV})
    if opt_on and readiness["options_chain_snapshot_count_today"] > 0:
        plan.append({"step": "options_paper", "gated_by": OPT_ENV})
    elif opt_on:
        plan.append({
            "step": "options_paper", "gated_by": OPT_ENV,
            "skipped": True,
            "reason": (
                f"options_chain_snapshot count for {as_of} = 0 — "
                f"refuse to fabricate options fills."
            ),
        })
    plan.append({"step": "options_strategy_outcomes",
                 "gated_by": "always_on"})
    if promo_on:
        plan.append({"step": "options_promotion_eval_dry_run",
                     "gated_by": PROMO_ENV})

    logger.info("[cycle.plan] steps={}",
                [s["step"] for s in plan])

    results: list[dict[str, Any]] = []

    if not args.commit:
        logger.info("[cycle] dry-run — no runners invoked")
    else:
        if stock_on:
            try:
                results.append(_run_safe_stock(as_of))
            except Exception as exc:  # noqa: BLE001
                logger.error("[cycle] safe stock crashed: {}", exc)
                results.append({
                    "runner": "run_paper_daily_safe",
                    "error": str(exc),
                })
        if expl_on:
            try:
                results.append(_run_exploratory(as_of))
            except Exception as exc:  # noqa: BLE001
                logger.error("[cycle] exploratory crashed: {}", exc)
                results.append({
                    "runner": "run_exploratory_paper_exec",
                    "error": str(exc),
                })
        if opt_on:
            if readiness["options_chain_snapshot_count_today"] == 0:
                results.append({
                    "runner": "run_options_paper_exec",
                    "skipped": True,
                    "reason": "no chain snapshot today",
                })
            else:
                try:
                    results.append(_run_options(as_of))
                except Exception as exc:  # noqa: BLE001
                    logger.error("[cycle] options crashed: {}", exc)
                    results.append({
                        "runner": "run_options_paper_exec",
                        "error": str(exc),
                    })
        try:
            results.append(_run_outcomes(as_of))
        except Exception as exc:  # noqa: BLE001
            logger.error("[cycle] outcomes crashed: {}", exc)
            results.append({
                "runner": "compute_options_strategy_outcomes",
                "error": str(exc),
            })
        if promo_on:
            try:
                results.append(_run_promotion_eval(as_of))
            except Exception as exc:  # noqa: BLE001
                logger.error("[cycle] promotion eval crashed: {}", exc)
                results.append({
                    "runner": "run_options_promotion_eval",
                    "error": str(exc),
                })

    with SessionLocal() as session:
        after_counts = _row_counts(session)
        pending_after = _pending_count(session, as_of)
    deltas = {
        k: after_counts[k] - before_counts[k]
        for k in before_counts
    }

    logger.info(
        "[cycle.summary] stock_inserted={} options_inserted={} "
        "outcomes_inserted={} pending_before={} pending_after={}",
        deltas["paper_trade"], deltas["options_paper_trade"],
        deltas["options_strategy_outcome"],
        pending_before, pending_after,
    )

    artifact = {
        "schema_version": 1,
        "as_of_date": as_of.isoformat(),
        "mode": "commit" if args.commit else "dry-run",
        "env": {
            STOCK_ENV: stock_on, EXPL_ENV: expl_on,
            OPT_ENV: opt_on, PROMO_ENV: promo_on,
        },
        "readiness": readiness,
        "before_counts": before_counts,
        "after_counts": after_counts,
        "deltas": deltas,
        "pending_before": pending_before,
        "pending_after": pending_after,
        "plan": plan,
        "results": results,
        "safety": {
            "live_execution_enabled": False,
            "ml_can_affect_trades": False,
            "same_bar_fills_allowed": False,
            "replay_touched": False,
            "scheduler_started": False,
        },
        "notice": (
            "One-shot post-ingest paper cycle. Each downstream runner "
            "self-enforces paper-only, next-bar guard, liquidity, "
            "duplicate-position, and confirmation envs. Orchestrator "
            "never bypasses any of these."
        ),
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACT_DIR / ARTIFACT_NAME.format(date=as_of.isoformat())
    out_path.write_text(json.dumps(artifact, indent=2, default=str))
    logger.info("[cycle] wrote artifact: {}", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
