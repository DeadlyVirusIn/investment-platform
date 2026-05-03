"""Market data ingestion — ES / SPY / VIX / VIX3M.

Writes to market_series_observation. Deduplicated via content_hash.
PIT-clean: published_at = session close bar-time + publisher lag.
"""

from __future__ import annotations

import datetime as dt
from typing import Iterable

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.data.raw.common import observation_hash

# Series IDs and their data sources
MARKET_SERIES = {
    "^VIX":   {"source": "yfinance", "publish_lag_min": 15},
    "^VIX3M": {"source": "yfinance", "publish_lag_min": 15},
    "ES=F":   {"source": "yfinance", "publish_lag_min": 15},
    "SPY":    {"source": "yfinance", "publish_lag_min": 0},
    "HYG":    {"source": "yfinance", "publish_lag_min": 0},
    "LQD":    {"source": "yfinance", "publish_lag_min": 0},
}


def ingest_market_observations(
    session: Session, series_id: str, observations: Iterable[dict],
) -> int:
    """Upsert-by-hash. Observations: iter of {date, close, source?}.

    Returns number of rows inserted (dedupe skip count = total - inserted).
    """
    if series_id not in MARKET_SERIES:
        raise ValueError(f"unknown market series: {series_id}")
    cfg = MARKET_SERIES[series_id]
    source = cfg["source"]
    lag = dt.timedelta(minutes=cfg["publish_lag_min"])
    n_in = 0
    for obs in observations:
        d = obs["date"] if isinstance(obs["date"], dt.date) else dt.date.fromisoformat(obs["date"])
        val = float(obs["close"])
        pub = dt.datetime.combine(
            d, dt.time(16, 0), tzinfo=dt.timezone.utc,
        ) + lag
        ch = observation_hash(source, series_id, d, val)
        # Insert-if-not-exists by (source, series_id, as_of_date)
        r = session.execute(text("""
            INSERT INTO market_series_observation
              (series_id, observation_date, close_value, source,
               published_at, as_of_date, content_hash)
            VALUES (:sid, :obs_d, :val, :src, :pub, :asof, :ch)
            ON CONFLICT (source, series_id, as_of_date) DO NOTHING
        """), {
            "sid": series_id, "obs_d": d, "val": val, "src": source,
            "pub": pub, "asof": d, "ch": ch,
        })
        n_in += r.rowcount or 0
    session.commit()
    logger.info("[raw.market] {}: {} rows inserted", series_id, n_in)
    return n_in


# TODO: add yfinance live fetcher wrapper that batches recent days
