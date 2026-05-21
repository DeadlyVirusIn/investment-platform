# Options paper trading — full forensic audit

**Date**: 2026-05-19
**Method**: read-only DB + code inspection. No execution attempted.
**Headline verdict**: **Category D — OFF but misleadingly surfaced.** Options paper trading is structurally dormant by design (master flag off, two key worker jobs are explicit stubs). But 22+ UI pages route as if the system functions, with a banner that misleads users into thinking a "simulated lifecycle" is actually running.

---

## ONE-PARAGRAPH BOTTOM LINE

Master switch `OPTIONS_ENABLED=false`. Canary switch `OPTIONS_CANARY_ENABLED=false`. The two worker jobs that would actually execute options trades (`options_canary_promotion` and `options_lifecycle_check`) are explicit stubs whose bodies log "Phase 1A/1B pending — noop" and return `{skipped: True}` even WHEN the gate is ON. **The database has 1 single `options_paper_trade` row, status='PROPOSED', from 2026-05-04, that never transitioned to OPEN or CLOSED.** Zero positions, zero lifecycle events, zero funnel telemetry. Chain data ingestion stopped 6 days ago (last write 2026-05-13). Shadow-eval also stopped 2026-05-13 — its cron has been running successfully but producing zero new rows. Despite all of this, the WebUI exposes 22+ options pages including "Paper trades," "Risk dashboard," "Positions," "Performance," "Lab," "Ops," "Decision Support," and a "Paper-only" banner saying "simulated lifecycle. No live orders." That banner is technically correct but operationally misleading — there IS no lifecycle running.

---

## PASS / FAIL MATRIX

| Criterion | Status | Evidence |
|----|----|----|
| Option recommendation generated | PARTIAL | 67 `options_strategy_candidate` rows exist, but ALL dated 2026-05-03 or 2026-05-13 (6+ days stale) |
| Option trade opened | **NO** | 1 row in `options_paper_trade`, status='PROPOSED', never transitioned |
| Option trade closed | **NO** | `closed_at` is NULL on the one trade |
| Cash updated | **NO** | `canary-spy-v1` portfolio: `cash_initial=2000`, `cash_current=2000` (zero delta) |
| Position updated | **NO** | 0 rows in `options_paper_position` |
| P&L updated | **NO** | `realized_pnl_dollars` is NULL on the one trade |
| Telemetry written | PARTIAL | `options_execution_funnel`: 0 rows. `options_shadow_decision_log`: 7505 rows but ALL from 2026-05-03/13 |
| UI reflects truth | **NO** | 22+ pages routed despite no lifecycle |
| No fake placeholders | **NO** | "Paper-only" banner implies a working simulated lifecycle |

---

## 1. OPTIONS RECOMMENDATION GENERATION

### Q: Are options recommendations generated?

**PARTIAL — only as shadow observations, and dormant since 2026-05-13.**

### Storage tables

| Table | Rows | Status |
|-------|------|--------|
| `options_strategy_candidate` | 67 | Dormant since 2026-05-13 |
| `options_shadow_decision_log` | 7505 | Dormant since 2026-05-13 |
| `options_strategy_outcome` | 45 | — |
| `options_strategy_bias` | 19 | — |
| `options_strategy_playbook` | 19 | — |
| `options_ai_playbook` | 7 | — |

### Action semantics

Options decisions do NOT use Buy/Sell/Trim semantics like stocks. Instead they use:
- `bias` (text) — directional view (BULLISH/BEARISH/NEUTRAL)
- `directional_view` (text)
- `risk_profile` (text)
- `strategy_name` — e.g. BULL_CALL_SPREAD, IRON_CONDOR, etc.
- `composite_score` (numeric)
- `confidence` (numeric)

The system is leg-based, not single-instrument. Each "decision" is a strategy proposal with multiple option legs (defined in `options_paper_trade_leg`).

### Recent activity

```sql
SELECT run_date, COUNT(*) FROM options_strategy_candidate GROUP BY 1 ORDER BY 1 DESC;
2026-05-13 | 62
2026-05-03 |  5
```

```sql
SELECT DATE(created_at), COUNT(*) FROM options_shadow_decision_log GROUP BY 1 ORDER BY 1 DESC;
2026-05-13 | 7495
2026-05-03 |   10
```

