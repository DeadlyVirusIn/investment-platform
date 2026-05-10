"""Phase 10 — Event-Aware Signal features.

Converts raw market events (filings, news, earnings) into a small
set of structured features per symbol. Features are ADVISORY:

    They feed into recommendation rationale and confidence,
    but never directly create Buy/Sell triggers.

Honest data discipline: features are computed from real provider
output only (SEC EDGAR + Polygon + Benzinga via market_events
service). When no events exist for a symbol the feature dict comes
back with all zeros / Nones and a flag explaining the absence.

Feature catalog:
    recent_8k_count_7d        int  — count of 8-K filings in last 7 days
    recent_10q_or_10k_flag    bool — 10-Q or 10-K filed in last 14 days
    news_count_3d             int  — total news items in last 3 days
    negative_news_count_3d    int
    positive_news_count_3d    int
    catalyst_freshness_score  0..1 (1 = within 24h, 0 = >14d / none)
    earnings_within_14d       bool — upcoming earnings in next 14 days
    filing_recency_days       int  — days since most recent filing (or None)
    high_impact_news_flag     bool — 3+ news items in last 24h
    event_risk_score          0..1 (weighted negative signals)
    event_momentum_score      0..1 (weighted positive signals)
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from apps.api.src.domain.market_events.service import (
    get_events_for_symbols,
)

logger = logging.getLogger(__name__)


def _parse_iso(s: Any) -> dt.datetime | None:
    if not s or not isinstance(s, str):
        return None
    try:
        # Tolerate trailing Z
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return dt.datetime.fromisoformat(s)
    except Exception:
        try:
            return dt.datetime.fromisoformat(s[:10])
        except Exception:
            return None


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _days_since(iso: Any) -> int | None:
    parsed = _parse_iso(iso)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    delta = _now_utc() - parsed
    return max(0, int(delta.total_seconds() // 86400))


def _within_days(iso: Any, days: int) -> bool:
    d = _days_since(iso)
    return d is not None and 0 <= d <= days


def _within_hours(iso: Any, hours: int) -> bool:
    parsed = _parse_iso(iso)
    if parsed is None:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    delta = _now_utc() - parsed
    return 0 <= delta.total_seconds() <= hours * 3600


def _empty_features(reason: str) -> dict[str, Any]:
    return {
        "recent_8k_count_7d": 0,
        "recent_10q_or_10k_flag": False,
        "news_count_3d": 0,
        "negative_news_count_3d": 0,
        "positive_news_count_3d": 0,
        "catalyst_freshness_score": 0.0,
        "earnings_within_14d": False,
        "filing_recency_days": None,
        "high_impact_news_flag": False,
        "event_risk_score": 0.0,
        "event_momentum_score": 0.0,
        "tags": [],
        "explainers": [],
        "available": False,
        "reason": reason,
    }


def _earnings_distance_days(earnings: list[dict[str, Any]]) -> int | None:
    """Smallest non-negative day-distance to an upcoming earnings event."""
    out: int | None = None
    for e in earnings:
        if (e.get("status") or "").lower() != "upcoming":
            continue
        parsed = _parse_iso(e.get("date"))
        if parsed is None:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        delta_days = int((parsed - _now_utc()).total_seconds() // 86400)
        if delta_days < 0:
            continue
        if out is None or delta_days < out:
            out = delta_days
    return out


def _freshness_score(days: int | None) -> float:
    """1.0 within 1d, decays linearly to 0.0 by 14d, 0 beyond."""
    if days is None:
        return 0.0
    if days <= 1:
        return 1.0
    if days >= 14:
        return 0.0
    return round(1.0 - (days - 1) / 13.0, 3)


def compute_features_from_events(events: dict[str, Any]) -> dict[str, Any]:
    """Compute the feature dict from a single SymbolEvents payload."""
    if not events:
        return _empty_features("no_events_payload")

    filings: list[dict[str, Any]] = events.get("filings") or []
    news:    list[dict[str, Any]] = events.get("news") or []
    earnings: list[dict[str, Any]] = events.get("earnings") or []

    if not filings and not news and not earnings:
        return _empty_features("no_events")

    # Filings
    recent_8k = sum(
        1 for f in filings
        if (f.get("form") or "").upper().startswith("8-K")
        and _within_days(f.get("filed_at"), 7)
    )
    recent_10q_or_10k = any(
        (f.get("form") or "").upper() in {"10-Q", "10-K"}
        and _within_days(f.get("filed_at"), 14)
        for f in filings
    )

    # Most recent filing recency
    filing_days_list = [
        d for d in (_days_since(f.get("filed_at")) for f in filings) if d is not None
    ]
    filing_recency_days: int | None = min(filing_days_list) if filing_days_list else None

    # News
    news_3d = [n for n in news if _within_days(n.get("published_at"), 3)]
    news_24h = [n for n in news if _within_hours(n.get("published_at"), 24)]
    pos_3d = sum(1 for n in news_3d if (n.get("sentiment") or "").lower() == "positive")
    neg_3d = sum(1 for n in news_3d if (n.get("sentiment") or "").lower() == "negative")
    high_impact = len(news_24h) >= 3

    # Earnings
    earn_distance = _earnings_distance_days(earnings)
    earnings_within_14d = earn_distance is not None and earn_distance <= 14

    # Freshness — closest of (latest news, latest filing)
    candidates = []
    if filing_recency_days is not None:
        candidates.append(filing_recency_days)
    news_recency_list = [
        d for d in (_days_since(n.get("published_at")) for n in news) if d is not None
    ]
    if news_recency_list:
        candidates.append(min(news_recency_list))
    catalyst_freshness = _freshness_score(min(candidates) if candidates else None)

    # Composite advisory scores
    risk_components: list[float] = []
    if neg_3d > 0:
        risk_components.append(min(1.0, neg_3d / 3.0))
    if recent_8k > 0:
        risk_components.append(min(1.0, recent_8k / 2.0) * 0.6)
    if high_impact and neg_3d > pos_3d:
        risk_components.append(0.4)
    event_risk_score = round(min(1.0, sum(risk_components) / max(1, len(risk_components))), 3) if risk_components else 0.0

    momentum_components: list[float] = []
    if pos_3d > 0:
        momentum_components.append(min(1.0, pos_3d / 3.0))
    if recent_10q_or_10k:
        momentum_components.append(0.3)
    if high_impact and pos_3d >= neg_3d:
        momentum_components.append(0.4)
    event_momentum_score = round(min(1.0, sum(momentum_components) / max(1, len(momentum_components))), 3) if momentum_components else 0.0

    # Plain-English tags + explainers (UI-friendly)
    tags: list[str] = []
    explainers: list[str] = []

    if recent_10q_or_10k:
        tags.append("Recent filing")
        explainers.append("10-Q or 10-K filed in the last 14 days.")
    if recent_8k > 0:
        tags.append(f"{recent_8k} new 8-K" + ("s" if recent_8k != 1 else ""))
        explainers.append("Material event(s) disclosed via 8-K in the last 7 days.")
    if earnings_within_14d:
        tags.append("Earnings window approaching")
        explainers.append(f"Upcoming earnings in {earn_distance}d.")
    if high_impact and neg_3d > pos_3d:
        tags.append("News risk rising")
        explainers.append("Negative news cluster detected in the last 24h.")
    elif high_impact:
        tags.append("News spike")
        explainers.append("High news volume in the last 24h.")
    if not tags:
        tags.append("No fresh catalyst")
        explainers.append("No recent filings, news, or earnings activity.")

    return {
        "recent_8k_count_7d": recent_8k,
        "recent_10q_or_10k_flag": recent_10q_or_10k,
        "news_count_3d": len(news_3d),
        "negative_news_count_3d": neg_3d,
        "positive_news_count_3d": pos_3d,
        "catalyst_freshness_score": catalyst_freshness,
        "earnings_within_14d": earnings_within_14d,
        "filing_recency_days": filing_recency_days,
        "high_impact_news_flag": high_impact,
        "event_risk_score": event_risk_score,
        "event_momentum_score": event_momentum_score,
        "tags": tags,
        "explainers": explainers,
        "available": True,
        "reason": None,
    }


def get_event_features_for_symbols(symbols: list[str]) -> dict[str, Any]:
    """Top-level orchestration: fetch market events then compute features."""
    raw = get_events_for_symbols(symbols)
    out: dict[str, Any] = {}
    for sym, ev in (raw.get("symbols") or {}).items():
        out[sym] = compute_features_from_events(ev)
    return {
        "symbols": out,
        "generated_at": raw.get("generated_at"),
        "providers": raw.get("providers"),
        "notice": (
            "Advisory features only. Inform recommendation rationale and "
            "confidence; do not directly create Buy/Sell triggers."
        ),
    }
