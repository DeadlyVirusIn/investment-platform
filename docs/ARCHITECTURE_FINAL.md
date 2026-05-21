# Final End-State Architecture: Alpha Core + Regime Router + ML Overlay

**Status:** Architecture design only. NO trading change. NO ML enable.
NO production execution change. Engine B remains live until operator
approves migration. ML stays advisory-only.

**Hard rules (binding throughout):**
- No auto-promotion of any kind.
- No hidden switches — every state-changing flag is named, env-driven,
  documented, reversible.
- No ML trade origination.
- No ML size-up — ML can only reduce or hold.
- No unlogged decision — every routed signal lands in
  `decision_log` + `paper_shadow_log`.
- No irreversible migration — each state has a defined revert path.

---

## 1. System At Steady State

```
                ┌──────────────────────────────┐
                │    Market Data Readiness     │ — daily, 3:30 ET
                └──────────────┬───────────────┘
                               │
                ┌──────────────▼───────────────┐
                │   Regime Classification      │ — context_daily v1.0.0
                │   (stress / directional /    │   + research_backfill_v1
                │    neutral)                  │   diagnostic shadow
                └──────────────┬───────────────┘
                               │
                ┌──────────────▼───────────────┐
                │       Regime Router          │
                │ ┌──────────────────────────┐ │
                │ │ stress     → Engine A    │ │
                │ │ non-stress → Directional │ │   (TSMOM 60d_no_stress)
                │ │ uncertain  → no-trade /  │ │
                │ │              reduce conf │ │
                │ │ Engine B   → research /  │ │   (legacy fallback only)
                │ │              shadow      │ │
                │ └──────────────────────────┘ │
                └──────────────┬───────────────┘
                               │
                ┌──────────────▼───────────────┐
                │   Sleeve-Specific Signals    │ — deterministic
                │   • Engine A: stress mean-   │
                │     reversion (P15 + reg)    │
                │   • Directional: TSMOM 60d   │
                │     w/ no_stress filter      │
                │   • Baselines: B&H, TSMOM    │
                │     20/60/120, MA50/200      │
                │     (LOGGED, NEVER TRADED)   │
                └──────────────┬───────────────┘
                               │
                ┌──────────────▼───────────────┐
                │     Risk + Similarity        │
                │   (position_size_pct,        │
                │    similarity score, budget) │
                └──────────────┬───────────────┘
                               │
                ┌──────────────▼───────────────┐
                │      ML Overlay (meta)       │ — never originates
                │  • multiplier ∈ [0.5, 1.0]   │
                │  • per-sleeve rules:         │
                │    A: protect (no down-mul   │
                │       on stress regime)      │
                │    Dir: reduce on low-conf   │
                │    B legacy: ignore in       │
                │       research mode          │
                └──────────────┬───────────────┘
                               │
                ┌──────────────▼───────────────┐
                │     Final Paper Decision     │ — paper_trade_log +
                │                              │   decision_log
                └──────────────────────────────┘
```

---

## 2. Alpha Core — Sleeve Definitions

| Sleeve              | Trigger                                  | Hold | Target |
|---------------------|------------------------------------------|------|--------|
| **Engine A** (stress mean-reversion) | `stress_regime=True` AND P15 entry | 5d barrier | 1-2% |
| **Directional**     | `stress_regime=False` AND TSMOM 60d > 0  | 1d roll | 0.5-1.5% |
| **Baselines** (B&H, TSMOM 20/60/120, MA50/200) | always | varies | NEVER traded |
| **Engine B legacy** | directional + credit_stable + rates_calm | 1d | research / shadow only |

### Per-sleeve invariants

- **Engine A is sacrosanct** — it is the proven edge (Sharpe 7.77, N=38).
  No sleeve, regime gate, or ML rule may down-weight Engine A in stress
  regime. The promotion guard explicitly forbids
  `engine_a_avg_multiplier < 0.85`.
- **Directional** is shadow-tracked under `tsmom_60_no_stress`. It does
  NOT execute until ENGINE_B_MODE migrates from LEGACY through the
  full state machine.
- **Baselines** exist for measurement only — every Sharpe report
  compares the system to its best baseline. Promotion requires
  `system_underperforming_baseline=False`.
