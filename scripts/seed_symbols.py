"""Seed the initial 10-ticker universe and the nightly Tiingo backfill job."""

from __future__ import annotations

import datetime as dt

from loguru import logger
from sqlalchemy import select

from decimal import Decimal

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import Asset, JobSchedule, PaperPortfolio

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
        "name": "ingest_prices_daily",
        "cron_expr": "0 22 * * 1-5",   # 22:00 Mon-Fri — Tiingo → Yahoo fallback
        "enabled": True,
    },
    {
        "name": "tiingo_backfill_eod",
        "cron_expr": "0 22 * * 1-5",   # legacy; disabled by default below
        "enabled": False,
    },
    {
        "name": "run_recommendations_for_all_accounts",
        "cron_expr": "30 22 * * 1-5",  # 22:30 Mon-Fri, after price ingest
        "enabled": True,
    },
    {
        "name": "score_recommendation_outcomes",
        "cron_expr": "0 23 * * 1-5",   # 23:00 Mon-Fri, after recommendation run
        "enabled": True,
    },
    {
        "name": "run_paper_trading",
        "cron_expr": "30 23 * * 1-5",  # 23:30 Mon-Fri, after outcome scoring
        "enabled": True,
    },
    {
        # V2 promotion-trigger weekly snapshot (Phase 8).
        # Cron evaluated in SCHEDULER_TZ. Design target = Monday 00:15 UTC;
        # set SCHEDULER_TZ=UTC for the worker to match exactly.
        # Idempotency on (iso_year, iso_week) makes accidental multi-fire
        # within the same ISO week safe (subsequent runs return noop).
        "name": "v2_promotion_snapshot",
        "cron_expr": "15 0 * * 1",     # Monday 00:15 in SCHEDULER_TZ
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

        # --- Default paper portfolio ---------------------------------------
        added_portfolio = 0
        has_active = session.scalars(
            select(PaperPortfolio.id).where(PaperPortfolio.is_active.is_(True)).limit(1)
        ).first()
        if not has_active:
            session.add(PaperPortfolio(
                name="Default Paper",
                starting_cash=Decimal("10000"),
                cash=Decimal("10000"),
                is_active=True,
            ))
            added_portfolio = 1

        session.commit()

    logger.info(
        "seed complete: assets +{}, jobs +{}, portfolios +{}",
        added_assets, added_jobs, added_portfolio,
    )


if __name__ == "__main__":
    seed()
