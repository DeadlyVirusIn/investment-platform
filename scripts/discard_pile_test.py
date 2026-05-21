"""Discard-pile test — measure Sharpe + skew + hit_rate of ML-rejected trades.

Hypothesis (Gemini): if ML filter stripped right-tail winners, the DISCARDED
bucket will have Sharpe comparable to or better than the ACCEPTED bucket,
with positive skew. If the ML classifier genuinely separates, DISCARDED
bucket will be materially worse.

Procedure:
  1. Load labels for current engine_version.
  2. Train full-CV model (same hyperparams as apps.ml.training).
  3. Predict proba on lockbox.
  4. Partition lockbox by proba >= threshold vs proba < threshold.
  5. Report Sharpe, skew, hit_rate, trade_count for both buckets.

Usage::

    python -m scripts.discard_pile_test --threshold 0.26
"""

from __future__ import annotations

import argparse
import math
from collections import defaultdict
from statistics import mean, stdev

import lightgbm as lgb
import numpy as np
from loguru import logger

from apps.ml.dataset import load_dataset, split_cv_and_lockbox
from apps.ml.training import LGB_PARAMS, NUM_BOOST_ROUND

TRADING_DAYS = 252


def _sharpe(daily_returns: list[float]) -> float:
    if len(daily_returns) < 5:
        return 0.0
    m = mean(daily_returns)
    s = stdev(daily_returns) if len(daily_returns) > 1 else 0.0
    if s == 0:
        return 0.0
    return (m / s) * math.sqrt(TRADING_DAYS)


def _max_dd_pct(daily_returns: list[float]) -> float:
    if not daily_returns:
        return 0.0
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in daily_returns:
        equity *= (1.0 + r)
        if equity > peak:
            peak = equity
        dd = (equity - peak) / peak
        if dd < max_dd:
            max_dd = dd
    return max_dd * 100.0


def _skew(xs: list[float]) -> float:
    if len(xs) < 3:
        return 0.0
    m = mean(xs)
    s = stdev(xs)
    if s == 0:
        return 0.0
    n = len(xs)
    return (n / ((n - 1) * (n - 2))) * sum(((x - m) / s) ** 3 for x in xs)


def _bucket_stats(df, label: str) -> dict:
    if len(df) == 0:
        return {"label": label, "trades": 0}
    df = df.copy()
    df["_daily_ret"] = (
        df["forward_return_pct"].astype(float) / 100.0
    ) / df["barrier_n_bars"].clip(lower=1)
    # Aggregate to daily mean return (equal-weight across same-day trades)
    by_day: dict = defaultdict(list)
    for _, r in df.iterrows():
        by_day[r["as_of_date"]].append(r["_daily_ret"])
    daily = [sum(v) / max(1, len(v)) for _, v in sorted(by_day.items())]

    raw_returns = df["forward_return_pct"].astype(float).tolist()
    wins = int((df["label"] == 1).sum())
    stops = int((df["label"] == -1).sum())
    timeouts = int((df["label"] == 0).sum())
    hit_rate = wins / len(df) * 100.0

    return {
        "label": label,
        "trades": int(len(df)),
        "days": len(daily),
        "sharpe": round(_sharpe(daily), 4),
        "max_dd_pct": round(_max_dd_pct(daily), 4),
        "hit_rate_pct": round(hit_rate, 2),
        "avg_forward_return_pct": round(float(np.mean(raw_returns)), 4),
        "median_forward_return_pct": round(float(np.median(raw_returns)), 4),
        "skew_forward_return": round(_skew(raw_returns), 4),
        "wins": wins,
        "stops": stops,
        "timeouts": timeouts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Discard-pile diagnostic test.")
    parser.add_argument("--threshold", type=float, default=0.26)
    args = parser.parse_args()

    logger.info("[discard] loading dataset + splitting cv/lockbox")
    bundle = load_dataset()
    cv_df, lockbox_df = split_cv_and_lockbox(bundle.df)

    # Fit single model on full CV (no fold CV — we want one set of probas)
    X_tr = cv_df[bundle.features].values
    y_tr = cv_df[bundle.target].values
    dtr = lgb.Dataset(X_tr, label=y_tr)
    model = lgb.train(LGB_PARAMS, dtr, num_boost_round=NUM_BOOST_ROUND)

    X_lock = lockbox_df[bundle.features].values
    proba = model.predict(X_lock)
    lockbox_df = lockbox_df.copy()
    lockbox_df["_proba"] = proba

    th = args.threshold
    accepted = lockbox_df[lockbox_df["_proba"] >= th]
    discarded = lockbox_df[lockbox_df["_proba"] < th]
    all_rows = lockbox_df

    stats_all = _bucket_stats(all_rows, "ALL (baseline)")
    stats_acc = _bucket_stats(accepted, f"ACCEPTED (proba >= {th})")
    stats_dis = _bucket_stats(discarded, f"DISCARDED (proba < {th})")

    logger.info("")
    logger.info("=" * 84)
    logger.info("DISCARD-PILE TEST — lockbox window")
    logger.info("threshold={} | total lockbox trades={}", th, len(lockbox_df))
    logger.info("=" * 84)

    for s in (stats_all, stats_acc, stats_dis):
        logger.info("")
        logger.info("[{}]", s["label"])
        if s["trades"] == 0:
            logger.info("  (empty)")
            continue
        logger.info("  trades={}  days={}", s["trades"], s["days"])
        logger.info("  sharpe={:.4f}  max_dd={:.2f}%  hit_rate={:.2f}%",
                    s["sharpe"], s["max_dd_pct"], s["hit_rate_pct"])
        logger.info("  avg_ret={:.3f}%  median_ret={:.3f}%  skew={:.3f}",
                    s["avg_forward_return_pct"],
                    s["median_forward_return_pct"],
                    s["skew_forward_return"])
        logger.info("  wins={}  stops={}  timeouts={}",
                    s["wins"], s["stops"], s["timeouts"])

    # Verdict logic
    logger.info("")
    logger.info("=" * 84)
    logger.info("VERDICT")
    logger.info("=" * 84)
    s_acc = stats_acc["sharpe"] if stats_acc["trades"] > 0 else 0.0
    s_dis = stats_dis["sharpe"] if stats_dis["trades"] > 0 else 0.0

    ratio = s_dis / s_acc if s_acc != 0 else float("inf") if s_dis > 0 else 0.0

    logger.info("accepted_sharpe={:.4f}  discarded_sharpe={:.4f}  ratio={:.3f}",
                s_acc, s_dis, ratio)

    if s_dis >= 0.8 * s_acc:
        logger.warning(
            "ANTI-SELECTIVE: Discarded Sharpe >= 0.8 * Accepted. "
            "Classifier stripped winners. Label/deployment problem. "
            "Next: Fix #2 (sizing deployment)."
        )
    elif s_dis < 0.3 * s_acc and stats_dis["hit_rate_pct"] < stats_acc["hit_rate_pct"]:
        logger.info(
            "SEPARATES: Discarded Sharpe < 0.3 * Accepted AND hit rate worse. "
            "Classifier separates signal. Label not dominant problem. "
            "Next: Fix #4 (walk-forward threshold stability)."
        )
    elif s_dis < 1.0 and s_acc < 1.0:
        logger.warning(
            "BOTH WEAK: Both buckets Sharpe < 1.0. Regime drift or no signal OOS. "
            "Next: Fix #3 (retrain with regression label + no vol features)."
        )
    else:
        logger.info(
            "MIXED: Neither extreme. Proceed with Fix #3 (retrain) to clarify."
        )


if __name__ == "__main__":
    main()
