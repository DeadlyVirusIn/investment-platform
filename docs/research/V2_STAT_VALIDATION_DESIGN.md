# V2 Statistical Validation Research Layer — Design (Phase 10A.1)

**Date:** 2026-04-26
**Status:** DESIGN ONLY — awaiting approval before Phase 10A.2 implementation
**Scope:** Pure research module. NO impact on execution, gates, state machine, approval, sizing, or routing.

---

## TL;DR

A new pure-function module `apps/api/src/research/v2_stat_validation.py` that
adds Probability of Backtest Overfitting (PBO via CSCV), Deflated Sharpe
Ratio, and bootstrapped confidence intervals over the existing V2 vs B2
shadow-comparison data. Outputs a JSON sub-bundle. Read-only; informational
only; never feeds back into gate / state-machine / approval logic.

---

## Hard Boundaries (mirror Phase 10 instructions)

| Constraint | Enforcement |
|---|---|
| No live execution change | Module imports stdlib + numpy only; no execution/routing/risk imports |
| No strategy logic change | No imports of `shadow_strategy*`, `engine_b*` |
| No gate / state-machine / approval coupling | No imports of `v2_promotion_gates`, `v2_promotion_state`, `v2_promotion`, models for snapshot/approval rows |
| Read-only | Pure functions; no DB writes; no side effects |
| Deterministic | All randomness via supplied `seed` parameter; default seed exposed as constant |
| Insufficient sample → explicit | Returns `INSUFFICIENT_SAMPLE` flag with reason; never fabricates precision |

Verified after implementation by:
```bash
grep -E "engine_b|shadow_strategy|paper_trade_log|decision_log|paper_shadow_log|v2_promotion_state|v2_promotion_gates|gate_|approval|execute|order|position" apps/api/src/research/v2_stat_validation.py
# expected: only docstring mentions
```

---

## Module Layout

```
apps/api/src/research/v2_stat_validation.py
apps/api/tests/unit/test_v2_stat_validation.py
```

**Single file, single namespace.** No subdirectory split — keeps audit
surface small and the "no leakage" grep simple.

**Optional read-only integration** (Phase 10A.2 second commit):
add `stat_validation` field to `compute_all` bundle output. Field is
informational; gates do NOT consume it.

---

## Public API

```python
# Frozen module constants — same revision-history discipline as gates
DEFAULT_SEED = 20260426
DEFAULT_BOOTSTRAP_REPLICATES = 1000
DEFAULT_CSCV_PARTITIONS = 16          # K in Bailey/López de Prado CSCV
DEFAULT_PBO_OVERFIT_HIGH = 0.50       # PBO ≥ 0.50 → HIGH overfit risk
DEFAULT_PBO_OVERFIT_MEDIUM = 0.25     # 0.25 ≤ PBO < 0.50 → MEDIUM
DEFAULT_DSR_SIGNIFICANCE = 0.95       # DSR p-value > this → significant
DEFAULT_MIN_SAMPLE = 60               # below this → INSUFFICIENT_SAMPLE
DEFAULT_MIN_CSCV_OBSERVATIONS = 200   # CSCV needs more data than mean tests
SCHEMA_VERSION = 1


# Result dataclasses (frozen)

@dataclass(frozen=True)
class CSCVResult:
    pbo_score: float            # ∈ [0, 1]; 0.5 = pure noise; ≤0.25 stable
    overfit_risk: str           # "LOW" | "MEDIUM" | "HIGH" | "INSUFFICIENT_SAMPLE"
    n_partitions: int
    n_trials: int               # number of variants compared
    median_oos_rank_decay: float
    notes: list[str]


@dataclass(frozen=True)
class DeflatedSharpeResult:
    sharpe: float
    deflated_sharpe: float      # adjusted for skew/kurtosis + n_trials
    significance_p: float       # one-sided test
    is_significant: bool
    n_observations: int
    notes: list[str]


@dataclass(frozen=True)
class BootstrapCI:
    point_estimate: float
    ci_low: float
    ci_high: float
    confidence_level: float     # e.g. 0.90
    n_replicates: int
    seed: int


@dataclass(frozen=True)
class StatValidationBundle:
    schema_version: int
    pbo: CSCVResult | None
    deflated_sharpe: DeflatedSharpeResult | None
    bootstrap_ci: dict[str, BootstrapCI]   # keyed by metric name
    warnings: list[str]


# Top-level entry points (pure functions)

def compute_pbo(
    *,
    return_matrix: list[list[float]],   # rows = days, cols = strategy variants
    n_partitions: int = DEFAULT_CSCV_PARTITIONS,
    seed: int = DEFAULT_SEED,
) -> CSCVResult: ...


def compute_deflated_sharpe(
    *,
    returns: list[float],
    n_trials: int = 1,
    annualization_factor: int = 252,
) -> DeflatedSharpeResult: ...


def bootstrap_ci(
    *,
    sample: list[float],
    statistic: Callable[[list[float]], float],
    confidence_level: float = 0.90,
    n_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
    seed: int = DEFAULT_SEED,
) -> BootstrapCI: ...


def compute_stat_validation(
    *,
    b2_returns: list[float],
    v2_returns: list[float],
    divergence_deltas: list[float],
    impact_weighted_terms: list[tuple[float, float]],   # (delta, denom)
    candidate_returns_matrix: list[list[float]] | None = None,
    n_trials: int = 1,
    seed: int = DEFAULT_SEED,
) -> StatValidationBundle:
    """Compute the full validation bundle. Returns INSUFFICIENT_SAMPLE
    flags rather than NaN when input series are too short."""
```

