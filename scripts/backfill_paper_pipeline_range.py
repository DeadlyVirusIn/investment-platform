"""Phase 11W (incident fix) — backfill paper pipeline over a date range.

For each business date in [start, end]:
  1. Run engine pipeline (macro → regime → factor → candidates).
  2. Run scripts.run_paper_daily for the same date with --force-recompute.

Idempotent: every stage upserts. Re-running produces the same end
state without duplicating rows.

Usage:
    python -m scripts.backfill_paper_pipeline_range \\
        --start 2026-04-29 --end 2026-05-01

NEVER changes strategy logic, gates, sizing, or research_ro. Pure
orchestration helper to recover missed days.
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from typing import Sequence

from loguru import logger

from scripts.run_engine_pipeline import (
    run_for_date as run_engine_pipeline,
)


def _trading_days(
    start: dt.date, end: dt.date,
) -> list[dt.date]:
    """Mon-Fri only. We do not consult a holiday calendar here —
    paper_daily already handles non-trading dates by writing a
    'skipped' status row, which is the desired behaviour."""
    out: list[dt.date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur)
        cur += dt.timedelta(days=1)
    return out


def _run_paper_daily(
    as_of: dt.date,
    *,
    force_recompute: bool,
) -> int:
    """Invoke scripts.run_paper_daily as a subprocess so its
    process-level state (loguru config, signal handlers) is fully
    isolated from the orchestrator."""
    cmd = [
        sys.executable, "-m", "scripts.run_paper_daily",
        "--date", as_of.isoformat(),
    ]
    if force_recompute:
        cmd.append("--force-recompute")
    logger.info("invoking: {}", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=False)
    return proc.returncode


def backfill_range(
    start: dt.date,
    end: dt.date,
    *,
    dry_run: bool = False,
    skip_paper_daily: bool = False,
    allow_missing: bool = False,
) -> dict:
    days = _trading_days(start, end)
    summary: dict = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days_processed": [],
        "ok": True,
    }
    for d in days:
        per_day: dict = {"as_of": d.isoformat()}
        engine = run_engine_pipeline(d, dry_run=dry_run)
        per_day["engine"] = engine
        if not engine["ok"]:
            per_day["status"] = "engine_failed"
            if not allow_missing:
                summary["ok"] = False
                summary["days_processed"].append(per_day)
                logger.error(
                    "engine failed for {} (--allow-missing not set, halting)",
                    d,
                )
                break
            logger.warning(
                "engine failed for {} but --allow-missing set; continuing",
                d,
            )
        if not skip_paper_daily and engine["ok"]:
            rc = _run_paper_daily(d, force_recompute=True)
            per_day["paper_daily_rc"] = rc
            if rc != 0:
                per_day["status"] = "paper_daily_failed"
                summary["ok"] = False
                summary["days_processed"].append(per_day)
                if not allow_missing:
                    break
                continue
        per_day["status"] = "ok"
        summary["days_processed"].append(per_day)
    return summary


def _parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="backfill_paper_pipeline_range",
        description=(
            "Backfill paper pipeline (engine → paper_daily) for a "
            "range of trading dates. Idempotent."
        ),
    )
    p.add_argument(
        "--start",
        type=lambda s: dt.date.fromisoformat(s),
        required=True,
    )
    p.add_argument(
        "--end",
        type=lambda s: dt.date.fromisoformat(s),
        required=True,
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--skip-paper-daily", action="store_true")
    p.add_argument(
        "--allow-missing",
        action="store_true",
        help="Continue past stages that fail (e.g., missing data).",
    )
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse(argv)
    if args.start > args.end:
        logger.error("--start must be <= --end")
        return 2
    summary = backfill_range(
        args.start, args.end,
        dry_run=args.dry_run,
        skip_paper_daily=args.skip_paper_daily,
        allow_missing=args.allow_missing,
    )
    logger.info("backfill summary: {}", summary)
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