- **Engine B legacy** continues firing under LEGACY/SHADOW_COMPARE.
  Migration is the ENGINE_B_MODE state machine; Engine B is preserved
  for fallback even at FULL_B2.

---

## 3. ML Overlay — Meta-Risk Layer Only

ML is **never** allowed to:
- Create a trade direction.
- Increase position size.
- Block execution unless explicitly enabled (`ML_HYBRID_ALLOW_BLOCK`).

ML is **only** allowed to:
- Output a multiplier in `[ML_HYBRID_MIN_MULTIPLIER, 1.0]` (default 0.50–1.0).
- Reduce paper size when `ML_HYBRID_MODE=paper_reduce` (advisory until
  promotion gates pass).
- Log advisory annotations in `decision_log`.

### Per-sleeve ML rules

| Sleeve         | ML behavior                                              |
|----------------|----------------------------------------------------------|
| Engine A       | Protected: ML may NEVER apply multiplier < 0.85 systematically. Promotion guard `engine_a_avg_multiplier ≥ 0.85` enforces. |
| Directional    | ML can reduce on low-confidence signal; never up-size.  |
| Engine B legacy| Ignored — `ml_hybrid` does not annotate Engine B trades in research mode. |

### Promotion guard (formal gates)

| Gate                                 | Threshold                          |
|--------------------------------------|-------------------------------------|
| min_labeled_outcomes                 | ≥ 30                                |
| min_advice                           | ≥ 20                                |
| min_healthy_days                     | ≥ 7                                 |
| max_ece                              | ≤ 0.10                              |
| max_false_avoid                      | ≤ 0.35                              |
| max_false_allow                      | ≤ 0.35                              |
| delta_sharpe_vs_deterministic        | > 0                                 |
| delta_sharpe_vs_baseline             | > 0                                 |
| engine_a_avg_multiplier              | ≥ 0.85 (Engine A protection)        |
| model_status                         | == SHADOW_OUTPERFORMING             |
| operator_approval                    | == True (manual)                    |
| **HARD BLOCKERS** (override all gates) | `ml_can_affect_trades=true` OR `system_underperforming_baseline=true` |

Implemented in `apps/api/src/governance/promotion_engine.py`. NEVER
auto-promotes. Output is consumed by Ops UI + nightly logs.

---

## 4. Regime Router (formal)

```
input:  stress_regime, directional_regime, engine_a_active,
        engine_b_signal, b2_signal, ENGINE_B_MODE
output: routed_signal ∈ {LONG, FLAT}
        routed_engine ∈ {A, B, B2, FLAT}
        execution_changed ∈ {True, False}
```

### Routing rules

```
if stress_regime AND p15_entry:
    routed_engine = A          # stress mean-reversion
    execution_changed = False  # Engine A is canonical

elif NOT stress_regime:
    if ENGINE_B_MODE == LEGACY:
        routed_engine = B
        routed_signal = engine_b_signal
        execution_changed = False
    elif ENGINE_B_MODE == SHADOW_COMPARE:
        routed_engine = B
        routed_signal = engine_b_signal
        execution_changed = False
        # B2 logged for analysis
    elif ENGINE_B_MODE == PARTIAL_B2_{25,50,75}:
        deterministic per-day pick(date, mode):
            B2 → routed_signal = b2_signal
            B  → routed_signal = engine_b_signal
        execution_changed = (picked == B2)
    elif ENGINE_B_MODE == FULL_B2:
        routed_engine = B2
        routed_signal = b2_signal
        execution_changed = True

else (uncertain regime):
    routed_engine = FLAT
    confidence = reduced
```

Implemented in `apps/api/src/research/engine_b_router.py`. Pure
function. Deterministic per `(date, mode)` — backtest of any historical
day yields the same answer as the live runner for that day.

---

## 5. Decision Flow

```
step 1: market_data_readiness     scripts/check_market_data.sh
step 2: regime_classification     context_daily upsert (production)
step 3: sleeve_selection          engine_a_or_directional_or_flat
step 4: deterministic_signal      engine_a / engine_b / engine_b2 logic
step 5: risk_checks               position_size, similarity, budget
step 6: similarity_layer          alpha_similarity_filter
step 7: ml_overlay                hybrid_advisor (advisory or paper_reduce)
step 8: final_decision            paper_runner.execute()
step 9: audit_snapshot            alpha_rule_snapshot jsonb persisted
step 10: shadow_log               paper_shadow_log written for B vs B2
```

