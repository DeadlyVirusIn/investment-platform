# Intraday Collection Operations Runbook

> **Audience:** operator running the Phase 2 intraday shadow collection.
> **Scope:** weekly observation cadence + anomaly playbooks + pause/rollback procedures.
> **Cross-refs:**
> - Architecture: `docs/research/INTRADAY_ML_SHADOW.md`
> - Phase 3 gates + SQL probes: `docs/research/PHASE_3_READINESS.md`
> - Migration safety: `docs/ops/MIGRATION_WORKFLOW.md`
> - Live state endpoint: `GET /api/intraday-shadow/health`
> - Ops UI: `/ops` page, `IntradayShadowHealthCard`
>
> **Operating philosophy:** this runbook exists so the operator (or a
> future operator, months later) can run the collection phase from
> memory-cold start. Every probe is read-only SQL or a curl. Every
> remediation has an explicit decision tree.
>
> **Discipline locks still in force** — see end of doc for the
> negative list.

---

## Weekly Sunday checklist

Run every **Sunday 20:00 ET** (after the markets close for the week,
before Monday's pre-market cycle). Total time: ~10 minutes.

### Step 1 — Reach the system
```bash
# (laptop / Cloudflare Tunnel — pick whichever is convenient)
curl -s http://localhost:8000/api/intraday-shadow/health | python -m json.tool
```
**Expected:** HTTP 200, JSON response with `enabled: true`, `stale.is_stale: false`, `tape.consecutive_errors: 0`.

### Step 2 — Capture phase 3 progress snapshot
From the JSON response, note:
- `phase_3_progress.lifetime_rows`
- `phase_3_progress.lifetime_distinct_symbols`
- `phase_3_progress.distinct_dates`

### Step 3 — Run weekly probes
Open a new file at `docs/research/observation_log/YYYY-MM-DD.md`
using the template from `PHASE_3_READINESS.md` Appendix A. Run the
SQL probes listed below; paste results.

Probes to run (all read-only SQL from `PHASE_3_READINESS.md`):

| Probe | Doc § | Time |
|---|---|---|
| Leakage L1 — observation timestamp gate | §2 | <1s |
| Leakage L6 — symbol imbalance | §2 | <1s |
| Leakage L7 — time-of-day balance | §2 | <1s |
| Leakage L8 — action-type balance | §2 | <1s |
| Dataset core counts | §4 | <1s |
| Daily ingestion rate (last 14 days) | §4 | <1s |
| Per-symbol coverage + concentration | §5 | <1s |
| Symbol turnover (last 14 days) | §5 | <1s |
| Time-of-day distribution | §6 | <1s |
| Action-type + position-state distribution | §7 | <1s |
| Per-feature null counts | §8 | <1s |
| Sparse-day flag | §8 | <1s |
| Backfill-vs-live attribution | §8 | <1s |
| Feature-distribution quartile shift | §9 | ~5s |
| Hash collision audit | §9 | <1s |
| Source attribution | §9 | <1s |

### Step 4 — Compare to expected healthy ranges
See "Expected healthy ranges" section below. Anything outside range
→ jump to the matching playbook below.

### Step 5 — Note anomalies + decisions
Use the observation-log template to record:
- Probes that passed
- Probes that failed (with output)
- Anomalies observed (if any)
- Decisions made (if any)

### Step 6 — Commit the log
```bash
git add docs/research/observation_log/YYYY-MM-DD.md
git commit -m "log: observation review YYYY-MM-DD"
git push origin phase-1/ledger
```

---

## Expected healthy ranges

Reference table — every field with its healthy band. Operator probes
this each Sunday + on-demand if `/ops` badge ever shows warning.

### Endpoint-level (from `GET /api/intraday-shadow/health`)

| Field | Healthy range | Yellow flag | Red flag |
|---|---|---|---|
| `enabled` | `true` | `false` (intentional pause OK) | `false` unintentionally |
| `stale.minutes_behind_now` | ≤ 20 | 20–30 | > 30 |
| `latest_slot.row_count` | 95–100 | 80–94 | < 80 |
| `latest_slot.cap_hit` | `true` | `false` (means we're underfilling) | n/a |
| `tape.consecutive_errors` | 0 | 1–2 | ≥ 3 |
| `tape.last_error` | `null` | recent transient | persistent non-null |
| `today.row_count` (mid-RTH) | growing each hour by ≥ 200 | flat for 1+ hour | flat for 4+ hours |
| `today.distinct_symbols` | 90–100 (RTH) | 70–89 | < 70 |

### DB-level (probes from §4–§9 of PHASE_3_READINESS.md)

| Metric | Healthy | Yellow | Red |
|---|---|---|---|
| L1 — `quote_ts > observed_at_15min` count | 0 | n/a | any positive value |
| Symbol concentration (top symbol % of total) | ≤ 12% | 12–15% | > 15% |
| Symbols with `days_covered ≥ 30` | growing weekly | flat for 2 weeks | shrinking |
| Time-of-day rows per bucket | each ≥ 200 (excl `off`) | one bucket 100–199 | any non-`off` bucket < 100 |
| Hold-action share | 30–50% | 50–65% | > 65% |
| Sell-action share | 0% (expected; engine emits no sells) | n/a | becomes non-zero unexpectedly |
| Null `intraday_change_pct` rate | < 1% | 1–5% | > 5% |
| Null `vs_macro_drift_pct` rate | < 5% | 5–15% | > 15% |
| Sparse days (rows < 30% of median) | 0 | 1 | ≥ 2 |
| Feature-quartile shift recent vs old | < 30% | 30–50% | > 50% |
| `feature_hash` collision count | 0 | n/a | any positive value |
| Distinct `(source, delay_minutes)` pairs | exactly 1: `('polygon', 15)` | n/a | any other pair appears |

---

## Anomaly examples (illustrative — not exhaustive)

Concrete patterns the operator should recognize.

### Anomaly A: `latest_slot.row_count` drops from 100 → 12

- Likely cause: resolver returned a tiny set this cycle
  (recommendations table emptied? open paper positions all closed?
  cap config changed silently?)
- Probe: `SELECT COUNT(*) FROM recommendation WHERE generated_at >= NOW() - INTERVAL '7 days';`
- Action: see "Symbol concentration spike / underfill" below.

### Anomaly B: `tape.consecutive_errors` = 8

- Likely cause: Polygon outage, key revoked, rate-limit hit (unlikely on Starter), local network down.
- Probe: `curl -s "https://api.polygon.io/v2/aggs/ticker/SPY/prev?apiKey=$POLYGON_API_KEY" | head -c 200`
- Action: see "Polygon degradation" below.

### Anomaly C: `intraday_change_pct` quartile shift Q1 went from `-0.4%` → `-2.1%` week over week

- Likely cause: market regime change (vol spike) OR upstream data definition drift OR backfill rerun with new cut.
- Probe: §9 quartile probe + last 14d daily ingestion + verify backfill hasn't been rerun.
- Action: see "Drift threshold exceeded" below.

### Anomaly D: One symbol holds 22% of total rows

- Likely cause: that symbol's rec has been "active" for many days while others rotate; OR resolver bug.
- Probe: `SELECT symbol, COUNT(*), MIN(observed_at_15min), MAX(observed_at_15min) FROM intraday_observation GROUP BY symbol ORDER BY 2 DESC LIMIT 3;`
- Action: see "Symbol concentration spike" below.

### Anomaly E: `today.row_count` was 3200 at 14:00 ET, still 3200 at 16:00 ET

- Likely cause: poller hung (asyncio task crashed), container restarted but flag is off, DB lock.
- Probe: `docker logs --tail 50 compose-api-1 2>&1 | grep -i "market_tape\|intraday"`
- Action: see "Pause / rollback" below — restart api first.

### Anomaly F: `feature_hash` collisions > 0

- Likely cause: `derive_observation()` lost a feature in code (hash determinism broken), OR Polygon returned identical bars across slots (frozen data feed).
- Probe: §9 hash collision SQL + inspect a few colliding rows.
- Action: HALT writes immediately. The collision implies the hash is not stable across data. Bump `feature_schema_version` after fix (per `PHASE_3_READINESS.md` §11).

---

## When to halt Phase 3 consideration

These conditions trigger an indefinite pause on advancing past
collection. Phase 3 trainer architecture work does NOT begin until
all conditions are resolved.

| Trigger | Detection | Pause action |
|---|---|---|
| **Leakage L1 fail** (`quote_ts > observed_at_15min` count > 0) | §2 weekly probe | Halt. Root-cause the timestamp bug. Invalidate the affected window (see below). |
| **Symbol concentration > 20%** persistent for 2 weeks | §5 probe | Halt. Either (a) operator opens more positions, (b) resolver scope tweaks, or (c) Phase 3 gate revised in arch doc |
| **Sparse-day count ≥ 4 in the 60-day window** | §8 probe | Halt. Investigate Polygon stability; consider extending the 60-day window |
| **Hash collision count > 0** | §9 probe | Halt immediately. Hash determinism is load-bearing for §10/§11 of the readiness doc |
| **Source attribution ≠ `('polygon', 15)`** | §9 probe | Halt. Misconfig or accidental fallback |
| **Quartile drift > 50% sustained for 2 consecutive weeks** | §9 probe | Halt only if data-source change is suspected. Market-regime drift alone is acceptable; document and proceed |
| **No new rows for ≥ 4 hours during RTH** | endpoint `today.row_count` flat | Halt + restart per "Pause / rollback" |

---

## When to invalidate a collection window

A collection window is **invalidated** (cannot be used in Phase 3
training) when one of these is found after-the-fact:

| Discovery | Action on the affected window |
|---|---|
| L1 leakage found inside the window | Delete or quarantine rows in that window (do NOT use in training); record in observation log |
| Resolver rule changed inside the window without version bump | Either (a) bump `resolver_config_version` retroactively and split window, or (b) discard window |
| Backfill rerun with different `LEAKAGE_CUT_DAYS` overlapping the window | Same as above — bump `leakage_rule_version` or discard |
| Feature definition changed inside the window | Bump `feature_schema_version`; split window at the change boundary |
| Polygon endpoint or tier changed inside the window | Bump `polygon_source_assumptions`; record cutover ts; split window |
| Hash collision found in any row of the window | Discard the colliding rows; investigate root cause before resuming |

Discarded rows stay in the DB (do NOT delete; the audit trail must
remain) but are excluded from training via a documented filter in the
trainer's data-loader (Phase 3 responsibility).

---

## How to detect Polygon degradation

Polygon Stocks Starter is generally stable. Degradation modes:

### Mode 1 — Auth / quota
- **Symptom:** `tape.last_error` shows `"401"` or `"403"` strings; or `"You are not entitled to this data."`.
- **Probe:** `curl -s "https://api.polygon.io/v2/aggs/ticker/SPY/prev?apiKey=$POLYGON_API_KEY"` — should return `status: OK`. If 401/403 → key revoked or downgraded.
- **Fix:** confirm key in Polygon dashboard; rotate if compromised; verify tier still Stocks Starter or higher.

### Mode 2 — Rate limit (rare; Starter is "unlimited")
- **Symptom:** `tape.last_error` contains `"429"`.
- **Probe:** check if many concurrent processes hit Polygon (backfill script + live poller simultaneously?).
- **Fix:** serialize. The live poller + backfill should NOT run concurrently. If you ran backfill while live poller was on, the 14 macro+symbol calls per cycle + 11 backfill calls may have stacked.

### Mode 3 — Stale upstream
- **Symptom:** observation rows arrive but `quote_ts` is stuck ≥ 30 min behind clock.
- **Probe:** `SELECT MAX(quote_ts), NOW() AT TIME ZONE 'UTC' - MAX(quote_ts) AS lag FROM intraday_observation;`
- **Fix:** Polygon-side issue. Wait 1 hour; recheck. If persistent, check [polygon.io/status](https://polygon.io/status).

### Mode 4 — Endpoint deprecation / response shape change
- **Symptom:** `tape.last_error` shows JSON parse errors; `feature_hash` distribution suddenly shifts.
- **Probe:** raw curl + visually inspect response shape against
  `apps/api/src/providers/polygon.py:fetch_tape_snapshot()` expected fields.
- **Fix:** code update; bump `polygon_source_assumptions` (per readiness §11); invalidate the cutover-day window.

---

## What to do if symbol concentration spikes

Define spike: top symbol's `rows / SUM(rows)` > 15%.

### Diagnostic steps
1. Confirm spike via §5 probe.
2. Determine WHICH symbol + WHY:
   - Is it an old holding that stays open forever? → expected for a long-hold portfolio
   - Is it a single rec that re-emits daily with same conviction? → resolver behaving correctly
   - Is it a backfill artifact from a longer-history symbol? → backfill spread, not live spread
3. Compute the LIVE-only concentration: `WHERE created_at - observed_at_15min < INTERVAL '5 minutes'` (live writes only). If live-only concentration is fine, the backfill is the imbalance source and is acceptable.

### Remediation options (operator decision)

| Option | When to choose |
|---|---|
| Accept — document in observation log | Concentration is real-portfolio behavior (single large position) |
| Open more paper positions on other symbols | Operator wants to broaden the live coverage |
| Wait — let active-rec rotation balance it out | Concentration is transient (1–2 weeks) |
| Phase 3 trainer enforces 15% per-fold cap | Permanent; punt to trainer-side downsampling |

**Do NOT delete rows.** The concentration is data truth; remediation
happens at trainer time, not collection time.

---

## What to do if sparse days appear

Define sparse: a day's `rows < 30%` of the 14-day median.

### Diagnostic steps
1. Run §8 sparse-day probe to identify the affected date(s).
2. Check the day's clock context:
   - Was it a US market holiday? → expected (markets closed or shortened)
   - Was it a weekend? → expected (poller writes only during cycles)
   - Was Polygon down? → check `tape.last_error` logs for that day in `docker logs compose-api-1`
   - Was the api container restarting all day? → check container uptime
3. Decide if the day should be EXCLUDED from training (`PHASE_3_READINESS.md` §8 final paragraph).

### Remediation

| Cause | Action |
|---|---|
| US holiday / shortened session | Document; include in training (real intraday context) |
| Polygon outage | Run backfill against the specific day: `python -m scripts.backfill_intraday_observations --days 14` (idempotent) and re-probe |
| api container restart | Note the restart timestamp; if the restart was operator-induced (deploy), accept; if crash, debug logs |
| Resolver returned empty set | Check `recommendation` table count for that day; if zero recs, root-cause the EOD recommendation cron |

If after remediation the day is STILL sparse, exclude it from
training (Phase 3 responsibility) and document.

---

## What to do if drift exceeds thresholds

Define drift: per §9 probe, quartile shift `|q1_recent - q1_old| / |q1_old| > 50%`.

### Diagnostic steps
1. Confirm via §9 weekly probe.
2. Identify WHICH feature drifted:
   - `intraday_change_pct` shift → market-regime change (acceptable)
   - `vs_macro_drift_pct` shift → relative symbol behavior shift (interesting; document)
   - `intraday_range_pct` shift → volatility regime change (acceptable)
   - All features shift simultaneously by similar magnitudes → upstream data definition drift (HALT)

### Remediation

| Drift pattern | Action |
|---|---|
| Single feature drifts; others stable | Document as regime change; continue collection; flag for Phase 3 trainer as a per-regime fold concern |
| All features drift simultaneously | HALT writes; suspect Polygon endpoint / tier change. Invalidate the cutover-day window per `PHASE_3_READINESS.md` §10–§11 |
| Drift correlates with operator-induced config change | Bump the relevant version per §11; split window at the change ts |
| Drift correlates with backfill rerun | Same as above; bump `leakage_rule_version` if cut changed |

---

## Rollback / pause procedure

Three escalation tiers. Each is reversible.

### Tier 1 — Pause writes (preserves running tape)

When: any anomaly that suggests writes might be tainted; tape itself is fine.

```bash
# Edit .env: INTRADAY_ML_SHADOW_ENABLED=false
sed -i 's/^INTRADAY_ML_SHADOW_ENABLED=.*/INTRADAY_ML_SHADOW_ENABLED=false/' .env

# Restart api ONLY (tape stays up, but no new intraday_observation rows)
docker compose -f infra/compose/docker-compose.yml --env-file .env up -d --no-deps api

# Verify
curl -s http://localhost:8000/api/intraday-shadow/health | python -c "import json,sys;d=json.load(sys.stdin);print('enabled=',d['enabled'])"
```

To resume: flip `INTRADAY_ML_SHADOW_ENABLED=true`, restart api. No data loss.

### Tier 2 — Quarantine a window (preserves data, excludes from training)

When: window is suspect but data should be retained for audit.

1. Identify start/end ts of the bad window.
2. Add an entry to `docs/research/observation_log/QUARANTINE.md` with `(start_ts, end_ts, reason, version_bump_needed)`.
3. Phase 3 trainer (when it lands) reads this file and excludes the window via a documented filter.
4. No DB changes.

### Tier 3 — Full rollback (worst case)

When: schema/derivation bug requires removing the new layer entirely. Reverse the Phase 2 commits in order. Single env-flag flip handles 90% of cases.

```bash
# Step 1 — pause writes (Tier 1)
# Step 2 — confirm 0 new rows
docker exec compose-db-1 psql -U invest -d investment_platform -c \
  "SELECT COUNT(*) FROM intraday_observation WHERE created_at > NOW() - INTERVAL '1 hour';"

# Step 3 — if rollback required, downgrade migration on DEV only:
# (Per docs/ops/MIGRATION_WORKFLOW.md §B; test DB first if you have that hygiene)
docker exec compose-api-1 sh -c "cd /app && PYTHONPATH=/app \
  alembic -c infra/alembic/alembic.ini downgrade 065_pipeline_run_ledger"

# Step 4 — revert code commits (3 step graph: poller hook, writer, migration)
# See git log --grep="intraday-shadow" for the exact SHAs.
```

**Tier 3 is destructive of `intraday_observation` data. Consider Tier 2 first.**

---

## Escalation criteria

When the operator should stop the routine cadence and treat this as an active incident:

| Criterion | Severity |
|---|---|
| Any §1 hard-gate failure on Phase 3 readiness | High — pauses Phase 3 indefinitely |
| Source attribution ≠ `('polygon', 15)` | High — misconfig; rollback may be required |
| Hash collisions > 0 | High — derivation bug; halt writes |
| Polygon auth/tier failure for > 24h | Medium — collection paused but recoverable |
| Sparse days ≥ 4 in 14-day rolling window | Medium — investigate upstream |
| Symbol concentration > 25% sustained | Medium — Phase 3 gate revision conversation |
| Container restart loop | High — operational, escalate immediately |
| Disk pressure on Postgres volume | Medium — `intraday_observation` is ~6 MB/day; check overall volume |

For each, the response is:
1. Capture state via `/api/intraday-shadow/health` + relevant SQL probes.
2. Write up the incident in `docs/ops/incidents/YYYY-MM-DD_intraday_<topic>.md` (free-form; severity, root cause, timeline, fix, prevention).
3. Tier 1 / Tier 2 / Tier 3 as appropriate.
4. After resolution, append decisions to `PHASE_3_READINESS.md` §11 if a version-bump was triggered.

---

## Decision tree quick reference

```
Weekly Sunday cadence
  │
  ├─► /api/intraday-shadow/health 200? ─── no ─► escalate (container? tunnel?)
  │   │
  │   yes
  │
  ├─► All §2 leakage probes pass? ─── no ─► HALT Phase 3 consideration → Tier 1 + log
  │   │
  │   yes
  │
  ├─► Healthy ranges (table above) all green? ─── no ─► consult matching playbook
  │   │
  │   yes
  │
  ├─► Phase 3 gates progress unchanged for 2+ weeks? ─── yes ─► re-evaluate gate thresholds
  │   │
  │   no
  │
  └─► File observation log + commit
```

---

## Discipline locks — still in force

Do NOT do any of these without a separate operator-approved task:

- ❌ Build a Phase 3 trainer
- ❌ Build a scorer / promotion guard
- ❌ Add intraday recommendation refresh
- ❌ Add intraday trades
- ❌ Mutate confidence in any persistent row
- ❌ Change sizing logic anywhere
- ❌ Add UI surfaces beyond `/ops` `IntradayShadowHealthCard`
- ❌ Add realtime notifications (push, email, slack, etc.)
- ❌ Run "just testing" model experiments outside the Phase 3 framework
- ❌ Hide notebooks / side trainers / off-the-books experimentation

**No more intraday ML work until all `PHASE_3_READINESS.md` §1 hard
gates legitimately pass.** Collection continues automatically; the
operator's only routine task is the weekly cadence in this runbook.

---

*Document originated 2026-05-12 ~17:00 ET as the Phase 2 collection-
phase operations runbook. Read-only. No code lands.*
