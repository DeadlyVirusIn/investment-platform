# Canary-1 — Gate 5 READY FOR MARKET-HOURS RESUME

**Date**: 2026-05-20
**State**: All resume prerequisites met EXCEPT fresh market-hours SPY chain ingest.
**Predecessors**:
- `OPTIONS_CANARY_1_GATE_5_BLAST_RADIUS.md` (memo)
- `OPTIONS_CANARY_1_GATE_5_PAUSE.md` (pause record)

---

## Status

| Prerequisite | State | Block? |
|---|---|---|
| Migration 090 applied                                          | ✅ `090_opt_canary_lifecycle_run` head | no |
| Canary cash $10,000                                            | ✅ preserved | no |
| Code changes on host                                           | ✅ all 9 files | no |
| Code changes on cron container                                 | ✅ re-synced after Polygon recreate | no |
| Code changes on tickloop container                             | ✅ re-synced after Polygon recreate | no |
| `md5_parity` (8 files × 2 containers)                          | ✅ PASS — 8/8 match | no |
| `alembic_head`                                                 | ✅ PASS — `090_opt_canary_lifecycle_run` | no |
| `canary_portfolio_active`                                      | ❌ `false` — flip at resume time | **expected blocker** |
| `chain_freshness`                                              | ❌ 973 min old (Tradier sandbox after-hours) | **single remaining blocker** |
| `scripts/canary_preflight.py --strict`                         | exit=1 (2 expected failures) | will exit 0 once chain refreshes + portfolio flipped |
| `OPTIONS_ENABLED`                                              | ✅ `false` | no |
| `OPTIONS_CANARY_ENABLED`                                       | ✅ `false` | no |
| `options_paper_position` count                                 | ✅ 0 | no |
| `options_trade_lifecycle_event` count                          | ✅ 0 | no |
| `options_canary_lifecycle_run` count                           | ✅ 0 | no |
| Stocks pipeline                                                | ✅ healthy (overnight cycle clean) | no |

**The single remaining blocker is fresh market-hours chain data.**

---

## Md5 parity table (verified at resume-prep time)

```
File                                                          host           cron           tickloop       Status
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────
apps/worker/src/jobs/options_chain_snapshot.py                6e9c7acee8e9   6e9c7acee8e9   6e9c7acee8e9   PASS
apps/worker/src/jobs/options_canary_proposal.py               5aef98001445   5aef98001445   5aef98001445   PASS
apps/worker/src/jobs/options_canary_lifecycle.py              8f32a4888c72   8f32a4888c72   8f32a4888c72   PASS
apps/api/src/options/data/chain_ingest.py                     719a6984787c   719a6984787c   719a6984787c   PASS
apps/api/src/options/data_provider/tradier_adapter.py         82860f5d7cac   82860f5d7cac   82860f5d7cac   PASS
apps/api/src/options/canary/engine.py                         c83600d1bbd0   c83600d1bbd0   c83600d1bbd0   PASS
apps/api/src/config/__init__.py                               4abef0aeb386   4abef0aeb386   4abef0aeb386   PASS
apps/api/src/db/models.py                                     bb0a2daa4371   bb0a2daa4371   bb0a2daa4371   PASS
```

Also re-synced (post-Polygon-env-recreate drift cleanup):
- `apps/api/src/options/data_provider/finnhub_adapter.py`
- `apps/api/src/options/data_provider/_redact.py`
- `apps/api/src/options/data_provider/base_adapter.py`
- `apps/api/src/options/data_provider/thetadata_adapter.py`
- `apps/api/src/options/data_provider/greeks.py`
- `apps/api/src/options/data/liquidity_filter.py`

---

## Fresh-chain requirement

Resume conditions met **only** when ALL of the following hold:

```sql
-- Latest SPY snapshot must be within 240 min (Gate 5 exception).
SELECT MAX(snapshot_at_utc),
       EXTRACT(EPOCH FROM (NOW() - MAX(snapshot_at_utc))) / 60.0 AS age_min
FROM options_chain_snapshot
WHERE underlying = 'SPY';
-- age_min must be < 240
```

