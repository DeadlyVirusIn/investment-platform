# Canary-1 — Gate 5 Blast Radius Memo

**Date**: 2026-05-19
**Status**: PRE-EXECUTION MEMO — no work performed yet
**Scope under review**: Apply migration 090 → resolve cron drift → implement
real preflight bodies → add scheduler rows → run proposal-only dry run →
verify telemetry. NOTHING else.

This memo enumerates exactly what Gate 5 touches and what it leaves alone.
Approve the memo before any of Gate 5's operational steps run.

---

## 1. Flags involved at Gate 5

| Flag | Pre-Gate-5 | During Gate 5 | Post-Gate-5 |
|---|---|---|---|
| `OPTIONS_ENABLED`         | `false` | `false` | `false` |
| `OPTIONS_CANARY_ENABLED`  | `false` | **`true`** during dry run window | reverts to `false` after dry run |
| `OPTIONS_SHADOW_EVAL_ENABLED` | `true`  | `true`  | `true`  |
| `OPTIONS_DATA_PROVIDER`   | `tradier` | `tradier` | `tradier` |

**Important asymmetry**: `OPTIONS_ENABLED` stays `false` throughout Gate 5.
Only `OPTIONS_CANARY_ENABLED` flips. This is the master flag for proposal-
only behavior. `OPTIONS_ENABLED` remains the master gate that authorizes
**fill / open / close** — none of which are implemented yet.

Lifecycle job (`run_options_canary_lifecycle_job`) gates on `OR` of both
flags, so it WILL un-skip during the dry-run window. Its engine cycle
is still a stub returning `gate_4_stub` — so the only observable effect
of the lifecycle job during Gate 5 is one telemetry row per scheduled
invocation, classification=`paused`, error_summary=`{"stub":"gate_4_stub"}`.
That is acceptable noise; the lifecycle job is verifying its scheduler
wiring only.

If a tighter posture is wanted: gate the lifecycle job on `OPTIONS_ENABLED`
only (not `OPTIONS_CANARY_ENABLED`). That would keep it dormant through
Gate 5. **Decision required — see §8.**

---

## 2. Schedules involved at Gate 5

| Schedule name | Cron expression (UTC) | Job | Inserted at Gate 5? |
|---|---|---|---|
| `options_canary_proposal`  | `0 14 * * 1-5` (≈ 1 hour after US market open) | `run_options_canary_proposal_job`  | **YES** |
| `options_canary_lifecycle` | `*/15 14-21 * * 1-5` (every 15 min during market) | `run_options_canary_lifecycle_job` | **YES (see §1 decision)** |

Both schedule rows are NEW. Both go into `job_schedule`. Neither exists
today. Removing the rows is a single `DELETE FROM job_schedule WHERE
name IN (...)` — clean rollback (§7).

Schedule timing rationale:
- Proposal at T+60min into the regular session: SPY chain has settled
  out of opening volatility; mid quotes are tight; 1 candidate per day.
- Lifecycle every 15min during regular session: dense enough to observe
  intra-day price evolution; sparse enough to keep telemetry sane
  (~28 invocations per session = 28 rows/day in `options_canary_lifecycle_run`).

---

## 3. Tables touched at Gate 5

### 3a. INSERT-only (audit / telemetry)

| Table | Why it's written | Bounded by |
|---|---|---|
| `options_canary_lifecycle_run`           | telemetry — one row per invocation | proposal=1/day + lifecycle=28/day = **≤ 29 rows/day** |
| `options_trade_lifecycle_event`          | one `PROPOSED` event per successful proposal day | **≤ 1 row/day** |
| `options_paper_trade`                    | one PROPOSED row per successful proposal day | **≤ 1 row/day** |

Bounded by the canary one-shot guard: `max_total_canary_trades = 1`
(Gate 3 §5.2 — enforced in `_select_candidate_contract` at Gate 5
when its body is filled). On the first successful proposal, all
subsequent proposal-job invocations return `canary_complete` and write
no further `options_paper_trade` / `options_trade_lifecycle_event`
rows.

### 3b. NEW SCHEMA (migration 090 only)

`options_canary_lifecycle_run` (table + 4 indexes + 6 CHECK constraints).
Already authored and reviewed at Gate 2; this is the apply step.

### 3c. UPDATE (state machine)

| Table | What changes | Guard |
|---|---|---|
| `options_paper_trade.status`    | `PROPOSED` (NEW row) — never transitions during Gate 5 | no fill logic exists |
| `options_paper_portfolio.active` | flipped `true` for dry run, reverted `false` after | manual operator action only |

