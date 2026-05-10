"""Benzinga provider — news with sentiment.

Activated only when BENZINGA_API_KEY env var is set. Empty otherwise.

Endpoint reference (paid):
- /api/v2/news?tokens={key}&tickers={ticker}&pageSize=5
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


BENZINGA_BASE = "https://api.benzinga.com"
TIMEOUT = httpx.Timeout(8.0, connect=4.0)


def _api_key() -> str:
    return os.environ.get("BENZINGA_API_KEY", "").strip()


def is_available() -> bool:
    return bool(_api_key())


def _classify_sentiment(score: Any) -> str | None:
    if score is None:
        return None
    try:
        s = float(score)
    except (TypeError, ValueError):
        return None
    if s >= 0.2:
        return "positive"
    if s <= -0.2:
        return "negative"
    return "neutral"


def fetch_news(ticker: str, limit: int = 5) -> list[dict[str, Any]]:
    key = _api_key()
    if not key or not ticker:
        return []
    url = f"{BENZINGA_BASE}/api/v2/news"
    params = {
        "token": key,
        "tickers": ticker.upper(),
        "pageSize": str(limit),
        "displayOutput": "full",
    }
    try:
        with httpx.Client(timeout=TIMEOUT, headers={"Accept": "application/json"}) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        logger.warning("Benzinga news fetch failed for %s: %s", ticker, exc)
        return []
    items = data if isinstance(data, list) else data.get("data", [])
    out: list[dict[str, Any]] = []
    for item in items[:limit]:
        title = str(item.get("title") or "")
        url_ = str(item.get("url") or "")
        if not (title and url_):
            continue
        out.append({
            "title": title,
            "source": str(item.get("author") or "Benzinga"),
            "published_at": str(item.get("created") or item.get("updated") or ""),
            "url": url_,
            "sentiment": _classify_sentiment(item.get("sentiment")),
            "summary": str(item.get("teaser") or "") or None,
        })
    return out
