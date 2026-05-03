"""Symbol-level + market-level news aggregations. Read-only.

All aggregations are simple, explainable, stdlib-only math. Supports:
    * per-symbol summary (count, avg sentiment, dominant category, latest)
    * market summary (top high-impact items, category breakdown)
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Sequence

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import NewsItem, NewsSymbolMap


POSITIVE_THRESHOLD = Decimal("0.30")
NEGATIVE_THRESHOLD = Decimal("-0.30")


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class NewsItemView:
    id: str
    source: str
    url: str
    title: str
    summary: str | None
    published_at: dt.datetime
    category: str
    sentiment: str
    sentiment_score: Decimal
    impact_level: str
    impact_score: int
    symbols: list[str] = field(default_factory=list)


@dataclass
class SymbolSummary:
    symbol: str
    window_days: int
    article_count: int
    avg_sentiment: Decimal | None         # [-1, +1]
    sentiment_label: str                   # positive / neutral / negative / unknown
    dominant_category: str | None
    category_counts: dict[str, int]
    max_impact_score: int
    latest: NewsItemView | None


@dataclass
class MarketSummary:
    window_days: int
    total_articles: int
    category_counts: dict[str, int]
    sentiment_counts: dict[str, int]
    top_headlines: list[NewsItemView]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_view(item: NewsItem, symbols: list[str]) -> NewsItemView:
    score = item.sentiment_score
    if not isinstance(score, Decimal):
        score = Decimal(str(score))
    return NewsItemView(
        id=item.id,
        source=item.source,
        url=item.url,
        title=item.title,
        summary=item.summary,
        published_at=item.published_at,
        category=item.category,
        sentiment=item.sentiment,
        sentiment_score=score,
        impact_level=item.impact_level,
        impact_score=int(item.impact_score),
        symbols=sorted(symbols),
    )


def _sentiment_label(avg: Decimal | None) -> str:
    if avg is None:
        return "unknown"
    if avg >= POSITIVE_THRESHOLD:
        return "positive"
    if avg <= NEGATIVE_THRESHOLD:
        return "negative"
    return "neutral"


def _load_symbol_map(
    session: Session, news_ids: Sequence[str],
) -> dict[str, list[str]]:
    if not news_ids:
        return {}
    stmt = select(NewsSymbolMap.news_id, NewsSymbolMap.symbol).where(
        NewsSymbolMap.news_id.in_(list(news_ids))
    )
    out: dict[str, list[str]] = {}
    for nid, sym in session.execute(stmt).all():
        out.setdefault(nid, []).append(sym)
    return out


def _window_lower(days: int) -> dt.datetime:
    now = dt.datetime.now(dt.timezone.utc)
    return now - dt.timedelta(days=max(1, days))


# ---------------------------------------------------------------------------
# Symbol-level
# ---------------------------------------------------------------------------


def list_symbol_news(
    session: Session, symbol: str, days: int = 7, limit: int = 20,
) -> list[NewsItemView]:
    """Latest N articles matching ``symbol`` within ``days``."""
    sym = symbol.upper()
    lower = _window_lower(days)

    stmt = (
        select(NewsItem)
        .join(NewsSymbolMap, NewsSymbolMap.news_id == NewsItem.id)
        .where(
            NewsSymbolMap.symbol == sym,
            NewsItem.published_at >= lower,
        )
        .order_by(desc(NewsItem.published_at))
        .limit(limit)
    )
    items = list(session.scalars(stmt))
    if not items:
        return []
    symbols = _load_symbol_map(session, [i.id for i in items])
    return [_to_view(it, symbols.get(it.id, [])) for it in items]


def summarize_symbol(
    session: Session, symbol: str, days: int = 7,
) -> SymbolSummary:
    sym = symbol.upper()
    items = list_symbol_news(session, sym, days=days, limit=500)
    if not items:
        return SymbolSummary(
            symbol=sym, window_days=days, article_count=0,
            avg_sentiment=None, sentiment_label="unknown",
            dominant_category=None, category_counts={},
            max_impact_score=0, latest=None,
        )
    scores = [it.sentiment_score for it in items]
    avg = sum(scores, Decimal("0")) / Decimal(len(scores))
    cats = Counter(it.category for it in items)
    dominant = cats.most_common(1)[0][0] if cats else None
    max_impact = max(it.impact_score for it in items)
    return SymbolSummary(
        symbol=sym, window_days=days,
        article_count=len(items),
        avg_sentiment=avg.quantize(Decimal("0.001")),
        sentiment_label=_sentiment_label(avg),
        dominant_category=dominant,
        category_counts=dict(cats),
        max_impact_score=max_impact,
        latest=items[0],
    )


def summarize_symbols_batch(
    session: Session, symbols: Iterable[str], days: int = 7,
) -> dict[str, SymbolSummary]:
    return {
        s.upper(): summarize_symbol(session, s.upper(), days=days)
        for s in symbols
    }


# ---------------------------------------------------------------------------
# Market-level
# ---------------------------------------------------------------------------


def market_summary(
    session: Session, days: int = 3, top_limit: int = 5,
) -> MarketSummary:
    lower = _window_lower(days)
    stmt = (
        select(NewsItem)
        .where(NewsItem.published_at >= lower)
        .order_by(
            desc(NewsItem.impact_score),
            desc(NewsItem.published_at),
        )
    )
    all_items = list(session.scalars(stmt))
    total = len(all_items)
    if total == 0:
        return MarketSummary(
            window_days=days, total_articles=0,
            category_counts={}, sentiment_counts={}, top_headlines=[],
        )
    cats = Counter(it.category for it in all_items)
    sentiments = Counter(it.sentiment for it in all_items)

    top_raw = all_items[:top_limit]
    symbols = _load_symbol_map(session, [t.id for t in top_raw])
    top = [_to_view(it, symbols.get(it.id, [])) for it in top_raw]

    return MarketSummary(
        window_days=days,
        total_articles=total,
        category_counts=dict(cats),
        sentiment_counts=dict(sentiments),
        top_headlines=top,
    )


# ---------------------------------------------------------------------------
# Latest feed
# ---------------------------------------------------------------------------


def list_latest(
    session: Session, limit: int = 20, days: int = 7,
) -> list[NewsItemView]:
    lower = _window_lower(days)
    stmt = (
        select(NewsItem)
        .where(NewsItem.published_at >= lower)
        .order_by(desc(NewsItem.published_at))
        .limit(limit)
    )
    items = list(session.scalars(stmt))
    if not items:
        return []
    symbols = _load_symbol_map(session, [i.id for i in items])
    return [_to_view(it, symbols.get(it.id, [])) for it in items]
