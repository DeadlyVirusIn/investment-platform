"""Deterministic keyword/rule classifier for news headlines.

Pure functions. No ML. Produces:
    category ∈ {earnings | analyst | regulatory | deal | product | macro | general}
    sentiment ∈ {positive | neutral | negative}
    sentiment_score ∈ {+1, 0, -1}
    impact_level ∈ {low | medium | high}
    impact_score ∈ {1, 2, 3}

Rules are lowercase substring matches against title + summary. First
match by priority wins for category; sentiment is computed from a +/-
keyword vote on the combined text.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Category rules (priority order — first match wins)
# ---------------------------------------------------------------------------

_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("earnings", (
        "beats earnings", "misses earnings", "earnings beat", "earnings miss",
        "quarterly results", "eps beat", "eps miss", "revenue beat", "revenue miss",
        "quarter results", "guidance", "outlook", "profit warning",
        "earnings report", "quarterly earnings",
    )),
    ("regulatory", (
        "sec ", "s.e.c.", "investigation", "lawsuit", "antitrust", "fine ",
        "subpoena", "doj ", "ftc ", "probe", "fraud", "settlement", "regulator",
        "compliance", "class action",
    )),
    ("deal", (
        "acquires", "acquisition", "merger", "takeover", "buyout", "divests",
        "spinoff", "spin-off", "to acquire", "buys ", "stake in",
    )),
    ("analyst", (
        "upgrade", "downgrade", "price target", "analyst", "rating raised",
        "rating cut", "initiates coverage", "buy rating", "sell rating",
        "overweight", "underweight",
    )),
    ("product", (
        "launches", "unveils", "debuts", "releases", "announces ", "new product",
        "recall", "pipeline", "trial results",
    )),
    ("macro", (
        "fed ", "federal reserve", "fomc", "rate hike", "rate cut",
        "interest rate", "inflation", "cpi", "ppi", "gdp", "unemployment",
        "payrolls", "recession", "treasury yield", "yield curve",
        "jobs report", "nonfarm",
    )),
)

_POSITIVE_KEYWORDS: frozenset[str] = frozenset({
    "beats", "beat ", "surges", "soars", "rallies", "jumps", "record",
    "exceeds", "wins", "upgrade", "upgrades", "raises guidance",
    "raises outlook", "raises target", "acquires", "approves", "approval",
    "expand", "expanded", "launches", "strong demand", "all-time high",
    "breakthrough", "outperform", "outperforms",
})

_NEGATIVE_KEYWORDS: frozenset[str] = frozenset({
    "misses", "miss ", "falls", "plunges", "slumps", "drops", "tumbles",
    "downgrade", "downgrades", "cuts guidance", "cuts outlook", "cut target",
    "warning", "warns", "lawsuit", "investigation", "probe", "fraud",
    "antitrust", "recall", "resign", "resigns", "layoffs", "bankruptcy",
    "breach", "underperform", "underperforms", "slashed", "slashes",
    "loss widens",
})

_HIGH_IMPACT_CATEGORIES: frozenset[str] = frozenset({"earnings", "regulatory", "macro"})
_MEDIUM_IMPACT_CATEGORIES: frozenset[str] = frozenset({"analyst", "deal"})


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Classification:
    category: str
    sentiment: str
    sentiment_score: int     # +1 / 0 / -1
    impact_level: str        # low / medium / high
    impact_score: int        # 1 / 2 / 3


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


def _normalize(text: str | None) -> str:
    return (text or "").lower().strip()


def classify_category(title: str, summary: str | None = None) -> str:
    blob = f"{_normalize(title)} {_normalize(summary)}"
    for category, keywords in _CATEGORY_RULES:
        for kw in keywords:
            if kw in blob:
                return category
    return "general"


def classify_sentiment(
    title: str, summary: str | None = None,
) -> tuple[str, int]:
    """Return (label, numeric_score) in {('positive', 1), ('neutral', 0),
    ('negative', -1)}. Ties + no keywords = neutral."""
    blob = f"{_normalize(title)} {_normalize(summary)}"
    pos = sum(1 for kw in _POSITIVE_KEYWORDS if kw in blob)
    neg = sum(1 for kw in _NEGATIVE_KEYWORDS if kw in blob)
    if pos > neg:
        return "positive", 1
    if neg > pos:
        return "negative", -1
    return "neutral", 0


def classify_impact(
    category: str, title: str, summary: str | None = None,
) -> tuple[str, int]:
    """Category drives the base level; presence of strong keywords promotes."""
    blob = f"{_normalize(title)} {_normalize(summary)}"
    if category in _HIGH_IMPACT_CATEGORIES:
        return "high", 3
    # Deal with explicit "acquires/merger" counts as high
    if "acquires" in blob or "acquisition" in blob or "merger" in blob:
        return "high", 3
    if category in _MEDIUM_IMPACT_CATEGORIES:
        return "medium", 2
    return "low", 1


def classify(title: str, summary: str | None = None) -> Classification:
    category = classify_category(title, summary)
    sentiment, sscore = classify_sentiment(title, summary)
    impact_level, iscore = classify_impact(category, title, summary)
    return Classification(
        category=category,
        sentiment=sentiment,
        sentiment_score=sscore,
        impact_level=impact_level,
        impact_score=iscore,
    )
