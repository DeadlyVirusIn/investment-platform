# Session Handoff — 2026-07-13

Fresh-context resume doc. Everything below is dev-only, flag-off, prod
untouched at migration 109.

## Where things are

- **Repo/worktree:** `C:\Users\kunal\projects\investment-platform-elite`
  (git worktree of `investment-platform`; branch
  `feature/elite-arthos-provable-ideas`).
- **HEAD pushed:** `2975180` (origin has it).
- **Dev DB:** `investment_platform` on `compose-db-1` (127.0.0.1:54329,
  role `invest`), **alembic head = 120**. Prod = 109 (do not touch).
- **Migrations added this program:** 119 `recommendation_preflight`,
  120 `system_posture_event`. Both dev-applied after backups
  (`.backups/devdb_full_20260712_pre119.dump`,
  `.backups/devdb_full_20260713_pre120.dump`).

## Feature flags (all default OFF)

`RECOMMENDATION_PREFLIGHT_ENABLED` · `SYSTEM_POSTURE_ENABLED`
(+`SYSTEM_POSTURE_OVERRIDE` when off) · `REC_DELTA_ENABLED` ·
`DECISION_REPLAY_ENABLED` · `RESEARCH_INBOX_ENABLED` (+web
`VITE_RESEARCH_INBOX=1`) · web `VITE_MEETS_BUY_BAR` (default on).

## Completed this program (Waves 1 + 2A)

| Wave | Feature | Rule set | Migration | Doc |
|---|---|---|---|---|
| 1A | Publication Preflight | pf-2 | 119 | RECOMMENDATION_PUBLICATION_PREFLIGHT.md |
| 1B | Research Safe Mode (posture) | posture-1 | 120 | RESEARCH_SAFE_MODE.md |
| 1C | "What changed?" delta | delta-1 | none | RECOMMENDATION_DELTA_CONTRACT.md |
| 1D | Decision Replay Timeline | replay-2 | none | DECISION_REPLAY_TIMELINE.md |
| 2A | Research Inbox completeness | — | none | RESEARCH_INBOX.md |

All docs under `docs/architecture/`. Research + roadmap:
`docs/research/FINAL_EXTERNAL_REPO_GAP_REVIEW_2026.md`,
`docs/roadmap/POST_ELITE_OPUS_IMPLEMENTATION_PLAN.md`,
`docs/roadmap/ELITE_ARTHOS_IMPLEMENTATION_STATUS.md`,
`docs/roadmap/post_elite_priority_matrix.json`. Elite WebUI:
`docs/ux/ELITE_WEBUI_AUDIT.md` + session report; screenshots in
`docs/ux/screenshots/elite-webui/`.

### Key invariants to preserve

- **Preflight pf-2:** verdict identity = stored fact ids + POLICY BUCKETS
  (provider/price fresh|stale|missing, skew coherent|invalid); the wall
  clock never enters the hash. Read path uses `ensure_current_verdicts_bulk`
  (cap bounds COLD evaluations only — never truncates lookups).
- **Posture:** SAFE pauses NEW publication only; existing ideas/portfolios/
  paper exits untouched. SAFE→NORMAL impossible in one step (owner ack
  gate). Failures → RESTRICTED, 3 consecutive → SAFE, never fake NORMAL.
- **Delta:** stored facts only; historical confidence wording via
  `presentation_for` (WORDING_CUTOVER 2026-07-11); plan-zone proximity
  UNAVAILABLE (plan not persisted).
- **Replay replay-2:** pinned to ONE rec+asset; later rows join the
  lifecycle ONLY with proven continuity (resolved-outcome window OR linked
  open paper position); user isolation server-side (anonymous = zero paper
  events; cache keyed by principal). Hindsight firewall: no engine imports,
  no evaluations, no network, no writes, no LLM.
- **Inbox 2A:** corrections always append vN+1 (prior byte-identical),
  provenance=human→approved, non-latest/race → 409, follow-up link is
  task-level (report-level deferred to migration 121).

### Test truth (state per SELECTION, never one global number)

- Wave-1 focused suite (9 files: preflight/hash/posture/delta/replay,
  unit+pg, one pytest command): **205 passed** (the old "158" in the
  ledger was an arithmetic error; corrected).
- Wave 2A: 11 pg + legacy 12 + 5 web.
- Web Vitest suite: **265 passed**.
- Broader local backend regression is environment-dependent: **147
  pre-existing failures byte-identical on clean HEAD** (path/env issues,
  green in containers) — never attribute them to this work.

## How to run/verify locally

Python venv (has API deps): `../investment-platform/.venv/Scripts/python.exe`.
Source `.env` for `POSTGRES_PASSWORD` — NEVER print it.

Start elite API on :8001 against dev DB (compose api image is an OLD branch —
its flags/routes lag; always run local uvicorn to test elite code):
```
set -a && . /c/Users/kunal/projects/investment-platform/.env && set +a
export DATABASE_URL="postgresql+psycopg://invest:${POSTGRES_PASSWORD}@127.0.0.1:54329/investment_platform"
export AUTH_DISABLED_LOCAL=false RECOMMENDATION_PREFLIGHT_ENABLED=true \
  SYSTEM_POSTURE_ENABLED=true REC_DELTA_ENABLED=true \
  DECISION_REPLAY_ENABLED=true RESEARCH_INBOX_ENABLED=true
../investment-platform/.venv/Scripts/python.exe -m uvicorn apps.api.src.main:app --port 8001
```
Vite web (proxy to :8001): from `apps/web`,
`VITE_API_PROXY_TARGET=http://127.0.0.1:8001 VITE_DEV_TRUST_CENTER=1 VITE_RESEARCH_INBOX=1 npx vite --port 5199`.

