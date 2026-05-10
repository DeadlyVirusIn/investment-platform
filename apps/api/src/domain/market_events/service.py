"""Market events orchestration.

Aggregates per-symbol events from multiple providers:
- SEC EDGAR (filings) — always on, free
- Polygon (earnings + news) — when POLYGON_API_KEY set
- Benzinga (news + sentiment) — when BENZINGA_API_KEY set; appended
  AFTER Polygon results so a Benzinga sentiment-tagged item ranks
  alongside / above plain Polygon news for the same URL
- Firecrawl (optional summarizer) — never source of truth

All providers return [] gracefully when not configured. Empty arrays
in the response are honest signals — the frontend treats them as
"no fresh catalyst" rather than "broken".
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from apps.api.src.providers import (
    benzinga,
    polygon,
    sec_edgar,
)

logger = logging.getLogger(__name__)


MAX_SYMBOLS = 25


def _empty_symbol_payload() -> dict[str, list[Any]]:
    return {
        "earnings": [],
        "news": [],
        "filings": [],
        "options_expirations": [],
    }


def _dedupe_news(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """De-dupe by URL, preserving order (first wins)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for it in items:
        url = it.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(it)
    return out


def _events_for_symbol(symbol: str) -> dict[str, Any]:
    payload = _empty_symbol_payload()

    # SEC filings (free, always on)
    try:
        payload["filings"] = sec_edgar.fetch_recent_filings(symbol, limit=10)
    except Exception as exc:
        logger.warning("SEC filings error for %s: %s", symbol, exc)

    # Earnings — Polygon only for now
    if polygon.is_available():
        try:
            payload["earnings"] = polygon.fetch_earnings(symbol, limit=4)
        except Exception as exc:
            logger.warning("Polygon earnings error for %s: %s", symbol, exc)

    # News — Polygon + Benzinga merged + deduped
    news: list[dict[str, Any]] = []
    if polygon.is_available():
        try:
            news.extend(polygon.fetch_news(symbol, limit=5))
        except Exception as exc:
            logger.warning("Polygon news error for %s: %s", symbol, exc)
    if benzinga.is_available():
        try:
            news.extend(benzinga.fetch_news(symbol, limit=5))
        except Exception as exc:
            logger.warning("Benzinga news error for %s: %s", symbol, exc)
    if news:
        # Sort by published_at desc, then dedupe by URL
        news.sort(key=lambda n: n.get("published_at") or "", reverse=True)
        payload["news"] = _dedupe_news(news)[:8]

    # Options expirations — needs ThetaData / Tradier; not yet wired
    # payload["options_expirations"] stays []

    return payload


def get_events_for_symbols(symbols: list[str]) -> dict[str, Any]:
    """Aggregate events for up to MAX_SYMBOLS tickers."""
    cleaned = []
    seen: set[str] = set()
    for s in symbols:
        s_norm = (s or "").strip().upper()
        if not s_norm or s_norm in seen:
            continue
        seen.add(s_norm)
        cleaned.append(s_norm)
        if len(cleaned) >= MAX_SYMBOLS:
            break

    out: dict[str, Any] = {}
    for sym in cleaned:
        out[sym] = _events_for_symbol(sym)

    return {
        "symbols": out,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "providers": {
            "sec_edgar": sec_edgar.is_available(),
            "polygon":   polygon.is_available(),
            "benzinga":  benzinga.is_available(),
        },
    }


def get_events_for_symbol(symbol: str) -> dict[str, Any]:
    """Single-symbol variant for the research cockpit."""
    if not symbol:
        return {
            "events": _empty_symbol_payload(),
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
    return {
        "events": _events_for_symbol(symbol.strip().upper()),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "providers": {
            "sec_edgar": sec_edgar.is_available(),
            "polygon":   polygon.is_available(),
            "benzinga":  benzinga.is_available(),
        },
    }
