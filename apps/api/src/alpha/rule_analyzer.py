"""Deterministic rule analyzer — observe patterns, produce findings.

Findings are raw observations (not yet suggestions). Suggestion engine
converts them into actionable rules with risk gating. Analyzer never
raises: returns empty list on insufficient data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


MIN_SAMPLE = 50


@dataclass
class Finding:
    rule_type: str                 # signal_weakness | strong_signal |
                                    # failure_pattern | execution_issue |
                                    # risk_issue | threshold_opportunity
    target: str                     # which feature / bucket / category
    confidence: float
    sample_size: int
    impact: str                     # positive | negative | uncertain
    suggestion: str                 # reduce_weight | tighten_threshold | ...
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_type":   self.rule_type,
            "target":      self.target,
            "confidence":  round(self.confidence, 4),
            "sample_size": self.sample_size,
            "impact":      self.impact,
            "suggestion":  self.suggestion,
            "details":     dict(self.details),
        }


def analyze_rules(
    df: pd.DataFrame,
    *,
    return_col: str = "fwd_ret_5d",
    min_sample: int = MIN_SAMPLE,
    confidence_min: float = 0.7,
) -> list[Finding]:
    """Run all analyzer passes. Return trustworthy findings only."""
    findings: list[Finding] = []
    if df.empty or return_col not in df.columns:
        return findings

    ctrl_mean = float(df[return_col].dropna().mean()) \
                if df[return_col].notna().any() else 0.0
    ctrl_std = float(df[return_col].dropna().std(ddof=0)) or 1e-9

    findings.extend(_weak_signals(df, return_col, ctrl_mean, ctrl_std,
                                     min_sample, confidence_min))
    findings.extend(_strong_signals(df, return_col, ctrl_mean, ctrl_std,
                                       min_sample, confidence_min))
    findings.extend(_failure_patterns(df, return_col,
                                         min_sample, confidence_min))
    findings.extend(_execution_issues(df, return_col,
                                         min_sample, confidence_min))
    findings.extend(_risk_issues(df, return_col,
                                    min_sample, confidence_min))
    return findings


# ---------------------------------------------------------------------------
# Weak / strong signal buckets
# ---------------------------------------------------------------------------

def _weak_signals(
    df: pd.DataFrame, return_col: str,
    ctrl_mean: float, ctrl_std: float,
    min_sample: int, confidence_min: float,
) -> list[Finding]:
    out: list[Finding] = []
    for col, label in _bucketed_features(df):
        buckets = _bucket_returns(df, col, return_col)
        for lab, rets in buckets.items():
            n = len(rets)
            if n < min_sample:
                continue
            lift = float(rets.mean()) - ctrl_mean
            if lift >= -1e-4:
                continue
            # Confidence via z-like score
            se = ctrl_std / (n ** 0.5)
            z = abs(lift) / max(1e-9, se)
            conf = _z_to_conf(z)
            if conf < confidence_min:
                continue
            out.append(Finding(
                rule_type="signal_weakness",
                target=f"{label}_bucket_{lab}",
                confidence=conf,
                sample_size=n,
                impact="negative",
                suggestion="reduce_weight",
                details={
                    "feature": col, "bucket": lab,
                    "mean_return": float(rets.mean()),
                    "control_mean": ctrl_mean,
                    "lift": lift,
                },
            ))
    return out


def _strong_signals(
    df: pd.DataFrame, return_col: str,
    ctrl_mean: float, ctrl_std: float,
    min_sample: int, confidence_min: float,
) -> list[Finding]:
    out: list[Finding] = []
    for col, label in _bucketed_features(df):
        buckets = _bucket_returns(df, col, return_col)
        # Require stability: sign consistent across regimes
        regime_mix = _regime_consistency(df, col, return_col)
        for lab, rets in buckets.items():
            n = len(rets)
            if n < min_sample:
                continue
            lift = float(rets.mean()) - ctrl_mean
            if lift <= 1e-4:
                continue
            se = ctrl_std / (n ** 0.5)
            conf = _z_to_conf(abs(lift) / max(1e-9, se))
            if conf < confidence_min:
                continue
            stable = regime_mix.get(lab, True)
            out.append(Finding(
                rule_type="strong_signal",
                target=f"{label}_bucket_{lab}",
                confidence=conf,
                sample_size=n,
                impact="positive",
                suggestion="increase_weight" if stable
                            else "require_confirmation",
                details={
                    "feature": col, "bucket": lab,
                    "mean_return": float(rets.mean()),
                    "lift": lift,
                    "regime_stable": stable,
                },
            ))
    return out


# ---------------------------------------------------------------------------
# Failure patterns
# ---------------------------------------------------------------------------

def _failure_patterns(
    df: pd.DataFrame, return_col: str,
    min_sample: int, confidence_min: float,
) -> list[Finding]:
    out: list[Finding] = []
    if "failure_reason" not in df.columns and "failure_analysis" \
            not in df.columns:
        return out
    # Prefer flattened failure_reason if present; else extract from
    # failure_analysis JSONB (top reason).
    if "failure_reason" not in df.columns:
        df = df.copy()
        df["failure_reason"] = df["failure_analysis"].apply(
            lambda v: _top_failure(v),
        )
    total = int(len(df))
    if total < min_sample:
        return out
    reasons = df["failure_reason"].dropna()
    counts = reasons.value_counts()
    for reason, n in counts.items():
        if n < min_sample:
            continue
        frac = n / total
        if frac < 0.1:
            continue
        out.append(Finding(
            rule_type="failure_pattern",
            target=str(reason),
            confidence=min(1.0, frac * 3.0),
            sample_size=int(n),
            impact="negative",
            suggestion="tighten_filters",
            details={"reason": str(reason), "fraction_of_losers": frac},
        ))
    return out


# ---------------------------------------------------------------------------
# Execution issues
# ---------------------------------------------------------------------------

def _execution_issues(
    df: pd.DataFrame, return_col: str,
    min_sample: int, confidence_min: float,
) -> list[Finding]:
    out: list[Finding] = []
    if "entry_quality_score" not in df.columns:
        return out
    sub = df.dropna(subset=["entry_quality_score", return_col])
    if len(sub) < min_sample:
        return out
    low_mask = sub["entry_quality_score"] < 0.5
    if low_mask.sum() < min_sample:
        return out
    low_mean = float(sub.loc[low_mask, return_col].mean())
    high_mean = float(sub.loc[~low_mask, return_col].mean())
    if low_mean >= high_mean - 1e-4:
        return out
    out.append(Finding(
        rule_type="execution_issue",
        target="low_entry_quality",
        confidence=min(1.0, (high_mean - low_mean) * 50),
        sample_size=int(low_mask.sum()),
        impact="negative",
        suggestion="execution_guardrail",
        details={
            "low_mean_return": low_mean,
            "high_mean_return": high_mean,
            "gap": high_mean - low_mean,
        },
    ))
    return out


# ---------------------------------------------------------------------------
# Risk issues
# ---------------------------------------------------------------------------

def _risk_issues(
    df: pd.DataFrame, return_col: str,
    min_sample: int, confidence_min: float,
) -> list[Finding]:
    out: list[Finding] = []
    if "concentration_at_entry" not in df.columns:
        return out
    sub = df.dropna(subset=["concentration_at_entry", return_col])
    if len(sub) < min_sample:
        return out
    high = sub["concentration_at_entry"] > 0.4
    if high.sum() < min_sample:
        return out
    high_mean = float(sub.loc[high, return_col].mean())
    base_mean = float(sub.loc[~high, return_col].mean())
    if high_mean >= base_mean - 1e-4:
        return out
    out.append(Finding(
        rule_type="risk_issue",
        target="high_concentration",
        confidence=min(1.0, (base_mean - high_mean) * 40),
        sample_size=int(high.sum()),
        impact="negative",
        suggestion="restrict_concentrated_trades",
        details={
            "high_conc_mean_return": high_mean,
            "base_mean_return": base_mean,
        },
    ))
    return out


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _bucketed_features(
    df: pd.DataFrame,
) -> list[tuple[str, str]]:
    """Which feature columns to sweep for weakness/strength."""
    candidates = [
        ("feature_confidence", "confidence"),
        ("event_risk_score",   "event_risk"),
        ("catalyst_score",     "catalyst"),
        ("gates_favorable",    "gates"),
        ("days_to_earnings",   "days_to_earnings"),
        ("vol_elevated",       "vol_elevated"),
    ]
    return [(c, l) for c, l in candidates if c in df.columns]


def _bucket_returns(
    df: pd.DataFrame, col: str, return_col: str,
) -> dict[str, pd.Series]:
    if col not in df.columns:
        return {}
    s = df[[col, return_col]].dropna()
    if s.empty:
        return {}
    # Boolean features → true/false buckets
    if s[col].dtype == bool or set(s[col].unique()) <= {0, 1, 0.0, 1.0}:
        return {
            "true":  s.loc[s[col].astype(bool), return_col],
            "false": s.loc[~s[col].astype(bool), return_col],
        }
    # Numeric → quartile buckets
    try:
        bins = pd.qcut(s[col], q=4, duplicates="drop")
    except ValueError:
        return {}
    labels = ["q1", "q2", "q3", "q4"][: bins.cat.categories.size]
    bins = bins.cat.rename_categories(labels)
    return {lab: s.loc[bins == lab, return_col] for lab in labels}


def _regime_consistency(
    df: pd.DataFrame, col: str, return_col: str,
) -> dict[str, bool]:
    """Check if mean-return sign is stable across regimes for each bucket."""
    regimes = [
        ("regime_stress", "stress"),
        ("regime_directional", "directional"),
        ("regime_neutral", "neutral"),
    ]
    regime_cols = [c for c, _ in regimes if c in df.columns]
    if not regime_cols:
        return {}
    out: dict[str, bool] = {}
    buckets = _bucket_returns(df, col, return_col)
    for lab, _rets in buckets.items():
        signs: list[int] = []
        mask_base = _matches_bucket(df, col, lab)
        for reg_col, _ in regimes:
            if reg_col not in df.columns:
                continue
            sub = df.loc[mask_base & df[reg_col].astype(bool), return_col] \
                    .dropna()
            if len(sub) < 10:
                continue
            m = float(sub.mean())
            signs.append(1 if m > 0 else (-1 if m < 0 else 0))
        out[lab] = (len(signs) < 2) or (len(set(signs)) == 1)
    return out


def _matches_bucket(
    df: pd.DataFrame, col: str, lab: str,
) -> pd.Series:
    s = df[col]
    if s.dtype == bool or set(s.dropna().unique()) <= {0, 1, 0.0, 1.0}:
        return s.astype(bool) if lab == "true" else ~s.astype(bool)
    try:
        bins = pd.qcut(s, q=4, duplicates="drop")
    except ValueError:
        return pd.Series(False, index=s.index)
    labels = ["q1", "q2", "q3", "q4"][: bins.cat.categories.size]
    bins = bins.cat.rename_categories(labels)
    return bins == lab


def _z_to_conf(z: float) -> float:
    """Approx one-sided normal CDF without scipy: 1 - 0.5*exp(-0.717z - 0.416 z^2)."""
    if z <= 0:
        return 0.5
    # Abramowitz & Stegun approximation for Phi(z)
    import math
    p = 1 - 0.5 * math.exp(-0.717 * z - 0.416 * z * z)
    return max(0.0, min(1.0, p))


def _top_failure(blob: Any) -> str | None:
    if not isinstance(blob, dict):
        return None
    reasons = blob.get("failure_reasons") or []
    if not reasons:
        return None
    return reasons[0].get("reason") if isinstance(reasons[0], dict) else None
