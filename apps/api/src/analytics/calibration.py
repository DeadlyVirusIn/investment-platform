"""MP2B.1 — pure confidence-calibration math (DB-free, no runtime).

Foundation for "is a confidence score calibrated to realized win
probability?". Operates on item-level pairs:

    pairs = list[(predicted_probability ∈ [0, 1], win_bool)]

Nothing here touches the DB, SQL, scoring, or trading. It is intentionally
unwired — wiring to the MP1A/MP1S attribution links is a LATER step
(MP2B.2), gated on data volume. Calibration is a stronger claim than a
single win-rate, so the threshold here (MIN_CALIBRATION_SAMPLES) is higher
than MP2A's MIN_CLOSES: below it, every function returns
note="insufficient_for_calibration" and NULL metrics — never a number on
thin samples.

Caveat for callers: a 0–100 "conviction" is NOT a trained probability;
mapping conviction/100 → p and calling the result "calibration" measures
discrimination-as-probability, not true calibration. confidence_v2 (already
0–1) is the better-posed calibration target. Document this wherever shown.
"""

from __future__ import annotations

from typing import Any

# Calibration needs far more samples than a single hit-rate. Stricter than
# MP2A's MIN_CLOSES (=10) on purpose; a reliability claim is harder.
MIN_CALIBRATION_SAMPLES = 50

_INSUFFICIENT = "insufficient_for_calibration"


def _clean(pairs: list[tuple[float | None, Any]]) -> list[tuple[float, float]]:
    """Keep only valid (p, y) pairs: p numeric in [0, 1], y → 0.0/1.0.
    Invalid/out-of-range pairs are dropped (pure, no raise)."""
    out: list[tuple[float, float]] = []
    for p, win in pairs:
        if p is None:
            continue
        try:
            pf = float(p)
        except (TypeError, ValueError):
            continue
        if pf < 0.0 or pf > 1.0:
            continue
        out.append((pf, 1.0 if win else 0.0))
    return out


def _bin_index(p: float, n_bins: int) -> int:
    """Equal-width bin index in [0, n_bins-1]. p=1.0 lands in the last bin."""
    idx = int(p * n_bins)
    if idx >= n_bins:
        idx = n_bins - 1
    if idx < 0:
        idx = 0
    return idx


def brier_score(pairs: list[tuple[float | None, Any]]) -> dict[str, Any]:
    """Mean squared error between predicted prob and realized outcome.
    Lower is better; 0 = perfect. Gated below MIN_CALIBRATION_SAMPLES."""
    clean = _clean(pairs)
    n = len(clean)
    if n < MIN_CALIBRATION_SAMPLES:
        return {"brier_score": None, "n": n, "note": _INSUFFICIENT}
    mse = sum((p - y) ** 2 for p, y in clean) / n
    return {"brier_score": round(mse, 6), "n": n, "note": None}


def reliability_bins(
    pairs: list[tuple[float | None, Any]],
    n_bins: int = 10,
) -> dict[str, Any]:
    """Expected-vs-observed reliability table. Each bin reports count,
    mean_predicted, observed_rate, and gap (mean_predicted − observed_rate;
    positive = overconfident). All n_bins are returned; empty bins carry
    null rates. Gated below MIN_CALIBRATION_SAMPLES."""
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    clean = _clean(pairs)
    n = len(clean)
    if n < MIN_CALIBRATION_SAMPLES:
        return {"bins": None, "n": n, "note": _INSUFFICIENT}

    width = 1.0 / n_bins
    acc: list[list[float]] = [[] for _ in range(n_bins)]  # predicted
    obs: list[list[float]] = [[] for _ in range(n_bins)]  # outcomes
    for p, y in clean:
        i = _bin_index(p, n_bins)
        acc[i].append(p)
        obs[i].append(y)

    bins: list[dict[str, Any]] = []
    for i in range(n_bins):
        lo = round(i * width, 4)
        hi = round((i + 1) * width, 4)
        cnt = len(acc[i])
        if cnt == 0:
            bins.append({
                "bin": f"[{lo:.2f},{hi:.2f})",
                "lo": lo, "hi": hi, "count": 0,
                "mean_predicted": None, "observed_rate": None, "gap": None,
            })
        else:
            mp = sum(acc[i]) / cnt
            orate = sum(obs[i]) / cnt
            bins.append({
                "bin": f"[{lo:.2f},{hi:.2f})",
                "lo": lo, "hi": hi, "count": cnt,
                "mean_predicted": round(mp, 6),
                "observed_rate": round(orate, 6),
                "gap": round(mp - orate, 6),
            })
    return {"bins": bins, "n": n, "note": None}


def expected_calibration_error(
    pairs: list[tuple[float | None, Any]],
    n_bins: int = 10,
) -> dict[str, Any]:
    """ECE = Σ (count_b / N) · |mean_predicted_b − observed_rate_b| over
    non-empty bins. 0 = perfectly calibrated. Gated below threshold."""
    rel = reliability_bins(pairs, n_bins=n_bins)
    if rel["note"] == _INSUFFICIENT:
        return {"ece": None, "n": rel["n"], "n_bins": n_bins, "note": _INSUFFICIENT}
    n = rel["n"]
    ece = 0.0
    for b in rel["bins"]:
        if b["count"] == 0:
            continue
        ece += (b["count"] / n) * abs(b["gap"])
    return {"ece": round(ece, 6), "n": n, "n_bins": n_bins, "note": None}


__all__ = [
    "MIN_CALIBRATION_SAMPLES",
    "brier_score",
    "reliability_bins",
    "expected_calibration_error",
]
