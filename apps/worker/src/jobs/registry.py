"""Job registry – maps job names to async handler functions."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Coroutine
from decimal import Decimal
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# Seeded universe for EOD backfill
# ---------------------------------------------------------------------------

_UNIVERSE: list[str] = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
    "META", "TSLA", "SPY",  "QQQ",  "VTI",
]


def _parse_ts(s: object) -> dt.datetime | None:
    """Parse Tiingo date strings (``2025-01-01T00:00:00.000Z``) → aware datetime."""
    if s is None or s == "":
        return None
    if isinstance(s, dt.datetime):
        return s if s.tzinfo else s.replace(tzinfo=dt.timezone.utc)
    text = str(s)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        logger.warning("Could not parse timestamp: {}", s)
        return None


def _dec(v: object) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


# ---------------------------------------------------------------------------
# tiingo_backfill_eod
# ---------------------------------------------------------------------------

async def tiingo_backfill_eod() -> None:
    """Backfill 1-year adjusted EOD bars from Tiingo for the seeded universe.

    Gracefully degrades (logs warning and returns) when TIINGO_API_KEY is absent.
    Upserts into price_bar on (asset_id, timeframe, ts, provider).
    """
    from apps.api.src.config import settings

    if not settings.TIINGO_API_KEY:
        logger.warning("TIINGO_API_KEY is not set – skipping tiingo_backfill_eod")
        return

    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from apps.api.src.db import SessionLocal
    from apps.api.src.db.models import Asset, PriceBar
    from apps.api.src.providers.tiingo import TiingoAdapter

    adapter = TiingoAdapter(api_key=settings.TIINGO_API_KEY)
    end_date = dt.date.today()
    start_date = end_date - dt.timedelta(days=365)

    total_fetched = 0
    total_written = 0

    for symbol in _UNIVERSE:
        try:
            with SessionLocal() as session:
                asset_row = session.scalars(
                    select(Asset).where(Asset.symbol == symbol)
                ).first()
                if asset_row is None:
                    asset_row = Asset(
                        symbol=symbol,
                        asset_class="equity",
                        exchange="NASDAQ",
                        currency="USD",
                    )
                    session.add(asset_row)
                    session.flush()

                bars = await adapter.fetch_prices(
                    symbol, start_date, end_date, session=session
                )
                total_fetched += len(bars)
                logger.info("Fetched {} bars for {}", len(bars), symbol)

                written = 0
                for bar in bars:
                    ts = _parse_ts(bar.get("ts"))
                    if ts is None:
                        continue
                    stmt = (
                        pg_insert(PriceBar)
                        .values(
                            asset_id=asset_row.id,
                            timeframe="1d",
                            ts=ts,
                            open=_dec(bar.get("open")),
                            high=_dec(bar.get("high")),
                            low=_dec(bar.get("low")),
                            close=_dec(bar.get("close")),
                            adjusted_close=_dec(bar.get("adjusted_close")),
                            volume=bar.get("volume"),
                            provider="tiingo",
                        )
                        .on_conflict_do_nothing(constraint="uq_price_bar")
                    )
                    result = session.execute(stmt)
                    if result.rowcount:
                        written += result.rowcount

                session.commit()
                total_written += written
                logger.info("Wrote {} new price_bar rows for {}", written, symbol)

        except Exception as exc:  # noqa: BLE001 – we log and keep going
            logger.error("tiingo_backfill_eod failed for {}: {}", symbol, exc)

    logger.info(
        "tiingo_backfill_eod complete: fetched={} written={}",
        total_fetched,
        total_written,
    )


# ---------------------------------------------------------------------------
# run_recommendations_for_all_accounts
# ---------------------------------------------------------------------------


async def run_recommendations_for_all_accounts() -> None:
    """Run the recommendation engine for every account that exists.

    Scheduled to run after the nightly price-ingestion job. Idempotent via
    recommendation_engine.persist()'s snapshot_hash dedup — repeated runs on
    unchanged inputs do not produce duplicate rows.
    """
    from sqlalchemy import select

    from apps.api.src.db import SessionLocal
    from apps.api.src.db.models import Account
    from apps.api.src.domain.recommendations.recommendation_engine import (
        load_engine_config,
        run_for_account,
    )

    total_accounts = 0
    total_recs = 0

    try:
        config = load_engine_config()
    except Exception as exc:  # noqa: BLE001
        logger.error("run_recommendations_for_all_accounts: config load failed: {}", exc)
        return

    with SessionLocal() as session:
        account_ids = [
            a[0] for a in session.execute(select(Account.id)).all()
        ]

    for account_id in account_ids:
        try:
            with SessionLocal() as session:
                results = run_for_account(session, account_id, config=config)
                session.commit()
                total_accounts += 1
                total_recs += len(results)
                logger.info(
                    "Recommendations: account={} generated={}",
                    account_id,
                    len(results),
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "run_recommendations_for_all_accounts: account={} failed: {}",
                account_id,
                exc,
            )

    logger.info(
        "run_recommendations_for_all_accounts complete: accounts={} recs={}",
        total_accounts,
        total_recs,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

JobFn = Callable[[], Coroutine[Any, Any, None]]

REGISTRY: dict[str, JobFn] = {
    "tiingo_backfill_eod": tiingo_backfill_eod,
    "run_recommendations_for_all_accounts": run_recommendations_for_all_accounts,
}