**Today (2026-05-19) is 6 days past the most recent shadow-eval activity.** Shadow eval cron has been running successfully ("success" duration ~15s on 2026-05-19 01:45 UTC) but producing zero new rows.

---

## 2. OPTIONS PAPER EXECUTION

### Q: Is there an options equivalent of paper_trade?

**YES — full schema exists.**

### Schema (verified)

| Table | Purpose | Row count |
|-------|---------|-----------|
| `options_paper_portfolio` | Portfolios with capital + risk caps | 1 |
| `options_paper_trade` | Multi-leg strategy execution rows | **1** |
| `options_paper_trade_leg` | Individual option contract legs per trade | 2 |
| `options_paper_position` | Open positions | **0** |
| `options_chain_snapshot` | Bid/ask/Greeks per option | 6561 (stale) |
| `options_feature_daily` | Daily option features | 25 |
| `options_trade_lifecycle_event` | Open/close/expiry/assign events | **0** |
| `options_expiration_event` | Expiration outcomes | **0** |
| `options_assignment_event` | Assignment outcomes | **0** |
| `options_execution_funnel` | Funnel telemetry | **0** |

### Are option contracts represented?

YES. `options_paper_trade_leg` carries:
- `option_symbol` (e.g. `AMZN260618C00275000`)
- `underlying`, `expiry`, `strike`, `option_type` (CALL/PUT)
- `side` (BUY/SELL), `qty`
- `entry_quote_at_utc`, `entry_bid`, `entry_ask`, `entry_mid`, `entry_iv`
- All Greeks (`entry_delta`, `entry_gamma`, etc.)

The ORM design is correct and complete.

### Are fills simulated?

**NO.** The `options_lifecycle_check` worker is the job responsible for transitioning `PROPOSED → OPEN`. Its body is an explicit stub:

```python
# apps/worker/src/jobs/options_lifecycle_check.py
async def run_options_lifecycle_check() -> dict:
    enabled = bool(getattr(settings, "OPTIONS_CANARY_ENABLED", False))
    if not enabled:
        logger.info("[options_lifecycle_check] OPTIONS_CANARY_ENABLED=false — noop")
        return {"skipped": True, "reason": "canary_disabled"}

    logger.info("[options_lifecycle_check] gate ON but body not yet shipped (Phase 1B pending) — noop")
    return {"skipped": True, "reason": "phase1b_not_shipped"}
```

**Even if `OPTIONS_CANARY_ENABLED` were flipped to true, the body returns sentinel — no fills happen.**

### Is there next-bar/T+1 logic?

