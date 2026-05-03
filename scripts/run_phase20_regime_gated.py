"""Phase 20 — Regime-Gated Mean Reversion System.

Base entry (frozen, unchanged from Phase 15):
    c1: ATR10 / ATR50 > 1.2
    c2: ATR10 >= rolling-252d P60  OR  ATR10 > ATR20
    c3: z_score(close, MA20, std20) < -1.0
    long-only, next-bar open entry, exits 1/3/5/10/20 bars

Four PIT-clean regime gates (added without modifying c1/c2/c3):
  G1 rates_calm          = d10y_5d < 0                    (FRED DGS10)
  G2 vrp_supportive      = VRP > rolling 6-month median   (yfinance VIX + SPY RV21)
  G3 credit_stable       = HY OAS 20d change <= 0         (FRED BAMLH0A0HYM2)
                           fallback: HYG 20d return >= 0  (yfinance, pre-2023-04)
  G4 liquidity_expanding = Fed-net-liq 20d change > 0     (FRED WALCL-WTREGEN-RRPONTSYD)

Main rule: P15 entry executed only when >= 3-of-4 gates favorable.
Diagnostic: also report 2-of-4 and 4-of-4 as comparisons.

Also: standalone directional sleeves for each gate (long ES when favorable)
with pairwise correlation matrix.

No ML. No tuning. No features beyond these four. Cost model unchanged.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import random
import statistics as st
import sys
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

OUT_DIR = Path("artifacts/phase20")
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = OUT_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

COST_BPS = (10, 20)
IS_END = dt.date(2024, 12, 31)
OOS_START = dt.date(2025, 1, 1)
Y2026_START = dt.date(2026, 1, 1)

# Gate thresholds (frozen)
VRP_WINDOW_BARS = 126   # ~6 months of trading days
RATES_LAG       = 5
CREDIT_LAG      = 20
LIQ_LAG         = 20
RV_WINDOW       = 21


# ---------------------------------------------------------------------------
# Data loaders (external)
# ---------------------------------------------------------------------------
def fetch_fred_csv(series_id: str) -> pd.Series:
    cache = CACHE_DIR / f"fred_{series_id}.csv"
    if cache.exists():
        df = pd.read_csv(cache)
    else:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd=2020-01-01"
        df = pd.read_csv(url)
        df.to_csv(cache, index=False)
    df.columns = ["date", series_id]
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df[series_id] = pd.to_numeric(df[series_id], errors="coerce")
    s = pd.Series(df[series_id].values, index=df["date"], name=series_id)
    return s.sort_index()


def fetch_hyg_lqd() -> pd.DataFrame:
    cache = CACHE_DIR / "hyg_lqd.csv"
    if cache.exists():
        df = pd.read_csv(cache, index_col=0)
        df.index = [dt.date.fromisoformat(i) for i in df.index]
        return df
    dfs = {}
    for sym in ("HYG", "LQD"):
        t = yf.Ticker(sym)
        h = t.history(start="2020-01-01", interval="1d", auto_adjust=False)
        s = h["Close"].copy()
        s.index = [i.date() for i in s.index]
        dfs[sym] = s[~s.index.duplicated(keep="last")]
    out = pd.DataFrame(dfs).sort_index()
    out.to_csv(cache)
    return out


def fetch_vix() -> pd.Series:
    cache = CACHE_DIR / "vix.csv"
    if cache.exists():
        df = pd.read_csv(cache, index_col=0)
        df.index = [dt.date.fromisoformat(i) for i in df.index]
        return df.iloc[:, 0]
    t = yf.Ticker("^VIX")
    h = t.history(start="2020-01-01", interval="1d", auto_adjust=False)
    s = h["Close"].copy()
    s.index = [i.date() for i in s.index]
    s = s[~s.index.duplicated(keep="last")]
    s.name = "VIX"
    s.to_csv(cache)
    return s


# ---------------------------------------------------------------------------
# Gate construction (PIT-clean)
# ---------------------------------------------------------------------------
def build_gates(f: pd.DataFrame, spy: pd.DataFrame) -> pd.DataFrame:
    logger.info("[p20] building regime gates")
    g = pd.DataFrame(index=f.index)

    # --- G1: rates_calm = d10y_5d < 0 ---
    dgs10 = fetch_fred_csv("DGS10").ffill()
    dgs10_aligned = dgs10.reindex(f.index).ffill()
    d10y_5d = dgs10_aligned - dgs10_aligned.shift(5)
    g["rates_calm"] = (d10y_5d < 0).fillna(False)
    g["_d10y_5d"] = d10y_5d

    # --- G2: vrp_supportive = VRP > rolling 6M median ---
    vix = fetch_vix().reindex(f.index).ffill()
    # RV21 from SPY close returns (daily close-to-close realized variance, annualized %^2)
    spy_close = spy["close"].reindex(f.index).ffill()
    daily_ret = spy_close.pct_change()
    rv21_annualized = daily_ret.rolling(RV_WINDOW).std() * math.sqrt(252) * 100  # %
    vrp = (vix ** 2) - (rv21_annualized ** 2)
    vrp_median = vrp.rolling(VRP_WINDOW_BARS).median()
    g["vrp_supportive"] = (vrp > vrp_median).fillna(False)
    g["_vrp"] = vrp
    g["_vrp_median"] = vrp_median
    g["_vix"] = vix
    g["_rv21"] = rv21_annualized

    # --- G3: credit_stable ---
    # Primary: FRED HY OAS 20d change <= 0 (credit improving or stable)
    # Fallback: HYG 20d return >= 0
    hy_oas = fetch_fred_csv("BAMLH0A0HYM2").ffill()
    hy_aligned = hy_oas.reindex(f.index).ffill()
    hy_20d_chg = hy_aligned - hy_aligned.shift(CREDIT_LAG)

    hyg_lqd = fetch_hyg_lqd()
    hyg = hyg_lqd["HYG"].reindex(f.index).ffill()
    hyg_20d_ret = hyg.pct_change(CREDIT_LAG)

    credit_primary = hy_20d_chg <= 0
    credit_fallback = hyg_20d_ret >= 0
    # Use primary where available, fallback otherwise (HY OAS starts 2023-04)
    g["credit_stable"] = credit_primary.where(
        hy_aligned.notna(), credit_fallback
    ).fillna(False)
    g["_hy_oas"] = hy_aligned
    g["_hy_20d_chg"] = hy_20d_chg
    g["_hyg_20d_ret"] = hyg_20d_ret

    # --- G4: liquidity_expanding = Fed-net-liquidity 20d change > 0 ---
    walcl = fetch_fred_csv("WALCL").ffill()
    wtregen = fetch_fred_csv("WTREGEN").ffill()
    rrp = fetch_fred_csv("RRPONTSYD").ffill()
    walcl_a = walcl.reindex(f.index).ffill()
    wtregen_a = wtregen.reindex(f.index).ffill()
    rrp_a = rrp.reindex(f.index).ffill()
    net_liq = walcl_a - wtregen_a - rrp_a
    net_liq_20d_chg = net_liq - net_liq.shift(LIQ_LAG)
    g["liquidity_expanding"] = (net_liq_20d_chg > 0).fillna(False)
    g["_net_liq"] = net_liq
    g["_net_liq_20d_chg"] = net_liq_20d_chg

    # Composite: count of gates favorable
    gate_cols = ["rates_calm", "vrp_supportive", "credit_stable", "liquidity_expanding"]
    g["gates_favorable"] = g[gate_cols].sum(axis=1)
    return g


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
    eq = 1.0; path = []
    for r in rn:
        eq *= (1 + r); path.append(eq)
    pk = path[0] if path else 1.0; dd = 0.0
    for v in path:
        pk = max(pk, v); dd = min(dd, (v - pk) / pk)
    return {
        "n": n, "mean_pct": mean * 100, "median_pct": med * 100,
        "std_pct": sd * 100, "hit": wins / n, "t": t,
        "ci95_pct": [lo * 100, hi * 100],
        "mean_gross_pct": st.mean(rets) * 100,
        "cum_pct": (path[-1] - 1) * 100 if path else 0.0,
        "max_dd_pct": dd * 100,
    }


def subset_rets(
    f: pd.DataFrame, entry: pd.Series, fwd: pd.Series,
    extra_mask: pd.Series | None = None,
) -> list[float]:
    out = []
    for i in f.index:
        if not entry[i]: continue
        if extra_mask is not None and not extra_mask[i]: continue
        r = fwd[i]
        if pd.isna(r): continue
        out.append(float(r))
    return out


def date_mask(f, predicate) -> pd.Series:
    return pd.Series([predicate(i) for i in f.index], index=f.index)


# ---------------------------------------------------------------------------
# Standalone directional sleeve
# ---------------------------------------------------------------------------
def sleeve_returns(
    f: pd.DataFrame, fwd: pd.Series, gate: pd.Series,
) -> list[float]:
    """Long ES on every bar where gate is True. Holding = window N."""
    out = []
    for i in f.index:
        if not gate[i]: continue
        r = fwd[i]
        if pd.isna(r): continue
        out.append(float(r))
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    logger.info("[p20] fetching ES=F + SPY")
    es = fetch_es_daily(start="2020-01-01")
    spy = load_spy_from_db()
    es = es[~es.index.duplicated(keep="last")].sort_index()
    spy = spy[~spy.index.duplicated(keep="last")].sort_index()
    common = es.index.intersection(spy.index)
    es = es.loc[common]; spy = spy.loc[common]
    logger.info("[p20] common {} bars ({} -> {})", len(es), es.index[0], es.index[-1])

    f = build_features(es)
    fwd = forward_returns(f, HOLD_WINDOWS)
    gates = build_gates(f, spy)

    # P15 entry
    c1 = f["loose_ratio"] > LOOSE_RATIO_THRESH
    c2 = f["vol_elevated"] | f["vol_expanding"]
    c3 = f["z_score"] < Z_EXTENSION_THRESH
    entry = (c1 & c2 & c3).fillna(False)
    n_entries = int(entry.sum())
    logger.info("[p20] P15 entries: {}", n_entries)

    # Gate counts at entry bars
    entries_by_gates = {}
    for k in range(5):
        m = entry & (gates["gates_favorable"] == k)
        entries_by_gates[str(k)] = int(m.sum())
    logger.info("[p20] entries by gates_favorable count: {}", entries_by_gates)

    # Date masks
    is_mask   = date_mask(f, lambda d: d <= IS_END)
    oos_mask  = date_mask(f, lambda d: d >= OOS_START)
    y26_mask  = date_mask(f, lambda d: d >= Y2026_START)
    all_mask  = pd.Series(True, index=f.index)

    # ----- Ungated (Phase 15 baseline) per window/cost -----
    ungated = {}
    for N in HOLD_WINDOWS:
        for bps in COST_BPS:
            for seg, msk in (("full", all_mask), ("is", is_mask),
                             ("oos", oos_mask), ("y2026", y26_mask)):
                rets = subset_rets(f, entry, fwd[N], msk)
                ungated[f"{seg}_{N}_{bps}bps"] = summarize(rets, bps)

    # ----- Gated variants: >=2, >=3, >=4 favorable -----
    gated_results = {}
    for threshold in (2, 3, 4):
        gated_mask = (gates["gates_favorable"] >= threshold).fillna(False)
        variant = {}
        for N in HOLD_WINDOWS:
            for bps in COST_BPS:
                for seg, msk in (("full", all_mask), ("is", is_mask),
                                 ("oos", oos_mask), ("y2026", y26_mask)):
                    rets = subset_rets(f, entry & gated_mask, fwd[N], msk)
                    variant[f"{seg}_{N}_{bps}bps"] = summarize(rets, bps)
        # Retention count
        n_kept = int((entry & gated_mask).sum())
        variant["n_kept"] = n_kept
        variant["retention_pct"] = n_kept / max(n_entries, 1)
        gated_results[f"gt{threshold}"] = variant

    # ----- Per-gate attribution (10D/20bps) at entry bars -----
    gate_attribution = {}
    gate_cols = ["rates_calm", "vrp_supportive", "credit_stable", "liquidity_expanding"]
    for gcol in gate_cols:
        fav = (entry & gates[gcol])
        unf = (entry & ~gates[gcol])
        gate_attribution[gcol] = {
            "favorable":   summarize(subset_rets(f, fav, fwd[10]), 20),
            "unfavorable": summarize(subset_rets(f, unf, fwd[10]), 20),
            "n_fav": int(fav.sum()),
            "n_unf": int(unf.sum()),
        }

    # ----- Gate orthogonality (correlation matrix at entry bars) -----
    ent_gates = gates.loc[entry, gate_cols].astype(int)
    corr_matrix = ent_gates.corr()

    # ----- Standalone directional sleeves (10D/20bps) -----
    sleeves = {}
    for gcol in gate_cols:
        gate_on = gates[gcol].fillna(False)
        for seg, msk in (("full", all_mask), ("is", is_mask), ("oos", oos_mask),
                         ("y2026", y26_mask)):
            rets = sleeve_returns(f, fwd[10], gate_on & msk)
            sleeves[f"{gcol}_{seg}_10_20bps"] = summarize(rets, 20)

    # ----- Sleeve pairwise correlation (bar-level sleeve returns) -----
    sleeve_bar_rets = {}
    for gcol in gate_cols:
        gate_on = gates[gcol].fillna(False)
        series = []
        for i in f.index:
            if gate_on[i] and not pd.isna(fwd[10][i]):
                series.append(fwd[10][i])
            else:
                series.append(None)
        sleeve_bar_rets[gcol] = pd.Series(series, index=f.index)
    sleeve_df = pd.DataFrame(sleeve_bar_rets)
    sleeve_corr = sleeve_df.corr()

    # ----- 2026 damage reduction (primary gate >=3, 10D 20bps) -----
    unfilt_2026_mean = ungated["y2026_10_20bps"].get("mean_pct", 0)
    gated3_2026_mean = gated_results["gt3"]["y2026_10_20bps"].get("mean_pct", 0)
    y2026_delta_pp = gated3_2026_mean - unfilt_2026_mean

    # ----- Verdict (PRIMARY = >=3 gates, OOS 10D 20bps) -----
    oos_stats = gated_results["gt3"]["oos_10_20bps"]
    oos_ci = oos_stats.get("ci95_pct", [0, 0])
    oos_lo_base = ungated["oos_10_20bps"].get("ci95_pct", [0, 0])[0]
    n_oos = oos_stats.get("n", 0); t_oos = oos_stats.get("t", 0)
    m_oos = oos_stats.get("mean_pct", 0)
    oos_improved = oos_ci[0] > oos_lo_base
    y2026_improved = y2026_delta_pp >= 1.0

    if n_oos == 0:
        verdict = "FAIL"; vr = ["no gated OOS signals"]
    elif (n_oos >= 15 and t_oos > 2.0 and m_oos > 0 and oos_ci[0] > 0
          and y2026_improved):
        verdict = "PASS"
        vr = [f"OOS n={n_oos} t={t_oos:.2f} mean={m_oos:.3f}% CI=[{oos_ci[0]:.3f},{oos_ci[1]:.3f}]",
              f"2026 damage reduction: {y2026_delta_pp:+.3f} pp (base {unfilt_2026_mean:+.3f}%, gated {gated3_2026_mean:+.3f}%)",
              f"OOS CI_lo {oos_ci[0]:+.3f} > base {oos_lo_base:+.3f}"]
    elif (n_oos >= 10 and m_oos > 0 and (oos_improved or y2026_improved)):
        verdict = "WEAK"
        vr = [f"OOS n={n_oos} t={t_oos:.2f} mean={m_oos:.3f}% CI=[{oos_ci[0]:.3f},{oos_ci[1]:.3f}]",
              f"2026 damage reduction: {y2026_delta_pp:+.3f} pp",
              f"improvement present but thin / CI-crossing"]
    else:
        verdict = "FAIL"
        vr = [f"OOS n={n_oos} t={t_oos:.2f} mean={m_oos:.3f}% CI=[{oos_ci[0]:.3f},{oos_ci[1]:.3f}]",
              f"2026 damage reduction: {y2026_delta_pp:+.3f} pp"]

    report = {
        "phase": "20_regime_gated",
        "today": dt.date.today().isoformat(),
        "data_range": [str(f.index[0]), str(f.index[-1])],
        "data_bars": len(f),
        "n_p15_entries": n_entries,
        "entries_by_gates_favorable_count": entries_by_gates,
        "ungated_baseline": ungated,
        "gated_gt2": gated_results["gt2"],
        "gated_gt3_PRIMARY": gated_results["gt3"],
        "gated_gt4": gated_results["gt4"],
        "gate_attribution_10d_20bps": gate_attribution,
        "gate_correlation_at_entries": corr_matrix.to_dict(),
        "standalone_sleeves_10d_20bps": sleeves,
        "sleeve_pairwise_correlation": sleeve_corr.to_dict(),
        "y2026_damage_reduction_pp": y2026_delta_pp,
        "verdict": verdict,
        "verdict_reasons": vr,
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=str))

    # ------------------------------ PRINT ------------------------------
    print("=" * 100)
    print(f"PHASE 20 - REGIME-GATED MEAN REVERSION SYSTEM  {dt.date.today()}")
    print("=" * 100)
    print(f"Data: ES=F {f.index[0]} -> {f.index[-1]} ({len(f)} bars)")
    print(f"P15 entries total: {n_entries}")
    print(f"Entries by #gates favorable: {entries_by_gates}")
    print()
    print("--- UNGATED P15 BASELINE (10D/20bps) ---")
    for seg in ("full", "is", "oos", "y2026"):
        s = ungated[f"{seg}_10_20bps"]
        if s.get("n", 0) == 0:
            print(f"  {seg:<6} n=0"); continue
        ci = s["ci95_pct"]
        print(f"  {seg:<6} n={s['n']:>3} mean={s['mean_pct']:+.3f}% hit={s['hit']:.3f} "
              f"t={s['t']:+.2f} CI=[{ci[0]:+.3f},{ci[1]:+.3f}] cum={s['cum_pct']:+.2f}% "
              f"maxDD={s['max_dd_pct']:+.2f}%")
    print()

    for thr, tag in [(3, "PRIMARY &gt;=3-of-4 GATES"), (2, "&gt;=2-of-4 GATES (diag)"), (4, "4-of-4 GATES (diag)")]:
        v = gated_results[f"gt{thr}"]
        print(f"--- {tag} retention={v['retention_pct']*100:.1f}% ({v['n_kept']}/{n_entries}) ---")
        for seg in ("full", "is", "oos", "y2026"):
            s = v[f"{seg}_10_20bps"]
            if s.get("n", 0) == 0:
                print(f"  {seg:<6} n=0"); continue
            ci = s["ci95_pct"]
            print(f"  {seg:<6} n={s['n']:>3} mean={s['mean_pct']:+.3f}% hit={s['hit']:.3f} "
                  f"t={s['t']:+.2f} CI=[{ci[0]:+.3f},{ci[1]:+.3f}] cum={s['cum_pct']:+.2f}% "
                  f"maxDD={s['max_dd_pct']:+.2f}%")
        print()

    print("--- GATE ATTRIBUTION (P15 entries, 10D/20bps) ---")
    for gcol, a in gate_attribution.items():
        f_s = a["favorable"]; u_s = a["unfavorable"]
        f_m = f_s.get("mean_pct", 0) if f_s.get("n", 0) > 0 else None
        u_m = u_s.get("mean_pct", 0) if u_s.get("n", 0) > 0 else None
        print(f"  {gcol:<24}  fav:n={a['n_fav']:>3} mean={f_m if f_m is not None else 'n/a':+.3f}%  "
              f"unf:n={a['n_unf']:>3} mean={u_m if u_m is not None else 'n/a':+.3f}%  "
              f"diff={(f_m - u_m) if (f_m is not None and u_m is not None) else 0:+.3f} pp")
    print()

    print("--- GATE ORTHOGONALITY AT ENTRY BARS ---")
    print(corr_matrix.round(3).to_string())
    print()

    print("--- STANDALONE SLEEVES (long ES when gate=True, 10D/20bps) ---")
    for gcol in gate_cols:
        print(f"  {gcol}:")
        for seg in ("full", "is", "oos", "y2026"):
            s = sleeves[f"{gcol}_{seg}_10_20bps"]
            if s.get("n", 0) == 0:
                print(f"    {seg:<6} n=0"); continue
            ci = s["ci95_pct"]
            print(f"    {seg:<6} n={s['n']:>4} mean={s['mean_pct']:+.3f}% hit={s['hit']:.3f} "
                  f"t={s['t']:+.2f} CI=[{ci[0]:+.3f},{ci[1]:+.3f}]")
    print()
    print("--- SLEEVE PAIRWISE RETURN CORRELATION ---")
    print(sleeve_corr.round(3).to_string())
    print()
    print(f"2026 damage reduction (gt3 vs ungated): {y2026_delta_pp:+.3f} pp")
    print(f"  (base 2026: {unfilt_2026_mean:+.3f}%, gated 2026: {gated3_2026_mean:+.3f}%)")
    print()
    print("-" * 100)
    print(f"VERDICT: {verdict}")
    for r in vr: print(f"  {r}")
    print("=" * 100)
    print(f"Report: {OUT_DIR / 'report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
