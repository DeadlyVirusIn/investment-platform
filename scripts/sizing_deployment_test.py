"""Fix #2 — sizing-multiplier deployment test.

Reference: AFML (Lopez de Prado) Ch. 10 — Bet Sizing.
Hypothesis (Opus): model separates per-trade (50% vs 23% hit rate) but hard
filter destroys breadth (Grinold-Kahn IR loss). Converting proba into a
position-weight multiplier (not a filter) should recover Sharpe by
preserving breadth while tilting toward conviction.

Three sizing variants:
  V1 linear:    w = clip(0.5 + 1.4 * (proba - 0.10), 0.5, 1.2)  [no filter]
  V2 tiered:    bottom 20% → 0.5x, middle 60% → 1.0x, top 20% → 1.2x
  V3 scaled:    w = proba / mean(proba)  (mean-1.0 relative weighting)
  V4 soft+linear: V1 scheme but drop rows with proba < 0.10 (tail cut only)

Compared against:
  - BASELINE   (equal-weight all 963)
  - HARD FILTER (current deployment, proba >= 0.26)

Usage::

    python -m scripts.sizing_deployment_test
"""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean, stdev

import lightgbm as lgb
import numpy as np
import pandas as pd
from loguru import logger

from apps.ml.dataset import load_dataset, split_cv_and_lockbox
from apps.ml.training import LGB_PARAMS, NUM_BOOST_ROUND

TRADING_DAYS = 252


def _sharpe(daily: list[float]) -> float:
    if len(daily) < 5:
        return 0.0
    m = mean(daily)
    s = stdev(daily) if len(daily) > 1 else 0.0
    return (m / s) * math.sqrt(TRADING_DAYS) if s else 0.0


def _max_dd_pct(daily: list[float]) -> float:
    if not daily:
        return 0.0
    eq = 1.0
    peak = 1.0
    mdd = 0.0
    for r in daily:
        eq *= (1.0 + r)
        peak = max(peak, eq)
        mdd = min(mdd, (eq - peak) / peak)
    return mdd * 100.0


def _eval(df: pd.DataFrame, label: str) -> dict:
    """Portfolio daily return = weighted mean of per-trade daily returns."""
    if len(df) == 0:
        return {"label": label, "trades": 0}
    df = df.copy()
    df["_daily_ret"] = (
        df["forward_return_pct"].astype(float) / 100.0
    ) / df["barrier_n_bars"].clip(lower=1)

    by_day: dict = defaultdict(lambda: {"r": [], "w": []})
    for _, row in df.iterrows():
        by_day[row["as_of_date"]]["r"].append(float(row["_daily_ret"]))
        by_day[row["as_of_date"]]["w"].append(float(row["_weight"]))

    daily = []
    total_w = 0.0
    total_notional = 0.0
    for _, v in sorted(by_day.items()):
        ws = sum(v["w"])
        if ws == 0:
            continue
        ret = sum(r * w for r, w in zip(v["r"], v["w"])) / ws
        daily.append(ret)
        total_w += ws
        total_notional += ws

    return {
        "label": label,
        "trades": int(len(df)),
        "days_with_trades": len(daily),
        "sharpe": round(_sharpe(daily), 4),
        "max_dd_pct": round(_max_dd_pct(daily), 4),
        "avg_weight": round(float(df["_weight"].mean()), 4),
        "total_notional": round(total_notional, 2),
        "hit_rate_pct": round(
            float((df["label"] == 1).mean() * 100.0), 2,
        ),
    }


