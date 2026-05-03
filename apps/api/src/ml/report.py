"""Feature health diagnostic report.

Pure-pandas. Produced BEFORE any training so we can honestly answer
"is ML justified yet?"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from apps.api.src.ml.features import FEATURE_COLUMNS, LABEL_COLUMNS


@dataclass
class FeatureHealthReport:
    n_rows: int
    n_symbols: int
    n_decisions: int
    date_range: tuple[str, str] | None
    missing_rate: dict[str, float] = field(default_factory=dict)
    stale_rate: dict[str, float] = field(default_factory=dict)
    feature_confidence_bucket_counts: dict[str, int] = field(default_factory=dict)
    catalyst_coverage: float = 0.0
    earnings_coverage: float = 0.0
    label_availability: dict[str, int] = field(default_factory=dict)
    class_balance: dict[str, dict[str, float]] = field(default_factory=dict)
    pnl_by_catalyst_score_bucket: list[dict[str, Any]] = field(default_factory=list)
    pnl_by_event_risk_bucket: list[dict[str, Any]] = field(default_factory=list)
    pnl_by_data_confidence_bucket: list[dict[str, Any]] = field(default_factory=list)
    pnl_near_earnings_vs_not: dict[str, float | int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_rows": self.n_rows,
            "n_symbols": self.n_symbols,
            "n_decisions": self.n_decisions,
            "date_range": self.date_range,
            "missing_rate": self.missing_rate,
            "stale_rate": self.stale_rate,
            "feature_confidence_bucket_counts": self.feature_confidence_bucket_counts,
            "catalyst_coverage": round(self.catalyst_coverage, 4),
            "earnings_coverage": round(self.earnings_coverage, 4),
            "label_availability": self.label_availability,
            "class_balance": self.class_balance,
            "pnl_by_catalyst_score_bucket": self.pnl_by_catalyst_score_bucket,
            "pnl_by_event_risk_bucket":     self.pnl_by_event_risk_bucket,
            "pnl_by_data_confidence_bucket": self.pnl_by_data_confidence_bucket,
            "pnl_near_earnings_vs_not":     self.pnl_near_earnings_vs_not,
            "warnings": self.warnings,
        }


def build_feature_health(
    df: pd.DataFrame,
    *,
    primary_return_col: str = "fwd_ret_5d",
) -> FeatureHealthReport:
    n = len(df)
    warnings: list[str] = []

    date_range: tuple[str, str] | None = None
    if "as_of_date" in df.columns and n > 0:
        dates = pd.to_datetime(df["as_of_date"]).dropna()
        if not dates.empty:
            date_range = (
                dates.min().date().isoformat(),
                dates.max().date().isoformat(),
            )

    # Missing / stale rates — only over declared features
    missing_rate: dict[str, float] = {}
    for col in FEATURE_COLUMNS:
        if col in df.columns and n > 0:
            missing_rate[col] = float(df[col].isna().mean())
        else:
            missing_rate[col] = 1.0
    # Stale rate: proxy via missing_field_count / stale_field_count if present
    stale_rate: dict[str, float] = {}
    if "stale_field_count" in df.columns and n > 0:
        stale_rate["__any__"] = float(df["stale_field_count"].gt(0).mean())

    # Feature confidence bucket counts
    bucket_counts: dict[str, int] = {}
    if "feature_confidence" in df.columns and n > 0:
        bins = pd.cut(
            df["feature_confidence"].fillna(0.0),
            bins=[-0.01, 0.3, 0.6, 0.85, 1.01],
            labels=["low", "mid_low", "mid_high", "high"],
        )
        for label, cnt in bins.value_counts().items():
            bucket_counts[str(label)] = int(cnt)

    # Catalyst + earnings coverage
    catalyst_cov = (
        float(df["catalyst_score"].notna().mean())
        if "catalyst_score" in df.columns and n > 0 else 0.0
    )
    earnings_cov = (
        float(df["days_to_earnings"].notna().mean())
        if "days_to_earnings" in df.columns and n > 0 else 0.0
    )

    # Label availability per column
    label_avail: dict[str, int] = {}
    for col in LABEL_COLUMNS:
        if col in df.columns:
            label_avail[col] = int(df[col].notna().sum())
        else:
            label_avail[col] = 0

    # Class balance on win labels
    class_bal: dict[str, dict[str, float]] = {}
    for col in LABEL_COLUMNS:
        if not col.startswith("label_win_"):
            continue
        if col in df.columns:
            s = df[col].dropna()
            if len(s) > 0:
                class_bal[col] = {
                    "n": int(len(s)),
                    "pos_rate": float(s.astype(float).mean()),
                }

    # PnL buckets on primary return col
    pbs: dict[str, list[dict[str, Any]]] = {
        "catalyst": [], "event_risk": [], "data_conf": [],
    }
    if primary_return_col in df.columns and n > 0:
        def _buckets(col: str, edges: list[float]) -> list[dict[str, Any]]:
            if col not in df.columns:
                return []
            rows = df[[col, primary_return_col]].dropna()
            if rows.empty:
                return []
            labels = [
                f"{edges[i]:.2f}–{edges[i+1]:.2f}"
                for i in range(len(edges) - 1)
            ]
            rows = rows.copy()
            rows["_b"] = pd.cut(rows[col], bins=edges, labels=labels,
                                 include_lowest=True)
            grouped = rows.groupby("_b", observed=True)
            out = []
            for k, g in grouped:
                out.append({
                    "bucket": str(k),
                    "n": int(len(g)),
                    "mean_ret": float(g[primary_return_col].mean()),
                    "median_ret": float(g[primary_return_col].median()),
                })
            return out

        pbs["catalyst"]   = _buckets("catalyst_score",
                                     [-0.01, 0.25, 0.5, 0.75, 1.01])
        pbs["event_risk"] = _buckets("event_risk_score",
                                     [-0.01, 0.25, 0.5, 0.75, 1.01])
        pbs["data_conf"]  = _buckets("feature_confidence",
                                     [-0.01, 0.5, 0.75, 0.9, 1.01])

    # Near-earnings pnl comparison
    near_vs_not: dict[str, float | int] = {}
    if (
        "has_earnings_soon" in df.columns
        and primary_return_col in df.columns and n > 0
    ):
        has = df["has_earnings_soon"].astype(bool).fillna(False)
        near = df.loc[has, primary_return_col].dropna()
        notn = df.loc[~has, primary_return_col].dropna()
        near_vs_not = {
            "near_n":   int(len(near)),
            "near_mean": float(near.mean()) if len(near) else 0.0,
            "notnear_n": int(len(notn)),
            "notnear_mean": float(notn.mean()) if len(notn) else 0.0,
        }

    # Warnings
    if n < 200:
        warnings.append(
            f"dataset size {n} < 200 — diagnostics only, no model training"
        )
    elif n < 1000:
        warnings.append(
            f"dataset size {n} < 1000 — baselines only; ML would overfit"
        )
    if label_avail.get("fwd_ret_5d", 0) == 0:
        warnings.append("no fwd_ret_5d labels available — price bars missing?")
    if catalyst_cov < 0.2:
        warnings.append(
            f"catalyst coverage {catalyst_cov:.0%} — catalyst features weak"
        )

    return FeatureHealthReport(
        n_rows=n,
        n_symbols=(
            int(df["symbol"].nunique()) if "symbol" in df.columns and n > 0 else 0
        ),
        n_decisions=(
            int(df["decision_id"].nunique())
            if "decision_id" in df.columns and n > 0 else n
        ),
        date_range=date_range,
        missing_rate=missing_rate,
        stale_rate=stale_rate,
        feature_confidence_bucket_counts=bucket_counts,
        catalyst_coverage=catalyst_cov,
        earnings_coverage=earnings_cov,
        label_availability=label_avail,
        class_balance=class_bal,
        pnl_by_catalyst_score_bucket=pbs["catalyst"],
        pnl_by_event_risk_bucket=pbs["event_risk"],
        pnl_by_data_confidence_bucket=pbs["data_conf"],
        pnl_near_earnings_vs_not=near_vs_not,
        warnings=warnings,
    )
