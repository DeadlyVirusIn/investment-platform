"""Data quality — provider reliability + feature confidence heatmap."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class ProviderReliability:
    provider: str
    reliability_score: float
    freshness_score:   float
    missing_rate:      float
    error_rate:        float
    latency_p50_ms: int | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "reliability_score": round(self.reliability_score, 4),
            "freshness_score":   round(self.freshness_score, 4),
            "missing_rate":      round(self.missing_rate, 4),
            "error_rate":        round(self.error_rate, 4),
            "latency_p50_ms":    self.latency_p50_ms,
            "notes":             self.notes,
        }


def compute_provider_reliability(
    *,
    provider: str,
    success_rate: float,
    freshness_score: float = 1.0,
    missing_rate: float = 0.0,
    error_rate: float = 0.0,
    latency_p50_ms: int | None = None,
    disagreement_rate: float | None = None,
    notes: str = "",
) -> ProviderReliability:
    """Weighted blend: success 50% + freshness 20% + (1-missing) 15% +
    (1-error) 10% + (1-disagreement) 5%."""
    s = max(0.0, min(1.0, success_rate))
    f = max(0.0, min(1.0, freshness_score))
    m = 1.0 - max(0.0, min(1.0, missing_rate))
    e = 1.0 - max(0.0, min(1.0, error_rate))
    if disagreement_rate is not None:
        d = 1.0 - max(0.0, min(1.0, disagreement_rate))
    else:
        d = 0.8                         # neutral prior when unknown
    reliability = (s * 0.50 + f * 0.20 + m * 0.15
                   + e * 0.10 + d * 0.05)
    return ProviderReliability(
        provider=provider,
        reliability_score=reliability,
        freshness_score=f,
        missing_rate=missing_rate,
        error_rate=error_rate,
        latency_p50_ms=latency_p50_ms,
        notes=notes,
    )


# ---------------------------------------------------------------------------
@dataclass
class FeatureConfidenceHeatmap:
    features: list[dict[str, Any]] = field(default_factory=list)
    most_unreliable: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "features": self.features,
            "most_unreliable": self.most_unreliable,
        }


def compute_feature_heatmap(
    df: pd.DataFrame, *,
    feature_cols: tuple[str, ...],
    confidence_col: str = "feature_confidence",
    top_k: int = 10,
) -> FeatureConfidenceHeatmap:
    if df.empty:
        return FeatureConfidenceHeatmap()
    rows: list[dict[str, Any]] = []
    for col in feature_cols:
        if col not in df.columns:
            rows.append({"feature": col, "missing_rate": 1.0,
                         "stale_rate": None, "note": "column missing"})
            continue
        missing = float(df[col].isna().mean())
        rows.append({
            "feature": col,
            "missing_rate": round(missing, 4),
            "n": int(df[col].notna().sum()),
        })
    rows.sort(key=lambda r: -r.get("missing_rate", 0.0))
    return FeatureConfidenceHeatmap(
        features=rows,
        most_unreliable=[r["feature"] for r in rows
                          if r.get("missing_rate", 0.0) >= 0.3][:top_k],
    )
