"""Phase 18 — Regime Type Model (classifier/diagnostic).

Classify Phase 15 triggers into panic / neutral / drift regimes using
interpretable behavioral features. No weight fitting. No new filters.
No trading logic. Diagnostic only.

Features per trigger bar (all computed as of signal-close):
  f1_ret5d            = 5-bar close-to-close return (negative = selling)
  f2_ret3d            = 3-bar close-to-close return
  f3_accel            = ret3d_now - ret3d_3bars_ago (acceleration of selling)
  f4_path_eff         = |net move| / sum(|daily moves|) over prior 10 bars
                          low -> choppy (panic-like), high -> smooth (drift-like)
  f5_down_streak      = consecutive down closes ending at signal bar
  f6_up_day_frac_10   = fraction of up days in prior 10 bars
                          high -> bouncy (panic+recovery), low -> persistent
  f7_shock_flag       = max(|daily_ret|) in prior 10 bars > 2.0 * median(|daily_ret|)
  f8_close_pos        = (close - low) / (high - low) for signal bar
                          low -> closed weak, high -> closed strong
  f9_rebound_after_down = mean next-day return after each down-day in prior 10 bars
  f10_sign_autocorr   = lag-1 autocorr of prior-10 daily-return signs

Rule-based label (simple, transparent, pre-view):
  PANIC_SCORE adds/subtracts:
    +1 if ret_5d < -0.03      (sharp 5d decline)
    +1 if path_eff  < 0.50    (choppy path)
    +1 if shock_flag          (outsized shock day)
    +1 if up_day_frac_10 >= 0.40   (bounce-prone)
    -1 if down_streak >= 4    (long persistent streak)
    -1 if path_eff > 0.70     (smooth drift)
    -1 if up_day_frac_10 < 0.30    (no bounces)

  Buckets:
    panic_like  = score >= 2
    neutral     = score 0 or 1
    drift_like  = score <= -1

Tests: per-bucket 10D/20D stats, 2026 composition, historical-winner mapping,
monotonicity, separation vs Phase 17.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import random
import statistics as st
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
from loguru import logger

from scripts.run_phase12_price_action import (
    fetch_es_daily, load_spy_from_db, HOLD_WINDOWS,
)
from scripts.run_phase15_mean_reversion import (
    build_features, forward_returns,
    LOOSE_RATIO_THRESH, Z_EXTENSION_THRESH,
)

OUT_DIR = Path("artifacts/phase18")
OUT_DIR.mkdir(parents=True, exist_ok=True)

COST_BPS = (10, 20)
YEAR_2026_START = dt.date(2026, 1, 1)


def _bootstrap_ci(xs, *, n_boot=5000, conf=0.95):
    if not xs: return (0.0, 0.0)
    rng = random.Random(42); n = len(xs)
    means = [sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot)]
    means.sort()
    return (means[int((1 - conf) / 2 * n_boot)],
            means[int((1 - (1 - conf) / 2) * n_boot) - 1])


def summarize(rets, bps):
    if not rets: return {"n": 0}
    cost = bps / 1e4
    rn = [r - cost for r in rets]
    n = len(rn)
    mean = st.mean(rn); med = st.median(rn)
    sd = st.pstdev(rn) if n > 1 else 0.0
    wins = sum(1 for r in rn if r > 0)
    t = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
    lo, hi = _bootstrap_ci(rn)
    return {
        "n": n, "mean_pct": mean * 100, "median_pct": med * 100,
        "std_pct": sd * 100, "hit": wins / n, "t": t,
        "ci95_pct": [lo * 100, hi * 100],
        "mean_gross_pct": st.mean(rets) * 100,
    }


# ---------------------------------------------------------------------------
# Behavioral-feature computation (all pre-signal, no look-ahead)
# ---------------------------------------------------------------------------
def add_behavioral_features(f: pd.DataFrame) -> pd.DataFrame:
    f = f.copy()
    close = f["close"]
    high = f["high"]; low = f["low"]
    ret1 = close.pct_change(1)
    f["f1_ret5d"]  = close.pct_change(5)
    f["f2_ret3d"]  = close.pct_change(3)
    f["f3_accel"]  = f["f2_ret3d"] - close.shift(3).pct_change(3)

    # Path efficiency: |net 10-bar move| / sum(|daily move|) over 10 bars
    net10 = (close - close.shift(10)).abs()
    gross10 = ret1.abs().rolling(10).sum() * close.shift(10)
    # Normalize correctly: net_price / gross_price
    f["f4_path_eff"] = net10 / gross10.replace(0, pd.NA)

    # Down streak (consecutive down closes ending at current bar)
    down = (ret1 < 0).astype(int)
    streak = []
    cur = 0
    for v in down.fillna(0).astype(int).tolist():
        if v == 1:
            cur += 1
        else:
            cur = 0
        streak.append(cur)
    f["f5_down_streak"] = pd.Series(streak, index=f.index)

    # Up-day fraction in prior 10 bars (excluding today)
    up_day = (ret1 > 0).astype(float)
    f["f6_up_day_frac_10"] = up_day.shift(1).rolling(10).mean()

    # Shock flag: max(|ret|) in prior 10 bars > 2.0 * median(|ret|)
    abs_ret = ret1.abs()
    max_abs_10 = abs_ret.shift(1).rolling(10).max()
    med_abs_10 = abs_ret.shift(1).rolling(10).median()
    f["f7_shock_flag"] = (max_abs_10 > 2.0 * med_abs_10).fillna(False)

    # Close position within current bar's range
    rng = (high - low).replace(0, pd.NA)
    f["f8_close_pos"] = ((close - low) / rng).clip(0, 1)

    # Rebound after down day — mean next-day return after each prior down day
    rebound: list[float] = []
    ret_list = ret1.tolist()
    for i in range(len(ret_list)):
        vals = []
        for j in range(max(0, i - 10), i):
            if j + 1 <= i and ret_list[j] is not None and ret_list[j] < 0:
                if ret_list[j + 1] is not None:
                    vals.append(ret_list[j + 1])
        rebound.append(sum(vals) / len(vals) if vals else float("nan"))
    f["f9_rebound_after_down"] = pd.Series(rebound, index=f.index)

    # Sign autocorr of prior 10 returns (lag-1)
    def _sign_ac(arr):
        s = [1 if x > 0 else (-1 if x < 0 else 0) for x in arr if pd.notna(x)]
        if len(s) < 3:
            return 0.0
        pairs = [(s[i], s[i+1]) for i in range(len(s) - 1)]
        if not pairs:
            return 0.0
        return sum(a * b for a, b in pairs) / len(pairs)
    f["f10_sign_autocorr"] = ret1.shift(1).rolling(10).apply(_sign_ac, raw=False)

    return f


def classify_regime(row) -> tuple[int, str]:
    score = 0
    if pd.notna(row["f1_ret5d"]) and row["f1_ret5d"] < -0.03:        score += 1
    if pd.notna(row["f4_path_eff"]) and row["f4_path_eff"] < 0.50:   score += 1
    if bool(row["f7_shock_flag"]):                                    score += 1
    if pd.notna(row["f6_up_day_frac_10"]) and row["f6_up_day_frac_10"] >= 0.40: score += 1
    if pd.notna(row["f5_down_streak"]) and row["f5_down_streak"] >= 4: score -= 1
    if pd.notna(row["f4_path_eff"]) and row["f4_path_eff"] > 0.70:    score -= 1
    if pd.notna(row["f6_up_day_frac_10"]) and row["f6_up_day_frac_10"] < 0.30: score -= 1

    if score >= 2:   label = "panic_like"
    elif score <= -1: label = "drift_like"
    else:            label = "neutral"
    return score, label


def main() -> int:
    logger.info("[p18] fetching ES=F + SPY")
    es = fetch_es_daily(start="2020-01-01")
    spy = load_spy_from_db()
    es = es[~es.index.duplicated(keep="last")].sort_index()
    spy = spy[~spy.index.duplicated(keep="last")].sort_index()
    common = es.index.intersection(spy.index)
    es = es.loc[common]
    logger.info("[p18] common {} bars ({} -> {})", len(es), es.index[0], es.index[-1])

    f = build_features(es)
    f = add_behavioral_features(f)
    fwd = forward_returns(f, HOLD_WINDOWS)

    # Phase 15 entry
    c1 = f["loose_ratio"] > LOOSE_RATIO_THRESH
    c2 = f["vol_elevated"] | f["vol_expanding"]
    c3 = f["z_score"] < Z_EXTENSION_THRESH
    entry = (c1 & c2 & c3).fillna(False)
    signal_idx = [i for i in f.index if entry[i]]

    # Classify each signal
    records = []
    for i in signal_idx:
        score, label = classify_regime(f.loc[i])
        records.append({
            "date": i,
            "score": score,
            "label": label,
            "f1_ret5d": f.loc[i, "f1_ret5d"],
            "f2_ret3d": f.loc[i, "f2_ret3d"],
            "f3_accel": f.loc[i, "f3_accel"],
            "f4_path_eff": f.loc[i, "f4_path_eff"],
            "f5_down_streak": int(f.loc[i, "f5_down_streak"])
                if pd.notna(f.loc[i, "f5_down_streak"]) else None,
            "f6_up_day_frac_10": f.loc[i, "f6_up_day_frac_10"],
            "f7_shock_flag": bool(f.loc[i, "f7_shock_flag"]),
            "f8_close_pos": f.loc[i, "f8_close_pos"],
            "f9_rebound_after_down": f.loc[i, "f9_rebound_after_down"],
            "f10_sign_autocorr": f.loc[i, "f10_sign_autocorr"],
            "ret_10d": fwd[10][i] if not pd.isna(fwd[10][i]) else None,
            "ret_20d": fwd[20][i] if not pd.isna(fwd[20][i]) else None,
            "is_2026": i >= YEAR_2026_START,
        })
    label_count = Counter(r["label"] for r in records)

    # Per-bucket stats
    per_bucket: dict = {}
    for lbl in ("panic_like", "neutral", "drift_like"):
        for N in (10, 20):
            rows = [r for r in records
                    if r["label"] == lbl
                    and r[f"ret_{N}d"] is not None]
            for bps in COST_BPS:
                key = f"{lbl}_{N}_{bps}bps"
                per_bucket[key] = summarize([r[f"ret_{N}d"] for r in rows], bps)
                per_bucket[key]["label"] = lbl
                per_bucket[key]["N"] = N

    # 2026 YTD composition
    y2026 = [r for r in records if r["is_2026"]]
    y2026_comp = Counter(r["label"] for r in y2026)
    y2026_stats_by_label: dict = {}
    for lbl in ("panic_like", "neutral", "drift_like"):
        rets = [r["ret_10d"] for r in y2026
                if r["label"] == lbl and r["ret_10d"] is not None]
        y2026_stats_by_label[lbl] = {
            "n": len(rets),
            "stats_10d_20bps": summarize(rets, 20),
        }

    # Historical winner vs loser by bucket (pre-2026 = IS+OOS excl 2026)
    historical = [r for r in records if not r["is_2026"]]
    hist_by_label: dict = {}
    for lbl in ("panic_like", "neutral", "drift_like"):
        rets = [r["ret_10d"] for r in historical
                if r["label"] == lbl and r["ret_10d"] is not None]
        wins = sum(1 for r in rets if r > 0.002)   # +20bps costs
        losses = sum(1 for r in rets if r < -0.002)
        hist_by_label[lbl] = {
            "n": len(rets),
            "winners": wins, "losers": losses,
            "stats_10d_20bps": summarize(rets, 20),
        }

    # Monotonicity check on 10D/20bps means
    ordering = ["drift_like", "neutral", "panic_like"]
    means = [per_bucket[f"{l}_10_20bps"].get("mean_pct", None) for l in ordering]
    mono_10d = (means[0] is not None and means[1] is not None and means[2] is not None
                and means[0] < means[1] < means[2])

    means20 = [per_bucket[f"{l}_20_20bps"].get("mean_pct", None) for l in ordering]
    mono_20d = (means20[0] is not None and means20[1] is not None and means20[2] is not None
                and means20[0] < means20[1] < means20[2])

    # Verdict
    panic_10 = per_bucket["panic_like_10_20bps"]
    drift_10 = per_bucket["drift_like_10_20bps"]
    panic_ci = panic_10.get("ci95_pct", [0, 0])
    drift_ci = drift_10.get("ci95_pct", [0, 0])
    n_panic = panic_10.get("n", 0); n_drift = drift_10.get("n", 0)
    m_panic = panic_10.get("mean_pct", 0); m_drift = drift_10.get("mean_pct", 0)

    # 2026 damage containment: what fraction of 2026 trades end up in drift_like?
    drift_frac_2026 = (
        y2026_comp.get("drift_like", 0) / max(sum(y2026_comp.values()), 1)
    )
    # Historical winners in panic_like
    panic_hist_n = hist_by_label["panic_like"]["n"]
    panic_hist_mean = hist_by_label["panic_like"]["stats_10d_20bps"].get("mean_pct", 0)

    reasons: list[str] = []
    if n_panic >= 30 and m_panic > 0 and panic_ci[0] > 0 and (mono_10d or mono_20d):
        verdict = "PASS"
        reasons.append(
            f"panic_like n={n_panic} mean={m_panic:.3f}% CI=[{panic_ci[0]:.3f},{panic_ci[1]:.3f}]"
        )
        reasons.append(f"monotonic 10D={mono_10d} 20D={mono_20d}")
        reasons.append(f"2026 in drift_like: {drift_frac_2026*100:.1f}%")
    elif ((m_panic - m_drift) > 1.0 and mono_10d) or (
        n_panic >= 15 and m_panic > 0 and drift_frac_2026 > 0.5
    ):
        verdict = "WEAK"
        reasons.append(f"panic n={n_panic} mean={m_panic:+.3f}% "
                       f"vs drift n={n_drift} mean={m_drift:+.3f}%")
        reasons.append(f"2026 drift share: {drift_frac_2026*100:.1f}%")
    else:
        verdict = "FAIL"
        reasons.append(
            f"panic n={n_panic} mean={m_panic:+.3f}% / drift n={n_drift} mean={m_drift:+.3f}%"
        )
        reasons.append(f"monotonic 10D={mono_10d} 20D={mono_20d}")
        reasons.append(f"2026 drift share {drift_frac_2026*100:.1f}% insufficient to contain damage")

    report = {
        "phase": "18_regime_type",
        "today": dt.date.today().isoformat(),
        "params_from_p15": {
            "loose_ratio": LOOSE_RATIO_THRESH,
            "z_thresh": Z_EXTENSION_THRESH,
        },
        "regime_label_rules": {
            "panic_like": "score >= 2",
            "neutral":    "score in {0, 1}",
            "drift_like": "score <= -1",
            "score_components": [
                "+1 if ret_5d < -0.03",
                "+1 if path_eff < 0.50",
                "+1 if shock_flag",
                "+1 if up_day_frac_10 >= 0.40",
                "-1 if down_streak >= 4",
                "-1 if path_eff > 0.70",
                "-1 if up_day_frac_10 < 0.30",
            ],
        },
        "bucket_counts": dict(label_count),
        "per_bucket_stats": per_bucket,
        "monotonicity": {"10D": mono_10d, "20D": mono_20d,
                          "means_10d_by_order": means, "means_20d_by_order": means20},
        "year_2026_composition": dict(y2026_comp),
        "year_2026_by_label": y2026_stats_by_label,
        "historical_winners_by_label": hist_by_label,
        "verdict": verdict,
        "verdict_reasons": reasons,
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=str))

    # Trade-level audit file
    audit = []
    for r in records:
        audit.append({**r, "date": r["date"].isoformat()
                      if hasattr(r["date"], "isoformat") else str(r["date"])})
    (OUT_DIR / "trades_labeled.jsonl").write_text(
        "\n".join(json.dumps(a, default=str) for a in audit)
    )

    # Print
    print("=" * 95)
    print(f"PHASE 18 — REGIME TYPE MODEL  {dt.date.today()}")
    print("=" * 95)
    print(f"Data: ES=F {f.index[0]} -> {f.index[-1]} ({len(f)} bars)")
    print(f"Phase-15 signals total: {len(records)}  (2026 YTD: {len(y2026)})")
    print()
    print(f"--- Bucket counts: {dict(label_count)} ---")
    print()
    print("--- Per-bucket stats (10D/20bps, 20D/20bps) ---")
    print(f"{'bucket':<12} {'N':>3} {'n':>4} {'mean%':>8} {'med%':>7} {'hit':>5} "
          f"{'t':>6} {'CI95%':<22}")
    for lbl in ("panic_like", "neutral", "drift_like"):
        for N in (10, 20):
            s = per_bucket[f"{lbl}_{N}_20bps"]
            if s.get("n", 0) == 0:
                print(f"{lbl:<12} {N:>3} 0 (empty)"); continue
            ci = s["ci95_pct"]
            print(f"{lbl:<12} {N:>3} {s['n']:>4} {s['mean_pct']:>+8.3f} "
                  f"{s['median_pct']:>+7.3f} {s['hit']:>5.3f} {s['t']:>+6.2f} "
                  f"[{ci[0]:+.3f},{ci[1]:+.3f}]")
    print()
    print("--- Monotonicity (drift < neutral < panic)? ---")
    print(f"  10D means by bucket order [drift, neutral, panic]: {[f'{x:+.3f}%' if x is not None else 'n/a' for x in means]}")
    print(f"  20D means by bucket order [drift, neutral, panic]: {[f'{x:+.3f}%' if x is not None else 'n/a' for x in means20]}")
    print(f"  monotonic 10D = {mono_10d}    20D = {mono_20d}")
    print()
    print("--- 2026 YTD composition ---")
    print(f"  total 2026 signals: {sum(y2026_comp.values())}")
    print(f"  composition: {dict(y2026_comp)}")
    for lbl, d in y2026_stats_by_label.items():
        s = d["stats_10d_20bps"]
        if s.get("n", 0) == 0:
            print(f"  {lbl:<12} n=0"); continue
        ci = s["ci95_pct"]
        print(f"  {lbl:<12} n={d['n']:>3} mean={s['mean_pct']:+.3f}% "
              f"hit={s['hit']:.3f} t={s['t']:+.2f} CI=[{ci[0]:+.3f},{ci[1]:+.3f}]")
    print()
    print("--- Historical (pre-2026) by bucket ---")
    for lbl, d in hist_by_label.items():
        s = d["stats_10d_20bps"]
        if s.get("n", 0) == 0:
            print(f"  {lbl:<12} n=0"); continue
        ci = s["ci95_pct"]
        print(f"  {lbl:<12} n={d['n']:>3} wins/losses={d['winners']}/{d['losers']} "
              f"mean={s['mean_pct']:+.3f}% hit={s['hit']:.3f} "
              f"t={s['t']:+.2f} CI=[{ci[0]:+.3f},{ci[1]:+.3f}]")
    print()
    print("-" * 95)
    print(f"VERDICT: {verdict}")
    for r in reasons: print(f"  - {r}")
    print("=" * 95)
    print(f"Report: {OUT_DIR / 'report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
