"""FMP consensus adapter — Phase 11.1.

Single-source discipline: this adapter emits CONSENSUS records only
(EPS + Revenue estimates). It NEVER emits actuals. Actuals come from
`edgar_actuals`.

FMP `/stable/earnings?symbol=X` returns one row per announcement with:
    {
      "symbol": "AAPL",
      "date": "YYYY-MM-DD",                -- announcement date (ET press release)
      "epsEstimated": 2.67 | null,
      "revenueEstimated": 138391000000 | null,
      "lastUpdated": "YYYY-MM-DD",          -- when consensus was last refreshed
      "epsActual": ...,                     -- DISCARDED
      "revenueActual": ...,                 -- DISCARDED
    }

Timezone: FMP publishes US-equity earnings in ET. We mark
`source_timezone=America/New_York` so Phase 10.6 ingest treats any derived
naive timestamp as ET-native.

Units:
    EPS      -> usd_per_share (native)
    Revenue  -> usd_raw       (native: absolute USD, e.g. 143_756_000_000)
"""

from __future__ import annotations

import datetime as dt
from typing import Iterable
from zoneinfo import ZoneInfo

import requests
from loguru import logger

FMP_BASE = "https://financialmodelingprep.com/stable"
SOURCE = "fmp"
ET = ZoneInfo("America/New_York")


class FMPError(RuntimeError):
    pass


FMP_FREE_MAX_LIMIT = 5


def _fetch_earnings(symbol: str, api_key: str, *, limit: int = 5) -> list[dict]:
    url = f"{FMP_BASE}/earnings"
    # Free tier caps `limit` at 5.
    eff_limit = min(limit, FMP_FREE_MAX_LIMIT)
    params = {"symbol": symbol, "limit": eff_limit, "apikey": api_key}
    r = requests.get(url, params=params, timeout=20)
    if r.status_code != 200:
        raise FMPError(f"{symbol}: HTTP {r.status_code} {r.text[:160]}")
    payload = r.json()
    if isinstance(payload, dict) and "Error Message" in payload:
        raise FMPError(f"{symbol}: {payload['Error Message']}")
    if not isinstance(payload, list):
        raise FMPError(f"{symbol}: unexpected payload shape {type(payload)}")
    return payload


def _announcement_naive_et(event_date: dt.date) -> dt.datetime:
    """Naive ET datetime for a date. Default to 16:00 ET (typical after-close
    earnings release window for US equities when FMP doesn't publish a time).

    The caller MUST pass source_timezone=ET into the ingestion pipeline so that
    Phase 10.6 converts this to aware-UTC. We never construct an aware TS here.
    """
    return dt.datetime(event_date.year, event_date.month, event_date.day, 16, 0)


def fetch_consensus_records(
    symbols: Iterable[tuple[str, str]], *, api_key: str, limit: int = 5,
) -> tuple[list[dict], list[dict], list[str]]:
    """Fetch FMP consensus for given (symbol, asset_id) pairs.

    Returns (earnings_records, consensus_records, errors).
    - earnings_records feed `ingest_earnings` — include TS in naive ET.
    - consensus_records feed `ingest_consensus` — EPS + Rev ESTIMATES ONLY.
    """
    earnings: list[dict] = []
    consensus: list[dict] = []
    errors: list[str] = []

    for sym, aid in symbols:
        try:
            rows = _fetch_earnings(sym, api_key, limit=limit)
        except FMPError as exc:
            logger.warning("[fmp.cons] {}", exc)
            errors.append(str(exc))
            continue

        for rec in rows:
            try:
                ed = dt.date.fromisoformat(rec["date"])
            except (KeyError, ValueError):
                errors.append(f"{sym}: bad date {rec.get('date')!r}")
                continue

            eps_est = rec.get("epsEstimated")
            rev_est = rec.get("revenueEstimated")
            last_up = rec.get("lastUpdated") or rec.get("updatedAt")

            # Announcement naive-in-ET — pipeline with source_timezone=ET
            # converts to aware-UTC. event_time='unknown' because FMP doesn't
            # publish time-of-day on this endpoint.
            ann_ts = _announcement_naive_et(ed)

            earnings.append({
                "asset_id": aid,
                "symbol": sym,
                "event_date": ed.isoformat(),
                "event_time": "unknown",
                "announcement_timestamp": ann_ts,
                "announcement_timestamp_raw": f"fmp:{rec['date']}",
                "fiscal_period": None,  # FMP doesn't publish fiscal label here
                "source": SOURCE,
                "external_id": f"fmp:{sym}:{ed.isoformat()}",
            })

            # as_of_date for consensus = lastUpdated (best PIT proxy). Must be
            # <= event_date for PIT correctness (strict `<=`).
            if last_up:
                try:
                    ao = dt.date.fromisoformat(last_up)
                except ValueError:
                    ao = ed
            else:
                ao = ed
            # Clamp to event_date if FMP's lastUpdated is after the event
            # (happens when FMP records a post-event revision — would violate PIT).
            if ao > ed:
                ao = ed

            if eps_est is not None:
                consensus.append({
                    "asset_id": aid, "symbol": sym,
                    "event_date": ed.isoformat(), "metric": "eps",
                    "estimate_type": "consensus",
                    "value": float(eps_est),
                    "value_unit": "usd_per_share",
                    "as_of_date": ao.isoformat(),
                    "source": SOURCE,
                    "external_id": f"fmp:{sym}:{ed.isoformat()}:eps:cons",
                })
            if rev_est is not None:
                consensus.append({
                    "asset_id": aid, "symbol": sym,
                    "event_date": ed.isoformat(), "metric": "revenue",
                    "estimate_type": "consensus",
                    "value": float(rev_est),
                    "value_unit": "usd_raw",
                    "as_of_date": ao.isoformat(),
                    "source": SOURCE,
                    "external_id": f"fmp:{sym}:{ed.isoformat()}:rev:cons",
                })

    return earnings, consensus, errors
