"""Phase 11T.2 - shadow_scorer unit tests."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from apps.api.src.ml import shadow_scorer as ss
from apps.api.src.ml.shadow_scorer import (
    BUCKET_EDGES_FROZEN,
    EXCLUDED_REASON_MISSING,
    EXCLUDED_REASON_PROVISIONAL,
    REGRESSION_TRANSFORM,
    SHADOW_HIGH,
    SHADOW_LOW,
    SHADOW_MID,
    ScorerConfig,
    ShadowScorerError,
    assign_bucket,
    regression_to_score,
    score_features_classification,
    score_features_regression,
)


# Module-level stubs so joblib/pickle paths in tests work.
class _StubClassifier:
    classes_ = ["negative", "neutral", "positive"]

    def __init__(self, *, p_pos: float = 0.5):
        self.p_pos = p_pos

    def predict_proba(self, X):
        n = len(X)
        out = np.zeros((n, 3))
        out[:, 0] = (1 - self.p_pos) / 2
        out[:, 1] = (1 - self.p_pos) / 2
        out[:, 2] = self.p_pos
        return out


class _StubRegressor:
    def __init__(self, *, pred: float = 0.0):
        self.pred = pred

    def predict(self, X):
        return np.full(len(X), self.pred, dtype=float)


# ---------------------------------------------------------------------------
# Frozen constants
# ---------------------------------------------------------------------------

def test_bucket_edges_frozen():
    assert BUCKET_EDGES_FROZEN == (0.33, 0.66)


def test_regression_transform_constant_frozen():
    assert REGRESSION_TRANSFORM == "frozen_sigmoid_v1.0.0"


def test_excluded_reason_constants_frozen():
    assert EXCLUDED_REASON_MISSING == "missing_features"
    assert EXCLUDED_REASON_PROVISIONAL == "is_provisional"


# ---------------------------------------------------------------------------
# Bucket assignment
# ---------------------------------------------------------------------------

def test_assign_bucket_low_below_first_edge():
    assert assign_bucket(0.05) == SHADOW_LOW
    assert assign_bucket(0.32999) == SHADOW_LOW


def test_assign_bucket_mid_between_edges():
    assert assign_bucket(0.33) == SHADOW_MID
    assert assign_bucket(0.5) == SHADOW_MID
    assert assign_bucket(0.65999) == SHADOW_MID


def test_assign_bucket_high_at_or_above_second_edge():
    assert assign_bucket(0.66) == SHADOW_HIGH
    assert assign_bucket(0.95) == SHADOW_HIGH


def test_assign_bucket_custom_edges():
    assert assign_bucket(0.4, edges=(0.5, 0.8)) == SHADOW_LOW
    assert assign_bucket(0.6, edges=(0.5, 0.8)) == SHADOW_MID
    assert assign_bucket(0.85, edges=(0.5, 0.8)) == SHADOW_HIGH


# ---------------------------------------------------------------------------
# Regression transform
# ---------------------------------------------------------------------------

def test_regression_to_score_at_median_returns_half():
    assert (
        abs(regression_to_score(0.0, train_median=0.0,
                                train_scale=0.01) - 0.5) < 1e-9
    )


def test_regression_to_score_monotone_increasing():
    a = regression_to_score(0.005, train_median=0.0, train_scale=0.01)
    b = regression_to_score(0.05,  train_median=0.0, train_scale=0.01)
    c = regression_to_score(0.5,   train_median=0.0, train_scale=0.01)
    assert a < b < c <= 1.0


def test_regression_to_score_clips_extreme_z():
    assert regression_to_score(1e6, train_scale=0.01) == 1.0
    assert regression_to_score(-1e6, train_scale=0.01) == 0.0


def test_regression_to_score_handles_zero_scale():
    out = regression_to_score(0.5, train_median=0.0, train_scale=0.0)
    assert 0.0 <= out <= 1.0


# ---------------------------------------------------------------------------
# Score functions
# ---------------------------------------------------------------------------

def test_score_classification_uses_positive_class():
    est = _StubClassifier(p_pos=0.7)
    s = score_features_classification(est, [[1.0]])
    assert abs(s - 0.7) < 1e-9


def test_score_classification_uses_decision_function_when_no_proba():
    class _NoProba:
        classes_ = ["negative", "positive"]

        def decision_function(self, X):
            return np.array([1.0])
    s = score_features_classification(_NoProba(), [[1.0]])
    assert 0.5 < s < 1.0


def test_score_regression_with_default_transform():
    est = _StubRegressor(pred=0.0)
    s = score_features_regression(est, [[1.0]])
    assert abs(s - 0.5) < 1e-9


def test_score_regression_with_train_median_offset():
    est = _StubRegressor(pred=0.05)
    s = score_features_regression(
        est, [[1.0]], train_median=0.0, train_scale=0.01,
    )
    assert s > 0.99   # 5x scale → tail


# ---------------------------------------------------------------------------
# ScorerConfig invariants
# ---------------------------------------------------------------------------

def _cfg(**kw):
    base = dict(
        model_id="x", start=dt.date(2026, 1, 1),
        end=dt.date(2026, 4, 1),
        sources=("research_fast_fill",),
        domain="equity",
        include_provisional=False,
        bucket_edges=BUCKET_EDGES_FROZEN,
        output_dir="reports",
        dry_run=True, commit=False,
    )
    base.update(kw)
    return ScorerConfig(**base)


def test_config_dry_xor_commit():
    with pytest.raises(ValueError, match="mutually exclusive"):
        _cfg(dry_run=True, commit=True)


def test_config_start_must_be_le_end():
    with pytest.raises(ValueError, match="start"):
        _cfg(start=dt.date(2026, 5, 1), end=dt.date(2026, 1, 1))


def test_config_domain_required_choice():
    with pytest.raises(ValueError, match="domain"):
        _cfg(domain="bogus")


def test_config_sources_nonempty():
    with pytest.raises(ValueError, match="sources"):
        _cfg(sources=())


def test_config_bucket_edges_validation():
    with pytest.raises(ValueError, match="bucket_edges"):
        _cfg(bucket_edges=(0.5,))
    with pytest.raises(ValueError, match="bucket_edges"):
        _cfg(bucket_edges=(0.7, 0.3))
    with pytest.raises(ValueError, match="bucket_edges"):
        _cfg(bucket_edges=(0.0, 0.5))
    with pytest.raises(ValueError, match="bucket_edges"):
        _cfg(bucket_edges=(0.5, 1.0))


# ---------------------------------------------------------------------------
# Boundary scans on the source file
# ---------------------------------------------------------------------------

def test_scorer_no_forbidden_imports():
    src = Path(ss.__file__).read_text(encoding="utf-8")
    for tok in (
        "from broker_", "import broker_",
        "from live_", "import live_",
        "from execution_", "import execution_",
        "order_router",
    ):
        assert tok not in src, f"forbidden token {tok!r}"


def test_scorer_no_strict_engine_imports():
    src = Path(ss.__file__).read_text(encoding="utf-8")
    for tok in (
        "data.strategy.engine_a", "data.strategy.engine_b",
        "data.strategy.selector", "data.context.production",
        "options.paper.engine", "options.paper.eval_runner",
        "domain.paper_trading.auto_trader",
        "data.research.fast_fill_runner",
    ):
        assert tok not in src, (
            f"strict-engine module pulled in: {tok!r}"
        )


def test_scorer_no_db_writes():
    src = Path(ss.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "INSERT INTO", "UPDATE ", "DELETE FROM",
        "session.commit",
    ):
        assert forbidden not in src, (
            f"shadow scorer must not write DB: {forbidden!r}"
        )


def test_scorer_no_recommendation_language():
    src = Path(ss.__file__).read_text(encoding="utf-8")
    for pat in (
        r"\brecommend\w*", r"\bsignal\b", r"\bbest\s+trade\b",
        r"\btrade\s+now\b", r"\bplace\s+order\b",
        r"\bauto-?trade\b", r"\bpromote\b", r"\btop\s+pick\b",
    ):
        assert not re.search(pat, src, flags=re.IGNORECASE), (
            f"forbidden pattern {pat!r}"
        )


def test_scorer_does_not_register_into_REGISTRY():
    from apps.worker.src.jobs.registry import REGISTRY
    assert all(
        "shadow" not in k.lower() and "scorer" not in k.lower()
        for k in REGISTRY.keys()
    )


def test_scorer_no_api_router_added_in_main():
    """`apps/api/src/main.py` must not import shadow_scorer / shadow
    report / model_registry — 11T is read-only and stays off the API
    router list."""
    repo_root = Path(__file__).resolve().parents[4]
    main_py = repo_root / "apps" / "api" / "src" / "main.py"
    src = main_py.read_text(encoding="utf-8")
    for tok in ("shadow_scorer", "shadow_scoring", "model_registry"):
        assert tok not in src, (
            f"main.py must not reference 11T: {tok!r}"
        )


def test_scorer_does_not_modify_pickle_or_dataset_files():
    """Source-level guard: the scorer never opens pickle / parquet
    in write mode."""
    src = Path(ss.__file__).read_text(encoding="utf-8")
    for tok in (
        '"wb"', "'wb'",                # binary write
        '"w"', "'w'",                  # text write
        "joblib.dump", "to_parquet", "to_csv",
    ):
        assert tok not in src, (
            f"scorer must be read-only on artifacts: {tok!r}"
        )


# ---------------------------------------------------------------------------
# Pickle load + reject paths
# ---------------------------------------------------------------------------

def test_scorer_rejects_unknown_model_id(tmp_path, monkeypatch):
    reg = tmp_path / "reg.json"
    reg.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(
        "apps.api.src.ml.model_registry.REGISTRY_PATH",
        reg,
    )
    cfg = _cfg(model_id="not-in-registry")
    with pytest.raises(ShadowScorerError, match="not in registry"):
        ss.run(cfg, registry_path=reg)


def test_scorer_rejects_non_shadow_status(tmp_path, monkeypatch):
    reg = tmp_path / "reg.json"
    reg.write_text(
        json.dumps([{
            "model_id": "x",
            "status": "promoted",   # not shadow_only
            "artifact_path": str(tmp_path / "missing.pkl"),
        }]),
        encoding="utf-8",
    )
    cfg = _cfg(model_id="x")
    with pytest.raises(ShadowScorerError, match="shadow_only"):
        ss.run(cfg, registry_path=reg)
