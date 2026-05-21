"""Nightly Phase 2 scorecard refresh — read-only analytics.

Computes rolling metrics (default 30 days) for every distinct
signal.strategy_id. Writes model_scorecard rows; nothing reads them yet.

Usage::

    python -m pipelines.scorecard_nightly                       # today, 30d
    python -m pipelines.scorecard_nightly --as-of 2026-03-13 --window-days 90
"""

from __future__ import annotations

import argparse
import datetime as dt

from loguru import logger

from apps.api.src.db import SessionLocal
from apps.api.src.domain.model_scorecard.runner import (
    DEFAULT_WINDOW_DAYS,
    compute_and_persist,
    list_distinct_models,
)


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", type=_parse_date, default=None)
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument(
        "--model", default=None,
        help="Compute a single model only; default = all distinct strategy_ids.",
    )
    args = parser.parse_args()
    today = args.as_of or dt.date.today()

    with SessionLocal() as session:
        models = [args.model] if args.model else list_distinct_models(session)
        if not models:
            logger.info("[scorecard_nightly] no signal rows found; nothing to compute")
            return 0
        logger.info(
            "[scorecard_nightly] start today={} window={}d models={}",
            today, args.window_days, models,
        )
        for m in models:
            compute_and_persist(
                session, model_name=m, today=today, window_days=args.window_days,
            )

    logger.info("[scorecard_nightly] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
