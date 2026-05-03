"""Dataset loader for ML research phase.

Pulls historical_label rows into a pandas DataFrame, one-hot encodes
categorical regime features, and exposes FEATURE_COLUMNS for training.

Lockbox split: final 20% of time range held out, not used for CV.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import HistoricalLabel
from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION

NUMERIC_FEATURES: list[str] = [
    "composite_score",
    "confidence",
    "residual_momentum_20d",
    "residual_momentum_60d",
    "sector_relative_rank",
    "trend_strength_20d",
    "price_vs_200sma",
    "atr_percent_14",
    "avg_dollar_volume_20d",
    "realized_vol_20d",
    "atr_pctile_1y",
]
CATEGORICAL_FEATURES: list[str] = ["market_trend", "vol_regime"]
TARGET_COL = "y_hit"  # binary: 1 if label==1 (hit), 0 otherwise
LOCKBOX_FRACTION = 0.20


@dataclass
class DatasetBundle:
    df: pd.DataFrame
    features: list[str]
    target: str
    group_col: str = "as_of_date"


def _rows_to_df(rows: list[HistoricalLabel]) -> pd.DataFrame:
    records = []
    for r in rows:
        rec = {
            "id": r.id,
            "as_of_date": r.as_of_date,
            "symbol": r.symbol,
            "action": r.action,
            "label": int(r.label),
            "forward_return_pct": float(r.forward_return_pct)
                if r.forward_return_pct is not None else 0.0,
            "barrier_n_bars": int(r.barrier_n_bars)
                if r.barrier_n_bars is not None else 20,
            "sector": r.sector,
            "market_trend": (r.market_trend or "unknown").lower(),
            "vol_regime": (r.vol_regime or "unknown").lower(),
        }
        for col in NUMERIC_FEATURES:
            val = getattr(r, col)
            rec[col] = float(val) if val is not None else np.nan
        records.append(rec)
    df = pd.DataFrame.from_records(records)
    df[TARGET_COL] = (df["label"] == 1).astype(int)
    return df


def _one_hot_encode(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    out = df.copy()
    feat_cols = list(NUMERIC_FEATURES)
    for cat in CATEGORICAL_FEATURES:
        dummies = pd.get_dummies(out[cat], prefix=cat, dummy_na=False)
        out = pd.concat([out, dummies], axis=1)
        feat_cols.extend(dummies.columns.tolist())
    return out, feat_cols


def load_dataset(
    session: Session | None = None,
    engine_version: str = MODEL_VERSION,
    action_filter: set[str] | None = None,
) -> DatasetBundle:
    """Load the full dataset (CV + lockbox) as one DataFrame.

    action_filter defaults to {"Buy"} — meta-label Buy decisions only.
    """
    if action_filter is None:
        action_filter = {"Buy"}

    owned = False
    if session is None:
        session = SessionLocal()
        owned = True
    try:
        stmt = select(HistoricalLabel).where(
            HistoricalLabel.engine_version == engine_version,
            HistoricalLabel.action.in_(list(action_filter)),
        )
        rows = list(session.execute(stmt).scalars().all())
    finally:
        if owned:
            session.close()

    logger.info(
        "[dataset] loaded rows={} engine_version={} actions={}",
        len(rows), engine_version, sorted(action_filter),
    )
    if not rows:
        raise RuntimeError(
            f"no historical_label rows for engine_version={engine_version}"
        )

    df = _rows_to_df(rows)
    df = df.sort_values("as_of_date").reset_index(drop=True)
    df, feat_cols = _one_hot_encode(df)
    logger.info(
        "[dataset] features={} target={} hit_rate={:.2%}",
        len(feat_cols), TARGET_COL, df[TARGET_COL].mean(),
    )
    return DatasetBundle(df=df, features=feat_cols, target=TARGET_COL)


def split_cv_and_lockbox(
    df: pd.DataFrame, lockbox_fraction: float = LOCKBOX_FRACTION,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = sorted(df["as_of_date"].unique())
    if not dates:
        raise ValueError("empty dataset")
    cutoff_idx = int(len(dates) * (1.0 - lockbox_fraction))
    cutoff = dates[cutoff_idx]
    cv = df[df["as_of_date"] < cutoff].copy()
    lockbox = df[df["as_of_date"] >= cutoff].copy()
    logger.info(
        "[dataset] split cv={} lockbox={} cutoff={}",
        len(cv), len(lockbox), cutoff,
    )
    return cv, lockbox
