"""Deterministic rule-based recommendation engine v1.

Reads engine.yaml, computes features per asset, aggregates score across
computable signal families, maps score → action, persists Recommendation +
RecommendationEvidence rows with reproducible snapshot_hash.

No ML. No LLM. No randomness. No external APIs (other than DB).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    Lot,
    PriceBar,
    Recommendation,
    RecommendationEvidence,
    RecommendationOutcome,
    Transaction,
)
from apps.api.src.domain.features.feature_engine import (
    FamilyOut,
    Series,
    compute_exposure,
    compute_trend_momentum,
    compute_volatility_risk,
    load_series,
)
from apps.api.src.domain.features.regime_classifier import classify_all

STALE_DAYS = 5   # > this → stale; 5 days tolerates weekends + a market holiday

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[5]
    / "packages"
    / "engine-config"
    / "engine.yaml"
)


# ---------------------------------------------------------------------------
# Engine config
# ---------------------------------------------------------------------------


@dataclass
class EngineConfig:
    version: str
    family_weights: dict[str, Decimal]
    action_thresholds: dict[str, Decimal]
    enough_data: dict[str, dict[str, Any]]
    trend_momentum: dict[str, Any]
    volatility_risk: dict[str, Any]
    exposure: dict[str, Any]
    raw_text: str

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(self.raw_text.encode()).hexdigest()[:16]


def load_engine_config(path: Path | str | None = None) -> EngineConfig:
    resolved = Path(path) if path else DEFAULT_CONFIG_PATH
    text = resolved.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return EngineConfig(
        version=str(data["version"]),
        family_weights={k: Decimal(str(v)) for k, v in data["family_weights"].items()},
        action_thresholds={k: Decimal(str(v)) for k, v in data["action_thresholds"].items()},
        enough_data=data.get("enough_data", {}),
        trend_momentum=data.get("trend_momentum", {}),
        volatility_risk=data.get("volatility_risk", {}),
        exposure=data.get("exposure", {}),
        raw_text=text,
    )


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class RecommendationResult:
    asset_id: str
    action: str  # Buy | Hold | Trim | Sell | Watch
    confidence: Decimal  # 0..100
    confidence_label: str  # Low | Medium | High
    enough_data: bool
    engine_version: str
    snapshot_hash: str
    thesis: str
    composite_score: Decimal
    family_scores: dict[str, Decimal]
    signals: list[dict[str, Any]]
    tags: list[str]
    stale_data: bool = False
    current_price: Decimal | None = None
    trend_regime: str | None = None
    volatility_regime: str | None = None
    drawdown_regime: str | None = None
    recommendation_id: str | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _map_score_to_action(score: Decimal, thresholds: dict[str, Decimal]) -> str:
    """5-value action vocabulary: Buy/Hold/Trim/Sell (Watch handled upstream)."""
    if score >= thresholds.get("BUY", Decimal("0.25")):
        return "Buy"
    if score >= thresholds.get("HOLD", Decimal("-0.25")):
        return "Hold"
    if score >= thresholds.get("REDUCE", Decimal("-0.65")):
        return "Trim"
    return "Sell"


def _check_enough_data(series: Series | None, asset: Asset, config: EngineConfig) -> bool:
    if series is None:
        return False
    req = config.enough_data.get(asset.asset_class, {}) or {}
    min_bars = int(req.get("price_bars_min", 60))
    return len(series) >= min_bars


def _is_stale(series: Series | None, *, as_of: dt.date | None = None) -> bool:
    """True if the most recent bar in ``series`` is older than STALE_DAYS.

    BACKTEST-PAPER-2: ``as_of`` makes staleness replay-correct. Default (None)
    is the exact legacy behaviour — age measured against wall-clock now(). When
    ``as_of`` is set, the reference is midnight(as_of + 1 day) UTC (end of the
    decision day) so a historical run does not flag a series as stale merely
    because real-world time has elapsed since the decision date.
    """
    if series is None or not series.ts:
        return True
    latest = series.ts[-1]
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=dt.timezone.utc)
    ref = (
        dt.datetime.now(dt.timezone.utc) if as_of is None
        else dt.datetime(as_of.year, as_of.month, as_of.day,
                         tzinfo=dt.timezone.utc) + dt.timedelta(days=1)
    )
    return (ref - latest) > dt.timedelta(days=STALE_DAYS)


def _compute_confidence(
    composite: Decimal,
    signals: list[dict[str, Any]],
    all_families_computable: bool,
    stale: bool,
) -> tuple[Decimal, str]:
    """Signal-agreement-based confidence (0..100) + label.

    Counts how many non-zero signals align with the composite direction.
    Applies penalties for missing families and stale data.
    """
    if composite == 0:
        return Decimal("0"), "Low"

    composite_positive = composite > 0
    aligned = 0
    total = 0
    for sig in signals:
        try:
            score = Decimal(sig["score"]) if sig.get("score") is not None else Decimal("0")
            weight = Decimal(sig["weight"]) if sig.get("weight") is not None else Decimal("0")
        except (ValueError, TypeError, InvalidOperation):
            continue
        if score == 0 or weight == 0:
            continue
        total += 1
        if (score > 0) == composite_positive:
            aligned += 1

    agreement = (
        Decimal(aligned) / Decimal(total) if total > 0 else Decimal("0")
    )

    penalty = Decimal("0")
    if not all_families_computable:
        penalty += Decimal("0.20")
    if stale:
        penalty += Decimal("0.30")

    adjusted = max(Decimal("0"), agreement - penalty)
    score_100 = (adjusted * Decimal("100")).quantize(Decimal("0.01"))

    if score_100 >= Decimal("60"):
        label = "High"
    elif score_100 >= Decimal("30"):
        label = "Medium"
    else:
        label = "Low"
    return score_100, label


def _snapshot_hash(inputs: dict[str, Any]) -> str:
    payload = json.dumps(inputs, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _family_to_signals(family: FamilyOut) -> list[dict[str, Any]]:
    return [
        {
            "factor_key": s.factor_key,
            "family": s.family,
            "score": str(s.score),
            "weight": str(s.weight),
            "value": str(s.raw_value) if s.raw_value is not None else None,
            "threshold": str(s.threshold) if s.threshold is not None else None,
            "direction": s.direction,
            "narrative": s.narrative,
        }
        for s in family.signals
    ]


# ---------------------------------------------------------------------------
# Per-asset compute
# ---------------------------------------------------------------------------


def compute_for_asset(
    session: Session,
    *,
    account_id: str,
    asset_id: str,
    config: EngineConfig,
    as_of: dt.date | None = None,
) -> RecommendationResult:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise ValueError(f"unknown asset_id: {asset_id}")

    # BACKTEST-PAPER-2: as_of (default None) bounds the price series and the
    # staleness reference to the decision date. None = exact live behaviour.
    series = load_series(session, asset_id, as_of=as_of)
    enough_by_bars = _check_enough_data(series, asset, config)
    stale = _is_stale(series, as_of=as_of)

    # Stale data forces Watch; we still compute families for evidence transparency.
    if series is not None:
        fam_trend = compute_trend_momentum(series, config.trend_momentum)
        fam_vol = compute_volatility_risk(series, config.volatility_risk)
        current_price = series.close[-1]
        regime = classify_all(series.close)
    else:
        fam_trend = FamilyOut("trend_momentum", Decimal("0"), [], computable=False)
        fam_vol = FamilyOut("volatility_risk", Decimal("0"), [], computable=False)
        current_price = None
        regime = {
            "trend_regime": None,
            "volatility_regime": None,
            "drawdown_regime": None,
        }

    fam_exp = compute_exposure(session, account_id, asset_id, config.exposure)

    computable = [f for f in (fam_trend, fam_vol, fam_exp) if f.computable]
    all_families_computable = len(computable) == 3
    total_w = Decimal("0")
    composite = Decimal("0")
    family_scores: dict[str, Decimal] = {}
    for fam in computable:
        w = config.family_weights.get(fam.family, Decimal("0"))
        total_w += w
        composite += fam.score * w
        family_scores[fam.family] = fam.score

    if total_w > 0:
        composite = composite / total_w
    else:
        composite = Decimal("0")

    tags: list[str] = [asset.asset_class]
    for fam in (fam_trend, fam_vol, fam_exp):
        if not fam.computable:
            tags.append(f"missing-{fam.family}")
    if stale:
        tags.append("stale-data")

    enough = enough_by_bars and total_w > 0 and not stale

    if not enough:
        action = "Watch"
    else:
        action = _map_score_to_action(composite, config.action_thresholds)

    all_signals: list[dict[str, Any]] = []
    for fam in (fam_trend, fam_vol, fam_exp):
        all_signals.extend(_family_to_signals(fam))

    # Signal-agreement confidence (0..100)
    confidence, confidence_label = _compute_confidence(
        composite,
        all_signals,
        all_families_computable=all_families_computable,
        stale=stale,
    )
    if not enough:
        confidence = Decimal("0")
        confidence_label = "Low"

    snapshot_inputs = {
        "engine_version": config.version,
        "config_hash": config.config_hash,
        "asset_id": asset_id,
        "account_id": account_id,
        "last_price_ts": series.ts[-1].isoformat() if series else None,
        "family_scores": {k: str(v) for k, v in family_scores.items()},
        "composite": str(composite),
    }
    snap = _snapshot_hash(snapshot_inputs)

    # Template thesis — deterministic, no LLM. ASCII-only for portability.
    parts: list[str] = [
        f"{asset.symbol}: composite score {composite:.3f} -> {action}."
    ]
    if fam_trend.computable:
        parts.append(f"Trend/momentum score {fam_trend.score:.3f}.")
    if fam_vol.computable:
        parts.append(f"Volatility/risk score {fam_vol.score:.3f}.")
    if fam_exp.computable:
        parts.append(f"Exposure score {fam_exp.score:.3f}.")
    parts.append(f"Confidence: {confidence} ({confidence_label}).")
    if stale:
        parts.append("Data is stale (>2 days). Action forced to Watch.")
    elif not enough:
        req = config.enough_data.get(asset.asset_class, {}) or {}
        parts.append(
            f"Insufficient data: require {req.get('price_bars_min', 'N')}+ bars "
            f"(have {len(series) if series else 0}). Action forced to Watch."
        )
    thesis = " ".join(parts)

    return RecommendationResult(
        asset_id=asset_id,
        action=action,
        confidence=confidence,
        confidence_label=confidence_label,
        enough_data=enough,
        engine_version=config.version,
        snapshot_hash=snap,
        thesis=thesis,
        composite_score=composite,
        family_scores=family_scores,
        signals=all_signals,
        tags=tags,
        stale_data=stale,
        current_price=current_price,
        trend_regime=regime["trend_regime"],
        volatility_regime=regime["volatility_regime"],
        drawdown_regime=regime["drawdown_regime"],
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _find_existing_by_snapshot(
    session: Session,
    asset_id: str,
    engine_version: str,
    snapshot_hash: str,
) -> Recommendation | None:
    """Direct lookup on the dedicated snapshot_hash column."""
    stmt = select(Recommendation).where(
        Recommendation.asset_id == asset_id,
        Recommendation.model_version == engine_version,
        Recommendation.snapshot_hash == snapshot_hash,
    )
    return session.execute(stmt).scalars().first()


def persist(
    session: Session,
    result: RecommendationResult,
    decision: "PolicyDecision | None" = None,
) -> str:
    """Write Recommendation + evidence + outcome rows. Idempotent on snapshot_hash.

    Uses the dedicated snapshot_hash column with UNIQUE index on
    (asset_id, model_version, snapshot_hash). Policy adjustments (when
    provided) are stored in rationale JSON alongside the original action
    and confidence.
    """
    existing = _find_existing_by_snapshot(
        session,
        asset_id=result.asset_id,
        engine_version=result.engine_version,
        snapshot_hash=result.snapshot_hash,
    )
    if existing is not None:
        result.recommendation_id = existing.id
        return existing.id

    rationale: dict[str, Any] = {
        "thesis": result.thesis,
        "snapshot_hash": result.snapshot_hash,
        "enough_data": result.enough_data,
        "stale_data": result.stale_data,
        "confidence_label": result.confidence_label,
        "tags": result.tags,
        "composite_score": str(result.composite_score),
        "family_scores": {k: str(v) for k, v in result.family_scores.items()},
    }

    if decision is not None and (
        decision.adjustments or decision.adjusted_action != decision.original_action
    ):
        rationale["policy"] = {
            "original_action": decision.original_action,
            "original_composite_score": str(decision.original_composite_score),
            "original_confidence": str(decision.original_confidence),
            "adjusted_action": decision.adjusted_action,
            "adjusted_composite_score": str(decision.adjusted_composite_score),
            "adjusted_confidence": str(decision.adjusted_confidence),
            "adjustments": decision.adjustments,
        }

    rec = Recommendation(
        asset_id=result.asset_id,
        action=result.action,
        conviction=result.confidence,
        rationale=json.dumps(rationale),
        model_version=result.engine_version,
        snapshot_hash=result.snapshot_hash,
    )
    session.add(rec)
    session.flush()

    for sig in result.signals:
        summary = json.dumps({
            "narrative": sig["narrative"],
            "value": sig["value"],
            "threshold": sig["threshold"],
            "direction": sig["direction"],
            "score": sig["score"],
        })
        session.add(RecommendationEvidence(
            recommendation_id=rec.id,
            evidence_type=sig["factor_key"],
            source=sig["family"],
            summary=summary,
            weight=Decimal(sig["weight"]),
        ))

    # Performance-tracking stub: record price_at_recommendation.
    if result.current_price is not None:
        session.add(RecommendationOutcome(
            recommendation_id=rec.id,
            price_at_recommendation=result.current_price,
        ))

    session.flush()
    result.recommendation_id = rec.id
    return rec.id


def list_latest_per_asset(
    session: Session, limit: int = 50
) -> list[Recommendation]:
    """Return the most recent Recommendation per asset (global, no account scope)."""
    # Subquery: max(generated_at) per asset
    from sqlalchemy import func

    latest_ts_stmt = (
        select(
            Recommendation.asset_id.label("asset_id"),
            func.max(Recommendation.generated_at).label("max_ts"),
        )
        .group_by(Recommendation.asset_id)
        .subquery()
    )
    stmt = (
        select(Recommendation)
        .join(
            latest_ts_stmt,
            (Recommendation.asset_id == latest_ts_stmt.c.asset_id)
            & (Recommendation.generated_at == latest_ts_stmt.c.max_ts),
        )
        .order_by(Recommendation.generated_at.desc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars())


# ---------------------------------------------------------------------------
# Account-level runner
# ---------------------------------------------------------------------------


def run_for_account(
    session: Session,
    account_id: str,
    config: EngineConfig | None = None,
    asset_ids: list[str] | None = None,
    policy_context: "PolicyContext | None" = None,
) -> list[RecommendationResult]:
    cfg = config or load_engine_config()

    # Lazy import to avoid circularity at module load.
    from apps.api.src.domain.recommendations.decision_policy import (
        PolicyContext,
        apply_policy,
        build_policy_context_from_db,
    )
    if policy_context is None:
        policy_context = build_policy_context_from_db(session)

    if asset_ids is None:
        stmt = (
            select(Lot.asset_id)
            .join(Transaction, Lot.open_transaction_id == Transaction.id)
            .where(
                Transaction.account_id == account_id,
                Lot.quantity_remaining > 0,
            )
            .distinct()
        )
        asset_ids = [row[0] for row in session.execute(stmt).all()]

    results: list[RecommendationResult] = []
    for aid in asset_ids:
        result = compute_for_asset(
            session,
            account_id=account_id,
            asset_id=aid,
            config=cfg,
        )
        decision = apply_policy(result, policy_context, cfg.action_thresholds)
        persist(session, result, decision=decision)
        results.append(result)
    return results
