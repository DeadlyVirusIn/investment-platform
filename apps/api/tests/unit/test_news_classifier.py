"""Unit tests: deterministic news classifier."""

from __future__ import annotations

from apps.api.src.domain.news.classifier import (
    Classification,
    classify,
    classify_category,
    classify_impact,
    classify_sentiment,
)


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------


def test_category_earnings_from_beat() -> None:
    assert classify_category("NVDA beats earnings, revenue beat") == "earnings"


def test_category_earnings_from_guidance() -> None:
    assert classify_category("Company cuts guidance for Q3") == "earnings"


def test_category_regulatory() -> None:
    assert classify_category("SEC investigation into bank practices") == "regulatory"


def test_category_deal() -> None:
    assert classify_category("TechCo acquires startup for $1B") == "deal"


def test_category_analyst() -> None:
    assert classify_category("Morgan Stanley raises price target") == "analyst"


def test_category_product() -> None:
    assert classify_category("Apple unveils new iPhone line") == "product"


def test_category_macro() -> None:
    assert classify_category("Fed holds interest rate steady") == "macro"


def test_category_general_fallback() -> None:
    assert classify_category("Some unrelated corporate blurb") == "general"


# ---------------------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------------------


def test_sentiment_positive() -> None:
    label, score = classify_sentiment("Stock surges after earnings beat")
    assert label == "positive"
    assert score == 1


def test_sentiment_negative() -> None:
    label, score = classify_sentiment("Firm warns on profit, shares plunge")
    assert label == "negative"
    assert score == -1


def test_sentiment_neutral() -> None:
    label, score = classify_sentiment("Company holds annual meeting")
    assert label == "neutral"
    assert score == 0


def test_sentiment_ties_go_neutral() -> None:
    label, _ = classify_sentiment("Beats estimates but warns on outlook")
    assert label == "neutral"


# ---------------------------------------------------------------------------
# Impact
# ---------------------------------------------------------------------------


def test_impact_high_on_regulatory() -> None:
    assert classify_impact("regulatory", "SEC probe") == ("high", 3)


def test_impact_high_on_macro() -> None:
    assert classify_impact("macro", "Fed raises rates") == ("high", 3)


def test_impact_high_on_deal_via_keyword() -> None:
    assert classify_impact("general", "X acquires Y") == ("high", 3)


def test_impact_medium_on_analyst() -> None:
    assert classify_impact("analyst", "Upgraded by GS") == ("medium", 2)


def test_impact_low_on_general() -> None:
    assert classify_impact("general", "quiet trading day") == ("low", 1)


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------


def test_classify_returns_complete_record() -> None:
    c = classify("NVDA beats earnings, revenue exceeds estimates")
    assert isinstance(c, Classification)
    assert c.category == "earnings"
    assert c.sentiment == "positive"
    assert c.sentiment_score == 1
    assert c.impact_level == "high"
    assert c.impact_score == 3