Every step writes to a logged surface. NO step is silent. NO ML output
can change steps 1-6.

---

## 6. State Machines

### 6.1 ENGINE_B_MODE (B → B2 migration)

```
LEGACY ──▶ SHADOW_COMPARE ──▶ PARTIAL_B2_25 ──▶ PARTIAL_B2_50
                                                     │
                                                     ▼
                                               PARTIAL_B2_75
                                                     │
                                                     ▼
                                                 FULL_B2
```

Transitions:
- **ADVANCE** (one step forward): all 6 promotion gates pass + operator
  approval flag flipped. Recommendation only — operator manually edits
  env var to apply.
- **REVERT** (one step back): kill switch fires (30d Sharpe ≤
  `ENGINE_B_KILL_SHARPE` OR 60d max-DD ≤ `ENGINE_B_KILL_DD_PCT`).
  Recommendation only — operator manually edits env var.
- **HOLD**: any failing gate or insufficient observations.

Promotion gates (`apps/api/src/research/engine_b_promotion.py`):
1. `min_shadow_days` (default 60)
2. `sharpe_improvement` (B2 Sharpe ≥ B Sharpe + 0.10)
3. `dd_constraint` (B2 max-DD not materially worse than B + 20% buffer)
4. `divergence_quality` (mean B2-advantage ≥ 0 on divergent days)
5. `routed_not_worse_than_b` (slippage tolerance ≤ 0.05 Sharpe)
6. `operator_approval` (manual flag)

### 6.2 ML promotion state machine

```
NOT_READY ──▶ READY_FOR_REVIEW ──▶ (operator) ──▶ paper_reduce
                                                         │
                                  (kill switch trips) ◀──┘
                                                         │
                                                         ▼
                                                    paper_off
                                                    (revert)
```

Only one promotion direction at a time. Hard blockers
(`ml_can_affect_trades=true`, `system_underperforming_baseline=true`)
override all gates and force `BLOCKED`.

### 6.3 Regime router state machine

```
                       ┌────────────────┐
                       │  market data   │
                       │   not ready    │
                       └────────┬───────┘
                                │
                                ▼
                       ┌────────────────┐
                       │   classified   │
                       └─────┬──────────┘
                             │
                ┌────────────┼────────────┐
                ▼            ▼            ▼
            stress    non-stress      uncertain
              │            │              │
              ▼            ▼              ▼
          Engine A   Directional       no-trade
                       │
                       ▼
                  ENGINE_B_MODE
                  state machine
```

---

## 7. Observability — UI Page Mapping

| Page         | Responsibility                                                  |
|--------------|------------------------------------------------------------------|
| **Overview** | Current state · current route · TradeReadinessIndicator · NextRunCountdown · Engine A/B core + baselines · recent events |
| **Alpha Lab**| Sleeve research console · strategy switcher · edge scoreboard · regime + trend buckets · what-if simulator · TSMOM family comparison |
| **ML Lab**   | ML validation · calibration reliability curve · regime perf · confidence buckets · promotion checklist (12 gates) |
| **Ops**      | Scheduler health · governance · ShadowMLCard · HybridAdvisorCard · HybridReadinessCard · MLReadinessProgressCard · **ShadowStrategyCard** · **EngineBTransitionCard** |
| **Portfolio**| Realized outcomes · paper trade tape · pnl · holdings |

The new `ShadowStrategyCard` and `EngineBTransitionCard` make migration
state visible without exposing any mutation surface.

---

## 8. Rollback Design

Every major switch is reversible via env-var flip + container restart.
NONE of these have an in-DB persistent state that prevents revert.

| Switch                        | Default | Rollback path                |
|-------------------------------|---------|-------------------------------|
| `ENGINE_B_MODE`               | LEGACY  | revert to previous state      |
| `DIRECTIONAL_SLEEVE_MODE`     | (future) | not yet introduced           |
| `ML_HYBRID_MODE`              | advisory| set to advisory               |
| `ML_CAN_AFFECT_TRADES`        | false   | already disabled              |
| `ML_HYBRID_ENABLED`           | false   | set to false                  |
| `ML_HYBRID_ALLOW_BLOCK`       | false   | set to false                  |
| `REGIME_ROUTER_MODE` (future) | (future) | router falls back to LEGACY   |
| `ENGINE_B_OPERATOR_APPROVAL`  | false   | set to false                  |

