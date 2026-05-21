"""Engine B alpha audit — deterministic only. Read-only. No ML.

Phases:
  1. Engine B trade distribution + decile breakdown
  2. Alignment with TSMOM / MA / vol at entry
  3. Replacement simulation (kill B, swap B for TSMOM 60d / blended)
  4. Gating simulation (B only when TSMOM agrees / vol gate / both)
  5. Recommendation summary

Run:
    DATABASE_URL=postgresql+psycopg://... ./.venv/Scripts/python.exe \\
        -m scripts.engine_b_audit
"""

from __future__ import annotations

import math
import sys
from collections.abc import Sequence

import numpy as np
import pandas as pd
from sqlalchemy import text

from apps.api.src.db import SessionLocal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sharpe(returns: Sequence[float], periods_per_year: float = 252) -> float:
    arr = np.asarray([r for r in returns if pd.notna(r)], dtype=float)
    if len(arr) < 2:
        return float("nan")
    mu, sd = float(arr.mean()), float(arr.std(ddof=1))
    if sd == 0 or not np.isfinite(sd):
        return float("nan")
    return mu / sd * math.sqrt(periods_per_year)


def _hit(returns: Sequence[float]) -> float:
    arr = np.asarray([r for r in returns if pd.notna(r)], dtype=float)
    return float((arr > 0).mean()) if len(arr) else float("nan")


def _max_dd(returns: Sequence[float]) -> float:
    arr = np.asarray([r for r in returns if pd.notna(r)], dtype=float)
    if len(arr) == 0:
        return 0.0
    eq = (1.0 + arr).cumprod()
    peak = np.maximum.accumulate(eq)
    return float((eq - peak).min() / peak.max() * 100.0)


def _summarize(label: str, returns: Sequence[float]) -> dict:
    arr = np.asarray([r for r in returns if pd.notna(r)], dtype=float)
    if len(arr) == 0:
        return {"label": label, "n": 0}
    return {
        "label": label,
        "n": int(len(arr)),
        "sharpe": round(_sharpe(arr), 3),
        "hit_pct": round(_hit(arr) * 100, 2),
        "total_pct": round(float((1 + arr).prod() - 1) * 100, 2),
        "best_pct": round(float(arr.max()) * 100, 2),
        "worst_pct": round(float(arr.min()) * 100, 2),
        "mean_bps": round(float(arr.mean()) * 1e4, 2),
        "stdev_bps": round(float(arr.std(ddof=1)) * 1e4, 2),
        "skew": round(float(pd.Series(arr).skew()), 3),
        "max_dd_pct": round(_max_dd(arr), 2),
    }


def _print_table(rows: list[dict], cols: list[str]) -> None:
    if not rows:
        print("  (no rows)")
        return
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows))
              for c in cols}
    fmt = "  " + "  ".join(f"{{:<{widths[c]}}}" for c in cols)
    print(fmt.format(*cols))
    for r in rows:
        print(fmt.format(*[str(r.get(c, "")) for c in cols]))


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _load_b_trades(session) -> pd.DataFrame:
    rows = session.execute(text("""
        SELECT entry_date, exit_date, net_ret_pct, gross_ret_pct,
               regime_at_entry, position_size_pct
        FROM paper_trade_log
        WHERE status='closed'
          AND engine='B'
          AND net_ret_pct IS NOT NULL
        ORDER BY entry_date
    """)).mappings().all()
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["entry_date"] = pd.to_datetime(df["entry_date"]).dt.normalize()
    df["net_ret"] = df["net_ret_pct"].astype(float) / 100.0
    return df


def _load_es_bars() -> pd.DataFrame:
    from scripts.run_phase12_price_action import fetch_es_daily
    df = fetch_es_daily(start="2018-01-01")
    df = df.copy()
    df.index = pd.to_datetime(df.index).normalize()
    df["ret"] = df["close"].pct_change()
    return df


