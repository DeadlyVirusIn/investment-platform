"""News ingestion orchestrator — dedup-safe inserts + symbol mapping.

Fetchers return ``RawItem`` blobs with only a ``_symbol_hint`` (Yahoo) or
nothing (CNBC). The ingest pass:

  1. Dedups by ``sha1(url)`` via the ``news_item.url_hash`` unique index.
  2. Runs the deterministic classifier.
  3. Maps to symbols:
       * if ``_symbol_hint`` present → direct map.
       * else scan the title for tickers in the given universe
         (case-sensitive, word-boundary matched; conservative).

Returns counts for logging.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from apps.api.src.db.models import NewsItem, NewsSymbolMap
from apps.api.src.domain.news.classifier import classify
from apps.api.src.domain.news.fetchers.rss import RawItem

FRESHNESS_DAYS = 14  # drop anything older than this from ingest


@dataclass
class IngestStats:
    fetched: int
    inserted: int
    duplicates: int
    mapped: int


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _symbol_candidates(title: str, known: set[str]) -> set[str]:
    """Conservative ticker scan. Requires either a leading ``$`` or an
    exact uppercase word-boundary match against a known universe."""
    if not known:
        return set()
    found: set[str] = set()
    # $TICKER style
    for m in re.finditer(r"\$([A-Z]{1,5})\b", title):
        sym = m.group(1).upper()
        if sym in known:
            found.add(sym)
    # Plain uppercase tokens — only emit if token is uppercase in original
    for m in re.finditer(r"\b([A-Z]{2,5})\b", title):
        sym = m.group(1)
        if sym in known:
            found.add(sym)
    return found


def _fresh(published_at: dt.datetime) -> bool:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=FRESHNESS_DAYS)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=dt.timezone.utc)
    return published_at >= cutoff


def ingest(
    session: Session,
    items: Sequence[RawItem],
    *,
    universe_symbols: Iterable[str] | None = None,
) -> IngestStats:
    known = {s.upper() for s in (universe_symbols or [])}

    fetched = 0
    inserted = 0
    duplicates = 0
    mapped = 0

    for raw in items:
        fetched += 1
        if not _fresh(raw.published_at):
            continue
        url_hash = _sha1(raw.url)
        cls = classify(raw.title, raw.summary)

        stmt = (
            pg_insert(NewsItem)
            .values(
                source=raw.source,
                url=raw.url,
                url_hash=url_hash,
                title=raw.title,
                summary=raw.summary,
                published_at=raw.published_at,
                category=cls.category,
                sentiment=cls.sentiment,
                sentiment_score=Decimal(str(cls.sentiment_score)),
                impact_level=cls.impact_level,
                impact_score=cls.impact_score,
                raw_payload=raw.raw,
            )
            .on_conflict_do_nothing(index_elements=["url_hash"])
            .returning(NewsItem.id)
        )
        result = session.execute(stmt).first()
        if result is None:
            duplicates += 1
            continue
        news_id = result[0]
        inserted += 1

        # Symbol mapping
        symbols: set[str] = set()
        hint = raw.raw.get("_symbol_hint") if isinstance(raw.raw, dict) else None
        if isinstance(hint, str):
            symbols.add(hint.upper())
        else:
            symbols |= _symbol_candidates(raw.title, known)

        for sym in symbols:
            session.execute(
                pg_insert(NewsSymbolMap)
                .values(news_id=news_id, symbol=sym)
                .on_conflict_do_nothing()
            )
            mapped += 1

    session.commit()
    return IngestStats(
        fetched=fetched, inserted=inserted,
        duplicates=duplicates, mapped=mapped,
    )
