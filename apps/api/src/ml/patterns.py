"""Pattern discovery — honest, deterministic, sample-size-aware.

Takes the same DataFrame as the rest of the ML module (built by
`ml.dataset.build_dataset`) and bucket-analyses it along several axes:
  * catalyst score / event risk / earnings proximity / trade policy
  * data quality (confidence / missing / stale)
  * regime (type, gates, volatility flags, rates/credit/liquidity)
  * engine (A/B/C, confidence buckets, accept vs skip)
  * symbol (top/worst by count and realized return)

Every bucket row carries a sample size + "low_confidence" flag when n is
below `MIN_SAMPLE`. Lift is computed against a per-axis control baseline
(typically the overall mean) so small wins in tiny buckets don't look huge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
import pandas as pd


# Below this we mark the bucket as low-confidence and refuse to rank it.
MIN_SAMPLE: int = 30

# Return column used for PnL analysis. Caller can override.
DEFAULT_RETURN_COL = "fwd_ret_5d"
FALLBACK_RETURN_COLS = ("realized_net_ret", "fwd_ret_5d", "fwd_ret_3d",
                        "fwd_ret_10d", "fwd_ret_1d")


@dataclass
class BucketStats:
    axis: str
    bucket: str
    n: int
    hit_rate: float
    mean_return: float
    median_return: float
    profit_factor: float
    max_drawdown: float
    sharpe_proxy: float
    lift_vs_control: float                  # mean_return − control_mean
    low_confidence: bool
    ci_half_width: float                    # naive 95% CI half-width on mean

    def to_dict(self) -> dict[str, Any]:
        return {
            "axis": self.axis,
            "bucket": self.bucket,
            "n": self.n,
            "hit_rate": _r(self.hit_rate),
            "mean_return": _r(self.mean_return, 6),
            "median_return": _r(self.median_return, 6),
            "profit_factor": _r(self.profit_factor),
            "max_drawdown": _r(self.max_drawdown, 6),
            "sharpe_proxy": _r(self.sharpe_proxy),
            "lift_vs_control": _r(self.lift_vs_control, 6),
            "low_confidence": bool(self.low_confidence),
            "ci_half_width": _r(self.ci_half_width, 6),
        }


@dataclass
class PatternReport:
    n_rows: int
    return_col: str
    control_mean: float
    buckets: list[BucketStats] = field(default_factory=list)
    positive_patterns: list[BucketStats] = field(default_factory=list)
    negative_patterns: list[BucketStats] = field(default_factory=list)
    pattern_warnings: list[str] = field(default_factory=list)
    low_confidence_excluded: int = 0
    min_sample: int = MIN_SAMPLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_rows": self.n_rows,
            "return_col": self.return_col,
            "control_mean": _r(self.control_mean, 6),
            "buckets": [b.to_dict() for b in self.buckets],
            "positive_patterns": [b.to_dict() for b in self.positive_patterns],
            "negative_patterns": [b.to_dict() for b in self.negative_patterns],
            "pattern_warnings": list(self.pattern_warnings),
            "low_confidence_excluded": self.low_confidence_excluded,
            "min_sample": self.min_sample,
        }


def discover_patterns(
    df: pd.DataFrame,
    *,
    return_col: str | None = None,
    min_sample: int = MIN_SAMPLE,
    top_k: int = 5,
) -> PatternReport:
    """Run the full pattern discovery sweep."""
    rc = return_col or _pick_return_col(df)
    if rc is None:
        return PatternReport(
            n_rows=len(df), return_col="", control_mean=0.0,
            buckets=[], pattern_warnings=[
                "no return column available; no patterns computed"
            ],
            min_sample=min_sample,
        )

    work = df.copy()
    work = work.dropna(subset=[rc])
    if work.empty:
        return PatternReport(
            n_rows=0, return_col=rc, control_mean=0.0,
            pattern_warnings=[f"no rows with {rc} populated"],
            min_sample=min_sample,
        )

    control_mean = float(work[rc].mean())

    buckets: list[BucketStats] = []
    buckets.extend(_catalyst_axes(work, rc, control_mean, min_sample))
    buckets.extend(_data_quality_axes(work, rc, control_mean, min_sample))
    buckets.extend(_regime_axes(work, rc, control_mean, min_sample))
    buckets.extend(_engine_axes(work, rc, control_mean, min_sample))
    buckets.extend(_symbol_axes(work, rc, control_mean, min_sample, top_k=top_k))

    trustworthy = [b for b in buckets if not b.low_confidence]
    low_count = len(buckets) - len(trustworthy)

    positives = sorted(
        trustworthy, key=lambda b: b.lift_vs_control, reverse=True,
    )[:top_k]
    negatives = sorted(
        trustworthy, key=lambda b: b.lift_vs_control,
    )[:top_k]

    warnings: list[str] = []
    if low_count > 0:
        warnings.append(
            f"{low_count} buckets excluded from ranking (n<{min_sample})"
        )
    if not positives and not negatives:
        warnings.append("no statistically meaningful patterns found yet")
    if len(work) < 100:
        warnings.append(f"dataset tiny ({len(work)} rows) — treat all findings"
                        " as directional")

    return PatternReport(
        n_rows=len(work),
        return_col=rc,
        control_mean=control_mean,
        buckets=buckets,
        positive_patterns=positives,
        negative_patterns=negatives,
        pattern_warnings=warnings,
        low_confidence_excluded=low_count,
        min_sample=min_sample,
    )


# ---------------------------------------------------------------------------
# axis builders
# ---------------------------------------------------------------------------

def _catalyst_axes(
    df: pd.DataFrame, rc: str, ctrl: float, min_sample: int,
) -> list[BucketStats]:
    out: list[BucketStats] = []
    if "catalyst_score" in df.columns:
        out.extend(_bucket_numeric(
            df, rc, ctrl, min_sample,
            col="catalyst_score", axis="catalyst_score",
            edges=[-0.01, 0.25, 0.5, 0.75, 1.01],
            labels=["low", "mid_low", "mid_high", "high"],
        ))
    if "event_risk_score" in df.columns:
        out.extend(_bucket_numeric(
            df, rc, ctrl, min_sample,
            col="event_risk_score", axis="event_risk_score",
            edges=[-0.01, 0.25, 0.5, 0.75, 1.01],
            labels=["low", "mid_low", "mid_high", "high"],
        ))
    if "has_earnings_soon" in df.columns:
        out.extend(_bucket_bool(
            df, rc, ctrl, min_sample,
            col="has_earnings_soon", axis="earnings_soon",
        ))
    for tp in ("trade_policy_neutral", "trade_policy_reduce",
               "trade_policy_confirm", "trade_policy_block",
               "trade_policy_watch"):
        if tp in df.columns:
            out.extend(_bucket_bool(
                df, rc, ctrl, min_sample,
                col=tp, axis=tp.replace("trade_policy_", "policy_"),
            ))
    return out


def _data_quality_axes(
    df: pd.DataFrame, rc: str, ctrl: float, min_sample: int,
) -> list[BucketStats]:
    out: list[BucketStats] = []
    if "feature_confidence" in df.columns:
        out.extend(_bucket_numeric(
            df, rc, ctrl, min_sample,
            col="feature_confidence", axis="feature_confidence",
            edges=[-0.01, 0.5, 0.75, 0.9, 1.01],
            labels=["low", "mid", "high", "very_high"],
        ))
    if "missing_field_count" in df.columns:
        out.extend(_bucket_threshold(
            df, rc, ctrl, min_sample,
            col="missing_field_count",
            axis="missing_field_count",
            predicates=[
                ("zero", lambda s: s == 0),
                ("any",  lambda s: s > 0),
            ],
        ))
    if "stale_field_count" in df.columns:
        out.extend(_bucket_threshold(
            df, rc, ctrl, min_sample,
            col="stale_field_count", axis="stale_field_count",
            predicates=[
                ("zero", lambda s: s == 0),
                ("any",  lambda s: s > 0),
            ],
        ))
    return out


def _regime_axes(
    df: pd.DataFrame, rc: str, ctrl: float, min_sample: int,
) -> list[BucketStats]:
    out: list[BucketStats] = []
    regime_cols = {
        "regime_stress": "stress",
        "regime_directional": "directional",
        "regime_neutral": "neutral",
    }
    for col, lab in regime_cols.items():
        if col in df.columns:
            out.append(_single_stat(
                df[df[col].astype(bool)], rc, ctrl, min_sample,
                axis="regime", bucket=lab,
            ))
    if "gates_favorable" in df.columns:
        out.extend(_bucket_threshold(
            df, rc, ctrl, min_sample,
            col="gates_favorable", axis="gates_favorable",
            predicates=[
                ("<=1",    lambda s: s <= 1),
                ("2",      lambda s: s == 2),
                (">=3",    lambda s: s >= 3),
            ],
        ))
    for col in ("input_rates_calm", "input_credit_stable",
                "input_liquidity_expanding", "input_vrp_supportive",
                "input_vol_elevated", "input_vol_expanding",
                "input_range_loose"):
        if col in df.columns:
            out.extend(_bucket_bool(
                df, rc, ctrl, min_sample,
                col=col, axis=col.replace("input_", "ctx_"),
            ))
    return out


def _engine_axes(
    df: pd.DataFrame, rc: str, ctrl: float, min_sample: int,
) -> list[BucketStats]:
    out: list[BucketStats] = []
    if "engine" in df.columns:
        for eng in sorted(df["engine"].dropna().unique()):
            sub = df[df["engine"] == eng]
            out.append(_single_stat(
                sub, rc, ctrl, min_sample,
                axis="engine", bucket=str(eng),
            ))
    if "feature_confidence" in df.columns:
        out.extend(_bucket_numeric(
            df, rc, ctrl, min_sample,
            col="feature_confidence", axis="engine_confidence",
            edges=[-0.01, 0.5, 0.75, 1.01],
            labels=["low", "mid", "high"],
        ))
    if "action" in df.columns:
        for action in sorted(df["action"].dropna().unique()):
            sub = df[df["action"] == action]
            out.append(_single_stat(
                sub, rc, ctrl, min_sample,
                axis="action", bucket=str(action),
            ))
    return out


def _symbol_axes(
    df: pd.DataFrame, rc: str, ctrl: float, min_sample: int, top_k: int,
) -> list[BucketStats]:
    out: list[BucketStats] = []
    if "symbol" not in df.columns:
        return out
    counts = df["symbol"].value_counts()
    top_syms = counts.head(top_k).index.tolist()
    for sym in top_syms:
        sub = df[df["symbol"] == sym]
        out.append(_single_stat(
            sub, rc, ctrl, min_sample,
            axis="top_symbol_by_decisions", bucket=str(sym),
        ))
    # Top + bottom by mean return (gated by min_sample)
    per_sym = df.groupby("symbol", observed=True)[rc].agg(
        ["count", "mean"]
    ).reset_index()
    eligible = per_sym[per_sym["count"] >= min_sample]
    if not eligible.empty:
        for sym in eligible.nlargest(top_k, "mean")["symbol"]:
            sub = df[df["symbol"] == sym]
            out.append(_single_stat(
                sub, rc, ctrl, min_sample,
                axis="top_symbol_by_return", bucket=str(sym),
            ))
        for sym in eligible.nsmallest(top_k, "mean")["symbol"]:
            sub = df[df["symbol"] == sym]
            out.append(_single_stat(
                sub, rc, ctrl, min_sample,
                axis="worst_symbol_by_return", bucket=str(sym),
            ))
    return out


# ---------------------------------------------------------------------------
# primitive bucket helpers
# ---------------------------------------------------------------------------

def _bucket_numeric(
    df: pd.DataFrame, rc: str, ctrl: float, min_sample: int,
    *, col: str, axis: str, edges: list[float], labels: list[str],
) -> list[BucketStats]:
    if col not in df.columns:
        return []
    s = df[[col, rc]].dropna()
    if s.empty:
        return []
    s = s.copy()
    s["_b"] = pd.cut(s[col], bins=edges, labels=labels, include_lowest=True)
    out = []
    for lab in labels:
        sub = s[s["_b"] == lab]
        out.append(_stats_from_returns(
            sub[rc], axis=axis, bucket=lab,
            control_mean=ctrl, min_sample=min_sample,
        ))
    return out


def _bucket_bool(
    df: pd.DataFrame, rc: str, ctrl: float, min_sample: int,
    *, col: str, axis: str,
) -> list[BucketStats]:
    out = []
    s = df[[col, rc]].dropna()
    if s.empty:
        return []
    for label, mask in (("true", s[col].astype(bool)),
                         ("false", ~s[col].astype(bool))):
        sub = s[mask][rc]
        out.append(_stats_from_returns(
            sub, axis=axis, bucket=label,
            control_mean=ctrl, min_sample=min_sample,
        ))
    return out


def _bucket_threshold(
    df: pd.DataFrame, rc: str, ctrl: float, min_sample: int,
    *, col: str, axis: str, predicates: Iterable[tuple[str, Any]],
) -> list[BucketStats]:
    out = []
    for label, pred in predicates:
        mask = pred(df[col])
        sub = df.loc[mask, rc].dropna()
        out.append(_stats_from_returns(
            sub, axis=axis, bucket=label,
            control_mean=ctrl, min_sample=min_sample,
        ))
    return out


def _single_stat(
    sub: pd.DataFrame, rc: str, ctrl: float, min_sample: int,
    *, axis: str, bucket: str,
) -> BucketStats:
    return _stats_from_returns(
        sub[rc].dropna() if isinstance(sub, pd.DataFrame) and rc in sub.columns
        else pd.Series(dtype=float),
        axis=axis, bucket=bucket,
        control_mean=ctrl, min_sample=min_sample,
    )


def _stats_from_returns(
    s: pd.Series, *, axis: str, bucket: str,
    control_mean: float, min_sample: int,
) -> BucketStats:
    if s is None or s.empty:
        return BucketStats(
            axis=axis, bucket=bucket, n=0,
            hit_rate=0.0, mean_return=0.0, median_return=0.0,
            profit_factor=0.0, max_drawdown=0.0, sharpe_proxy=0.0,
            lift_vs_control=0.0,
            low_confidence=True, ci_half_width=0.0,
        )
    arr = s.to_numpy(dtype=float)
    n = int(len(arr))
    wins = int((arr > 0).sum())
    losses = int((arr < 0).sum())
    gross_win = float(arr[arr > 0].sum())
    gross_loss = -float(arr[arr < 0].sum())
    pf = gross_win / gross_loss if gross_loss > 1e-9 else float("inf")
    curve = np.cumsum(arr)
    peak = np.maximum.accumulate(curve) if len(curve) else curve
    dd = float(np.min(curve - peak)) if len(curve) else 0.0
    sd = float(np.std(arr, ddof=0))
    mu = float(np.mean(arr))
    sharpe = mu / sd if sd > 1e-9 else 0.0
    ci_half = 1.96 * (sd / (n ** 0.5)) if n > 1 else 0.0
    return BucketStats(
        axis=axis,
        bucket=str(bucket),
        n=n,
        hit_rate=float(wins / n) if n else 0.0,
        mean_return=mu,
        median_return=float(np.median(arr)),
        profit_factor=float(pf if np.isfinite(pf) else 1e9),
        max_drawdown=dd,
        sharpe_proxy=sharpe,
        lift_vs_control=mu - control_mean,
        low_confidence=bool(n < min_sample),
        ci_half_width=ci_half,
    )


def _pick_return_col(df: pd.DataFrame) -> str | None:
    for c in FALLBACK_RETURN_COLS:
        if c in df.columns and df[c].notna().any():
            return c
    return None


def _r(x: float, digits: int = 4) -> float:
    if x is None:
        return 0.0
    try:
        return round(float(x), digits)
    except (TypeError, ValueError):
        return 0.0