---

## 9. Data Contracts

### Required tables (all exist today)

| Table                              | Purpose                                  | Write path                   |
|------------------------------------|------------------------------------------|------------------------------|
| `paper_trade_log`                  | Production trades                        | `paper_runner` only          |
| `decision_log`                     | Per-decision audit (incl. ML annotation) | `decision_logger`            |
| `paper_shadow_log` ✱               | B-vs-B2 shadow comparison                | `run_shadow_strategy`        |
| `alpha_rule_snapshot` (jsonb col)  | Rule fingerprint per trade               | `alpha_rule_snapshot_builder`|
| `ml_shadow_prediction`             | ML predictions (advisory)                | `nightly_ml_shadow`          |
| `ml_hybrid_performance_snapshot`   | Hybrid windowed metrics                  | `ml_hybrid_monitor_nightly`  |
| `context_daily`                    | Regime labels (production + diagnostic)  | `context_classifier` + `backfill_research_regime` |
| `ml_model_run`                     | Model fit log                            | `nightly_ml_shadow`          |
| `paper_run_log`                    | Daily orchestrator outcomes              | `run_paper_daily`            |
| `job_schedule` / `job_run`         | Tickloop scheduler                       | worker-tickloop              |

✱ Extended in migration `041_phase_shadow_log` + `042_engine_b_migration_columns`.

### `paper_shadow_log` columns

Core: `as_of_date`, `instrument`, `source_strategy`, `signal`,
`entry_price`, `exit_price`, `fwd_return_1d`, `fwd_return_5d`,
`regime_label`, `engine_a_active`, `trend_score`, `note`.

B-vs-B2 (042): `engine_b_signal`, `b2_signal`, `divergence_flag`,
`divergence_outcome`, `mode_at_decision`, `routed_signal`.

Natural key: `(as_of_date, instrument, source_strategy)`.

### Governance snapshots (future, not required)

If we ever need persistent governance state, add:

```
governance_state_snapshot (
    id uuid, as_of_date date, layer text,
    state text, verdict_json jsonb, advisory_only bool,
    created_at tstz, ...)
```

Currently governance verdicts are computed on-demand from
`paper_shadow_log` + `ml_*` tables. No persistence needed yet.

---

## 10. Rollout Phases

### Phase 1 — Document + architecture (NOW)
- ✅ This document.
- ✅ Stability + edge audit (81/100 confidence).
- ✅ Regime quality audit.
- ✅ Data extension audit (recommendation: 2001+ ES=F).

### Phase 2 — Shadow tracking (CURRENT)
- ✅ `paper_shadow_log` populated daily.
- ✅ `ENGINE_B_MODE=LEGACY` (default).
- ✅ B-vs-B2 divergence captured.
- → 60-90 days of OOS evidence accumulating.
- Required: completion of `ENGINE_B_MIN_SHADOW_DAYS=60` window with all
  promotion gates passing.

### Phase 3 — Controlled B migration
1. `ENGINE_B_MODE=SHADOW_COMPARE` (operator flips). Behaviorally
   identical to LEGACY; just adds extra logging. Wait 30+ days.
2. Promotion gate check → ADVANCE → `PARTIAL_B2_25`. Operator flips env.
3. Each subsequent step requires fresh promotion gate evaluation
   + operator approval. Kill switch can revert at any time.
4. Terminal: `FULL_B2`. Engine B logic preserved (not deleted) for
   research / fallback.

### Phase 4 — ML advisory validation
- Continue `ML_HYBRID_MODE=advisory` accumulation.
- ML labels populate as paper trades close. Need ≥ 30 outcomes for
  promotion eligibility.
- Promotion guard evaluates 12 gates daily. Output advisory only.

### Phase 5 — ML paper_reduce (only if approved)
- All 12 promotion gates pass + operator approval.
- `ML_HYBRID_MODE=paper_reduce`. ML may apply multiplier 0.50-1.0 to
  paper size. Engine A still protected (`engine_a_avg_multiplier ≥ 0.85`).
- Hard blockers immediately revert: `ml_can_affect_trades=true` is
  forbidden until system_underperforming_baseline is decisively false.

