"""V2 statistical-validation research layer (Phase 10A.2).

Pure functions. No DB. No side effects. Deterministic with supplied seed.
NEVER imports any execution / routing / risk / approval / governance /
strategy module. Read-only research surface only.

Implements:
  * Probability of Backtest Overfitting (PBO) via Combinatorially
    Symmetric Cross-Validation (CSCV) — Bailey & López de Prado (2014).
  * Deflated Sharpe Ratio with skew/kurtosis adjustment (Mertens 2002)
    + multiple-trials penalty (Bailey & López de Prado 2014b).
  * Percentile bootstrap confidence intervals.
  * Top-level `compute_stat_validation` orchestrator returning
    StatValidationBundle.

INSUFFICIENT_SAMPLE: thin inputs return an explicit flag/note rather
than fabricating precision. NaN is reserved for "computation undefined"
(e.g. zero-variance series), never for "sample too small".

Spec: docs/research/V2_STAT_VALIDATION_DESIGN.md
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# Frozen module constants. Changing any value REQUIRES a revision-history
# entry in V2_STAT_VALIDATION_DESIGN.md. No config-driven tuning.
# ---------------------------------------------------------------------------

DEFAULT_SEED = 20260426
DEFAULT_BOOTSTRAP_REPLICATES = 1000
DEFAULT_CSCV_PARTITIONS = 16          # K (must be even)
DEFAULT_PBO_OVERFIT_HIGH = 0.50       # PBO ≥ 0.50 → HIGH
DEFAULT_PBO_OVERFIT_MEDIUM = 0.25     # 0.25 ≤ PBO < 0.50 → MEDIUM
DEFAULT_DSR_SIGNIFICANCE = 0.95
DEFAULT_MIN_SAMPLE = 60
DEFAULT_MIN_CSCV_OBSERVATIONS = 200
DEFAULT_ANNUALIZATION_FACTOR = 252
DEFAULT_CONFIDENCE_LEVEL = 0.90

SCHEMA_VERSION = 1

# Sentinel for "sample too small to compute defensibly"
INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


# ---------------------------------------------------------------------------
# Result dataclasses (frozen for immutability + safe JSON serialization)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CSCVResult:
    pbo_score: float
    overfit_risk: str
    n_partitions: int
    n_trials: int
    median_oos_rank_decay: float
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DeflatedSharpeResult:
    sharpe: float
    deflated_sharpe: float
    significance_p: float
    is_significant: bool
    n_observations: int
    n_trials: int
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BootstrapCI:
    point_estimate: float
    ci_low: float
    ci_high: float
    confidence_level: float
    n_replicates: int
    seed: int
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class StatValidationBundle:
    schema_version: int
    pbo: CSCVResult | None
    deflated_sharpe: DeflatedSharpeResult | None
    bootstrap_ci: dict[str, BootstrapCI]
    warnings: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_float_array(xs: Sequence[float]) -> np.ndarray:
    arr = np.asarray(list(xs), dtype=float)
    return arr[np.isfinite(arr)]


def _safe_sharpe(rets: np.ndarray, *, annualization: int = 1) -> float:
    """Annualized Sharpe. Returns NaN on zero variance or empty."""
    if rets.size < 2:
        return float("nan")
    mu = float(rets.mean())
    sd = float(rets.std(ddof=1))
    if sd == 0.0 or not math.isfinite(sd):
        return float("nan")
    return (mu / sd) * math.sqrt(annualization)


def _logit(x: float, eps: float = 1e-9) -> float:
    """Logistic logit, clipped to avoid ±inf at 0/1."""
    x = max(eps, min(1.0 - eps, x))
    return math.log(x / (1.0 - x))


# ---------------------------------------------------------------------------
# 1. CSCV / PBO
# ---------------------------------------------------------------------------

def compute_pbo(
    *,
    return_matrix: Sequence[Sequence[float]],
    n_partitions: int = DEFAULT_CSCV_PARTITIONS,
    seed: int = DEFAULT_SEED,
) -> CSCVResult:
    """Probability of Backtest Overfitting via Combinatorially Symmetric
    Cross-Validation.

    return_matrix: T rows × N cols. T = days; N = candidate strategy variants.
                   Each col is the per-day return series of one variant.
    """
    notes: list[str] = []
    arr = np.asarray(return_matrix, dtype=float)
    if arr.ndim != 2:
        return CSCVResult(
            pbo_score=float("nan"),
            overfit_risk=INSUFFICIENT_SAMPLE,
            n_partitions=0, n_trials=0, median_oos_rank_decay=float("nan"),
            notes=("return_matrix must be 2-D (T × N)",),
        )
    t, n = arr.shape

    if n < 2:
        return CSCVResult(
            pbo_score=float("nan"),
            overfit_risk=INSUFFICIENT_SAMPLE,
            n_partitions=int(n_partitions), n_trials=int(n),
            median_oos_rank_decay=float("nan"),
            notes=("CSCV requires ≥ 2 candidate variants",),
        )

    if t < DEFAULT_MIN_CSCV_OBSERVATIONS:
        return CSCVResult(
            pbo_score=float("nan"),
            overfit_risk=INSUFFICIENT_SAMPLE,
            n_partitions=int(n_partitions), n_trials=int(n),
            median_oos_rank_decay=float("nan"),
            notes=(
                f"CSCV requires T ≥ {DEFAULT_MIN_CSCV_OBSERVATIONS}; "
                f"got T = {t}",
            ),
        )

    if n_partitions < 2 or n_partitions % 2 != 0:
        return CSCVResult(
            pbo_score=float("nan"),
            overfit_risk=INSUFFICIENT_SAMPLE,
            n_partitions=int(n_partitions), n_trials=int(n),
            median_oos_rank_decay=float("nan"),
            notes=("n_partitions must be even and ≥ 2",),
        )

    # Slice T into K equal chunks (drop remainder for symmetry)
    chunk = t // n_partitions
    used_t = chunk * n_partitions
    if used_t < t:
        notes.append(
            f"dropped {t - used_t} trailing rows for symmetric partitioning"
        )
    arr = arr[:used_t, :]
    chunks = arr.reshape(n_partitions, chunk, n)   # (K, chunk, N)

    rng = np.random.default_rng(seed)
    half = n_partitions // 2
    partition_indices = list(range(n_partitions))
    splits = list(combinations(partition_indices, half))

    rank_decays: list[float] = []
    pbo_hits = 0
    for is_idx in splits:
        is_set = list(is_idx)
        oos_set = [i for i in partition_indices if i not in is_set]
        is_rets = chunks[is_set].reshape(-1, n)
        oos_rets = chunks[oos_set].reshape(-1, n)

        is_sharpes = np.array([
            _safe_sharpe(is_rets[:, j]) for j in range(n)
        ])
        oos_sharpes = np.array([
            _safe_sharpe(oos_rets[:, j]) for j in range(n)
        ])

        # Replace NaN with -inf so they sort to bottom
        is_sharpes_clean = np.where(np.isnan(is_sharpes), -np.inf, is_sharpes)
        oos_sharpes_clean = np.where(np.isnan(oos_sharpes), -np.inf, oos_sharpes)

        # Tie-break with seeded jitter (deterministic across runs)
        jitter = rng.uniform(-1e-12, 1e-12, size=n)
        best_is = int(np.argmax(is_sharpes_clean + jitter))

        # Rank of best_is in OOS (1 = best)
        oos_with_jitter = oos_sharpes_clean + jitter
        ranking = np.argsort(-oos_with_jitter)   # descending
        rank_pos = int(np.where(ranking == best_is)[0][0]) + 1   # 1-based

        # Normalized rank in [0, 1]; 0 = top, 1 = bottom
        normalized_rank = (rank_pos - 1) / max(1, n - 1)
        # logit transform per Bailey/LdP — relative rank
        relative_rank = (n - rank_pos) / n
        if _logit(relative_rank) <= 0:
            pbo_hits += 1
        rank_decays.append(normalized_rank)

    pbo_score = pbo_hits / len(splits)
    median_decay = float(np.median(rank_decays)) if rank_decays else float("nan")

    if pbo_score >= DEFAULT_PBO_OVERFIT_HIGH:
        risk = "HIGH"
    elif pbo_score >= DEFAULT_PBO_OVERFIT_MEDIUM:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return CSCVResult(
        pbo_score=round(pbo_score, 6),
        overfit_risk=risk,
        n_partitions=int(n_partitions),
        n_trials=int(n),
        median_oos_rank_decay=round(median_decay, 6),
        notes=tuple(notes),
    )


# ---------------------------------------------------------------------------
# 2. Deflated Sharpe Ratio
# ---------------------------------------------------------------------------

def _normal_cdf(x: float) -> float:
    """Φ(x) via math.erf — stdlib, no scipy dep."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _expected_max_sharpe(n_trials: int) -> float:
    """E[max SR] under null for N i.i.d. N(0,1) Sharpe estimates.
    Uses the standard extreme-value approximation (Bailey/LdP 2014b)."""
    if n_trials <= 1:
        return 0.0
    n = float(n_trials)
    gamma = 0.5772156649015329   # Euler-Mascheroni
    log_n = math.log(n)
    if log_n <= 0:
        return 0.0
    return (
        math.sqrt(2.0 * log_n)
        - (gamma + math.log(log_n)) / math.sqrt(2.0 * log_n)
    )