def _enrich_signals(trades: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """For each Engine B entry date, compute TSMOM/MA/vol signals
    using PRIOR bars only (no lookahead)."""
    if trades.empty:
        return trades
    out = trades.copy()
    bars_idx = bars.index
    n = len(out)
    tsmom20 = np.full(n, np.nan)
    tsmom60 = np.full(n, np.nan)
    tsmom120 = np.full(n, np.nan)
    ma_signal = np.full(n, np.nan)
    rvol20 = np.full(n, np.nan)
    rvol60 = np.full(n, np.nan)

    for i, ed in enumerate(out["entry_date"]):
        # Use bars STRICTLY before entry_date
        mask = bars_idx < ed
        if mask.sum() < 121:
            continue
        prior = bars.loc[mask]
        c = prior["close"]
        r = prior["ret"].dropna()
        # TSMOM = (close_t / close_{t-h}) - 1, sign
        tsmom20[i]  = float(c.iloc[-1] / c.iloc[-21] - 1.0)
        tsmom60[i]  = float(c.iloc[-1] / c.iloc[-61] - 1.0)
        tsmom120[i] = float(c.iloc[-1] / c.iloc[-121] - 1.0)
        # MA50/200
        if len(c) >= 200:
            ma50  = c.iloc[-50:].mean()
            ma200 = c.iloc[-200:].mean()
            ma_signal[i] = 1.0 if ma50 > ma200 else 0.0
        # Realized vol
        if len(r) >= 60:
            rvol20[i] = float(r.iloc[-20:].std() * math.sqrt(252))
            rvol60[i] = float(r.iloc[-60:].std() * math.sqrt(252))

    out["tsmom_20"]  = tsmom20
    out["tsmom_60"]  = tsmom60
    out["tsmom_120"] = tsmom120
    out["ma_long"]   = ma_signal
    out["rvol_20"]   = rvol20
    out["rvol_60"]   = rvol60
    return out


# ---------------------------------------------------------------------------
# Phase 1 — Engine B distribution + decile breakdown
# ---------------------------------------------------------------------------

def phase1(b: pd.DataFrame) -> None:
    print("\n=== PHASE 1 — Engine B distribution ===")
    s = _summarize("engine_B_all", b["net_ret"].tolist())
    print(f"  n={s['n']}  sharpe={s['sharpe']}  hit%={s['hit_pct']}  "
          f"total%={s['total_pct']}  worst%={s['worst_pct']}  "
          f"best%={s['best_pct']}  skew={s['skew']}  "
          f"maxDD%={s['max_dd_pct']}")
    # Deciles
    deciles = pd.qcut(b["net_ret"], 10, labels=False, duplicates="drop")
    rows = []
    for q in sorted(deciles.unique()):
        mask = deciles == q
        avg_ret = float(b.loc[mask, "net_ret"].mean()) * 100.0
        rows.append({
            "decile": int(q + 1), "n": int(mask.sum()),
            "avg_ret%": round(avg_ret, 3),
            "min%": round(float(b.loc[mask, "net_ret"].min()) * 100, 3),
            "max%": round(float(b.loc[mask, "net_ret"].max()) * 100, 3),
        })
    _print_table(rows, ["decile", "n", "avg_ret%", "min%", "max%"])


# ---------------------------------------------------------------------------
# Phase 2 — Alignment buckets
# ---------------------------------------------------------------------------

def phase2(b: pd.DataFrame) -> None:
    print("\n=== PHASE 2 — Alignment with TSMOM / MA / vol ===")
    if b.empty or b["tsmom_60"].notna().sum() == 0:
        print("  no enriched signals")
        return
    bb = b.dropna(subset=["tsmom_60", "rvol_20"])
    print(f"  enriched_n={len(bb)}")

    splits = [
        ("tsmom_20_pos", bb["tsmom_20"] > 0),
        ("tsmom_60_pos", bb["tsmom_60"] > 0),
        ("tsmom_120_pos", bb["tsmom_120"] > 0),
        ("ma_long",       bb["ma_long"] > 0.5),
        ("vol_low (rvol_20 < 0.18)", bb["rvol_20"] < 0.18),
        ("vol_high (rvol_20 >= 0.25)", bb["rvol_20"] >= 0.25),
        ("agree_20_AND_60", (bb["tsmom_20"] > 0) & (bb["tsmom_60"] > 0)),
        ("agree_60_AND_MA", (bb["tsmom_60"] > 0) & (bb["ma_long"] > 0.5)),
        ("disagree_60",   bb["tsmom_60"] <= 0),
    ]
    rows = []
    for name, mask in splits:
        sub = bb.loc[mask]
        s_in = _summarize(name, sub["net_ret"].tolist())
        rows.append({
            "bucket": name,
            "n": s_in.get("n", 0),
            "sharpe": s_in.get("sharpe", "—"),
            "hit%": s_in.get("hit_pct", "—"),
            "mean_bps": s_in.get("mean_bps", "—"),
            "worst%": s_in.get("worst_pct", "—"),
        })
    _print_table(rows, ["bucket", "n", "sharpe", "hit%", "mean_bps",
                          "worst%"])


# ---------------------------------------------------------------------------
# Phase 3 — Replacement simulation
# ---------------------------------------------------------------------------

def phase3(b: pd.DataFrame, bars: pd.DataFrame) -> None:
    print("\n=== PHASE 3 — Replacement simulation ===")
    # Build a TSMOM 60d long-flat strategy on the same bar series.
    # Then count "trades" the same way: 1-bar holds entered each day the
    # signal flips on. For a fair comparison vs Engine B's own per-trade
    # net returns, we sample the TSMOM strategy on Engine B's *entry
    # dates* and use a 1-day forward net return - 5bps cost to mimic
    # Engine B's 1-day hold convention.
    cost_frac = 10.0 / 1e4   # 10bps round-trip
    b_dates = pd.DatetimeIndex(b["entry_date"]).unique()
    bars_idx = bars.index

    def _sample(signal_fn, label: str) -> dict:
        rets: list[float] = []
        for ed in b_dates:
            prior = bars.loc[bars_idx < ed]
            if len(prior) < 121:
                continue
            sig = signal_fn(prior)
            # Forward 1-day return on `ed` (the bar AT entry_date if exists)
            mask_at = bars_idx == ed
            if not mask_at.any():
                continue
            pos_at = int(np.where(mask_at)[0][0])
            if pos_at + 1 >= len(bars):
                continue
            r = float(bars["ret"].iloc[pos_at + 1])
            if not np.isfinite(r):
                continue
            net = (sig * r) - (abs(sig) * cost_frac if sig != 0 else 0.0)
            rets.append(net)
        return _summarize(label, rets)

    def sig_60(prior):
        c = prior["close"]
        return 1.0 if c.iloc[-1] / c.iloc[-61] - 1.0 > 0 else 0.0

    def sig_blend_20_60(prior):
        c = prior["close"]
        s20 = c.iloc[-1] / c.iloc[-21] - 1.0
        s60 = c.iloc[-1] / c.iloc[-61] - 1.0
        if s20 > 0 and s60 > 0:
            return 1.0
        if s20 < 0 and s60 < 0:
            return 0.0   # long-only
        return 0.0

    def sig_ma(prior):
        c = prior["close"]
        if len(c) < 200:
            return 0.0
        return 1.0 if c.iloc[-50:].mean() > c.iloc[-200:].mean() else 0.0

    rows = [
        _summarize("engine_B_all_kept", b["net_ret"].tolist()),
        _sample(lambda p: 0.0, "remove_engine_B (no trades)"),
        _sample(sig_60,         "replace_with_TSMOM_60d"),
        _sample(sig_blend_20_60, "replace_with_TSMOM_20+60_blend"),
        _sample(sig_ma,         "replace_with_MA50_200"),
    ]
    _print_table(rows, ["label", "n", "sharpe", "hit_pct",
                          "total_pct", "worst_pct", "max_dd_pct"])


# ---------------------------------------------------------------------------
# Phase 4 — Gating simulation
# ---------------------------------------------------------------------------

def phase4(b: pd.DataFrame) -> None:
    print("\n=== PHASE 4 — Gating simulation ===")
    bb = b.dropna(subset=["tsmom_60", "rvol_20"])
    if bb.empty:
        print("  no enriched data"); return
    rows = [_summarize("engine_B_all_kept", bb["net_ret"].tolist())]

    # Gate 1: only when TSMOM 60d agrees (positive)
    g1 = bb[bb["tsmom_60"] > 0]
    rows.append(_summarize("gate_tsmom_60_pos", g1["net_ret"].tolist()))

    # Gate 2: only when realized vol below 18%
    g2 = bb[bb["rvol_20"] < 0.18]
    rows.append(_summarize("gate_rvol20_lt_18", g2["net_ret"].tolist()))

    # Gate 3: BOTH (TSMOM agrees AND vol low)
    g3 = bb[(bb["tsmom_60"] > 0) & (bb["rvol_20"] < 0.18)]
    rows.append(_summarize("gate_BOTH", g3["net_ret"].tolist()))

    # Gate 4: TSMOM 20 AND 60 both positive
    g4 = bb[(bb["tsmom_20"] > 0) & (bb["tsmom_60"] > 0)]
    rows.append(_summarize("gate_tsmom_20_AND_60", g4["net_ret"].tolist()))

    # Gate 5: MA long AND TSMOM 60 agrees
    g5 = bb[(bb["ma_long"] > 0.5) & (bb["tsmom_60"] > 0)]
    rows.append(_summarize("gate_MA_long_AND_tsmom60",
                              g5["net_ret"].tolist()))

    _print_table(rows, ["label", "n", "sharpe", "hit_pct",
                          "total_pct", "worst_pct", "max_dd_pct"])
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    with SessionLocal() as s:
        b = _load_b_trades(s)
    if b.empty:
        print("no closed Engine B trades")
        return 0
    print(f"Loaded {len(b)} closed Engine B trades.")
    bars = _load_es_bars()
    b = _enrich_signals(b, bars)
    phase1(b)
    phase2(b)
    phase3(b, bars)
    phase4(b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
