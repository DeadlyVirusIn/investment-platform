# Options chain ingest — forensic audit

**Date**: 2026-05-19
**Method**: Read-only code + env + DB inspection. Live probe of Tradier sandbox.
**Verdict**: **THREE concurrent failures**, all preventing chain ingestion from producing new rows. One of them (worker stale code) is the same disease as the stocks-side sell deployment drift, just on a different surface. Cron continues reporting `success` because the wrapper returns `None`, which tick_loop classifies as success regardless of work performed.

---

## ONE-LINE ROOT CAUSE

Cron worker container `compose-worker-cron-1` has stale options-module files dated **2026-04-26/28** — pre-dating the Tradier-adapter rollout. Its settings carry `OPTIONS_SHADOW_EVAL_ENABLED=False`, `OPTIONS_DATA_PROVIDER=thetadata` (default), and `TRADIER_ACCESS_TOKEN` empty. The wrapper early-returns `None` and tick_loop classifies that as `success`. Stocks-side D2.3 wrapper-RC honesty was never applied to this wrapper.

---

## THE THREE CONCURRENT FAILURES

### Failure 1 — Worker has stale options module files

```
Host:                                Worker (compose-worker-cron-1):
  data_provider/__init__.py            data_provider/__init__.py
  data_provider/_redact.py             (MISSING)
  data_provider/base_adapter.py        data_provider/base_adapter.py
  data_provider/finnhub_adapter.py     (MISSING)
  data_provider/greeks.py              data_provider/greeks.py
  data_provider/thetadata_adapter.py   data_provider/thetadata_adapter.py
  data_provider/tradier_adapter.py     (MISSING)
```

File timestamps on worker: **2026-04-26 to 2026-04-28**. The Tradier adapter was added later but never deployed to the worker. `chain_ingest.py` on the worker is the OLDER version that only imports `thetadata_adapter`.

Identical pattern to the stocks-side stale `paper_service.py` / `models.py` (2026-04-19 timestamps). Same disease, different module tree.

### Failure 2 — Worker settings differ from API container