def compute_deflated_sharpe(
    *,
    returns: Sequence[float],
    n_trials: int = 1,
    annualization_factor: int = DEFAULT_ANNUALIZATION_FACTOR,
) -> DeflatedSharpeResult:
    """Deflated Sharpe Ratio with skew/kurtosis adjustment + multi-trials
    penalty.

    `returns` is a per-period (e.g. daily) return series. Sharpe is
    annualized by `annualization_factor` (default 252).
    """
    arr = _to_float_array(returns)
    n = arr.size
    notes: list[str] = []

    if n < DEFAULT_MIN_SAMPLE:
        return DeflatedSharpeResult(
            sharpe=float("nan"),
            deflated_sharpe=float("nan"),
            significance_p=float("nan"),
            is_significant=False,
            n_observations=int(n),
            n_trials=int(n_trials),
            notes=(
                f"{INSUFFICIENT_SAMPLE}: need ≥ {DEFAULT_MIN_SAMPLE} obs; "
                f"got {n}",
            ),
        )

    sharpe = _safe_sharpe(arr, annualization=annualization_factor)
    if not math.isfinite(sharpe):
        return DeflatedSharpeResult(
            sharpe=float("nan"),
            deflated_sharpe=float("nan"),
            significance_p=float("nan"),
            is_significant=False,
            n_observations=int(n),
            n_trials=int(n_trials),
            notes=("zero variance or NaN in returns",),
        )

    # Convert to per-period Sharpe for distributional moments
    sr_period = float(arr.mean()) / float(arr.std(ddof=1))

    # Sample skew + excess kurtosis (Fisher) — guarded against zero std
    mu = float(arr.mean())
    centered = arr - mu
    var = float((centered ** 2).mean())
    if var <= 0:
        return DeflatedSharpeResult(
            sharpe=sharpe, deflated_sharpe=float("nan"),
            significance_p=float("nan"), is_significant=False,
            n_observations=int(n), n_trials=int(n_trials),
            notes=("variance ≤ 0 in returns",),
        )
    std = math.sqrt(var)
    skew = float((centered ** 3).mean() / (std ** 3))
    kurt = float((centered ** 4).mean() / (std ** 4))   # raw kurtosis

    # Mertens (2002) per-period Sharpe variance
    sr_var_per = (
        (1.0 - skew * sr_period + ((kurt - 1.0) / 4.0) * (sr_period ** 2))
        / (n - 1)
    )
    if sr_var_per <= 0 or not math.isfinite(sr_var_per):
        return DeflatedSharpeResult(
            sharpe=sharpe, deflated_sharpe=float("nan"),
            significance_p=float("nan"), is_significant=False,
            n_observations=int(n), n_trials=int(n_trials),
            notes=("non-positive Sharpe variance estimate",),
        )
    sr_se_per = math.sqrt(sr_var_per)

    expected_max = _expected_max_sharpe(n_trials)
    # Compare sr_period (per-period) to expected_max (per-period units)
    dsr = (sr_period - expected_max * sr_se_per) / sr_se_per
    significance_p = _normal_cdf(dsr)
    is_sig = significance_p > DEFAULT_DSR_SIGNIFICANCE

    return DeflatedSharpeResult(
        sharpe=round(sharpe, 6),
        deflated_sharpe=round(dsr, 6),
        significance_p=round(significance_p, 6),
        is_significant=bool(is_sig),
        n_observations=int(n),
        n_trials=int(n_trials),
        notes=tuple(notes),
    )


