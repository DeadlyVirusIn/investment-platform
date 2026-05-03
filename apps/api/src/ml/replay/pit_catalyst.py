"""Replay-safe catalyst service.

CRITICAL: historical catalyst context must NOT use live Finnhub/Yahoo
responses — those return current-date news. For replay, this service
returns a catalyst summary built ONLY from rows in our DB whose
`published_at <= as_of_date` (if the historical news table is populated).

If no historical catalyst data exists for the symbol/date, returns a
neutral summary with `data_confidence=0.0` and `partial=True`. Engines
downstream then reduce confidence automatically.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.data.catalysts.scoring import build_summary
from apps.api.src.data.catalysts.types import (
    CatalystSummary, Headline, UpcomingEvent,
)


class PITCatalystService:
    """Point-in-time catalyst summary — DB only, no live providers."""

    def __init__(self, session: Session):
        self._session = session

    def summary_for(
        self, symbol: str, *, as_of: dt.date,
    ) -> CatalystSummary:
        now = dt.datetime.combine(as_of, dt.time(16, 0),
                                    tzinfo=dt.timezone.utc)
        headlines = self._fetch_headlines(symbol, as_of=as_of)
        next_event = self._fetch_next_event(symbol, as_of=as_of)
        providers_used: list[str] = []
        partial = False
        if headlines:
            providers_used.append("db:news")
        else:
            partial = True
        if next_event:
            providers_used.append("db:earnings")
        else:
            partial = True
        data_conf = _confidence_from_availability(
            has_event=next_event is not None,
            has_news=bool(headlines),
            partial=partial,
        )
        return build_summary(
            symbol=symbol,
            now=now,
            next_event=next_event,
            headlines=headlines,
            data_confidence=data_conf,
            providers_used=providers_used,
            partial=partial,
        )

    # ------------------------------------------------------------------
    # DB lookups — tolerant of missing tables / missing columns
    # ------------------------------------------------------------------

    def _fetch_headlines(
        self, symbol: str, *, as_of: dt.date, limit: int = 3,
    ) -> list[Headline]:
        window_start = as_of - dt.timedelta(days=3)
        try:
            rows = self._session.execute(text("""
                SELECT n.title, n.source, n.url, n.published_at,
                       n.sentiment, n.sentiment_score
                FROM news_item n
                JOIN news_symbol_map m ON m.news_item_id = n.id
                WHERE m.symbol = :sym
                  AND n.published_at <= :asof
                  AND n.published_at >= :start
                ORDER BY n.published_at DESC
                LIMIT :lim
            """), {
                "sym": symbol.upper(),
                "asof": dt.datetime.combine(as_of, dt.time(23, 59),
                                              tzinfo=dt.timezone.utc),
                "start": dt.datetime.combine(window_start, dt.time(0, 0),
                                               tzinfo=dt.timezone.utc),
                "lim":   int(limit),
            }).mappings().all()
        except Exception:
            return []
        out: list[Headline] = []
        for r in rows:
            sentiment = r.get("sentiment_score")
            if sentiment is None:
                sentiment = _sentiment_label_to_num(r.get("sentiment"))
            out.append(Headline(
                title=str(r.get("title") or ""),
                source=str(r.get("source") or "db"),
                url=r.get("url"),
                published_at=r.get("published_at"),
                sentiment=_f(sentiment),
                relevance=None,
            ))
        return out

    def _fetch_next_event(
        self, symbol: str, *, as_of: dt.date,
    ) -> UpcomingEvent | None:
        """Look up the next earnings event known AT as_of_date.

        Require both:
          event_date >= as_of_date    (upcoming)
          known_at  <= as_of_date     (we had this knowledge by then)
        """
        try:
            row = self._session.execute(text("""
                SELECT event_date, known_at, source
                FROM earnings_event
                WHERE symbol = :sym
                  AND event_date >= :asof
                  AND (known_at IS NULL OR known_at <= :asof_ts)
                ORDER BY event_date ASC
                LIMIT 1
            """), {
                "sym": symbol.upper(),
                "asof": as_of,
                "asof_ts": dt.datetime.combine(
                    as_of, dt.time(23, 59), tzinfo=dt.timezone.utc,
                ),
            }).mappings().first()
        except Exception:
            return None
        if not row:
            return None
        return UpcomingEvent(
            kind="earnings",
            date=row["event_date"],
            title=f"{symbol} earnings",
            confirmed=True,
        )


def _confidence_from_availability(
    *, has_event: bool, has_news: bool, partial: bool,
) -> float:
    if not (has_event or has_news):
        return 0.0
    score = 0.5
    if has_event: score += 0.3
    if has_news:  score += 0.2
    if partial:   score *= 0.85
    return max(0.0, min(1.0, score))


def _sentiment_label_to_num(label: Any) -> float | None:
    if label is None:
        return None
    s = str(label).strip().lower()
    if s in {"positive", "pos", "bullish"}:   return 0.5
    if s in {"negative", "neg", "bearish"}:   return -0.5
    if s in {"neutral"}:                       return 0.0
    return None


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
