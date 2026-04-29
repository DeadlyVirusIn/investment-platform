"""Phase 11U.1 - drift metrics (pure-fn).

Deterministic, side-effect-free computations:
  * PSI (Population Stability Index)
  * KS (Kolmogorov-Smirnov)
  * calibration_delta (per-bin actual-rate delta + max abs)
  * performance_deltas (AUC / Brier / hit-ratio)
  * bucket_lift (SHADOW_HIGH / SHADOW_LOW lift + relative drop)
  * coverage_deltas (rows_scored / missingness / provisional)

NEVER imports broker / live / execution modules. NEVER touches the
database. NEVER reads or writes files. NEVER loads or invokes a model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Sequence


PSI_EPS = 1e-4              # Smoothing for zero-count bins.
PSI_BIN_COUNT_NUMERIC = 10  # Frozen quantile bin count.
OTHER_BIN_LABEL = "OTHER"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class DriftMetricsError(ValueError):
    """Raised on invalid input to a metrics function."""


# ---------------------------------------------------------------------------
# Helpers (pure-fn)
# ---------------------------------------------------------------------------

def _quantile(sorted_vals: Sequence[float], q: float) -> float:
    if not sorted_vals:
        raise DriftMetricsError("cannot compute quantile of empty array")
    if q <= 0.0:
        return float(sorted_vals[0])
    if q >= 1.0:
        return float(sorted_vals[-1])
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_vals[lo])
    frac = pos - lo
    return float(sorted_vals[lo]) * (1 - frac) + float(
        sorted_vals[hi]
    ) * frac


def _numeric_quantile_edges(
    baseline_values: Sequence[float],
    *,
    n_bins: int = PSI_BIN_COUNT_NUMERIC,
) -> list[float]:
    """Build n_bins+1 frozen bin edges from baseline. Edges expanded to
    +/- inf at the ends so recent values outside baseline range still
    fall into the outer bins."""
    cleaned = [float(v) for v in baseline_values if v is not None]
    if not cleaned:
        raise DriftMetricsError(
            "baseline numeric series must be non-empty"
        )
    cleaned.sort()
    qs = [i / n_bins for i in range(1, n_bins)]
    inner = [_quantile(cleaned, q) for q in qs]
    edges = [-math.inf] + inner + [math.inf]
    # If duplicates collapse the bins (constant series), fall back
    # to two inf-bounded bins so PSI degenerates gracefully.
    deduped: list[float] = []
    for e in edges:
        if not deduped or e != deduped[-1]:
            deduped.append(e)
    return deduped


def _bin_index(value: float, edges: Sequence[float]) -> int:
    """Return bin index in [0, len(edges)-2]. Right-open by
    convention except final bin which is right-closed."""
    last = len(edges) - 2
    for i in range(last + 1):
        lo = edges[i]
        hi = edges[i + 1]
        if i == last:
            if lo <= value <= hi:
                return i
        else:
            if lo <= value < hi:
                return i
    # Fallback (NaN, etc.) → last bin
    return last


def _counts_per_bin_numeric(
    values: Sequence[float], edges: Sequence[float],
) -> list[int]:
    counts = [0] * (len(edges) - 1)
    for v in values:
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isnan(f):
            continue
        counts[_bin_index(f, edges)] += 1
    return counts


def _to_pcts(counts: Sequence[int], n: int) -> list[float]:
    if n <= 0:
        return [0.0] * len(counts)
    return [c / n for c in counts]


def _smooth(pct: float) -> float:
    return PSI_EPS if pct <= 0 else pct


# ---------------------------------------------------------------------------
# PSI
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PSIResult:
    psi: float
    n_baseline: int
    n_recent: int
    bins: list[dict]


def psi_numeric(
    baseline: Sequence[float],
    recent: Sequence[float],
    *,
    n_bins: int = PSI_BIN_COUNT_NUMERIC,
) -> PSIResult:
    """PSI for numeric series. Edges built from BASELINE only and
    reused for recent. Returns PSI=0 for identical inputs."""
    edges = _numeric_quantile_edges(baseline, n_bins=n_bins)
    b_counts = _counts_per_bin_numeric(baseline, edges)
    r_counts = _counts_per_bin_numeric(recent, edges)
    n_b = sum(b_counts)
    n_r = sum(r_counts)
    b_pcts = _to_pcts(b_counts, n_b)
    r_pcts = _to_pcts(r_counts, n_r)
    psi_value = 0.0
    bin_rows: list[dict] = []
    for i, (bp, rp) in enumerate(zip(b_pcts, r_pcts)):
        bp_s = _smooth(bp)
        rp_s = _smooth(rp)
        contrib = (rp_s - bp_s) * math.log(rp_s / bp_s)
        psi_value += contrib
        bin_rows.append({
            "bin_index": i,
            "edge_lo": edges[i] if math.isfinite(edges[i]) else None,
            "edge_hi":
                edges[i + 1] if math.isfinite(edges[i + 1]) else None,
            "baseline_pct": round(bp, 6),
            "recent_pct": round(rp, 6),
            "contribution": round(contrib, 6),
        })
    return PSIResult(
        psi=round(psi_value, 6),
        n_baseline=n_b, n_recent=n_r,
        bins=bin_rows,
    )


def psi_boolean(
    baseline: Sequence[bool],
    recent: Sequence[bool],
) -> PSIResult:
    b_counts = [
        sum(1 for v in baseline if v is False),
        sum(1 for v in baseline if v is True),
    ]
    r_counts = [
        sum(1 for v in recent if v is False),
        sum(1 for v in recent if v is True),
    ]
    n_b = sum(b_counts)
    n_r = sum(r_counts)
    b_pcts = _to_pcts(b_counts, n_b)
    r_pcts = _to_pcts(r_counts, n_r)
    psi_value = 0.0
    rows: list[dict] = []
    for i, (bp, rp) in enumerate(zip(b_pcts, r_pcts)):
        bp_s = _smooth(bp)
        rp_s = _smooth(rp)
        contrib = (rp_s - bp_s) * math.log(rp_s / bp_s)
        psi_value += contrib
        rows.append({
            "bin_label": "False" if i == 0 else "True",
            "baseline_pct": round(bp, 6),
            "recent_pct": round(rp, 6),
            "contribution": round(contrib, 6),
        })
    return PSIResult(
        psi=round(psi_value, 6), n_baseline=n_b, n_recent=n_r,
        bins=rows,
    )


def psi_categorical(
    baseline: Sequence[Any],
    recent: Sequence[Any],
) -> PSIResult:
    """Category bins built from BASELINE; unseen categories in recent
    accumulate into one OTHER bin."""
    cats: list[str] = []
    seen: set[str] = set()
    for v in baseline:
        s = str(v)
        if s not in seen:
            seen.add(s)
            cats.append(s)
    cats_sorted = sorted(cats)
    cats_sorted.append(OTHER_BIN_LABEL)

    b_counts = [0] * len(cats_sorted)
    for v in baseline:
        s = str(v)
        if s in cats_sorted[:-1]:
            b_counts[cats_sorted.index(s)] += 1
        else:
            b_counts[-1] += 1
    r_counts = [0] * len(cats_sorted)
    for v in recent:
        s = str(v)
        if s in cats_sorted[:-1]:
            r_counts[cats_sorted.index(s)] += 1
        else:
            r_counts[-1] += 1

    n_b = sum(b_counts)
    n_r = sum(r_counts)
    b_pcts = _to_pcts(b_counts, n_b)
    r_pcts = _to_pcts(r_counts, n_r)
    psi_value = 0.0
    rows: list[dict] = []
    for i, (label, bp, rp) in enumerate(
        zip(cats_sorted, b_pcts, r_pcts)
    ):
        bp_s = _smooth(bp)
        rp_s = _smooth(rp)
        contrib = (rp_s - bp_s) * math.log(rp_s / bp_s)
        psi_value += contrib
        rows.append({
            "bin_label": label,
            "baseline_pct": round(bp, 6),
            "recent_pct": round(rp, 6),
            "contribution": round(contrib, 6),
        })
    return PSIResult(
        psi=round(psi_value, 6), n_baseline=n_b, n_recent=n_r,
        bins=rows,
    )


def psi(
    baseline: Sequence[Any],
    recent: Sequence[Any],
    *,
    kind: str | None = None,
) -> PSIResult:
    """Dispatcher. `kind` ∈ {numeric, boolean, categorical}; auto-
    detected when None based on the first non-None baseline value."""
    if kind is None:
        sample = next((v for v in baseline if v is not None), None)
        if isinstance(sample, bool):
            kind = "boolean"
        elif isinstance(sample, (int, float)):
            kind = "numeric"
        else:
            kind = "categorical"
    if kind == "numeric":
        return psi_numeric(
            [v for v in baseline if v is not None],
            [v for v in recent if v is not None],
        )
    if kind == "boolean":
        return psi_boolean(
            [bool(v) for v in baseline if v is not None],
            [bool(v) for v in recent if v is not None],
        )
    if kind == "categorical":
        return psi_categorical(baseline, recent)
    raise DriftMetricsError(f"unknown kind {kind!r}")


# ---------------------------------------------------------------------------
# KS (numeric only)
# ---------------------------------------------------------------------------

def ks(
    baseline: Sequence[float],
    recent: Sequence[float],
) -> float | None:
    a = sorted(float(v) for v in baseline if v is not None)
    b = sorted(float(v) for v in recent if v is not None)
    if not a or not b:
        return None
    all_xs = sorted(set(a) | set(b))
    n_a = len(a); n_b = len(b)
    max_diff = 0.0
    i = j = 0
    for x in all_xs:
        while i < n_a and a[i] <= x:
            i += 1
        while j < n_b and b[j] <= x:
            j += 1
        diff = abs(i / n_a - j / n_b)
        if diff > max_diff:
            max_diff = diff
    return round(max_diff, 6)


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CalibrationDelta:
    bins: list[dict]
    max_abs_bin_delta: float


def calibration_delta(
    baseline_bins: Sequence[dict],
    recent_bins: Sequence[dict],
) -> CalibrationDelta:
    """Each input element: dict with `bin` + `actual_positive_rate`."""
    by_bin_b: dict[str, float] = {
        str(r["bin"]): float(r["actual_positive_rate"])
        for r in baseline_bins
        if r.get("actual_positive_rate") is not None
    }
    by_bin_r: dict[str, float] = {
        str(r["bin"]): float(r["actual_positive_rate"])
        for r in recent_bins
        if r.get("actual_positive_rate") is not None
    }
    out: list[dict] = []
    max_abs = 0.0
    keys = sorted(set(by_bin_b.keys()) | set(by_bin_r.keys()))
    for k in keys:
        b = by_bin_b.get(k)
        r = by_bin_r.get(k)
        if b is None or r is None:
            out.append({
                "bin": k,
                "baseline_rate": b,
                "recent_rate": r,
                "delta": None,
            })
            continue
        delta = round(r - b, 6)
        out.append({
            "bin": k,
            "baseline_rate": round(b, 6),
            "recent_rate": round(r, 6),
            "delta": delta,
        })
        if abs(delta) > max_abs:
            max_abs = abs(delta)
    return CalibrationDelta(
        bins=out, max_abs_bin_delta=round(max_abs, 6),
    )


# ---------------------------------------------------------------------------
# Performance deltas
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PerformanceDeltas:
    auc_baseline: float | None
    auc_recent: float | None
    auc_delta: float | None
    brier_baseline: float | None
    brier_recent: float | None
    brier_delta: float | None
    hit_ratio_baseline: float | None
    hit_ratio_recent: float | None
    hit_ratio_delta: float | None


def _safe_delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round(b - a, 6)


def performance_deltas(
    baseline_metrics: dict,
    recent_metrics: dict,
) -> PerformanceDeltas:
    def _g(d: dict, k: str) -> float | None:
        v = d.get(k)
        if v is None:
            return None
        if k == "brier_score" and float(v) < 0:
            raise DriftMetricsError("brier_score must be non-negative")
        return float(v)

    ab = _g(baseline_metrics, "auc_macro")
    ar = _g(recent_metrics, "auc_macro")
    bb = _g(baseline_metrics, "brier_score")
    br = _g(recent_metrics, "brier_score")
    hb = _g(baseline_metrics, "hit_ratio")
    hr = _g(recent_metrics, "hit_ratio")
    return PerformanceDeltas(
        auc_baseline=ab, auc_recent=ar,
        auc_delta=_safe_delta(ab, ar),
        brier_baseline=bb, brier_recent=br,
        brier_delta=_safe_delta(bb, br),
        hit_ratio_baseline=hb, hit_ratio_recent=hr,
        hit_ratio_delta=_safe_delta(hb, hr),
    )


# ---------------------------------------------------------------------------
# Bucket lift
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BucketLift:
    baseline_lift: float | None
    recent_lift: float | None
    lift_drop_rel: float | None
    by_bucket: list[dict]


def _lift(rate_high: float | None, rate_low: float | None) -> float | None:
    if rate_high is None or rate_low is None or rate_low <= 0:
        return None
    return round(rate_high / rate_low, 6)


def bucket_lift(
    baseline_buckets: dict,
    recent_buckets: dict,
) -> BucketLift:
    def _rate(d: dict, name: str) -> float | None:
        b = d.get(name)
        if not isinstance(b, dict):
            return None
        v = b.get("actual_positive_rate")
        return None if v is None else float(v)

    def _n(d: dict, name: str) -> int:
        b = d.get(name)
        if not isinstance(b, dict):
            return 0
        return int(b.get("n", 0) or 0)

    rh_b = _rate(baseline_buckets, "SHADOW_HIGH")
    rl_b = _rate(baseline_buckets, "SHADOW_LOW")
    rh_r = _rate(recent_buckets, "SHADOW_HIGH")
    rl_r = _rate(recent_buckets, "SHADOW_LOW")
    base_lift = _lift(rh_b, rl_b)
    rec_lift = _lift(rh_r, rl_r)
    drop_rel: float | None = None
    if base_lift is not None and rec_lift is not None and base_lift > 0:
        drop_rel = round((base_lift - rec_lift) / base_lift, 6)
    by_b = []
    for name in ("SHADOW_LOW", "SHADOW_MID", "SHADOW_HIGH"):
        by_b.append({
            "bucket": name,
            "baseline_n": _n(baseline_buckets, name),
            "recent_n": _n(recent_buckets, name),
            "baseline_rate": _rate(baseline_buckets, name),
            "recent_rate": _rate(recent_buckets, name),
        })
    return BucketLift(
        baseline_lift=base_lift,
        recent_lift=rec_lift,
        lift_drop_rel=drop_rel,
        by_bucket=by_b,
    )


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CoverageDeltas:
    rows_scored_baseline: int
    rows_scored_recent: int
    rows_scored_delta_pct: float | None
    missingness_baseline: float | None
    missingness_recent: float | None
    missingness_delta: float | None
    provisional_baseline: float | None
    provisional_recent: float | None
    provisional_delta: float | None
    outlier_rate_baseline: float | None
    outlier_rate_recent: float | None
    outlier_rate_delta: float | None


def _rate(num: int | None, den: int | None) -> float | None:
    if num is None or not den or den <= 0:
        return None
    return round(num / den, 6)


def coverage_deltas(
    baseline_coverage: dict,
    recent_coverage: dict,
) -> CoverageDeltas:
    bs = int(baseline_coverage.get("rows_scored", 0) or 0)
    rs = int(recent_coverage.get("rows_scored", 0) or 0)
    ds_pct: float | None = None
    if bs > 0:
        ds_pct = round((rs - bs) / bs, 6)

    def _exc(d: dict, key: str) -> int:
        b = d.get("rows_excluded") or {}
        return int(b.get(key, 0) or 0)

    bm = _rate(_exc(baseline_coverage, "missing_features"),
               bs + _exc(baseline_coverage, "missing_features"))
    rm = _rate(_exc(recent_coverage, "missing_features"),
               rs + _exc(recent_coverage, "missing_features"))
    bp = _rate(_exc(baseline_coverage, "is_provisional"),
               bs + _exc(baseline_coverage, "is_provisional"))
    rp = _rate(_exc(recent_coverage, "is_provisional"),
               rs + _exc(recent_coverage, "is_provisional"))
    bo = _rate(_exc(baseline_coverage, "outlier"), bs +
               _exc(baseline_coverage, "outlier"))
    ro = _rate(_exc(recent_coverage, "outlier"), rs +
               _exc(recent_coverage, "outlier"))

    return CoverageDeltas(
        rows_scored_baseline=bs,
        rows_scored_recent=rs,
        rows_scored_delta_pct=ds_pct,
        missingness_baseline=bm,
        missingness_recent=rm,
        missingness_delta=_safe_delta(bm, rm),
        provisional_baseline=bp,
        provisional_recent=rp,
        provisional_delta=_safe_delta(bp, rp),
        outlier_rate_baseline=bo,
        outlier_rate_recent=ro,
        outlier_rate_delta=_safe_delta(bo, ro),
    )
