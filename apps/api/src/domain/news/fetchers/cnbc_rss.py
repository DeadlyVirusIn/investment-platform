"""CNBC top-news RSS adapter (market-wide headlines)."""

from __future__ import annotations

from apps.api.src.domain.news.fetchers.rss import RawItem, fetch_url, parse_rss

SOURCE = "cnbc_rss"
URL = "https://www.cnbc.com/id/100003114/device/rss/rss.html"


def fetch_top_news() -> list[RawItem]:
    try:
        xml = fetch_url(URL)
    except Exception:  # noqa: BLE001
        return []
    return parse_rss(xml, source=SOURCE)