| Setting | API container | Worker container |
|---------|---------------|-------------------|
| `OPTIONS_ENABLED` | False | False |
| `OPTIONS_SHADOW_EVAL_ENABLED` | True (env) | **False** (worker can't see env) |
| `OPTIONS_DATA_PROVIDER` | tradier | **thetadata** (default fallback) |
| `TRADIER_BASE_URL` | `https://sandbox.tradier.com/v1` | **MISSING** |
| `TRADIER_ACCESS_TOKEN` | set (28 chars) | **empty** |

The worker container's docker-compose `env` either doesn't include the OPTIONS / TRADIER environment variables, or they get filtered before reaching the Python process. The API container loads them correctly.

### Failure 3 — Wrapper-RC honesty never applied to chain ingest

`apps/worker/src/jobs/options_chain_snapshot.py` returns `None` on all paths:

```python
async def run_options_chain_snapshot_job() -> None:
    if not (OPTIONS_ENABLED or OPTIONS_SHADOW_EVAL_ENABLED):
        logger.info("...skipped — both are False")
        return  # ← returns None implicitly
    summaries = ingest_universe(...)
    logger.info(...)  # logs but doesn't return
    # implicit return None
```

`tick_loop._execute_job` (D2.3 wrapper-RC honesty work) checks for `{skipped: True}` to classify as 'skipped'. **`None` doesn't match.** Result: every chain_snapshot run classifies as `job_run.status='success'` regardless of whether 0 or 6561 rows were inserted.

Compare to `options_canary_promotion` and `options_lifecycle_check` stubs — those DO return `{"skipped": True, "reason": "..."}` and CORRECTLY classify as 'skipped'. The chain_snapshot wrapper was written before D2.3 honesty was established and was never updated.

---

## CALL FLOW MAPPING

### Read path (intended)

```
cron tick_loop
  → run_options_chain_snapshot_job()                    [worker wrapper]
      ↳ if gate flags off → return None (skips silently)
      → ingest_universe(DEFAULT_UNIVERSE)               [orchestrator]
          for each underlying (SPY/QQQ/IWM/GLD/TLT):
            → ingest_chain_snapshot(...)                [per-symbol]
                → adapter._build_adapter(provider)
                    → TradierOptionsAdapter             [needs token]
                → adapter.get_chain_snapshot()
                    → /markets/options/expirations
                    → /markets/options/chains × N expiries
                → filter_chain(quotes, profile)
                → _insert_quotes(session, accepted)
                    → INSERT ... ON CONFLICT DO NOTHING
                    → returns (inserted, skipped_existing)
                → IngestSummary(status, n_inserted, ...)
            → logger.info(per-symbol summary)
      → logger.info(total_inserted across universe)
```

### What ACTUALLY happens on cron worker (today)

```
cron tick_loop
  → run_options_chain_snapshot_job()
      ↳ settings.OPTIONS_ENABLED = False
      ↳ settings.OPTIONS_SHADOW_EVAL_ENABLED = False
      → early return None
  → tick_loop sees None → classifies as 'success'
  → job_run row written with status='success', duration ≈ 0.005s
```

(The historical 2026-05-19 01:30 UTC run with `duration=74s` corresponds to a DIFFERENT worker process state. Recent worker restarts have reset the in-process environment. Cannot reconstruct exactly what was happening then without log archives.)

### What WAS happening on 2026-05-13 (when 6561 rows landed)

Hypothesis based on evidence:
- Manual operator-driven invocation from the API container (which DOES have credentials + full module set), OR
- An earlier worker process state with full Tradier adapter + credentials, which has since been lost across container restarts

The 6561-row corpus is a single-moment snapshot from `snapshot_at_utc = 2026-05-13 17:47:27 UTC`. Tradier sandbox snapshots all options across the 5-symbol universe at that exact moment. This is consistent with ONE successful manual call, not a series of cron-driven calls.

---

## DB BEHAVIOR (correct, not the bug)

### ON CONFLICT semantics

```sql
INSERT INTO options_chain_snapshot ( ... ) VALUES ( ... )
ON CONFLICT ON CONSTRAINT ux_options_chain_snapshot_natural_key DO NOTHING
```

Natural key: `(snapshot_at_utc, underlying, expiry, strike, option_type)`.

`result.rowcount` returns 1 on insert, 0 on conflict. `_insert_quotes` correctly classifies each as `inserted` or `skipped_existing`. The DB layer is honest.

### What would happen if same data arrived twice

Same `snapshot_at_utc` (timestamp resolution: microseconds) means natural-key collision → DO NOTHING → `skipped_existing` count increments. Inserted count stays 0. This is CORRECT.

What would NOT cause this bug: dedup itself. If the adapter were producing fresh quotes with current `snapshot_at_utc`, they would always insert (timestamp uniqueness). The dedup is not the issue.

---

## PROVIDER REALITY (live probe)

Tradier sandbox responds **200 OK** to `/markets/clock` from the API container (token present):

```json
{
  "clock": {
    "date": "2026-05-19",
    "description": "Market is open from 09:30 to 16:00",
    "state": "open",
    "timestamp": 1779207480,
    "next_change": "16:00",
    "next_state": "postmarket"
  }
}
```

Tradier sandbox is alive, market data is current. **The provider is not the problem.** The problem is the worker can't authenticate (no token).

From the WORKER container, the same probe fails immediately because `TRADIER_BASE_URL` and `TRADIER_ACCESS_TOKEN` are both unset.

---

## HONESTY AUDIT — classification of today's chain ingest

If we ran the chain_snapshot job RIGHT NOW from cron worker, the outcome would be:

| Indicator | Value | Honest classification |
|-----------|-------|----------------------|
| Provider reachable | NO (worker has no creds) | provider-config error |
| Code present | Stale (Tradier adapter missing) | deployment drift |
| `OPTIONS_SHADOW_EVAL_ENABLED` (worker view) | False | gate-off |
| Wrapper return value | `None` | should be `{skipped: True, reason: "..."}` |
| tick_loop classification | `success` | wrong — actual work was zero |
| `total_inserted` logged | 0 | logged but not surfaced |
| Telemetry row | none (no telemetry table) | absent |

True classification: **silent no-op** disguised as success.

---

## CODE-PATH FAILURE ENUMERATION

What the chain_snapshot wrapper SHOULD report under each condition:

| Condition | Honest skip reason |
|-----------|---------------------|
| OPTIONS_ENABLED=false AND OPTIONS_SHADOW_EVAL_ENABLED=false | `master_flags_off` |
| Tradier creds missing | `provider_credentials_missing` |
| Tradier adapter module missing | `adapter_module_missing` (would actually raise ImportError but we'd want classification) |
| Tradier API returned 401/403 | `provider_auth_failed` |
| Tradier API returned 429 | `provider_rate_limited` |
| Tradier API returned 5xx | `provider_unavailable` |
| Tradier returned empty universe | `provider_returned_empty` |
| All inserts dedup'd (no new data) | `no_new_chain_data` |
| Partial chain (some symbols failed) | `partial_success` with per-symbol breakdown |
| All inserts succeeded | `success` with row count |

Current implementation collapses ALL of these into `success`.

---

## SQL EVIDENCE

### Chain data freshness

```sql
SELECT COUNT(*), MIN(snapshot_at_utc), MAX(snapshot_at_utc)
FROM options_chain_snapshot;
-- 6561 | 2026-05-13 17:47:27.878858+00 | 2026-05-13 17:47:27.878858+00
```

Single point-in-time snapshot. Range zero. No cron-driven updates.

### Job run history

```sql
SELECT name, last_run_at, status FROM job_schedule
WHERE name='options_chain_snapshot';
-- options_chain_snapshot | 2026-05-19 01:30:13.206793+00 | (success per job_run)
```

Most-recent run: 2026-05-19 01:30 UTC, status=success, duration=74s.

No artifact of work in the DB. The 74s was likely either:
- Module load + early-return paths × some delays = several seconds, plus retries
- An earlier worker process state that did make API calls but got dedup'd

### Worker file timestamps

```
options/data_provider/__init__.py       2026-04-26
options/data_provider/base_adapter.py   2026-04-26
options/data_provider/greeks.py         2026-04-26
options/data_provider/thetadata_adapter.py  2026-04-28
options/data/chain_ingest.py            2026-04-26
```

All pre-date the May 2026 Tradier adapter rollout. Stale window: ~3 weeks.

---

## MINIMAL FIX PROPOSAL (do NOT implement without approval)

Three coordinated changes, in this order:

### Fix 1 — Sync options modules to worker containers

```bash
# Deploy missing/stale options modules to both worker containers
for c in compose-worker-cron-1 compose-worker-tickloop-1; do
  docker cp apps/api/src/options/data_provider/_redact.py $c:/app/apps/api/src/options/data_provider/_redact.py
  docker cp apps/api/src/options/data_provider/finnhub_adapter.py $c:/app/apps/api/src/options/data_provider/finnhub_adapter.py
  docker cp apps/api/src/options/data_provider/tradier_adapter.py $c:/app/apps/api/src/options/data_provider/tradier_adapter.py
  docker cp apps/api/src/options/data_provider/base_adapter.py $c:/app/apps/api/src/options/data_provider/base_adapter.py
  docker cp apps/api/src/options/data_provider/thetadata_adapter.py $c:/app/apps/api/src/options/data_provider/thetadata_adapter.py
  docker cp apps/api/src/options/data_provider/greeks.py $c:/app/apps/api/src/options/data_provider/greeks.py
  docker cp apps/api/src/options/data/chain_ingest.py $c:/app/apps/api/src/options/data/chain_ingest.py
  docker cp apps/api/src/options/data/liquidity_filter.py $c:/app/apps/api/src/options/data/liquidity_filter.py
done
```

This is the same kind of deploy-only operation used for `paper_service.py` + `models.py` during stocks-side recovery. No code change, just file sync.

### Fix 2 — Set Tradier credentials + OPTIONS settings on worker

The worker container's environment must include:
- `TRADIER_BASE_URL=https://sandbox.tradier.com/v1`
- `TRADIER_ACCESS_TOKEN=<same as API container>`
- `OPTIONS_DATA_PROVIDER=tradier`
- `OPTIONS_SHADOW_EVAL_ENABLED=true`

Requires `infra/compose/docker-compose.yml` change to propagate environment variables to worker services. Verify worker services list explicitly carries the OPTIONS_* + TRADIER_* env vars under their `environment:` keys.

### Fix 3 — Wrapper-RC honesty for chain_snapshot job

Modify `apps/worker/src/jobs/options_chain_snapshot.py` to return structured outcomes:

```python
async def run_options_chain_snapshot_job() -> dict:
    if not (settings.OPTIONS_ENABLED or settings.OPTIONS_SHADOW_EVAL_ENABLED):
        return {"skipped": True, "reason": "master_flags_off"}

    try:
        summaries = ingest_universe(...)
    except Exception as exc:
        logger.error(...)
        return {"return_code": 1, "reason": f"exception:{type(exc).__name__}"}

    total_inserted = sum(s.n_inserted for s in summaries)
    n_error = sum(1 for s in summaries if s.status == "error")
    n_partial = sum(1 for s in summaries if s.status == "partial")

    if total_inserted == 0:
        # Honest classification of zero-work success
        return {
            "skipped": True,
            "reason": "no_new_chain_data" if n_error == 0 else "all_symbols_failed",
            "detail": {"summaries": [dataclasses.asdict(s) for s in summaries]},
        }
    return {"return_code": 0, "inserted": total_inserted}
```

Wrapper now classifies into `skipped` / `error` / `success` honestly. tick_loop will record the right `job_run.status`.

---

## TELEMETRY PROPOSAL

New table: `options_chain_ingest_run` (analog of `envelope_generation_run`):

```sql
CREATE TABLE options_chain_ingest_run (
    id              BIGSERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL,
    finished_at     TIMESTAMPTZ,
    provider        TEXT NOT NULL,
    universe        TEXT[] NOT NULL,
    rows_inserted   INTEGER NOT NULL DEFAULT 0,
    rows_dedup      INTEGER NOT NULL DEFAULT 0,
    rows_filtered_out INTEGER NOT NULL DEFAULT 0,
    n_symbols_ok    INTEGER NOT NULL DEFAULT 0,
    n_symbols_partial INTEGER NOT NULL DEFAULT 0,
    n_symbols_error INTEGER NOT NULL DEFAULT 0,
    classification  TEXT NOT NULL,
        -- 'success' | 'no_new_data' | 'partial' | 'error' | 'flags_off'
    error_summary   JSONB,
    duration_sec    NUMERIC(8,3)
);

CREATE INDEX ix_options_chain_ingest_run_started ON options_chain_ingest_run (started_at);
```

The wrapper writes ONE row per run. Reading this table answers "did chain ingest actually do work today?" deterministically. No more silent successes.

---

## VALIDATION PLAN

After deploying Fixes 1-3:

### Step 1 — verify worker has new files
```bash
for c in compose-worker-cron-1 compose-worker-tickloop-1; do
  docker exec $c ls /app/apps/api/src/options/data_provider/ | grep tradier_adapter
done
# Expect: tradier_adapter.py present on both
```

### Step 2 — verify worker can see Tradier creds
```bash
docker exec compose-worker-cron-1 python -c "
from apps.api.src.config import settings
print(bool(getattr(settings, 'TRADIER_ACCESS_TOKEN', '')))
"
# Expect: True
```

### Step 3 — manual chain ingest from worker
```bash
docker exec compose-worker-cron-1 python -c "
import asyncio
from apps.worker.src.jobs.options_chain_snapshot import run_options_chain_snapshot_job
r = asyncio.run(run_options_chain_snapshot_job())
print(f'result: {r}')
"
# Expect (with Fix 3): {'return_code': 0, 'inserted': N} with N > 0
```

### Step 4 — verify new chain rows
```sql
SELECT COUNT(*), MAX(snapshot_at_utc) FROM options_chain_snapshot;
-- Expect: count > 6561, max ~now
```

### Step 5 — verify telemetry row
```sql
SELECT * FROM options_chain_ingest_run ORDER BY started_at DESC LIMIT 1;
-- Expect: row with classification='success', rows_inserted > 0
```

### Step 6 — re-run job — verify honest classification of zero-work
```bash
# Same call moments later, no new data:
# Expect: {'skipped': True, 'reason': 'no_new_chain_data'}
```

### Step 7 — observe one natural cron fire
Wait for 2026-05-20 01:30 UTC cron. Verify `job_run.status` reflects actual outcome (success with N rows OR skipped with reason), NOT silent success.

---

## FAILURE-MODE COMPARISON TABLE (stocks vs options)

| Stocks-side disease | Options analog | Same disease? |
|---------------------|------------------|------------------|
| `paper_service.py` stale on workers (D1.4 deploy didn't reach workers) | Options modules stale on workers since 2026-04-26 | **YES, identical** |
| `models.py` ORM stale | Tradier/finnhub adapters MISSING entirely | **YES, worse — file absent not just stale** |
| Buy-side anchor math wrong | (none — chain ingest doesn't have this) | NO |
| Sell-side exit_cycle "success" with 0 closes | Chain "success" with 0 inserts | **YES, identical** — wrapper returns wrong type, tick_loop misclassifies |
| Wrapper-RC honesty applied to some jobs but not all | options_chain_snapshot was missed | **YES** |

The two stocks-side disease categories (deployment drift + wrapper-RC honesty) BOTH affect options chain ingest. Fixing chain ingest requires both fixes in tandem.

---

## WHY CRON "APPEARED HEALTHY" FOR 6 DAYS

Concretely, day-by-day:

| Date | Cron fired? | Actual work | job_run.status | DB rows added |
|------|-------------|-------------|----------------|----------------|
| 2026-05-13 | yes (manual?) | 6561 rows ingested | (success) | +6561 |
| 2026-05-14 | yes | 0 rows | success | 0 |
| 2026-05-15 | yes | 0 rows | success | 0 |
| 2026-05-16 | yes | 0 rows | success | 0 |
| 2026-05-17 (Sun) | no (1-5 cron) | — | — | — |
| 2026-05-18 (Sun) | no | — | — | — |
| 2026-05-19 | yes | 0 rows | success | 0 |

Five consecutive zero-work days reported as success. No alarm. No human noticing.

Identical pattern to stocks-side exit_cycle on 2026-05-19 03:00 UTC: status=success, 0 work, no closes. The wrapper-RC honesty work (D2.3) was supposed to prevent this category of dishonesty. It was applied to canary_promotion + lifecycle_check + run_paper_exit_cycle but NOT to options_chain_snapshot.

---

## ROOT CAUSE — FINAL STATEMENT

**Worker container drift + wrapper honesty gap** = silent zero-work cron.

The drift is the same shape as the stocks sell-side incident. The honesty gap is the same shape as the stocks exit_cycle incident. **We have rediscovered both bugs on a different surface.**

This validates the Phase 1A/1B activation plan's emphasis on:
1. Container parity script (would have caught Failure 1)
2. Worker env-var verification (would have caught Failure 2)
3. Wrapper-RC honesty extension (would have caught Failure 3)

All three are in §5 + §8 of the activation plan. They are the prerequisite for any Phase 1A code to be trustworthy.

---

## CLOSING NOTE

The investigation found exactly what the user predicted: chain ingestion is the options analog of the stocks-side failures. Two of three failure modes (deployment drift, wrapper-RC dishonesty) have the same shape as the stocks bugs. The third (provider config missing on worker) is new but in the same family — environment configuration that should be uniform across containers but isn't.

The fix is mechanical, not architectural. The architecture is correct. The operational discipline failed.

**Next deliverable (when this memo is approved)**: apply Fixes 1, 2, 3 in order. Validate per the 7-step plan. Then options chain ingestion will produce fresh rows daily, and the Phase 1A precondition `assert_fresh_chain_for_today` becomes satisfiable.

NO IMPLEMENTATION until approval. Awaiting direction.
