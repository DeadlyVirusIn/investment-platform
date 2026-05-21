"""Seed the default stock-swing universe.

Expanded to ~60 liquid US equities + ETFs spread across sectors. Curated
static list chosen for:
  * avg daily dollar volume >> $50M
  * price > $10
  * not penny / micro-cap
  * broad sector coverage (tech, financials, healthcare, consumer,
    industrials, energy, staples, utilities, materials, communications,
    real estate, plus benchmark ETFs)

Idempotent. Re-runnable. Inserts missing Asset rows on first run so the
same script both seeds Assets + seeds the universe membership.
"""

from __future__ import annotations

import datetime as dt

from loguru import logger
from sqlalchemy import select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import Asset, UniverseMembership

DEFAULT_UNIVERSE = "stock_swing_v1"


# Curated liquid US large-cap universe across sectors.
# Each entry: (symbol, asset_class, sector, exchange)
SEED_UNIVERSE: list[tuple[str, str, str, str]] = [
    # Mega-cap tech
    ("AAPL",  "equity", "tech",          "NASDAQ"),
    ("MSFT",  "equity", "tech",          "NASDAQ"),
    ("NVDA",  "equity", "tech",          "NASDAQ"),
    ("GOOGL", "equity", "communication", "NASDAQ"),
    ("AMZN",  "equity", "consumer_disc", "NASDAQ"),
    ("META",  "equity", "communication", "NASDAQ"),
    ("TSLA",  "equity", "consumer_disc", "NASDAQ"),
    ("AVGO",  "equity", "tech",          "NASDAQ"),
    ("ORCL",  "equity", "tech",          "NYSE"),
    ("ADBE",  "equity", "tech",          "NASDAQ"),
    ("CRM",   "equity", "tech",          "NYSE"),
    ("AMD",   "equity", "tech",          "NASDAQ"),
    ("NFLX",  "equity", "communication", "NASDAQ"),
    ("INTC",  "equity", "tech",          "NASDAQ"),
    ("CSCO",  "equity", "tech",          "NASDAQ"),
    ("QCOM",  "equity", "tech",          "NASDAQ"),
    ("TXN",   "equity", "tech",          "NASDAQ"),

    # Financials
    ("JPM",   "equity", "financials",    "NYSE"),
    ("BAC",   "equity", "financials",    "NYSE"),
    ("WFC",   "equity", "financials",    "NYSE"),
    ("GS",    "equity", "financials",    "NYSE"),
    ("MS",    "equity", "financials",    "NYSE"),
    ("BLK",   "equity", "financials",    "NYSE"),
    ("V",     "equity", "financials",    "NYSE"),
    ("MA",    "equity", "financials",    "NYSE"),

    # Healthcare
    ("UNH",   "equity", "healthcare",    "NYSE"),
    ("JNJ",   "equity", "healthcare",    "NYSE"),
    ("LLY",   "equity", "healthcare",    "NYSE"),
    ("PFE",   "equity", "healthcare",    "NYSE"),
    ("ABBV",  "equity", "healthcare",    "NYSE"),
    ("MRK",   "equity", "healthcare",    "NYSE"),
    ("TMO",   "equity", "healthcare",    "NYSE"),

    # Consumer discretionary + staples
    ("HD",    "equity", "consumer_disc", "NYSE"),
    ("NKE",   "equity", "consumer_disc", "NYSE"),
    ("MCD",   "equity", "consumer_disc", "NYSE"),
    ("COST",  "equity", "consumer_stap", "NASDAQ"),
    ("WMT",   "equity", "consumer_stap", "NYSE"),
    ("PEP",   "equity", "consumer_stap", "NASDAQ"),
    ("KO",    "equity", "consumer_stap", "NYSE"),
    ("PG",    "equity", "consumer_stap", "NYSE"),

    # Industrials
    ("CAT",   "equity", "industrials",   "NYSE"),
    ("BA",    "equity", "industrials",   "NYSE"),
    ("GE",    "equity", "industrials",   "NYSE"),
    ("HON",   "equity", "industrials",   "NASDAQ"),
    ("UPS",   "equity", "industrials",   "NYSE"),

    # Energy
    ("XOM",   "equity", "energy",        "NYSE"),
    ("CVX",   "equity", "energy",        "NYSE"),
    ("COP",   "equity", "energy",        "NYSE"),

    # Utilities + materials
    ("NEE",   "equity", "utilities",     "NYSE"),
    ("DUK",   "equity", "utilities",     "NYSE"),
    ("LIN",   "equity", "materials",     "NYSE"),

    # Communications / media
    ("DIS",   "equity", "communication", "NYSE"),
    ("T",     "equity", "communication", "NYSE"),
    ("VZ",    "equity", "communication", "NYSE"),

    # Real estate
    ("AMT",   "equity", "real_estate",   "NYSE"),

    # Benchmark ETFs (not traded by engine but kept in universe for context)
    ("SPY",   "etf",    "etf",           "NYSE"),
    ("QQQ",   "etf",    "etf",           "NASDAQ"),
    ("VTI",   "etf",    "etf",           "NYSE"),
    ("IWM",   "etf",    "etf",           "NYSE"),
    ("DIA",   "etf",    "etf",           "NYSE"),
    ("XLK",   "etf",    "etf",           "NYSE"),
    ("XLF",   "etf",    "etf",           "NYSE"),
    ("XLE",   "etf",    "etf",           "NYSE"),
]


def _ensure_assets(session) -> dict[str, str]:
    """Insert any missing Asset rows. Returns {symbol: asset_id}."""
    existing = {
        sym: aid for aid, sym in session.execute(
            select(Asset.id, Asset.symbol)
        ).all()
    }
    added = 0
    for symbol, asset_class, sector, exchange in SEED_UNIVERSE:
        if symbol in existing:
            # Backfill sector if unset
            a = session.get(Asset, existing[symbol])
            if a is not None and not a.sector:
                a.sector = sector
            continue
        a = Asset(
            symbol=symbol, asset_class=asset_class, sector=sector,
            exchange=exchange, currency="USD", is_active=True,
        )
        session.add(a)
        session.flush()
        existing[symbol] = a.id
        added += 1
    session.commit()
    if added:
        logger.info("seeded {} new assets", added)
    return existing


def seed() -> None:
    today = dt.date.today()
    with SessionLocal() as session:
        asset_map = _ensure_assets(session)

        already_open = {
            row[0] for row in session.execute(
                select(UniverseMembership.asset_id).where(
                    UniverseMembership.universe_name == DEFAULT_UNIVERSE,
                    UniverseMembership.end_date.is_(None),
                )
            ).all()
        }

        added = 0
        for symbol, _cls, _sector, _exch in SEED_UNIVERSE:
            aid = asset_map.get(symbol)
            if aid is None or aid in already_open:
                continue
            session.add(UniverseMembership(
                universe_name=DEFAULT_UNIVERSE,
                asset_id=aid,
                start_date=today,
                reason="seeded",
            ))
            added += 1
        session.commit()

    logger.info(
        "universe seed complete: universe={} symbols={} added={}",
        DEFAULT_UNIVERSE, len(SEED_UNIVERSE), added,
    )


if __name__ == "__main__":
    seed()
