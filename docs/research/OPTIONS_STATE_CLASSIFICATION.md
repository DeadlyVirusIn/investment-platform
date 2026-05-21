# OPTIONS_STATE_CLASSIFICATION

**Status**: Operational classification memo.
**Date**: 2026-05-19, post-HONEST-BANNER cleanup.
**Purpose**: state explicitly what is operational vs research vs dormant, so the UI, copy, and future plans align with truth.

---

## Stocks vs Options — operational contract

| Dimension | **Stocks** | **Options** |
|-----------|-----------|-------------|
| Architectural state | OPERATIONAL SYSTEM | RESEARCH / DORMANT SUBSTRATE |
| Live cron produces trades | YES (52 live-path trades, 2026-05-19) | NO (1 PROPOSED row from 2026-05-04; never transitioned) |
| Sell / exit cycle runs | YES (2 SL closes today, 40 historical sells) | NO (lifecycle_check is a stub) |
| Cash recycles | YES (proven sell → free → buy cycle) | NO (canary cash unchanged from initial) |
| Phase L envelope generation | LIVE-WIRED (43 live audit rows) | N/A — no trades to attach to |
| UI surface contract | "operating system" framing | "research and observation surfaces" framing |

This split is the central operational truth and the reason for separate UI banners and copy.

---

## Definition: "dormant" (Options)

Options paper trading is **structurally dormant**. This is more specific than "off" or "disabled":

- **The DESIGN is shipped**: 16 DB tables, 10 alembic migrations applied, ORM models present, 9 API router files, 22 UI pages, 5 worker jobs registered in cron.
- **The OBSERVATION layer is active**: chain ingest job runs (though data has been stale since 2026-05-13), features compute runs, shadow eval runs and persists decision logs.
- **The EXECUTION bodies are explicit stubs**: `options_canary_promotion` and `options_lifecycle_check` worker jobs return `{skipped: True, reason: "phase1aX_not_shipped"}` even when their gate flag is ON.
- **No simulated trades execute**: zero positions, zero fills, zero closes, zero cash movement, zero lifecycle events.

Dormant ≠ broken. Dormant means: the system intentionally does not yet run the execution lifecycle. Activation requires deliberate code shipping (Phase 1A + Phase 1B), not just flag flips.

---

## What IS implemented

### Database schema (10 migrations)
- `047_phase11b_options_schema` — core paper portfolio / trade / position / leg tables
- `056_options_shadow_decision_log` — shadow observation logging
- `062_options_paper_strategy_extension` — strategy proposal extensions
- `063_options_strategy_outcome` — outcome scoring
- `068_options_analytics_indexes`
- `069_options_canary_pre0` — canary portfolio + scheduler stubs
- `072_options_strategy_bias`
- `073_options_strategy_candidate`
- `076_options_strategy_playbook`
- `077_options_ai_playbook`

### Worker jobs (registered + scheduled)

| Job | Cron (ET) | Body | Behavior |
|-----|-----------|------|----------|
| `options_chain_snapshot` | 21:30 | ACTIVE | runs ingest_universe(), persists chain rows |
| `compute_options_features` | 21:35 | ACTIVE | computes daily features |
| `options_shadow_eval` | 21:45 | ACTIVE | evaluates shadow decisions, writes log |
| `run_options_canary_promotion` | 22:00 | **STUB** | returns {skipped: True, reason: "phase1a_not_shipped"} |
| `run_options_lifecycle_check` | 13:30 | **STUB** | returns {skipped: True, reason: "phase1b_not_shipped"} |

### Provider integration

- `OPTIONS_DATA_PROVIDER=tradier` (sandbox)
- `provider_version=tradier-sandbox`
- 6561 chain snapshots ingested (all dated 2026-05-13; stale since)

### API surface (read-only)

9 router files, ~20 endpoints, ALL `GET`:
- `options/canary/routes.py` — portfolio + funnel telemetry
- `options/journal/routes.py` — timeline + trade evolution
- `options/opportunities/routes.py` — research opportunities
- `options/playbooks/routes.py` — playbook library
- `options/ai_playbooks/routes.py` — AI playbook variants
- `options/positions/routes.py` — position intelligence
- `options/research/routes.py` — research universe / underlying
- `options/routes_readonly.py` — broad read-only surface
- `options/routes_analytics.py` — analytics

