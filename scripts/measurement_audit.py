"""Post-MUST-FIX measurement audit.

Read-only. Computes baselines + deterministic perf + ML evaluation skeleton
against actual data. No state mutation. No new endpoints.

Phases:
  1. Baselines (buy-hold ES, TSMOM 20/60/120, MA50/200 crossover)
  2. Deterministic perf from paper_trade_log
  3. ML evaluation (skipped if no predictions exist; reason logged)
  4. Feature importance (when model trains successfully)
  5. Regime split

Run:
    cd C:/Users/kunal/projects/investment-platform
    ./.venv/Scripts/python.exe -m scripts.measurement_audit
"""

from __future__ import annotations

import datetime as dt
import math
import sys
from collections.abc import Sequence
from typing import Any

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


def _max_drawdown(equity: Sequence[float]) -> float:
    arr = np.asarray(equity, dtype=float)
    if len(arr) < 2:
        return 0.0
    peak = np.maximum.accumulate(arr)
    dd = (arr - peak) / peak
    return float(dd.min()) * 100.0


def _hit_rate(returns: Sequence[float]) -> float:
    arr = np.asarray([r for r in returns if pd.notna(r)], dtype=float)
    if len(arr) == 0:
        return float("nan")
    return float((arr > 0).mean())


def _total_return(returns: Sequence[float]) -> float:
    arr = np.asarray([r for r in returns if pd.notna(r)], dtype=float)
    if len(arr) == 0:
        return 0.0
    return float((1.0 + arr).prod() - 1.0) * 100.0


def _summary(label: str, returns: Sequence[float],
              equity: Sequence[float] | None = None) -> dict:
    arr = np.asarray([r for r in returns if pd.notna(r)], dtype=float)
    if equity is None:
        equity = (1.0 + arr).cumprod()
    return {
        "strategy": label,
        "n_trades": int(len(arr)),
        "sharpe": round(_sharpe(arr), 3),
        "hit_rate_pct": round(_hit_rate(arr) * 100, 2),
        "max_dd_pct":   round(_max_drawdown(equity), 2),
        "total_ret_pct": round(_total_return(arr), 2),
        "best": round(float(arr.max()) * 100, 2) if len(arr) else float("nan"),
        "worst": round(float(arr.min()) * 100, 2) if len(arr) else float("nan"),
    }


# ---------------------------------------------------------------------------
# Phase 1 — Baselines from yfinance ES bars
# ---------------------------------------------------------------------------

def phase1_baselines() -> dict[str, Any]:
    print("\n=== PHASE 1 — Baselines ===")
    try:
        from scripts.run_phase12_price_action import fetch_es_daily
        df = fetch_es_daily(start="2020-01-01")
    except Exception as e:
        print(f"  ! ES bars fetch failed: {e}")
        return {"error": str(e)}

    df["ret"] = df["close"].pct_change()
    df = df.dropna()

    out: list[dict] = []

    # Buy & hold
    out.append(_summary("buy_hold_ES", df["ret"].tolist()))

    # TSMOM long-flat (long if N-day return > 0 else flat)
    for h in (20, 60, 120):
        sig = (df["close"] / df["close"].shift(h) - 1.0).gt(0).astype(int)
        # Apply tomorrow's signal to today (no lookahead)
        pos = sig.shift(1).fillna(0).astype(int)
        strat = pos * df["ret"]
        out.append(_summary(f"tsmom_long_flat_{h}d", strat.tolist()))

    # MA 50/200 crossover (long when MA50 > MA200)
    df["ma50"]  = df["close"].rolling(50).mean()
    df["ma200"] = df["close"].rolling(200).mean()
    sig = (df["ma50"] > df["ma200"]).astype(int)
    pos = sig.shift(1).fillna(0).astype(int)
    out.append(_summary("ma50_200_long_flat", (pos * df["ret"]).tolist()))

    print(f"{'strategy':30s} {'N':>6s} {'sharpe':>8s} "
          f"{'hit%':>6s} {'maxDD%':>8s} {'total%':>9s} "
          f"{'best%':>7s} {'worst%':>7s}")
    for r in out:
        print(f"{r['strategy']:30s} {r['n_trades']:>6d} "
              f"{r['sharpe']:>8.3f} {r['hit_rate_pct']:>6.2f} "
              f"{r['max_dd_pct']:>8.2f} {r['total_ret_pct']:>9.2f} "
              f"{r['best']:>7.2f} {r['worst']:>7.2f}")
    return {"baselines": out, "n_bars": int(len(df))}


# ---------------------------------------------------------------------------
# Phase 2 — Deterministic perf + ML evaluation
# ---------------------------------------------------------------------------

