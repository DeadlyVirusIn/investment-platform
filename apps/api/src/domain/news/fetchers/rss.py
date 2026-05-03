"""Minimal RSS 2.0 parser using stdlib. No new deps.

Exposes ``parse_rss(xml_bytes)`` → list of ``RawItem`` and ``fetch_url(url)``
using ``httpx`` (already a platform dep). Network calls are isolated to
``fetch_url`` so unit tests can feed XML bytes directly.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree import ElementTree as ET

import httpx

HTTP_TIMEOUT = 15.0


@dataclass
class RawItem:
    source: str
    url: str
    title: str
    summary: str | None
    published_at: dt.datetime
    raw: dict[str, Any]


def fetch_url(url: str, user_agent: str = "invest-platform/0.1") -> bytes:
    resp = httpx.get(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
        timeout=HTTP_TIMEOUT,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.content


def _parse_published(text: str | None) -> dt.datetime:
    if not text:
        return dt.datetime.now(dt.timezone.utc)
    try:
        return parsedate_to_datetime(text).astimezone(dt.timezone.utc)
    except (TypeError, ValueError):
        return dt.datetime.now(dt.timezone.utc)


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _first_child_text(elem: ET.Element, tag: str) -> str | None:
    for child in elem:
        if _strip_ns(child.tag) == tag:
            return (child.text or "").strip() or None
    return None


def parse_rss(xml_bytes: bytes, source: str) -> list[RawItem]:
    """Parse an RSS 2.0 feed. Silently skips malformed items."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []

    channel = None
    for child in root:
        if _strip_ns(child.tag) == "channel":
            channel = child
            break
    if channel is None:
        return []

    out: list[RawItem] = []
    for item in channel:
        if _strip_ns(item.tag) != "item":
            continue
        link = _first_child_text(item, "link")
        title = _first_child_text(item, "title")
        if not link or not title:
            continue
        desc = _first_child_text(item, "description")
        pub = _first_child_text(item, "pubDate")
        out.append(RawItem(
            source=source,
            url=link.strip(),
            title=title.strip(),
            summary=desc,
            published_at=_parse_published(pub),
            raw={"pubDate": pub, "description": desc},
        ))
    return out
