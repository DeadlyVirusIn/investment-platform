"""Real model attribution via LightGBM native contributions (Sprint 2).

Scope honesty (from docs/research/MODEL_AND_DATA_FORENSICS.md): the
user-facing STOCK recommendation confidence is produced by the rule-based
engine (`recommendation_engine._compute_confidence`), NOT by LightGBM.
The LightGBM meta-labeler is shadow/research-only today (kill switch
`ML_CAN_AFFECT_TRADES=False`, dead inference seam). Therefore:

  * this module attributes the ACTUAL LightGBM shadow model, for the
    Experiment Lab / research surfaces and for any future promoted model;
  * it must NOT be presented as "why this idea exists" on stock idea
    pages while those ideas come from the rule engine — the idea page's
    factor evidence (`recommendation_evidence`, family_scores) already
    reflects the true producer.

Method: ``booster.predict(X, pred_contrib=True)`` — per-row additive
feature contributions in RAW-SCORE (log-odds) space with the expected
value in the trailing column, satisfying exactly:

    base_value + sum(contributions) == raw_score

For the binary meta-labeler, displayed probability = sigmoid(raw_score);
contributions are additive in log-odds, NOT in probability space — the
beginner payload therefore only ever ranks and directionally labels
factors ("influenced"), never quotes per-factor probability points.

Wording contract (approved): "Factors that influenced the model result."
NEVER causal market claims ("reasons the stock will rise").
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
import pandas as pd

ATTRIBUTION_METHOD = "lightgbm_pred_contrib"
_RECONCILE_ATOL = 1e-6

# ---------------------------------------------------------------------------
# Beginner feature language — stable dictionary, versioned with the schema.
# Descriptions are influence-neutral: they name the factor, never a promise.
# ---------------------------------------------------------------------------
FEATURE_LANGUAGE: dict[str, str] = {
    "composite_score": "the engine's overall score for this setup",
    "confidence": "the engine's own signal agreement",
    "residual_momentum_20d": "recent price momentum (about a month), market-adjusted",
    "residual_momentum_60d": "medium-term price momentum (about a quarter), market-adjusted",
    "sector_relative_rank": "strength compared with its sector",
    "trend_strength_20d": "how steady the recent trend has been",
    "price_vs_200sma": "price versus its long-term average",
    "atr_percent_14": "size of day-to-day price swings",
    "avg_dollar_volume_20d": "how easily the stock trades (liquidity)",
    "realized_vol_20d": "recent volatility",
    "atr_pctile_1y": "volatility versus its own past year",
    # one-hot categorical prefixes (matched by prefix below)
    "market_trend": "the overall market trend",
    "vol_regime": "current market volatility conditions",
}

LIMITATIONS_STATEMENT = (
    "These are the factors that influenced the model result — a statistical "
    "read of past patterns, not reasons the stock will rise or fall. "
    "Influences are measured in the model's internal score space; they are "
    "relative, can change as data updates, and do not imply causality."
)


class AttributionError(ValueError):
    """Raised when contributions cannot be produced or verified."""


def beginner_label(feature: str) -> str:
    """Stable plain-English name for a model feature (prefix-aware for
    one-hot categoricals, e.g. ``market_trend_bull``)."""
    if feature in FEATURE_LANGUAGE:
        return FEATURE_LANGUAGE[feature]
    for prefix, label in FEATURE_LANGUAGE.items():
        if feature.startswith(prefix + "_"):
            suffix = feature[len(prefix) + 1 :].replace("_", " ")
            return f"{label} ({suffix})"
    raise AttributionError(f"unknown feature has no beginner language: {feature!r}")


def feature_schema_version(feature_names: Sequence[str]) -> str:
    """Deterministic version of the exact feature set AND ordering (the
    forensics doc flagged one-hot ordering as data-dependent — hashing the
    ordered list makes any drift visible)."""
    payload = json.dumps(list(feature_names)).encode("utf-8")
    return "fs-" + hashlib.sha256(payload).hexdigest()[:16]


def model_version_of(booster: Any) -> str:
    """Content hash of the trained booster (no artifact registry exists yet
    — see forensics §10 — so the model string itself is the identity)."""
    return "lgbm-" + hashlib.sha256(
        booster.model_to_string().encode("utf-8")
    ).hexdigest()[:16]


@dataclass
class FeatureContribution:
    feature: str
    value: float | None
    contribution: float
    beginner_label: str
    direction: str  # "supporting" | "cautionary"

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "value": self.value,
            "contribution": self.contribution,
            "beginner_label": self.beginner_label,
            "direction": self.direction,
        }


@dataclass
class AttributionRecord:
    model_version: str
    feature_schema_version: str
    inference_at: str
    method: str
    raw_score: float
    base_value: float
    probability: float
    contributions: list[FeatureContribution] = field(default_factory=list)
    limitations: str = LIMITATIONS_STATEMENT

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "feature_schema_version": self.feature_schema_version,
            "inference_at": self.inference_at,
            "method": self.method,
            "raw_score": self.raw_score,
            "base_value": self.base_value,
            "probability": self.probability,
            "contributions": [c.to_dict() for c in self.contributions],
            "limitations": self.limitations,
        }


def _finite(name: str, arr: np.ndarray) -> None:
    if not np.isfinite(arr).all():
        raise AttributionError(f"non-finite values in {name} — refusing to attribute")


def compute_attributions(
    booster: Any,
    X: pd.DataFrame,
    *,
    feature_names: Sequence[str],
    now: dt.datetime | None = None,
) -> list[AttributionRecord]:
    """Attribute each row of ``X`` against the given LightGBM booster.

    Verifies per row that ``base_value + Σ contributions == raw_score``
    (the additivity guarantee of ``pred_contrib``) and that all outputs are
    finite. NaN feature VALUES are legal (LightGBM handles missing values
    natively and still attributes them); NaN/Inf in the model OUTPUT is a
    hard error.
    """
    missing = [f for f in feature_names if f not in X.columns]
    if missing:
        raise AttributionError(f"X lacks expected features: {missing[:5]}")
    unknown = [c for c in X.columns if c not in feature_names]
    if unknown:
        raise AttributionError(f"unexpected features not in schema: {unknown[:5]}")

    ordered = X[list(feature_names)]
    for f in feature_names:
        beginner_label(f)  # every feature must have language BEFORE display

    contrib = np.asarray(booster.predict(ordered, pred_contrib=True), dtype=float)
    raw = np.asarray(booster.predict(ordered, raw_score=True), dtype=float)
    _finite("pred_contrib", contrib)
    _finite("raw_score", raw)

    if contrib.shape != (len(ordered), len(feature_names) + 1):
        raise AttributionError(
            f"contribution shape {contrib.shape} != "
            f"({len(ordered)}, {len(feature_names) + 1})"
        )

    # additivity: base (last column) + feature contributions == raw score
    recon = contrib.sum(axis=1) - raw
    if not np.allclose(recon, 0.0, atol=_RECONCILE_ATOL):
        raise AttributionError(
            f"reconciliation failed: max |base+Σcontrib−raw| = {np.abs(recon).max():.3e}"
        )

    stamp = (now or dt.datetime.now(dt.timezone.utc)).isoformat()
    mv = model_version_of(booster)
    fsv = feature_schema_version(feature_names)

    records: list[AttributionRecord] = []
    for i in range(len(ordered)):
        raw_i = float(raw[i])
        base_i = float(contrib[i, -1])
        rows = []
        for j, f in enumerate(feature_names):
            c = float(contrib[i, j])
            v = ordered.iloc[i, j]
            rows.append(FeatureContribution(
                feature=f,
                value=None if pd.isna(v) else float(v),
                contribution=c,
                beginner_label=beginner_label(f),
                direction="supporting" if c >= 0 else "cautionary",
            ))
        rows.sort(key=lambda r: abs(r.contribution), reverse=True)
        records.append(AttributionRecord(
            model_version=mv,
            feature_schema_version=fsv,
            inference_at=stamp,
            method=ATTRIBUTION_METHOD,
            raw_score=raw_i,
            base_value=base_i,
            probability=1.0 / (1.0 + math.exp(-raw_i)),
            contributions=rows,
        ))
    return records


def beginner_payload(record: AttributionRecord, *, top_k: int = 3) -> dict[str, Any]:
    """Dev-only 'See the working' payload. Ranks by |influence|; shows
    relative magnitude (share of total |contribution|), never per-factor
    probability points (contributions live in log-odds space)."""
    total = sum(abs(c.contribution) for c in record.contributions) or 1.0

    def rows(direction: str) -> list[dict[str, Any]]:
        picked = [c for c in record.contributions if c.direction == direction][:top_k]
        return [
            {
                "label": c.beginner_label,
                "relative_influence": round(abs(c.contribution) / total, 4),
            }
            for c in picked
        ]

    return {
        "headline": "Factors that influenced the model result",
        "supporting": rows("supporting"),
        "cautionary": rows("cautionary"),
        "model_version": record.model_version,
        "feature_schema_version": record.feature_schema_version,
        "as_of": record.inference_at,
        "limitations": record.limitations,
        # Honesty banner for any dev render while the shadow model is not
        # the producer of user-facing stock ideas:
        "scope_note": (
            "Attribution of the research (shadow) model — not the engine "
            "that published this idea."
        ),
    }
