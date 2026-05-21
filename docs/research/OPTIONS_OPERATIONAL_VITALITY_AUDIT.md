# Options Operational Vitality Audit (OOVA)

**Date**: 2026-05-16
**Trigger**: After stock OVA closure, user explicitly demanded same forensic depth for options before claiming any options health
**Methodology**: Two parallel Haiku agents (code-side + DB-side), evidence over philosophy
**Status**: Verdict reached. Composite D + B + C + structural unimplemented.

---

## Executive verdict

> **Options is not a functioning paper lifecycle. It is a real engine + real schema + real shadow telemetry + real UI, with the entire PROPOSED → OPEN → CLOSED execution chain explicitly stubbed and self-labeled `phase1a_not_shipped` / `phase1b_not_shipped`.**
>
> **Flags being OFF is the second-layer block. Even if all three flags flipped to True today, NOTHING would happen — the scheduled job bodies are explicit no-ops that return without writing.**

Using the user's verdict palette:

- **(A) Functioning end-to-end paper lifecycle** → NO
- **(B) Shadow-only research system** → PARTIAL — shadow data exists but is 70+ hours stale; not continuously refreshing
- **(C) Proposal-only system** → PARTIAL — 1 PROPOSED trade exists, operator-seeded, never advanced
- **(D) Blocked by execution gates** → YES — three flags + two explicit Phase 1A/1B stubs
- **(E) Temporally deadlocked (stock-style)** → NO — no temporal conflict because no execution attempted
- **(F) Not enough data to say** → NO — evidence is complete

**Best-fit composite**: D-primary + B/C secondary. The lifecycle is *structurally not implemented*, not bugged.

---

## Smoking guns (raw evidence)

| # | finding | number |
|---|---|---|
| 1 | options_paper_trade rows | **1** (PROPOSED from 2026-05-06, AMZN) |
| 2 | options_paper_position rows | **0** |
| 3 | options_trade_lifecycle_event rows | **0** (audit trail entirely absent) |
| 4 | options_execution_funnel rows | **0** |
| 5 | Days since last chain ingest | **70+ hours** (single batch 2026-05-13 17:47 UTC) |
| 6 | Underlyings ever covered | **5** (SPY, QQQ, IWM, GLD, TLT) |
| 7 | AMZN ever in options_chain_snapshot | **0 rows** — yet AMZN is the underlying of the 1 PROPOSED |
| 8 | options_strategy_outcome rows in `good`/`neutral`/`bad`/`pending` | **0** (all 45 are `data_blocked`) |
| 9 | Canary portfolio status | created 2026-05-14, **`active=false`** — operator note says "active=false until Phase 1B opens fill path" |
| 10 | Options jobs scheduled | 5 (chain_snapshot, shadow_eval, features_compute, canary_promotion, lifecycle_check) |
| 11 | Options jobs firing successfully | 5/5 — all report status=success daily |
| 12 | Options jobs doing actual work | **0/5** — all silent-skip per flag/stub |
| 13 | OPTIONS_ENABLED default | `False` |
| 14 | OPTIONS_CANARY_ENABLED default | `False` |
| 15 | OPTIONS_SHADOW_EVAL_ENABLED default | `False` |
| 16 | Scheduled job stub literals | `phase1a_not_shipped`, `phase1b_not_shipped` (in return values) |
| 17 | UI POST/PUT/PATCH/DELETE endpoints for options | **0** (test-enforced read-only) |
| 18 | UI components for options | 78 |
| 19 | UI pages for options | 28 |
| 20 | Commits in last 60 days that ship PROPOSED→OPEN | **0** (all infrastructure / read-only / schema) |

---

## Findings by section

### 1. Options lifecycle state

| state | count | last event |
|---|---|---|
| PROPOSED | 1 | 2026-05-06 01:36 UTC |
| OPEN | 0 | never |
| CLOSED | 0 | never |
| EXPIRED | 0 | never |
| ASSIGNED | 0 | never |

Lifecycle event audit trail is **empty**. Zero transitions ever logged.