# ---------------------------------------------------------------------------
# 3. Bootstrap CI
# ---------------------------------------------------------------------------

def bootstrap_ci(
    *,
    sample: Sequence[float],
    statistic: Callable[[Sequence[float]], float] = lambda xs: float(
        np.mean(xs)
    ),
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    n_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
    seed: int = DEFAULT_SEED,
) -> BootstrapCI:
    """Percentile bootstrap CI on a user-supplied statistic.

    Default statistic is the sample mean. `confidence_level` defines a
    two-sided interval; the lower bound is generally the operationally
    relevant edge metric.
    """
    arr = _to_float_array(sample)
    n = arr.size
    notes: list[str] = []

    if n < DEFAULT_MIN_SAMPLE:
        return BootstrapCI(
            point_estimate=float("nan"),
            ci_low=float("nan"), ci_high=float("nan"),
            confidence_level=float(confidence_level),
            n_replicates=int(n_replicates), seed=int(seed),
            notes=(
                f"{INSUFFICIENT_SAMPLE}: need ≥ {DEFAULT_MIN_SAMPLE} obs; "
                f"got {n}",
            ),
        )

    if not (0.0 < confidence_level < 1.0):
        raise ValueError("confidence_level must be in (0, 1)")
    if n_replicates < 100:
        notes.append(
            f"n_replicates={n_replicates} < 100 may be unreliable"
        )

    rng = np.random.default_rng(seed)
    point = float(statistic(arr))
    samples = np.empty(n_replicates, dtype=float)
    for i in range(n_replicates):
        idx = rng.integers(0, n, size=n)
        resample = arr[idx]
        samples[i] = float(statistic(resample))

    alpha = (1.0 - confidence_level) / 2.0
    lo = float(np.quantile(samples, alpha))
    hi = float(np.quantile(samples, 1.0 - alpha))

    return BootstrapCI(
        point_estimate=round(point, 6),
        ci_low=round(lo, 6),
        ci_high=round(hi, 6),
        confidence_level=float(confidence_level),
        n_replicates=int(n_replicates),
        seed=int(seed),
        notes=tuple(notes),
    )


