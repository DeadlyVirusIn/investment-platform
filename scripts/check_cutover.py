"""Phase 1.6 cutover readiness CLI — human summary + JSON.

Usage::

    python -m scripts.check_cutover
    python -m scripts.check_cutover --today 2026-04-21 --required-days 7
    python -m scripts.check_cutover --json-only
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

from apps.api.src.db import SessionLocal
from apps.api.src.domain.cutover.check import (
    REQUIRED_CONSECUTIVE_DAYS,
    CutoverReport,
    check_cutover_ready,
)


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _print_summary(r: CutoverReport) -> None:
    status = "READY ✓" if r.ready else "NOT READY ✗"
    print(f"Cutover: {status}")
    print(f"  required_days:         {r.required_days}")
    print(f"  consecutive_days_ok:   {r.consecutive_days_ok}")
    print(f"  rows_examined:         {r.rows_examined}")
    print(f"  missing_days:          {len(r.missing_days)}")
    print(f"  failing_days:          {len(r.failing_days)}")
    print(f"  non_consecutive:       {r.non_consecutive}")
    print(f"  signal_count_variance: {r.signal_count_variance}")
    print(f"  max_score_delta:       {r.max_score_delta:.6g}")
    print(f"  avg_score_delta:       {r.avg_score_delta:.6g}")
    if r.warnings:
        print("  warnings:")
        for w in r.warnings:
            print(f"    - {w}")
    if not r.ready:
        print("  blocking reasons:")
        for reason in r.reasons:
            print(f"    - {reason}")
        if r.missing_days:
            print("  missing days detail:")
            for d in r.missing_days:
                print(f"    - {d}")
        if r.failing_days:
            print("  failing days detail:")
            for d in r.failing_days:
                print(f"    - {d}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--today", type=_parse_date, default=None)
    parser.add_argument("--required-days", type=int, default=REQUIRED_CONSECUTIVE_DAYS)
    parser.add_argument(
        "--json-only", action="store_true",
        help="Print JSON to stdout only (no human summary).",
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        report = check_cutover_ready(
            session, today=args.today, required_days=args.required_days,
        )

    if not args.json_only:
        _print_summary(report)
        print()

    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.ready else 1


if __name__ == "__main__":
    sys.exit(main())