def main() -> None:
    logger.info("[sizing] loading dataset + splitting cv/lockbox")
    bundle = load_dataset()
    cv_df, lockbox_df = split_cv_and_lockbox(bundle.df)

    # Train on full CV
    X_tr = cv_df[bundle.features].values
    y_tr = cv_df[bundle.target].values
    model = lgb.train(
        LGB_PARAMS, lgb.Dataset(X_tr, label=y_tr),
        num_boost_round=NUM_BOOST_ROUND,
    )

    X_lock = lockbox_df[bundle.features].values
    proba = model.predict(X_lock)
    lockbox_df = lockbox_df.copy()
    lockbox_df["_proba"] = proba

    # --- Variants ---
    results: list[dict] = []

    # BASELINE
    bdf = lockbox_df.copy()
    bdf["_weight"] = 1.0
    results.append(_eval(bdf, "BASELINE equal-weight (no ML)"))

    # HARD FILTER (current deployment)
    hf = lockbox_df[lockbox_df["_proba"] >= 0.26].copy()
    hf["_weight"] = 1.0
    results.append(_eval(hf, "HARD FILTER proba>=0.26 (current)"))

    # V1: linear sizing, no filter
    v1 = lockbox_df.copy()
    v1["_weight"] = np.clip(0.5 + 1.4 * (v1["_proba"] - 0.10), 0.5, 1.2)
    results.append(_eval(v1, "V1 linear sizing [0.5..1.2], no filter"))

    # V2: quantile tiered
    v2 = lockbox_df.copy()
    q20, q80 = np.quantile(v2["_proba"], [0.20, 0.80])
    v2["_weight"] = np.where(
        v2["_proba"] <= q20, 0.5,
        np.where(v2["_proba"] >= q80, 1.2, 1.0),
    )
    results.append(_eval(v2, f"V2 tiered [q20={q20:.3f},q80={q80:.3f}]"))

    # V3: relative (mean-1.0)
    v3 = lockbox_df.copy()
    mp = v3["_proba"].mean()
    v3["_weight"] = np.clip(v3["_proba"] / mp, 0.3, 2.0) if mp > 0 else 1.0
    results.append(_eval(v3, f"V3 relative proba/mean={mp:.3f}"))

    # V4: soft filter (drop bottom 10%) + linear sizing
    v4 = lockbox_df[lockbox_df["_proba"] >= 0.10].copy()
    v4["_weight"] = np.clip(0.5 + 1.4 * (v4["_proba"] - 0.10), 0.5, 1.2)
    results.append(_eval(v4, "V4 soft-cut proba>=0.10 + linear sizing"))

    # --- Report ---
    logger.info("")
    logger.info("=" * 92)
    logger.info("SIZING DEPLOYMENT TEST — lockbox {} rows", len(lockbox_df))
    logger.info("=" * 92)
    hdr = (
        f"{'Variant':<44s} {'trades':>7s} {'days':>5s} "
        f"{'sharpe':>8s} {'max_dd%':>9s} {'avg_w':>7s} {'hit%':>6s}"
    )
    logger.info(hdr)
    logger.info("-" * 92)
    baseline_sharpe = results[0]["sharpe"]
    for r in results:
        if r["trades"] == 0:
            continue
        uplift = r["sharpe"] - baseline_sharpe
        logger.info(
            "{:<44s} {:>7d} {:>5d} {:>8.4f} {:>9.4f} {:>7.4f} {:>6.2f}  Δ={:+.4f}",
            r["label"][:44], r["trades"], r["days_with_trades"],
            r["sharpe"], r["max_dd_pct"], r["avg_weight"],
            r["hit_rate_pct"], uplift,
        )

    # Winner
    non_baseline = results[1:]
    best = max(non_baseline, key=lambda r: r["sharpe"])
    logger.info("")
    logger.info("BEST variant: {} sharpe={:.4f} Δbaseline={:+.4f}",
                best["label"], best["sharpe"], best["sharpe"] - baseline_sharpe)
    if best["sharpe"] > baseline_sharpe + 0.3:
        logger.info("RESULT: sizing deployment BEATS baseline — uplift ≥ +0.3 ✓")
    elif best["sharpe"] > baseline_sharpe:
        logger.info("RESULT: marginal improvement — uplift < +0.3, inconclusive")
    else:
        logger.warning("RESULT: no sizing variant beats baseline")


if __name__ == "__main__":
    main()