# ---------------------------------------------------------------------------
# 4. Top-level orchestrator
# ---------------------------------------------------------------------------

def _impact_weighted_edge(terms: Sequence[tuple[float, float]]) -> float:
    """sum(delta) / sum(|b2| + |v2|). Returns NaN on zero denominator."""
    if not terms:
        return float("nan")
    sum_delta = 0.0
    sum_abs = 0.0
    for delta, denom in terms:
        sum_delta += float(delta)
        sum_abs += float(denom)
    if sum_abs == 0:
        return float("nan")
    return sum_delta / sum_abs


def compute_stat_validation(
    *,
    b2_returns: Sequence[float],
    v2_returns: Sequence[float],
    divergence_deltas: Sequence[float],
    impact_weighted_terms: Sequence[tuple[float, float]],
    candidate_returns_matrix: Sequence[Sequence[float]] | None = None,
    n_trials: int = 1,
    seed: int = DEFAULT_SEED,
    annualization_factor: int = DEFAULT_ANNUALIZATION_FACTOR,
) -> StatValidationBundle:
    """Full validation bundle. Pure function; deterministic on (seed)."""
    warnings: list[str] = []

    # PBO requires candidate_returns_matrix; otherwise omit
    pbo_result: CSCVResult | None = None
    if candidate_returns_matrix is not None:
        pbo_result = compute_pbo(
            return_matrix=candidate_returns_matrix,
            seed=seed,
        )
        if pbo_result.overfit_risk == INSUFFICIENT_SAMPLE:
            warnings.append(f"pbo: {INSUFFICIENT_SAMPLE}")

    # DSR over divergence_deltas (V2 − B2). n_trials reflects how many
    # variants were compared in selecting V2 (caller's responsibility
    # to supply honest count, NOT the test author).
    dsr_result = compute_deflated_sharpe(
        returns=divergence_deltas,
        n_trials=n_trials,
        annualization_factor=annualization_factor,
    )
    if any(INSUFFICIENT_SAMPLE in n for n in dsr_result.notes):
        warnings.append(f"deflated_sharpe: {INSUFFICIENT_SAMPLE}")

    # Bootstrap CIs on three operationally interesting metrics.
    bootstrap_results: dict[str, BootstrapCI] = {}

    bootstrap_results["avg_return_diff_1d_bps"] = bootstrap_ci(
        sample=[d * 1e4 for d in divergence_deltas],
        statistic=lambda xs: float(np.mean(xs)),
        seed=seed,
    )
    if any(INSUFFICIENT_SAMPLE in n
           for n in bootstrap_results["avg_return_diff_1d_bps"].notes):
        warnings.append(f"bootstrap.avg_return_diff_1d_bps: {INSUFFICIENT_SAMPLE}")

    # Impact-weighted edge bootstrap: resample (delta, denom) pairs
    if impact_weighted_terms:
        terms_arr = np.asarray(impact_weighted_terms, dtype=float)
        if terms_arr.ndim == 2 and terms_arr.shape[0] >= DEFAULT_MIN_SAMPLE:
            rng = np.random.default_rng(seed)
            n_terms = terms_arr.shape[0]
            iwe_samples = np.empty(DEFAULT_BOOTSTRAP_REPLICATES, dtype=float)
            for i in range(DEFAULT_BOOTSTRAP_REPLICATES):
                idx = rng.integers(0, n_terms, size=n_terms)
                resample = terms_arr[idx]
                num = float(resample[:, 0].sum())
                den = float(resample[:, 1].sum())
                iwe_samples[i] = num / den if den != 0 else float("nan")
            iwe_clean = iwe_samples[np.isfinite(iwe_samples)]
            if iwe_clean.size > 0:
                point = _impact_weighted_edge(impact_weighted_terms)
                alpha = (1.0 - DEFAULT_CONFIDENCE_LEVEL) / 2.0
                lo = float(np.quantile(iwe_clean, alpha))
                hi = float(np.quantile(iwe_clean, 1.0 - alpha))
                bootstrap_results["impact_weighted_edge"] = BootstrapCI(
                    point_estimate=round(point, 6),
                    ci_low=round(lo, 6),
                    ci_high=round(hi, 6),
                    confidence_level=DEFAULT_CONFIDENCE_LEVEL,
                    n_replicates=DEFAULT_BOOTSTRAP_REPLICATES,
                    seed=int(seed),
                )
            else:
                bootstrap_results["impact_weighted_edge"] = BootstrapCI(
                    point_estimate=float("nan"),
                    ci_low=float("nan"), ci_high=float("nan"),
                    confidence_level=DEFAULT_CONFIDENCE_LEVEL,
                    n_replicates=DEFAULT_BOOTSTRAP_REPLICATES,
                    seed=int(seed),
                    notes=("all bootstrap denominators were zero",),
                )
                warnings.append("bootstrap.impact_weighted_edge: zero denom")
        else:
            bootstrap_results["impact_weighted_edge"] = BootstrapCI(
                point_estimate=float("nan"),
                ci_low=float("nan"), ci_high=float("nan"),
                confidence_level=DEFAULT_CONFIDENCE_LEVEL,
                n_replicates=DEFAULT_BOOTSTRAP_REPLICATES,
                seed=int(seed),
                notes=(
                    f"{INSUFFICIENT_SAMPLE}: need ≥ {DEFAULT_MIN_SAMPLE} "
                    f"terms; got {terms_arr.shape[0] if terms_arr.ndim == 2 else 0}",
                ),
            )
            warnings.append(f"bootstrap.impact_weighted_edge: {INSUFFICIENT_SAMPLE}")

    # V2 p99 tail loss bootstrap (negative number; lower bound is the
    # operationally relevant figure)
    bootstrap_results["v2_p99_loss_bps"] = bootstrap_ci(
        sample=[r * 1e4 for r in v2_returns],
        statistic=lambda xs: float(np.percentile(xs, 1)),
        seed=seed,
    )
    if any(INSUFFICIENT_SAMPLE in n
           for n in bootstrap_results["v2_p99_loss_bps"].notes):
        warnings.append(f"bootstrap.v2_p99_loss_bps: {INSUFFICIENT_SAMPLE}")

    # iid limitation note
    warnings.append(
        "iid percentile bootstrap; CI widths may understate "
        "uncertainty for autocorrelated return series"
    )

    return StatValidationBundle(
        schema_version=SCHEMA_VERSION,
        pbo=pbo_result,
        deflated_sharpe=dsr_result,
        bootstrap_ci=bootstrap_results,
        warnings=tuple(warnings),
    )


def to_jsonable(bundle: StatValidationBundle) -> dict[str, Any]:
    """Serialize bundle for storage / API exposure. Pure."""
    out = dataclasses.asdict(bundle)
    # bootstrap_ci dict-of-dataclass → dict-of-dict already via asdict
    return out
