"""Phase 12 — Price Action + Compression framework (multi-variant).

Deterministic signal framework. No discretionary logic. No Fibonacci drawing.
No parameter tuning after results.

Universe:
    primary      = ES=F (E-mini S&P 500 continuous front-month, yfinance)
    confirmation = SPY  (DB price_bar)

Variants:
    A: pure compression + breakout
    B: + trend alignment
    C: + pullback context
    D: + ES/SPY cross-asset confirmation
    E: all: pullback + compression + trend + confirmation

Parameters are FROZEN before results:
    compression:      inside_bar OR range_compression (TR < 0.8 * avg_TR_10)
    breakout lookback: 5 and 10 bars (run both, report both)
    trend MA:          20 and 50 (run both, report both)
    pullback window:   5 bars
    confirmation:      same-sign return over 3-bar lookback on both ES and SPY
    hold windows:      1, 3, 5, 10, 20 bars
    costs:             10 bps + 20 bps round-trip (existing model)

Outputs: per-variant, per-config event counts, hit, mean/median, t-stat,
bootstrap CI, sequential equity + max-drawdown, cross-variant comparison,
regime splits, signal-quality splits, confirmation splits, trend splits.

Verdict per variant at 10D/20bps with 5-bar breakout, 20MA trend, against
consolidated direction (long+short pooled via sign-flip on short returns).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import yfinance as yf
from loguru import logger
from sqlalchemy import text

from apps.api.src.db import SessionLocal

# Frozen parameters
COMP_TR_FACTOR      = 0.8
COMP_TR_WINDOW      = 10
BREAKOUT_LOOKBACKS  = (5, 10)
TREND_MA_WINDOWS    = (20, 50)
PULLBACK_WINDOW     = 5
CONFIRM_LOOKBACK    = 3
HOLD_WINDOWS        = (1, 3, 5, 10, 20)
COST_BPS            = (10, 20)
ATR_VOL_WINDOW      = 20
REGIME_MA           = 200
SIGNAL_QUALITY_QUANTILE = 0.5  # strong vs weak median split

OUT_DIR = Path("artifacts/phase12")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------
def fetch_es_daily(start="2020-01-01") -> pd.DataFrame:
    """Fetch continuous front-month ES (E-mini S&P) daily OHLC via yfinance."""
    t = yf.Ticker("ES=F")
    df = t.history(start=start, interval="1d", auto_adjust=False)
    if df.empty:
        raise RuntimeError("ES=F fetch returned no data")
    df = df.rename(columns=str.lower)
    df.index = [i.date() for i in df.index]
    df = df[["open", "high", "low", "close", "volume"]].copy()
    df = df[~df.index.duplicated(keep="last")]
    return df.sort_index()


def load_spy_from_db() -> pd.DataFrame:
    with SessionLocal() as s:
        rows = s.execute(text("""
            SELECT pb.ts, pb.open, pb.high, pb.low, pb.close, pb.volume
            FROM price_bar pb JOIN asset a ON a.id = pb.asset_id
            WHERE a.symbol='SPY' AND pb.timeframe='1d'
            ORDER BY pb.ts
        """)).all()
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["date"] = df["ts"].apply(lambda t: t.date())
    df = df[["date", "open", "high", "low", "close", "volume"]]
    df.set_index("date", inplace=True)
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].astype(float)
    df = df[~df.index.duplicated(keep="last")]
    return df.sort_index()


# ---------------------------------------------------------------------------
# Feature engineering (deterministic)
# ---------------------------------------------------------------------------
def true_range(df: pd.DataFrame) -> pd.Series:
    high = df["high"]; low = df["low"]; prev_close = df["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["tr"] = true_range(out)
    out["atr10"] = out["tr"].rolling(COMP_TR_WINDOW).mean()
    out["atr20"] = out["tr"].rolling(ATR_VOL_WINDOW).mean()

    # Compression flags
    out["inside_bar"] = (
        (out["high"] < out["high"].shift(1)) &
        (out["low"]  > out["low"].shift(1))
    )
    out["range_compress"] = out["tr"] < (COMP_TR_FACTOR * out["atr10"])
    out["compression"] = out["inside_bar"] | out["range_compress"]

    # Breakout (per lookback) — evaluated on current-bar close vs prior rolling
    for lb in BREAKOUT_LOOKBACKS:
        prior_hi = out["high"].shift(1).rolling(lb).max()
        prior_lo = out["low"].shift(1).rolling(lb).min()
        out[f"bo_up_{lb}"]   = out["close"] > prior_hi
        out[f"bo_down_{lb}"] = out["close"] < prior_lo

    # Trend alignment (per MA)
    for ma in TREND_MA_WINDOWS:
        out[f"ma_{ma}"] = out["close"].rolling(ma).mean()
        out[f"trend_up_{ma}"]   = out["close"] > out[f"ma_{ma}"]
        out[f"trend_down_{ma}"] = out["close"] < out[f"ma_{ma}"]

    # Pullback context (MA20 touch within PULLBACK_WINDOW bars, then recover)
    ma20 = out["ma_20"]
    touched_below = (out["low"]  <= ma20).rolling(PULLBACK_WINDOW).sum() > 0
    touched_above = (out["high"] >= ma20).rolling(PULLBACK_WINDOW).sum() > 0
    out["pullback_long_ctx"]  = touched_below & (out["close"] > ma20)
    out["pullback_short_ctx"] = touched_above & (out["close"] < ma20)

    # Market regime (vs 200-MA on close)
    out[f"ma_{REGIME_MA}"] = out["close"].rolling(REGIME_MA).mean()
    out[f"regime_bull"] = out["close"] > out[f"ma_{REGIME_MA}"]
    out[f"regime_high_vol"] = out["atr20"] > out["atr20"].rolling(60).median()
    return out


def add_confirmation(es: pd.DataFrame, spy: pd.DataFrame) -> pd.DataFrame:
    """Add same-sign confirmation flag over CONFIRM_LOOKBACK bars."""
    es = es.copy()
    spy_close = spy["close"].reindex(es.index).ffill()
    es_ret3 = es["close"].pct_change(CONFIRM_LOOKBACK)
    spy_ret3 = spy_close.pct_change(CONFIRM_LOOKBACK)
    es["conf_long"]  = (es_ret3 > 0) & (spy_ret3 > 0)
    es["conf_short"] = (es_ret3 < 0) & (spy_ret3 < 0)
    return es


# ---------------------------------------------------------------------------
# Signal generation
# ---------------------------------------------------------------------------
def generate_signals(
    feat: pd.DataFrame, *, breakout_lb: int, trend_ma: int,
) -> dict[str, pd.DataFrame]:
    """Return dict variant_name -> DataFrame with 'long' / 'short' bool columns."""
    bo_up = feat[f"bo_up_{breakout_lb}"]
    bo_dn = feat[f"bo_down_{breakout_lb}"]
    trend_up   = feat[f"trend_up_{trend_ma}"]
    trend_down = feat[f"trend_down_{trend_ma}"]
    comp = feat["compression"]
    pl_long  = feat["pullback_long_ctx"]
    pl_short = feat["pullback_short_ctx"]
    cl, cs = feat["conf_long"], feat["conf_short"]

    variants: dict[str, pd.DataFrame] = {}

    variants["A"] = pd.DataFrame({
        "long":  comp & bo_up,
        "short": comp & bo_dn,
    })
    variants["B"] = pd.DataFrame({
        "long":  comp & bo_up & trend_up,
        "short": comp & bo_dn & trend_down,
    })
    variants["C"] = pd.DataFrame({
        "long":  trend_up   & pl_long  & comp & bo_up,
        "short": trend_down & pl_short & comp & bo_dn,
    })
    variants["D"] = pd.DataFrame({
        "long":  comp & bo_up & trend_up   & cl,
        "short": comp & bo_dn & trend_down & cs,
    })
    variants["E"] = pd.DataFrame({
        "long":  trend_up   & pl_long  & comp & bo_up & cl,
        "short": trend_down & pl_short & comp & bo_dn & cs,
    })
    return variants


# ---------------------------------------------------------------------------
# Trade construction + stats
# ---------------------------------------------------------------------------
def compute_forward_returns(feat: pd.DataFrame, windows: tuple[int, ...]) -> dict[int, pd.Series]:
    out: dict[int, pd.Series] = {}
    for N in windows:
        # Entry at next bar OPEN after signal close; exit at close of bar N.
        # Conservative: use next-bar open.
        entry = feat["open"].shift(-1)
        exit_ = feat["close"].shift(-N)
        out[N] = (exit_ - entry) / entry
    return out


def _bootstrap_ci(xs: list[float], *, n_boot=5000, conf=0.95) -> tuple[float, float]:
    if not xs:
        return (0.0, 0.0)
    rng = random.Random(42)
    n = len(xs)
    means = [sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot)]
    means.sort()
    return (means[int((1 - conf) / 2 * n_boot)],
            means[int((1 - (1 - conf) / 2) * n_boot) - 1])


def summarize(returns: list[float], *, bps: float) -> dict:
    if not returns:
        return {"n": 0}
    cost = bps / 1e4
    rn = [r - cost for r in returns]
    n = len(rn)
    mean = st.mean(rn); med = st.median(rn)
    sd = st.pstdev(rn) if n > 1 else 0.0
    wins = sum(1 for r in rn if r > 0)
    t = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
    ci_lo, ci_hi = _bootstrap_ci(rn)
    eq = 1.0; path = []
    for r in rn:
        eq *= (1 + r); path.append(eq)
    pk = path[0] if path else 1.0; maxdd = 0.0
    for v in path:
        pk = max(pk, v)
        maxdd = min(maxdd, (v - pk) / pk)
    return {
        "n": n, "cost_bps": bps,
        "mean_pct": mean * 100, "median_pct": med * 100,
        "std_pct": sd * 100, "hit_rate": wins / n, "t_stat": t,
        "ci95_mean_pct": [ci_lo * 100, ci_hi * 100],
        "cumulative_pct": (path[-1] - 1) * 100 if path else 0.0,
        "max_dd_pct": maxdd * 100,
        "mean_gross_pct": st.mean(returns) * 100,
    }


def pooled_returns(
    signal_df: pd.DataFrame, fwd_rets: pd.Series,
) -> list[float]:
    """Combine long + short signals, sign-flipping short returns.
    Returns a list of trade returns (one per signal bar).
    """
    longs = signal_df["long"] & fwd_rets.notna()
    shorts = signal_df["short"] & fwd_rets.notna()
    long_rets  = fwd_rets[longs].tolist()
    short_rets = [-r for r in fwd_rets[shorts].tolist()]
    return long_rets + short_rets


def split_returns(
    signal_df: pd.DataFrame, fwd_rets: pd.Series, mask: pd.Series,
) -> list[float]:
    """Pooled long+short returns restricted to rows where mask is True."""
    longs  = signal_df["long"]  & fwd_rets.notna() & mask
    shorts = signal_df["short"] & fwd_rets.notna() & mask
    return fwd_rets[longs].tolist() + [-r for r in fwd_rets[shorts].tolist()]


def long_short_split(
    signal_df: pd.DataFrame, fwd_rets: pd.Series,
) -> tuple[list[float], list[float]]:
    longs  = fwd_rets[signal_df["long"]  & fwd_rets.notna()].tolist()
    shorts = [-r for r in fwd_rets[signal_df["short"] & fwd_rets.notna()].tolist()]
    return longs, shorts


# ---------------------------------------------------------------------------
# Variant evaluation
# ---------------------------------------------------------------------------
def evaluate_variant(
    variant_name: str, signal_df: pd.DataFrame, feat: pd.DataFrame,
    fwd_rets: dict[int, pd.Series],
) -> dict:
    """Per-window, per-cost summary + diagnostic splits."""
    v_out: dict = {"variant": variant_name,
                   "counts": {
                       "n_long_signals":  int(signal_df["long"].sum()),
                       "n_short_signals": int(signal_df["short"].sum()),
                   },
                   "per_window": {}}

    # Per-window pooled
    for N in HOLD_WINDOWS:
        ret_series = fwd_rets[N]
        pooled = pooled_returns(signal_df, ret_series)
        per_cost = {
            f"{b}bps": summarize(pooled, bps=b) for b in COST_BPS
        }
        # Long-only vs Short-only
        long_rets, short_rets = long_short_split(signal_df, ret_series)
        long_stat  = summarize(long_rets,  bps=20)
        short_stat = summarize(short_rets, bps=20)
        v_out["per_window"][str(N)] = {
            "pooled": per_cost,
            "long_only_20bps": long_stat,
            "short_only_20bps": short_stat,
        }

    # Diagnostic splits at primary window (10D, 20bps pooled)
    N = 10; bps = 20.0
    ret10 = fwd_rets[N]
    diag: dict = {}

    # Regime splits (bull vs bear, high-vol vs low-vol)
    bull = feat["regime_bull"].fillna(False)
    hv = feat["regime_high_vol"].fillna(False)
    for label, mask in [("bull_trend", bull),
                        ("bear_trend", ~bull),
                        ("high_vol", hv),
                        ("low_vol", ~hv)]:
        rs = split_returns(signal_df, ret10, mask)
        diag[f"regime_{label}"] = summarize(rs, bps=bps)

    # Signal-quality splits — use SIGNAL-SUBSET median so strong/weak are
    # relative to the signals themselves (not the full series, which would
    # make all signals "strong" by construction when compression is required).
    signal_mask = signal_df["long"] | signal_df["short"]
    comp_strength = (feat["atr10"] - feat["tr"]) / feat["atr10"]
    comp_med = comp_strength[signal_mask].median()
    strong_comp = comp_strength > comp_med
    weak_comp   = comp_strength <= comp_med
    diag["comp_strong"] = summarize(split_returns(signal_df, ret10, strong_comp), bps=bps)
    diag["comp_weak"]   = summarize(split_returns(signal_df, ret10, weak_comp),   bps=bps)

    # Breakout strength — distance beyond prior 5-bar extreme, normalized by ATR10
    prior_max5 = feat["high"].shift(1).rolling(5).max()
    prior_min5 = feat["low"].shift(1).rolling(5).min()
    bo_up_strength = (feat["close"] - prior_max5) / feat["atr10"]
    bo_dn_strength = (prior_min5 - feat["close"]) / feat["atr10"]
    bo_strength = bo_up_strength.where(signal_df["long"], bo_dn_strength)
    bo_med = bo_strength[signal_mask].median()
    strong_bo = bo_strength > bo_med
    weak_bo   = (bo_strength <= bo_med) & bo_strength.notna()
    diag["breakout_strong"] = summarize(split_returns(signal_df, ret10, strong_bo), bps=bps)
    diag["breakout_weak"]   = summarize(split_returns(signal_df, ret10, weak_bo),   bps=bps)

    # Confirmation splits (with and without alignment)
    with_conf = (
        (signal_df["long"]  & feat["conf_long"]) |
        (signal_df["short"] & feat["conf_short"])
    )
    diag["with_conf"]  = summarize(split_returns(signal_df, ret10, with_conf),  bps=bps)
    diag["without_conf"] = summarize(split_returns(signal_df, ret10, ~with_conf), bps=bps)

    # Trend-aligned vs countertrend
    trend_aligned = (
        (signal_df["long"]  & feat["trend_up_20"]) |
        (signal_df["short"] & feat["trend_down_20"])
    )
    diag["trend_aligned"]   = summarize(split_returns(signal_df, ret10, trend_aligned),  bps=bps)
    diag["countertrend"] = summarize(split_returns(signal_df, ret10, ~trend_aligned), bps=bps)

    v_out["diagnostic_splits_10d_20bps"] = diag

    # Variant-level verdict on primary config (10D pooled, 20bps)
    primary = v_out["per_window"]["10"]["pooled"]["20bps"]
    v_out["verdict"] = _variant_verdict(primary)
    return v_out


def _variant_verdict(primary: dict) -> dict:
    if primary.get("n", 0) == 0:
        return {"verdict": "FAIL", "reason": "no trades"}
    n = primary["n"]; t = primary["t_stat"]; m = primary["mean_pct"]
    lo, hi = primary["ci95_mean_pct"]
    if n >= 30 and t > 2.0 and m > 0 and lo > 0:
        return {"verdict": "PASS", "detail":
                f"n={n} t={t:.2f} mean={m:.3f}% CI=[{lo:.3f},{hi:.3f}]"}
    if n >= 15 and (t > 1.0 or (m > 0 and hi > 0)):
        return {"verdict": "WEAK", "detail":
                f"n={n} t={t:.2f} mean={m:.3f}% CI=[{lo:.3f},{hi:.3f}]"}
    return {"verdict": "FAIL", "detail":
            f"n={n} t={t:.2f} mean={m:.3f}% CI=[{lo:.3f},{hi:.3f}]"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2020-01-01")
    args = p.parse_args()

    logger.info("[p12] fetching ES=F from yfinance...")
    es = fetch_es_daily(start=args.start)
    logger.info("[p12] ES=F bars: {} ({} -> {})", len(es), es.index[0], es.index[-1])

    logger.info("[p12] loading SPY from DB...")
    spy = load_spy_from_db()
    logger.info("[p12] SPY bars: {} ({} -> {})", len(spy), spy.index[0], spy.index[-1])

    # Align ES to common date range with SPY; dedupe as defensive guard
    es = es[~es.index.duplicated(keep="last")].sort_index()
    spy = spy[~spy.index.duplicated(keep="last")].sort_index()
    common = es.index.intersection(spy.index)
    es = es.loc[common]
    spy = spy.loc[common]
    logger.info("[p12] common range: {} bars ({} -> {})",
                len(es), es.index[0], es.index[-1])

    feat = build_features(es)
    feat = add_confirmation(feat, spy)
    fwd_rets = compute_forward_returns(feat, HOLD_WINDOWS)

    # Grid: breakout_lb × trend_ma (2 × 2 = 4 configs).
    # Primary config for verdict = (5, 20). Others reported for robustness.
    all_results: dict = {
        "params": {
            "comp_tr_factor": COMP_TR_FACTOR, "comp_tr_window": COMP_TR_WINDOW,
            "breakout_lookbacks": list(BREAKOUT_LOOKBACKS),
            "trend_mas": list(TREND_MA_WINDOWS),
            "pullback_window": PULLBACK_WINDOW,
            "confirm_lookback": CONFIRM_LOOKBACK,
            "hold_windows": list(HOLD_WINDOWS),
            "cost_bps": list(COST_BPS),
            "entry_rule": "next_bar_open",
            "exit_rule": "close_at_N_bars",
        },
        "data": {
            "es_start": str(es.index[0]), "es_end": str(es.index[-1]),
            "n_bars": len(es),
        },
        "configs": {},
    }

    for lb in BREAKOUT_LOOKBACKS:
        for ma in TREND_MA_WINDOWS:
            key = f"bo{lb}_ma{ma}"
            variants = generate_signals(feat, breakout_lb=lb, trend_ma=ma)
            config_out = {}
            for vname in ("A", "B", "C", "D", "E"):
                config_out[vname] = evaluate_variant(
                    vname, variants[vname], feat, fwd_rets,
                )
            all_results["configs"][key] = config_out

    # Cross-variant comparison — primary (5,20) at 10D 20bps pooled
    primary_key = "bo5_ma20"
    comparison_rows = []
    for vname in ("A", "B", "C", "D", "E"):
        pr = all_results["configs"][primary_key][vname]
        summ = pr["per_window"]["10"]["pooled"]["20bps"]
        comparison_rows.append({
            "variant": vname,
            "n_long": pr["counts"]["n_long_signals"],
            "n_short": pr["counts"]["n_short_signals"],
            "n_trades": summ.get("n", 0),
            "mean_pct": summ.get("mean_pct"),
            "median_pct": summ.get("median_pct"),
            "hit_rate": summ.get("hit_rate"),
            "t_stat": summ.get("t_stat"),
            "ci95_pct": summ.get("ci95_mean_pct"),
            "cumret_pct": summ.get("cumulative_pct"),
            "max_dd_pct": summ.get("max_dd_pct"),
            "verdict": pr["verdict"]["verdict"],
        })
    all_results["cross_variant_comparison_primary_config_10d_20bps"] = comparison_rows

    (OUT_DIR / "report.json").write_text(
        json.dumps(all_results, indent=2, default=str)
    )

    # Human-readable output
    print("=" * 90)
    print(f"PHASE 12 — PRICE ACTION + COMPRESSION FRAMEWORK ({dt.date.today()})")
    print("=" * 90)
    print(f"ES=F bars: {len(es)}  range: {es.index[0]} -> {es.index[-1]}")
    print(f"SPY bars:  {len(spy)}")
    print()
    print(f"Primary config for verdict: breakout_lb=5, trend_ma=20, hold=10D, cost=20bps")
    print()
    print("--- Cross-variant comparison (primary config, 10D, 20bps) ---")
    print(f"{'V':>2} {'n_L':>5} {'n_S':>5} {'n':>5} {'mean%':>8} {'med%':>7} "
          f"{'hit':>5} {'t':>6} {'CI95% (20bps)':<24} {'cum%':>8} {'maxDD%':>7} {'verd':>6}")
    for r in comparison_rows:
        ci = r["ci95_pct"] or [0, 0]
        print(f"{r['variant']:>2} {r['n_long']:>5} {r['n_short']:>5} "
              f"{r['n_trades']:>5} "
              f"{(r['mean_pct'] or 0):>+8.3f} {(r['median_pct'] or 0):>+7.3f} "
              f"{(r['hit_rate'] or 0):>5.3f} {(r['t_stat'] or 0):>+6.2f} "
              f"[{ci[0]:+.3f},{ci[1]:+.3f}]   "
              f"{(r['cumret_pct'] or 0):>+8.2f} {(r['max_dd_pct'] or 0):>+7.2f} "
              f"{r['verdict']:>6}")
    print()

    for vname in ("A", "B", "C", "D", "E"):
        print(f"\n========== VARIANT {vname} — full sweep (primary config bo5_ma20) ==========")
        pr = all_results["configs"][primary_key][vname]
        print(f"counts: long={pr['counts']['n_long_signals']}  "
              f"short={pr['counts']['n_short_signals']}")
        print(f"{'N':>3} {'n':>4} {'gross%':>8} {'net10%':>8} {'net20%':>8} "
              f"{'hit':>5} {'t(20)':>6} {'CI95 20bps':<22} {'maxDD%':>7}")
        for N in HOLD_WINDOWS:
            p10 = pr["per_window"][str(N)]["pooled"]["10bps"]
            p20 = pr["per_window"][str(N)]["pooled"]["20bps"]
            if p20.get("n", 0) == 0:
                continue
            ci = p20["ci95_mean_pct"]
            print(f"{N:>3} {p20['n']:>4} {p20['mean_gross_pct']:>+8.3f} "
                  f"{p10['mean_pct']:>+8.3f} {p20['mean_pct']:>+8.3f} "
                  f"{p20['hit_rate']:>5.3f} {p20['t_stat']:>+6.2f} "
                  f"[{ci[0]:+.3f},{ci[1]:+.3f}]  {p20['max_dd_pct']:>+7.2f}")
        print()
        diag = pr["diagnostic_splits_10d_20bps"]
        print("  --- diagnostic splits @ 10D/20bps pooled ---")
        for k in ("regime_bull_trend", "regime_bear_trend",
                  "regime_high_vol", "regime_low_vol",
                  "comp_strong", "comp_weak",
                  "breakout_strong", "breakout_weak",
                  "with_conf", "without_conf",
                  "trend_aligned", "countertrend"):
            s = diag.get(k, {})
            if s.get("n", 0) == 0:
                print(f"  {k:<20}  n=0")
                continue
            ci = s["ci95_mean_pct"]
            print(f"  {k:<20}  n={s['n']:>3}  mean={s['mean_pct']:+.3f}%  "
                  f"hit={s['hit_rate']:.3f}  t={s['t_stat']:+.2f}  "
                  f"CI=[{ci[0]:+.3f},{ci[1]:+.3f}]")
        print(f"  VARIANT {vname} VERDICT: {pr['verdict']}")

    # Robustness across 4 config-grid points
    print("\n" + "=" * 90)
    print("CROSS-CONFIG ROBUSTNESS (10D/20bps pooled)")
    print("=" * 90)
    print(f"{'config':<12}  ", end="")
    for vname in ("A", "B", "C", "D", "E"):
        print(f"{vname:>18}", end="")
    print()
    for k, cfg_res in all_results["configs"].items():
        print(f"{k:<12}  ", end="")
        for vname in ("A", "B", "C", "D", "E"):
            s = cfg_res[vname]["per_window"]["10"]["pooled"]["20bps"]
            if s.get("n", 0) == 0:
                cell = "  (n=0)"
            else:
                cell = (f"n={s['n']:>3} m={s['mean_pct']:+.2f}% "
                        f"t={s['t_stat']:+.2f}")
            print(f"{cell:>18}", end="")
        print()

    print()
    print(f"Report: {OUT_DIR / 'report.json'}")
    print("=" * 90)
    return 0


if __name__ == "__main__":
    sys.exit(main())
