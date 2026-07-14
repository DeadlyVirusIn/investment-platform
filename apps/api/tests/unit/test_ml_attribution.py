"""Sprint 2 — LightGBM native attribution: reconciliation + guards.

Trains tiny real LightGBM boosters in-test (fast, seeded) so every pin is
against actual `pred_contrib` behavior, not mocks.
"""

from __future__ import annotations

import datetime as dt
import json

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest

from apps.ml.attribution import (
    ATTRIBUTION_METHOD,
    AttributionError,
    beginner_label,
    beginner_payload,
    compute_attributions,
    feature_schema_version,
    model_version_of,
)

FEATURES = [
    "residual_momentum_20d",
    "atr_percent_14",
    "market_trend_bull",
    "market_trend_bear",
]
NOW = dt.datetime(2026, 7, 9, 12, 0, tzinfo=dt.timezone.utc)


def _train(seed: int = 42, n: int = 400) -> lgb.Booster:
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({
        "residual_momentum_20d": rng.normal(0, 1, n),
        "atr_percent_14": rng.uniform(0.5, 6.0, n),
        "market_trend_bull": rng.integers(0, 2, n).astype(float),
        "market_trend_bear": rng.integers(0, 2, n).astype(float),
    })
    # Monotone construction: momentum and bull-flag help, volatility hurts.
    logit = 1.5 * X["residual_momentum_20d"] - 0.8 * X["atr_percent_14"] \
        + 1.0 * X["market_trend_bull"] + rng.normal(0, 0.3, n)
    y = (logit > logit.median()).astype(int)
    ds = lgb.Dataset(X[FEATURES], label=y)
    return lgb.train(
        {"objective": "binary", "verbosity": -1, "seed": seed,
         "deterministic": True, "num_leaves": 7},
        ds, num_boost_round=25,
    )


@pytest.fixture(scope="module")
def booster() -> lgb.Booster:
    return _train()


def _sample(momentum: float, atr: float, bull: float = 1.0,
            bear: float = 0.0) -> pd.DataFrame:
    return pd.DataFrame([{
        "residual_momentum_20d": momentum,
        "atr_percent_14": atr,
        "market_trend_bull": bull,
        "market_trend_bear": bear,
    }])[FEATURES]


def test_base_plus_contributions_equals_raw(booster: lgb.Booster) -> None:
    X = pd.concat([_sample(2.0, 1.0), _sample(-2.0, 5.0), _sample(0.0, 3.0)])
    records = compute_attributions(booster, X, feature_names=FEATURES, now=NOW)
    for r in records:
        assert abs(r.base_value + sum(c.contribution for c in r.contributions)
                   - r.raw_score) < 1e-6
        # displayed probability is sigmoid(raw) — documented conversion
        assert abs(r.probability - 1 / (1 + np.exp(-r.raw_score))) < 1e-9


def test_positive_and_negative_drivers_detected(booster: lgb.Booster) -> None:
    strong = compute_attributions(
        booster, _sample(2.5, 0.6), feature_names=FEATURES, now=NOW)[0]
    weak = compute_attributions(
        booster, _sample(-2.5, 5.5), feature_names=FEATURES, now=NOW)[0]
    mom_strong = next(c for c in strong.contributions
                      if c.feature == "residual_momentum_20d")
    mom_weak = next(c for c in weak.contributions
                    if c.feature == "residual_momentum_20d")
    assert mom_strong.contribution > 0 and mom_strong.direction == "supporting"
    assert mom_weak.contribution < 0 and mom_weak.direction == "cautionary"
    assert strong.probability > weak.probability


def test_missing_values_still_reconcile(booster: lgb.Booster) -> None:
    X = _sample(1.0, 2.0)
    X.loc[:, "atr_percent_14"] = np.nan          # LightGBM-native missing
    rec = compute_attributions(booster, X, feature_names=FEATURES, now=NOW)[0]
    assert abs(rec.base_value + sum(c.contribution for c in rec.contributions)
               - rec.raw_score) < 1e-6
    atr = next(c for c in rec.contributions if c.feature == "atr_percent_14")
    assert atr.value is None                     # surfaced as missing, not 0


def test_encoded_features_have_beginner_language(booster: lgb.Booster) -> None:
    rec = compute_attributions(
        booster, _sample(1.0, 2.0), feature_names=FEATURES, now=NOW)[0]
    bull = next(c for c in rec.contributions if c.feature == "market_trend_bull")
    assert "market trend" in bull.beginner_label
    assert "bull" in bull.beginner_label


def test_unknown_feature_rejected() -> None:
    with pytest.raises(AttributionError):
        beginner_label("mystery_feature_42")
    b = _train()
    X = _sample(1.0, 2.0)
    X["mystery_feature_42"] = 1.0
    with pytest.raises(AttributionError, match="unexpected features"):
        compute_attributions(b, X, feature_names=FEATURES, now=NOW)


def test_multiple_model_artifacts_distinct_and_reconcile() -> None:
    b1, b2 = _train(seed=42), _train(seed=7)
    assert model_version_of(b1) != model_version_of(b2)
    X = _sample(1.2, 2.2)
    r1 = compute_attributions(b1, X, feature_names=FEATURES, now=NOW)[0]
    r2 = compute_attributions(b2, X, feature_names=FEATURES, now=NOW)[0]
    for r in (r1, r2):
        assert abs(r.base_value + sum(c.contribution for c in r.contributions)
                   - r.raw_score) < 1e-6
    assert r1.model_version != r2.model_version


def test_nan_inf_output_protection(booster: lgb.Booster) -> None:
    class _EvilBooster:
        def predict(self, X, **kw):
            if kw.get("pred_contrib"):
                return np.full((len(X), len(FEATURES) + 1), np.nan)
            return np.zeros(len(X))

        def model_to_string(self):
            return "evil"

    with pytest.raises(AttributionError, match="non-finite"):
        compute_attributions(
            _EvilBooster(), _sample(1.0, 1.0), feature_names=FEATURES, now=NOW)


def test_provenance_fields_present(booster: lgb.Booster) -> None:
    rec = compute_attributions(
        booster, _sample(1.0, 2.0), feature_names=FEATURES, now=NOW)[0]
    assert rec.method == ATTRIBUTION_METHOD
    assert rec.model_version.startswith("lgbm-")
    assert rec.feature_schema_version == feature_schema_version(FEATURES)
    assert rec.inference_at == NOW.isoformat()
    payload = rec.to_dict()
    json.dumps(payload)                          # JSON-safe


def test_beginner_payload_wording_and_shape(booster: lgb.Booster) -> None:
    rec = compute_attributions(
        booster, _sample(2.0, 4.0), feature_names=FEATURES, now=NOW)[0]
    p = beginner_payload(rec, top_k=2)
    assert p["headline"] == "Factors that influenced the model result"
    # No causal promises anywhere OUTSIDE the limitations disclaimer
    # (which legitimately says "not reasons the stock will rise or fall").
    non_disclaimer = {k: v for k, v in p.items() if k != "limitations"}
    encoded = json.dumps(non_disclaimer).lower()
    assert "will rise" not in encoded
    assert p["limitations"]
    assert p["scope_note"].startswith("Attribution of the research")
    assert len(p["supporting"]) <= 2 and len(p["cautionary"]) <= 2
    for row in p["supporting"] + p["cautionary"]:
        assert 0.0 <= row["relative_influence"] <= 1.0
