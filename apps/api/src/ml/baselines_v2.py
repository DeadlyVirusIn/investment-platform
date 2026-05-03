"""Phase ML-2 — improved rule-based baselines.

Augments `baselines.py` with 5 richer baselines that exercise the new
reliability + catalyst signal. Keeps the same `BaselineResult` shape so the
report card can render both sets uniformly.

These baselines are RECOMMENDATIONS. They are NOT auto-deployed. The paper
pipeline still runs with Engines A + B only.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from apps.api.src.ml.baselines import BaselineResult, _score_block


# Threshold grids we sweep for the report. Kept small + deterministic.
CATALYST_RISK_THRESHOLDS = (0.50, 0.70)
DATA_CONFIDENCE_THRESHOLDS = (0.5, 0.6, 0.7, 0.8)
ENGINE_CONFIDENCE_THRESHOLDS = (0.0, 0.3, 0.5, 0.7)


def run_improved_baselines(
    df: pd.DataFrame,
    *,
    label_col: str = "fwd_ret_5d",
) -> list[BaselineResult]:
    """All five new baselines + threshold sweeps."""
    if label_col not in df.columns:
        return []
    work = df.dropna(subset=[label_col]).copy()
    if work.empty:
        return []

    results: list[BaselineResult] = []
    results.extend(_catalyst_risk_overlay(work, label_col))
    results.extend(_data_confidence_filter(work, label_col))
    results.extend(_regime_gate(work, label_col))
    results.extend(_hybrid_conservative(work, label_col))
    results.extend(_symbol_quality_penalty(work, label_col))
    return results


# --------------------------------------------------------------- 1. catalyst --

def _catalyst_risk_overlay(df: pd.DataFrame, label_col: str) -> list[BaselineResult]:
    out = []
    has_event = df.get("has_earnings_soon",
                        pd.Series(False, index=df.index)).astype(bool)
    risk = df.get("event_risk_score",
                   pd.Series(0.0, index=df.index)).fillna(0.0)
    for thr in CATALYST_RISK_THRESHOLDS:
        # Accept = (no earnings soon) OR (event_risk below thr)
        accept_mask = (~has_event) | (risk < thr)
        out.append(_block_from_mask(
            df[label_col], accept_mask,
            name=f"v2_catalyst_overlay@{thr:.2f}",
            threshold=thr,
            notes=(
                f"reject if has_earnings_soon AND event_risk≥{thr:.2f}"
            ),
        ))
    return out


# --------------------------------------------------------- 2. data confidence --

def _data_confidence_filter(df: pd.DataFrame, label_col: str) -> list[BaselineResult]:
    out = []
    conf = df.get("feature_confidence",
                    pd.Series(1.0, index=df.index)).fillna(0.0)
    for thr in DATA_CONFIDENCE_THRESHOLDS:
        accept_mask = conf >= thr
        out.append(_block_from_mask(
            df[label_col], accept_mask,
            name=f"v2_data_conf@{thr:.2f}",
            threshold=thr,
            notes=f"accept iff feature_confidence ≥ {thr:.2f}",
        ))
    return out


# ----------------------------------------------------------------- 3. regime --

def _regime_gate(df: pd.DataFrame, label_col: str) -> list[BaselineResult]:
    out = []
    if "gates_favorable" in df.columns:
        g = df["gates_favorable"].fillna(0)
        for min_g in (2, 3):
            accept_mask = g >= min_g
            out.append(_block_from_mask(
                df[label_col], accept_mask,
                name=f"v2_regime_gate>={min_g}",
                threshold=float(min_g),
                notes=f"accept iff gates_favorable ≥ {min_g}",
            ))
    # Per-regime breakdown — simple mean-of-returns snapshot
    for col, label in (("regime_stress", "stress"),
                       ("regime_directional", "directional"),
                       ("regime_neutral", "neutral")):
        if col in df.columns:
            accept_mask = df[col].astype(bool)
            out.append(_block_from_mask(
                df[label_col], accept_mask,
                name=f"v2_only_regime_{label}",
                threshold=0.0,
                notes=f"only trades in {label} regime",
            ))
    return out


# ------------------------------------------------------- 4. hybrid conservative

def _hybrid_conservative(df: pd.DataFrame, label_col: str) -> list[BaselineResult]:
    conf = df.get("feature_confidence",
                    pd.Series(1.0, index=df.index)).fillna(0.0)
    risk = df.get("event_risk_score",
                   pd.Series(0.0, index=df.index)).fillna(0.0)
    gates = df.get("gates_favorable",
                    pd.Series(0, index=df.index)).fillna(0)
    # Most conservative combination
    accept_mask = (conf >= 0.7) & (risk < 0.5) & (gates >= 2)
    return [_block_from_mask(
        df[label_col], accept_mask,
        name="v2_hybrid_conservative",
        threshold=0.0,
        notes=("accept iff feature_confidence≥0.7 AND event_risk<0.5 "
               "AND gates_favorable≥2"),
    )]


# --------------------------------------------------- 5. symbol quality penalty

def _symbol_quality_penalty(df: pd.DataFrame, label_col: str) -> list[BaselineResult]:
    if "symbol" not in df.columns:
        return []
    # Rolling per-symbol mean without lookahead — we use an expanding *prior*
    # mean computed on rows strictly before each index by date order.
    if "as_of_date" in df.columns:
        sorted_df = df.sort_values("as_of_date").copy()
    else:
        sorted_df = df.copy()
    sorted_df["_prior_mean"] = (
        sorted_df.groupby("symbol")[label_col]
                 .transform(lambda s: s.shift(1).expanding(min_periods=5).mean())
    )
    # Reject when prior mean is negative (underperforming symbol)
    prior = sorted_df["_prior_mean"]
    accept_mask = (prior.isna()) | (prior >= 0.0)   # keep unknown symbols
    # Align back with original index
    accept_mask = accept_mask.reindex(df.index, fill_value=True)
    return [_block_from_mask(
        df[label_col], accept_mask,
        name="v2_symbol_quality_penalty",
        threshold=0.0,
        notes=("reject symbols with ≥5 prior observations AND "
               "negative expanding mean return"),
    )]


# ------------------------------------------------------ helpers --------------

def _block_from_mask(
    returns: pd.Series, accept_mask: pd.Series,
    *, name: str, threshold: float, notes: str,
) -> BaselineResult:
    accepted = returns[accept_mask.fillna(False)].to_numpy()
    rejected = returns[~accept_mask.fillna(False)].to_numpy()
    return _score_block(
        name=name, threshold=threshold, note=notes,
        accepted_returns=accepted,
        rejected_returns=rejected,
        n_total=int(len(returns)),
    )
