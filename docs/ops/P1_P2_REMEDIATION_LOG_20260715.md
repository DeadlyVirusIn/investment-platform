# Stage-B Remediations P-1 + P-2 — Production Remediation Log (2026-07-15)

All VM access via the vm-guard marker workflow (one marker per exact
command); secrets redacted; every command recorded in the session log.
Baseline re-verified before action: local == origin `phase-1/ledger` @
`315c1fb`; prod checkout `1d9b175`; prod DB `109_research_run`; **no
Elite flag present in any prod service env** (only pre-Elite flags, all
false); service images recorded (api `fee27fb5c1a6`, started
2026-07-10T13:22Z; 6/6 healthy).

## P-2 — production checkout drift: **RESOLVED (analysis; no prod edits)**

Full `git status` on the VM shows the drift is wider than the three
audited files (14 modified + untracked admin-era files incl.
`admin_guard.py`, `admin_console.py`, `Admin.tsx`,
`108_app_user_role.py`) — consistent with one mechanism: **the Admin-1/2
/ password-security / redaction era was deployed by copying files onto
the checkout instead of pulling commits.**

Classification of the three audited files (exact diffs + SHA256 captured):

| File | Prod SHA256 (16) | Classification | Evidence |
|---|---|---|---|
| `apps/api/src/auth/identity.py` | `76c58ed490c1a7a4` | **COMMITTED_EQUIVALENT_EXISTS (byte-identical)** | prod hash == committed blob at `315c1fb` (and `e091453`/`52a5e3b`) — the `_MAX_PASSWORD_LEN` DoS guard |
| `apps/api/src/api/admin_observability.py` | `47dd0e1377bb1148` | **COMMITTED_EQUIVALENT_EXISTS (byte-identical)** | prod hash == committed blob — the `require_owner` router guard |
| `apps/api/src/config/__init__.py` | `22a6e864…` | **COMMITTED_EQUIVALENT_EXISTS (strict subset)** | every non-empty line of the live file exists in `phase-1/ledger`'s config; ledger adds only the Elite flag defaults (all False) |

Resolution per policy: canonical implementation preserved (it already
IS canonical); **no live file edits performed**; checkout drift will be
eliminated by the image replacement at the next deploy (images build
from a clean checkout — the running containers already bake the drifted
content, which equals committed content). No hotfix port, no behavior
unique to production. Untracked `.env.bak.*` files remain on the VM
(local backups, not code) — remove during the rebuild window.

## P-1 — orphan `job_run` rows: **RESOLVED (production repaired + verified)**

**Root cause (proven):** all 11 current prod `job_schedule` rows were
created **2026-06-22 — production genesis day** (prod was seeded by
dev-clone). `job_run` history was copied from dev carrying old schedule
UUIDs while `job_schedule` was re-seeded with fresh ids; the bulk copy
inserted under FK bypass (restore/copy path with enforcement disabled),
which is how `job_run_job_schedule_id_fkey` could report
`convalidated=true` over violating rows. Orphans existed since prod
birth; **zero new orphans post-genesis** (verified: 0 rows with
`started_at >= 2026-06-23`).

