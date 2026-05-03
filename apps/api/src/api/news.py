"""News API — 4 read-only endpoints over stored news_item rows."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.domain.news.aggregator import (
    MarketSummary,
    NewsItemView,
    SymbolSummary,
    list_latest,
    list_symbol_news,
    market_summary,
    summarize_symbol,
    summarize_symbols_batch,
)

router = APIRouter(prefix="/news", tags=["news"])


def _dec(v: Decimal | None) -> str | None:
    return str(v) if v is not None else None


def _item_payload(v: NewsItemView) -> dict[str, Any]:
    return {
        "id": v.id,
        "source": v.source,
        "url": v.url,
        "title": v.title,
        "summary": v.summary,
        "published_at": v.published_at.isoformat(),
        "category": v.category,
        "sentiment": v.sentiment,
        "sentiment_score": _dec(v.sentiment_score),
        "impact_level": v.impact_level,
        "impact_score": v.impact_score,
        "symbols": v.symbols,
    }


def _summary_payload(s: SymbolSummary) -> dict[str, Any]:
    return {
        "symbol": s.symbol,
        "window_days": s.window_days,
        "article_count": s.article_count,
        "avg_sentiment": _dec(s.avg_sentiment),
        "sentiment_label": s.sentiment_label,
        "dominant_category": s.dominant_category,
        "category_counts": s.category_counts,
        "max_impact_score": s.max_impact_score,
        "latest": _item_payload(s.latest) if s.latest else None,
    }


def _market_payload(m: MarketSummary) -> dict[str, Any]:
    return {
        "window_days": m.window_days,
        "total_articles": m.total_articles,
        "category_counts": m.category_counts,
        "sentiment_counts": m.sentiment_counts,
        "top_headlines": [_item_payload(it) for it in m.top_headlines],
    }


@router.get("/symbol/{symbol}")
def get_symbol_news(
    symbol: str,
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(10, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    sym = symbol.upper()
    items = list_symbol_news(session, sym, days=days, limit=limit)
    summary = summarize_symbol(session, sym, days=days)
    return {
        "symbol": sym,
        "summary": _summary_payload(summary),
        "count": len(items),
        "items": [_item_payload(it) for it in items],
    }


@router.get("/summary")
def get_news_summary(
    symbols: list[str] = Query(..., alias="symbols"),
    days: int = Query(7, ge=1, le=90),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    summaries = summarize_symbols_batch(session, symbols, days=days)
    return {
        "days": days,
        "count": len(summaries),
        "summaries": {k: _summary_payload(v) for k, v in summaries.items()},
    }


@router.get("/market-summary")
def get_market_summary(
    days: int = Query(3, ge=1, le=30),
    limit: int = Query(5, ge=1, le=20),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _market_payload(market_summary(session, days=days, top_limit=limit))


@router.get("/latest")
def get_latest(
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    items = list_latest(session, limit=limit, days=days)
    return {
        "days": days,
        "count": len(items),
        "items": [_item_payload(it) for it in items],
    }
