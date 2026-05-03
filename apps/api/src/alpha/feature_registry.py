"""Feature registry + schema/dataset drift detection."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class FeatureRegistryEntry:
    feature_name: str
    feature_set_version: str
    dtype: str
    nullable: bool = True
    allowed_range: tuple[float, float] | None = None
    source: str | None = None
    active: bool = True
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "feature_set_version": self.feature_set_version,
            "dtype": self.dtype,
            "nullable": self.nullable,
            "allowed_range": (
                list(self.allowed_range) if self.allowed_range else None
            ),
            "source": self.source,
            "active": self.active,
            "notes": self.notes,
        }


@dataclass
class DriftReport:
    schema_new_features:     list[str] = field(default_factory=list)
    schema_removed_features: list[str] = field(default_factory=list)
    schema_dtype_changes:    list[dict[str, Any]] = field(default_factory=list)
    distribution_drift:      list[dict[str, Any]] = field(default_factory=list)
    high_missing:            list[dict[str, Any]] = field(default_factory=list)
    out_of_range:            list[dict[str, Any]] = field(default_factory=list)
    warnings:                list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_new_features":     self.schema_new_features,
            "schema_removed_features": self.schema_removed_features,
            "schema_dtype_changes":    self.schema_dtype_changes,
            "distribution_drift":      self.distribution_drift,
            "high_missing":            self.high_missing,
            "out_of_range":            self.out_of_range,
            "warnings":                self.warnings,
        }


def detect_drift(
    *,
    baseline: pd.DataFrame,
    recent: pd.DataFrame,
    registry: list[FeatureRegistryEntry],
    psi_threshold: float = 0.25,
    missing_delta_threshold: float = 0.15,
) -> DriftReport:
    """Compare `recent` distribution to `baseline`. Return drift report."""
    warnings: list[str] = []
    out = DriftReport()

    baseline_cols = set(baseline.columns)
    recent_cols = set(recent.columns)
    registry_cols = {r.feature_name for r in registry if r.active}

    out.schema_new_features = sorted(recent_cols - baseline_cols)
    out.schema_removed_features = sorted(baseline_cols - recent_cols)
    if registry_cols:
        unknown_in_recent = sorted(recent_cols - registry_cols - {
            "as_of_date", "decision_id", "decision_ts", "symbol",
            "instrument", "engine", "action", "source_type",
            "replay_run_id", "sample_weight",
        })
        if unknown_in_recent:
            warnings.append(
                "recent frame has features not in registry: "
                + ", ".join(unknown_in_recent[:5])
            )

    for col in baseline_cols & recent_cols:
        bd = baseline[col].dtype
        rd = recent[col].dtype
        if str(bd) != str(rd):
            out.schema_dtype_changes.append({
                "feature": col, "baseline_dtype": str(bd),
                "recent_dtype":  str(rd),
            })

        b_miss = float(baseline[col].isna().mean()) if len(baseline) else 0.0
        r_miss = float(recent[col].isna().mean())   if len(recent)   else 0.0
        if abs(r_miss - b_miss) > missing_delta_threshold:
            out.high_missing.append({
                "feature": col,
                "baseline_missing": round(b_miss, 4),
                "recent_missing":   round(r_miss, 4),
            })

        if pd.api.types.is_numeric_dtype(baseline[col]) \
           and pd.api.types.is_numeric_dtype(recent[col]):
            psi = _psi(baseline[col], recent[col])
            if psi is not None and psi > psi_threshold:
                out.distribution_drift.append({
                    "feature": col, "psi": round(psi, 4),
                })

    # Out-of-range check vs registry
    for entry in registry:
        if entry.allowed_range is None:
            continue
        col = entry.feature_name
        if col not in recent.columns:
            continue
        lo, hi = entry.allowed_range
        over = recent[col].dropna()
        if over.empty:
            continue
        n_out = int(((over < lo) | (over > hi)).sum())
        if n_out > 0:
            out.out_of_range.append({
                "feature": col, "lo": lo, "hi": hi,
                "n_out": n_out,
                "pct_out": round(n_out / len(over), 4),
            })

    out.warnings = warnings
    return out


def _psi(
    baseline: pd.Series, recent: pd.Series, bins: int = 10,
) -> float | None:
    """Population Stability Index — simple fixed-bin variant."""
    b = baseline.dropna().astype(float).to_numpy()
    r = recent.dropna().astype(float).to_numpy()
    if len(b) < 30 or len(r) < 30:
        return None
    edges = np.quantile(b, np.linspace(0, 1, bins + 1))
    edges = np.unique(edges)
    if len(edges) < 3:
        return None
    b_hist, _ = np.histogram(b, bins=edges)
    r_hist, _ = np.histogram(r, bins=edges)
    b_pct = (b_hist + 1) / (b_hist.sum() + len(edges))
    r_pct = (r_hist + 1) / (r_hist.sum() + len(edges))
    psi = float(np.sum((r_pct - b_pct) * np.log(r_pct / b_pct)))
    return psi
