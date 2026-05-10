"""Tests for the Phase 10 event-feature pipeline."""

from __future__ import annotations

import datetime as dt

import pytest

from apps.api.src.domain.event_features.service import (
    compute_features_from_events,
    _empty_features,
)


def _now_iso(days_ago: float) -> str:
    """Helper: ISO timestamp `days_ago` days before now (UTC)."""
    delta = dt.timedelta(days=days_ago)
    return (dt.datetime.now(dt.timezone.utc) - delta).isoformat()


class TestEmptyFeatures:
    def test_empty_payload(self) -> None:
        f = compute_features_from_events({})
        assert f["available"] is False
        assert f["reason"] == "no_events_payload"
        assert f["recent_8k_count_7d"] == 0
        assert f["event_risk_score"] == 0.0

    def test_payload_with_no_events(self) -> None:
        f = compute_features_from_events({
            "filings": [], "news": [], "earnings": [], "options_expirations": []
        })
        assert f["available"] is False
        assert f["reason"] == "no_events"

    def test_no_recent_events_yields_no_fresh_catalyst_tag(self) -> None:
        f = compute_features_from_events({
            "filings": [
                {"form": "10-K", "filed_at": _now_iso(400), "title": "old", "url": "u"},
            ],
            "news": [], "earnings": [],
        })
        # Filing is old → recent_10q_or_10k_flag False, recency days >> 14
        assert f["available"] is True
        assert f["recent_10q_or_10k_flag"] is False
        assert f["filing_recency_days"] is not None
        assert f["catalyst_freshness_score"] == 0.0
        assert "No fresh catalyst" in f["tags"]


class Test8KCounting:
    def test_8k_within_7d_counted(self) -> None:
        f = compute_features_from_events({
            "filings": [
                {"form": "8-K", "filed_at": _now_iso(2), "title": "8-K", "url": "u1"},
                {"form": "8-K", "filed_at": _now_iso(5), "title": "8-K", "url": "u2"},
                {"form": "8-K", "filed_at": _now_iso(10), "title": "8-K", "url": "u3"},
            ],
            "news": [], "earnings": [],
        })
        assert f["recent_8k_count_7d"] == 2
        assert any("8-K" in t for t in f["tags"])

    def test_10q_within_14d_flag(self) -> None:
        f = compute_features_from_events({
            "filings": [
                {"form": "10-Q", "filed_at": _now_iso(5), "title": "10-Q", "url": "u"},
            ],
            "news": [], "earnings": [],
        })
        assert f["recent_10q_or_10k_flag"] is True
        assert "Recent filing" in f["tags"]

    def test_10k_within_14d_flag(self) -> None:
        f = compute_features_from_events({
            "filings": [
                {"form": "10-K", "filed_at": _now_iso(10), "title": "10-K", "url": "u"},
            ],
            "news": [], "earnings": [],
        })
        assert f["recent_10q_or_10k_flag"] is True


class TestNewsCounting:
    def test_news_3d_window(self) -> None:
        f = compute_features_from_events({
            "filings": [],
            "news": [
                {"title": "a", "published_at": _now_iso(1), "sentiment": "positive", "url": "u1", "source": "s"},
                {"title": "b", "published_at": _now_iso(2), "sentiment": "negative", "url": "u2", "source": "s"},
                {"title": "c", "published_at": _now_iso(5), "sentiment": "positive", "url": "u3", "source": "s"},
            ],
            "earnings": [],
        })
        assert f["news_count_3d"] == 2
        assert f["positive_news_count_3d"] == 1
        assert f["negative_news_count_3d"] == 1

    def test_high_impact_threshold(self) -> None:
        f = compute_features_from_events({
            "filings": [],
            "news": [
                {"title": str(i), "published_at": _now_iso(0.1), "sentiment": "negative",
                 "url": f"u{i}", "source": "s"}
                for i in range(4)
            ],
            "earnings": [],
        })
        assert f["high_impact_news_flag"] is True
        assert f["event_risk_score"] > 0.0
        assert "News risk rising" in f["tags"]

    def test_high_impact_positive_tags_news_spike(self) -> None:
        f = compute_features_from_events({
            "filings": [],
            "news": [
                {"title": str(i), "published_at": _now_iso(0.1), "sentiment": "positive",
                 "url": f"u{i}", "source": "s"}
                for i in range(4)
            ],
            "earnings": [],
        })
        assert f["high_impact_news_flag"] is True
        assert "News spike" in f["tags"]
        assert f["event_momentum_score"] > 0.0


class TestEarnings:
    def test_upcoming_earnings_within_14d_true(self) -> None:
        future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=10)).isoformat()
        f = compute_features_from_events({
            "filings": [],
            "news": [],
            "earnings": [
                {"date": future, "type": "AMC",
                 "estimate_eps": None, "actual_eps": None, "status": "upcoming"},
            ],
        })
        assert f["earnings_within_14d"] is True
        assert "Earnings window approaching" in f["tags"]

    def test_past_earnings_ignored(self) -> None:
        past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=20)).isoformat()
        f = compute_features_from_events({
            "filings": [],
            "news": [],
            "earnings": [
                {"date": past, "type": "AMC",
                 "estimate_eps": None, "actual_eps": 1.0, "status": "reported"},
            ],
        })
        assert f["earnings_within_14d"] is False


class TestFreshnessAndScores:
    def test_freshness_score_within_24h_is_one(self) -> None:
        f = compute_features_from_events({
            "filings": [
                {"form": "8-K", "filed_at": _now_iso(0.1), "title": "x", "url": "u"},
            ],
            "news": [], "earnings": [],
        })
        assert f["catalyst_freshness_score"] == 1.0

    def test_freshness_score_zero_beyond_14d(self) -> None:
        f = compute_features_from_events({
            "filings": [
                {"form": "8-K", "filed_at": _now_iso(20), "title": "x", "url": "u"},
            ],
            "news": [], "earnings": [],
        })
        assert f["catalyst_freshness_score"] == 0.0

    def test_scores_bounded_zero_one(self) -> None:
        # Stress with many negative items
        f = compute_features_from_events({
            "filings": [
                {"form": "8-K", "filed_at": _now_iso(1), "title": "x", "url": f"u{i}"}
                for i in range(6)
            ],
            "news": [
                {"title": str(i), "published_at": _now_iso(0.1), "sentiment": "negative",
                 "url": f"n{i}", "source": "s"}
                for i in range(8)
            ],
            "earnings": [],
        })
        assert 0.0 <= f["event_risk_score"] <= 1.0
        assert 0.0 <= f["event_momentum_score"] <= 1.0


class TestTagPlainEnglish:
    def test_no_recent_returns_no_fresh_catalyst(self) -> None:
        old = _now_iso(60)
        f = compute_features_from_events({
            "filings": [{"form": "8-K", "filed_at": old, "title": "x", "url": "u"}],
            "news":    [{"title": "x", "published_at": old, "sentiment": None, "url": "u", "source": "s"}],
            "earnings": [],
        })
        assert "No fresh catalyst" in f["tags"]
