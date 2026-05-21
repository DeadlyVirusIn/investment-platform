"""Extend price_bar history for all active universe assets + benchmarks.

Uses Tiingo (if TIINGO_API_KEY set) → Yahoo fallback chain.

Usage::

    python -m scripts.extend_price_history --from 2022-01-01 --to 2025-04-20
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt

from loguru import logger
from sqlalchemy import select

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.db.models import Asset
from apps.api.src.domain.prices.providers.base import DailyPriceProvider
from apps.api.src.domain.prices.providers.tiingo import TiingoProvider
from apps.api.src.domain.prices.providers.yahoo import YahooProvider
from apps.api.src.domain.prices.service import ingest_symbols


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _provider_chain() -> list[DailyPriceProvider]:
    chain: list[DailyPriceProvider] = []
    if settings.TIINGO_API_KEY:
        chain.append(TiingoProvider(api_key=settings.TIINGO_API_KEY))
    chain.append(YahooProvider())
    return chain


async def _run(start: dt.date, end: dt.date) -> None:
    with SessionLocal() as session:
        symbols = [
            a.symbol for a in session.scalars(
                select(Asset).where(Asset.is_active.is_(True))
            )
        ]
    logger.info(
        "[extend_prices] symbols={} start={} end={} providers={}",
        len(symbols), start, end,
        [p.__class__.__name__ for p in _provider_chain()],
    )

    with SessionLocal() as session:
        report = await ingest_symbols(
            session, symbols,
            providers=_provider_chain(),
            start_date=start,
            end_date=end,
            incremental=False,
        )

    logger.info(
        "[extend_prices] done symbols={} total_written={}",
        len(report.symbols), report.total_written,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Extend price_bar history.")
    parser.add_argument("--from", dest="from_", required=True, type=_parse_date)
    parser.add_argument("--to", dest="to", required=True, type=_parse_date)
    args = parser.parse_args()
    if args.to < args.from_:
        raise SystemExit("--to must be >= --from")
    asyncio.run(_run(args.from_, args.to))


if __name__ == "__main__":
    main()
