"""Phase 11W (incident fix) — single-date engine pipeline orchestrator.

Runs the four read+write stages required to produce a usable
context for the strict paper engine:

  1. backfill_macro_features  → public.context_daily
  2. compute_regime_snapshot   → public.regime_snapshot
  3. compute_factor_snapshots  → public.factor_snapshot
  4. generate_stock_candidates → public.candidate_idea

This is the gap that left target_date pinned to 2026-04-28: each
stage already exists in the codebase but was never wired into a
scheduler. This helper bundles them into a single deterministic
invocation, idempotent against existing rows.

Usage:
    python -m scripts.run_engine_pipeline --as-of 2026-05-01

Exit codes:
    0 — all four stages completed
    2 — a critical stage failed (caller should NOT proceed to
        run_paper_daily for this date)
    3 — required upstream data missing (e.g., no price_bar for
        the date), reported with detail

NEVER changes strategy, thresholds, gate logic, sizing, or
anything in research_ro / engine_b. Pure orchestration of existing
stages.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys
from typing import Sequence

from loguru import logger
from sqlalchemy import text

from apps.api.src.db import SessionLocal


_FETCH_FROM_FRED = True


def _stage_max_dates() -> dict[str, str | None]:
    """Snapshot the latest as_of_date in each downstream table for
    diagnostic logging."""
    with SessionLocal() as s:
        rows = s.execute(text(
            """
            SELECT
              (SELECT max(ts)::date FROM price_bar) AS price_bar,
              (SELECT max(as_of_date) FROM context_daily) AS context_daily,
              (SELECT max(as_of_date) FROM regime_snapshot) AS regime_snapshot,
              (SELECT max(as_of_date) FROM factor_snapshot) AS factor_snapshot,
              (SELECT max(as_of_date) FROM candidate_idea) AS candidate_idea
            """
        )).mappings().first()
    return {
        k: (v.isoformat() if v is not None else None)
        for k, v in (rows or {}).items()
    }


def _has_price_bar_for(as_of: dt.date) -> bool:
    """Confirm at least one bar exists at or before as_of."""
    with SessionLocal() as s:
        n = s.execute(
            text(
                "SELECT count(*) FROM price_bar "
                "WHERE ts::date <= :d"
            ),
            {"d": as_of},
        ).scalar_one()
    return int(n) > 0


# ---------------------------------------------------------------------------
# Stage runners — each delegates to existing code; no duplication.
# ---------------------------------------------------------------------------


def _run_macro_backfill(
    as_of: dt.date, *, dry_run: bool,
) -> int:
    """Invoke scripts.backfill_macro_features for a single-date window."""
    import scripts.backfill_macro_features as macro_mod

    args = [
        "--start", as_of.isoformat(),
        "--end", as_of.isoformat(),
    ]
    if dry_run:
        args.append("--dry-run")
    else:
        args.extend(["--commit", "--confirm-commit", "YES"])
    return macro_mod.main(args)


async def _run_regime_snapshot(as_of: dt.date) -> None:
    from apps.worker.src.jobs.compute_regime_snapshot import (
        compute_regime_snapshot,
    )
    await compute_regime_snapshot(as_of=as_of)


async def _run_factor_snapshots(as_of: dt.date) -> None:
    from apps.worker.src.jobs.compute_factor_snapshots import (
        compute_factor_snapshots,
    )
    await compute_factor_snapshots(as_of=as_of)


async def _run_generate_candidates(as_of: dt.date) -> None:
    from apps.worker.src.jobs.generate_stock_candidates import (
        generate_stock_candidates,
    )
    await generate_stock_candidates(as_of=as_of)


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


def run_for_date(
    as_of: dt.date,
    *,
    dry_run: bool = False,
    skip_macro: bool = False,
    skip_regime: bool = False,
    skip_factor: bool = False,
    skip_candidate: bool = False,
) -> dict:
    """Run all four stages for `as_of`. Returns a result dict with
    per-stage status. Caller decides whether to proceed to
    run_paper_daily based on `result['ok']`."""
    result: dict = {
        "as_of": as_of.isoformat(),
        "dry_run": dry_run,
        "stages": {},
        "ok": True,
        "max_dates_before": _stage_max_dates(),
    }

    if not _has_price_bar_for(as_of):
        result["ok"] = False
        result["error"] = (
            f"no price_bar at or before {as_of}; cannot run engine pipeline"
        )
        logger.error(result["error"])
        return result

    # Stage 1 — macro
    if skip_macro:
        result["stages"]["macro_backfill"] = "skipped"
    else:
        try:
            rc = _run_macro_backfill(as_of, dry_run=dry_run)
            if rc != 0:
                result["ok"] = False
                result["stages"]["macro_backfill"] = f"failed:rc={rc}"
            else:
                result["stages"]["macro_backfill"] = "ok"
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["stages"]["macro_backfill"] = f"crash:{exc!r}"
            logger.error("macro_backfill crash: {}", exc)

    # Stage 2 — regime
    if skip_regime:
        result["stages"]["regime_snapshot"] = "skipped"
    elif result["ok"] or skip_macro:
        try:
            asyncio.run(_run_regime_snapshot(as_of))
            result["stages"]["regime_snapshot"] = "ok"
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["stages"]["regime_snapshot"] = f"crash:{exc!r}"
            logger.error("regime_snapshot crash: {}", exc)
    else:
        result["stages"]["regime_snapshot"] = "skipped:upstream_failed"

    # Stage 3 — factor
    if skip_factor:
        result["stages"]["factor_snapshots"] = "skipped"
    elif result["ok"] or skip_macro or skip_regime:
        try:
            asyncio.run(_run_factor_snapshots(as_of))
            result["stages"]["factor_snapshots"] = "ok"
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["stages"]["factor_snapshots"] = f"crash:{exc!r}"
            logger.error("factor_snapshots crash: {}", exc)
    else:
        result["stages"]["factor_snapshots"] = "skipped:upstream_failed"

    # Stage 4 — candidates
    if skip_candidate:
        result["stages"]["generate_stock_candidates"] = "skipped"
    elif result["ok"] or skip_macro or skip_regime or skip_factor:
        try:
            asyncio.run(_run_generate_candidates(as_of))
            result["stages"]["generate_stock_candidates"] = "ok"
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["stages"]["generate_stock_candidates"] = (
                f"crash:{exc!r}"
            )
            logger.error("generate_stock_candidates crash: {}", exc)
    else:
        result["stages"]["generate_stock_candidates"] = (
            "skipped:upstream_failed"
        )

    result["max_dates_after"] = _stage_max_dates()
    return result


def _parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_engine_pipeline",
        description=(
            "Run the daily engine pipeline (macro → regime → factor "
            "→ candidates) for a single as-of date. NEVER changes "
            "strategy logic; pure orchestration of existing stages."
        ),
    )
    p.add_argument(
        "--as-of",
        type=lambda s: dt.date.fromisoformat(s),
        required=True,
        help="ISO date (YYYY-MM-DD).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Run macro stage in dry-run; non-DB stages still execute.",
    )
    p.add_argument("--skip-macro", action="store_true")
    p.add_argument("--skip-regime", action="store_true")
    p.add_argument("--skip-factor", action="store_true")
    p.add_argument("--skip-candidate", action="store_true")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse(argv)
    result = run_for_date(
        args.as_of,
        dry_run=args.dry_run,
        skip_macro=args.skip_macro,
        skip_regime=args.skip_regime,
        skip_factor=args.skip_factor,
        skip_candidate=args.skip_candidate,
    )
    logger.info("engine pipeline result: {}", result)
    if not result["ok"]:
        if "error" in result and "no price_bar" in result["error"]:
            return 3
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
