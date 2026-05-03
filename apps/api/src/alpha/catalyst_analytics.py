"""Earnings-window + news-age + catalyst-type analytics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

MIN_SAMPLE = 15


@dataclass
class CatalystAnalytics:
    earnings_window_buckets: list[dict[str, Any]] = field(default_factory=list)
    news_age_buckets:        list[dict[str, Any]] = field(default_factory=list)
    catalyst_type_buckets:   list[dict[str, Any]] = field(default_factory=list)
    windows_to_avoid:        list[str] = field(default_factory=list)
    types_helping:           list[str] = field(default_factory=list)
    types_hurting:           list[str] = field(default_factory=list)
    warnings:                list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "earnings_window_buckets": self.earnings_window_buckets,
            "news_age_buckets":        self.news_age_buckets,
            "catalyst_type_buckets":   self.catalyst_type_buckets,
            "windows_to_avoid":        self.windows_to_avoid,
            "types_helping":           self.types_helping,
            "types_hurting":           self.types_hurting,
            "warnings":                self.warnings,
        }


def build_catalyst_analytics(
    df: pd.DataFrame, *,
    return_col: str = "fwd_ret_5d",
) -> CatalystAnalytics:
    if df.empty or return_col not in df.columns:
        return CatalystAnalytics(warnings=["no data"])

    warnings: list[str] = []
    ctrl_mean = float(df[return_col].dropna().mean()) \
                if df[return_col].notna().any() else 0.0

    # --- Earnings timing buckets ---
    win_buckets: list[dict[str, Any]] = []
    if "days_to_earnings" in df.columns:
        rules = [
            ("pre_0_1",   lambda x: (x >= 0) & (x <= 1)),
            ("pre_2_3",   lambda x: (x >= 2) & (x <= 3)),
            ("pre_4_7",   lambda x: (x >= 4) & (x <= 7)),
            ("post_0_1",  lambda x: (x >= -1) & (x < 0)),
            ("post_2_5",  lambda x: (x >= -5) & (x < -1)),
            ("no_event",  lambda x: x.isna() | (x > 7)),
        ]
        x = df["days_to_earnings"]
        for lab, pred in rules:
            mask = pred(x)
            sub = df.loc[mask, return_col].dropna()
            win_buckets.append(_bucket(lab, sub, ctrl_mean))
    windows_to_avoid = [
        b["bucket"] for b in win_buckets
        if b["lift_vs_control"] < -0.003 and b["n"] >= MIN_SAMPLE
    ]

    # --- News age buckets ---
    age_buckets: list[dict[str, Any]] = []
    if "catalyst_news_age_hours" in df.columns:
        rules = [
            ("0_2h",   lambda x: (x >= 0) & (x < 2)),
            ("2_24h",  lambda x: (x >= 2) & (x < 24)),
            ("1_3d",   lambda x: (x >= 24) & (x < 72)),
            ("3d_plus", lambda x: x >= 72),
        ]
        x = df["catalyst_news_age_hours"]
        for lab, pred in rules:
            sub = df.loc[pred(x), return_col].dropna()
            age_buckets.append(_bucket(lab, sub, ctrl_mean))
    else:
        warnings.append(
            "catalyst_news_age_hours missing — cannot bucket by news age"
        )

    # --- Catalyst type buckets ---
    type_buckets: list[dict[str, Any]] = []
    if "catalyst_type" in df.columns:
        for cat_type in sorted(df["catalyst_type"].dropna().unique()):
            sub = df.loc[df["catalyst_type"] == cat_type, return_col].dropna()
            type_buckets.append(_bucket(str(cat_type), sub, ctrl_mean))
    else:
        warnings.append(
            "catalyst_type missing — enable provider enrichment for typed buckets"
        )

    helping = [
        b["bucket"] for b in type_buckets
        if b["lift_vs_control"] > 0.003 and b["n"] >= MIN_SAMPLE
    ]
    hurting = [
        b["bucket"] for b in type_buckets
        if b["lift_vs_control"] < -0.003 and b["n"] >= MIN_SAMPLE
    ]

    return CatalystAnalytics(
        earnings_window_buckets=win_buckets,
        news_age_buckets=age_buckets,
        catalyst_type_buckets=type_buckets,
        windows_to_avoid=windows_to_avoid,
        types_helping=helping,
        types_hurting=hurting,
        warnings=warnings,
    )


def _bucket(
    label: str, returns: pd.Series, ctrl_mean: float,
) -> dict[str, Any]:
    rets = returns.to_numpy(dtype=float)
    n = int(len(rets))
    if n == 0:
        return {"bucket": label, "n": 0, "mean_return": 0.0,
                "median_return": 0.0, "hit_rate": 0.0,
                "lift_vs_control": 0.0, "low_confidence": True}
    mu = float(rets.mean())
    return {
        "bucket": label,
        "n": n,
        "mean_return":    round(mu, 6),
        "median_return":  round(float(np.median(rets)), 6),
        "hit_rate":       round(float((rets > 0).mean()), 4),
        "lift_vs_control": round(mu - ctrl_mean, 6),
        "low_confidence": n < MIN_SAMPLE,
    }
