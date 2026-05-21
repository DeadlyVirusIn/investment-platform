"""Nightly signal outcome evaluation pipeline — Phase 1.

Write-only. Does not influence ranker, ActionItem, paper_trade, or sizing.

Usage::

    python -m pipelines.evaluate_signals                 # today UTC
    python -m pipelines.evaluate_signals --as-of 2026-04-15
"""

from __future__ import annotations

import argparse
import datetime as dt

from loguru import logger

from apps.api.src.db import SessionLocal
from apps.api.src.domain.signal_evaluator.runner import evaluate_pending_signals


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate pending signals.")
    parser.add_argument(
        "--as-of", type=_parse_date, default=None,
        help="Date to evaluate against (default: today UTC).",
    )
    args = parser.parse_args()
    today = args.as_of or dt.date.today()

    with SessionLocal() as session:
        report = evaluate_pending_signals(session, today=today)

    logger.info(
        "SUMMARY total={} evaluated={} skipped={} timeouts={}",
        report.signals_total, report.signals_evaluated,
        report.signals_skipped, report.signals_timeout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