NB: `options_paper_trade.status` is INSERTed once at PROPOSED and never
UPDATEd during Gate 5 because no fill code path exists. Lifecycle job
discovers PROPOSED state and reports `no_fill_yet` (a stub no-op until
Gate 6+).

### 3d. job_schedule

INSERT two rows: `options_canary_proposal` + `options_canary_lifecycle`.
No UPDATE / no DELETE during normal Gate 5 operation. Cleanup at Gate 5
exit is an explicit DELETE.

---

## 4. Tables GUARANTEED untouched at Gate 5

These tables remain bit-identical (modulo unrelated stocks-side activity)
throughout Gate 5. Any change here is a violation.

| Table | Guarantee |
|---|---|
| `options_paper_position`                | **0 rows** for canary portfolio throughout |
| `options_chain_snapshot`                | unchanged by canary code; chain ingest job continues independently |
| `options_chain_ingest_run`              | unchanged by canary code; chain ingest job continues independently |
| `options_paper_portfolio` (except `active` flag) | name, cash, universe, strategy_family unchanged |
| `account` / `lot` / `transaction`       | stocks-side; untouched |
| `paper_trade` / `paper_equity_snapshot` | stocks-side; untouched |
| `reasoning_audit` / `envelope_generation_run` | Phase L; untouched |
| `signal_v1` / `forbidden_phrases_*`     | constitutional; untouched |
| Any table outside the explicit §3 list  | untouched |

Verification at end of dry run: snapshot row counts before + after, diff
must equal §3a expected counts exactly.

---

## 5. Cron container drift — resolution plan

**Discovered at Gate 4**: `compose-worker-cron-1` has no
`/app/apps/api/src/options/canary/` directory. Image predates the canary
folder creation (2026-05-14). `compose-worker-tickloop-1` has it.

**Resolution sequence** (must complete BEFORE step 6 schedule insertion):

1. **Hot-patch cron container** via `docker cp` for the 4 new files +
   modified registry.py:
   ```
   apps/api/src/options/canary/__init__.py
   apps/api/src/options/canary/engine.py
   apps/worker/src/jobs/options_canary_proposal.py
   apps/worker/src/jobs/options_canary_lifecycle.py
   apps/worker/src/jobs/registry.py
   ```
2. **Restart cron container** so the in-memory Python module cache is
   refreshed.
3. **Verify md5 parity** across all critical files × cron + tickloop +
   host via the (now-real) preflight md5 check.
4. **Schedule cron-image rebuild as a durable follow-up** — outside Gate
   5 critical path, but documented as a hardening item so the next image
   pull does not regress.

If hot-patch fails or md5 parity does not pass: STOP. Do not insert
schedule rows. Do not flip flag.

---

## 6. Real preflight implementations to author

Each of the four `engine.preflight()` stubs becomes real at Gate 5.
Concrete shape:

| Check | Implementation | Failure → PreflightResult |
|---|---|---|
| `_check_md5_parity()`        | For each of 8 files × 2 containers: `docker exec <c> md5sum /app/<file>` via `subprocess.run`; compare against host hash. Container access via container name from env. | `kind="drift"`, `failed_check="md5:<file>:<container>"` |
| `_check_alembic_head()`      | `docker exec <c> alembic current` head extracted via regex; compare to `alembic heads` on host filesystem (read from `infra/alembic/versions/`). | `kind="schema_drift"`, `failed_check="alembic:<container>"` |
| `_check_canary_portfolio_active()` | `SELECT active FROM options_paper_portfolio WHERE name = 'canary-spy-v1'`. Fail if no row or `active = false`. | `kind="portfolio_paused"`, `failed_check="portfolio:active=false"` |
| `_check_chain_freshness()`   | `SELECT classification, started_at FROM options_canary_lifecycle_run … ORDER BY started_at DESC LIMIT 1` — wait, **read from `options_chain_ingest_run`** (telemetry from M089). Latest row must have `classification='success'` AND `started_at > now() - 90min`. | `kind="chain_stale"`, `failed_check="chain_age:<min>min"` |

Notes:
- md5 + alembic checks require host-environment context. The preflight
  function will read container names from `settings.WORKER_CONTAINERS`
  (new setting, default `["compose-worker-cron-1","compose-worker-tickloop-1"]`).
- Both checks are TOLERANT of subprocess failure: if `docker exec` itself
  errors (Docker daemon issue), return `kind="exception"` rather than
  `kind="drift"` so we distinguish "deployment broken" from "Docker is
  down".

