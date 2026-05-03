"""Catalyst types — compact, UI-friendly, ML-loggable."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TradePolicy(str, Enum):
    NEUTRAL              = "neutral"
    REDUCE_SIZE          = "reduce_size"
    REQUIRE_CONFIRMATION = "require_confirmation"
    BLOCK_NEW_ENTRY      = "block_new_entry"
    WATCH_ONLY           = "watch_only"


@dataclass(frozen=True)
class Headline:
    title: str
    source: str                              # provider or publisher
    url: str | None
    published_at: dt.datetime | None
    sentiment: float | None = None           # -1..+1 if provider supplies
    relevance: float | None = None           # 0..1 to this symbol

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "published_at": self.published_at.isoformat()
                            if self.published_at else None,
            "sentiment": self.sentiment,
            "relevance": self.relevance,
        }


@dataclass(frozen=True)
class UpcomingEvent:
    kind: str                                # "earnings" | "dividend" | "macro"
    date: dt.date
    title: str
    confirmed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "date": self.date.isoformat(),
            "title": self.title,
            "confirmed": self.confirmed,
        }


@dataclass
class CatalystSummary:
    symbol: str
    as_of: dt.datetime
    next_event: UpcomingEvent | None = None
    days_to_earnings: int | None = None
    has_earnings_soon: bool = False
    headlines: list[Headline] = field(default_factory=list)
    catalyst_score: float = 0.0              # 0..1 overall catalyst intensity
    event_risk_score: float = 0.0            # 0..1 upcoming-event risk
    trade_policy: TradePolicy = TradePolicy.NEUTRAL
    short_reason: str = ""
    data_confidence: float = 1.0             # from reliability layer
    # Provenance
    providers_used: list[str] = field(default_factory=list)
    partial: bool = False                    # some providers failed

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "as_of": self.as_of.isoformat(),
            "next_event": self.next_event.to_dict() if self.next_event else None,
            "days_to_earnings": self.days_to_earnings,
            "has_earnings_soon": self.has_earnings_soon,
            "headlines": [h.to_dict() for h in self.headlines[:3]],
            "catalyst_score": round(self.catalyst_score, 4),
            "event_risk_score": round(self.event_risk_score, 4),
            "trade_policy": self.trade_policy.value,
            "short_reason": self.short_reason,
            "data_confidence": round(self.data_confidence, 4),
            "providers_used": list(self.providers_used),
            "partial": self.partial,
        }

    # ------ Engine-facing helpers ------

    def allows_new_entry(self) -> bool:
        return self.trade_policy not in {
            TradePolicy.BLOCK_NEW_ENTRY,
            TradePolicy.WATCH_ONLY,
        }

    def size_multiplier(self) -> float:
        """Engines multiply their intended size by this (range 0..1)."""
        if self.trade_policy == TradePolicy.BLOCK_NEW_ENTRY:
            return 0.0
        if self.trade_policy == TradePolicy.WATCH_ONLY:
            return 0.0
        if self.trade_policy == TradePolicy.REDUCE_SIZE:
            return 0.5
        if self.trade_policy == TradePolicy.REQUIRE_CONFIRMATION:
            return 0.35
        return 1.0