No POST/PUT/PATCH/DELETE anywhere — execution is not exposed via API.

### UI surface

22 pages routed under `/options/*` in `App.tsx`. Each page renders `OptionsPaperOnlyBanner` either via `OptionsLayout` or directly. Banner copy now reflects HONEST-BANNER framing.

### Research artifacts (real data, dormant since 2026-05-13)

- `options_strategy_candidate`: 67 rows (62 from 2026-05-13, 5 from 2026-05-03)
- `options_shadow_decision_log`: 7505 rows (7495 from 2026-05-13, 10 from 2026-05-03)
- `options_strategy_outcome`: 45 rows
- `options_strategy_bias`: 19 rows
- `options_strategy_playbook`: 19 rows
- `options_ai_playbook`: 7 rows
- `options_feature_daily`: 25 rows

These are real, useful research observations. They are NOT trades.

---

## What is INTENTIONALLY NOT yet active

### Phase 1A — Canary promotion logic

`apps/worker/src/jobs/options_canary_promotion.py` documents the intended Phase 1A body in its docstring:

> 1. Read today's would_trade=true rows from options_shadow_decision_log filtered by universe + strategy
> 2. Apply DTE window
> 3. Check canary-spy-v1 portfolio open-trade count vs OPTIONS_CANARY_MAX_OPEN
> 4. Check capital cap vs OPTIONS_CANARY_MAX_CAPITAL_USD
> 5. Build OptionLegSpec list from Tradier sandbox quotes
> 6. Call persist_option once per allowed promotion (max 1/day in Phase 1A)
> 7. Write options_execution_funnel row with rollup counts

None of these steps are implemented.

### Phase 1B — Lifecycle fill + close logic

`apps/worker/src/jobs/options_lifecycle_check.py` documents Phase 1B intent:

> Morning fill pass (PROPOSED → OPEN):
>   1. SELECT * FROM options_paper_trade WHERE status='PROPOSED' AND opened_at::date < today
>   2. For each: query latest options_chain_snapshot for the legs
>   3. If snapshot date > opened_at date (next-bar discipline): call lifecycle.transition_to_fill
>   4. Reserve capital in options_paper_position
>   5. Decrement options_paper_portfolio.cash_current
>
> Afternoon evaluation pass (OPEN → CLOSED/EXPIRED/ASSIGNED):
>   a. Compute current spread mid from latest chain
>   b. If target_pct hit → transition_to_close (target_hit)
>   c. If stop_pct hit → transition_to_close (stop_hit)
>   d. If DTE <= time_stop_dte → transition_to_close (time_stop)
>   e. At expiry: assignment-precedence rule

None of these are implemented.

### Library functions that DO exist but are not called

- `apps.api.src.options.persist_option.persist_option` — function exists, awaiting Phase 1A caller
- `apps.api.src.options.lifecycle.transition_to_fill` — function exists, awaiting Phase 1B caller
- `apps.api.src.options.lifecycle.transition_to_close` — function exists
- `apps.api.src.options.lifecycle.transition_to_expired` — function exists
- `apps.api.src.options.lifecycle.transition_to_assigned` — function exists

The execution library is ready. The orchestrating worker bodies are not.

---

## Flag matrix (current values)

| Flag | Value | Effect |
|------|-------|--------|
| `OPTIONS_ENABLED` | **false** | master switch — paper execution master OFF |
| `OPTIONS_CANARY_ENABLED` | **false** | canary promotion gate OFF |
| `OPTIONS_PAPER_ONLY` | **true** | safety — schema-level enforcement |
| `OPTIONS_ML_CAN_AFFECT_TRADES` | **false** | safety — ML cannot influence execution |
| `OPTIONS_SHADOW_EVAL_ENABLED` | **true** | research persistence — shadow log writes |
| `OPTIONS_DATA_PROVIDER` | `tradier` | active for sandbox ingestion |

Even flipping `OPTIONS_ENABLED=true` and `OPTIONS_CANARY_ENABLED=true` would NOT cause trades to fire, because the worker bodies are stubs. Activation requires CODE shipping, not flag flipping.