---

## 6a. Gate 5 freshness exception (post-memo addendum, 2026-05-19)

Discovered during step 6 execution: the originally specified
`chain_freshness` check (latest `options_chain_ingest_run.classification
= 'success'` AND `started_at > now − 90min`) fails after US market close
because the Tradier sandbox returns stale-marked quotes; the liquidity
filter rejects 100% of them; ingest_run classifies as `no_new_data`;
preflight refuses to run even though usable SPY chain rows from earlier
in the session (e.g. 18:38 UTC, ~2,400 rows) remain in
`options_chain_snapshot` and are exactly what the proposal selector
acts on.

**Gate 5-only exception** (applied to both `engine.preflight` and
`scripts/canary_preflight.py`):

| Aspect | Memo §6 (original) | Gate 5 exception |
|---|---|---|
| Anchor | `options_chain_ingest_run.started_at` | `MAX(snapshot_at_utc) FROM options_chain_snapshot WHERE underlying='SPY'` |
| Threshold | 90 minutes | 240 minutes |
| Classification check | requires `'success'` | not checked (anchor is data, not telemetry) |

**Rationale**: the proposal selector queries `options_chain_snapshot`
directly. Anchoring freshness on the data we would actually act on is
more truthful than anchoring on telemetry that may classify a successful
provider call as `no_new_data` due to liquidity filtering.

**MUST tighten at Gate 6+** (when fill/lifecycle ships):

- Revert threshold to 90 minutes OR adopt market-session-aware bound
  (e.g. relax to 240 min only when `EXTRACT(DOW FROM NOW())` is a
  weekend or `EXTRACT(HOUR FROM NOW() AT TIME ZONE 'America/New_York')`
  is outside 09:30–16:00)
- Add additional guard: reject quotes whose individual `quote_age_seconds`
  exceeds a per-quote freshness limit (chain-level freshness is necessary
  but not sufficient for fill decisions)
- Do NOT relax quote-validity gates at Gate 6+ — those remain strict
  (bid>0, ask>0, spread ≤5%, OI≥100, vol≥10)

This addendum is the only deviation from the memo. All other §1–§11
specifications hold.

---

## 7. Rollback posture

Gate 5 is fully reversible. Three rollback layers:

### 7a. Soft rollback (revert flag, leave artifacts)

```
UPDATE options_paper_portfolio SET active = false WHERE name = 'canary-spy-v1';
-- set OPTIONS_CANARY_ENABLED=false in .env, restart worker containers
```

Effect: proposal and lifecycle jobs immediately resume `master_flags_off`
behavior. Schedules continue firing but every invocation writes
`classification='paused'` telemetry and returns wrapper-RC skip. No new
PROPOSED rows.

Preserved: any PROPOSED row + lifecycle event from the dry run remain
in place as evidence.

### 7b. Schedule rollback (remove cron rows)

```
DELETE FROM job_schedule
WHERE name IN ('options_canary_proposal','options_canary_lifecycle');
```

Effect: tick_loop stops invoking the jobs entirely. No more telemetry
rows written.

### 7c. Migration rollback (drop telemetry table)

```
alembic downgrade -1   -- 090 → 089
```

Effect: `options_canary_lifecycle_run` table removed. Any rows recorded
during the dry run are destroyed. Telemetry from Gate 5 is lost; the
PROPOSED row in `options_paper_trade` + the lifecycle event in
`options_trade_lifecycle_event` survive (those are not in 090).

**Recommended rollback order**: 7a → 7b. Only 7c if migration itself
is broken; otherwise leave the telemetry rows as evidence.

---

## 8. Decisions required before Gate 5 starts

