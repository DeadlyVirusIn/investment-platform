"""CLI entrypoint — historical catalyst backfill.

Usage:
    python -m apps.api.src.jobs.backfill_catalysts \
        --symbols AAPL,MSFT,NVDA \
        --start-date 2024-01-01 --end-date 2025-01-01 \
        --providers finnhub,yahoo \
        --dry-run
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from loguru import logger

from apps.api.src.config import settings
from apps.api.src.data.catalysts.backfill import (
    BackfillRunConfig, BackfillService,
)
from apps.api.src.data.catalysts.backfill.rate_limit import RateLimiter
from apps.api.src.db import SessionLocal


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Historical catalyst backfill.")
    p.add_argument("--symbols", required=True,
                   help="comma-separated symbol list")
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date",   required=True)
    p.add_argument("--providers",
                   default=getattr(
                       settings,
                       "CATALYST_BACKFILL_PROVIDER_PRIORITY",
                       "finnhub,yahoo"),
                   help="comma-separated provider priority")
    p.add_argument("--window-days", type=int,
                   default=getattr(settings,
                                    "CATALYST_BACKFILL_WINDOW_DAYS", 30))
    p.add_argument("--rate-per-min", type=int,
                   default=getattr(settings,
                                    "CATALYST_BACKFILL_RATE_LIMIT_PER_MIN",
                                    60))
    p.add_argument("--max-symbols", type=int,
                   default=getattr(settings,
                                    "CATALYST_BACKFILL_MAX_SYMBOLS", 50))
    p.add_argument("--dry-run", action="store_true",
                   default=getattr(settings,
                                    "CATALYST_BACKFILL_DRY_RUN_DEFAULT", True))
    p.add_argument("--live", action="store_true",
                   help="force dry_run=False (writes to DB)")
    return p.parse_args()


def main() -> int:
    args = _parse()
    symbols = tuple(
        s.strip().upper()
        for s in args.symbols.split(",") if s.strip()
    )
    if args.max_symbols and len(symbols) > args.max_symbols:
        symbols = symbols[: args.max_symbols]
    providers = tuple(
        p.strip().lower()
        for p in args.providers.split(",") if p.strip()
    )
    try:
        start = dt.date.fromisoformat(args.start_date)
        end   = dt.date.fromisoformat(args.end_date)
    except ValueError as e:
        logger.error("bad date: {}", e)
        return 2

    dry = True if not args.live else False
    if args.dry_run and not args.live:
        dry = True

    cfg = BackfillRunConfig(
        symbols=symbols,
        start_date=start,
        end_date=end,
        providers=providers,
        window_days=int(args.window_days),
        rate_limit_per_min=int(args.rate_per_min),
        dry_run=dry,
    )
    logger.info(
        "backfill: symbols={} window={}->{} providers={} dry_run={}",
        len(symbols), start, end, providers, dry,
    )
    with SessionLocal() as session:
        rl = RateLimiter(max_per_minute=cfg.rate_limit_per_min)
        svc = BackfillService(session, rate_limiter=rl)
        result = svc.run(cfg)
    logger.info(
        "backfill done: run_id={} news_in={} news_skip={} "
        "earn_in={} earn_skip={} errors={}",
        result.run_id,
        result.news_inserted, result.news_skipped,
        result.earnings_inserted, result.earnings_skipped,
        len(result.provider_errors),
    )
    for w in result.warnings[:10]:
        logger.warning("  warn: {}", w)
    for e in result.provider_errors[:10]:
        logger.warning("  err:  {}", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
