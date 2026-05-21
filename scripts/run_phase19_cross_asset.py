"""Phase 19 — Cross-Asset Signal Layer on Phase 15 signal.

External series (yfinance — existing stack):
  ^VIX   CBOE VIX
  ^TNX   10Y Treasury yield
  HYG    High-yield bond ETF
  RSP    Equal-weight S&P 500
  SPY    Cap-weight S&P 500

Features at signal date:
  vix_level         = VIX close
  vix_5d_change     = VIX(t) - VIX(t-5)   (vol regime direction)
  d10y_5d           = ^TNX(t) - ^TNX(t-5) (rates direction, bps-equivalent)
  hyg_ret_5d        = HYG.close.pct_change(5)  (credit direction)
  rsp_spy_5d        = (RSP/SPY)(t) / (RSP/SPY)(t-5) - 1  (breadth direction)

Buckets: terciles per feature (below/mid/above) computed on full-sample.

Tests:
  1. Univariate separation per feature (P15 10D/20D forward returns per tercile)
  2. 2026 YTD composition per bucket
  3. Simple 2-condition filters:
     a. d10y_5d falling (bottom tercile) + signal
     b. hyg_ret_5d positive (top 2 terciles) + signal
     c. high vix (top tercile) + high vix_5d_change (top tercile) + signal
     d. hyg_ret_5d positive + rsp_spy_5d improving (top 2 terciles) + signal
  4. OOS 2025-2026 + 2026 YTD per filter

No ML. No threshold tuning. Max 2 conditions per filter. Stop at verdict.
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
import yfinance as yf
from loguru import logger

from scripts.run_phase12_price_action import (
    fetch_es_daily, load_spy_from_db, HOLD_WINDOWS,
)
from scripts.run_phase15_mean_reversion import (
    build_features, forward_returns,
    LOOSE_RATIO_THRESH, Z_EXTENSION_THRESH,
)

OUT_DIR = Path("artifacts/phase19")
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE = OUT_DIR / "external_cache.parquet"

COST_BPS = (10, 20)
IS_END = dt.date(2024, 12, 31)
OOS_START = dt.date(2025, 1, 1)
YEAR_2026_START = dt.date(2026, 1, 1)


# ---------------------------------------------------------------------------
# External-data loader (yfinance, cached)
# ---------------------------------------------------------------------------
def fetch_external(start="2020-01-01") -> pd.DataFrame:
    if CACHE.exists():
        try:
            df = pd.read_parquet(CACHE)
            return df
        except Exception:
            pass
    tickers = ["^VIX", "^TNX", "HYG", "RSP", "SPY"]
    rows: dict[str, pd.Series] = {}
    for sym in tickers:
        t = yf.Ticker(sym)
        df = t.history(start=start, interval="1d", auto_adjust=False)
        if df.empty:
            logger.warning("[p19] {} empty", sym)
            continue
        s = df["Close"].copy()
        s.index = [i.date() for i in s.index]
        s = s[~s.index.duplicated(keep="last")]
        rows[sym] = s
    out = pd.DataFrame(rows).sort_index()
    try:
        out.to_parquet(CACHE)
    except Exception:
        pass
    return out


def build_cross_asset_features(ext: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=ext.index)
    f["vix_level"]     = ext["^VIX"]
    f["vix_5d_change"] = ext["^VIX"] - ext["^VIX"].shift(5)
    f["d10y_5d"]       = ext["^TNX"] - ext["^TNX"].shift(5)
    f["hyg_ret_5d"]    = ext["HYG"].pct_change(5)
    rsp_spy            = ext["RSP"] / ext["SPY"]
    f["rsp_spy_5d"]    = rsp_spy.pct_change(5)
    return f


def tercile_labels(s: pd.Series) -> pd.Series:
    q_lo, q_hi = s.dropna().quantile([1/3, 2/3]).values
    def _lab(x):
        if pd.isna(x): return None
        if x < q_lo:   return "low"
        if x < q_hi:   return "mid"
        return "high"
    return s.apply(_lab)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
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
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    logger.info("[p19] fetching ES=F + SPY")
    es = fetch_es_daily(start="2020-01-01")
    spy = load_spy_from_db()
    es = es[~es.index.duplicated(keep="last")].sort_index()
    spy = spy[~spy.index.duplicated(keep="last")].sort_index()
    common = es.index.intersection(spy.index)
    es = es.loc[common]
    logger.info("[p19] ES common {} bars ({} -> {})", len(es), es.index[0], es.index[-1])

    logger.info("[p19] fetching external series (VIX, TNX, HYG, RSP, SPY) from yfinance")
    ext = fetch_external(start="2020-01-01")
    logger.info("[p19] external {} rows", len(ext))

    f = build_features(es)
    xa = build_cross_asset_features(ext)
    # Align xa to f's index — forward-fill small gaps (weekend/holiday misalignments)
    xa_aligned = xa.reindex(f.index).ffill()
    for c in xa.columns:
        f[c] = xa_aligned[c]

    fwd = forward_returns(f, HOLD_WINDOWS)

    # P15 entry
    c1 = f["loose_ratio"] > LOOSE_RATIO_THRESH
    c2 = f["vol_elevated"] | f["vol_expanding"]
    c3 = f["z_score"] < Z_EXTENSION_THRESH
    entry = (c1 & c2 & c3).fillna(False)

    # Tercile labels per cross-asset feature
    feature_cols = ["vix_level", "vix_5d_change", "d10y_5d",
                    "hyg_ret_5d", "rsp_spy_5d"]
    for c in feature_cols:
        f[f"{c}_bucket"] = tercile_labels(f[c])

    # Signal table
    sig_rows: list[dict] = []
    for i in f.index:
        if not entry[i]: continue
        row = {"date": i,
               "ret_10d": fwd[10][i] if not pd.isna(fwd[10][i]) else None,
               "ret_20d": fwd[20][i] if not pd.isna(fwd[20][i]) else None,
               "is_2026": i >= YEAR_2026_START,
               "is_oos":  i >= OOS_START}
        for c in feature_cols:
            row[c] = f.loc[i, c]
            row[f"{c}_bucket"] = f.loc[i, f"{c}_bucket"]
        sig_rows.append(row)
    logger.info("[p19] signals={}  2026_ytd={}",
                len(sig_rows), sum(1 for r in sig_rows if r["is_2026"]))

    # 1) Univariate separation — per-bucket P15 stats at 10D and 20D
    univariate: dict = {}
    for c in feature_cols:
        univariate[c] = {}
        for lbl in ("low", "mid", "high"):
            for N in (10, 20):
                rets = [r[f"ret_{N}d"] for r in sig_rows
                        if r[f"{c}_bucket"] == lbl and r[f"ret_{N}d"] is not None]
                univariate[c][f"{lbl}_{N}_20bps"] = summarize(rets, 20)
                univariate[c][f"{lbl}_{N}_20bps"]["bucket"] = lbl
                univariate[c][f"{lbl}_{N}_20bps"]["N"] = N

    # 2) 2026 YTD composition per bucket (10D/20bps)
    year2026 = [r for r in sig_rows if r["is_2026"]]
    y26_comp: dict = {}
    for c in feature_cols:
        y26_comp[c] = dict(Counter(r[f"{c}_bucket"] for r in year2026))

    # 3) Simple 2-condition filters
    def filter_predicate(name: str):
        if name == "A_d10y_falling":
            return lambda r: r["d10y_5d_bucket"] == "low"
        if name == "B_hyg_positive":
            return lambda r: r["hyg_ret_5d_bucket"] in ("mid", "high")
        if name == "C_high_vix_and_rising":
            return lambda r: (r["vix_level_bucket"] == "high"
                              and r["vix_5d_change_bucket"] == "high")
        if name == "D_hyg_pos_and_rsp_improving":
            return lambda r: (r["hyg_ret_5d_bucket"] in ("mid", "high")
                              and r["rsp_spy_5d_bucket"] in ("mid", "high"))
        raise ValueError(name)

    filter_names = ("A_d10y_falling", "B_hyg_positive",
                    "C_high_vix_and_rising", "D_hyg_pos_and_rsp_improving")

    filters_out: dict = {}
    unfilt_10d = summarize([r["ret_10d"] for r in sig_rows if r["ret_10d"] is not None], 20)
    unfilt_is  = summarize([r["ret_10d"] for r in sig_rows
                            if not r["is_oos"] and r["ret_10d"] is not None], 20)
    unfilt_oos = summarize([r["ret_10d"] for r in sig_rows
                            if r["is_oos"] and r["ret_10d"] is not None], 20)
    unfilt_2026 = summarize([r["ret_10d"] for r in sig_rows
                             if r["is_2026"] and r["ret_10d"] is not None], 20)
    n_unfilt = len(sig_rows)

    for fname in filter_names:
        pred = filter_predicate(fname)
        kept = [r for r in sig_rows if pred(r)]
        rets_10 = [r["ret_10d"] for r in kept if r["ret_10d"] is not None]
        rets_20 = [r["ret_20d"] for r in kept if r["ret_20d"] is not None]
        is_rets  = [r["ret_10d"] for r in kept
                    if not r["is_oos"] and r["ret_10d"] is not None]
        oos_rets = [r["ret_10d"] for r in kept
                    if r["is_oos"] and r["ret_10d"] is not None]
        y26_rets = [r["ret_10d"] for r in kept
                    if r["is_2026"] and r["ret_10d"] is not None]
        filters_out[fname] = {
            "n_kept": len(kept),
            "retention_pct": len(kept) / max(n_unfilt, 1),
            "full_10d_20bps":  summarize(rets_10, 20),
            "full_20d_20bps":  summarize(rets_20, 20),
            "is_10d_20bps":    summarize(is_rets, 20),
            "oos_10d_20bps":   summarize(oos_rets, 20),
            "y2026_10d_20bps": summarize(y26_rets, 20),
        }

    # Best filter — ranked by OOS t-stat, break tie by 2026 mean
    def _rank(f):
        s = filters_out[f]
        return (-s["oos_10d_20bps"].get("t", 0),
                -s["y2026_10d_20bps"].get("mean_pct", 0))
    best_filter = sorted(filter_names, key=_rank)[0]
    bf = filters_out[best_filter]

    # Verdict
    bf_oos = bf["oos_10d_20bps"]
    bf_2026 = bf["y2026_10d_20bps"]
    oos_ci = bf_oos.get("ci95_pct", [0, 0])
    n_oos_bf = bf_oos.get("n", 0)
    m_oos_bf = bf_oos.get("mean_pct", 0)
    t_oos_bf = bf_oos.get("t", 0)
    base_oos_lo = unfilt_oos.get("ci95_pct", [0, 0])[0]
    base_2026_mean = unfilt_2026.get("mean_pct", 0)
    bf_2026_mean = bf_2026.get("mean_pct", 0)
    oos_lo_improved = oos_ci[0] > base_oos_lo
    y2026_improved = bf_2026_mean > base_2026_mean

    if (n_oos_bf >= 15 and t_oos_bf > 2.0 and m_oos_bf > 0 and oos_ci[0] > 0
        and y2026_improved):
        verdict = "PASS"
        vr = [f"best={best_filter}  OOS n={n_oos_bf} t={t_oos_bf:.2f} "
              f"mean={m_oos_bf:.3f}% CI=[{oos_ci[0]:.3f},{oos_ci[1]:.3f}]",
              f"2026 improved: {bf_2026_mean:+.3f}% (base {base_2026_mean:+.3f}%)"]
    elif (n_oos_bf >= 10 and m_oos_bf > 0 and oos_lo_improved
          and y2026_improved):
        verdict = "WEAK"
        vr = [f"best={best_filter} OOS n={n_oos_bf} t={t_oos_bf:.2f} "
              f"mean={m_oos_bf:+.3f}% CI=[{oos_ci[0]:+.3f},{oos_ci[1]:+.3f}]",
              f"OOS lo {oos_ci[0]:+.3f} > base {base_oos_lo:+.3f}",
              f"2026: {bf_2026_mean:+.3f}% vs base {base_2026_mean:+.3f}%"]
    else:
        verdict = "FAIL"
        vr = [f"best={best_filter} OOS n={n_oos_bf} t={t_oos_bf:.2f} "
              f"mean={m_oos_bf:+.3f}% CI=[{oos_ci[0]:+.3f},{oos_ci[1]:+.3f}]",
              f"OOS improvement pp: {oos_ci[0] - base_oos_lo:+.3f}",
              f"2026 improvement pp: {bf_2026_mean - base_2026_mean:+.3f}"]

    report = {
        "phase": "19_cross_asset",
        "today": dt.date.today().isoformat(),
        "data_range": [str(f.index[0]), str(f.index[-1])],
        "n_signals": n_unfilt,
        "n_2026_ytd": sum(1 for r in sig_rows if r["is_2026"]),
        "unfiltered_p15_10d_20bps": unfilt_10d,
        "unfiltered_is_10d_20bps": unfilt_is,
        "unfiltered_oos_10d_20bps": unfilt_oos,
        "unfiltered_2026_10d_20bps": unfilt_2026,
        "univariate_buckets": univariate,
        "year_2026_composition_by_feature": y26_comp,
        "filters": filters_out,
        "best_filter": best_filter,
        "verdict": verdict,
        "verdict_reasons": vr,
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=str))

    # Print
    print("=" * 100)
    print(f"PHASE 19 - CROSS-ASSET SIGNAL LAYER  {dt.date.today()}")
    print("=" * 100)
    print(f"Data: ES=F {f.index[0]} -> {f.index[-1]} ({len(f)} bars)")
    print(f"P15 signals: {n_unfilt}   (2026 YTD: {sum(1 for r in sig_rows if r['is_2026'])})")
    print()
    print("--- Unfiltered P15 baseline ---")
    print(f"  full: n={unfilt_10d.get('n',0)} mean={unfilt_10d.get('mean_pct',0):+.3f}% "
          f"t={unfilt_10d.get('t',0):+.2f} CI=[{unfilt_10d.get('ci95_pct',[0,0])[0]:+.3f},"
          f"{unfilt_10d.get('ci95_pct',[0,0])[1]:+.3f}]")
    print(f"  IS:   n={unfilt_is.get('n',0)} mean={unfilt_is.get('mean_pct',0):+.3f}% "
          f"t={unfilt_is.get('t',0):+.2f}")
    print(f"  OOS:  n={unfilt_oos.get('n',0)} mean={unfilt_oos.get('mean_pct',0):+.3f}% "
          f"t={unfilt_oos.get('t',0):+.2f}")
    print(f"  2026: n={unfilt_2026.get('n',0)} mean={unfilt_2026.get('mean_pct',0):+.3f}% "
          f"t={unfilt_2026.get('t',0):+.2f}")
    print()
    print("--- 1) UNIVARIATE TERCILE SEPARATION (10D/20bps) ---")
    for c in feature_cols:
        print(f"  feature: {c}")
        for lbl in ("low", "mid", "high"):
            s = univariate[c][f"{lbl}_10_20bps"]
            if s.get("n", 0) == 0:
                print(f"    {lbl:<5}: n=0"); continue
            ci = s["ci95_pct"]
            print(f"    {lbl:<5}: n={s['n']:>3} mean={s['mean_pct']:+.3f}% "
                  f"hit={s['hit']:.3f} t={s['t']:+.2f} CI=[{ci[0]:+.3f},{ci[1]:+.3f}]")
    print()
    print("--- 2) 2026 YTD COMPOSITION PER FEATURE ---")
    for c in feature_cols:
        print(f"  {c:<20} {y26_comp[c]}")
    print()
    print("--- 3) CONDITIONAL FILTERS (<=2 conditions) ---")
    for fname in filter_names:
        pf = filters_out[fname]
        print(f"  {fname}")
        print(f"    retention={pf['retention_pct']*100:.1f}% ({pf['n_kept']}/{n_unfilt})")
        for label, stat in (("full_10d", pf["full_10d_20bps"]),
                            ("is_10d",   pf["is_10d_20bps"]),
                            ("oos_10d",  pf["oos_10d_20bps"]),
                            ("2026_10d", pf["y2026_10d_20bps"])):
            if stat.get("n", 0) == 0:
                print(f"    {label:<8} n=0"); continue
            ci = stat["ci95_pct"]
            print(f"    {label:<8} n={stat['n']:>3} mean={stat['mean_pct']:+.3f}% "
                  f"hit={stat['hit']:.3f} t={stat['t']:+.2f} "
                  f"CI=[{ci[0]:+.3f},{ci[1]:+.3f}]")
    print()
    print(f"--- BEST FILTER: {best_filter} ---")
    print(f"  OOS lo vs base pp: "
          f"{filters_out[best_filter]['oos_10d_20bps'].get('ci95_pct', [0,0])[0] - base_oos_lo:+.3f}")
    print(f"  2026 mean vs base pp: "
          f"{bf_2026_mean - base_2026_mean:+.3f}")
    print()
    print("-" * 100)
    print(f"VERDICT: {verdict}")
    for r in vr: print(f"  - {r}")
    print("=" * 100)
    print(f"Report: {OUT_DIR / 'report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
