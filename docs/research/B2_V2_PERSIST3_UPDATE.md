# B2 → V2 Persist-3 Shadow Strategy Update — Review Doc

**Date:** 2026-04-25
**Status:** Shadow research only. NO production change. NO B2 modification.
NO execution enabled. NO ML promotion. NO ENGINE_B_MODE flip.

---

## TL;DR

Added a parallel shadow strategy `tsmom_60_no_stress_v2_persist3` that
runs alongside the current B2 (`tsmom_60_no_stress`) using a richer
MA200 stress trigger (3-consecutive-closes confirmation). B2 unchanged
and still paused (BLOCKING via edge_trajectory). V2 collects OOS data
for 30-60 days before any operator review.

---

## Why This Change

Recent diagnostic audits showed:

1. B2 promotion **paused** (BLOCKING) — 30d edge -8.77 bps,
   60d edge -0.07 bps, trend DECLINING.
2. Stress filter misclassification audit identified
   **`close < MA200`** as the failing component:
   - 178 false-stress missed-winner days over 25 years
   - **97.2% of false-stress days had this trigger**
   - **156 of 178 (87.6%) had ONLY this trigger** — no other stress
     condition fired
   - Cumulative missed gain: +184% over 2001+
3. MA200 redesign audit tested 5 candidates. **Persist-3 confirmation**
   was the safest:
   - Eliminates 156/178 single-close false fires
   - Catches every multi-day MA200 breakdown (no missed bears)
   - Full 2001+: Sharpe 0.602 → 0.625 (+0.023), DD -20.39 → -20.07
     (slightly better)
   - 2018+: Sharpe 0.905 → 0.962 (+0.057), DD -12.34 → **-11.21** (BETTER)
   - p99 IDENTICAL to baseline (-2.0771)
   - p95 difference 0.06 bp — within noise

Strict acceptance rules failed Rule 1 (30d edge no-improve) and Rule 3
(p95 by 0.06 bp). Created V2 as parallel shadow rather than swapping
B2 — operator gets 30-60 days of OOS evidence before deciding.

---

## What Changed (Code)

| File | Type | Purpose |
|---|---|---|
| `apps/api/src/research/regime_backfill_persist3.py` | NEW | PIT-safe persist-3 classifier · `logic_version=research_backfill_persist3_v1` |
| `apps/api/src/research/shadow_strategy_v2.py` | NEW | `SOURCE_STRATEGY_V2='tsmom_60_no_stress_v2_persist3'` + `compute_decision_v2` |
| `scripts/backfill_research_regime_persist3.py` | NEW | Backfill diagnostic regime labels |
| `scripts/run_shadow_strategy.py` | UPDATED | Computes B2 + V2 each daily run; backfill covers both |
| `apps/api/tests/unit/test_regime_persist3_pit.py` | NEW | 9 PIT-safety tests |
| `apps/api/tests/unit/test_shadow_strategy_v2.py` | NEW | 6 V2 strategy tests |

**B2 module byte-unchanged.** `regime_backfill.py`, `engine_b2.py`,
`shadow_strategy.py` (the existing B2 logic) NOT modified.

---

## What Changed (Data)

### `context_daily` — new diagnostic logic version

| logic_version | Status | Rows | Use |
|---|---|---|---|
| `research_backfill_v1` | diagnostic | 4,184 | feeds B2 (unchanged) |
| **`research_backfill_persist3_v1`** | diagnostic | **4,184** | **feeds V2 (new)** |
| (production v1.0.0) | production | 2 | NOT changed |

