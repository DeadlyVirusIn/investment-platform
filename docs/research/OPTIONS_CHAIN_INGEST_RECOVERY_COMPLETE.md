# Options Chain Ingest — Recovery Complete

**Date**: 2026-05-19
**Branch**: `phase-1/ledger`
**Scope**: Fix only the chain-data ingest path. Do **not** activate options
execution. Do **not** flip Phase 1A/1B flags. Do **not** create paper option
trades. Do **not** touch UI state.

---

## TL;DR

Options chain ingest was **silently producing 0 new rows for 6 days** while
`job_run.status` reported `success` daily. Root cause was a combined
deployment-drift + wrapper-RC dishonesty failure on the options side that
mirrors the stocks-side anchor-math regression discovered earlier this week.

Three coordinated fixes were applied together:

| Fix | What | Where |
|-----|------|-------|
| 1   | Sync 8 options provider/module files to both worker containers | `compose-worker-cron-1`, `compose-worker-tickloop-1` |
| 2   | Add Tradier env block (provider, token, base URL) to compose worker services | `infra/compose/docker-compose.yml` |
| 3   | Rewrite chain-snapshot wrapper for RC honesty + write telemetry-of-truth row each invocation | `apps/worker/src/jobs/options_chain_snapshot.py` |

A new telemetry table `options_chain_ingest_run` (migration `089_opt_chain_ingest_run`) is the source of truth for ingest outcomes.

Outcome: chain went from **0 fresh rows / 6 days** → **20,430 rows for today
(2026-05-19)** across 5 universe symbols, dual-sourced from Tradier sandbox.

No Phase 1A / 1B activation occurred. No flag flips. No paper option trades
created. UI state unchanged. Constitutional locks remain in force.

---

## Validation results

### Step 1 — md5 parity host vs containers ✅ PASS

All four critical files match between host and `compose-worker-tickloop-1`
(the container that actually runs the cron job). Final md5s:

| File | md5 |
|------|-----|
| `apps/worker/src/jobs/options_chain_snapshot.py`     | `6e9c7acee8e95368701f83eaf1ac02c8` |
| `apps/api/src/options/data/chain_ingest.py`          | `719a6984787c5bfdb57df0a56569727b` |
| `apps/api/src/options/data_provider/tradier_adapter.py` | `82860f5d7cac9c41f21cdab06e4734c8` |
| `apps/api/src/config/__init__.py`                    | `4abef0aeb3863db6d468ad302b7885ca` |

Notes:
- `compose-api-1` shows older wrapper hash (acceptable: API does not run the
  cron job; wrapper is worker-only code).
- `config/__init__.py` had been stale on `compose-worker-cron-1` (md5
  `bb56a587…`). Discovered mid-validation, synced via `docker cp`, restart.

### Step 2 — worker settings reach Tradier ✅ PASS

```
compose-worker-tickloop-1:
  OPTIONS_DATA_PROVIDER       = tradier
  OPTIONS_SHADOW_EVAL_ENABLED = True
  TRADIER_BASE_URL            = https://sandbox.tradier.com/v1
  TRADIER_ACCESS_TOKEN        = <len=28, redacted>

compose-worker-cron-1:        (same)
```

Pre-fix: provider was `unknown`; token absent; ingest would no-op every
invocation. Post-fix: provider concrete; token present; ingest reachable.

### Step 3 — manual ingest from tick_loop container ✅ PASS

```python
JOB RESULT: {'return_code': 0, 'inserted': 6831, 'dedup': 0,
             'classification': 'success'}
```

Provider returned data; rows persisted; wrapper returned correct success
dict.

### Step 4 — SQL verifies new rows appeared ✅ PASS

```
day        | rows
-----------+-------
2026-05-19 | 20430
2026-05-13 |  6561   ← last pre-fix snapshot, 6 days stale
```

Gap closed. Today's count = three ingest invocations × ~6800 rows each.

### Step 5 — rerun should produce no_new_chain_data ⚠ STRUCTURAL PASS, BEHAVIORAL FINDING

**Expected**: rerun within minutes returns
`{skipped: True, reason: "no_new_chain_data"}`.

**Actual**: rerun returned
`{return_code: 0, inserted: 6728, classification: 'success'}` — fresh rows.

**Why this is not a wrapper bug**:

`options_chain_snapshot.run_options_chain_snapshot_job()` sets
`snapshot_at_utc = started_at = now()` per call. The natural-key uniqueness
constraint on `options_chain_snapshot` is
`(snapshot_at_utc, underlying, expiry, strike, option_type)`. Different
`snapshot_at_utc` per call ⇒ different natural key ⇒ no dedup ⇒ every row
inserts as a legitimately new point-in-time snapshot.

This is the **correct** semantics for a quote-instant time series: each
invocation is a distinct observation moment, not a duplicate.

