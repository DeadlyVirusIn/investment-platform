"""Daily price-ingestion job. Tiingo primary → Yahoo fallback."""

from __future__ import annotations

from loguru import logger
from sqlalchemy import select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import Asset
from apps.api.src.domain.prices.providers.base import DailyPriceProvider
from apps.api.src.domain.prices.providers.tiingo import TiingoProvider
from apps.api.src.domain.prices.providers.yahoo import YahooProvider
from apps.api.src.domain.prices.service import ingest_symbols


def _provider_chain() -> list[DailyPriceProvider]:
    from apps.api.src.config import settings
    chain: list[DailyPriceProvider] = []
    if settings.TIINGO_API_KEY:
        chain.append(TiingoProvider(api_key=settings.TIINGO_API_KEY))
    else:
        logger.warning("TIINGO_API_KEY not set — skipping Tiingo provider")
    chain.append(YahooProvider())
    # BP27B: Polygon is intentionally NOT in the daily chain. Its raw bars
    # carry adjusted_close=None; first-non-empty chain semantics mean a
    # Polygon-first daily run would write None adjusted_close on fresh days,
    # degrading the live total-return series. Polygon is reserved for the
    # explicit gap-backfill driver (BP24), where adj=None on uncovered names
    # is acceptable. Tiingo/Yahoo remain the live adjusted_close authority.
    return chain


async def ingest_prices_daily() -> None:
    """Incremental daily ingestion over all active assets (+ SPY benchmark)."""
    providers = _provider_chain()
    if not providers:
        logger.error("no providers available — nothing to ingest")
        return

    with SessionLocal() as session:
        symbols = [
            a.symbol for a in session.scalars(
                select(Asset).where(Asset.is_active.is_(True)).order_by(Asset.symbol.asc())
            )
        ]

    if not symbols:
        symbols = []  # ingest_symbols still pulls benchmark

    with SessionLocal() as session:
        report = await ingest_symbols(
            session, symbols,
            providers=providers,
            incremental=True,
        )

    logger.info(
        "ingest_prices_daily: attempted={} total_written={}",
        len(report.symbols), report.total_written,
    )
