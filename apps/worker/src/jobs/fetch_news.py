"""Scheduled job: pull headlines from Yahoo per-symbol + CNBC top-news RSS,
classify, dedupe-insert, map symbols.

Cron default: every 2 hours on weekdays (``0 */2 * * 1-5``).
"""

from __future__ import annotations

from loguru import logger
from sqlalchemy import or_, select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import Asset, UniverseMembership, Watchlist
from apps.api.src.domain.news.fetchers import cnbc_rss, yahoo_rss
from apps.api.src.domain.news.ingest_service import ingest


def _active_symbols(session) -> list[str]:
    """Union of today's universe members + watchlist."""
    universe = session.execute(
        select(Asset.symbol)
        .join(UniverseMembership, UniverseMembership.asset_id == Asset.id)
        .where(
            UniverseMembership.universe_name == "stock_swing_v1",
            or_(
                UniverseMembership.end_date.is_(None),
                UniverseMembership.end_date >= __import__("datetime").date.today(),
            ),
        )
    ).all()
    watch = session.execute(select(Watchlist.symbol)).all()
    out = {row[0] for row in universe} | {row[0] for row in watch}
    return sorted(out)


async def fetch_news() -> None:
    # Yahoo: per-symbol
    with SessionLocal() as session:
        symbols = _active_symbols(session)

    total_items = []

    if symbols:
        yahoo_items = yahoo_rss.fetch_for_symbols(symbols)
        total_items.extend(yahoo_items)
        logger.info("yahoo_rss: fetched {} items across {} symbols",
                    len(yahoo_items), len(symbols))
    else:
        logger.warning("fetch_news: no active symbols")

    cnbc_items = cnbc_rss.fetch_top_news()
    total_items.extend(cnbc_items)
    logger.info("cnbc_rss: fetched {} items", len(cnbc_items))

    if not total_items:
        logger.info("fetch_news: nothing to ingest")
        return

    with SessionLocal() as session:
        stats = ingest(session, total_items, universe_symbols=symbols)

    logger.info(
        "fetch_news complete: fetched={} inserted={} duplicates={} mapped={}",
        stats.fetched, stats.inserted, stats.duplicates, stats.mapped,
    )