| # | Decision | Default if not specified |
|---|---|---|
| D1 | Should `run_options_canary_lifecycle_job` un-skip during the dry-run window (current gate: `OPTIONS_ENABLED or OPTIONS_CANARY_ENABLED`), or stay dormant by gating ONLY on `OPTIONS_ENABLED`? | **Recommend: stay dormant.** Change wrapper to gate on `OPTIONS_ENABLED` only. Justification: Gate 5 is proposal-path only; lifecycle scheduler wiring can be verified at Gate 6+ when fill logic lands. Reduces telemetry noise (~28 rows/day reduced to 0). |
| D2 | Cron-container hot-patch: docker cp + restart, OR full image rebuild? | **Recommend: docker cp + restart** for speed; schedule durable rebuild as follow-up. md5 parity check at preflight will catch regression on next image pull. |
| D3 | Dry-run duration: one cron firing only, or one full trading day? | **Recommend: one cron firing only.** Insert schedule row, manually trigger via `python -c` once, verify telemetry, then either (a) leave schedule active for natural fire next session, or (b) delete schedule row. Gate 5 success criterion = one clean PROPOSED row + correct telemetry, not a multi-day soak. |
| D4 | Canary portfolio initial cash? (sets the dollar size of the eventual one trade) | **Recommend: $10,000.** Enough to express SPY ATM call premium (~$300–800 per contract) with comfortable cash buffer; small enough that no realistic outcome materially affects anything. Need to be set BEFORE Gate 5 by `UPDATE options_paper_portfolio SET cash_initial=10000, cash_current=10000 WHERE name='canary-spy-v1'`. Currently NULL/0 (need to verify). |

---

## 9. Order of operations (proposed)

Each step has a stop condition. If any step fails its check, halt and
report — do not proceed to the next.

1. **Memo approval** (this document)
2. **Decision answers** (D1–D4 above)
3. **Cron-container hot-patch + restart** → verify `docker exec compose-worker-cron-1 python -c "from apps.api.src.options.canary import engine"` succeeds
4. **Apply migration 090** → verify `options_canary_lifecycle_run` table exists with 6 CHECKs + 4 indexes
5. **Set canary portfolio cash** (per D4)
6. **Implement real preflight bodies** → `python scripts/canary_preflight.py --strict` returns exit 0
7. **Optional**: tighten lifecycle wrapper gate per D1
8. **Insert job_schedule row** for `options_canary_proposal` (and `options_canary_lifecycle` if D1 keeps both active)
9. **Flip** `OPTIONS_CANARY_ENABLED=true`, restart workers
10. **Flip** `options_paper_portfolio.active=true` for `canary-spy-v1`
11. **Single triggered dry run** of proposal job (manual invocation, not waiting for cron)
12. **Verify** §3a row counts match expected; §4 tables untouched
13. **Revert flag** (`active=false`, `OPTIONS_CANARY_ENABLED=false`)
14. **Write Gate 5 completion report**

---

## 10. What Gate 5 explicitly does NOT do

- No fill logic. `_execute_fill()` remains a stub returning `None`.
- No exit logic. `_evaluate_exit_triggers()` / `_reconcile_close_accounting()`
  remain stubs.
- No OPENED / MONITORED / CLOSED lifecycle events written. Only PROPOSED.
- No `options_paper_position` row created. Zero positions throughout.
- No portfolio cash debit (no fill = no debit).
- No flag flip on `OPTIONS_ENABLED`.
- No production data widening: canary portfolio remains capped at
  `max_open_trades = 1` and `max_total_canary_trades = 1`.
- No web-UI changes. HONEST-BANNER copy, OptionsCanaryStatus widget,
  forbidden-phrase lint all stay intact.
- No operator-event implementation (deferred).
- No Phase 1A / 1B work.

---

## 11. Success criteria for Gate 5

Gate 5 declared COMPLETE when ALL of the following hold simultaneously:

| # | Criterion |
|---|---|
| S1 | Migration 090 applied; `\d options_canary_lifecycle_run` shows 6 CHECKs + 4 indexes |
| S2 | Cron container md5-parity with tickloop + host on all 8 critical files |
| S3 | `python scripts/canary_preflight.py --strict` exits 0 |
| S4 | One PROPOSED row in `options_paper_trade` for canary portfolio, with target SPY ATM call ~30 DTE selected deterministically |
| S5 | One PROPOSED event in `options_trade_lifecycle_event` matching that trade |
| S6 | One row in `options_canary_lifecycle_run`, classification='success', n_proposals_generated=1 |
| S7 | Zero rows in `options_paper_position` |
| S8 | Zero CLOSED / OPENED / MONITORED events |
| S9 | All §4 GUARANTEED-untouched tables unchanged (row-count diff = 0) |
| S10 | Constitutional locks remain green (forbidden_phrases + resolver_anchor + canary_gateway lints) |

---

## 12. Approval requested

Approve the memo (with or without redlines on D1–D4) before any of the
Gate 5 operational steps begin. Do not start at step 3 of §9 until the
memo is signed off.

Recommended decisions repeated for fast read:

- **D1**: lifecycle job stays dormant (gate on `OPTIONS_ENABLED` only)
- **D2**: docker cp + restart cron container
- **D3**: one manual triggered dry run
- **D4**: canary portfolio cash $10,000