def phase2_deterministic(session) -> dict[str, Any]:
    print("\n=== PHASE 2 — Deterministic perf (paper_trade_log) ===")
    rows = session.execute(text("""
        SELECT entry_date, exit_date, engine, status, regime_at_entry,
               net_ret_pct, gross_ret_pct, position_size_pct,
               exploratory_paper
        FROM paper_trade_log
        WHERE status = 'closed' AND net_ret_pct IS NOT NULL
        ORDER BY entry_date
    """)).mappings().all()
    df = pd.DataFrame(rows)
    if df.empty:
        print("  no closed trades")
        return {}
    df["net_ret"] = df["net_ret_pct"].astype(float) / 100.0
    full = _summary("deterministic_all", df["net_ret"].tolist())
    print(f"  closed={len(df)}  sharpe={full['sharpe']}  "
          f"hit%={full['hit_rate_pct']}  total%={full['total_ret_pct']}")
    by_engine: list[dict] = []
    for eng, g in df.groupby("engine"):
        s = _summary(f"deterministic_engine_{eng}", g["net_ret"].tolist())
        s["engine"] = eng
        by_engine.append(s)
        print(f"  engine {eng}: n={s['n_trades']}  sharpe={s['sharpe']}  "
              f"hit%={s['hit_rate_pct']}  worst%={s['worst']}")

    # Best / worst single trade for tail check
    print(f"  worst trade: {float(df['net_ret'].min())*100:.2f}%  "
          f"best trade: {float(df['net_ret'].max())*100:.2f}%  "
          f"skew: {float(df['net_ret'].skew()):.3f}  "
          f"kurt: {float(df['net_ret'].kurt()):.3f}")
    return {"deterministic_all": full, "by_engine": by_engine,
            "skew": float(df["net_ret"].skew()),
            "kurt": float(df["net_ret"].kurt()),
            "frame": df}


def phase2_ml_eval(session) -> dict[str, Any]:
    print("\n=== PHASE 2b — ML evaluation (confusion + calibration) ===")
    rows = session.execute(text("""
        SELECT id::text AS id, model_run_id::text AS mrid,
               symbol, as_of_date, ml_score, ml_confidence, ml_action,
               actual_outcome, outcome_available
        FROM ml_shadow_prediction
        WHERE outcome_available = true
    """)).mappings().all()
    n = len(rows)
    if n == 0:
        print("  ml_shadow_prediction has 0 rows with outcome_available=true")
        print("  reason: ml_model_run.status=SKIPPED_NO_LABELS — "
              "no predictions persisted yet (~T+5 from oldest decision)")
        return {"status": "skipped_no_predictions", "n": 0}
    # Define ML "buy" = ml_action in {accept,reduce} AND outcome > 0 = TP
    df = pd.DataFrame(rows)
    df["pred_buy"] = df["ml_action"].isin(["accept", "reduce"])
    df["actual_pos"] = df["actual_outcome"].astype(float) > 0
    tp = int(((df["pred_buy"]) & (df["actual_pos"])).sum())
    fp = int(((df["pred_buy"]) & (~df["actual_pos"])).sum())
    tn = int(((~df["pred_buy"]) & (~df["actual_pos"])).sum())
    fn = int(((~df["pred_buy"]) & (df["actual_pos"])).sum())
    print(f"  TP={tp} FP={fp} TN={tn} FN={fn}")
    false_allow = fp / max(1, fp + tp)
    false_avoid = fn / max(1, fn + tn)
    return {
        "status": "ok", "n": n,
        "TP": tp, "FP": fp, "TN": tn, "FN": fn,
        "false_allow_rate": round(false_allow, 4),
        "false_avoid_rate": round(false_avoid, 4),
    }


# ---------------------------------------------------------------------------
# Phase 3 — Feature importance (best-effort)
# ---------------------------------------------------------------------------

def phase3_feature_importance(session) -> dict[str, Any]:
    print("\n=== PHASE 3 — Feature sanity (importance) ===")
    try:
        from apps.api.src.ml.dataset import build_dataset
        from apps.api.src.ml.features import (
            TRAINING_FEATURE_WHITELIST,
        )
        from apps.api.src.ml.models import fit_simple_model
    except Exception as e:
        print(f"  import failed: {e}")
        return {"status": "import_error"}

    ds = build_dataset(session)
    df = ds.df
    label_col = "label_win_net_5d"
    if label_col not in df.columns:
        print(f"  label column {label_col} missing")
        return {"status": "label_missing"}
    labeled = df.dropna(subset=[label_col])
    n_labeled = int(len(labeled))
    print(f"  labeled rows={n_labeled} (full rows={len(df)})")
    if n_labeled < 30:
        print("  insufficient labeled rows — feature importance skipped")
        return {"status": "insufficient", "n_labeled": n_labeled}

    feats = [c for c in TRAINING_FEATURE_WHITELIST if c in labeled.columns]
    X = labeled[feats].fillna(0.0)
    y = labeled[label_col].astype(int)
    m = fit_simple_model(X, y, name="rf", feature_names=feats,
                          class_balanced=True)
    if m.skipped:
        print(f"  model skipped: {m.skip_reason}")
        return {"status": "model_skipped", "reason": m.skip_reason}
    importances = getattr(m.model, "feature_importances_", None)
    if importances is None:
        return {"status": "no_importances"}
    pairs = sorted(zip(feats, importances),
                    key=lambda p: -p[1])
    print("  top features:")
    for f, imp in pairs[:10]:
        print(f"    {f:30s} {imp:.4f}")
    return {"status": "ok", "top": pairs[:10], "n_labeled": n_labeled}


