"""Job registry – maps job names to async handler functions."""

from __future__ import annotations

import datetime
from collections.abc import Callable, Coroutine
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# Seeded universe for EOD backfill
# ---------------------------------------------------------------------------

_UNIVERSE: list[str] = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
    "META", "TSLA", "SPY",  "QQQ",  "VTI",
]


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

    from decimal import Decimal

    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from apps.api.src.db import SessionLocal
    from apps.api.src.db.models import Asset, PriceBar
    from apps.api.src.providers.tiingo import TiingoAdapter

    adapter = TiingoAdapter(api_key=settings.TIINGO_API_KEY)
    end_date   = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=365)

    for symbol in _UNIVERSE:
        try:
            with SessionLocal() as session:
                # Resolve asset row; create stub if absent
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
                logger.info("Fetched {} bars for {}", len(bars), symbol)

                for bar in bars:
                    stmt = (
                        pg_insert(PriceBar)
                        .values(
                            asset_id=asset_row.id,
                            timeframe="1d",
                            ts=bar["ts"],
                            open=Decimal(str(bar["open"])) if bar["open"] is not None else None,
                            high=Decimal(str(bar["high"])) if bar["high"] is not None else None,
                            low=Decimal(str(bar["low"]))  if bar["low"]  is not None else None,
                            close=Decimal(str(bar["close"])) if bar["close"] is not None else None,
                            adjusted_close=Decimal(str(bar["adjusted_close"]))
                            if bar["adjusted_close"] is not None else None,
                            volume=bar["volume"],
                            provider="tiingo",
                        )
                        .on_conflict_do_nothing(
                            constraint="uq_price_bar"
                        )
                    )
                    session.execute(stmt)

                session.commit()

        except Exception as exc:
            logger.error("tiingo_backfill_eod failed for {}: {}", symbol, exc)
            # Continue to next symbol – do not crash the entire job


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

JobFn = Callable[[], Coroutine[Any, Any, None]]

REGISTRY: dict[str, JobFn] = {
    "tiingo_backfill_eod": tiingo_backfill_eod,
}
