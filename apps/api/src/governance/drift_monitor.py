"""Drift monitoring — feature / performance / regime drift detection.

Pure functions. NEVER mutate. Output is advisory drift flags consumed
by Ops UI + nightly logs. NEVER triggers retraining or model swap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


PSI_LOW = 0.10
PSI_MED = 0.25
SHARPE_DRIFT_WARN = 0.5      # absolute drop in annualized Sharpe
SHARPE_DRIFT_CRIT = 1.0
REGIME_FREQ_DRIFT = 0.20     # |delta share| triggering regime drift
PERIODS_PER_YEAR = 252


@dataclass
class DriftResult:
    name: str
    severity: str            # OK | WARN | CRITICAL | INSUFFICIENT
    statistic: float | None
    detail: str = ""
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        s = self.statistic
        if isinstance(s, float) and not math.isfinite(s):
            s = None
        elif isinstance(s, float):
            s = round(s, 4)
        return {
            "name": self.name, "severity": self.severity,
            "statistic": s, "detail": self.detail,
            "extras": self.extras,
        }


def _finite(xs: Sequence[float]) -> list[float]:
    return [float(x) for x in xs
            if x is not None and isinstance(x, (int, float))
            and math.isfinite(float(x))]


def _quantile_edges(xs: list[float], n_buckets: int) -> list[float]:
    if not xs:
        return []
    xs_sorted = sorted(xs)
    edges = []
    for i in range(1, n_buckets):
        q = i / n_buckets
        idx = min(len(xs_sorted) - 1,
                  max(0, int(round(q * (len(xs_sorted) - 1)))))
        edges.append(xs_sorted[idx])
    return edges


def _bucketize(xs: list[float], edges: list[float]) -> list[int]:
    counts = [0] * (len(edges) + 1)
    for x in xs:
        placed = False
        for i, e in enumerate(edges):
            if x <= e:
                counts[i] += 1
                placed = True
                break
        if not placed:
            counts[-1] += 1
    return counts


def _psi(baseline: list[float], current: list[float],
        n_buckets: int = 10) -> float:
    if len(baseline) < n_buckets or len(current) < n_buckets:
        return float("nan")
    edges = _quantile_edges(baseline, n_buckets)
    if not edges:
        return float("nan")
    b_counts = _bucketize(baseline, edges)
    c_counts = _bucketize(current, edges)
    b_total = sum(b_counts) or 1
    c_total = sum(c_counts) or 1
    psi = 0.0
    eps = 1e-6
    for bc, cc in zip(b_counts, c_counts):
        b = max(eps, bc / b_total)
        c = max(eps, cc / c_total)
        psi += (c - b) * math.log(c / b)
    return psi


def feature_drift(
    baseline: Sequence[float], current: Sequence[float],
    *, name: str = "feature", n_buckets: int = 10,
) -> DriftResult:
    """PSI-style distribution shift between two windows."""
    b = _finite(baseline)
    c = _finite(current)
    if len(b) < n_buckets or len(c) < n_buckets:
        return DriftResult(
            name=f"feature_drift:{name}",
            severity="INSUFFICIENT", statistic=None,
            detail=f"need >={n_buckets} samples per window "
                   f"(got b={len(b)}, c={len(c)})")
    psi = _psi(b, c, n_buckets=n_buckets)
    if not math.isfinite(psi):
        return DriftResult(
            name=f"feature_drift:{name}",
            severity="INSUFFICIENT", statistic=None,
            detail="psi non-finite")
    if psi >= PSI_MED:
        sev = "CRITICAL"
    elif psi >= PSI_LOW:
        sev = "WARN"
    else:
        sev = "OK"
    return DriftResult(
        name=f"feature_drift:{name}",
        severity=sev, statistic=psi,
        detail=f"PSI={psi:.3f} (warn>={PSI_LOW}, crit>={PSI_MED})",
        extras={"n_baseline": len(b), "n_current": len(c)})


def _sharpe(returns: list[float]) -> float:
    if len(returns) < 2:
        return float("nan")
    mu = sum(returns) / len(returns)
    var = sum((r - mu) ** 2 for r in returns) / max(1, len(returns) - 1)
    sd = math.sqrt(var)
    if sd <= 0:
        return float("nan")
    return (mu / sd) * math.sqrt(PERIODS_PER_YEAR)


def performance_drift(
    baseline_returns: Sequence[float],
    current_returns: Sequence[float],
    *, min_n: int = 20,
) -> DriftResult:
    """Drop in annualized Sharpe across two windows."""
    b = _finite(baseline_returns)
    c = _finite(current_returns)
    if len(b) < min_n or len(c) < min_n:
        return DriftResult(
            name="performance_drift", severity="INSUFFICIENT",
            statistic=None,
            detail=f"need >= {min_n} per window "
                   f"(got b={len(b)}, c={len(c)})")
    s_b = _sharpe(b)
    s_c = _sharpe(c)
    if not (math.isfinite(s_b) and math.isfinite(s_c)):
        return DriftResult(
            name="performance_drift", severity="INSUFFICIENT",
            statistic=None, detail="Sharpe non-finite")
    delta = s_c - s_b
    if delta <= -SHARPE_DRIFT_CRIT:
        sev = "CRITICAL"
    elif delta <= -SHARPE_DRIFT_WARN:
        sev = "WARN"
    else:
        sev = "OK"
    return DriftResult(
        name="performance_drift", severity=sev, statistic=delta,
        detail=f"Sharpe baseline={s_b:.2f} current={s_c:.2f} "
               f"delta={delta:+.2f}",
        extras={"sharpe_baseline": round(s_b, 4),
                "sharpe_current": round(s_c, 4)})


def regime_drift(
    baseline_regimes: Sequence[str],
    current_regimes: Sequence[str],
    *, min_n: int = 10,
) -> DriftResult:
    """Largest |delta share| of any regime between windows."""
    b = [str(r) for r in baseline_regimes if r is not None]
    c = [str(r) for r in current_regimes if r is not None]
    if len(b) < min_n or len(c) < min_n:
        return DriftResult(
            name="regime_drift", severity="INSUFFICIENT",
            statistic=None,
            detail=f"need >= {min_n} per window "
                   f"(got b={len(b)}, c={len(c)})")
    keys = sorted(set(b) | set(c))
    bf = {k: b.count(k) / len(b) for k in keys}
    cf = {k: c.count(k) / len(c) for k in keys}
    deltas = {k: cf[k] - bf[k] for k in keys}
    worst_key = max(keys, key=lambda k: abs(deltas[k]))
    worst_delta = deltas[worst_key]
    abs_delta = abs(worst_delta)
    if abs_delta >= REGIME_FREQ_DRIFT * 1.5:
        sev = "CRITICAL"
    elif abs_delta >= REGIME_FREQ_DRIFT:
        sev = "WARN"
    else:
        sev = "OK"
    return DriftResult(
        name="regime_drift", severity=sev, statistic=worst_delta,
        detail=f"largest shift: {worst_key} {worst_delta:+.2f} "
               f"(baseline {bf[worst_key]:.2f} → "
               f"current {cf[worst_key]:.2f})",
        extras={"baseline_freq": {k: round(v, 3) for k, v in bf.items()},
                "current_freq": {k: round(v, 3) for k, v in cf.items()}})


def aggregate(results: list[DriftResult]) -> dict:
    """Roll up worst severity across drift checks."""
    rank = {"OK": 0, "INSUFFICIENT": 0, "WARN": 1, "CRITICAL": 2}
    worst = "OK"
    for r in results:
        if rank.get(r.severity, 0) > rank[worst]:
            worst = r.severity
    return {
        "overall_severity": worst,
        "results": [r.to_dict() for r in results],
        "any_critical": any(r.severity == "CRITICAL" for r in results),
        "any_warn": any(r.severity == "WARN" for r in results),
    }
