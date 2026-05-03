"""Decision policy layer — adjusts recommendations using learned insights.

Additive, deterministic, feature-flagged. Does not mutate core engine output:
the original composite_score / confidence / action are preserved; the policy
emits adjusted copies alongside plus a list of adjustment records.

Three simple rules:
    1. High-volatility damping — dampen composite when current vol regime is high.
    2. Regime suppression — dampen composite when current regime is on the
       "historically worst" list (derived from regime_sensitivity insight).
    3. Confidence-inversion cap — cap confidence at a fixed ceiling when the
       engine's own confidence signal has been shown to be mis-calibrated.

Rules are composable; each applies in sequence on top of the prior output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid circular import at runtime
    from apps.api.src.domain.recommendations.recommendation_engine import (
        RecommendationResult,
    )


# ---------------------------------------------------------------------------
# Context + Decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyContext:
    enabled: bool = True
    high_vol_damping_enabled: bool = True
    suppress_regimes: frozenset[tuple[str, str]] = frozenset()
    confidence_inversion: bool = False

    # Factors — constants are conservative defaults for Phase 2D.
    high_vol_factor: Decimal = Decimal("0.7")
    suppressed_regime_factor: Decimal = Decimal("0.5")
    confidence_inversion_cap: Decimal = Decimal("50")
    worst_regime_hit_rate_threshold: Decimal = Decimal("0.3")


@dataclass
class PolicyDecision:
    original_action: str
    original_composite_score: Decimal
    original_confidence: Decimal
    adjusted_action: str
    adjusted_composite_score: Decimal
    adjusted_confidence: Decimal
    adjustments: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _d(v: object) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _map_action(score: Decimal, thresholds: dict[str, Decimal]) -> str:
    if score >= thresholds.get("BUY", Decimal("0.25")):
        return "Buy"
    if score >= thresholds.get("HOLD", Decimal("-0.25")):
        return "Hold"
    if score >= thresholds.get("REDUCE", Decimal("-0.65")):
        return "Trim"
    return "Sell"


def _passthrough(result: "RecommendationResult") -> PolicyDecision:
    return PolicyDecision(
        original_action=result.action,
        original_composite_score=_d(result.composite_score),
        original_confidence=_d(result.confidence),
        adjusted_action=result.action,
        adjusted_composite_score=_d(result.composite_score),
        adjusted_confidence=_d(result.confidence),
        adjustments=[],
    )


# ---------------------------------------------------------------------------
# apply_policy
# ---------------------------------------------------------------------------


def apply_policy(
    result: "RecommendationResult",
    context: PolicyContext,
    action_thresholds: dict[str, Decimal],
) -> PolicyDecision:
    """Apply the policy to a RecommendationResult. Pure function."""
    if not context.enabled:
        return _passthrough(result)

    adjusted_score = _d(result.composite_score)
    adjusted_confidence = _d(result.confidence)
    adjustments: list[dict[str, Any]] = []

    # Rule 1 — High volatility damping
    if context.high_vol_damping_enabled and result.volatility_regime == "high":
        before = adjusted_score
        adjusted_score = adjusted_score * context.high_vol_factor
        adjustments.append({
            "rule": "high_volatility_damping",
            "factor": str(context.high_vol_factor),
            "score_before": str(before),
            "score_after": str(adjusted_score),
            "reason": "High volatility regime — damping composite score.",
        })

    # Rule 2 — Regime suppression (per-dimension)
    for dimension, regime_value in (
        ("trend", result.trend_regime),
        ("volatility", result.volatility_regime),
        ("drawdown", result.drawdown_regime),
    ):
        if regime_value is None:
            continue
        if (dimension, regime_value) in context.suppress_regimes:
            before = adjusted_score
            adjusted_score = adjusted_score * context.suppressed_regime_factor
            adjustments.append({
                "rule": "regime_suppression",
                "dimension": dimension,
                "regime": regime_value,
                "factor": str(context.suppressed_regime_factor),
                "score_before": str(before),
                "score_after": str(adjusted_score),
                "reason": (
                    f"{dimension}={regime_value} has historically worst hit_rate "
                    f"below {context.worst_regime_hit_rate_threshold}; damping."
                ),
            })

    # Rule 3 — Confidence inversion cap
    if (
        context.confidence_inversion
        and adjusted_confidence > context.confidence_inversion_cap
    ):
        before = adjusted_confidence
        adjusted_confidence = context.confidence_inversion_cap
        adjustments.append({
            "rule": "confidence_inversion_cap",
            "factor": str(context.confidence_inversion_cap),
            "confidence_before": str(before),
            "confidence_after": str(adjusted_confidence),
            "reason": (
                "Confidence inversion detected in recent outcomes — capping "
                "reported confidence."
            ),
        })

    # Re-map action from adjusted score. Preserve Watch (insufficient data).
    if result.action == "Watch":
        adjusted_action = "Watch"
    else:
        adjusted_action = _map_action(adjusted_score, action_thresholds)

    return PolicyDecision(
        original_action=result.action,
        original_composite_score=_d(result.composite_score),
        original_confidence=_d(result.confidence),
        adjusted_action=adjusted_action,
        adjusted_composite_score=adjusted_score,
        adjusted_confidence=adjusted_confidence,
        adjustments=adjustments,
    )


# ---------------------------------------------------------------------------
# Context loader
# ---------------------------------------------------------------------------


def build_policy_context_from_db(
    session,
    enabled: bool = True,
) -> PolicyContext:
    """Load recent labeled outcomes, compute insights, produce a PolicyContext.

    Returns a passthrough (disabled) context when ``enabled=False``.
    Always returns a valid context — insufficient data yields an empty
    suppress set and `confidence_inversion=False`.
    """
    if not enabled:
        return PolicyContext(enabled=False)

    from sqlalchemy import select

    from apps.api.src.db.models import (
        Asset,
        Recommendation,
        RecommendationOutcome,
    )
    from apps.api.src.domain.performance.report import (
        OutcomeRecord,
        compute_confidence_buckets,
        compute_insights,
        compute_per_drawdown_regime,
        compute_per_trend_regime,
        compute_per_volatility_regime,
    )

    stmt = (
        select(RecommendationOutcome, Recommendation, Asset.symbol)
        .join(Recommendation, RecommendationOutcome.recommendation_id == Recommendation.id)
        .join(Asset, Recommendation.asset_id == Asset.id)
        .where(RecommendationOutcome.barrier_label.isnot(None))
    )
    records: list[OutcomeRecord] = []
    for outcome, rec, symbol in session.execute(stmt).all():
        conf = rec.conviction
        if conf is not None and not isinstance(conf, Decimal):
            conf = Decimal(str(conf))
        raw = outcome.realized_30d_return
        if raw is not None and not isinstance(raw, Decimal):
            raw = Decimal(str(raw))
        records.append(OutcomeRecord(
            generated_at_iso=rec.generated_at.isoformat() if rec.generated_at else "",
            symbol=symbol,
            asset_id=rec.asset_id,
            confidence=conf,
            return_value=raw,
            label=outcome.barrier_label,
            trend_regime=outcome.trend_regime,
            volatility_regime=outcome.volatility_regime,
            drawdown_regime=outcome.drawdown_regime,
        ))

    conf_buckets = compute_confidence_buckets(records)
    regime_brks = {
        "trend": compute_per_trend_regime(records),
        "volatility": compute_per_volatility_regime(records),
        "drawdown": compute_per_drawdown_regime(records),
    }
    insights = compute_insights(conf_buckets, regime_brks)

    default_threshold = PolicyContext().worst_regime_hit_rate_threshold
    suppress: set[tuple[str, str]] = set()
    for sens in insights["regime_sensitivity"]:
        worst_hr = sens.get("worst_hit_rate")
        if worst_hr is None:
            continue
        worst_hr_d = worst_hr if isinstance(worst_hr, Decimal) else Decimal(str(worst_hr))
        if worst_hr_d < default_threshold:
            suppress.add((sens["dimension"], sens["worst_regime"]))

    return PolicyContext(
        enabled=True,
        suppress_regimes=frozenset(suppress),
        confidence_inversion=len(insights["confidence_inversion"]) > 0,
    )