```sql
-- Most recent options_chain_ingest_run row must NOT be 'error' or
-- 'flags_off'. (Need not be 'success' under Gate 5 exception.)
SELECT classification, started_at
FROM options_chain_ingest_run
ORDER BY started_at DESC LIMIT 1;
-- classification ∈ {success, no_new_data, partial}
```

US regular session: Mon–Fri 13:30–20:00 UTC (09:30–16:00 ET). Scheduled
chain ingest fires at 01:30 UTC daily; Tradier sandbox quotes become
ingestable once the regular session is open.

---

## Exact resume command sequence

When all preconditions above are met:

```bash
# 1. Re-verify preflight (must exit 0 BEFORE flipping anything).
python scripts/canary_preflight.py --strict
echo "preflight exit=$?"        # MUST be 0 after portfolio flip

# 2. Flip canary portfolio active.
docker exec compose-db-1 sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
   -c "UPDATE options_paper_portfolio \
       SET active=true, updated_at=now() \
       WHERE name='\''canary-spy-v1'\'';"'

# 3. Re-run preflight (now expected to be all green).
python scripts/canary_preflight.py --strict   # exit 0 expected

# 4. Single manual proposal fire (ephemeral OPTIONS_CANARY_ENABLED).
docker exec -e OPTIONS_CANARY_ENABLED=true compose-worker-tickloop-1 \
  bash -c 'cd /app && python -c "
import asyncio
from apps.worker.src.jobs.options_canary_proposal \
  import run_options_canary_proposal_job
r = asyncio.run(run_options_canary_proposal_job())
print(\"JOB RESULT:\", r)
"'

# 5. Verify expected row deltas (queries below).

# 6. Revert canary portfolio active.
docker exec compose-db-1 sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
   -c "UPDATE options_paper_portfolio \
       SET active=false, updated_at=now() \
       WHERE name='\''canary-spy-v1'\'';"'
```

---

## Validation query set (run after step 5)

```sql
-- Telemetry row written?
SELECT * FROM options_canary_lifecycle_run
ORDER BY started_at DESC LIMIT 1;
-- Expected: 1 row, classification='success' (or 'no_op' if no candidate),
--           job_name='canary_proposal', portfolio_id='canary-spy-v1'

-- Proposal trade row created?
SELECT id, status, strategy_name, underlying, proposal_hash, created_at
FROM options_paper_trade
WHERE strategy_name = 'LONG_CALL'
ORDER BY created_at DESC LIMIT 1;
-- Expected on candidate-found path: 1 row, status='PROPOSED', strategy='LONG_CALL'
-- Expected on no-candidate path: no new row

-- PROPOSED lifecycle event written?
SELECT trade_id, event_type, event_at_utc, payload_json
FROM options_trade_lifecycle_event
WHERE event_type = 'PROPOSED'
ORDER BY event_at_utc DESC LIMIT 1;
-- Expected on candidate-found path: 1 row, event_type='PROPOSED'

-- Guaranteed-untouched counts (must remain 0):
SELECT 'options_paper_position', COUNT(*) FROM options_paper_position
UNION ALL SELECT 'OPENED events',
  COUNT(*) FROM options_trade_lifecycle_event
  WHERE event_type IN ('OPENED','MONITORED','CLOSED');

-- Stocks-side counts (must remain on natural cron trajectory):
SELECT 'paper_trade', COUNT(*) FROM paper_trade;
SELECT 'paper_position open', COUNT(*) FROM paper_position WHERE is_open=true;
SELECT 'paper_equity_snapshot', COUNT(*) FROM paper_equity_snapshot;
```

---

## Exact rollback command (if anything looks wrong)