All functions are **pure**. All randomness flows through the `seed`
parameter. Same inputs → same outputs.

---

## Algorithm details

### 1. CSCV / PBO — Bailey & López de Prado (2014)

Given a `T × N` return matrix (T days, N candidate variants — minimum
case is `N=2` comparing B2 vs V2):

1. Split T rows into K equal-sized partitions (K = 16 default; must be
   even). Discard remainder rows.
2. Enumerate the `C(K, K/2)` ways to choose IS half. For each:
   - Compute Sharpe per variant on IS half.
   - Compute Sharpe per variant on OOS half.
   - Find the variant with best IS Sharpe; record its OOS rank `r`.
   - Logit transform: `logit_r = log(r / (N - r + 1))`.
3. PBO = fraction of splits where `logit_r ≤ 0` (best IS performer
   ranks in bottom half OOS).
4. Risk classification:
   - `pbo ≥ 0.50` → HIGH (essentially noise-driven selection)
   - `0.25 ≤ pbo < 0.50` → MEDIUM
   - `pbo < 0.25` → LOW

**Insufficient sample handling:** if `T < DEFAULT_MIN_CSCV_OBSERVATIONS`
or `N < 2`, return `CSCVResult(overfit_risk="INSUFFICIENT_SAMPLE", ...)`
with explanatory note. **Never** fabricate a PBO score from thin data.

**Determinism:** the partition enumeration is exhaustive (no random
sampling); seed only used for tie-breaking in rank computation.

### 2. Deflated Sharpe Ratio — Bailey & López de Prado (2014b)

```
DSR = (SR - E[max SR | n_trials, T]) / σ(max SR | n_trials, T)
```

where `E[max SR]` and `σ(max SR)` come from the maximum-of-N Sharpe
distribution under the null. Uses standard formula with skew/kurtosis
adjustment per Mertens (2002):

```
σ(SR) = sqrt((1 - skew·SR + ((kurt-1)/4)·SR²) / (T-1))
expected_max_SR ≈ sqrt(2·log(N)) - (γ + log(log(N))) / sqrt(2·log(N))
```

Significance: `is_significant = (1 - Φ(DSR)) < (1 - DEFAULT_DSR_SIGNIFICANCE)`.

**Insufficient sample handling:** if `len(returns) < DEFAULT_MIN_SAMPLE`,
return result with `is_significant=False`, note `"INSUFFICIENT_SAMPLE"`,
and `deflated_sharpe=NaN`.

### 3. Bootstrap CI

Standard percentile bootstrap on the supplied sample:

1. Use `numpy.random.default_rng(seed)` for reproducibility.
2. Sample `n_replicates` resamples with replacement.
3. Apply `statistic(resample)` to each.
4. Return percentile CI at supplied confidence level (one-sided
   90% by default — lower bound on edge metrics is the operationally
   relevant figure).

**Block bootstrap** for autocorrelated series (returns) added in a
follow-up phase if needed; v1 uses simple iid percentile bootstrap and
documents this limitation in `warnings`.

**Insufficient sample handling:** if `len(sample) < DEFAULT_MIN_SAMPLE`,
return `BootstrapCI(point_estimate=NaN, ci_low=NaN, ci_high=NaN, ...)`
with note appended to bundle warnings.

### 4. Top-level `compute_stat_validation`

Coordinates the above. Returns `StatValidationBundle` containing:

- `pbo`: `compute_pbo(return_matrix=...)` if matrix supplied, else `None`
- `deflated_sharpe`: on `divergence_deltas` (V2 − B2)
- `bootstrap_ci`:
  - `"avg_return_diff_1d_bps"` over `divergence_deltas × 1e4`
  - `"impact_weighted_edge"` over normalized term ratios
  - `"v2_p99_loss_bps"` over `v2_returns × 1e4` using `numpy.percentile(., 1)` statistic
- `warnings`: aggregated insufficient-sample notes + algorithm caveats

---

## Optional read-only bundle integration

Phase 10A.2 second commit:

