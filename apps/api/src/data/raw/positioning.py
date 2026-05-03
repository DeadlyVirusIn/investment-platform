"""Positioning data — COT weekly, GEX daily.

Writes to positioning_observation. Both series statused CANDIDATE or
DIAGNOSTIC only — never wired to production decisions.
"""

from __future__ import annotations

import datetime as dt
from io import StringIO
from typing import Iterable

import pandas as pd
import requests
from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.data.raw.common import observation_hash

GEX_CSV_URL = "https://squeezemetrics.com/monitor/static/DIX.csv"


def ingest_gex_from_squeezemetrics(session: Session) -> int:
    """Ingest SPX aggregate dealer gamma (daily) from SqueezeMetrics free CSV.
    Series_id = 'GEX_SPX_DAILY'. Published at ~T+18h ET (published next AM).
    Status upstream: DIAGNOSTIC (Phase X3 FAIL).
    """
    r = requests.get(GEX_CSV_URL, timeout=30,
                     headers={"User-Agent": "dl2-positioning-ingest"})
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["gex"] = pd.to_numeric(df["gex"], errors="coerce")
    df = df.dropna(subset=["gex"])
    series_id = "GEX_SPX_DAILY"
    source = "squeezemetrics"
    n_in = 0
    for _, row in df.iterrows():
        d = row["date"]
        v = float(row["gex"])
        pub = dt.datetime.combine(
            d, dt.time(0, 0), tzinfo=dt.timezone.utc,
        ) + dt.timedelta(hours=18)
        ch = observation_hash(source, series_id, d, v)
        r2 = session.execute(text("""
            INSERT INTO positioning_observation
              (series_id, observation_date, value, source, report_type,
               published_at, content_hash)
            VALUES (:sid, :d, :v, :src, 'daily', :pub, :ch)
            ON CONFLICT (source, series_id, observation_date) DO NOTHING
        """), {"sid": series_id, "d": d, "v": v, "src": source,
               "pub": pub, "ch": ch})
        n_in += r2.rowcount or 0
    session.commit()
    logger.info("[raw.positioning] GEX: {} rows inserted", n_in)
    return n_in


def ingest_cot_weekly(session: Session, data_path: str) -> int:
    """COT ingestion skeleton — requires CFTC CSV download workflow.
    TODO: wire CFTC historical API; until then, accept pre-downloaded CSV.
    Series: COT_ES_NONCOMM_NET weekly.
    """
    # TODO: implement CFTC pull
    logger.warning("[raw.positioning] COT ingestion not yet implemented")
    return 0