```bash
# Layer A (soft) — revert flag, leave evidence:
docker exec compose-db-1 sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
   -c "UPDATE options_paper_portfolio \
       SET active=false, updated_at=now() \
       WHERE name='\''canary-spy-v1'\'';"'

# Layer B (delete schedule rows — none inserted during Gate 5 per D3,
# so this is a no-op unless step 4 was followed by a schedule INSERT):
# docker exec compose-db-1 sh -c \
#   'psql ... -c "DELETE FROM job_schedule \
#    WHERE name IN ('\''options_canary_proposal'\'','\''options_canary_lifecycle'\'');"'

# Layer C (migration rollback — destroys telemetry evidence; only if
# 090 itself is broken):
# docker exec compose-api-1 bash -c \
#   'cd /app && PYTHONPATH=/app alembic -c infra/alembic/alembic.ini \
#    downgrade 089_opt_chain_ingest_run'
```

Recommended on first failure: **Layer A only**. Preserves telemetry +
lifecycle event chain for post-mortem.

---

## State guards at resume-prep snapshot (2026-05-20)

```
OPTIONS_ENABLED         = false   (tickloop env)
OPTIONS_CANARY_ENABLED  = false   (tickloop env)
canary-spy-v1.active    = false
canary-spy-v1.cash      = 10,000.0000  (preserved)

options_paper_position           = 0
options_paper_trade              = 1   (pre-existing fixture)
options_trade_lifecycle_event    = 0
options_canary_lifecycle_run     = 0
job_schedule canary rows         = 0
```

Identical to the snapshot recorded in `OPTIONS_CANARY_1_GATE_5_PAUSE.md`.

---

## Envelope-generation-run quietness — trace result

Audit was performed in parallel with the resume prep. Findings:

| Aspect | Finding |
|---|---|
| Recent rows in last 24h                                            | 0 rows for today (2026-05-20) |
| Earliest INSERT path                                                 | `apps/worker/src/jobs/run_paper_trading.py:282` |
| Write gate                                                           | `if _trades_exec > 0:` (line 276) — row written ONLY when the run opened ≥1 new trade |
| Today's `run_paper_trading`                                          | success, duration 0.14s (no work — typical no-buy-day fast path) |
| `run_paper_exit_cycle` envelope writes                              | none — by design; envelopes are for entries (BUYS), not exits |
| Historical rows                                                     | 7 total, latest 2026-05-19 11:41 + 14:26 (confirmed writer works) |

**Classification**: **EXPECTED quietness**, not broken. Today's overnight
cycle:
- Opened 0 new entries via `run_paper_trading` (0.14s = no-work)
- Closed 14 positions via `run_paper_exit_cycle` (exit path; doesn't write envelopes)
- No envelope rows because no new entries

A real defect would look like: `run_paper_trading` reports `success` AND
`trades_executed > 0` AND no `envelope_generation_run` row appears. That
did not happen tonight.

**Minor pre-existing data-quality observation** (not in Gate 5 scope, not
implementing): the 3 most recent envelope_generation_run rows have
`as_of_date = NULL`. Worth investigating in a separate session — likely a
missing-or-nullable `as_of` parameter at one INSERT call site. Documented
here for future cleanup; NOT a Gate 5 blocker, NOT touched per directive.

---

## What's true at this checkpoint

- ✅ All Gate 5 prerequisites met EXCEPT fresh market-hours chain data
- ✅ Md5 parity restored across all 8 critical files × 2 worker containers
- ✅ Alembic head consistent
- ✅ Constitutional locks (forbidden-phrase, resolver-anchor, canary-gateway lints) all green
- ✅ State guards identical to pre-pause snapshot
- ✅ Stocks pipeline operationally healthy
- ✅ Polygon-powered live-NAV operationally healthy
- ✅ Wrapper-RC honesty validated in production (today's `options_chain_snapshot` cron firing classified `skipped` not `success`)
- ❌ Chain data 973 min old (Tradier sandbox after-hours; cron at 01:30 UTC won't help — needs regular session)
- ❌ Portfolio.active=false (will flip at resume time only)

**Next concrete action**: wait for next US regular session (today
2026-05-20 ≥ 13:30 UTC). After the first market-hours `options_chain_snapshot`
fires with `classification='success'`, re-run the resume command sequence.

No code changes between now and resume.
No flag flips between now and resume.
No new options trades/positions/events between now and resume.

This document is the contract for resume.
