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
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    Lot,
    Recommendation,
    RecommendationEvidence,
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
    confidence: Decimal  # 0..1
    enough_data: bool
    engine_version: str
    snapshot_hash: str
    thesis: str
    composite_score: Decimal
    family_scores: dict[str, Decimal]
    signals: list[dict[str, Any]]
    tags: list[str]
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
) -> RecommendationResult:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise ValueError(f"unknown asset_id: {asset_id}")

    series = load_series(session, asset_id)
    enough = _check_enough_data(series, asset, config)

    if series is not None:
        fam_trend = compute_trend_momentum(series, config.trend_momentum)
        fam_vol = compute_volatility_risk(series, config.volatility_risk)
    else:
        fam_trend = FamilyOut("trend_momentum", Decimal("0"), [], computable=False)
        fam_vol = FamilyOut("volatility_risk", Decimal("0"), [], computable=False)

    fam_exp = compute_exposure(session, account_id, asset_id, config.exposure)

    # Renormalize across computable families only.
    computable = [f for f in (fam_trend, fam_vol, fam_exp) if f.computable]
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
        enough = False

    tags: list[str] = [asset.asset_class]
    for fam in (fam_trend, fam_vol, fam_exp):
        if not fam.computable:
            tags.append(f"missing-{fam.family}")

    if not enough:
        action = "Watch"
    else:
        action = _map_score_to_action(composite, config.action_thresholds)

    confidence = abs(composite) if enough else Decimal("0")

    all_signals: list[dict[str, Any]] = []
    for fam in (fam_trend, fam_vol, fam_exp):
        all_signals.extend(_family_to_signals(fam))

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
    if not enough:
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
        enough_data=enough,
        engine_version=config.version,
        snapshot_hash=snap,
        thesis=thesis,
        composite_score=composite,
        family_scores=family_scores,
        signals=all_signals,
        tags=tags,
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def persist(session: Session, result: RecommendationResult) -> str:
    """Write Recommendation + evidence rows. Returns recommendation id."""
    rationale = {
        "thesis": result.thesis,
        "snapshot_hash": result.snapshot_hash,
        "enough_data": result.enough_data,
        "tags": result.tags,
        "composite_score": str(result.composite_score),
        "family_scores": {k: str(v) for k, v in result.family_scores.items()},
    }

    rec = Recommendation(
        asset_id=result.asset_id,
        action=result.action,
        conviction=result.confidence,
        rationale=json.dumps(rationale),
        model_version=result.engine_version,
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

    session.flush()
    result.recommendation_id = rec.id
    return rec.id


# ---------------------------------------------------------------------------
# Account-level runner
# ---------------------------------------------------------------------------


def run_for_account(
    session: Session,
    account_id: str,
    config: EngineConfig | None = None,
    asset_ids: list[str] | None = None,
) -> list[RecommendationResult]:
    cfg = config or load_engine_config()

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
        persist(session, result)
        results.append(result)
    return results
