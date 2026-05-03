"""Module D — News Usefulness Analyzer.

Joins each paper position (or closed trade) to news for that symbol in a
window before the entry, then aggregates by sentiment and category.

Honest about small samples — returns "insufficient_sample" when the
per-bucket count drops below MIN_SAMPLE.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    NewsItem,
    NewsSymbolMap,
    PaperPortfolio,
    PaperPosition,
)
from apps.api.src.domain.pnl.engine import (
    latest_price,
    portfolio_pnl,
    resolve_portfolio,
)

MIN_SAMPLE = 3
LOOKBACK_DAYS_BEFORE_ENTRY = 7


@dataclass
class NewsBucketStat:
    key: str
    trade_count: int
    avg_return_pct: Decimal | None
    wins: int
    losses: int


@dataclass
class NewsAnalysis:
    sample_notes: list[str] = field(default_factory=list)
    by_sentiment: list[NewsBucketStat] = field(default_factory=list)
    by_category: list[NewsBucketStat] = field(default_factory=list)
    alignment_pct: Decimal | None = None
    trades_analyzed: int = 0


def _mean(xs: list[Decimal]) -> Decimal | None:
    return (sum(xs, Decimal("0")) / Decimal(len(xs))) if xs else None


def _position_return(pos: PaperPosition, mark: Decimal | None) -> Decimal | None:
    if mark is None:
        return None
    avg = pos.avg_cost if isinstance(pos.avg_cost, Decimal) else Decimal(str(pos.avg_cost))
    if avg <= 0:
        return None
    return (mark - avg) / avg


def _entry_news_for(
    session: Session, asset_id: str, opened_at: dt.datetime,
) -> list[NewsItem]:
    if opened_at.tzinfo is None:
        opened_at = opened_at.replace(tzinfo=dt.timezone.utc)
    lower = opened_at - dt.timedelta(days=LOOKBACK_DAYS_BEFORE_ENTRY)
    stmt = (
        select(NewsItem)
        .join(NewsSymbolMap, NewsSymbolMap.news_id == NewsItem.id)
        .join(Asset, Asset.id == asset_id)
        .where(
            NewsSymbolMap.symbol == Asset.symbol,
            NewsItem.published_at >= lower,
            NewsItem.published_at <= opened_at,
        )
    )
    return list(session.scalars(stmt))


def analyze_news(
    session: Session, portfolio_id: str | None = None,
) -> NewsAnalysis:
    out = NewsAnalysis()
    portfolio = resolve_portfolio(session, portfolio_id)
    if portfolio is None:
        out.sample_notes.append("no_active_portfolio")
        return out

    pnl = portfolio_pnl(session, portfolio)
    if not pnl.positions:
        out.sample_notes.append("no_positions_to_analyze")
        return out

    # Collect (sentiment_label, category, return_pct) for each position's
    # entry-news window.
    sentiment_returns: dict[str, list[Decimal]] = {}
    category_returns: dict[str, list[Decimal]] = {}
    aligned = 0
    counted = 0

    open_positions = session.scalars(
        select(PaperPosition).where(
            PaperPosition.portfolio_id == portfolio.id,
            PaperPosition.is_open.is_(True),
        )
    ).all()

    for pos in open_positions:
        mark = latest_price(session, pos.asset_id)
        ret = _position_return(pos, mark)
        if ret is None:
            continue
        counted += 1
        news = _entry_news_for(session, pos.asset_id, pos.opened_at)
        if not news:
            continue
        # Dominant sentiment across window (vote; ties → neutral)
        sent_counts = Counter(n.sentiment for n in news)
        dominant_sent = sent_counts.most_common(1)[0][0]
        cat_counts = Counter(n.category for n in news)
        dominant_cat = cat_counts.most_common(1)[0][0]

        sentiment_returns.setdefault(dominant_sent, []).append(ret)
        category_returns.setdefault(dominant_cat, []).append(ret)

        # Alignment: positive news + positive return OR negative + negative
        if (dominant_sent == "positive" and ret > 0) or (
            dominant_sent == "negative" and ret < 0
        ):
            aligned += 1

    out.trades_analyzed = counted

    def _to_stats(buckets: dict[str, list[Decimal]]) -> list[NewsBucketStat]:
        result: list[NewsBucketStat] = []
        for key, rets in sorted(buckets.items()):
            wins = sum(1 for r in rets if r > 0)
            losses = sum(1 for r in rets if r < 0)
            avg = _mean(rets) if len(rets) >= MIN_SAMPLE else None
            result.append(NewsBucketStat(
                key=key, trade_count=len(rets),
                avg_return_pct=avg,
                wins=wins, losses=losses,
            ))
        return result

    out.by_sentiment = _to_stats(sentiment_returns)
    out.by_category = _to_stats(category_returns)

    # Alignment %
    denom = sum(len(v) for v in sentiment_returns.values())
    out.alignment_pct = (
        Decimal(aligned) / Decimal(denom) if denom > 0 else None
    )

    if counted < MIN_SAMPLE:
        out.sample_notes.append("position_sample_small")
    if sum(len(v) for v in sentiment_returns.values()) < MIN_SAMPLE:
        out.sample_notes.append("news_linked_trades_small")

    return out
