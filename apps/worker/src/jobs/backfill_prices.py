"""Ad-hoc / manual backfill job. Larger window, explicit symbols.

Uses Tiingo → Yahoo fallback chain. When invoked without args (via scheduler),
backfills the last 2 years for every active asset plus SPY.
"""

from __future__ import annotations

import datetime as dt

from loguru import logger
from sqlalchemy import select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import Asset
from apps.api.src.domain.prices.providers.base import DailyPriceProvider
from apps.api.src.domain.prices.providers.tiingo import TiingoProvider
from apps.api.src.domain.prices.providers.yahoo import YahooProvider
from apps.api.src.domain.prices.service import ingest_symbols


def _chain() -> list[DailyPriceProvider]:
    from apps.api.src.config import settings
    chain: list[DailyPriceProvider] = []
    if settings.TIINGO_API_KEY:
        chain.append(TiingoProvider(api_key=settings.TIINGO_API_KEY))
    chain.append(YahooProvider())
    return chain


async def backfill_prices(
    symbols: list[str] | None = None,
    *,
    years: int = 2,
) -> None:
    """Backfill ``years`` of history for ``symbols`` (or all active assets)."""
    with SessionLocal() as session:
        if symbols is None:
            symbols = [
                a.symbol for a in session.scalars(
                    select(Asset).where(Asset.is_active.is_(True))
                )
            ]
    today = dt.date.today()
    start = today.replace(year=today.year - years)

    with SessionLocal() as session:
        report = await ingest_symbols(
            session, symbols,
            providers=_chain(),
            start_date=start,
            end_date=today,
            incremental=False,
        )

    logger.info(
        "backfill_prices: symbols={} total_written={}",
        len(report.symbols), report.total_written,
    )
