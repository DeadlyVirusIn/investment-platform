"""Shadow-mode ML scorer.

Loads historical_label rows for current engine_version, trains a LightGBM
meta-label classifier on the FULL CV window (no lockbox split), caches the
booster + feature list in process memory, and exposes a predict() method
that accepts a mapping of features and returns ml_proba per asset.

Intentionally minimal: no persistence, no registry, no monitoring. Shadow
deployment only — never writes to live production tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from loguru import logger

from apps.api.src.db.models import FactorSnapshot, RegimeSnapshot
from apps.api.src.domain.stock_engine.scoring import (
    MODEL_VERSION,
    composite_score,
)
from apps.ml.dataset import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    load_dataset,
)
from apps.ml.training import LGB_PARAMS, NUM_BOOST_ROUND


@dataclass
class ShadowModel:
    booster: lgb.Booster
    features: list[str]
    engine_version: str


_CACHED_MODEL: ShadowModel | None = None


def get_shadow_model(refresh: bool = False) -> ShadowModel:
    """Lazy-init cached model. Call refresh=True to retrain."""
    global _CACHED_MODEL
    if _CACHED_MODEL is not None and not refresh:
        return _CACHED_MODEL

    logger.info("[shadow_scorer] training shadow model on full CV window")
    bundle = load_dataset()
    X = bundle.df[bundle.features].values
    y = bundle.df[bundle.target].values
    dtr = lgb.Dataset(X, label=y)
    booster = lgb.train(LGB_PARAMS, dtr, num_boost_round=NUM_BOOST_ROUND)
    _CACHED_MODEL = ShadowModel(
        booster=booster,
        features=bundle.features,
        engine_version=MODEL_VERSION,
    )
    logger.info(
        "[shadow_scorer] cached model features={} engine_version={}",
        len(bundle.features), MODEL_VERSION,
    )
    return _CACHED_MODEL


def _build_feature_row(
    f: FactorSnapshot,
    regime: RegimeSnapshot,
    universe_atr_median: Any,
) -> dict[str, float]:
    """Assemble a one-hot feature dict for a single candidate."""
    score = composite_score(f, universe_atr_median)
    row: dict[str, float] = {}

    def _num(v: Any) -> float:
        return float(v) if v is not None else float("nan")

    row["composite_score"] = float(score.composite) if score.composite is not None else float("nan")
    row["confidence"]      = float(score.confidence) if score.confidence is not None else float("nan")
    row["residual_momentum_20d"] = _num(f.residual_momentum_20d)
    row["residual_momentum_60d"] = _num(f.residual_momentum_60d)
    row["sector_relative_rank"]  = _num(f.sector_relative_rank)
    row["trend_strength_20d"]    = _num(f.trend_strength_20d)
    row["price_vs_200sma"]       = _num(f.price_vs_200sma)
    row["atr_percent_14"]        = _num(f.atr_percent_14)
    row["avg_dollar_volume_20d"] = _num(f.avg_dollar_volume_20d)
    row["realized_vol_20d"]      = _num(regime.realized_vol_20d)
    row["atr_pctile_1y"]         = _num(regime.atr_pctile_1y)

    trend = (regime.market_trend or "unknown").lower()
    vol   = (regime.vol_regime or "unknown").lower()
    return row, trend, vol


def predict_proba_for_candidates(
    factor_rows: list[FactorSnapshot],
    regime: RegimeSnapshot,
    universe_atr_median: Any,
) -> dict[str, float]:
    """Return {asset_id: ml_proba} for a list of factor rows under a regime."""
    model = get_shadow_model()
    records: list[dict[str, float]] = []
    asset_ids: list[str] = []
    for f in factor_rows:
        row, trend, vol = _build_feature_row(f, regime, universe_atr_median)
        # One-hot encode the way dataset.py does
        row[f"market_trend_{trend}"] = 1.0
        row[f"vol_regime_{vol}"]     = 1.0
        records.append(row)
        asset_ids.append(f.asset_id)

    df = pd.DataFrame.from_records(records)
    # Align columns to model features, fill missing with 0 (one-hot absence)
    for col in model.features:
        if col not in df.columns:
            df[col] = 0.0
    X = df[model.features].fillna(0.0).values.astype(float)
    probas = model.booster.predict(X)
    return {aid: float(p) for aid, p in zip(asset_ids, probas)}
