"""Shadow-mode evaluation — 20-30 day rolling comparison, no code changes.

Uses existing V1 sizing (multiplier + normalization to production sum).
For each day in the last N trading days of lockbox:
  - baseline: equal-weight the day's accepted Buys (production path)
  - shadow:   apply ML multiplier, normalize shadow_sum → baseline_sum
  - daily return = weighted mean(forward_return_pct / barrier_n_bars)

Aggregate Sharpe/DD/win_rate/vol, rolling Sharpe (5d/10d), multiplier
distribution, percentile-bucket contribution.
"""

from __future__ import annotations

import argparse
import math
from collections import defaultdict
from decimal import Decimal
from statistics import mean, stdev

import lightgbm as lgb
import numpy as np
import pandas as pd
from loguru import logger

from apps.api.src.domain.ml.sizing import compute_ml_multiplier
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


def _win_rate(daily: list[float]) -> float:
    if not daily:
        return 0.0
    return sum(1 for r in daily if r > 0) / len(daily) * 100.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    logger.info("[eval] loading data + training shadow model")
    bundle = load_dataset()
    cv_df, lockbox_df = split_cv_and_lockbox(bundle.df)
    X_tr = cv_df[bundle.features].values
    y_tr = cv_df[bundle.target].values
    model = lgb.train(
        LGB_PARAMS, lgb.Dataset(X_tr, label=y_tr),
        num_boost_round=NUM_BOOST_ROUND,
    )

    X_lock = lockbox_df[bundle.features].values
    proba = model.predict(X_lock)
    lb = lockbox_df.copy()
    lb["_proba"] = proba
    lb["_daily_ret"] = (
        lb["forward_return_pct"].astype(float) / 100.0
    ) / lb["barrier_n_bars"].clip(lower=1)

    all_days = sorted(lb["as_of_date"].unique())
    window_days = all_days[-args.days:]
    logger.info("[eval] window={} days {} → {}", len(window_days),
                window_days[0], window_days[-1])

    # Per-day metrics
    daily_rows = []
    all_multipliers: list[float] = []
    bucket_returns = {"top20": [], "mid60": [], "bot20": []}

    for d in window_days:
        day = lb[lb["as_of_date"] == d]
        n = len(day)
        if n == 0:
            continue

        # Baseline: equal weight = 1/n per trade
        base_ret = float((day["_daily_ret"].astype(float)).mean())

        # Shadow: multiplier on each trade, normalize to baseline sum
        base_weights = np.ones(n) / n                # sum = 1
        raw_mult = np.array([
            float(compute_ml_multiplier(Decimal(str(p))))
            for p in day["_proba"].tolist()
        ])
        shadow_raw = base_weights * raw_mult
        s_pre = shadow_raw.sum()
        scale = 1.0 / s_pre if s_pre > 0 else 1.0    # normalize sum back to 1.0
        shadow_w = shadow_raw * scale
        shadow_ret = float((day["_daily_ret"].values.astype(float) * shadow_w).sum())

        # Percentile-bucket contribution (shadow only)
        order = np.argsort(-raw_mult)   # high→low by multiplier ≈ by proba
        sorted_day = day.iloc[order].reset_index(drop=True)
        tops = int(max(1, round(n * 0.20)))
        bots = int(max(1, round(n * 0.20)))
        if tops + bots < n:
            bucket_returns["top20"].append(float(sorted_day.iloc[:tops]["_daily_ret"].mean()))
            bucket_returns["mid60"].append(float(sorted_day.iloc[tops:n - bots]["_daily_ret"].mean()))
            bucket_returns["bot20"].append(float(sorted_day.iloc[n - bots:]["_daily_ret"].mean()))
        else:
            bucket_returns["top20"].append(float(sorted_day.iloc[:tops]["_daily_ret"].mean()))
            bucket_returns["bot20"].append(float(sorted_day.iloc[-bots:]["_daily_ret"].mean()))

        all_multipliers.extend(raw_mult.tolist())

        daily_rows.append({
            "date": d,
            "n": n,
            "base_ret": base_ret,
            "shadow_ret": shadow_ret,
            "avg_multiplier": float(raw_mult.mean()),
            "scale_factor": float(scale * s_pre),    # = 1.0 by design (sanity)
        })

    df = pd.DataFrame(daily_rows)

    base_daily = df["base_ret"].tolist()
    shd_daily = df["shadow_ret"].tolist()

    # Aggregates
    agg = {
        "baseline": {
            "sharpe": round(_sharpe(base_daily), 4),
            "max_dd_pct": round(_max_dd_pct(base_daily), 4),
            "ann_return_pct": round(
                (float(np.prod([1 + r for r in base_daily])) ** (TRADING_DAYS / max(1, len(base_daily))) - 1) * 100, 4,
            ),
            "vol_pct": round(stdev(base_daily) * math.sqrt(TRADING_DAYS) * 100 if len(base_daily) > 1 else 0.0, 4),
            "win_rate_pct": round(_win_rate(base_daily), 2),
        },
        "shadow": {
            "sharpe": round(_sharpe(shd_daily), 4),
            "max_dd_pct": round(_max_dd_pct(shd_daily), 4),
            "ann_return_pct": round(
                (float(np.prod([1 + r for r in shd_daily])) ** (TRADING_DAYS / max(1, len(shd_daily))) - 1) * 100, 4,
            ),
            "vol_pct": round(stdev(shd_daily) * math.sqrt(TRADING_DAYS) * 100 if len(shd_daily) > 1 else 0.0, 4),
            "win_rate_pct": round(_win_rate(shd_daily), 2),
        },
    }

    # Rolling Sharpe
    def _rolling_sharpe(xs: list[float], w: int) -> list[float]:
        out = []
        for i in range(len(xs)):
            if i < w - 1:
                out.append(float("nan"))
                continue
            win = xs[i - w + 1 : i + 1]
            out.append(round(_sharpe(win), 3))
        return out

    df["base_rolling_5"] = _rolling_sharpe(base_daily, 5)
    df["shd_rolling_5"] = _rolling_sharpe(shd_daily, 5)
    df["base_rolling_10"] = _rolling_sharpe(base_daily, 10)
    df["shd_rolling_10"] = _rolling_sharpe(shd_daily, 10)
    df["uplift_bp"] = ((df["shadow_ret"] - df["base_ret"]) * 10000).round(2)

    # Consistency: fraction of days where shadow >= baseline
    uplift_days = (df["shadow_ret"] >= df["base_ret"]).sum()
    consistency_pct = 100.0 * uplift_days / len(df)

    # --- Reports ---
    logger.info("")
    logger.info("=" * 92)
    logger.info("SHADOW EVALUATION — {} days window", len(df))
    logger.info("=" * 92)
    logger.info("baseline: sharpe={} max_dd={}% ann_ret={}% vol={}% win_rate={}%",
                agg['baseline']['sharpe'], agg['baseline']['max_dd_pct'],
                agg['baseline']['ann_return_pct'], agg['baseline']['vol_pct'],
                agg['baseline']['win_rate_pct'])
    logger.info("shadow:   sharpe={} max_dd={}% ann_ret={}% vol={}% win_rate={}%",
                agg['shadow']['sharpe'], agg['shadow']['max_dd_pct'],
                agg['shadow']['ann_return_pct'], agg['shadow']['vol_pct'],
                agg['shadow']['win_rate_pct'])
    logger.info("")
    logger.info("uplift (shadow_sharpe - baseline_sharpe) = {}",
                round(agg['shadow']['sharpe'] - agg['baseline']['sharpe'], 4))
    logger.info("consistency: shadow >= baseline on {}/{} days ({:.1f}%)",
                uplift_days, len(df), consistency_pct)

    # Per-day table
    logger.info("")
    logger.info("DAILY TABLE")
    logger.info("{:<12s} {:>3s} {:>8s} {:>8s} {:>6s} {:>8s} {:>8s} {:>8s}",
                "date", "n", "base_ret", "shd_ret", "avg_m", "r5_base", "r5_shd", "upl_bp")
    for _, r in df.iterrows():
        logger.info(
            "{:<12s} {:>3d} {:>8.4f}% {:>8.4f}% {:>6.3f} {:>8} {:>8} {:>+8.2f}",
            str(r["date"]), int(r["n"]),
            r["base_ret"] * 100, r["shadow_ret"] * 100,
            r["avg_multiplier"],
            f"{r['base_rolling_5']:.2f}" if not math.isnan(r['base_rolling_5']) else "—",
            f"{r['shd_rolling_5']:.2f}" if not math.isnan(r['shd_rolling_5']) else "—",
            float(r["uplift_bp"]),
        )

    # Multiplier distribution
    mm = np.array(all_multipliers)
    logger.info("")
    logger.info("MULTIPLIER DISTRIBUTION (n={})", len(mm))
    logger.info("  min={:.3f}  p25={:.3f}  median={:.3f}  p75={:.3f}  max={:.3f}  mean={:.3f}",
                mm.min(), np.percentile(mm, 25), np.median(mm),
                np.percentile(mm, 75), mm.max(), mm.mean())
    logger.info("  at floor (0.5): {:.1f}%   at cap (1.2): {:.1f}%",
                (mm <= 0.5).mean() * 100, (mm >= 1.2).mean() * 100)

    # Bucket contribution
    logger.info("")
    logger.info("PERCENTILE-BUCKET CONTRIBUTION (mean daily return per bucket)")
    for b in ("top20", "mid60", "bot20"):
        vals = bucket_returns[b]
        if vals:
            logger.info("  {:<6s} n_days={} mean_ret={:+.4f}% sharpe={:.3f}",
                        b, len(vals), mean(vals) * 100, _sharpe(vals))

    # Regime-dependence check — split window in half
    mid = len(df) // 2
    first_half_upl = df["uplift_bp"].iloc[:mid].mean() if mid > 0 else 0
    second_half_upl = df["uplift_bp"].iloc[mid:].mean()
    logger.info("")
    logger.info("REGIME-DEPENDENCE CHECK")
    logger.info("  first half avg uplift = {:.2f}bp", first_half_upl)
    logger.info("  second half avg uplift = {:.2f}bp", second_half_upl)

    # Decision
    logger.info("")
    logger.info("=" * 92)
    logger.info("DECISION")
    logger.info("=" * 92)
    shd_s = agg['shadow']['sharpe']
    base_s = agg['baseline']['sharpe']
    dd_delta = agg['shadow']['max_dd_pct'] - agg['baseline']['max_dd_pct']

    criteria = {
        "sharpe_uplift >= 0.3": shd_s - base_s >= 0.3,
        "consistency >= 60%": consistency_pct >= 60,
        "dd_not_worse_by_5pp": dd_delta >= -5.0,
        "regime_stability (halves within 30bp)": abs(first_half_upl - second_half_upl) <= 30,
    }
    for k, v in criteria.items():
        logger.info("  [{}] {}", "✓" if v else "✗", k)

    passed = sum(criteria.values())
    if passed == 4:
        logger.info("VERDICT: SHADOW → LIVE")
    elif passed >= 2:
        logger.info("VERDICT: EXTEND SHADOW (some but not all criteria met)")
    else:
        logger.info("VERDICT: REDESIGN (multiple criteria failed)")


if __name__ == "__main__":
    main()
