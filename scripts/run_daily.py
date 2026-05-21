"""Daily live-forward pipeline CLI.

Usage::

    # Run now (for today UTC)
    python -m scripts.run_daily

    # Rerun a specific date (ignores lock)
    python -m scripts.run_daily --as-of 2026-04-17 --force

    # Dry run (read-only health checks, no writes)
    python -m scripts.run_daily --dry-run

    # Inspect latest run status
    python -m scripts.run_daily --inspect
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

from loguru import logger

from apps.api.src.domain.ops.daily_runner import (
    AlreadyRan,
    latest_run_status,
    run_daily_pipeline,
)


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", type=_parse_date, default=None,
                        help="Run date (YYYY-MM-DD). Default today UTC.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run checks without writing anything.")
    parser.add_argument("--force", action="store_true",
                        help="Override duplicate-execution lock.")
    parser.add_argument("--inspect", action="store_true",
                        help="Print latest run status JSON and exit.")
    args = parser.parse_args()

    if args.inspect:
        status = latest_run_status()
        if status is None:
            logger.info("[inspect] no daily runs recorded yet")
            return 0
        print(json.dumps(status, indent=2, default=str))
        return 0

    try:
        result = run_daily_pipeline(
            args.as_of, dry_run=args.dry_run, force=args.force,
        )
    except AlreadyRan as exc:
        logger.error("[daily] {}", exc)
        return 2

    print(json.dumps({
        "run_date": str(result.run_date),
        "status": result.status,
        "stage_failed": result.stage_failed,
        "alert_count": len(result.alerts),
        "summary": result.summary,
    }, indent=2, default=str))

    if result.status == "failed":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