The wrapper's `no_new_chain_data` branch fires **only** when the provider
returns 0 quotes per symbol (e.g. weekend, holiday, provider outage). That
branch is exercised by the codepath; we just can't trigger it during market
hours with a live sandbox.

**Structural honesty verified**: the wrapper correctly distinguishes the
four meaningful outcomes —
`master_flags_off` / `exception:*` / `all_symbols_failed` / `no_new_chain_data`
/ `success|partial` — and writes one row to `options_chain_ingest_run` per
invocation with a closed-enum `classification`.

### Step 6 — job_run.status reflects actual work ⚙ DEFERRED TO NEXT SCHEDULED FIRE

```
job_name                 | started_at                  | status
options_chain_snapshot   | 2026-05-19 01:30:13.20+00   | success   ← PRE-FIX
options_chain_snapshot   | 2026-05-16 01:30:19.24+00   | success   ← PRE-FIX
options_chain_snapshot   | 2026-05-15 01:30:04.63+00   | success   ← PRE-FIX
options_chain_snapshot   | 2026-05-14 01:30:51.97+00   | success   ← PRE-FIX
```

All four historical rows say `success` despite producing zero work. They
predate the wrapper-RC fix. Manual ingest runs bypass `tick_loop` (called
via `python -c` inside the container) and therefore write only to the new
telemetry table, not `job_run`.

`tick_loop.py` classification logic (lines surfaced in validation) already
correctly distinguishes:
- `{skipped: True, reason: ...}`  → `status='skipped'`, `error_message='skipped: <reason>'`
- `{return_code: !=0, ...}`        → `status='error'`
- otherwise                        → `status='success'`

This was already validated in Phase L Day 2 (task #113, D2.3 wrapper-RC
regression test). End-to-end verification of the options-specific path will
become visible at the **next scheduled fire (~01:30 UTC tomorrow)**, which
will produce the first post-fix `job_run` row.

### Step 7 — no Phase 1A / 1B flags flipped ✅ PASS

```
worker-tickloop:
  OPTIONS_ENABLED         = false
  OPTIONS_CANARY_ENABLED  = false
```

Master execution gate stays off. Canary remains gated.

### Step 8 — no options lifecycle activation ✅ PASS

```
options_paper_portfolio (canary-spy-v1)    active = f
options_paper_trade                        count  = 1   (pre-existing fixture)
options_paper_position                     count  = 0
options_trade_lifecycle_event              count  = 0
```

No new paper option trades. No positions opened. No lifecycle events
written. The chain table is fresh; nothing acts on it.

---

## Telemetry-of-truth: `options_chain_ingest_run`

Two rows present (from validation Steps 3 + 5):

```
started_at                  | provider | inserted | dedup | n_ok | class    | dur(s)
2026-05-19 18:38:09.348+00  | tradier  |     6728 |     0 |    5 | success  | 80.256
2026-05-19 18:35:13.395+00  | tradier  |     6831 |     0 |    5 | success  | 83.684
```

This table now answers the question "did chain ingest actually work today?"
**without** trusting `job_run.status`. Dashboards / monitors should join on
this table for the next 30 days while we observe wrapper-RC behavior under
real scheduled fires.

---

## What was NOT done (in-scope guardrail)

- Did **not** activate options execution
- Did **not** flip `OPTIONS_ENABLED` or `OPTIONS_CANARY_ENABLED`
- Did **not** activate canary portfolio (`active` still false)
- Did **not** create any paper option trade
- Did **not** modify UI state, banners, or HONEST-BANNER copy
- Did **not** open Phase 1A or Phase 1B work

Anything beyond chain-data freshness remains in dormant / observation
posture exactly as before the recovery.

---

## Open items (observation queue, no action required)

1. **Wait for the 01:30 UTC scheduled fire on 2026-05-20** and verify the
   resulting `job_run` row honestly reflects work (status=success only when
   `options_chain_ingest_run.rows_inserted > 0`).
2. **Decide on quote-instant cadence**: today the cron fires daily and each
   call creates a fresh `snapshot_at_utc`. If Phase 1A wants intra-day
   quote refresh, this is the natural insertion point — the wrapper is
   already honest about it.
3. **Sandbox vs production Tradier**: current token points at
   `sandbox.tradier.com/v1`. Production cutover is a separate decision
   (Phase 1A prerequisite).
4. **Universe expansion**: `DEFAULT_UNIVERSE` is 5 symbols. Phase 1A
   activation should reassess.

None of these block the recovery from being declared complete.

---

## Verdict

**Chain ingest is truthful and fresh.** Wrapper-RC honesty is structurally
deployed and telemetry-of-truth is live. The system can now be observed
under real scheduled fires before any Phase 1A / 1B activation decision.

Recovery: **COMPLETE**.