# ---------------------------------------------------------------------------
# Phase 4 — Regime split
# ---------------------------------------------------------------------------

def phase4_regimes(det_frame: pd.DataFrame) -> dict[str, Any]:
    print("\n=== PHASE 4 — Regime analysis ===")
    if det_frame is None or det_frame.empty:
        print("  no trades")
        return {}
    out: list[dict] = []
    for reg, g in det_frame.groupby("regime_at_entry"):
        s = _summary(f"regime_{reg}", g["net_ret"].tolist())
        s["regime"] = reg
        out.append(s)
        print(f"  regime {reg:>14s}: n={s['n_trades']}  "
              f"sharpe={s['sharpe']}  hit%={s['hit_rate_pct']}  "
              f"worst%={s['worst']}")
    return {"by_regime": out}


# ---------------------------------------------------------------------------
# Phase 5 — Shadow vs deterministic
# ---------------------------------------------------------------------------

def phase5_shadow_vs_deterministic(session) -> dict[str, Any]:
    print("\n=== PHASE 5 — Shadow vs deterministic ===")
    # Read counterfactual: for each closed paper trade, what did ML say?
    rows = session.execute(text("""
        SELECT t.id::text AS trade_id, t.net_ret_pct,
               t.alpha_rule_snapshot->>'ml_shadow_multiplier' AS ml_mult,
               t.alpha_rule_snapshot->>'ml_hybrid_action' AS ml_action,
               t.alpha_rule_snapshot->>'ml_shadow_available' AS avail
        FROM paper_trade_log t
        WHERE t.status='closed' AND t.net_ret_pct IS NOT NULL
    """)).mappings().all()
    df = pd.DataFrame(rows)
    df["net_ret"] = pd.to_numeric(df["net_ret_pct"], errors="coerce") / 100.0
    df["ml_mult"] = pd.to_numeric(df["ml_mult"], errors="coerce")
    n_with_ml = int(df["ml_mult"].notna().sum())
    print(f"  closed trades: {len(df)}  with ml_shadow_multiplier: "
          f"{n_with_ml}")
    if n_with_ml == 0:
        print("  no ML-attached trades yet — comparison skipped")
        print("  reason: ML hybrid only began wiring 2026-04-23; "
              "all prior trades pre-date hybrid")
        return {"status": "no_ml_attached", "n_with_ml": 0}

    det_sharpe = _sharpe(df["net_ret"].tolist())
    cf_returns = df["net_ret"] * df["ml_mult"].fillna(1.0)
    cf_sharpe = _sharpe(cf_returns.tolist())
    delta_sharpe = (cf_sharpe or 0.0) - (det_sharpe or 0.0)
    det_hit = _hit_rate(df["net_ret"].tolist())
    cf_hit = _hit_rate(cf_returns.tolist())
    print(f"  det_sharpe={det_sharpe:.3f}  cf_sharpe={cf_sharpe:.3f}  "
          f"Δ={delta_sharpe:+.3f}")
    print(f"  det_hit%={det_hit*100:.1f}  cf_hit%={cf_hit*100:.1f}")
    return {
        "status": "ok", "n_with_ml": n_with_ml,
        "det_sharpe": det_sharpe, "cf_sharpe": cf_sharpe,
        "delta_sharpe": delta_sharpe,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    with SessionLocal() as s:
        b = phase1_baselines()
        det = phase2_deterministic(s)
        mlv = phase2_ml_eval(s)
        fi  = phase3_feature_importance(s)
        det_frame = det.get("frame") if det else None
        reg = phase4_regimes(det_frame) if det_frame is not None else {}
        sd  = phase5_shadow_vs_deterministic(s)

    print("\n=== SUMMARY ===")
    print(f"  baselines     : {len(b.get('baselines', []))} strategies")
    print(f"  deterministic : "
          f"{det.get('deterministic_all', {}).get('n_trades', 0)} trades")
    print(f"  ML evaluation : {mlv.get('status')} (n={mlv.get('n', 0)})")
    print(f"  feature imp.  : {fi.get('status')}")
    print(f"  regime split  : "
          f"{len(reg.get('by_regime', []))} buckets")
    print(f"  shadow vs det : {sd.get('status')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
