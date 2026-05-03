"""Yahoo Finance per-symbol RSS adapter."""

from __future__ import annotations

from typing import Iterable

from apps.api.src.domain.news.fetchers.rss import RawItem, fetch_url, parse_rss

SOURCE = "yahoo_rss"
URL_TEMPLATE = (
    "https://feeds.finance.yahoo.com/rss/2.0/headline"
    "?s={symbol}&region=US&lang=en-US"
)


def fetch_for_symbol(symbol: str) -> list[RawItem]:
    url = URL_TEMPLATE.format(symbol=symbol.upper())
    try:
        xml = fetch_url(url)
    except Exception:  # noqa: BLE001 — network flakiness must not poison the job
        return []
    items = parse_rss(xml, source=SOURCE)
    # Tag the originating symbol on each raw item so the orchestrator can
    # link without guessing.
    for it in items:
        it.raw["_symbol_hint"] = symbol.upper()
    return items


def fetch_for_symbols(symbols: Iterable[str]) -> list[RawItem]:
    out: list[RawItem] = []
    for s in symbols:
        out.extend(fetch_for_symbol(s))
    return out
