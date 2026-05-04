"""SAFE_WORKER_MODE — one-shot stock paper trading runner.

Executes the live stock-paper-trading pipeline ONCE then exits. NO
loops, NO scheduling, NO daemon behavior.

Pipeline:
  1. generate_stock_candidates           (worker job — writes candidate_idea)
  2. run_recommendations_for_all_accounts (worker job — writes recommendation)
  3. selector evaluation (read-only diagnostic — logs SelectorInputs +
     fire/reject + reason; does not write paper_trade_log)
  4. run_paper_trading                   (worker job — writes paper_trade
                                          + paper_position via auto_trader)
  5. print summary, exit

Strict scope:
  * Stock paper trading only. Options pipeline NOT touched.
  * No replay rows mutated. (Replay rows were tagged via the manifest
    in earlier phases; this script only writes new live rows produced
    by the existing jobs above.)
  * No DB schema change. No threshold change. No business-logic
    change. No new compose service. No new cron entry.
  * SAFE_WORKER_MODE flag is local to this script — never set in any
    shared config or env that other code reads.

Docker invocation:
    docker compose -f infra/compose/docker-compose.yml \\
        --env-file .env run --rm worker-tickloop \\
        python -m scripts.run_paper_daily_safe

Exit codes:
  0  pipeline completed (regardless of zero-trade outcomes)
  1  pipeline crashed in a stage; see logs
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import text

# Local-only flag — surfaced for clarity in logs. NOT exported.
SAFE_WORKER_MODE = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _row_counts(session) -> dict[str, int]:
    """Snapshot counts that bracket each stage."""
    out: dict[str, int] = {}
    queries = (
        ("candidate_idea_today", text(
            "SELECT count(*) FROM candidate_idea WHERE as_of_date = :d"
        )),
        ("recommendation_today", text(
            "SELECT count(*) FROM recommendation "
            "WHERE generated_at::date = :d"
        )),
        ("paper_trade_today", text(
            "SELECT count(*) FROM paper_trade "
            "WHERE fill_ts::date = :d"
        )),
        ("paper_trade_total", text(
            "SELECT count(*) FROM paper_trade"
        )),
        ("paper_trade_log_today", text(
            "SELECT count(*) FROM paper_trade_log "
            "WHERE entry_date = :d"
        )),
    )
    for key, q in queries:
        try:
            params = {"d": dt.date.today()} if ":d" in q.text else {}
            out[key] = int(session.execute(q, params).scalar() or 0)
        except Exception as exc:  # noqa: BLE001
            out[key] = -1
            logger.warning("count {} failed: {}", key, exc)
    return out


def _log_selector(as_of: dt.date) -> dict[str, Any]:
    """Read-only diagnostic: pull the most-recent context_daily +
    paper_run_log gating rows for `as_of` and run the pure selector
    function. Does NOT write paper_trade_log; that path is owned by
    `scripts.run_paper_daily` when the operator chooses to run it.

    If gating values aren't materialized for the date, log
    `skip_reason="gates_not_materialized_for_date"` and proceed
    without fabricating inputs."""
    from apps.api.src.db import SessionLocal
    from apps.api.src.data.context.production import (
        classify_production_context,
    )
    from apps.api.src.data.strategy.selector import (
        SelectorInputs, select,
    )

    out: dict[str, Any] = {
        "ran": False,
        "fire": None,
        "engine": None,
        "reason": None,
        "inputs": None,
        "skip_reason": None,
    }
    try:
        with SessionLocal() as s:
            # Pull gating booleans from the most-recent paper_run_log
            # row at or before `as_of`. Schema is permissive — fall
            # back to context_daily when columns aren't present.
            gates_favorable: int | None = None
            try:
                row = s.execute(text(
                    "SELECT gates_favorable FROM paper_run_log "
                    "WHERE as_of_date <= :d "
                    "ORDER BY as_of_date DESC LIMIT 1"
                ), {"d": as_of}).first()
                gates_favorable = int(row[0]) if row and row[0] is not None else None
            except Exception:
                gates_favorable = None

            # P15 / credit / rates booleans — read from any
            # available diagnostic surface; missing values are NOT
            # fabricated.
            p15_entry = False
            credit_stable = False
            rates_calm = False
            try:
                ctx_rows = s.execute(text(
                    "SELECT key, value FROM context_daily "
                    "WHERE as_of_date = :d"
                ), {"d": as_of}).all()
                ctx_map = {r[0]: r[1] for r in ctx_rows}
                p15_entry = bool(ctx_map.get("p15_entry", False))
                credit_stable = bool(ctx_map.get("credit_stable", False))
                rates_calm = bool(ctx_map.get("rates_calm", False))
            except Exception:
                pass

        if gates_favorable is None:
            out["skip_reason"] = "gates_not_materialized_for_date"
            logger.warning(
                "[3/4 selector] gates_favorable unavailable for {} — "
                "diagnostic skip, no fabrication",
                as_of,
            )
            return out

        ctx = classify_production_context(gates_favorable=gates_favorable)
        inputs = SelectorInputs(
            p15_entry=p15_entry,
            credit_stable=credit_stable,
            rates_calm=rates_calm,
            production_context=ctx,
        )
        decision = select(inputs)
        out["ran"] = True
        out["fire"] = bool(decision.fire)
        out["engine"] = decision.engine
        out["reason"] = decision.reason
        out["inputs"] = {
            "p15_entry": p15_entry,
            "credit_stable": credit_stable,
            "rates_calm": rates_calm,
            "gates_favorable": gates_favorable,
            "stress_regime": ctx.stress_regime,
            "directional_regime": ctx.directional_regime,
        }
        logger.info(
            "[3/4 selector] engine={} fire={} reason={!r}",
            decision.engine, decision.fire, decision.reason,
        )
        logger.info("[3/4 selector] inputs={}", out["inputs"])
    except Exception as exc:  # noqa: BLE001
        out["skip_reason"] = (
            f"selector_eval_error: {type(exc).__name__}: {exc}"
        )
        logger.warning(
            "[3/4 selector] evaluation failed: {} — diagnostic only, "
            "no rows written",
            exc,
        )
    return out


def _read_paper_trading_skips(as_of: dt.date) -> list[dict[str, Any]]:
    """run_paper_trading writes per-symbol skip detail under
    artifacts/paper_trading_skips/. Surface the latest dump so the
    operator sees exactly why each candidate was rejected by the
    auto-trader gating."""
    skips_path = Path("artifacts/paper_trading_skips") / f"{as_of}.json"
    if not skips_path.exists():
        return []
    try:
        return json.loads(skips_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------
async def _stage_generate_candidates(as_of: dt.date) -> int:
    from apps.api.src.db import SessionLocal
    from apps.worker.src.jobs.generate_stock_candidates import (
        generate_stock_candidates,
    )
    with SessionLocal() as s:
        before = int(s.execute(text(
            "SELECT count(*) FROM candidate_idea WHERE as_of_date = :d"
        ), {"d": as_of}).scalar() or 0)
    logger.info("[1/4 candidates] start as_of={} (before={})",
                as_of, before)
    await generate_stock_candidates(as_of)
    with SessionLocal() as s:
        after = int(s.execute(text(
            "SELECT count(*) FROM candidate_idea WHERE as_of_date = :d"
        ), {"d": as_of}).scalar() or 0)
        # Surface symbols for visibility.
        symbols = [
            r[0] for r in s.execute(text(
                "SELECT a.symbol FROM candidate_idea c "
                "JOIN asset a ON a.id = c.asset_id "
                "WHERE c.as_of_date = :d "
                "ORDER BY a.symbol LIMIT 100"
            ), {"d": as_of}).all()
        ]
    delta = after - before
    logger.info(
        "[1/4 candidates] inserted={} total_today={} symbols={}",
        delta, after, symbols,
    )
    return delta


async def _stage_run_recommendations() -> int:
    from apps.api.src.db import SessionLocal
    from apps.worker.src.jobs.registry import (
        run_recommendations_for_all_accounts,
    )
    today = dt.date.today()
    with SessionLocal() as s:
        before = int(s.execute(text(
            "SELECT count(*) FROM recommendation "
            "WHERE generated_at::date = :d"
        ), {"d": today}).scalar() or 0)
    logger.info("[2/4 recommendations] start (before_today={})", before)
    await run_recommendations_for_all_accounts()
    with SessionLocal() as s:
        after = int(s.execute(text(
            "SELECT count(*) FROM recommendation "
            "WHERE generated_at::date = :d"
        ), {"d": today}).scalar() or 0)
    delta = after - before
    logger.info(
        "[2/4 recommendations] inserted_today={} total_today={}",
        delta, after,
    )
    return delta


async def _stage_run_paper_trading(as_of: dt.date) -> dict[str, Any]:
    from apps.api.src.db import SessionLocal
    from apps.worker.src.jobs.run_paper_trading import run_paper_trading
    with SessionLocal() as s:
        before = int(s.execute(text(
            "SELECT count(*) FROM paper_trade WHERE fill_ts::date = :d"
        ), {"d": as_of}).scalar() or 0)
    logger.info(
        "[4/4 paper_trading] start as_of={} (before_today={})",
        as_of, before,
    )
    inserted_ids: list[str] = []
    error: str | None = None
    try:
        await run_paper_trading(as_of=as_of)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        logger.error("[4/4 paper_trading] crash: {}", error)
    with SessionLocal() as s:
        rows = s.execute(text(
            "SELECT id FROM paper_trade "
            "WHERE fill_ts::date = :d "
            "ORDER BY fill_ts DESC"
        ), {"d": as_of}).all()
        inserted_ids = [r[0] for r in rows][:before:-1] if before else [
            r[0] for r in rows
        ]
        after = len(rows)
    delta = after - before
    logger.info(
        "[4/4 paper_trading] inserted={} total_today={} ids_sample={}",
        delta, after, inserted_ids[:5],
    )
    skips = _read_paper_trading_skips(as_of)
    if skips:
        logger.info(
            "[4/4 paper_trading] per-symbol skips={}",
            len(skips),
        )
        for s_row in skips[:25]:
            logger.info("  skip {}", s_row)
    return {
        "inserted_count": delta,
        "total_today": after,
        "inserted_ids": inserted_ids,
        "skips": skips,
        "error": error,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _argparse() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_paper_daily_safe",
        description="One-shot SAFE_WORKER_MODE stock paper trading runner.",
    )
    p.add_argument(
        "--as-of", default=None,
        help="ISO date (YYYY-MM-DD). Defaults to today UTC.",
    )
    return p


async def _amain(as_of: dt.date) -> int:
    logger.info(
        "[safe-runner] SAFE_WORKER_MODE={} as_of={} stock-only",
        SAFE_WORKER_MODE, as_of,
    )

    # Stage 1
    try:
        cand_delta = await _stage_generate_candidates(as_of)
    except Exception as exc:  # noqa: BLE001
        logger.error("[safe-runner] candidate generation failed: {}", exc)
        return 1

    # Stage 2
    try:
        rec_delta = await _stage_run_recommendations()
    except Exception as exc:  # noqa: BLE001
        logger.error("[safe-runner] recommendations failed: {}", exc)
        return 1

    # Stage 3 — diagnostic only
    selector_diag = _log_selector(as_of)

    # Stage 4
    pt_result = await _stage_run_paper_trading(as_of)

    # Summary
    logger.info("=" * 68)
    logger.info("[safe-runner] EXECUTION SUMMARY (stock paper trading)")
    logger.info("[safe-runner]   Candidates inserted today : {}", cand_delta)
    logger.info("[safe-runner]   Recommendations today     : {}", rec_delta)
    logger.info(
        "[safe-runner]   Selector fire             : {}  engine={}",
        selector_diag.get("fire"), selector_diag.get("engine"),
    )
    logger.info(
        "[safe-runner]   Paper trades inserted     : {}",
        pt_result["inserted_count"],
    )
    logger.info(
        "[safe-runner]   Paper trades total today  : {}",
        pt_result["total_today"],
    )
    logger.info("=" * 68)

    # Root cause readout if zero trades.
    if pt_result["inserted_count"] == 0:
        bits: list[str] = []
        if cand_delta == 0:
            bits.append("no candidates produced (stage 1 zero)")
        if rec_delta == 0:
            bits.append("no recommendations generated (stage 2 zero)")
        if selector_diag.get("fire") is False:
            bits.append(
                f"selector did not fire: {selector_diag.get('reason')}"
            )
        elif selector_diag.get("skip_reason"):
            bits.append(
                f"selector eval skipped: {selector_diag['skip_reason']}"
            )
        if pt_result.get("skips"):
            n = len(pt_result["skips"])
            bits.append(f"{n} per-symbol skip(s) — see logs above")
        if pt_result.get("error"):
            bits.append(f"paper_trading crash: {pt_result['error']}")
        if not bits:
            bits.append(
                "no obvious blocker — check candidate→recommendation→fill window"
            )
        logger.warning(
            "[safe-runner] ROOT CAUSE (zero new paper_trade rows):"
        )
        for b in bits:
            logger.warning("  - {}", b)

    return 0


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
    return asyncio.run(_amain(as_of))


if __name__ == "__main__":
    sys.exit(main())