The 1 PROPOSED trade:
- Trade ID: 2
- Underlying: AMZN
- Strategy: BULL_CALL_SPREAD (275C buy / 290C sell, qty 1 each)
- Expiry: 2026-06-18 (33 DTE, not expired)
- max_loss: $610, max_profit: $890
- entry_mid populated for both legs ($11.375 / $5.40), exit_mid NULL
- created_at: 2026-05-06 01:36 UTC
- opened_at: 2026-05-04 21:00 UTC — **2 days BEFORE creation** (temporal inconsistency confirming operator-seeded origin, not a real fill)

### 2. Shadow → candidate → proposal waterfall (30 days)

```
Chain snapshots         6,561  (single batch 2026-05-13 17:47 UTC)
        ↓
Shadow decisions ever   7,505  (5/3: 10; 5/13: 7,495; nothing else)
        ↓ would_trade
Would-trade approvals      25  (5/3: 5; 5/13: 25; including overlap)
        ↓
Strategy candidates        67  (single day 5/14)
        ↓
Outcomes computed          45  (ALL labeled `data_blocked`)
        ↓
Proposals (PROPOSED)        1  (5/6, AMZN — predates ALL the above!)
        ↓
Filled (OPEN)               0
```

Pipeline is **discontinuous, not real-time**. The 1 PROPOSED trade actually predates the shadow + candidate generation by a week — confirming it is operator-seeded test data, not the output of the normal pipeline.

Rejection histogram from the 5/13 shadow run (7,470 rejections):

| reason | count | % |
|---|---|---|
| `blocked:open_interest` | 2,482 | 33.2% |
| `blocked:top_n_capped` | 1,805 | 24.2% |
| `blocked:spread` | 1,519 | 20.3% |
| `blocked:dte` | 1,505 | 20.1% |
| `blocked:greeks` | 161 | 2.2% |
| `blocked:risk` | 3 | 0.04% |

