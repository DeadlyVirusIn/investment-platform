# Session Handoff — 2026-07-15 (end of Elite consolidation + prod rebuild session)

Fresh-context resume doc. Supersedes `SESSION_HANDOFF_20260713.md` (kept
for history; its addendums track this session).

## Where things are RIGHT NOW

- **Canonical branch:** `phase-1/ledger` @ **`237038a`** (local == origin).
  Work in the worktree `C:\Users\kunal\projects\investment-platform-integration`
  (currently checked out on `phase-1/ledger`).
- **PRODUCTION runs `phase-1/ledger @ 7e0af44`** (rebuilt 2026-07-15
  ~22:12–22:36 UTC): api `ae721095227b`, worker-cron `c7da1bbd46c9`,
  worker-tickloop `c6c84a136340`, web recreated on clean source.
  Postgres + caddy untouched. Public: https://app.arthosfinance.xyz (200).
- **Prod DB:** `109_research_run`. **Migrations 110–121 NOT applied**
  (Approval Point B NOT granted). Every Elite/Post-Elite flag OFF/absent.
- **Dev DB** (compose-db-1 @127.0.0.1:54329, db `investment_platform`,
  role `invest`): migration **121**.
- **Prod disk:** root 41G @ 67% (14GB free) after LVM reallocation
  (oled 15G→4G; backup `~/backups/oled_backup_20260715.tar.gz`).
- **Rollback assets (protected):** images
  `compose-{api,worker-cron,worker-tickloop}:pre-elite-rebuild-20260715`;
  `~/backups/proddb_pre_p1_20260715.dump` (sha256 `7586097d…`);
  `~/backups/checkout_drift_20260715.tar.gz`; local (elite worktree)
  `.backups/proddb_v1_20260714.dump` (sha256 `6e3d8be8…`, off-VM copy) +
  `p1_orphan_archive_prod_20260715.csv`. Stopped container `pgv1clone`
  holds `prodclone_v1` at migration 121 (Approval-B rehearsal reuse).

## THE ONE PENDING ITEM (do this first next session)

**48h observation window ends 2026-07-17 22:36 UTC.** After that, run
the completion checklist in
`docs/ops/STAGE_B_PREAPPROVAL_READINESS_20260717.md`: pull both nightly
cycles (23:30 UTC `run_paper_trading` + 07:30 UTC daily loop, Jul 16 +
17), verify user-book isolation (engine ∩ `user:%` = ∅), orphans still
0, `research_run` still 0, Elite routes 404, restarts 0, disk growth
normal. Fill in the doc, commit, push. Green ⇒ **READY FOR APPROVAL
POINT B** (owner decision: apply 110–121 to prod, flags stay off —
runbook: `STAGE_B_PROMOTION_KICKOFF.md` §2–3; clone rehearsal already
V1 PASS).

## What this session shipped (chronology, all pushed)

1. **Wave 2B** Mission Board (`82c8b75`) → **2C design** (`b07f921`) →
   **2C migration 121 implemented, dev-applied** (`f5f619c`).
2. **Wave 3A** Experiment Lab (`dcf6934`, honest INSUFFICIENT_EVIDENCE
   verdict) → **3A.1** evidence reconstruction + replay-pooling fix +
   matched accounting (`fb477e0`); trained adapter BLOCKED (fold depth,
   unlock ≈ late 2026-08).
3. **Consolidation**: review+plan (`a055c63`) → integration branch →
   **PR #26 MERGED** into `phase-1/ledger` (merge `3ad3ca7`; ledger was
   the exact merge base — zero conflicts; 196 commits; tags
   `pre-elite-consolidation-{ledger,elite}`).
4. **Route-scan security test fixed** (`8f199dc` — FastAPI 0.136 prefix
   flattening; vacuity floor + mutation-proof tests).
5. **Stage-B V1 prod-clone rehearsal** PASS WITH REMEDIATIONS
   (`315c1fb`): PG 17.10; 110→121 <8s, no rewrite; downgrade+re-upgrade
   proven; backup-restorability proven.
6. **P-1 RESOLVED IN PROD** (419 orphan job_run rows — prod-genesis
   dev-clone artifact — archived + deleted, FK genuinely revalidated,
   restore now clean) + **P-2 RESOLVED** (drift = committed-equivalent;
   admin-era file-copy deploys) (`7e0af44`).
7. **PRODUCTION REBUILT** on `7e0af44` (`3f1728c` report) — all
   verification green, checkout drift closed at source.
8. **Disk expanded** + 48h watch opened (`237038a`).

## Key invariants/decisions to preserve

- Elite features ship flag-off; promotion = staged per
  `STAGE_B_PROMOTION_KICKOFF.md` approval points B→C→D (lease flag
  first — closes P0-5 in prod; Preflight+Posture coupled; Experiment
  Lab never public).
- Migration 122 (themes/links) gated on 121 owner-usage evidence;
  LightGBM adapter gated on ≥4 folds; Arena premature (one adapter,
  INSUFFICIENT verdicts); replay campaign = separate approval.
- Runbook rule: never copy child tables across environments without
  parents; post-copy FK orphan audit mandatory.
- Prod deploys: clean checkout only, both compose files
  (`-f docker-compose.yml -f docker-compose.prod.yml`) + `--env-file
  .env`; web = Vite dev-server bind-mount (recreate after source
  change); keep exactly ONE rollback image generation.
- vm-guard: write the exact command to a file with the Write tool
  (never inline the VM address in the marker-writing Bash), one marker
  per byte-identical command.
- Test-count claims: per SELECTION with exact command; pre-existing
  failures require paired runs on the clean target.

## Environment quick-start (unchanged from 20260713 handoff)

venv `../investment-platform/.venv/Scripts/python.exe`; source
`/c/Users/kunal/projects/investment-platform/.env` for
`POSTGRES_PASSWORD` (never print). Local elite-code API: uvicorn on
:8002+ (compose :8000/:8001 images are stale for dev testing). Web:
`export VITE_API_PROXY_TARGET=http://127.0.0.1:8002` (+ feature
`VITE_*` flags) then `npx vite --port 5199`; browser tests need
`?skipOnboarding=1&skipMotion=1` and login via a smoke owner
(signup → `UPDATE app_user SET access_role='owner'` → clean up after).

## Doc map (authoritative evidence)

`ELITE_ARTHOS_IMPLEMENTATION_STATUS.md` (ledger of everything) ·
`ELITE_INTEGRATION_REPORT.md` (G1–G8) ·
`STAGE_B_V1_PROD_CLONE_REHEARSAL_REPORT.md` ·
`P1_P2_REMEDIATION_LOG_20260715.md` ·
`PRODUCTION_REBUILD_REPORT_20260715.md` ·
`STAGE_B_PREAPPROVAL_READINESS_20260717.md` (open checklist) ·
`STAGE_B_PROMOTION_KICKOFF.md` (approval points) ·
`TRACKED_ENTITY_AND_RESEARCH_PROVENANCE_DESIGN.md` (122 design, gated) ·
`EXPERIMENT_LAB.md` + validation/unlock reports.

Auto-memory `project_post_elite_plan_20260712.md` carries the same
program log; update IT (not this file) for the next increment.