---

## Activation path (Phase 1A → 1B) — for future planning, NOT to be implemented now

The path from dormant to operational, in order:

1. **Phase 1A**: Implement `options_canary_promotion` body per its docstring. Validates that shadow-eval winners can be promoted to `PROPOSED` trades within capital/risk limits. Single-portfolio (canary-spy-v1), single-strategy (BULL_CALL_SPREAD), max 1/day.

2. **Phase 1A validation**: End-to-end manual test — one promotion attempted, one `PROPOSED` row created, one `options_execution_funnel` row written, no lifecycle progression.

3. **Phase 1B**: Implement `options_lifecycle_check` morning fill pass. Transitions `PROPOSED → OPEN` against next-bar chain data. Creates `options_paper_position`, decrements `cash_current`.

4. **Phase 1B validation**: Manual test — one `PROPOSED` filled, one position open, cash debited, capital reserved.

5. **Phase 1B afternoon pass**: Implement TP/SL/DTE/expiry close logic. Transitions `OPEN → CLOSED/EXPIRED/ASSIGNED`. Realized P&L recorded.

6. **Phase 1B validation**: End-to-end — manual fill + close cycle, cash recycled.

7. **Canary observation**: Run for 4-6 weeks with the single-portfolio canary. Confirm no economic anomalies.

8. **Broader activation**: Only after canary observation. Out of scope for this memo.

Estimated effort: Phase 1A ~2-3 days, Phase 1B ~3-5 days, canary observation 4-6 weeks. **Do not begin without explicit operator decision.**

---

## UI copy contract (HONEST-BANNER, now in effect)

### Global banner — `OptionsPaperOnlyBanner.tsx`

| Element | Copy |
|---------|------|
| Title | "Options lifecycle is currently dormant" |
| Body | "These pages show research, candidates, and observation surfaces. No simulated options trades are running — no fills, no closes, no P&L. The execution path is intentionally unshipped pending Phase 1A / 1B activation." |
| Test ID | `options-lifecycle-dormant-banner` |

### Phrases REMOVED from the codebase

- ~~"simulated lifecycle"~~ (was in banner)
- ~~"Simulated by the options paper engine"~~ (was in PaperTradesPage intro)
- ~~"v1 paper engine"~~ (was in RiskFlagsPanel assignment explanation)

### Phrases that remain OK

- "Shadow only — Engine observes; no paper or live execution" (already honest)
- "Canary armed — Single-portfolio paper canary active" (will be honest when activated)
- "Broad execution — Full paper-execution gate is on" (will be honest when activated)
- "No paper trades yet" (already honest)
- Internal code identifiers (`engineLabel`, `engine_state`, etc.) — not user-visible

### Page-level copy

- `OptionsPaperTradesPage` intro now reads "Strategy proposal records and their multi-leg structure. The lifecycle that would fill, monitor, and close these is currently dormant — no simulated orders are placed."
- `OptionsRiskFlagsPanel` assignment explanation now references "the v1 design model" and parenthetically notes "Lifecycle dormant — no live or simulated executions today."

---

## What changed today (deliverable manifest)

- `apps/web/src/components/options/OptionsPaperOnlyBanner.tsx` — rewrote banner content
- `apps/web/src/pages/options/OptionsPaperTradesPage.tsx` — replaced intro paragraph
- `apps/web/src/components/options/OptionsRiskFlagsPanel.tsx` — updated assignment model copy

3 files. Pure copy / framing change. No execution path activated. No flags flipped. No new endpoints. No new schemas. No Phase L touched. No stocks affected.

---

## Closing principle

The operations posture is now consistent:

- **Honest absence on stocks**: "We don't have a clear read on this one" (Phase L UI-1)
- **Honest dormancy on options**: "Options lifecycle is currently dormant"

Both use the same constitutional pattern: locked operator-authored copy that names the absence as a deliberate behavior, not as broken software.

Stocks ran into operational bugs (anchor math, deployment drift) that surfaced as silent failures. Options ran into a different category — unshipped code that the UI implied was working. Both are now disclosed plainly.