24.2% being `top_n_capped` is notable — genuinely-qualified contracts thrown away due to the per-underlying top-5 cap. Already flagged in stock OVA. Not urgent here (lifecycle isn't running anyway), but worth raising in eventual unlock plan.

### 3. Gate stack inventory

Three terminal kill-switch flags, each defaults False:

| flag | file:line | behavior when False |
|---|---|---|
| `OPTIONS_ENABLED` | `config/__init__.py:216` | Multiple early-return paths: routes_readonly:120-125, paper/engine:120-122 (REJECT_KILL_SWITCH), paper/eval_runner:123-125 (raises EvalRunnerSafetyError), worker/options_chain_snapshot:41-44 (silent skip), worker/options_shadow_eval:199-203 (silent skip) |
| `OPTIONS_SHADOW_EVAL_ENABLED` | `config/__init__.py:387` | shadow_eval job runs dry-mode (no persistence) |
| `OPTIONS_CANARY_ENABLED` | `config/__init__.py:419` | canary_promotion job + lifecycle_check job return `{"skipped": True}` |

Shadow eval thresholds (used when flag is on):

| param | default | file |
|---|---|---|
| `OPTIONS_SHADOW_MIN_OPEN_INTEREST` | 500 | config:388 |
| `OPTIONS_SHADOW_MAX_SPREAD` | $0.10 | config:389 |
| `OPTIONS_SHADOW_MIN_BID` | $0.01 | config:390 |
| `OPTIONS_SHADOW_MIN_DTE` | 7 | config:391 |
| `OPTIONS_SHADOW_MAX_DTE` | 45 | config:392 |
| `OPTIONS_SHADOW_TOP_N` | 5 | config:393 |

Canary configuration (loaded but never consumed, because the canary jobs are stubs):

| param | default |
|---|---|
| `OPTIONS_CANARY_UNIVERSE` | `"SPY"` |
| `OPTIONS_CANARY_STRATEGY` | `"BULL_CALL_SPREAD"` |
| `OPTIONS_CANARY_MAX_OPEN` | 1 |
| `OPTIONS_CANARY_MAX_CAPITAL_USD` | $500 |
| `OPTIONS_CANARY_MIN_DTE` | 21 |
| `OPTIONS_CANARY_MAX_DTE` | 45 |

### 4. Stale proposal investigation (Trade ID 2, AMZN, 2026-05-06)

| fact | value |
|---|---|
| Created | 2026-05-06 01:36:48 UTC |
| Marked opened_at | 2026-05-04 21:00:00 UTC (impossible — 2 days before creation) |
| Lifecycle events | **0** |
| AMZN chain ingests after 5/6 | **0** (AMZN never even in the options universe) |
| Expiry | 2026-06-18 (not yet expired) |
| Linked candidate ID | none — candidates started 5/14, trade was created 5/6 |
| Linked outcome | none |
| Origin | operator-seeded artifact (no automated path could create it) |

**The stale proposal is not waiting on anything. It was never going to advance.** There is no scheduled job that would call `transition_to_fill()` on it. The trade exists as a snapshot of an operator's experiment.

### 5. Options chain freshness

All 6,561 chain rows are from a **single timestamp**: `2026-05-13 17:47:27 UTC`. That's 70+ hours ago at audit time (now ~2026-05-16 14:00 UTC).

The `options_chain_snapshot` job has fired successfully 3 times in 30 days (last fire `2026-05-16 01:30:19`, duration 74.8s). **It returns success but writes no rows** because OPTIONS_ENABLED=False causes silent skip at line 41-44.

The shadow_eval job fired 7 times successfully (last fire `2026-05-16 01:45:55`, duration 0.825s). Also silent-skipping.

Feature freshness is somewhat misleading: `options_feature_daily` has rows dated `2026-05-16` for 5 underlyings (SPY/QQQ/IWM/GLD/TLT). The features compute job seems to write something despite OPTIONS_ENABLED=False. **AMZN is not in the universe and has no features**, which is consistent with the 5/13 chain ingest only covering 5 underlyings.

### 6. Options fill semantics

`apps/api/src/options/paper/fills.py:73-101` defines a conservative fill model:

```
side BUY  → fill_price = mid + slippage_per_contract
side SELL → fill_price = mid − slippage_per_contract
slippage = min(half_bid_ask_spread, DEFAULT_SLIPPAGE_CAP_DOLLARS=$0.05)
```

**Crucially: no `find_next_open` equivalent. No same-bar guard. No `fill_ts > submitted_at` predicate.**

The options fill model uses the *latest available quote* unconditionally. There is no temporal deadlock equivalent to the stock fix — because there is no execution path at all. If/when the canary promotion is shipped, fills would land against the latest chain snapshot, not a future bar.

This is a different temporal model from stocks (which use EOD bars at midnight UTC). Options operate on multi-snapshots-per-day chain ingests. The fill design is correct for the chain model — but only relevant once the calling path exists.

### 7. Options exit / management lifecycle

Comprehensively **unimplemented**.

| exit mechanism | code status | scheduled? |
|---|---|---|
| TP target | undefined constant; commented in lifecycle_check.py | no |
| SL target | undefined constant; commented | no |
| Max hold (DTE cutoff) | undefined constant; commented | no |
| Expiry handling | state-machine transition defined; **no caller** | no |
| Assignment precedence | state-machine enforces "if ITM short at expiry, must call assigned()"; **no caller** | no |
| Roll logic | does not exist | no |
| MTM updates | state-machine event type defined; **no caller** | no |

The `options_lifecycle_check` job body literally returns:

```python
return {"skipped": True, "reason": "phase1b_not_shipped"}
```

### 8. Telemetry truth (table consistency)

| concern | finding |
|---|---|
| Are tables consistent? | Yes, internally. Schema migrations 069+ landed correctly. |
| Is data current? | No. Chain stale 70h, last shadow run 5/13, last candidate emission 5/14, no proposal since 5/6, lifecycle events table empty. |
| Are job_run statuses honest? | **No.** All 5 jobs report status=success daily despite doing nothing (silent skip). Same wrapper-RC issue as stocks but applied to 5 jobs. |
| Are dashboards using truthful data? | UI is fully read-only and consumes whatever the API returns. API does return shadow/candidate data faithfully. So dashboards show *what exists* — which is stale telemetry, not lifecycle reality. |

The most material telemetry lie is **job_run status='success'** on 5 jobs that do zero substantive work. Operators reading job logs see "everything is green" while the system is dormant.

### 9. Verdict (blunt)

The closest single-letter match is **D — blocked by execution gates**.

But the precise reality is layered:

```
Layer 1 (flag): OPTIONS_ENABLED=false
  ↓ silent skip
  Chain ingest does NOTHING
  Shadow eval does NOTHING

Layer 2 (flag): OPTIONS_CANARY_ENABLED=false
  ↓ silent skip with reason="canary_disabled"
  canary_promotion does NOTHING
  lifecycle_check does NOTHING

Layer 3 (CODE): even if Layer 1+2 flags flip True
  ↓ Phase 1A is an explicit STUB returning "phase1a_not_shipped"
  ↓ Phase 1B is an explicit STUB returning "phase1b_not_shipped"
  PROPOSED still cannot become OPEN
  OPEN (if it existed) still has no exit logic

Layer 4 (DATA): chain ingest has been silently skipping for 3+ days
  ↓ even with full code AND flags, the engine has no fresh data to work with
```

**Three independent walls block lifecycle execution.** Flipping flags alone unlocks zero. Phase 1A + 1B + fresh chain data are all prerequisites.

This is the OPPOSITE of the stock-OVA situation (where the engine was almost working but for a temporal mismatch). Options is honestly incomplete by design.

### 10. Recommendations — ordered fix sequence

**Sequenced safety gates. Each must complete before the next.**

#### Phase 1: TRUTHFUL OBSERVABILITY (no behavior change)

**R1.** Patch all 5 options job wrappers to honestly distinguish "skipped due to flag" vs "succeeded with work" in `job_run.status` (or in metadata). Mirror the stock R1 wrapper-RC fix — but for honesty, not execution. **Possible approach**: store the return-dict's `"skipped"` field in `job_run.metadata` so dashboards can filter `WHERE NOT (metadata->>'skipped' = 'true')` to find runs that actually did work.

**R2.** Surface flag state on a dashboard somewhere. The single read-only line on `/options/ops` should make it impossible to mistake "scheduled-job-success" for "system-doing-work."

**R3.** Empty-state hardening: when `OPTIONS_CANARY_ENABLED=false` AND no PROPOSED exists past 24 hours, the UI should display *"Options paper-trading is in pre-canary observation phase. No execution path is active."* — not a vague "no opportunities today."

#### Phase 2: VALIDATE WHAT EXISTS

**R4.** Confirm whether the chain ingest worked correctly on 5/13 was *driven by a flag flip* or *by manual operator invocation*. Read `provider_raw_archive` or git history of `.env` to confirm. If a flag flip: document the procedure. If manual: document that path too.

**R5.** Re-run chain ingest once manually (operator-controlled, ad-hoc, NOT enabling the global flag) to confirm the adapter still works. Verify: 5 underlyings, 6,000+ contracts, no integration errors.

**R6.** Re-run shadow eval once manually after R5. Confirm the 9-filter pipeline produces sane rejection-reason distribution. Compare against the 5/13 distribution.

**R7.** Re-run strategy candidate generator once manually. Confirm composite scoring still emits candidates from would_trade observations.

**This phase produces zero PROPOSED trades. Zero positions. Zero fills. Pure validation that the data side is alive.**

#### Phase 3: DELETE THE STALE PROPOSAL

**R8.** Trade ID 2 (the 2026-05-06 AMZN PROPOSED) should be **manually closed/deleted as an operator-seeded artifact**, not left in the table. Use a `transition_to_close()` with reason="operator_manual_cleanup" OR mark with a flag. The exact mechanism depends on whether we want to retain the audit footprint.

This produces the first row in `options_trade_lifecycle_event`. Validates the state-machine actually writes when called.

#### Phase 4: PHASE 1A + 1B IMPLEMENTATION (real lifecycle work)

The audit cannot recommend specifics here — this is a build, not a fix. But the **prerequisites** for that build are:

- Specification of exact TP/SL/MaxHold/DTE constants for options (currently undocumented anywhere)
- Specification of the PROPOSED → OPEN trigger (scheduled scan? operator action? per-snapshot tick?)
- Decision on whether canary's `MAX_OPEN=1` is too restrictive for validation (likely yes — single slot means single-tick validation)
- Decision on whether `top_n_capped` should remain at 5 (24.2% of rejections; very restrictive)

**None of these decisions should be made until R1-R8 land.**

#### What MUST stay disabled

- `OPTIONS_ENABLED=False` until Phase 1A + 1B both ship AND pass test coverage
- `OPTIONS_CANARY_ENABLED=False` until canary portfolio is explicitly re-activated by operator decision
- Options write paths in UI: **never** — UI is locked read-only by test enforcement; do not relax

#### What is OUT of scope until later

- Threshold tuning (top_n, OI floor, DTE window) — irrelevant until lifecycle works
- Canary scope expansion (universe, strategies) — irrelevant until single-tier canary works
- Live execution — non-existent, far out of scope

#### Should options remain UI-only until lifecycle proof?

**Yes.** The UI is the only currently-trustworthy options surface. It shows shadow telemetry + research read-outs + educational content. None of it pretends execution exists. **The current state is honest** — the issue is the *gap between what the UI shows and what the user might infer*.

A single banner line on `/options/overview` clarifying "execution lifecycle is in pre-canary build state — what you see below is research, not paper trading" would close the perception gap.

---

## Anomalies catalogued

| # | anomaly | severity |
|---|---|---|
| OOVA-1 | All 5 options jobs report `job_run.status=success` while silent-skipping | **high** (telemetry dishonesty across 5 jobs) |
| OOVA-2 | Trade ID 2 has `opened_at` 2 days BEFORE `created_at` — operator-seeded with bogus timestamps | **medium** (data integrity) |
| OOVA-3 | Chain ingest single snapshot from 5/13, 70+ hours stale | **medium** (data freshness; not regression — design state) |
| OOVA-4 | `options_strategy_outcome` 45 rows all `data_blocked` — no resolution path implemented | **medium** (outcome computation incomplete) |
| OOVA-5 | Canary portfolio created 2026-05-14 with `active=false`; notes reference Phase 1B as unlock condition | **low** (honest by design) |
| OOVA-6 | UI never breaks the "no execution path active" reality to the user | **low/medium** (perception gap) |
| OOVA-7 | `top_n_capped` accounts for 24.2% of options rejections — high vocabulary inflation in the gate stack | **low** (cosmetic until lifecycle is live) |

OOVA-1 is the most consequential operational issue (and parallels the stock-side wrapper bug that was just fixed). The other six are honest-by-design states until Phase 1A/1B ships.

---

## What this audit does NOT cover

- Phase 1A / 1B implementation specs (out of audit scope; that's a build, not a forensic)
- Live execution (does not exist)
- Real-money pathway (does not exist)
- Specific threshold-tuning recommendations (premature)
- Whether the options engine *should* exist at all (philosophical, not forensic)

---

## Standing locks (unchanged)

- No options enablement
- No canary expansion
- No threshold changes
- No UI changes
- No Phase 1A / 1B implementation in this audit
- Phase K creative-direction work still paused
- Current J-rev1 frontend state held

---

## Source agents

This report consolidates findings from two forensic agents run on 2026-05-16:

- **Code side**: every flag check site, gate inventory file:line, scheduled job classification, exit-lifecycle absence
- **Data side**: per-table row counts, lifecycle state, waterfall over 30 days, chain freshness, stale-proposal deep dive, telemetry consistency

Full agent outputs preserved in conversation history.