The DESIGN includes it (per the stub's docstring): "Phase 1B target body ... If snapshot.snapshot_at_utc::date > opened_at::date (next-bar discipline) ..." — but NOT implemented.

### Are option chains available for fill pricing?

PARTIAL. 6561 chain rows exist. **ALL dated 2026-05-13 17:47 UTC.** Tradier sandbox provider. Last ingest cron success at 2026-05-19 01:30 UTC (74 sec duration) — but zero new rows since 2026-05-13. Either:
- The sandbox is rate-limited / returning empty
- The ingest job is silently no-op'ing (e.g. dedup on natural key against unchanged data)
- The sandbox API is returning the same point-in-time data

### Are bid/ask/mid prices used?

Schema supports them (`entry_bid`, `entry_ask`, `entry_mid` columns). NOT exercised because no fills occur.

### Are expiration, strike, contract type, quantity handled?

Schema supports all. Not exercised.

---

## 3. OPTIONS SELL / EXIT LIFECYCLE

### Q: Are option positions opened?

**NO.** Zero rows in `options_paper_position`.

### Q: Are option positions closed?

**NO** (cannot close what was never opened).

### Q: Are TP/SL/max-hold/expiry exits implemented?

The DESIGN exists. The stub docstring describes the intended afternoon-evaluation pass:
- target_pct hit → transition_to_close (target_hit)
- stop_pct hit → transition_to_close (stop_hit)
- DTE <= time_stop_dte → transition_to_close (time_stop)
- At expiry: assignment-precedence rule routes to transition_to_assigned / _expired

**None of this is implemented in code.** The Phase 1B body has not been written.

### Q: Are expired contracts handled?

NO. `options_expiration_event` table: 0 rows. Module exists (`apps/api/src/options/lifecycle.py` presumably) but its expiry-handling functions are not called by any active job.

### Q: Is cash credited/debited correctly?

UNTESTED — cash flow path never executes.

### Q: Are option P&L and Greeks updated?

NO. Schema supports it, no code path exercises it.

---

## 4. CRON / SCHEDULER

### Scheduled options jobs

| Job | Cron | Last run | Status | Duration |
|-----|------|----------|--------|----------|
| `options_chain_snapshot` | 21:30 ET | 2026-05-19 01:30 UTC | success | 74.23s |
| `compute_options_features` | 21:35 ET | 2026-05-19 01:35 UTC | success | 0.028s |
| `options_shadow_eval` | 21:45 ET | 2026-05-19 01:45 UTC | success | 0.015s |
| `run_options_canary_promotion` | 22:00 ET | 2026-05-19 02:00 UTC | **skipped** | 0.005s |
| `run_options_lifecycle_check` | 13:30 ET | 2026-05-18 17:30 UTC | **skipped** | 0.016s |

### Were they skipped, disabled, erroring, or silently doing nothing?

| Job | Behavior |
|-----|----------|
| chain_snapshot | RUNS but produces zero new rows (since 2026-05-14) |
| features_compute | RUNS in 0.028s — likely silent no-op |
| shadow_eval | RUNS in 0.015s — fast suggests early-exit (no new chain data → no new shadow rows) |
| canary_promotion | EXPLICITLY SKIPPED via stub return value |
| lifecycle_check | EXPLICITLY SKIPPED via stub return value |

The two job_run rows for canary_promotion and lifecycle_check show `status='skipped'` (per D2.3 wrapper-RC honesty work — `{skipped: True}` returns classify as 'skipped' rather than 'success').

**The wrapper-RC telemetry is honest.** The system correctly self-reports that these jobs are skipped. The dishonesty is in the UI layer, which doesn't tell users this.

---

## 5. UI TRUTHFULNESS — CRITICAL FINDING

### 22+ options pages routed in `App.tsx`

| Route | Page component | Implies functioning? |
|-------|----------------|------------------------|
| `/options/overview` | `OptionsOverviewPage` | YES (research pulse hero + candidates) |
| `/options/chain` | `OptionsChainPage` | partial — read-only chain view |
| `/options/features` | `OptionsFeaturesPage` | partial |
| `/options/trades` | `OptionsPaperTradesPage` | **YES — explicitly says "Multi-leg paper options trades... Simulated by the options paper engine"** |
| `/options/risk` | `OptionsRiskDashboardPage` | YES (suggests live risk monitoring) |
| `/options/positions` | `OptionsPositionsPage` | YES |
| `/options/performance` | `OptionsPaperPerformancePage` | YES |
| `/options/observatory` | `OptionsStrategyObservatoryPage` | partial |
| `/options/diagnostics` | `OptionsStrategyDiagnosticsPage` | YES |
| `/options/replay` | `OptionsScenarioReplayPage` | YES |
| `/options/evaluation` | `OptionsStrategyEvaluationPage` | YES |
| `/options/decision-support` | `OptionsDecisionSupportPage` | YES |
| `/options/decision-framing` | `OptionsDecisionFramingPage` | YES |
| `/options/research` | `OptionsResearchUniversePage` | partial — research-only is honest |
| `/options/journal` | `OptionsJournalUnifiedPage` | YES (suggests trade journal) |
| `/options/learning` | `OptionsLearningPage` | educational — OK |
| `/options/learn/*` | `OptionsPlaybookLibraryPage` etc | educational — OK |
| `/options/approaches/*` | `OptionsApproachLibrary*` | educational — OK |
| `/options/lab` | `OptionsLabPage` | partial |
| `/options/ops` | `OptionsOpsPage` | YES (operator surface) |
| `/options/settings` | `OptionsSettingsPage` | partial |
| `/options/opportunities` | `OptionsOpportunitiesPage` | YES |

### The "Paper-only" banner

Located at `apps/web/src/components/options/OptionsPaperOnlyBanner.tsx`:

```tsx
<span className="font-semibold">Options are paper-trading only</span>
<span className="text-amber-200/80">
  — simulated lifecycle. No live orders. No execution. No ML signals.
</span>
```

This banner appears on `OptionsPaperTradesPage` and likely other surfaces. The text implies:
- "paper-trading only" — TRUE (only paper, never real)
- "simulated lifecycle" — **FALSE** — there IS no simulated lifecycle running
- "No live orders" — TRUE (no real-money orders)
- "No execution" — **AMBIGUOUS** — meant as "no real-money execution," but actually true also for paper

The banner is technically defensible per its narrow legal reading. Operationally it MISLEADS — a user reads "simulated lifecycle" and expects to see simulated trades happening.

### OptionsPaperTradesPage intro text

```tsx
<p>
  Simulated by the options paper engine. Separate from
  your stock paper trades. Read-only — nothing here places
  real orders. Click a row for full leg detail.
</p>
```

"Simulated by the options paper engine." → IMPLIES an engine is running. There is no running engine.

### Verdict per page (recommended disposition)

| Page | Current state | Should be |
|------|---------------|-----------|
| OptionsPaperTradesPage | 1 row "PROPOSED", never transitioned | **HIDE or banner: "Lifecycle dormant — Phase 1B pending"** |
| OptionsPositionsPage | 0 positions | **HIDE** (page describes empty state but user can't tell why) |
| OptionsRiskDashboardPage | computed from 0 positions | **HIDE** |
| OptionsPaperPerformancePage | 0 trades to measure | **HIDE** |
| OptionsStrategyObservatoryPage | observes shadow data | acceptable as research |
| OptionsResearchPage / OptionsResearchUniversePage | read-only research | **acceptable** if banner says "research observations" |
| OptionsOpportunitiesPage | shows candidates | acceptable as research surface |
| OptionsOpsPage | operator-only | acceptable |
| OptionsSettingsPage | governance | acceptable |
| OptionsLearningPage / OptionsPlaybookLibraryPage | educational | acceptable |
| All "DecisionSupport / DecisionFraming / StrategyEvaluation" | analytical | implies actionable — banner needed |

---

## 6. DEPLOYMENT DRIFT

Per the recent stock-side deployment-drift incident, checked whether options code suffers similar gaps.

### API container

10 options migrations applied (047 → 077 in alembic history). Phase L migrations 078-088 applied on top. ORM model in `apps/api/src/db/models.py` carries all options table classes.

### Workers

Worker containers also need the options table classes since they could import models.py during cron jobs. Recent deployment (paper_service.py + models.py to both workers) addressed PaperEquitySnapshot drift. **The options table classes inside models.py are now also present on workers.**

### Risk

The 5 options worker jobs import their own modules. If any of those modules were modified during Phase L and not synced to workers, the options jobs could fail silently. The stubs themselves don't import much, so risk is low for canary_promotion + lifecycle_check.

The 3 active jobs (chain_snapshot, features_compute, shadow_eval) have last-run statuses of `success`, so they execute without raising. Whether they produce CORRECT data is a separate question.

### Why no new chain data since 2026-05-13?

Hypothesis 1: Tradier sandbox returns stale snapshot (sandbox accounts are limited).
Hypothesis 2: The ingest does INSERT ON CONFLICT DO NOTHING — same chain values from sandbox get dedup'd.
Hypothesis 3: Chain ingest code has been silently failing per-symbol but reporting overall success.

Cannot resolve without inspecting `ingest_universe()` code path, which is out of scope for this audit (would require deeper investigation).

---

## 7. MINIMAL PROOF TEST — what would prove options paper trading works

The smallest safe end-to-end validation:

### Pre-conditions (all currently FAIL)

- [ ] Fresh chain data in `options_chain_snapshot` for today (`snapshot_at_utc::date = today`)
- [ ] At least one `options_strategy_candidate` row for today
- [ ] `OPTIONS_ENABLED = true` AND `OPTIONS_CANARY_ENABLED = true`
- [ ] `options_canary_promotion` body shipped (Phase 1A)
- [ ] `options_lifecycle_check` body shipped (Phase 1B)
- [ ] Canary portfolio `active = true`

### Minimal test sequence (when pre-conditions met)

1. Manual run `options_canary_promotion` → should produce 1 row in `options_paper_trade` with `status='PROPOSED'`
2. Manual run `options_lifecycle_check` (morning fill pass) → should transition `PROPOSED → OPEN`, create rows in `options_paper_position`, `options_paper_trade_leg` with entry quotes, decrement `cash_current`
3. Wait 1 day (or manual time-advance) for new chain data
4. Manual run `options_lifecycle_check` (afternoon eval pass) → if TP/SL/DTE hit, transition `OPEN → CLOSED`, set `realized_pnl_dollars`, increment `cash_current`
5. Verify `options_trade_lifecycle_event` rows for OPEN + CLOSE
6. Verify `options_execution_funnel` row for the run

**None of steps 1-6 are reachable today.** Steps 1 and 2's code does not exist (Phase 1A/1B not shipped).

---

## 8. FINAL CLASSIFICATION

**Category D — OFF but misleadingly surfaced.**

Reasoning:
- Architecturally: paper-only flag in DB schema (`paper_only=true` default), master flag off, canary off, stubs in place
- Behaviorally: zero trades opening, zero closing, zero cash movement
- UI-wise: 22 pages routed with "Paper-only" banner that implies a running simulated lifecycle
- Truth-contract violation: the banner says "simulated lifecycle" but no lifecycle is running

Not Category E (dangerous) because:
- No real-money path exists
- `paper_only=true` is enforced at schema level
- All worker stubs explicitly return `{skipped: True}` even if gates flipped

But not Category C (off but honestly hidden) because:
- Pages ARE reachable from the main nav
- "Paper-only" banner implies functionality that doesn't exist
- A user clicking through cannot tell from the UI alone that nothing is running

---

## RECOMMENDED MINIMAL FIX (do NOT implement without approval)

The honest options posture requires choosing between three paths:

### Option HONEST-HIDE (smallest)
- Move all options routes behind a feature flag check
- Hide options entries from main navigation
- Show a single placeholder page at `/options` reading: "Options paper trading is in development. Currently dormant."

### Option HONEST-BANNER (medium)
- Add a global top-of-options banner: "The options lifecycle is currently dormant. The pages below show research and design surfaces only. No simulated trades are running."
- Keep existing pages but every page MUST render this banner
- Remove the current "Paper-only" banner that implies a running lifecycle

### Option HONEST-ACTIVATE (largest)
- Ship Phase 1A (canary promotion logic) per the stub's docstring
- Ship Phase 1B (lifecycle fill + close logic)
- Re-enable `OPTIONS_CANARY_ENABLED`
- Validate end-to-end via the 6-step minimal test
- Then UI is truthful by virtue of the system actually running

**Recommended**: HONEST-BANNER. Lowest effort, restores truth without hiding research work that genuinely exists (the shadow_eval observations and strategy candidates ARE real research artifacts, just operationally dormant).

---

## ARTIFACTS SAVED

- The 1 `options_paper_trade` row (id=2, AMZN BULL_CALL_SPREAD, status=PROPOSED)
- The 2 leg rows attached to it
- 6561 stale chain snapshots from 2026-05-13
- 7505 shadow decision rows
- 67 strategy candidates

All artifacts are paper-only by schema enforcement (`paper_only BOOLEAN NOT NULL DEFAULT true`). No risk of real-money leakage.

---

## CLOSING NOTE

The options system architecture is more complete than I expected — 16 tables, 10 migrations, 9 API router files, 22+ UI pages, 5 worker jobs. The reasoning, observation, and journaling surfaces ARE doing useful work (the shadow decision log captures decisions the system WOULD have made). 

The missing piece is the actual execution lifecycle. Without Phase 1A and Phase 1B shipped, none of the candidate proposals ever become trades, and the entire "paper trading" promise on the UI is unfulfilled.

The system is not lying outright, but it IS misleading by omission. The "Paper-only" banner is the load-bearing untruth — it implies a running simulation that doesn't exist. Until Phase 1A/1B ship, the UI should disclose this state plainly.
