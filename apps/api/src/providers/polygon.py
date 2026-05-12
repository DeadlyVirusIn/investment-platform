"""Polygon.io provider — earnings + news + market tape snapshots.

Activated only when POLYGON_API_KEY env var is set. Otherwise all
fetch functions return empty lists / None. Frontend handles the empty
case without faking.

Endpoint references (require paid key for full data):
- Earnings: /vX/reference/earnings?ticker={ticker}
- News:     /v2/reference/news?ticker={ticker}&limit=5
- Tape:     /v2/snapshot/locale/us/markets/stocks/tickers?tickers=A,B,C
            (Stocks Starter tier, 15-min delayed)
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


POLYGON_BASE = "https://api.polygon.io"
TIMEOUT = httpx.Timeout(8.0, connect=4.0)


def _api_key() -> str:
    return os.environ.get("POLYGON_API_KEY", "").strip()


def is_available() -> bool:
    return bool(_api_key())


def fetch_news(ticker: str, limit: int = 5) -> list[dict[str, Any]]:
    """Return recent news items for ticker. Empty list when not configured."""
    key = _api_key()
    if not key or not ticker:
        return []
    url = f"{POLYGON_BASE}/v2/reference/news"
    params = {"ticker": ticker.upper(), "limit": str(limit), "apiKey": key}
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        logger.warning("Polygon news fetch failed for %s: %s", ticker, exc)
        return []
    out: list[dict[str, Any]] = []
    for item in data.get("results", [])[:limit]:
        out.append({
            "title": str(item.get("title") or ""),
            "source": str(item.get("publisher", {}).get("name") or "Polygon"),
            "published_at": str(item.get("published_utc") or ""),
            "url": str(item.get("article_url") or ""),
            "sentiment": None,
            "summary": str(item.get("description") or "") or None,
        })
    return [n for n in out if n["title"] and n["url"]]


# ---------------------------------------------------------------------------
# Market tape — 15-min delayed bulk snapshots (Stocks Starter tier).
# Used by apps/api/src/api/market.py to drive the UI's macro tape ribbon.
# ---------------------------------------------------------------------------


async def fetch_tape_snapshot(
    client: httpx.AsyncClient, symbols: list[str],
) -> list[dict[str, Any]]:
    """Fetch one bulk delayed snapshot for the given symbols.

    Returns a list of normalized dicts, one per symbol that Polygon
    returned. Symbols Polygon couldn't price are simply absent from
    the result. Raises on transport / auth / non-OK status — caller
    decides how to surface the failure.

    Normalized shape:
      {
        "symbol":        "SPY",
        "price":         736.10,    # last delayed price (day.c → min.c → prevDay.c)
        "prev_close":    739.30,
        "change_abs":    -3.20,
        "change_pct":    -0.4328,
        "quote_ts":      1778585229.571,   # epoch seconds (source-reported, delayed)
        "source":        "polygon",
        "delay_minutes": 15,
      }
    """
    key = _api_key()
    if not key:
        raise RuntimeError("POLYGON_API_KEY not set")
    if not symbols:
        return []
    url = f"{POLYGON_BASE}/v2/snapshot/locale/us/markets/stocks/tickers"
    params = {"tickers": ",".join(symbols), "apiKey": key}
    r = await client.get(url, params=params, timeout=10.0)
    r.raise_for_status()
    payload = r.json()
    status = payload.get("status")
    if status not in ("OK", "DELAYED"):
        raise RuntimeError(
            f"polygon snapshot returned status={status}: {payload.get('error', '')}"
        )
    out: list[dict[str, Any]] = []
    for t in payload.get("tickers", []):
        sym = str(t.get("ticker") or "").upper()
        if not sym:
            continue
        prev_day = t.get("prevDay") or {}
        min_bar = t.get("min") or {}
        day_bar = t.get("day") or {}
        # Price selection: prefer intraday day close (nonzero only when
        # session has started), then last delayed minute bar, then prior
        # session close as a fallback.
        price = (
            (day_bar.get("c") or 0)
            or (min_bar.get("c") or 0)
            or prev_day.get("c")
        )
        prev_close = prev_day.get("c")
        if price is None or prev_close is None:
            change_abs: float | None = None
            change_pct: float | None = None
        else:
            change_abs = float(price) - float(prev_close)
            change_pct = (
                (change_abs / float(prev_close)) * 100.0
                if float(prev_close) != 0 else None
            )
        # Polygon's `updated` is nanoseconds since epoch.
        ns = t.get("updated")
        quote_ts = (float(ns) / 1e9) if ns else None
        out.append({
            "symbol": sym,
            "price": float(price) if price is not None else None,
            "prev_close": float(prev_close) if prev_close is not None else None,
            "change_abs": change_abs,
            "change_pct": change_pct,
            "quote_ts": quote_ts,
            "source": "polygon",
            "delay_minutes": 15,
        })
    return out


async def fetch_intraday_history(
    client: httpx.AsyncClient, symbol: str, limit: int = 30,
) -> list[float]:
    """Fetch last N minute-bar closes for one symbol (chronological order).

    Used by the market tape to render a small intraday sparkline. Returns
    the closes only; the timestamps are implicit (latest = current price).
    Empty list on any failure — caller falls back to no-sparkline render.
    """
    key = _api_key()
    if not key or not symbol:
        return []
    # Today (UTC) at minute resolution. Polygon accepts YYYY-MM-DD on
    # both sides of the range; we just need recent bars.
    import datetime as _dt
    today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
    url = f"{POLYGON_BASE}/v2/aggs/ticker/{symbol.upper()}/range/1/minute/{today}/{today}"
    params = {
        "adjusted": "true",
        "sort": "desc",
        "limit": str(limit),
        "apiKey": key,
    }
    try:
        r = await client.get(url, params=params, timeout=10.0)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        logger.warning("Polygon minute aggs fetch failed for %s: %s", symbol, exc)
        return []
    results = data.get("results") or []
    # Polygon returns desc-sorted; reverse so the sparkline draws
    # left-to-right with the latest minute on the right.
    closes: list[float] = []
    for row in reversed(results):
        c = row.get("c")
        if c is None:
            continue
        try:
            closes.append(float(c))
        except (TypeError, ValueError):
            continue
    return closes


def fetch_earnings(ticker: str, limit: int = 4) -> list[dict[str, Any]]:
    """Return recent + upcoming earnings events. Empty when not configured."""
    key = _api_key()
    if not key or not ticker:
        return []
    url = f"{POLYGON_BASE}/vX/reference/earnings"
    params = {"ticker": ticker.upper(), "limit": str(limit), "apiKey": key}
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        logger.warning("Polygon earnings fetch failed for %s: %s", ticker, exc)
        return []
    out: list[dict[str, Any]] = []
    for item in data.get("results", [])[:limit]:
        date = str(item.get("report_date") or item.get("date") or "")
        actual = item.get("eps_actual")
        out.append({
            "date": date,
            "type": str(item.get("time") or "").upper() or "Pending",
            "estimate_eps": item.get("eps_estimate"),
            "actual_eps": actual,
            "status": "reported" if actual is not None else "upcoming",
        })
    return [e for e in out if e["date"]]
