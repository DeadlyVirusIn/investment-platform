"""Integration: news ingestion dedup, aggregation, endpoints."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.src.db.models import NewsItem, NewsSymbolMap
from apps.api.src.domain.news.aggregator import (
    list_symbol_news,
    market_summary,
    summarize_symbol,
)
from apps.api.src.domain.news.fetchers.rss import RawItem
from apps.api.src.domain.news.ingest_service import ingest

pytestmark = pytest.mark.integration


def _raw(
    url: str, title: str, summary: str | None = None,
    published_at: dt.datetime | None = None,
    symbol_hint: str | None = None,
    source: str = "yahoo_rss",
) -> RawItem:
    raw = {}
    if symbol_hint is not None:
        raw["_symbol_hint"] = symbol_hint
    return RawItem(
        source=source, url=url, title=title, summary=summary,
        published_at=published_at or dt.datetime.now(dt.timezone.utc),
        raw=raw,
    )


def test_ingest_inserts_and_dedupes(pg_session: Session) -> None:
    items = [
        _raw("https://example.com/a", "NVDA beats earnings", symbol_hint="NVDA"),
        _raw("https://example.com/a", "duplicate URL ignored", symbol_hint="NVDA"),
        _raw("https://example.com/b", "GOOGL faces SEC probe", symbol_hint="GOOGL"),
    ]
    stats = ingest(pg_session, items, universe_symbols=["NVDA", "GOOGL"])
    assert stats.fetched == 3
    assert stats.inserted == 2
    assert stats.duplicates == 1
    assert stats.mapped == 2
    rows = list(pg_session.query(NewsItem).all())
    assert len(rows) == 2


def test_classifier_persisted_correctly(pg_session: Session) -> None:
    items = [
        _raw("https://example.com/earn", "Tesla beats earnings, revenue beat",
             symbol_hint="TSLA"),
        _raw("https://example.com/sec", "SEC investigation opens into firm",
             symbol_hint="XYZ"),
    ]
    ingest(pg_session, items, universe_symbols=["TSLA", "XYZ"])
    rows = {r.title: r for r in pg_session.query(NewsItem).all()}
    assert rows["Tesla beats earnings, revenue beat"].category == "earnings"
    assert rows["Tesla beats earnings, revenue beat"].sentiment == "positive"
    assert rows["Tesla beats earnings, revenue beat"].impact_level == "high"
    assert rows["SEC investigation opens into firm"].category == "regulatory"
    assert rows["SEC investigation opens into firm"].sentiment == "negative"


def test_symbol_mapping_from_title_scan(pg_session: Session) -> None:
    items = [
        _raw(
            "https://example.com/scan",
            "Analyst upgrades AAPL and MSFT on strong demand",
            source="cnbc_rss",
        ),
    ]
    ingest(pg_session, items, universe_symbols=["AAPL", "MSFT", "NVDA"])
    maps = list(pg_session.query(NewsSymbolMap).all())
    syms = {m.symbol for m in maps}
    assert "AAPL" in syms
    assert "MSFT" in syms
    assert "NVDA" not in syms


def test_list_symbol_news_filters_by_window(pg_session: Session) -> None:
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=12)
    new = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
    items = [
        _raw("https://example.com/old", "old NVDA story", published_at=old,
             symbol_hint="NVDA"),
        _raw("https://example.com/new", "fresh NVDA story", published_at=new,
             symbol_hint="NVDA"),
    ]
    ingest(pg_session, items, universe_symbols=["NVDA"])
    rows = list_symbol_news(pg_session, "NVDA", days=7, limit=10)
    assert len(rows) == 1
    assert rows[0].title == "fresh NVDA story"


def test_summarize_symbol_aggregates(pg_session: Session) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    items = [
        _raw("https://example.com/1", "NVDA beats earnings", symbol_hint="NVDA",
             published_at=now - dt.timedelta(hours=1)),
        _raw("https://example.com/2", "NVDA analyst upgrade, price target raised",
             symbol_hint="NVDA",
             published_at=now - dt.timedelta(hours=3)),
        _raw("https://example.com/3", "NVDA faces SEC probe", symbol_hint="NVDA",
             published_at=now - dt.timedelta(hours=2)),
    ]
    ingest(pg_session, items, universe_symbols=["NVDA"])

    summary = summarize_symbol(pg_session, "NVDA", days=7)
    assert summary.article_count == 3
    assert summary.max_impact_score == 3
    assert summary.latest is not None
    assert summary.latest.title == "NVDA beats earnings"
    # Mix of +1, +1, -1 → avg > 0 → positive
    assert summary.sentiment_label in ("positive", "neutral")
    assert set(summary.category_counts.keys()) >= {"earnings", "analyst", "regulatory"}


def test_market_summary_ranks_by_impact(pg_session: Session) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    items = [
        _raw("https://example.com/a", "Fed raises interest rate",
             published_at=now - dt.timedelta(hours=1)),
        _raw("https://example.com/b", "Random corporate news",
             published_at=now - dt.timedelta(hours=2)),
    ]
    ingest(pg_session, items)

    summary = market_summary(pg_session, days=3, top_limit=5)
    assert summary.total_articles == 2
    # Higher impact first
    assert summary.top_headlines[0].title == "Fed raises interest rate"
    assert summary.category_counts.get("macro") == 1


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def test_news_symbol_endpoint(pg_session: Session) -> None:
    from apps.api.src.main import app

    items = [
        _raw("https://example.com/x", "NVDA beats earnings", symbol_hint="NVDA"),
    ]
    ingest(pg_session, items, universe_symbols=["NVDA"])

    client = TestClient(app)
    resp = client.get("/api/news/symbol/NVDA?days=7&limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "NVDA"
    assert data["count"] == 1
    assert data["items"][0]["title"] == "NVDA beats earnings"
    assert data["summary"]["article_count"] == 1


def test_news_summary_batch_endpoint(pg_session: Session) -> None:
    from apps.api.src.main import app

    items = [
        _raw("https://example.com/a", "NVDA beats earnings", symbol_hint="NVDA"),
        _raw("https://example.com/b", "AMZN unveils new product", symbol_hint="AMZN"),
    ]
    ingest(pg_session, items, universe_symbols=["NVDA", "AMZN"])

    client = TestClient(app)
    resp = client.get("/api/news/summary?symbols=NVDA&symbols=AMZN")
    assert resp.status_code == 200
    data = resp.json()
    assert "NVDA" in data["summaries"]
    assert "AMZN" in data["summaries"]
    assert data["summaries"]["NVDA"]["article_count"] == 1


def test_news_market_summary_endpoint(pg_session: Session) -> None:
    from apps.api.src.main import app

    items = [_raw("https://example.com/m", "Fed cuts rates")]
    ingest(pg_session, items)
    client = TestClient(app)
    resp = client.get("/api/news/market-summary?days=3")
    assert resp.status_code == 200
    assert resp.json()["total_articles"] == 1


def test_news_latest_endpoint(pg_session: Session) -> None:
    from apps.api.src.main import app

    items = [_raw("https://example.com/l", "A generic headline")]
    ingest(pg_session, items)
    client = TestClient(app)
    resp = client.get("/api/news/latest?limit=5")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