**Quantification:** 419 rows, 2026-05-07→06-22, statuses 412 success /
2 error / 4 skipped / 1 stale "running" (started ≤06-22, unfinished —
cannot be live: every worker restarted since (Up 5 days) and its parent
schedule doesn't exist). 15 distinct missing parents. `job_run` has NO
dependent tables; dashboards join through `job_schedule` (orphans were
invisible); no billing/audit dependency (pre-genesis dev telemetry).
**Classification: all 419 = SAFE_TO_DELETE**, archived anyway (Option B
lite).

**Clone rehearsal (retained V1 clone, identical data):** archive CSV
(419 rows + header) → guarded transaction (lock_timeout 5s,
statement_timeout 60s, temp approved-ids table built by the genesis-
boundary predicate, expected-count assertion = 419, stale-running
recency assertion, post-delete zero-orphan assertion) → DELETE 419 →
FK drop/re-add with FULL validation → `convalidated = t` → **cleaned
clone dump restores with ZERO errors** (the V1 restore failure is
gone) → app smoke 200s → scheduler-health query sane.

**Production apply (2026-07-15 13:27–13:33 UTC):**
1. Pre-apply verification: prod orphans exactly **419**, new orphans
   **0**; archive CSV exported; **fresh full backup**
   `~/backups/proddb_pre_p1_20260715.dump` (453,912,898 bytes, sha256
   `7586097d…`) — rollback source containing the deleted rows.
2. Applied the **byte-identical clone-tested SQL** (`ON_ERROR_STOP`):
   `SELECT 419 → DELETE 419 → COMMIT → FK re-add (full validation)`,
   exit 0. No service paused (transaction-scoped; new runs have valid
   parents; lock timeout guards).
3. Post: orphans **0**; `convalidated = t` (now genuinely true);
   job_run 107 rows (105 retained + 2 new runs during the window);
   API health 200; all 6 services healthy and untouched; temp files
   removed; archive CSV retained locally
   (`.backups/p1_orphan_archive_prod_20260715.csv`, git-ignored) and
   the backup retained on-VM per policy.

**Rollback (tested path):** restore `proddb_pre_p1_20260715.dump`
(same procedure proven ×3 in V1); CSV manifest is the row-level
reference (error text truncated to 200 chars — full text lives only in
the backup, which is why the backup is the rollback authority).

**Recurrence prevention:** the mechanism was a one-time genesis
procedure, not a code path (no code deletes schedules; no
`session_replication_role` usage in the repo). Prevention = runbook
rule added below + the restore process itself now acts as the integrity
check (a future orphan reintroduction fails the next clone restore
loudly). No noisy production job added.

> **Runbook rule (data seeding/cloning):** never copy child tables
> across environments without their parents; after any bulk copy, run
> the FK orphan audit
> (`SELECT count(*) FROM job_run jr LEFT JOIN job_schedule js ON js.id
> = jr.job_schedule_id WHERE js.id IS NULL`) and
> `ALTER TABLE … VALIDATE CONSTRAINT`-equivalent (drop/re-add) before
> declaring the environment healthy.

## Rebuild readiness

- P-1: orphans zero; FK truly validated; restore proven clean. ✅
- P-2: all drift classified `COMMITTED_EQUIVALENT_EXISTS`; canonical
  `phase-1/ledger` @ `315c1fb` (+ this log) is a superset of deployed
  behavior; image replacement removes checkout drift. ✅
- Migrations remain at 109; every Elite flag absent/off in prod. ✅
- Branch/CI: gateway+authz+paper selection 149 passed; route-scan fix
  `8f199dc` green. ✅

**Verdict: READY TO REBUILD ON DB 109 — FLAGS OFF.**

### Prepared rebuild sequence (execution = separate explicit go)

```
# on the VM, after `git fetch && git checkout <FROZEN_SHA> && git status` is CLEAN:
FROZEN_SHA=<phase-1/ledger head at go-time>
docker tag compose-api:latest            compose-api:rollback-pre-elite-code
docker tag compose-worker-cron:latest    compose-worker-cron:rollback-pre-elite-code
docker tag compose-worker-tickloop:latest compose-worker-tickloop:rollback-pre-elite-code
GIT_SHA=$FROZEN_SHA docker compose --env-file .env -f infra/compose/docker-compose.yml \
  build api worker-cron worker-tickloop web
docker compose --env-file .env -f infra/compose/docker-compose.yml up -d \
  --no-deps api worker-cron worker-tickloop web
# verify: health 200, login/session, recommendations, portfolios,
# paper safety suite spot checks, admin observability owner-404,
# NO /agent|/theses|/admin/inbox|/admin/experiments routes,
# zero writes to (still-absent) Elite tables, no 500s in logs.
# rollback: retag rollback-pre-elite-code -> latest, up -d --no-deps (same services)
```
Constraints: DB stays 109 (no alembic step — Approval Point B separate);
all Elite flags stay unset; caddy/db services untouched; remove
`.env.bak.*` clutter during the window.
