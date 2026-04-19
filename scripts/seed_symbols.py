"""Seed the initial 10-ticker universe and the nightly Tiingo backfill job."""

from __future__ import annotations

import datetime as dt

from loguru import logger
from sqlalchemy import select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import Asset, JobSchedule

SEED_UNIVERSE: list[dict[str, str]] = [
    {"symbol": "AAPL",  "name": "Apple Inc.",          "asset_class": "equity", "exchange": "NASDAQ"},
    {"symbol": "MSFT",  "name": "Microsoft Corp.",     "asset_class": "equity", "exchange": "NASDAQ"},
    {"symbol": "NVDA",  "name": "NVIDIA Corp.",        "asset_class": "equity", "exchange": "NASDAQ"},
    {"symbol": "GOOGL", "name": "Alphabet Inc.",       "asset_class": "equity", "exchange": "NASDAQ"},
    {"symbol": "AMZN",  "name": "Amazon.com Inc.",     "asset_class": "equity", "exchange": "NASDAQ"},
    {"symbol": "META",  "name": "Meta Platforms",      "asset_class": "equity", "exchange": "NASDAQ"},
    {"symbol": "TSLA",  "name": "Tesla Inc.",          "asset_class": "equity", "exchange": "NASDAQ"},
    {"symbol": "SPY",   "name": "SPDR S&P 500 ETF",    "asset_class": "etf",    "exchange": "NYSE"},
    {"symbol": "QQQ",   "name": "Invesco QQQ Trust",   "asset_class": "etf",    "exchange": "NASDAQ"},
    {"symbol": "VTI",   "name": "Vanguard Total Mkt",  "asset_class": "etf",    "exchange": "NYSE"},
]

JOB_DEFS: list[dict[str, str | bool]] = [
    {
        "name": "tiingo_backfill_eod",
        "cron_expr": "0 22 * * 1-5",   # 22:00 Mon-Fri
        "enabled": True,
    },
]


def seed() -> None:
    with SessionLocal() as session:
        # --- Assets ---------------------------------------------------------
        existing_symbols: set[str] = {
            row[0] for row in session.execute(select(Asset.symbol)).all()
        }
        added_assets = 0
        for row in SEED_UNIVERSE:
            if row["symbol"] in existing_symbols:
                continue
            session.add(Asset(**row, currency="USD", is_active=True))
            added_assets += 1

        # --- Jobs -----------------------------------------------------------
        existing_jobs: set[str] = {
            row[0] for row in session.execute(select(JobSchedule.name)).all()
        }
        added_jobs = 0
        for job in JOB_DEFS:
            if job["name"] in existing_jobs:
                continue
            session.add(
                JobSchedule(
                    name=job["name"],
                    cron_expr=job["cron_expr"],
                    enabled=bool(job["enabled"]),
                    next_run_at=dt.datetime.now(dt.timezone.utc),
                )
            )
            added_jobs += 1

        session.commit()

    logger.info("seed complete: assets +{}, jobs +{}", added_assets, added_jobs)


if __name__ == "__main__":
    seed()
