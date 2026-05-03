"""Deterministic tests for catalyst scoring — no network.

Critical invariants:
  * earnings within 2 days → BLOCK
  * earnings within 5 days → REDUCE_SIZE
  * data_confidence < 0.3 → WATCH_ONLY
  * neutral when nothing catalyzing
  * sentiment-negative + near-earnings → REQUIRE_CONFIRMATION
"""

from __future__ import annotations

import datetime as dt

from apps.api.src.data.catalysts.scoring import build_summary
from apps.api.src.data.catalysts.types import (
    Headline, TradePolicy, UpcomingEvent,
)


NOW = dt.datetime(2026, 4, 23, 14, 0, tzinfo=dt.timezone.utc)
TODAY = NOW.date()


def _ev(days: int) -> UpcomingEvent:
    return UpcomingEvent(
        kind="earnings",
        date=TODAY + dt.timedelta(days=days),
        title="earnings",
        confirmed=True,
    )


def _headline(title: str, hours_old: int, sentiment: float | None = None):
    return Headline(
        title=title, source="test", url=None,
        published_at=NOW - dt.timedelta(hours=hours_old),
        sentiment=sentiment, relevance=1.0,
    )


def test_imminent_earnings_blocks_entry():
    s = build_summary(
        symbol="AAPL", now=NOW, next_event=_ev(1),
        headlines=[], data_confidence=1.0,
        providers_used=["finnhub:event"], partial=False,
    )
    assert s.trade_policy == TradePolicy.BLOCK_NEW_ENTRY
    assert s.has_earnings_soon is True
    assert s.days_to_earnings == 1
    assert s.event_risk_score >= 0.95


def test_earnings_near_window_reduces_size():
    s = build_summary(
        symbol="MSFT", now=NOW, next_event=_ev(4),
        headlines=[], data_confidence=1.0,
        providers_used=["yahoo:event"], partial=False,
    )
    assert s.trade_policy == TradePolicy.REDUCE_SIZE
    assert s.size_multiplier() < 1.0


def test_earnings_plus_negative_requires_confirmation():
    s = build_summary(
        symbol="NVDA", now=NOW, next_event=_ev(4),
        headlines=[_headline("guidance cut", 2, sentiment=-0.6)],
        data_confidence=1.0, providers_used=["f:e", "f:n"], partial=False,
    )
    assert s.trade_policy == TradePolicy.REQUIRE_CONFIRMATION


def test_low_data_confidence_locks_to_watch_only():
    s = build_summary(
        symbol="XYZ", now=NOW, next_event=None, headlines=[],
        data_confidence=0.2, providers_used=[], partial=True,
    )
    assert s.trade_policy == TradePolicy.WATCH_ONLY
    assert s.allows_new_entry() is False
    assert s.size_multiplier() == 0.0


def test_neutral_when_nothing_happening():
    s = build_summary(
        symbol="SPY", now=NOW, next_event=None, headlines=[],
        data_confidence=0.9, providers_used=["yahoo:news"], partial=False,
    )
    assert s.trade_policy == TradePolicy.NEUTRAL
    assert s.size_multiplier() == 1.0
    assert s.event_risk_score == 0.0


def test_recent_positive_catalyst_stays_neutral():
    # Positive sentiment alone shouldn't produce a restrictive policy.
    s = build_summary(
        symbol="META", now=NOW, next_event=None,
        headlines=[_headline("analyst upgrade", 1, sentiment=0.7)],
        data_confidence=1.0, providers_used=["y:n"], partial=False,
    )
    assert s.trade_policy in {TradePolicy.NEUTRAL, TradePolicy.REDUCE_SIZE}
    assert s.allows_new_entry() is True


def test_serialisation_roundtrip_shape():
    s = build_summary(
        symbol="AAPL", now=NOW, next_event=_ev(3),
        headlines=[_headline("beat", 5, sentiment=0.4)],
        data_confidence=0.8, providers_used=["finnhub:event"], partial=False,
    )
    d = s.to_dict()
    # Stable schema for frontend / ML pipeline
    assert set(d.keys()) >= {
        "symbol", "trade_policy", "catalyst_score", "event_risk_score",
        "headlines", "next_event", "days_to_earnings", "has_earnings_soon",
        "short_reason", "data_confidence", "providers_used", "partial",
    }
    assert d["trade_policy"] in {
        p.value for p in TradePolicy
    }
    assert 0.0 <= d["catalyst_score"] <= 1.0
    assert 0.0 <= d["event_risk_score"] <= 1.0