---

## 11. Explicit Non-Goals

This architecture does NOT include:
- Real-money execution (not in scope; `ML_CAN_AFFECT_TRADES=false`).
- Multi-asset universe expansion (ES only for now).
- Intraday signal generation (daily resolution only).
- Short side / leveraged products.
- Auto-promotion or auto-revert of any state machine.
- ML-originated trades.
- ML-up-sized trades.
- Hidden flags or dual-state machines.
- Stitched datasets — all-or-nothing per source.
- Re-architecture of `paper_trade_log` or `decision_log` schemas.

---

## 12. Risks + Mitigations

| Risk                                              | Mitigation                          |
|---------------------------------------------------|-------------------------------------|
| Operator forgets to flip back after kill switch   | UI banner + nightly digest          |
| `paper_shadow_log` divergence_outcome backfill    | Idempotent CASE-based UPDATE        |
| Yfinance ES=F roll artifact distorts B2 signal    | p99 abs return < 4.5% — small effect |
| 2018+ Sharpe (0.98) over-states forward expectation | 25-yr backtest sets realistic 0.55-0.70 |
| B2 over-fit to specific regime                    | Sensitivity audit ±10% threshold variants stable |
| Future research changes thresholds                | Logic_version bump + diagnostic status; never overwrites production |
| Test pollution between integration tests          | Synthetic dates (e.g. 2099-12-30) used for upsert tests |
| Multi-decade extension not yet applied to production regime | research_backfill_v1 stays diagnostic; production v1.0.0 unchanged |
| Shadow runner failure breaks daily loop           | Wired as OPTIONAL — failure is non-blocking |

---

## Files Referenced

```
apps/api/src/config/__init__.py                      # ENGINE_B_MODE etc.
apps/api/src/research/engine_b_router.py             # routing logic
apps/api/src/research/engine_b_promotion.py          # gate + kill switch
apps/api/src/research/engine_b2.py                   # B2 strategy
apps/api/src/research/regime_backfill.py             # regime classifier
apps/api/src/research/shadow_strategy.py             # daily shadow logger
apps/api/src/governance/promotion_engine.py          # 12-gate ML guard
apps/api/src/governance/engine_b_policy.py           # Engine B advisory policy
apps/api/src/governance/baseline_enforcement.py      # baseline comparison
apps/api/src/governance/drift_monitor.py             # PSI / Sharpe / regime drift
apps/api/src/governance/alerting.py                  # rule-based alerts
apps/api/src/api/shadow.py                           # /api/shadow/*
apps/api/src/api/engine_b_transition.py              # /api/engine-b/transition
infra/alembic/versions/041_phase_shadow_log.py
infra/alembic/versions/042_engine_b_migration_columns.py
scripts/run_shadow_strategy.py                       # daily runner
scripts/backfill_research_regime.py
scripts/engine_b_candidate_sweep.py
scripts/audit_*.py                                   # multiple audit scripts

apps/web/src/components/ops/ShadowStrategyCard.tsx
apps/web/src/components/ops/EngineBTransitionCard.tsx
apps/web/src/lib/shadow/hooks.ts
apps/web/src/lib/engineB/hooks.ts
```

Migrations applied: 040 → 041 → 042. Head: `042_engine_b_migration_columns`.

---

## Confirmation: No Execution Change Until Mode != LEGACY

**Until `ENGINE_B_MODE` is manually changed by an operator from `LEGACY`
to a value in `{SHADOW_COMPARE, PARTIAL_B2_25, PARTIAL_B2_50,
PARTIAL_B2_75, FULL_B2}`, the production execution path is byte-for-byte
unchanged.**

- LEGACY: routed_engine = B, execution_changed = False.
- SHADOW_COMPARE: routed_engine = B, execution_changed = False.
  (Adds extra logging only.)
- PARTIAL_B2_*: execution_changed = True (operator-approved migration).
- FULL_B2: execution_changed = True (operator-approved migration).

All production trade-execution paths still call the existing Engine B
logic when `ENGINE_B_MODE in {LEGACY, SHADOW_COMPARE}`. The router
output is consumed by the shadow logger only — **the live trade runner
is not yet wired to read `routed_signal`**, by design. Wiring is a
separate phase, gated on operator approval of migration.

This is the intentional safety boundary between architecture and
execution.
