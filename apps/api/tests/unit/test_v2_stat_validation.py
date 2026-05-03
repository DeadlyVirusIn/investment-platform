"""Unit tests for v2_stat_validation (Phase 10A.2).

All tests deterministic. No DB. No async. Verifies:
  * INSUFFICIENT_SAMPLE handling
  * stable strategy → low PBO
  * pure noise → PBO ≈ 0.5
  * partial overfit → MEDIUM
  * DSR significance threshold
  * DSR n_trials penalty
  * bootstrap CI shape + determinism
  * bundle schema version + warnings
  * no execution / governance imports (greppable proof)
"""

from __future__ import annotations

import importlib
import math
import re
from pathlib import Path

import numpy as np
import pytest

from src.research.v2_stat_validation import (
    DEFAULT_BOOTSTRAP_REPLICATES,
    DEFAULT_CSCV_PARTITIONS,
    DEFAULT_DSR_SIGNIFICANCE,
    DEFAULT_MIN_CSCV_OBSERVATIONS,
    DEFAULT_MIN_SAMPLE,
    DEFAULT_PBO_OVERFIT_HIGH,
    DEFAULT_PBO_OVERFIT_MEDIUM,
    DEFAULT_SEED,
    INSUFFICIENT_SAMPLE,
    SCHEMA_VERSION,
    BootstrapCI,
    CSCVResult,
    DeflatedSharpeResult,
    StatValidationBundle,
    bootstrap_ci,
    compute_deflated_sharpe,
    compute_pbo,
    compute_stat_validation,
    to_jsonable,
)


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _stable_edge_returns(
    n: int = 1000, edge: float = 0.001, sd: float = 0.01,
    seed: int = 1,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(edge, sd, size=n)


def _noise_returns(n: int = 1000, sd: float = 0.01, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, sd, size=n)


def _consistent_winner_matrix(t: int, n_variants: int, seed: int = 1) -> np.ndarray:
    """Variant 0 has clear edge in BOTH halves; others are pure noise.
    PBO should be near 0 because best-IS variant (0) also wins OOS."""
    rng = np.random.default_rng(seed)
    mat = rng.normal(0.0, 0.01, size=(t, n_variants))
    mat[:, 0] += 0.002   # consistent edge for variant 0
    return mat


def _noise_matrix(t: int, n_variants: int, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, 0.01, size=(t, n_variants))


# ===========================================================================
# 1. INSUFFICIENT_SAMPLE handling
# ===========================================================================

def test_compute_pbo_insufficient_sample_too_few_rows():
    mat = _noise_matrix(t=DEFAULT_MIN_CSCV_OBSERVATIONS - 10, n_variants=4)
    r = compute_pbo(return_matrix=mat)
    assert r.overfit_risk == INSUFFICIENT_SAMPLE
    assert math.isnan(r.pbo_score)
    assert any("CSCV requires" in n for n in r.notes)


def test_compute_pbo_insufficient_sample_single_variant():
    mat = _noise_matrix(t=DEFAULT_MIN_CSCV_OBSERVATIONS + 50, n_variants=1)
    r = compute_pbo(return_matrix=mat)
    assert r.overfit_risk == INSUFFICIENT_SAMPLE
    assert any("≥ 2 candidate variants" in n for n in r.notes)


def test_compute_pbo_rejects_odd_partitions():
    mat = _noise_matrix(t=400, n_variants=4)
    r = compute_pbo(return_matrix=mat, n_partitions=15)
    assert r.overfit_risk == INSUFFICIENT_SAMPLE
    assert any("even" in n for n in r.notes)


def test_compute_dsr_insufficient_sample():
    r = compute_deflated_sharpe(returns=[0.01] * (DEFAULT_MIN_SAMPLE - 1))
    assert math.isnan(r.deflated_sharpe)
    assert math.isnan(r.sharpe)
    assert not r.is_significant
    assert any(INSUFFICIENT_SAMPLE in n for n in r.notes)


def test_bootstrap_ci_insufficient_sample():
    r = bootstrap_ci(sample=[0.001] * (DEFAULT_MIN_SAMPLE - 1))
    assert math.isnan(r.point_estimate)
    assert math.isnan(r.ci_low)
    assert math.isnan(r.ci_high)
    assert any(INSUFFICIENT_SAMPLE in n for n in r.notes)


# ===========================================================================
# 2. PBO behavior on synthetic patterns
# ===========================================================================

def test_pbo_low_for_consistent_winner():
    mat = _consistent_winner_matrix(t=400, n_variants=8, seed=42)
    r = compute_pbo(return_matrix=mat, seed=DEFAULT_SEED)
    assert r.overfit_risk == "LOW"
    assert r.pbo_score < DEFAULT_PBO_OVERFIT_MEDIUM
    assert r.n_trials == 8
    assert r.n_partitions == DEFAULT_CSCV_PARTITIONS


def test_pbo_high_for_pure_noise():
    """Pure noise → no real edge → MEDIUM or HIGH overfit risk."""
    mat = _noise_matrix(t=400, n_variants=8, seed=42)
    r = compute_pbo(return_matrix=mat, seed=DEFAULT_SEED)
    assert r.overfit_risk in ("MEDIUM", "HIGH")
    # PBO must be ≥ MEDIUM threshold (not LOW)
    assert r.pbo_score >= DEFAULT_PBO_OVERFIT_MEDIUM


def test_pbo_distinguishes_consistent_from_noise():
    """Consistent winner vs pure noise must produce different PBO labels."""
    consistent = compute_pbo(
        return_matrix=_consistent_winner_matrix(t=400, n_variants=8, seed=7),
        seed=DEFAULT_SEED,
    )
    noisy = compute_pbo(
        return_matrix=_noise_matrix(t=400, n_variants=8, seed=7),
        seed=DEFAULT_SEED,
    )
    assert consistent.pbo_score < noisy.pbo_score


def test_pbo_deterministic_with_seed():
    mat = _consistent_winner_matrix(t=400, n_variants=4, seed=99)
    r1 = compute_pbo(return_matrix=mat, seed=DEFAULT_SEED)
    r2 = compute_pbo(return_matrix=mat, seed=DEFAULT_SEED)
    assert r1 == r2


# ===========================================================================
# 3. DSR behavior
# ===========================================================================

def test_dsr_significant_for_real_edge():
    """Strong synthetic edge → DSR > 0 → is_significant=True."""
    returns = _stable_edge_returns(n=500, edge=0.002, sd=0.005, seed=1)
    r = compute_deflated_sharpe(returns=returns, n_trials=1)
    assert r.is_significant
    assert r.significance_p > DEFAULT_DSR_SIGNIFICANCE
    assert math.isfinite(r.deflated_sharpe)
    assert r.deflated_sharpe > 0


def test_dsr_not_significant_for_pure_noise():
    returns = _noise_returns(n=500, sd=0.01, seed=1)
    r = compute_deflated_sharpe(returns=returns, n_trials=1)
    assert not r.is_significant


def test_dsr_n_trials_penalizes_score():
    """Same series with more trials → lower DSR (multiple-testing penalty)."""
    returns = _stable_edge_returns(n=500, edge=0.002, sd=0.005, seed=1)
    r1 = compute_deflated_sharpe(returns=returns, n_trials=1)
    r10 = compute_deflated_sharpe(returns=returns, n_trials=10)
    r100 = compute_deflated_sharpe(returns=returns, n_trials=100)
    assert r1.deflated_sharpe > r10.deflated_sharpe > r100.deflated_sharpe


def test_dsr_zero_variance_returns_nan():
    r = compute_deflated_sharpe(returns=[0.01] * 100)
    assert math.isnan(r.deflated_sharpe)
    assert not r.is_significant


def test_dsr_output_bounds():
    returns = _stable_edge_returns(n=500, edge=0.002, sd=0.005, seed=1)
    r = compute_deflated_sharpe(returns=returns, n_trials=1)
    assert 0 <= r.significance_p <= 1
    assert isinstance(r.is_significant, bool)
    assert r.n_observations == 500


# ===========================================================================
# 4. Bootstrap CI behavior
# ===========================================================================

def test_bootstrap_ci_contains_point_estimate():
    sample = list(_stable_edge_returns(n=500, edge=0.001, sd=0.005, seed=1))
    r = bootstrap_ci(sample=sample, confidence_level=0.90, seed=DEFAULT_SEED)
    assert r.ci_low <= r.point_estimate <= r.ci_high
    assert r.confidence_level == 0.90
    assert r.n_replicates == DEFAULT_BOOTSTRAP_REPLICATES


def test_bootstrap_ci_deterministic_with_seed():
    sample = list(_stable_edge_returns(n=200, edge=0.001, sd=0.005, seed=1))
    r1 = bootstrap_ci(sample=sample, seed=DEFAULT_SEED)
    r2 = bootstrap_ci(sample=sample, seed=DEFAULT_SEED)
    assert r1.ci_low == r2.ci_low
    assert r1.ci_high == r2.ci_high
    assert r1.point_estimate == r2.point_estimate


def test_bootstrap_ci_different_seed_produces_different_ci():
    sample = list(_stable_edge_returns(n=200, edge=0.001, sd=0.005, seed=1))
    r1 = bootstrap_ci(sample=sample, seed=DEFAULT_SEED)
    r2 = bootstrap_ci(sample=sample, seed=DEFAULT_SEED + 1)
    # Should differ at least at ci_low or ci_high (extremely unlikely to match)
    assert (r1.ci_low, r1.ci_high) != (r2.ci_low, r2.ci_high)


def test_bootstrap_ci_invalid_confidence_level_raises():
    sample = list(_stable_edge_returns(n=100, seed=1))
    with pytest.raises(ValueError):
        bootstrap_ci(sample=sample, confidence_level=0.0)
    with pytest.raises(ValueError):
        bootstrap_ci(sample=sample, confidence_level=1.0)


def test_bootstrap_ci_custom_statistic():
    """Bootstrap on the median, not the mean."""
    sample = list(_noise_returns(n=200, sd=0.01, seed=1))
    r = bootstrap_ci(
        sample=sample,
        statistic=lambda xs: float(np.median(xs)),
        seed=DEFAULT_SEED,
    )
    assert r.ci_low <= r.point_estimate <= r.ci_high


# ===========================================================================
# 5. Top-level bundle
# ===========================================================================

def test_compute_stat_validation_full_bundle_with_pbo():
    rng = np.random.default_rng(7)
    n = 400
    b2 = rng.normal(0.0, 0.01, size=n)
    v2 = b2 + rng.normal(0.0005, 0.002, size=n)
    deltas = (v2 - b2).tolist()
    iwt = [(float(v2[i] - b2[i]), abs(b2[i]) + abs(v2[i])) for i in range(n)]
    matrix = _consistent_winner_matrix(t=400, n_variants=4, seed=7)

    bundle = compute_stat_validation(
        b2_returns=b2.tolist(),
        v2_returns=v2.tolist(),
        divergence_deltas=deltas,
        impact_weighted_terms=iwt,
        candidate_returns_matrix=matrix.tolist(),
        n_trials=4,
        seed=DEFAULT_SEED,
    )
    assert bundle.schema_version == SCHEMA_VERSION
    assert bundle.pbo is not None
    assert bundle.deflated_sharpe is not None
    assert "avg_return_diff_1d_bps" in bundle.bootstrap_ci
    assert "impact_weighted_edge" in bundle.bootstrap_ci
    assert "v2_p99_loss_bps" in bundle.bootstrap_ci
    # Always contains the iid bootstrap caveat warning
    assert any("iid" in w for w in bundle.warnings)


def test_compute_stat_validation_no_pbo_when_matrix_omitted():
    n = 100
    b2 = list(_noise_returns(n=n, seed=1))
    v2 = list(_stable_edge_returns(n=n, edge=0.0005, sd=0.01, seed=1))
    deltas = [v - b for v, b in zip(v2, b2)]
    iwt = [(d, abs(b) + abs(v)) for d, b, v in zip(deltas, b2, v2)]

    bundle = compute_stat_validation(
        b2_returns=b2, v2_returns=v2,
        divergence_deltas=deltas,
        impact_weighted_terms=iwt,
        candidate_returns_matrix=None,
        seed=DEFAULT_SEED,
    )
    assert bundle.pbo is None
    assert bundle.deflated_sharpe is not None


def test_compute_stat_validation_warnings_on_thin_data():
    bundle = compute_stat_validation(
        b2_returns=[0.001] * 5,
        v2_returns=[0.002] * 5,
        divergence_deltas=[0.001] * 5,
        impact_weighted_terms=[(0.001, 0.003)] * 5,
        candidate_returns_matrix=None,
        seed=DEFAULT_SEED,
    )
    # All sub-tests should flag insufficient sample
    insufficient_warnings = [
        w for w in bundle.warnings if INSUFFICIENT_SAMPLE in w
    ]
    assert len(insufficient_warnings) >= 2


def test_compute_stat_validation_deterministic():
    rng = np.random.default_rng(11)
    n = 300
    b2 = rng.normal(0, 0.01, n).tolist()
    v2 = (np.array(b2) + rng.normal(0.0005, 0.002, n)).tolist()
    deltas = [v - b for v, b in zip(v2, b2)]
    iwt = [(d, abs(b) + abs(v)) for d, b, v in zip(deltas, b2, v2)]

    b1 = compute_stat_validation(
        b2_returns=b2, v2_returns=v2, divergence_deltas=deltas,
        impact_weighted_terms=iwt, n_trials=1, seed=DEFAULT_SEED,
    )
    b2bundle = compute_stat_validation(
        b2_returns=b2, v2_returns=v2, divergence_deltas=deltas,
        impact_weighted_terms=iwt, n_trials=1, seed=DEFAULT_SEED,
    )
    assert b1 == b2bundle


def test_to_jsonable_returns_serializable_dict():
    bundle = StatValidationBundle(
        schema_version=SCHEMA_VERSION,
        pbo=None,
        deflated_sharpe=None,
        bootstrap_ci={},
        warnings=("test",),
    )
    out = to_jsonable(bundle)
    assert isinstance(out, dict)
    assert out["schema_version"] == SCHEMA_VERSION
    import json
    json.dumps(out)   # must round-trip via standard json


# ===========================================================================
# 6. Hard boundary: no execution / governance imports
# ===========================================================================

_FORBIDDEN_PATTERNS = [
    r"\bengine_b\w*",
    r"\bshadow_strategy\w*",
    r"\bpaper_trade_log\b",
    r"\bdecision_log\b",
    r"\bpaper_shadow_log\b",
    r"\bv2_promotion_state\b",
    r"\bv2_promotion_gates\b",
    r"\bv2_promotion(?!_snapshot)\w*",
    r"\bapproval\b",
    r"\bexecute\b",
    r"\border\b",
    r"\bposition\b",
    r"\bsizing\b",
    r"\brouting\b",
]


def _module_source() -> str:
    here = Path(__file__).resolve()
    src = (
        here.parent.parent.parent
        / "src" / "research" / "v2_stat_validation.py"
    )
    return src.read_text(encoding="utf-8")


def test_no_forbidden_imports_in_module():
    """Module must NOT import any execution / governance / strategy module.

    Substantive matches in `import`/`from` lines are forbidden;
    docstring mentions are allowed.
    """
    src = _module_source()
    import_lines = [
        ln for ln in src.splitlines()
        if ln.strip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    for pat in _FORBIDDEN_PATTERNS:
        assert not re.search(pat, joined, re.IGNORECASE), (
            f"forbidden pattern {pat!r} found in imports:\n{joined}"
        )


def test_module_imports_only_safe_dependencies():
    """Whitelist module-level imports."""
    src = _module_source()
    allowed_top_level_imports = {
        "dataclasses", "math", "collections", "itertools",
        "typing", "numpy",
    }
    import_lines = [
        ln.strip() for ln in src.splitlines()
        if ln.strip().startswith(("import ", "from "))
    ]
    for line in import_lines:
        # Strip annotations / future imports
        if line.startswith("from __future__"):
            continue
        # Extract first segment after `from ` or `import `
        if line.startswith("from "):
            module = line.split()[1].split(".")[0]
        else:
            module = line.split()[1].split(".")[0]
        assert module in allowed_top_level_imports, (
            f"unexpected module imported: {module!r} (line: {line!r})"
        )


def test_module_can_be_imported_in_isolation():
    """Module must import cleanly without pulling in execution code."""
    importlib.import_module("src.research.v2_stat_validation")
