"""Recommendation diagnostics — pure functions over existing rec/evidence rows.

Answers "why aren't we seeing Buys?" without changing the engine. Computes:

* distance_to_buy for each rec (uses policy-adjusted composite when present)
* top positive / negative evidence contributors (signed score × weight)
* damper flags from policy.adjustments
* stale / insufficient-data flags
* batch-level summary (distributions, near-buy counts)

Deterministic. Decimal-only. No engine re-evaluation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

DEFAULT_BUY_THRESHOLD = Decimal("0.25")
NEAR_BUY_PCT_TIGHT = Decimal("0.05")   # within 5% (absolute composite distance)
NEAR_BUY_PCT_LOOSE = Decimal("0.10")

# Score distribution buckets covering the composite_score space [-1, +1].
_BUCKETS: tuple[tuple[str, Decimal, Decimal], ...] = (
    ("<= -0.65",   Decimal("-1.01"), Decimal("-0.65")),
    ("-0.65..-0.25", Decimal("-0.65"), Decimal("-0.25")),
    ("-0.25..0",     Decimal("-0.25"), Decimal("0")),
    ("0..0.25",      Decimal("0"),    Decimal("0.25")),
    ("0.25..0.65",   Decimal("0.25"), Decimal("0.65")),
    (">= 0.65",      Decimal("0.65"), Decimal("1.01")),
)


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class Contributor:
    factor_key: str
    family: str | None
    score: Decimal
    weight: Decimal | None
    direction: str | None
    narrative: str


@dataclass
class DamperFlag:
    rule: str
    factor: str | None
    score_before: Decimal | None
    score_after: Decimal | None
    reason: str | None


@dataclass
class Diagnostic:
    recommendation_id: str
    asset_id: str
    symbol: str | None
    action: str
    composite_score: Decimal | None          # policy-adjusted if applied, else original
    original_composite_score: Decimal | None
    confidence: Decimal | None
    confidence_label: str | None
    distance_to_buy: Decimal | None          # None when composite missing / stale
    top_positive: list[Contributor] = field(default_factory=list)
    top_negative: list[Contributor] = field(default_factory=list)
    dampers: list[DamperFlag] = field(default_factory=list)
    stale_data: bool = False
    enough_data: bool = True
    family_scores: dict[str, Decimal] = field(default_factory=dict)
    generated_at_iso: str | None = None


@dataclass
class BucketCount:
    label: str
    count: int


@dataclass
class BatchSummary:
    total: int
    action_distribution: dict[str, int]
    score_distribution: list[BucketCount]
    confidence_distribution: list[BucketCount]
    near_buy_tight: int                      # distance ≤ 5%
    near_buy_loose: int                      # distance ≤ 10%
    buys: int
    dampers_applied: int
    stale_count: int
    insufficient_data_count: int
    buy_threshold: Decimal
    max_composite: Decimal | None
    min_composite: Decimal | None
    median_composite: Decimal | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dec(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except Exception:  # noqa: BLE001
        return None


def _parse_json(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    try:
        out = json.loads(text)
        return out if isinstance(out, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _resolve_composite(rationale: dict[str, Any]) -> tuple[Decimal | None, Decimal | None]:
    """Return (policy-adjusted or original composite, original composite).

    Prefers the post-policy composite when available (that's the score the
    action was mapped from after dampers). Falls back to the raw composite.
    """
    original = _dec(rationale.get("composite_score"))
    policy = rationale.get("policy") or {}
    adjusted = _dec(policy.get("adjusted_composite_score")) if policy else None
    effective = adjusted if adjusted is not None else original
    return effective, original


def _parse_evidence(ev: Any) -> Contributor | None:
    """Accepts either an ORM RecommendationEvidence or a plain dict.

    Dict shape (what the existing API payload uses):
        factor_key | evidence_type
        family | source
        weight
        summary|value|threshold|direction|score|narrative  (nested or flat)
    """
    if isinstance(ev, dict):
        factor = ev.get("factor_key") or ev.get("evidence_type") or ""
        family = ev.get("family") or ev.get("source")
        weight = _dec(ev.get("weight"))
        inner = ev.get("summary")
        if isinstance(inner, str):
            inner_parsed = _parse_json(inner)
        elif isinstance(inner, dict):
            inner_parsed = inner
        else:
            inner_parsed = {}
        score = _dec(ev.get("score")) or _dec(inner_parsed.get("score"))
        direction = ev.get("direction") or inner_parsed.get("direction")
        narrative = ev.get("narrative") or inner_parsed.get("narrative") or ""
    else:
        # ORM path
        factor = getattr(ev, "evidence_type", "") or ""
        family = getattr(ev, "source", None)
        weight = _dec(getattr(ev, "weight", None))
        summary = _parse_json(getattr(ev, "summary", None))
        score = _dec(summary.get("score"))
        direction = summary.get("direction")
        narrative = summary.get("narrative") or ""

    if score is None:
        return None
    return Contributor(
        factor_key=factor,
        family=family,
        score=score,
        weight=weight,
        direction=direction,
        narrative=narrative,
    )


def _extract_dampers(rationale: dict[str, Any]) -> list[DamperFlag]:
    policy = rationale.get("policy") or {}
    adj = policy.get("adjustments") or []
    out: list[DamperFlag] = []
    for a in adj:
        if not isinstance(a, dict):
            continue
        out.append(DamperFlag(
            rule=str(a.get("rule", "unknown")),
            factor=str(a.get("factor")) if a.get("factor") is not None else None,
            score_before=_dec(a.get("score_before")),
            score_after=_dec(a.get("score_after")),
            reason=str(a.get("reason")) if a.get("reason") is not None else None,
        ))
    return out


# ---------------------------------------------------------------------------
# Per-recommendation analysis
# ---------------------------------------------------------------------------


def analyze_recommendation(
    *,
    recommendation_id: str,
    asset_id: str,
    symbol: str | None,
    action: str,
    rationale_json: str | dict[str, Any] | None,
    conviction: Decimal | None,
    generated_at_iso: str | None,
    evidences: list[Any],
    buy_threshold: Decimal = DEFAULT_BUY_THRESHOLD,
    top_n: int = 3,
) -> Diagnostic:
    rationale = (
        rationale_json if isinstance(rationale_json, dict)
        else _parse_json(rationale_json)
    )
    composite, original = _resolve_composite(rationale)

    stale = bool(rationale.get("stale_data", False))
    enough = bool(rationale.get("enough_data", True))

    if composite is None or stale or not enough:
        distance: Decimal | None = None
    else:
        distance = buy_threshold - composite
        if distance < 0:
            distance = Decimal("0")

    contributors: list[Contributor] = []
    for ev in evidences:
        c = _parse_evidence(ev)
        if c is not None:
            contributors.append(c)

    positive = sorted(
        [c for c in contributors if c.score > 0],
        key=lambda c: c.score, reverse=True,
    )[:top_n]
    negative = sorted(
        [c for c in contributors if c.score < 0],
        key=lambda c: c.score,
    )[:top_n]

    family_scores_raw = rationale.get("family_scores", {}) or {}
    family_scores: dict[str, Decimal] = {}
    if isinstance(family_scores_raw, dict):
        for k, v in family_scores_raw.items():
            d = _dec(v)
            if d is not None:
                family_scores[str(k)] = d

    return Diagnostic(
        recommendation_id=recommendation_id,
        asset_id=asset_id,
        symbol=symbol,
        action=action,
        composite_score=composite,
        original_composite_score=original,
        confidence=_dec(conviction),
        confidence_label=rationale.get("confidence_label"),
        distance_to_buy=distance,
        top_positive=positive,
        top_negative=negative,
        dampers=_extract_dampers(rationale),
        stale_data=stale,
        enough_data=enough,
        family_scores=family_scores,
        generated_at_iso=generated_at_iso,
    )


# ---------------------------------------------------------------------------
# Ordering + batch summary
# ---------------------------------------------------------------------------


def order_by_closest_to_buy(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    """Sort rule:
    1. Known-distance rows first, ascending by distance_to_buy (Buys → 0)
    2. Unknown-distance rows last, alphabetical by symbol for determinism
    """
    known = [d for d in diagnostics if d.distance_to_buy is not None]
    unknown = [d for d in diagnostics if d.distance_to_buy is None]
    known.sort(key=lambda d: (d.distance_to_buy, d.symbol or ""))
    unknown.sort(key=lambda d: d.symbol or "")
    return known + unknown


def _histogram_score(diagnostics: list[Diagnostic]) -> list[BucketCount]:
    out: list[BucketCount] = []
    scores = [d.composite_score for d in diagnostics if d.composite_score is not None]
    for label, lo, hi in _BUCKETS:
        n = sum(1 for s in scores if lo <= s < hi)
        out.append(BucketCount(label=label, count=n))
    return out


def _histogram_confidence(diagnostics: list[Diagnostic]) -> list[BucketCount]:
    # Confidence is 0..100.
    boundaries = [
        ("0-20", Decimal("0"), Decimal("20")),
        ("20-40", Decimal("20"), Decimal("40")),
        ("40-60", Decimal("40"), Decimal("60")),
        ("60-80", Decimal("60"), Decimal("80")),
        ("80-100", Decimal("80"), Decimal("100.01")),
    ]
    vals = [d.confidence for d in diagnostics if d.confidence is not None]
    out: list[BucketCount] = []
    for label, lo, hi in boundaries:
        n = sum(1 for v in vals if lo <= v < hi)
        out.append(BucketCount(label=label, count=n))
    return out


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / Decimal("2")


def summarize_batch(
    diagnostics: list[Diagnostic],
    buy_threshold: Decimal = DEFAULT_BUY_THRESHOLD,
) -> BatchSummary:
    action_dist: dict[str, int] = {}
    for d in diagnostics:
        action_dist[d.action] = action_dist.get(d.action, 0) + 1

    distances = [d.distance_to_buy for d in diagnostics if d.distance_to_buy is not None]
    near_tight = sum(1 for dd in distances if dd <= NEAR_BUY_PCT_TIGHT)
    near_loose = sum(1 for dd in distances if dd <= NEAR_BUY_PCT_LOOSE)
    buys = sum(1 for d in diagnostics if d.action == "Buy")

    dampers_applied = sum(1 for d in diagnostics if d.dampers)
    stale_count = sum(1 for d in diagnostics if d.stale_data)
    insufficient = sum(1 for d in diagnostics if not d.enough_data)

    scores = [d.composite_score for d in diagnostics if d.composite_score is not None]

    return BatchSummary(
        total=len(diagnostics),
        action_distribution=action_dist,
        score_distribution=_histogram_score(diagnostics),
        confidence_distribution=_histogram_confidence(diagnostics),
        near_buy_tight=near_tight,
        near_buy_loose=near_loose,
        buys=buys,
        dampers_applied=dampers_applied,
        stale_count=stale_count,
        insufficient_data_count=insufficient,
        buy_threshold=buy_threshold,
        max_composite=max(scores) if scores else None,
        min_composite=min(scores) if scores else None,
        median_composite=_median(scores),
    )
