# Canary-1 — Gate 5 Paused (Pending Market-Hours Retry)

**Date paused**: 2026-05-19 ~22:55 UTC (after US regular session close)
**Reason**: Refusing to bump chain-freshness threshold a second time
**Resumes**: Next US market session (2026-05-20 ~14:30 UTC or later, once
fresh SPY chain data exists)

---

## Why we paused

Gate 5 ran end-to-end through step 11 setup. Preflight on step 10 produced
this result with all other checks green:

```
[ PASS ] md5_parity            files_checked: 8
[ PASS ] alembic_head           head: 090_opt_canary_lifecycle_run
[ PASS ] canary_portfolio_active
[ FAIL ] chain_freshness        age_minutes: 263.51, max=240
```

Latest SPY chain snapshot in `options_chain_snapshot` is 18:38 UTC (today,
during regular session). At pause time the gap exceeded 240 minutes by
~23 minutes. The previously-approved Gate 5 exception had already moved
the threshold from 90 → 240 minutes; moving it again would have been
fitting the threshold to the test rather than proving the preflight
honestly.

We refuse to:
- bump freshness threshold a second time
- bypass `chain_freshness` for the manual fire
- run the dry run on data we wouldn't trust at Gate 6+

This is not "wait and hope". This is preserving the proof condition.

---

## State at pause (verified)

### Row counts identical to pre-Gate-5

| Table | Count | Notes |
|---|---|---|
| `options_paper_trade`            | 1     | pre-existing fixture, unchanged |
| `options_paper_position`         | 0     | unchanged |
| `options_trade_lifecycle_event`  | 0     | unchanged |
| `options_canary_lifecycle_run`   | 0     | unchanged (table empty since creation) |
| `options_chain_snapshot`         | 26,991 | unchanged |
| `options_chain_ingest_run`       | 3     | unchanged |
| `paper_trade` (stocks)           | 138   | untouched (independent) |
| `job_schedule`                   | 12    | no canary rows inserted |
| `job_schedule` rows for canary   | 0     | confirmed via SELECT |
| `options_paper_trade` strategy=LONG_CALL | 0 | confirmed |

### Flags + portfolio state

```
OPTIONS_ENABLED         = false   (unchanged from pre-Gate-5)
OPTIONS_CANARY_ENABLED  = false   (unchanged from pre-Gate-5)
canary-spy-v1.active    = false   (reverted from true)
canary-spy-v1.cash_initial = 10000.0000   (preserved from Gate 5 step 5)
canary-spy-v1.cash_current = 10000.0000   (preserved from Gate 5 step 5)
```

### What persisted intentionally (not reverted)

These are the durable Gate 5 artifacts that the next retry will use:

1. **Migration 090** applied (`alembic current = 090_opt_canary_lifecycle_run`).
   Table + 6 CHECK constraints + 4 indexes ready for telemetry writes
   on retry.
2. **Canary portfolio cash** $10,000 (was $2,000 pre-Gate-5). Set per
   blast-radius D4 to avoid underfunded-canary failure mode.
3. **Code changes** on host + both worker containers + cron drift fixed:
   - `apps/api/src/options/canary/engine.py`               (real preflight + proposal cycle)
   - `apps/worker/src/jobs/options_canary_proposal.py`     (master flag gate)
   - `apps/worker/src/jobs/options_canary_lifecycle.py`    (dormant-on-canary-flag-alone per D1)
   - `apps/worker/src/jobs/registry.py`                    (2 new entries)
   - `scripts/canary_preflight.py`                          (4 real check bodies)
   - `infra/ci/constitutional_checklist/canary_gateway_lint.py` (L1–L6)
   - `.github/workflows/phase_l_lint.yml`                   (CI wiring)
   - `docs/research/OPTIONS_CANARY_1_GATE_5_BLAST_RADIUS.md` (§6a addendum)
4. **Cron container drift fix** — 10 files docker cp'd to
   `compose-worker-cron-1` (canary files + 4 pre-existing options jobs
   + `run_paper_exit_cycle.py` + `models.py` + `registry.py`).

None of these introduce production behavior. All paths gate on either
`OPTIONS_ENABLED` or `OPTIONS_CANARY_ENABLED`, both of which are `false`.

### What did NOT happen

- No `OPTIONS_ENABLED` flip
- No canary trade created (zero LONG_CALL rows)
- No lifecycle events written
- No telemetry rows written
- No options_paper_position rows
- No fill, no OPENED event
- No `job_schedule` row inserted for canary jobs
- No stocks-side impact (paper_trade count unchanged)
- No Phase L impact (envelopes, audits, snapshots untouched)
- No UI change

---

## Resume conditions (next market session)

Required state before resuming step 10:

