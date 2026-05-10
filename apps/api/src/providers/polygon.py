"""Polygon.io provider — earnings + news.

Activated only when POLYGON_API_KEY env var is set. Otherwise all
fetch functions return empty lists. Frontend handles the empty case
without faking.

Endpoint references (require paid key for full data):
- Earnings: /vX/reference/earnings?ticker={ticker}
- News:     /v2/reference/news?ticker={ticker}&limit=5
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
