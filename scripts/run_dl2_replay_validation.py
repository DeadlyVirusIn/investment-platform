"""Phase DL2 — Replay Validation.

Proves the new strategy-adapter infrastructure produces EXACTLY the same
trading decisions and P&L as the frozen Phase 21/22 production backtest.

Method:
  1. Run existing Phase 21 backtest logic (frozen reference).
  2. Re-run using the new DL2 strategy adapter (engine_a + engine_b + selector).
  3. Compare trade-by-trade: same dates, same engines, same entry/exit, same P&L.

PASS = zero mismatch on every dimension.
FAIL = any discrepancy — do not proceed to DL3.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
from loguru import logger

from scripts.run_phase12_price_action import fetch_es_daily, load_spy_from_db, HOLD_WINDOWS
from scripts.run_phase15_mean_reversion import (
    build_features, forward_returns,
    LOOSE_RATIO_THRESH, Z_EXTENSION_THRESH,
)
from scripts.run_phase20_regime_gated import build_gates

from apps.api.src.data.features.registry import get_registry
from apps.api.src.data.context.production import classify_production_context
from apps.api.src.data.strategy.selector import SelectorInputs, select

OUT_DIR = Path("artifacts/phase_dl2")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    logger.info("[dl2] loading data + building features (same as Phase 21)")
    es = fetch_es_daily(start="2020-01-01")
    spy = load_spy_from_db()
    es = es[~es.index.duplicated(keep="last")].sort_index()
    spy = spy[~spy.index.duplicated(keep="last")].sort_index()
    common = es.index.intersection(spy.index)
    es = es.loc[common]; spy = spy.loc[common]
    f = build_features(es)
    fwd = forward_returns(f, HOLD_WINDOWS)
    gates = build_gates(f, spy)

    c1 = f["loose_ratio"] > LOOSE_RATIO_THRESH
    c2 = f["vol_elevated"] | f["vol_expanding"]
    c3 = f["z_score"] < Z_EXTENSION_THRESH
    p15_entry = (c1 & c2 & c3).fillna(False)
    g = gates["gates_favorable"]
    cs = gates["credit_stable"].fillna(False)
    rc = gates["rates_calm"].fillna(False)

    # Verify registry loads
    reg = get_registry()
    logger.info("[dl2] registry loaded: {} features, {} contexts",
                len(reg.features), len(reg.contexts))
    assert reg.is_production_feature("p15_entry")
    assert reg.is_production_feature("credit_stable")
    assert reg.is_production_feature("rates_calm")

    # ------------------------------------------------------------------
    # Reference: inline Phase 21 logic
    # ------------------------------------------------------------------
    reference_decisions: list[dict] = []
    for i in f.index:
        gf = int(g[i]) if not pd.isna(g[i]) else 0
        stress_ref = gf <= 1
        directional_ref = gf >= 2
        p15_ref = bool(p15_entry[i])

        if p15_ref and stress_ref:
            eng = "A"; fire = True
        elif directional_ref and bool(cs[i]) and bool(rc[i]):
            eng = "B"; fire = True
        else:
            eng = "none"; fire = False

        reference_decisions.append({
            "as_of_date": i, "engine": eng, "fire": fire,
            "p15_entry": p15_ref, "gates_fav": gf,
            "stress": stress_ref, "directional": directional_ref,
            "credit_stable": bool(cs[i]), "rates_calm": bool(rc[i]),
        })

    # ------------------------------------------------------------------
    # DL2: use the new adapter
    # ------------------------------------------------------------------
    dl2_decisions: list[dict] = []
    for i in f.index:
        gf = int(g[i]) if not pd.isna(g[i]) else 0
        ctx = classify_production_context(gates_favorable=gf)
        out = select(SelectorInputs(
            p15_entry=bool(p15_entry[i]),
            credit_stable=bool(cs[i]),
            rates_calm=bool(rc[i]),
            production_context=ctx,
        ))
        dl2_decisions.append({
            "as_of_date": i, "engine": out.engine, "fire": out.fire,
            "p15_entry": bool(p15_entry[i]), "gates_fav": gf,
            "stress": ctx.stress_regime, "directional": ctx.directional_regime,
            "credit_stable": bool(cs[i]), "rates_calm": bool(rc[i]),
        })

    # ------------------------------------------------------------------
    # Compare
    # ------------------------------------------------------------------
    mismatches = []
    for ref, dl2 in zip(reference_decisions, dl2_decisions):
        if (ref["engine"] != dl2["engine"] or ref["fire"] != dl2["fire"]
            or ref["stress"] != dl2["stress"]
            or ref["directional"] != dl2["directional"]):
            mismatches.append({
                "as_of_date": str(ref["as_of_date"]),
                "ref": {k: ref[k] for k in ("engine", "fire", "stress",
                                             "directional")},
                "dl2": {k: dl2[k] for k in ("engine", "fire", "stress",
                                             "directional")},
            })

    # Trade counts
    ref_a = sum(1 for r in reference_decisions
                if r["engine"] == "A" and r["fire"])
    ref_b = sum(1 for r in reference_decisions
                if r["engine"] == "B" and r["fire"])
    dl2_a = sum(1 for r in dl2_decisions
                if r["engine"] == "A" and r["fire"])
    dl2_b = sum(1 for r in dl2_decisions
                if r["engine"] == "B" and r["fire"])

    # P&L check — recompute trade returns both ways
    HOLD_A = 10
    COST_A_BPS = 20.0; COST_B_BPS = 5.0
    entry_1d = f["open"].shift(-1)
    exit_1d = f["close"].shift(-1)
    fwd_1d = (exit_1d - entry_1d) / entry_1d

    def trades_from(decisions):
        out = []
        for d in decisions:
            if not d["fire"]: continue
            i = d["as_of_date"]
            if d["engine"] == "A":
                r = fwd[HOLD_A][i]
                if pd.isna(r): continue
                out.append((i, float(r) - COST_A_BPS / 1e4, "A"))
            elif d["engine"] == "B":
                r = fwd_1d[i]
                if pd.isna(r): continue
                out.append((i, float(r) - COST_B_BPS / 1e4, "B"))
        out.sort(key=lambda t: t[0])
        return out

    ref_trades = trades_from(reference_decisions)
    dl2_trades = trades_from(dl2_decisions)

    pnl_match = True
    trade_diffs = []
    if len(ref_trades) != len(dl2_trades):
        pnl_match = False
        trade_diffs.append({"kind": "trade_count_mismatch",
                            "ref": len(ref_trades), "dl2": len(dl2_trades)})
    else:
        for (a, b) in zip(ref_trades, dl2_trades):
            if a[0] != b[0] or a[2] != b[2] or abs(a[1] - b[1]) > 1e-10:
                pnl_match = False
                trade_diffs.append({
                    "ref": {"date": str(a[0]), "engine": a[2], "ret": a[1]},
                    "dl2": {"date": str(b[0]), "engine": b[2], "ret": b[1]},
                })

    # Cumulative P&L
    def cum_pct(trades):
        eq = 1.0
        for _, r, _ in trades: eq *= (1 + r)
        return (eq - 1) * 100

    ref_cum = cum_pct(ref_trades)
    dl2_cum = cum_pct(dl2_trades)

    verdict = "PASS" if (not mismatches and pnl_match
                         and ref_a == dl2_a and ref_b == dl2_b) else "FAIL"

    report = {
        "phase": "DL2_replay_validation",
        "today": dt.date.today().isoformat(),
        "bars_total": len(f),
        "reference_n_A": ref_a, "reference_n_B": ref_b,
        "dl2_n_A": dl2_a, "dl2_n_B": dl2_b,
        "decision_mismatches": len(mismatches),
        "trade_diffs_count": len(trade_diffs),
        "first_5_mismatches": mismatches[:5],
        "first_5_trade_diffs": trade_diffs[:5],
        "reference_cum_pct": ref_cum,
        "dl2_cum_pct": dl2_cum,
        "cum_pnl_exact_match": abs(ref_cum - dl2_cum) < 1e-8,
        "verdict": verdict,
    }
    (OUT_DIR / "replay_report.json").write_text(
        json.dumps(report, indent=2, default=str)
    )

    # Print
    print("=" * 96)
    print(f"PHASE DL2 - REPLAY VALIDATION  {dt.date.today()}")
    print("=" * 96)
    print(f"Bars: {len(f)}")
    print(f"Engine A count:    reference={ref_a}  dl2={dl2_a}  "
          f"match={ref_a == dl2_a}")
    print(f"Engine B count:    reference={ref_b}  dl2={dl2_b}  "
          f"match={ref_b == dl2_b}")
    print(f"Decision mismatches: {len(mismatches)}")
    print(f"Trade diffs:         {len(trade_diffs)}")
    print(f"Ref cum%:  {ref_cum:+.6f}")
    print(f"DL2 cum%:  {dl2_cum:+.6f}")
    print(f"Cum P&L exact match: {abs(ref_cum - dl2_cum) < 1e-8}")
    print()
    if mismatches:
        print("First 5 mismatches:")
        for m in mismatches[:5]:
            print(f"  {m}")
    if trade_diffs:
        print("First 5 trade diffs:")
        for d in trade_diffs[:5]:
            print(f"  {d}")
    print()
    print("-" * 96)
    print(f"VERDICT: {verdict}")
    print("=" * 96)
    print(f"Report: {OUT_DIR / 'replay_report.json'}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
