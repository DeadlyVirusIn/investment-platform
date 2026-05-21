"""Historical data extension feasibility audit + validation — read-only.

Probes yfinance for ES=F / SPY / ^GSPC deep history, then runs the
SAME TSMOM 60d + research_backfill_v1 stress filter (with proper
warmup) on each extended dataset and compares to the current
2018+ baseline.

Hard rules honored:
  - read-only DB / yfinance
  - NEVER mutates features_daily, context_daily, paper_*log, ml_*
  - NEVER changes thresholds
  - All-or-nothing per dataset (one continuous series per run)

Run:
    DATABASE_URL=postgresql+psycopg://... ./.venv/Scripts/python.exe \
        -m scripts.audit_data_extension
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from apps.api.src.research.regime_backfill import classify_pit


PERIODS_PER_YEAR = 252
TSMOM_HORIZON = 60
COST_BPS = 10.0
WARMUP_BARS = 200


def _sharpe(arr: Sequence[float]) -> float:
    a = [float(x) for x in arr if x is not None and math.isfinite(float(x))]
    if len(a) < 2: return float("nan")
    mu = sum(a) / len(a)
    try: sd = statistics.stdev(a)
    except statistics.StatisticsError: return float("nan")
    if sd == 0 or not math.isfinite(sd): return float("nan")
    return (mu / sd) * math.sqrt(PERIODS_PER_YEAR)


def _max_dd(arr: Sequence[float]) -> float:
    a = [float(x) for x in arr if x is not None and math.isfinite(float(x))]
    if not a: return 0.0
    eq = peak = 1.0; worst = 0.0
    for r in a:
        eq *= 1 + r; peak = max(peak, eq)
        worst = min(worst, (eq - peak) / peak)
    return worst * 100.0


def _summarize(label: str, rets: Sequence[float]) -> dict:
    a = np.asarray([r for r in rets if pd.notna(r)], dtype=float)
    if len(a) == 0:
        return {"label": label, "n": 0, "sharpe": None,
                "hit_pct": None, "total_pct": None,
                "max_dd_pct": 0.0, "mean_bps": None}
    return {
        "label": label,
        "n": int(len(a)),
        "sharpe": round(float(_sharpe(a)), 3),
        "hit_pct": round(float((a > 0).mean()) * 100, 2),
        "total_pct": round(float((1 + a).prod() - 1) * 100, 2),
        "max_dd_pct": round(float(_max_dd(a)), 2),
        "mean_bps": round(float(a.mean()) * 1e4, 2),
    }


def _print_table(rows: list[dict], cols: list[str]) -> None:
    if not rows:
        print("  (no rows)"); return
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows))
              for c in cols}
    fmt = "  " + "  ".join(f"{{:<{widths[c]}}}" for c in cols)
    print(fmt.format(*cols))
    for r in rows:
        print(fmt.format(*[str(r.get(c, "")) for c in cols]))


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def _fetch(symbol: str, start: str) -> pd.DataFrame:
    df = yf.Ticker(symbol).history(start=start, interval="1d",
                                          auto_adjust=False)
    if df.empty: return df
    df = df.rename(columns=str.lower)
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df = df[~df.index.duplicated(keep="last")]
    df = df.sort_index()
    df["ret"] = df["close"].pct_change()
    return df


def _gap_audit(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"n": 0, "first": None, "last": None,
                "gap_days_max": None, "gap_count_gt_5": None}
    diffs = (df.index.to_series().diff().dt.days.dropna().astype(int))
    return {
        "n": int(len(df)),
        "first": str(df.index[0].date()),
        "last": str(df.index[-1].date()),
        "gap_days_max": int(diffs.max()) if not diffs.empty else None,
        "gap_count_gt_5": int((diffs > 5).sum()),
        "gap_count_gt_10": int((diffs > 10).sum()),
    }


# --------------------------------------------------------------------------
# Strategy walk
# --------------------------------------------------------------------------

def _walk_filtered(closes: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (raw_tsmom_ret, filtered_ret, stress_label)."""
    cost = COST_BPS / 1e4
    cl = list(closes.values.astype(float))
    idx = closes.index
    n = len(cl)
    raw = [np.nan] * n
    filt = [np.nan] * n
    stress = [False] * n
    prev_raw = 0
    prev_filt = 0

    for t in range(n - 1):
        if t < WARMUP_BARS:
            continue
        # Stress label using PIT classification
        labels = classify_pit(idx[t].date(), cl[: t + 1])
        s_flag = bool(labels.stress_regime)
        stress[t] = s_flag

        a = cl[t - TSMOM_HORIZON]; b = cl[t]; c = cl[t + 1]
        if a == 0 or not all(np.isfinite([a, b, c])):
            prev_raw = 0; prev_filt = 0
            continue
        sig_raw = 1 if (b / a - 1.0) > 0 else 0
        r = c / b - 1.0
        applied_raw = sig_raw * r
        if sig_raw != prev_raw: applied_raw -= cost
        raw[t] = applied_raw
        prev_raw = sig_raw

        sig_filt = 0 if s_flag else sig_raw
        applied_filt = sig_filt * r
        if sig_filt != prev_filt: applied_filt -= cost
        filt[t] = applied_filt
        prev_filt = sig_filt

    return (pd.Series(raw, index=idx), pd.Series(filt, index=idx),
              pd.Series(stress, index=idx))