Distribution under persist-3:
- stress: 397 days (vs v1's 436 → 39 fewer)
- directional: 1,085 days (same)
- neutral: 411 days (vs v1's 372 → 39 more)

The 39-day shift is the persist-3 change: single-close MA200 breaks
that v1 flagged as stress are now neutral under V2.

### `paper_shadow_log` — second strategy logged

```
 source_strategy                | rows | LONG | FLAT
 tsmom_60_no_stress             |  330 |  234 |   96
 tsmom_60_no_stress_v2_persist3 |  330 |  235 |   95
```

Both populated 2025-01-02 → 2026-04-24. Same column shape, distinct
rows via `(as_of_date, instrument, source_strategy)` natural key.

### B2 vs V2 cross-tab (16-mo shadow window)

| B2 | V2 | n | Avg fwd_1d |
|---|---|---|---|
| FLAT | FLAT | 95 | +5.24 bps |
| **FLAT** | **LONG** | **1** | **+71.74 bps** ← V2 captured |
| LONG | LONG | 234 | +6.85 bps |
| LONG | FLAT | 0 | — |

V2 captured 1 missed winner. Long-term backtest predicted ~156 such
recoveries; recent OOS is early data.

---

## Persist-3 Logic (exact)

Same vol/dd triggers as v1 baseline, ONLY MA200 component differs:

```
v1 (current B2):
    stress = (rvol_20 ≥ 0.30
           OR rvol_5  ≥ 0.45
           OR dd_60   ≤ -0.10
           OR close < MA200)             ← single close, any day

v2_persist3 (new V2):
    stress = (rvol_20 ≥ 0.30
           OR rvol_5  ≥ 0.45
           OR dd_60   ≤ -0.10
           OR _persist_below_ma200(closes, n=3))   ← 3 consecutive
```

`_persist_below_ma200(closes, n=3)` returns True only if for each of
the last 3 bars, that bar's close is below the 200-day MA computed
from the 200 bars STRICTLY BEFORE it. PIT-safe.

`directional_regime` definition unchanged.

---

## Backtest Evidence (2001+)

| Variant | Sharpe | Max DD% | p95% | p99% | 2018+ Sharpe | 2018+ DD% |
|---|---|---|---|---|---|---|
| baseline (B2 v1) | 0.602 | -20.39 | -1.000 | -2.077 | 0.905 | -12.34 |
| **V2 persist3** | **0.625** | **-20.07** | -1.006 | -2.077 | **0.962** | **-11.21** |

V2 dominates 2018+: better Sharpe, BETTER DD. Tail risk identical
(p99 same to 4 decimals). Full-period DD also slightly better.

False-stress recovery vs new losses (vs v1):
- Recovered wins: 18 (avg +105 bps)
- New losses: 16 (avg -83 bps)
- Net: +2 days, +551 bps cumulative

Conservative gain — fewer changes than other candidates (3_volexp had
+12 net days but worse 2018+ DD).

---

## What Did NOT Change

| Surface | Status |
|---|---|
| `regime_backfill.py` (v1) | UNCHANGED |
| `engine_b2.py` | UNCHANGED |
| `shadow_strategy.py` (B2 logic) | UNCHANGED |
| `paper_trade_log` / `decision_log` | NOT TOUCHED |
| `ml_*` tables | NOT TOUCHED |
| `engine_b_decision_snapshot` | NOT TOUCHED (pause logic untouched) |
| `ENGINE_B_MODE` | LEGACY (unchanged) |
| `ENGINE_B_OPERATOR_APPROVAL` | false (unchanged) |
| Promotion pause state | BLOCKING (unchanged, correct) |
| `ML_HYBRID_MODE` | advisory (unchanged) |
| `ML_CAN_AFFECT_TRADES` | false (unchanged) |
| Risk parameters | UNCHANGED |
| Trading execution | UNCHANGED |
| Production v1.0.0 regime rows | NOT TOUCHED |

V2 only writes to `paper_shadow_log` (research table). Failure of V2
path is non-blocking. Existing B2 promotion gates evaluate B2 ONLY —
V2 is purely observed for now.

---

## Tests

**140 / 140 PASS** across the full B-migration + governance + shadow
suite.

V2-specific tests:
- PIT invariance (no future-bar leakage)
- Single close below MA200 does NOT trigger persist-3
- Three consecutive closes DOES trigger
- High vol still triggers (vol component intact)
- Direct comparison with v1 proves only MA200 component differs
- `SOURCE_STRATEGY_V2` distinct from B2 constant
- `compute_decision_v2` honors persist-3 stress flag
- `to_dict()` payload + no-mutation invariants

---

## Operations

V2 runs automatically each daily cron tick alongside B2:

```
B2  decision @ 2026-04-24: signal=LONG regime=DIRECTIONAL ...
V2  decision @ 2026-04-24: signal=LONG regime=DIRECTIONAL
Processed N days (B2: x LONG / y FLAT) (V2: x LONG / y FLAT)
```

Same `run_daily_loop.sh` step (`shadow_strategy_tsmom60_no_stress`
optional job) — no scheduler change.

Backfill historical: `python -m scripts.backfill_research_regime_persist3`
(idempotent on conflict). Already applied for 2018-2026.

---

## Suggested Next Steps (Operator Decisions Required)

### Now → 60 days
1. Let V2 accumulate OOS shadow data (passive observation).
2. Continue B2 BLOCKING pause via edge_trajectory.
3. NO code change to B2 or production.

### After 30+ days V2 OOS
4. Operator reviews V2 vs B2 metrics:
   - Divergence stats (B2 FLAT vs V2 LONG days)
   - Realized 1d / 5d return on those divergent days
   - Cumulative recovery vs new losses
5. If V2 demonstrates the predicted 2018+ improvement (~+0.06 Sharpe,
   better DD) AND recovers missed winners without proportional new
   losses → operator considers:
   - Promoting V2 to B2 replacement (would require new
     `regime_backfill.py` change + version bump, NOT auto)
   - OR keeping V2 as research artifact and continuing B2

### What blocks V2 promotion automatically
- B2 promotion pause (separate machinery) only evaluates B2
- V2 has no promotion machinery yet — operator-gated entirely
- V2 cannot affect execution under any current code path

### What I (operator) need to decide
1. **Acceptance bar for V2**: should we relax Rule 1 (30d strict
   improvement) or Rule 3 (p95 0.06 bp deterioration) given the
   strong 2018+ evidence? My audit recommended documenting these as
   "within noise" but did NOT auto-relax them.
2. **Wiring**: V2 is observation-only. To actually swap V2 in for B2
   would need:
   - New router input or config flag
   - Updated `engine_b2.py` to call persist3 classifier
   - New ENGINE_B_MODE state machine entry (or sub-flag)
   - Operator approval flag bumped
3. **Timeline**: 30 days minimum OOS recommended. 60 days would give
   stronger statistical signal.

---

## Files Reference

```
apps/api/src/research/
  regime_backfill.py              # v1 (UNCHANGED — feeds B2)
  regime_backfill_persist3.py     # NEW v2 classifier (feeds V2)
  shadow_strategy.py              # B2 (UNCHANGED)
  shadow_strategy_v2.py           # NEW V2 module
  engine_b2.py                    # UNCHANGED
  engine_b_router.py              # UNCHANGED
  engine_b_promotion.py           # UNCHANGED (still evaluates B2 only)
  engine_b_decision.py            # UNCHANGED
  engine_b_pause.py               # UNCHANGED (BLOCKING on B2 only)
  engine_b_analytics.py           # UNCHANGED

scripts/
  backfill_research_regime.py            # v1 backfill (UNCHANGED)
  backfill_research_regime_persist3.py   # NEW v2 backfill
  run_shadow_strategy.py                 # UPDATED to dual-compute

apps/api/tests/unit/
  test_regime_backfill_pit.py        # v1 (UNCHANGED, 9 tests)
  test_regime_persist3_pit.py        # NEW (9 tests)
  test_shadow_strategy.py            # B2 (UNCHANGED)
  test_shadow_strategy_v2.py         # NEW (6 tests)
  test_engine_b_*.py                 # all UNCHANGED
```

Audit artifacts:
- `artifacts/regime_audit/20260425T165506Z/` — regime quality
- `artifacts/stability_audit/20260425T172017Z/` — stability + edge
- `artifacts/edge_diagnostic/20260425T180217Z/` — edge decline diagnostic
- `artifacts/stress_filter_audit/20260425T182019Z/` — filter misclass
- `artifacts/ma200_redesign/20260425T184656Z/` — 5 MA200 candidates
- `docs/ARCHITECTURE_FINAL.md` — overall system design

---

## Risk + Mitigation Summary

| Risk | Mitigation |
|---|---|
| V2 captures fewer real bears | persist-3 catches every multi-day breakdown by definition; only single-close noise filtered |
| V2 absorbs more 2018+ drawdown | Backtest shows OPPOSITE: 2018+ DD -11.21 vs baseline -12.34 |
| Recent 30d edge unchanged | Acknowledged; recent stress days had multi-trigger firings, not just MA200 |
| V2 backfill could overwrite v1 rows | Different `logic_version` on natural key — no overlap possible |
| V2 daily compute fails | Wrapped in same error handling as B2; non-blocking for daily loop |
| V2 inadvertently affects production | Read-only DB ops, separate `source_strategy`, no router wiring |

---

## Bottom Line

V2 is a low-risk, fully reversible parallel research artifact. Lets
operator compare two stress-filter philosophies on real OOS data
without touching production B2, ML, or execution. **Decision deferred
to operator** after sufficient OOS evidence accumulates.