1. **Fresh SPY chain ingest succeeded within the past 90 minutes**:
   ```
   SELECT classification, started_at, NOW() - started_at AS age
   FROM options_chain_ingest_run
   WHERE classification = 'success'
   ORDER BY started_at DESC LIMIT 1;
   ```
   AND most-recent snapshot in `options_chain_snapshot WHERE underlying='SPY'`
   is also within 90 minutes.

2. **`python scripts/canary_preflight.py --strict` returns exit 0**
   with portfolio flipped to `active=true`.

3. **Gate 5 freshness threshold remains 240 minutes** (the previously
   approved exception). We do NOT bump it further. The expectation is
   that during market hours, the actionable data is fresh enough that
   the 240-min bound is comfortably satisfied (typical age < 30 min
   during active ingest cycles).

4. **OPTIONS_ENABLED stays false**. Only `OPTIONS_CANARY_ENABLED` flips,
   via ephemeral `docker exec -e` for the manual fire.

5. **Hard constraints unchanged from original directive**:
   - one manual proposal fire only
   - no fill
   - no OPENED event
   - no `options_paper_position` row
   - no lifecycle execution
   - stop on unexpected mutation

---

## Resume sequence (when conditions met)

Pick up at memo step 10. Steps 1–9 of the original Gate 5 14-step order
are already complete (or intentionally skipped per D1/D3).

| # | Step | Status |
|---|---|---|
| 1 | Memo approval | ✅ DONE |
| 2 | D1–D4 decisions | ✅ DONE |
| 3 | Cron-container hot-patch + restart | ✅ DONE (10 files) |
| 4 | Apply migration 090 | ✅ DONE |
| 5 | Set canary cash $10,000 | ✅ DONE |
| 6 | Real preflight bodies + Gate 5 freshness exception (90→240, anchor on snapshot_at_utc) | ✅ DONE |
| 7 | Tighten lifecycle wrapper per D1 (dormant on canary flag alone) | ✅ DONE |
| 8 | Insert job_schedule row | ⏭ SKIPPED per D3 (one manual fire only) |
| 9 | Flip `OPTIONS_CANARY_ENABLED=true` | ⏭ DEFERRED to ephemeral `docker exec -e` at step 11 |
| 10 | Flip portfolio `active=true` | ↩ REVERTED at pause; redo on retry |
| 11 | Single triggered dry run | ⏸ PAUSED — blocked on chain freshness |
| 12 | Verify §3a + §4 row deltas | pending |
| 13 | Revert flags + portfolio active | pending |
| 14 | Write completion report | pending |

On retry: re-do step 10, then step 11 via:

```
MSYS_NO_PATHCONV=1 docker exec -e OPTIONS_CANARY_ENABLED=true \
  compose-worker-tickloop-1 bash -c \
  'cd /app && python -c "import asyncio; \
    from apps.worker.src.jobs.options_canary_proposal \
      import run_options_canary_proposal_job; \
    r = asyncio.run(run_options_canary_proposal_job()); \
    print(\"JOB RESULT:\", r)"'
```

Then step 12 verifies S1–S10 from the memo §11.

---

## Why this pause is the right call

A canary that runs because we keep relaxing its gates is not a canary —
it is a self-fulfilling demonstration. Gate 5's purpose is to prove that
the preflight will halt proposals when chain data is too stale. If we
relax the threshold every time the preflight fires, we are removing the
very mechanism we built.

The 90→240 exception was justified by the **architectural** mismatch
between ingest-telemetry anchor and chain-data anchor. A 240→360 bump
would be justified only by the **schedule** mismatch between when we
want to test and when the data is fresh. Those are different categories
of deviation, and only the first kind belongs in a hardened spec.

Holding the line costs ~16 hours of waiting. Compromising it costs the
proof that everything else in Gate 5 was supposed to deliver. The wait
wins.

---

## Rollback inventory (in case we ever need to scrub Gate 5 entirely)

For completeness; not requested, not executed.

```sql
-- Soft (already done):
UPDATE options_paper_portfolio SET active=false WHERE name='canary-spy-v1';

-- Cash revert (NOT done; cash stays at $10k for retry):
-- UPDATE options_paper_portfolio SET cash_initial=2000, cash_current=2000
--   WHERE name='canary-spy-v1';

-- Migration revert (NOT done; 090 stays applied for retry):
-- alembic -c infra/alembic/alembic.ini downgrade 089_opt_chain_ingest_run

-- Code revert (NOT done; files stay staged for retry):
-- git checkout HEAD -- apps/api/src/options/canary/ apps/worker/src/jobs/options_canary_*.py
-- (and the other files listed above)
```

None of these are needed unless the retry produces unexpected outcomes.