def _by_decade(closes: pd.Series, ret_filtered: pd.Series) -> list[dict]:
    df = pd.DataFrame({"ret": ret_filtered}).dropna()
    if df.empty: return []
    df["decade"] = (df.index.year // 10) * 10
    rows = []
    for d, sub in df.groupby("decade"):
        rows.append({"decade": f"{d}s",
                       **_summarize(str(d), sub["ret"].tolist())})
    return rows


def _by_year(closes: pd.Series, ret_filtered: pd.Series) -> list[dict]:
    df = pd.DataFrame({"ret": ret_filtered}).dropna()
    if df.empty: return []
    rows = []
    for yr, sub in df.groupby(df.index.year):
        rows.append({"year": int(yr),
                       **_summarize(str(yr), sub["ret"].tolist())})
    return rows


# --------------------------------------------------------------------------
# Stitching check (continuity / large daily jumps)
# --------------------------------------------------------------------------

def _continuity_check(df: pd.DataFrame) -> dict:
    if df.empty or "ret" not in df.columns:
        return {"large_moves_n": 0, "max_abs_ret_pct": None}
    rets = df["ret"].dropna()
    if rets.empty:
        return {"large_moves_n": 0, "max_abs_ret_pct": None}
    big = rets[rets.abs() >= 0.10]   # >10% daily move = check
    return {
        "large_moves_n": int(len(big)),
        "max_abs_ret_pct": round(float(rets.abs().max()) * 100, 3),
        "p99_abs_ret_pct": round(float(rets.abs().quantile(0.99)) * 100, 3),
    }


# --------------------------------------------------------------------------
# Runner per dataset
# --------------------------------------------------------------------------

def _run_dataset(label: str, symbol: str, start: str) -> dict:
    print(f"\n=== {label}  ({symbol}, start={start}) ===")
    df = _fetch(symbol, start)
    gap = _gap_audit(df)
    print(f"  bars={gap['n']}  range={gap['first']} -> {gap['last']}")
    print(f"  max_gap_days={gap['gap_days_max']}  "
            f"gaps>5d={gap['gap_count_gt_5']}  "
            f"gaps>10d={gap['gap_count_gt_10']}")
    if df.empty or len(df) < WARMUP_BARS + TSMOM_HORIZON + 50:
        return {"label": label, "symbol": symbol, "start": start,
                "gap_audit": gap, "ok": False,
                "reason": "insufficient bars"}

    cont = _continuity_check(df)
    print(f"  max_abs_daily_ret={cont['max_abs_ret_pct']}%  "
            f"p99={cont['p99_abs_ret_pct']}%  "
            f"|moves>=10%|: {cont['large_moves_n']}")

    closes = df["close"].astype(float)
    raw, filt, stress = _walk_filtered(closes)

    summary_raw  = _summarize(f"{label}_tsmom_raw", raw.dropna().tolist())
    summary_filt = _summarize(f"{label}_tsmom_filtered",
                                  filt.dropna().tolist())
    print(f"  TSMOM raw     : Sharpe={summary_raw['sharpe']}  "
            f"DD={summary_raw['max_dd_pct']}%  "
            f"total={summary_raw['total_pct']}%  n={summary_raw['n']}")
    print(f"  TSMOM filtered: Sharpe={summary_filt['sharpe']}  "
            f"DD={summary_filt['max_dd_pct']}%  "
            f"total={summary_filt['total_pct']}%  n={summary_filt['n']}")

    stress_pct = round(float(stress[stress].dropna().shape[0])
                          / max(1, stress.dropna().shape[0]) * 100, 2)
    print(f"  stress label fires on {stress_pct}% of valid days")

    by_dec = _by_decade(closes, filt)
    by_yr = _by_year(closes, filt)
    print("  --- by decade ---")
    _print_table(by_dec, ["decade", "n", "sharpe", "hit_pct",
                            "total_pct", "max_dd_pct"])

    return {
        "label": label, "symbol": symbol, "start": start,
        "gap_audit": gap, "continuity": cont,
        "tsmom_raw": summary_raw,
        "tsmom_filtered": summary_filt,
        "stress_label_pct": stress_pct,
        "by_decade": by_dec,
        "by_year": by_yr,
        "ok": True,
    }


# --------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------

def _compare(results: list[dict]) -> None:
    print("\n=== CROSS-DATASET COMPARISON (TSMOM filtered) ===")
    rows = []
    for r in results:
        if not r.get("ok"): continue
        s = r["tsmom_filtered"]
        rows.append({
            "dataset": r["label"],
            "symbol": r["symbol"],
            "start": r["gap_audit"]["first"],
            "end":   r["gap_audit"]["last"],
            "n_bars": r["gap_audit"]["n"],
            "stress_pct": r["stress_label_pct"],
            "sharpe": s["sharpe"],
            "max_dd_pct": s["max_dd_pct"],
            "total_pct": s["total_pct"],
            "hit_pct": s["hit_pct"],
        })
    _print_table(rows, ["dataset", "symbol", "start", "end", "n_bars",
                          "stress_pct", "sharpe", "max_dd_pct",
                          "total_pct", "hit_pct"])


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    print("=== Historical Data Extension Audit — read-only ===")
    print(f"Strategy: TSMOM 60d long-flat + research_backfill_v1 stress filter")
    print(f"Cost: {COST_BPS} bps round-trip on flips. Warmup: {WARMUP_BARS} bars.")

    datasets = [
        ("ES_2018_baseline",   "ES=F",  "2018-01-01"),
        ("ES_2008_extended",   "ES=F",  "2008-01-01"),
        ("ES_2001_full",       "ES=F",  "2001-01-01"),
        ("SPY_proxy_1995",     "SPY",   "1995-01-01"),
        ("GSPC_index_1990",    "^GSPC", "1990-01-01"),
    ]
    results: list[dict] = []
    for label, sym, start in datasets:
        try:
            results.append(_run_dataset(label, sym, start))
        except Exception as e:
            print(f"  ERROR running {label}: {e}")
            results.append({"label": label, "symbol": sym, "start": start,
                             "ok": False, "reason": str(e)})

    _compare(results)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path("artifacts") / "data_extension" / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_utc": ts,
        "params": {
            "tsmom_horizon": TSMOM_HORIZON, "cost_bps": COST_BPS,
            "warmup_bars": WARMUP_BARS,
        },
        "results": results,
    }
    (out_dir / "audit.json").write_text(json.dumps(payload, indent=2,
                                                          default=str))
    print(f"\nArtifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