Owner-gated routes need a real session: sign up a user via the web
`/account`, then `UPDATE app_user SET access_role='owner' WHERE email=…`
in dev DB. **Clean up smoke users/fixtures afterward** and restore
`local-dev` to `access_role='user'` (append-only audit rows like posture
events legitimately remain).

Backend focused suite:
```
../investment-platform/.venv/Scripts/python.exe -m pytest \
  apps/api/tests/unit/test_publication_preflight.py \
  apps/api/tests/unit/test_preflight_freshness_hash.py \
  apps/api/tests/unit/test_system_posture_unit.py \
  apps/api/tests/unit/test_recommendation_delta.py \
  apps/api/tests/unit/test_decision_replay.py \
  apps/api/tests/integration/test_publication_preflight_pg.py \
  apps/api/tests/integration/test_system_posture_pg.py \
  apps/api/tests/integration/test_recommendation_delta_pg.py \
  apps/api/tests/integration/test_decision_replay_pg.py \
  apps/api/tests/integration/test_research_inbox_completeness_pg.py \
  -q -m "integration or not integration"
```
Web gate (from `apps/web`): `npx tsc --noEmit` · `npm run lint` ·
`npm run lint:portfolio` · `npm run build` · `npx vitest run`.
Ephemeral migration validation: `docker run --rm -d postgres:16-alpine`,
`alembic upgrade head` / `downgrade` / `upgrade head`.

## NEXT: Wave 2B — Research Mission Board

Spec: Opus plan #6. **Pure aggregation, ZERO migration, no new states.**
- Owner surface over EXISTING state: `research_task` (+ `follow_up_of_task_id`
  chains, now populated by 2A), `research_report` review-states + version
  chains, gateway job status (owner path).
- Columns: Queued / Running / Review-needed / Delivered / Corrected /
  Stale / Failed. **Do NOT invent a `blocked` state** — no producer exists.
- Sits ABOVE `/admin/research-inbox`, must not duplicate it. Reuse the
  version-chain grouping + `formatSupersedesNote` from Wave 1C/2A.
- Flag: reuse `VITE_RESEARCH_INBOX` / `RESEARCH_INBOX_ENABLED`.
- Then (separate, later): tracked-entity thin slice — DESIGN REVIEW FIRST;
  proposed migration 121, verify `alembic heads` (dev at 120) before
  generating. Wikilinks + full graph rejected (see gap-review).

## Hard stops (unchanged, every wave)

No deploy · no merge · no prod migration/flags · no Mission Board building
of entity-link tables · no migration 121 without reporting why · no agent
auto-execution/approval · no live trading · no LLM · no new infra service ·
no deleting report/audit history · no editing reports in place · additive
migrations only with tested downgrade · smallest auditable diffs · every
feature behind its own default-off flag.

## Memory pointer

Auto-memory `project_post_elite_plan_20260712.md` holds the running
program log (indexed in MEMORY.md). Update it, not this file, for the next
increment.

## Addendum 2026-07-14 — program state after Waves 2B/2C/3A/3A.1 + consolidation review

HEAD (pushed): see git — waves 2B (Mission Board), 2C design+121
implementation (dev at migration 121), 3A (Experiment Lab, honest
INSUFFICIENT verdict), 3A.1 (evidence reconstruction; replay-pooling fix;
matched accounting; trained adapter BLOCKED on fold depth) are complete.
Consolidation review verdict: READY FOR CONSOLIDATION BRANCH —
phase-1/ledger is the exact merge base (elite strict descendant, zero
conflicts); plan in docs/roadmap/ELITE_MERGE_BACK_PLAN.md awaits explicit
approval. Prod untouched at 109 / 1fb6e28.

## Addendum 2026-07-14 (2) — consolidation executed
Integration branch `integration/elite-arthos-consolidation` created:
merge `acb6eb6` (zero conflicts) + doc `4d26523`; gates G1–G8 green (4
pre-existing test failures paired-run-proven); draft PR into
phase-1/ledger opened, NOT merged. Tags pre-elite-consolidation-{ledger,
elite} pushed. Prod untouched (109/1fb6e28). All Elite flags off.

## Addendum 2026-07-14 (3) — MERGED
PR #26 merged: phase-1/ledger @ 3ad3ca7 (merge commit, parents d4286e7 +
1e56110). Prod untouched (109/1fb6e28); all Elite flags default-off.
Stage-B kickoff checklist: docs/roadmap/STAGE_B_PROMOTION_KICKOFF.md
(PLAN ONLY — approval point A pending). Route-scan test fix pending
(normalization defect, invariant intact).

## Addendum 2026-07-14 (4) — route-scan fix + V1 rehearsal
phase-1/ledger: 8f199dc (route-scan fix) + V1 report commit. V1 verdict
PASS WITH REMEDIATIONS (P-1 job_run orphan FK finding, P-2 prod drift
1d9b175+3 dirty files). Backup .backups/proddb_v1_20260714.dump (sha256
6e3d8be8…, git-ignored); clone container pgv1clone stopped+retained at
migration 121. Approval Point B pending (apply 110-121 to prod, flags
off).

## Addendum 2026-07-15 — P-1/P-2 remediations DONE
P-1: production repaired (419 orphans deleted, FK truly validated,
restore clean; backup proddb_pre_p1_20260715.dump on VM + CSV archive
local). P-2: drift = committed-equivalent (admin-era file-copy deploys);
no live edits; image replacement clears it. Verdict: READY TO REBUILD ON
DB 109 — FLAGS OFF. Prod DB stays 109; no Elite flags; no containers
replaced yet. Log: docs/ops/P1_P2_REMEDIATION_LOG_20260715.md.
