"""Macro ingestion — FRED series (DGS10, WALCL, WTREGEN, RRPONTSYD,
BAMLH0A0HYM2, BAA, AAA).

Writes to EXISTING macro_series_observation table (Phase 10). Uses CSV
endpoint https://fred.stlouisfed.org/graph/fredgraph.csv?id=<series>.
"""

from __future__ import annotations

import datetime as dt
from typing import Iterable

import pandas as pd
import requests
from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.data.raw.common import observation_hash

FRED_SERIES = {
    "DGS10":         {"publish_lag_hours": 18},  # next-morning
    "DGS2":          {"publish_lag_hours": 18},
    "WALCL":         {"publish_lag_hours": 28},  # Thursday evening
    "WTREGEN":       {"publish_lag_hours": 28},
    "RRPONTSYD":     {"publish_lag_hours": 16},
    "BAMLH0A0HYM2":  {"publish_lag_hours": 24},
    "BAA":           {"publish_lag_hours": 24},
    "AAA":           {"publish_lag_hours": 24},
}


def fetch_fred_csv(series_id: str, start: str = "2020-01-01") -> pd.DataFrame:
    url = (f"https://fred.stlouisfed.org/graph/fredgraph.csv"
           f"?id={series_id}&cosd={start}")
    r = requests.get(url, timeout=30, headers={"User-Agent": "dl2-macro-ingest"})
    r.raise_for_status()
    from io import StringIO
    df = pd.read_csv(StringIO(r.text))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna()


def ingest_fred_series(session: Session, series_id: str) -> int:
    """Insert-or-skip macro observations. Uses existing macro_series_observation
    schema. Idempotent via (series_id, observation_date) unique constraint."""
    if series_id not in FRED_SERIES:
        raise ValueError(f"unknown FRED series: {series_id}")
    lag = dt.timedelta(hours=FRED_SERIES[series_id]["publish_lag_hours"])
    df = fetch_fred_csv(series_id)
    n_in = 0
    for _, row in df.iterrows():
        d = row["date"]
        v = float(row["value"])
        pub = dt.datetime.combine(d, dt.time(0, 0), tzinfo=dt.timezone.utc) + lag
        ch = observation_hash("FRED", series_id, d, v)
        r = session.execute(text("""
            INSERT INTO macro_series_observation
              (series_id, observation_date, value, source,
               published_at, as_of_date, content_hash)
            VALUES (:sid, :d, :v, 'FRED', :pub, :d, :ch)
            ON CONFLICT (series_id, observation_date) DO NOTHING
        """), {"sid": series_id, "d": d, "v": v, "pub": pub, "ch": ch})
        n_in += r.rowcount or 0
    session.commit()
    logger.info("[raw.macro] {}: {} rows inserted", series_id, n_in)
    return n_in


def ingest_all_fred(session: Session) -> dict[str, int]:
    return {s: ingest_fred_series(session, s) for s in FRED_SERIES}
