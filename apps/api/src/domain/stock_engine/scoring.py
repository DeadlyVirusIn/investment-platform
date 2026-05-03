"""Composite score + action mapping for stock-swing candidates.

Formulas per spec Section 5.3 / 5.5:

    composite =
        0.35 * clamp(rm60,        -3, 3) / 3
      + 0.20 * clamp(rm20,        -3, 3) / 3
      + 0.20 * (2 * sector_rank - 1)
      + 0.15 * clamp(trend_20d,   -2, 2) / 2
      + 0.10 * (-1 * clamp((atr_pct - p50) / p50, -1, 1))

    confidence = 50 + 50 * |composite|

    action = Buy   if composite >= 0.25
             Hold  if composite >= -0.25
             Trim  if composite >= -0.65
             Sell  otherwise
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from apps.api.src.db.models import FactorSnapshot

# ---------------------------------------------------------------------------
# Config (frozen for this engine version)
# ---------------------------------------------------------------------------

WEIGHTS: dict[str, float] = {
    "rm60":   0.35,
    "rm20":   0.10,
    "sector": 0.10,
    "trend":  0.25,
    "vol":    0.20,
}

ACTION_THRESHOLDS: dict[str, float] = {
    "BUY":    0.25,
    "HOLD":  -0.25,
    "REDUCE": -0.65,
    # below REDUCE → Sell
}

ENGINE_NAME = "stock_swing_v1"
GATE_SET_VERSION = "v2_extended_from_sma200"
SCORE_TRANSFORM_VERSION = "v3_antiextension_penalty"

# Anti-extension soft penalty — applied after weighted composite is computed.
# No penalty when price_vs_200sma <= EXT_PENALTY_START; scales linearly to
# EXT_PENALTY_MAX_FRAC at EXT_PENALTY_FULL and above.
EXT_PENALTY_START    = 0.15
EXT_PENALTY_FULL     = 0.35     # +15% + 0.20 range → full penalty at +35%
EXT_PENALTY_MAX_FRAC = 0.50     # cap: reduce composite by up to 50%


def _engine_config_hash() -> str:
    blob = json.dumps(
        {
            "weights": WEIGHTS,
            "thresholds": ACTION_THRESHOLDS,
            "gate_set": GATE_SET_VERSION,
            "score_transform": SCORE_TRANSFORM_VERSION,
            "ext_penalty_start": EXT_PENALTY_START,
            "ext_penalty_full":  EXT_PENALTY_FULL,
            "ext_penalty_max":   EXT_PENALTY_MAX_FRAC,
        },
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


ENGINE_CONFIG_HASH: str = _engine_config_hash()
MODEL_VERSION: str = f"{ENGINE_NAME}:{ENGINE_CONFIG_HASH}"


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Score + action
# ---------------------------------------------------------------------------


@dataclass
class ScoreResult:
    composite: Decimal | None
    confidence: Decimal | None
    confidence_label: str | None
    action: str | None
    contributions: dict[str, Decimal]   # per-component contribution to composite
    missing_components: list[str]        # components that were None


def composite_score(
    row: FactorSnapshot, universe_atr_median: Decimal | float | None,
) -> ScoreResult:
    """Compute composite from a factor_snapshot row. Missing inputs produce
    component-level zeros (with the component name listed in
    ``missing_components``). When *every* input is missing, composite = None
    (fully unscorable)."""
    rm60_raw = _to_float(row.residual_momentum_60d)
    rm20_raw = _to_float(row.residual_momentum_20d)
    sect_raw = _to_float(row.sector_relative_rank)
    trnd_raw = _to_float(row.trend_strength_20d)
    atrp_raw = _to_float(row.atr_percent_14)
    p50_raw  = _to_float(universe_atr_median)

    missing: list[str] = []
    contrib: dict[str, float] = {}

    if rm60_raw is None:
        missing.append("residual_momentum_60d")
        contrib["rm60"] = 0.0
    else:
        contrib["rm60"] = WEIGHTS["rm60"] * _clamp(rm60_raw, -3, 3) / 3

    if rm20_raw is None:
        missing.append("residual_momentum_20d")
        contrib["rm20"] = 0.0
    else:
        contrib["rm20"] = WEIGHTS["rm20"] * _clamp(rm20_raw, -3, 3) / 3

    if sect_raw is None:
        missing.append("sector_relative_rank")
        contrib["sector"] = 0.0
    else:
        contrib["sector"] = WEIGHTS["sector"] * (2 * sect_raw - 1)

    if trnd_raw is None:
        missing.append("trend_strength_20d")
        contrib["trend"] = 0.0
    else:
        contrib["trend"] = WEIGHTS["trend"] * _clamp(trnd_raw, -2, 2) / 2

    if atrp_raw is None or p50_raw is None or p50_raw <= 0:
        if atrp_raw is None:
            missing.append("atr_percent_14")
        contrib["vol"] = 0.0
    else:
        vol_term = -1 * _clamp((atrp_raw - p50_raw) / p50_raw, -1, 1)
        contrib["vol"] = WEIGHTS["vol"] * vol_term

    if len(missing) >= len(WEIGHTS):
        return ScoreResult(
            composite=None, confidence=None, confidence_label=None,
            action=None, contributions={k: Decimal("0") for k in contrib},
            missing_components=missing,
        )

    score = sum(contrib.values())

    # Anti-extension soft penalty (ranking correction only).
    # Penalty applies even when price_vs_200sma is missing? No — only when
    # value is known and above start threshold.
    p200 = _to_float(row.price_vs_200sma)
    if p200 is not None and p200 > EXT_PENALTY_START:
        span = EXT_PENALTY_FULL - EXT_PENALTY_START
        frac = min(max((p200 - EXT_PENALTY_START) / span, 0.0), 1.0)
        score = score * (1.0 - EXT_PENALTY_MAX_FRAC * frac)
        contrib["ext_penalty"] = -EXT_PENALTY_MAX_FRAC * frac * (score / (1.0 - EXT_PENALTY_MAX_FRAC * frac) if (1.0 - EXT_PENALTY_MAX_FRAC * frac) != 0 else 0.0)

    conf = 50 + 50 * abs(score)
    label = "Low" if conf < 40 else ("High" if conf > 70 else "Medium")
    action = map_action(score)

    return ScoreResult(
        composite=Decimal(str(round(score, 6))),
        confidence=Decimal(str(round(conf, 4))),
        confidence_label=label,
        action=action,
        contributions={k: Decimal(str(round(v, 6))) for k, v in contrib.items()},
        missing_components=missing,
    )


def map_action(score: float) -> str:
    if score >= ACTION_THRESHOLDS["BUY"]:
        return "Buy"
    if score >= ACTION_THRESHOLDS["HOLD"]:
        return "Hold"
    if score >= ACTION_THRESHOLDS["REDUCE"]:
        return "Trim"
    return "Sell"


def factor_breakdown_payload(
    row: FactorSnapshot, score: ScoreResult,
) -> dict[str, Any]:
    """Assemble the JSONB payload stored in candidate_idea.factor_breakdown."""
    return {
        "weights": WEIGHTS,
        "thresholds": ACTION_THRESHOLDS,
        "values": {
            "residual_momentum_60d": str(row.residual_momentum_60d) if row.residual_momentum_60d is not None else None,
            "residual_momentum_20d": str(row.residual_momentum_20d) if row.residual_momentum_20d is not None else None,
            "sector_relative_rank": str(row.sector_relative_rank) if row.sector_relative_rank is not None else None,
            "trend_strength_20d": str(row.trend_strength_20d) if row.trend_strength_20d is not None else None,
            "atr_percent_14": str(row.atr_percent_14) if row.atr_percent_14 is not None else None,
            "price_vs_200sma": str(row.price_vs_200sma) if row.price_vs_200sma is not None else None,
            "avg_dollar_volume_20d": str(row.avg_dollar_volume_20d) if row.avg_dollar_volume_20d is not None else None,
        },
        "contributions": {k: str(v) for k, v in score.contributions.items()},
        "missing_components": score.missing_components,
        "composite": str(score.composite) if score.composite is not None else None,
        "confidence": str(score.confidence) if score.confidence is not None else None,
        "confidence_label": score.confidence_label,
    }
