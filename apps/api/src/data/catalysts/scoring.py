"""Deterministic catalyst scoring.

Pure functions — no IO. Testable in isolation. Keeps TradePolicy derivation
centralised so providers can be swapped without changing behaviour.
"""

from __future__ import annotations

import datetime as dt

from apps.api.src.data.catalysts.types import (
    CatalystSummary, Headline, TradePolicy, UpcomingEvent,
)

# Tunables — collected here so tests + config can override.
EARNINGS_BLOCK_WINDOW_DAYS   = 2      # within N trading days → block
EARNINGS_REDUCE_WINDOW_DAYS  = 5      # within N days → reduce size
EARNINGS_WATCH_WINDOW_DAYS   = 10     # within N days → confidence decay
HEADLINE_RECENT_HOURS        = 24     # headlines newer than N hrs = fresh
HEADLINE_DECAY_HOURS         = 72     # exponential decay window


def compute_event_risk(
    next_event: UpcomingEvent | None,
    as_of: dt.date,
) -> tuple[float, int | None, bool]:
    """Return (risk_score 0..1, days_to_event or None, has_earnings_soon)."""
    if next_event is None or next_event.kind != "earnings":
        return 0.0, None, False
    days = (next_event.date - as_of).days
    if days < 0:
        return 0.0, days, False   # past
    if days <= EARNINGS_BLOCK_WINDOW_DAYS:
        return 1.0, days, True
    if days <= EARNINGS_REDUCE_WINDOW_DAYS:
        return 0.7, days, True
    if days <= EARNINGS_WATCH_WINDOW_DAYS:
        return 0.4, days, True
    # Linear decay past window — 10d -> 0.4, 30d -> ~0.1
    risk = max(0.0, 0.4 - (days - EARNINGS_WATCH_WINDOW_DAYS) * 0.015)
    return risk, days, False


def compute_catalyst_score(
    headlines: list[Headline],
    now: dt.datetime,
) -> float:
    """Weighted recency-decayed score 0..1 from headlines."""
    if not headlines:
        return 0.0
    total = 0.0
    weight_sum = 0.0
    for h in headlines:
        if h.published_at is None:
            continue
        age_h = (now - h.published_at).total_seconds() / 3600.0
        if age_h < 0:
            continue
        # Exponential decay: ~0.37 @ HEADLINE_DECAY_HOURS
        decay = 2.718281828 ** (-age_h / HEADLINE_DECAY_HOURS)
        relevance = h.relevance if h.relevance is not None else 0.5
        sentiment_mag = abs(h.sentiment) if h.sentiment is not None else 0.35
        weight = relevance * (0.5 + 0.5 * sentiment_mag)
        total += decay * weight
        weight_sum += weight
    if weight_sum == 0.0:
        return 0.0
    normalised = total / max(weight_sum, 1e-9)
    return max(0.0, min(1.0, normalised))


def derive_policy(
    event_risk: float,
    catalyst_score: float,
    has_negative_headline: bool,
    data_confidence: float,
) -> tuple[TradePolicy, str]:
    """Combine signals into a single trade policy + short reason."""
    # Critical data gap → watch only
    if data_confidence < 0.3:
        return TradePolicy.WATCH_ONLY, "data confidence below 0.3"

    # Hard block: earnings imminent
    if event_risk >= 0.95:
        return TradePolicy.BLOCK_NEW_ENTRY, "earnings within 2 trading days"

    # High event risk + negative news → require confirmation
    if event_risk >= 0.6 and has_negative_headline:
        return TradePolicy.REQUIRE_CONFIRMATION, "earnings + negative catalyst"

    # High event risk alone → reduce size
    if event_risk >= 0.6:
        return TradePolicy.REDUCE_SIZE, "earnings within ~5 days"

    # High catalyst intensity with negative headlines
    if catalyst_score >= 0.65 and has_negative_headline:
        return TradePolicy.REQUIRE_CONFIRMATION, "elevated negative catalyst"

    # Mild elevation
    if catalyst_score >= 0.5 or event_risk >= 0.3:
        return TradePolicy.REDUCE_SIZE, "elevated catalyst / event"

    return TradePolicy.NEUTRAL, "no notable catalyst"


def has_negative_headline(headlines: list[Headline]) -> bool:
    return any(
        (h.sentiment is not None and h.sentiment < -0.25) for h in headlines
    )


def build_summary(
    *, symbol: str,
    now: dt.datetime,
    next_event: UpcomingEvent | None,
    headlines: list[Headline],
    data_confidence: float,
    providers_used: list[str],
    partial: bool,
) -> CatalystSummary:
    """Assemble a fully-scored CatalystSummary from raw inputs."""
    event_risk, days, earnings_soon = compute_event_risk(
        next_event, as_of=now.date(),
    )
    cat_score = compute_catalyst_score(headlines, now=now)
    neg = has_negative_headline(headlines)
    policy, reason = derive_policy(
        event_risk=event_risk,
        catalyst_score=cat_score,
        has_negative_headline=neg,
        data_confidence=data_confidence,
    )
    # Trim + sort headlines: newest first, cap to 3
    sorted_headlines = sorted(
        [h for h in headlines if h.published_at is not None],
        key=lambda h: h.published_at or now,
        reverse=True,
    )[:3]
    return CatalystSummary(
        symbol=symbol,
        as_of=now,
        next_event=next_event,
        days_to_earnings=days,
        has_earnings_soon=earnings_soon,
        headlines=sorted_headlines,
        catalyst_score=cat_score,
        event_risk_score=event_risk,
        trade_policy=policy,
        short_reason=reason,
        data_confidence=data_confidence,
        providers_used=providers_used,
        partial=partial,
    )
