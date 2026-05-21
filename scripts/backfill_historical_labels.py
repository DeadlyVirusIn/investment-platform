"""Backfill historical_label rows for ML research phase.

Usage::

    python -m scripts.backfill_historical_labels --from 2022-01-01 --to 2025-12-31
    python -m scripts.backfill_historical_labels --from 2022-01-01 --to 2025-12-31 --reset
"""

from __future__ import annotations

import argparse
import datetime as dt

from loguru import logger

from apps.api.src.domain.ml.backfill_service import (
    DEFAULT_UNIVERSE,
    backfill_historical_labels,
)


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical_label rows.")
    parser.add_argument("--from", dest="from_", required=True, type=_parse_date)
    parser.add_argument("--to", dest="to", required=True, type=_parse_date)
    parser.add_argument("--universe", default=DEFAULT_UNIVERSE)
    parser.add_argument(
        "--actions",
        default="Buy,Trim,Sell",
        help="Comma-separated engine actions to label.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete rows for current engine_version before backfilling.",
    )
    args = parser.parse_args()

    if args.to < args.from_:
        raise SystemExit("--to must be >= --from")

    actions = {a.strip() for a in args.actions.split(",") if a.strip()}
    logger.info("CLI backfill_historical_labels actions={}", actions)

    backfill_historical_labels(
        start=args.from_,
        end=args.to,
        universe=args.universe,
        actions=actions,
        reset=args.reset,
    )


if __name__ == "__main__":
    main()