```python
# apps/api/src/research/b2_v2_comparison.py — additive only
def compute_all(rows, *, include_stat_validation: bool = False) -> dict:
    bundle = ...        # existing
    if include_stat_validation:
        from apps.api.src.research import v2_stat_validation as sv
        bundle["stat_validation"] = dataclasses.asdict(
            sv.compute_stat_validation(
                b2_returns=..., v2_returns=...,
                divergence_deltas=..., impact_weighted_terms=...,
                seed=sv.DEFAULT_SEED,
            )
        )
        bundle["schema_version"] = 3   # bumped from 2 — additive field
    return bundle
```

`include_stat_validation` defaults to `False`; existing call sites
unaffected. Snapshot job invocation will be added under a Phase 10A.3
sub-step (not in initial scope) so gates remain blind to the new field.

**Audit invariant:** `git grep stat_validation apps/api/src/research/v2_promotion_gates.py apps/api/src/research/v2_promotion_state.py` → zero matches.

---

## Test plan

`apps/api/tests/unit/test_v2_stat_validation.py`:

| Test | What it asserts |
|---|---|
| `test_insufficient_sample_returns_explicit_flag` | `n=10` returns INSUFFICIENT_SAMPLE on PBO + Bootstrap |
| `test_pbo_zero_for_perfectly_consistent_strategy` | Variant with strictly dominant IS+OOS Sharpe → `pbo ≈ 0`, `LOW` |
| `test_pbo_high_for_pure_noise` | Random Gaussian variants → `pbo ≈ 0.5`, `HIGH` |
| `test_pbo_medium_for_partial_overfit` | Synthetic series with overfit pattern → `MEDIUM` |
| `test_deflated_sharpe_below_threshold_for_noise` | Random returns → `is_significant = False` |
| `test_deflated_sharpe_significant_for_real_edge` | Synthetic +5bps mean return → `is_significant = True` |
| `test_deflated_sharpe_n_trials_penalizes_score` | Same series, `n_trials=10` → lower DSR than `n_trials=1` |
| `test_bootstrap_ci_contains_point_estimate` | CI contains the sample mean |
| `test_bootstrap_ci_one_sided_lower_bound_for_edge` | 90% lower bound below mean |
| `test_bootstrap_ci_deterministic_with_seed` | Two runs same seed → identical CI |
| `test_bootstrap_ci_different_seed_produces_different_ci` | Determinism boundary |
| `test_compute_stat_validation_full_bundle` | All sub-results populated when sample sufficient |
| `test_compute_stat_validation_warnings_on_thin_data` | Warnings list non-empty when any sub-test thin |
| `test_no_imports_from_execution_or_governance` | Module-level grep — verifies the audit boundary in code |

All tests deterministic (seeded). No DB. No async. Use `numpy` for the
random generator (already a project dependency for analytics).

---

## Files to be added (Phase 10A.2)

| File | Type | Lines (est.) |
|---|---|---:|
| `apps/api/src/research/v2_stat_validation.py` | NEW | ~400 |
| `apps/api/tests/unit/test_v2_stat_validation.py` | NEW | ~400 |

**Files NOT modified in 10A.2:** zero. Module is fully isolated.

Optional follow-up (separate commit, requires explicit approval):
- `apps/api/src/research/b2_v2_comparison.py` — opt-in `include_stat_validation` parameter on `compute_all`. Strictly additive; default `False`; gate code path untouched.

---

## Acceptance criteria (Phase 10A.2)

1. All 14 unit tests pass deterministically.
2. `pytest --tb=short -p no:randomly` produces identical output across runs.
3. `git grep -E "engine_b|shadow_strategy|paper_trade_log|decision_log|paper_shadow_log|v2_promotion_state|v2_promotion_gates|approval" apps/api/src/research/v2_stat_validation.py` returns zero substantive matches (only docstring mentions allowed).
4. No DB writes, no scheduler edits, no router edits, no model edits.
5. INSUFFICIENT_SAMPLE returned (not NaN-filled) for thin inputs.
6. Snapshot job + comparison API behavior byte-identical (no opt-in flag passed).

---

## What is explicitly out of scope for Phase 10A

- Block bootstrap (autocorrelated series) — research backlog.
- White Reality Check / Hansen SPA — separate module if/when needed.
- Walk-forward validation engine — Phase 10B territory.
- Cross-instrument transfer (QQQ / IWM / EFA / EEM) — separate research project.
- ML — strictly Phase 10C territory.
- Any change to `v2_promotion_gates.py`, `v2_promotion_state.py`, snapshot job behavior, or scheduler.

---

## Final recommendation

After 10A.2 ships and passes review, the next safe phase is **10B.1**
(OOS monitoring report design). Do NOT proceed directly to 10C ML
design until 10B is also reviewed — the OOS monitoring layer surfaces
data quality gaps that should inform ML feature selection.

**Awaiting operator approval to implement Phase 10A.2.**
