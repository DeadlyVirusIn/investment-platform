# Elite ArthOS — Implementation Status (authoritative inventory)

Branch: `feature/elite-arthos-provable-ideas` @ `d71c379`+consolidation ·
2026-07-11. Single source of truth for what is built, tested, and where it
lives. **Production is at migration 109; nothing Elite is in production.**
Development DB is at **117** (isolated; applied after backups).

## Migration ledger 109–117 (single linear chain, no conflicts)

| Rev | Table/column | Program item | Dev | Prod |
|---|---|---|---|---|
| 109 | `research_run` | Research registry (Honest Numbers) | applied | **applied** |
| 110 | `thesis` (+revisions) | Thesis Ledger | applied* | no |
| 111 | `thesis_evidence/catalyst/risk/link` | Thesis Ledger | applied* | no |
| 112 | `research_task/research_report` | Research Inbox | applied* | no |
| 113 | `lesson` | Learning Loop | applied* | no |
| 114 | `agent_token`, `agent_audit` | Agent Gateway core | applied | no |
| 115 | `paper_trade.execution_cost_json` | Paper-cost audit | applied | no |
| 116 | `agent_job`, `agent_job_event`, `agent_idempotency` | Gateway B/D | applied | no |
| 117 | `research_report.generated_by` | Gateway D | applied | no |

`down_revision` chain verified contiguous 109→117, one head (`117_report_generated_by`),
no branch labels, no duplicate revision ids. (*110–113 were applied to dev
during their build sprints; confirmed present, `alembic current` = 117.)

## Feature inventory

### Agent Gateway — R/P/B/D
- **Spec:** `docs/architecture/AGENT_GATEWAY_V0_SPEC.md` (status: IMPLEMENTING,
  R/P/B/D sections current); `docs/security/NAMED_USER_BETA_AUTHZ.md`.
- **Migrations:** 114, 116, 117.
- **Files:** `domain/agent_gateway/{tokens,audit,jobs}.py`,
  `api/agent_gateway.py`, `api/agent_admin.py`.
- **Flag:** `AGENT_GATEWAY_ENABLED=False` (fail-closed: router + console +
  middleware all absent when off).
- **Routes:** `/agent/whoami|recommendations|recommendations/{id}|portfolio|
  portfolio/trades|jobs|jobs/{uid}|jobs/{uid}/cancel|jobs/{uid}/events|drafts`;
  owner console `/admin/agent-tokens[/{id}/revoke]`.
- **Tests:** `test_agent_gateway_tokens.py` (24), `test_agent_gateway_pg.py`
  (16), `test_agent_gateway_http_pg.py` (~24), `test_agent_jobs_pg.py` (44),
  `test_elite_authz_matrix_pg.py` (23).
- **Dev status:** COMPLETE, flag-off, exercised end-to-end.
- **Prod status:** not deployed.
- **Dependencies:** research_run registry (109), research_report (112),
  paper_service book naming.
- **Rollback:** flag off → surface vanishes; `alembic downgrade` drops tables
  (additive); revoke-all-tokens = one UPDATE.
- **Blockers:** in-memory rate limiter (single-replica); owner-only principal;
  30-day dev audit history; fresh security review before enable.

### Paper-cost audit
- **Spec:** cost model in `execution_costs.py` docstring; Priority 3.
- **Migration:** 115. **Files:** `domain/paper_trading/execution_costs.py`
  (`as_stamp`, non-finite guard), `paper_execution.py` (stamps on fill),
  `db/models.py` (`PaperTrade.execution_cost_json`).
- **Flag:** `PAPER_COST_MODEL_ENABLED=False`.
- **Tests:** `test_paper_cost_audit_pg.py` (6), `test_execution_costs*`.
- **Dev:** COMPLETE (115 applied). **Prod:** no.
- **Rollback:** flag off → NULL stamps, legacy fills; downgrade drops column
  (clone-proven data-preserving). **Blockers:** none technical; ships behind
  its flag.

### Thesis Ledger
- **Spec:** `docs/architecture/*THESIS*`. **Migrations:** 110, 111.
- **Files:** `domain/thesis/service.py` (+ catalyst/risk CRUD),
  `api/thesis.py`. **Flag:** `THESIS_LEDGER_ENABLED=False`.
- **Routes:** public `/theses`, `/theses/{id}`; owner `/admin/theses*`,
  `/admin/catalysts/{id}/resolve`, `/admin/risks/{id}/materialize`.
- **Tests:** `test_thesis_service_pg.py`, slice mount in
  `test_product_slices_pg.py`. **Dev:** COMPLETE. **Prod:** no.
- **Rollback:** flag off → 404; downgrade drops tables. **Blockers:** none;
  promotion is a product decision.

### Research Inbox
- **Migration:** 112 (+117 `generated_by`). **Files:**
  `domain/research_inbox/service.py`, `api/research_inbox.py`.
  **Flag:** `RESEARCH_INBOX_ENABLED=False`.
- **Routes:** owner `/admin/inbox/tasks[/{id}/reports]`,
  `/admin/inbox/reports[/{id}/approve|reject]`.
- **Tests:** `test_research_inbox_pg.py`, slice mount, gateway-D drafts.
  **Dev:** COMPLETE. **Prod:** no. **Rollback:** flag off → 404.

### Learning Loop
- **Migration:** 113. **Files:** `domain/learning/service.py`,
  `api/learning.py`. **Flag:** `LEARNING_LOOP_ENABLED=False`.
- **Routes:** owner `/admin/lessons[/{id}/approve|reject]`.
- **Tests:** `test_learning_loop_pg.py`, slice mount. **Dev:** COMPLETE.
  **Prod:** no. **Rollback:** flag off → 404. Hindsight guard + forced-draft
  are service-enforced.

### SQL-first drift monitor
- **Files:** `domain/monitoring/drift.py` (+ ml/governance drift). No migration,
  no new service. **Tests:** `test_drift_sql_hardening.py` (17) +
  `test_drift_monitor*`. **Dev:** COMPLETE. **Prod:** logic ships with the
  gateway drift_report job or standalone; read-only.

## Reconciliation notes
- No undocumented schema changes: every table/column above maps to a numbered
  migration; `alembic heads` = one; dev `alembic current` = 117.
- The master roadmap (`ELITE_ARTHOS_ROADMAP.md`) is updated so no completed
  item still reads "DESIGN ONLY" / "PROTOTYPE" — see its status column.
- Screenshots/fixtures: sanitized, token prefixes only.

---

## Addendum 2026-07-12 — status corrections + post-Elite pointers

- Branch head is now `e401d53`; **dev DB is at migration 118**
  (118_execution_lease applied 2026-07-11 with backup; prod unchanged at
  109). The header above ("dev at 117") is superseded by this note.
- **Elite WebUI (2 passes) COMPLETE in dev**: audit + all CRITICAL/HIGH and
  M2/M4/M5/M7/M8 fixed; Vitest runner with 241 passing tests;
  `lint:portfolio` green; Research Inbox UI at `/admin/research-inbox`
  (VITE_RESEARCH_INBOX=1). Evidence: `docs/ux/ELITE_WEBUI_AUDIT.md`,
  `docs/ux/ELITE_WEBUI_SESSION_REPORT.md`.
- **Confidence wording**: approved "Meets the buy bar" presentation is now
  the web DEFAULT (`VITE_MEETS_BUY_BAR=0` restores legacy). The
  trust_center.py body sentence "copy change not yet applied" is stale and
  should be updated in the next backend copy pass.
- ~~**Known small backend gap**: `research_inbox.correct_report` has no HTTP
  route~~ — CLOSED in Wave 2A (2026-07-13): `POST /admin/inbox/reports/
  {id}/correct` + `/follow-up`; see `docs/architecture/RESEARCH_INBOX.md`.
- **Post-Elite program** (research → plan complete, implementation NOT
  started): see `docs/research/FINAL_EXTERNAL_REPO_GAP_REVIEW_2026.md`,
  `docs/roadmap/POST_ELITE_OPUS_IMPLEMENTATION_PLAN.md`,
  `docs/roadmap/post_elite_priority_matrix.json`. First build item:
  **Recommendation Publication Preflight** (proposed migration 119 —
  verify `alembic heads` first).

### Publication Preflight (Wave 1A) — 2026-07-12
- **Spec:** `docs/architecture/RECOMMENDATION_PUBLICATION_PREFLIGHT.md`.
- **Migration:** 119 (dev APPLIED after backup
  `.backups/devdb_full_20260712_pre119.dump`; ephemeral up/down/up proven;
  prod untouched at 109).
- **Files:** `domain/publication/{preflight,posture}.py`,
  `api/publication_preflight.py`, seam integration in
  `api/recommendations.py`, ORM `RecommendationPreflight`; web
  `PreflightLimitations` chips (Discover + PickPage), owner console
  `/admin/preflight`.
- **Flag:** `RECOMMENDATION_PREFLIGHT_ENABLED=False` (fail-closed; off =
  byte-identical legacy, pinned by test). Posture seam for Wave 1B:
  `SYSTEM_POSTURE_OVERRIDE`.
- **Tests:** 44 unit + 18 pg + 4 web, all green; unit-sweep failure set
  identical to clean HEAD. Live smoke: truthful HOLD on stale dev ingest;
  READY_WITH_LIMITATIONS publish path with honest chips verified.
- **Prod status:** not deployed; promotion gates in the spec doc.

### Research Safe Mode (Wave 1B) + pf-2 hash fix — 2026-07-13
- **Spec:** `docs/architecture/RESEARCH_SAFE_MODE.md`; preflight doc pf-2
  addendum.
- **Migration:** 120 (dev APPLIED after backup
  `.backups/devdb_full_20260713_pre120.dump`; ephemeral up/down/up incl.
  NULLS NOT DISTINCT idempotency index; prod untouched at 109).
- **Files:** `domain/publication/posture.py` (signals/hysteresis/events),
  `preflight.py` (pf-2 buckets + bulk path), `api/system_posture.py`,
  worker `evaluate_system_posture`, Trust Center posture section; web
  `PostureBanner` (Discover/Today/Pick), owner panel in AdminPreflight.
- **Flags:** `SYSTEM_POSTURE_ENABLED=False` (off = Wave-1A byte-parity,
  override honored, zero reads/writes — pinned).
- **Tests:** 15+26 posture, 15 hash-boundary, Wave-1A suites re-green under
  pf-2 (44+20), 249 web. Live drill: SAFE incident → 0 published + calm
  banner; ack recovery path; read-path 18s→1.18s cold via bulk evaluator.
- **Prod:** not deployed; gates in spec.

### "What changed?" delta (Wave 1C) — 2026-07-13
- **Spec:** `docs/architecture/RECOMMENDATION_DELTA_CONTRACT.md`. Zero
  migration, read-only, rule set delta-1.
- **Files:** `domain/recommendations/delta.py`, `api/recommendation_delta.py`;
  web `WhatChanged.tsx` (PickPage slot-4 section, Discover featured note,
  Briefing strip one-liner, Inbox supersedes helper).
- **Flag:** `REC_DELTA_ENABLED=False` (route absent, responses
  byte-compatible, zero extra queries).
- **Prior rule:** same-asset `(generated_at, id)` strictly-earlier tuple;
  cross-asset/duplicate-timestamp safe (pinned).
- **Consumes persisted preflight/posture/outcome facts only — never
  evaluates, never writes.** Thesis-revision category honestly omitted (no
  stored rec↔revision link); plan-zone proximity unavailable by design
  (plan not persisted) — stored-price movement + outcome barriers cover it.
- **Perf:** 127ms cold / 8ms warm (GE, 447 rows); ≤10 queries/delta.
  Shipped alongside: preflight request cap now bounds cold evaluations
  only (was silently truncating the 500-limit Discover request to 250).
- **Tests:** 39 unit + 12 pg + 1 cap regression + 7 web; all gates green.
- **Prod:** not deployed; gates in spec. WebUI audit M3: CLOSED for
  desk-level + per-idea narrative (plan-zone proximity remains the
  documented residual).

### Decision Replay Timeline (Wave 1D) — 2026-07-13
- **Spec:** `docs/architecture/DECISION_REPLAY_TIMELINE.md`. Zero migration,
  read-only, rule set replay-1. **Wave 1 (trust-control spine) COMPLETE.**
- **Files:** `domain/recommendations/replay.py`, `api/decision_replay.py`;
  web `IdeaHistory.tsx` (+ /today/pick/:symbol/history route), PickPage
  history link, owner replay link in the Preflight console.
- **Flag:** `DECISION_REPLAY_ENABLED=False`.
- **Identity:** replay pinned to one recommendation+asset; cross-asset
  same-symbol immunity pg-pinned. Reliable links only (outcome, preflight,
  posture-at-time, paper via opened_by_recommendation_id/trade stamps,
  lesson.recommendation_id); thesis = asset-level "related" label;
  research reports deferred to Wave 2 (listed unavailable).
- **Isolation:** principal resolved server-side; anonymous zero paper
  events; user A/B + engine-book exclusion + principal-keyed cache pinned.
- **Perf:** 157ms cold / 7ms warm (GE 447 rows); ≤12 queries.
- **Tests (reconciled 2026-07-13 — counts are per SELECTION, never one
  global number):**
  - Wave-1 FOCUSED suite (one pytest command over the nine Wave-1 files:
    `test_publication_preflight.py`, `test_preflight_freshness_hash.py`,
    `test_system_posture_unit.py`, `test_recommendation_delta.py`,
    `test_decision_replay.py` + the four matching `_pg` integration
    files): **205 passed** after replay-2 (**199** at the 1D report; the
    "158" previously written here was an arithmetic error in this ledger,
    not a test change).
  - Web Vitest suite: **260 passed**.
  - Broader local backend regression including shared legacy modules is
    environment-dependent (147 pre-existing failures byte-identical on
    clean HEAD; containers give green totals).
  **Prod:** not deployed; gates in spec.

### Wave 2A — Research Inbox completeness — 2026-07-13
- **Spec:** `docs/architecture/RESEARCH_INBOX.md`. No new migration.
- **Files:** `api/research_inbox.py` (+correct, +follow-up routes),
  `AdminResearchInbox.tsx` (correction + follow-up dialogs, version chain).
- **Flags:** existing `RESEARCH_INBOX_ENABLED` + `VITE_RESEARCH_INBOX`.
- **Correction:** always v N+1, prior byte-identical, human-authored →
  approved (existing contract), superseded-non-latest 409, concurrent race
  409 via UNIQUE(task_id, version), no agent path. Follow-up: task-level
  provenance (`follow_up_of_task_id`); report-level link deferred to
  migration 121; no report mutation, no job launch.
- **Tests:** 11 new pg + legacy 12 + 5 web; web suite 265.
- **Prod:** not deployed. Wave 2B (Mission Board) next.

### Wave 2B — Research Mission Board — 2026-07-13
- **Spec:** `docs/architecture/RESEARCH_MISSION_BOARD.md`. Rule set
  `mission-board-1`. NO migration, no new states, no stored copies —
  pure read aggregation (≤4 bounded SELECTs, pinned) over research_task /
  research_report chains / agent_job.
- **Files:** `domain/research_inbox/mission_board.py`,
  `api/research_inbox.py` (+`GET /admin/inbox/mission-board`),
  `AdminResearchBoard.tsx` (+route `/admin/research-board`, Inbox
  cross-links).
- **Flags:** existing `RESEARCH_INBOX_ENABLED` + `VITE_RESEARCH_INBOX`.
- **Truth decisions (pinned):** agent_job has NO task linkage → Running/
  Failed hold clearly-labelled job cards, tasks never enter them; no
  `blocked` column (no producer); corrected approved chains live in
  Corrected (not Delivered); precedence review_needed > stale > corrected
  > delivered > queued; staleness advisory
  (fresh/aging/stale/unknown — no as-of fact ⇒ unknown, never fresh);
  gateway off ⇒ zero job queries + explicit note.
- **Tests:** 34 unit + 12 pg new (focused selection incl. Wave-1 files:
  261 passed); web +9 (suite 274); tsc/eslint/lint:portfolio/build green.
- **Prod:** not deployed. Next: Wave 2C tracked-entity thin slice —
  DESIGN REVIEW FIRST (proposed migration 121).

### Wave 2C — Tracked-entity & research provenance DESIGN REVIEW — 2026-07-13
- **Design-only wave; zero code, zero migrations.** Doc of record:
  `docs/architecture/TRACKED_ENTITY_AND_RESEARCH_PROVENANCE_DESIGN.md`.
- **Phase-0 verified:** local=origin @ 82c8b75; single alembic head 120;
  dev DB 120; prod 109. Errata fixed: agent_job is migration **116**
  (Wave 2B docs said 115).
- **Proposed polymorphic entity_link REJECTED** (no FK integrity possible,
  deletion behavior undefinable, evidence-gate bypass, symbol duplicates
  asset). Replaced by typed design: migration 121 = execution + origin
  provenance (`agent_job.research_task_id` FK RESTRICT;
  `research_task.source_report_id` composite FK (id, task_id) — DB
  enforces the source report belongs to the parent task); migration 122
  (gated) = `research_theme` vocabulary + `research_task_theme` +
  `research_task_asset` + `report_recommendation_link` (fixed "context"
  relation, owner-curated, never evidence — closes the Replay
  research-report limitation).
- **Verdicts:** tracked entity REDESIGN (theme-only, deferred to 122) ·
  task-job GO (121) · job-report DEFER (no producer exists; drafts already
  have provenance via generated_by + agent_idempotency) · follow-up
  source-report GO (121) · Replay linkage GO-with-conditions (122).
  Backfill: NONE (no log/free-text parsing; history stays honestly
  unlinked). Overall: **WAVE 2C DESIGN APPROVED FOR IMPLEMENTATION** —
  awaits explicit authorization.

### Wave 2C — Migration 121 IMPLEMENTED — 2026-07-13
- **Authorized scope only** (122 untouched). Record:
  `docs/architecture/RESEARCH_EXECUTION_PROVENANCE.md`.
- **Migration `121_research_exec_provenance` APPLIED TO DEV** (backup
  `.backups/devdb_full_20260713_pre121.dump` verified readable; row
  counts unchanged; head 120→121; note: alembic version ids cap at
  varchar(32)). Ephemeral 16-point validation matrix 16/16 (up/down/up,
  FK/CHECK/RESTRICT/trigger refusals). **Prod verified untouched at 109**
  (read-only SSH check).
- **DB immutability triggers** `trg_arthos_agent_job_provenance` +
  `trg_arthos_research_task_provenance` (DDL exported from the migration
  module into the pg suite — zero drift).
- **Gateway:** optional `research_task_id` on POST /agent/jobs (open|
  paused accept, closed 422, unknown 422); task id joins the idempotency
  fingerprint only-when-present (pre-121 hashes unchanged) — same key +
  different task = 409, replay preserves the original link; transitions/
  cancel preserve it (whitelist + trigger).
- **Follow-up:** route server-stamps source_report_id (exact version);
  pinned policy = follow-up allowed from ANY retained version, UI labels
  "from vN (superseded…)" / "source version was not recorded".
- **Execution history:** GET /admin/inbox/tasks/{id}/execution-history
  (owner 404 posture, newest-first, cap 50 + overflow, redacted: no
  request_hash/params/created_by/token hash).
- **Mission Board `mission-board-2`:** linked jobs move their TASK card
  (precedence running > review_needed > failed > stale > corrected >
  delivered > queued; failure superseded by newer attempt OR
  later-delivered report; task-linkage retries), execution summary +
  expandable history on cards, follow-up "from vN" labels; historical
  NULL-linked jobs keep board-1 standalone cards verbatim; ≤5 SELECTs
  pinned.
- **Tests:** 46 unit board + 18 pg board + 20 pg provenance + gateway/
  inbox/authz suites → combined 161 passed; Wave-1 focused + gateway
  http 233 passed (1 pre-existing route-scan failure byte-identical on
  clean HEAD); web tsc/eslint/lint:portfolio/build green, Vitest 281.
- **Live drill (fixtures cleaned, zero residue):** linked queued/running/
  failed, retry suppressing failure, standalone historical job, follow-up
  from superseded v1, live composite-FK + trigger rejections, execution
  history 200/7ms, anon 404; screenshots
  `board2-desktop-linked.png` + `board2-mobile-running.png`.
- **Prod:** untouched (109). Migration 122 evidence gate: unchanged.

### Wave 3A — Experiment Lab harness — 2026-07-14
- **Spec:** `docs/architecture/EXPERIMENT_LAB.md`; validation:
  `docs/research/EXPERIMENT_LAB_VALIDATION_REPORT.md`. **NO migration**
  (research_run registry verified sufficient). Flags
  `EXPERIMENT_LAB_ENABLED` + `VITE_EXPERIMENT_LAB` (default OFF).
- **Files:** `domain/evaluation/lab.py` (spec canon+hash, dataset
  fingerprint, calendar-eval-1 folds, stored_rules_engine adapter,
  benchmarks/costs via apps/ml/lab reuse, lab-gates-1 verdict,
  RegistryClient persistence, reproduce-as-new-linked-run),
  `api/experiments.py`, `AdminExperiments.tsx` (+route).
- **Decisions:** statsmodels NOT added (Wilson CIs via closed form;
  hypothesis testing = Wave 3A.2); Optuna NOT added (no sweep; nested
  validation required before any); synchronous bounded execution
  (0.5s real run — no second scheduler); historical_label EMPTY on dev
  ⇒ trained-model path data-blocked, stored-decision evaluation is the
  v1 adapter.
- **Real evidence (runs retained in dev registry):** top-30 universe →
  2,217 resolved / 336 censored / 3 folds; hit 57.9% BUT conviction AUC
  0.41–0.50 and base-rate Brier wins 0/3 folds; ECE 0.11+ in 2 folds;
  net 30d +2.8% at expected cost vs buy&hold +111.9% same-window.
  **Verdict INSUFFICIENT_EVIDENCE** (honest negative). Reproduction:
  metric hash EXACT match, original byte-identical.
- **Tests:** 24 unit + 14 pg new; combined Wave-1+2+3 selection **371
  passed**; web +6 (Vitest 287), tsc/eslint/lint:portfolio/build green.
- **Prod:** untouched (109).

### Wave 3A.1 — Historical evidence reconstruction — 2026-07-14
- **Investigation-first; docs:** HISTORICAL_LABEL_ROOT_CAUSE.md,
  OUTCOME_RECONSTRUCTION_AUDIT.md,
  EXPERIMENT_LAB_EVIDENCE_UNLOCK_REPORT.md (+ validation-report
  addendum — originals never rewritten). Backup
  devdb_full_20260714_pre3a1.dump before any write.
- **Root cause A (historical_label empty):** writer has ZERO callers
  (never scheduled; BP-era artifact from a prior DB era) AND point-in-
  time snapshots only exist from 2026-04-22. Rebuilt via the ORIGINAL
  pipeline: 1,601 rows / 36 days / balanced classes.
  **Trained-adapter gate: BLOCKED (≤2 folds < 4)** — no LightGBM
  adapter built; unlock ≈ late 2026-08 via snapshot accumulation.
- **Root cause B (2024-H2/2025 gap):** NOT an outcome defect —
  recommendations were never generated for those windows (replay-era
  coverage). Outcome backfill scope = 49 immaterial rows → **no inserts,
  existing outcomes byte-untouched**. Real defect found instead:
  Wave 3A POOLED up to 8 replay model_version variants (duplicate
  correlated samples).
- **Lab lab-1.1:** model_versions scoping in the hashed identity +
  CRITICAL replay-pooling warning + matched event-horizon benchmark
  (comparable accounting: per-event same-asset same-horizon same-entry).
- **Re-runs (4 new, originals retained):** pooled matched excess +0.18%
  mean / median ≈ 0 / share-beating CI 49.7–54.3% (indistinguishable
  from no edge); live-engine-only (0.1.0) +0.82% excess, 66% share
  (CI 57–74%) but 1 fold/109 events → INSUFFICIENT_EVIDENCE; 2024/2025
  replay eras NEGATIVE excess (−0.60%); reproduction hash EXACT.
- **Tests:** lab 42 green (+ pooling/scoping/matched pg pins); Vitest
  287; tsc/eslint/lint:portfolio/build green. Prod untouched (109).

### Program consolidation review — 2026-07-14 (PLAN ONLY)
- **Docs:** `ELITE_PROGRAM_CONSOLIDATION_REVIEW.md` +
  `ELITE_MERGE_BACK_PLAN.md`. Nothing merged/rebased/deployed/tagged.
- **Topology:** `phase-1/ledger` @ d4286e7 IS the merge base (0 ahead) —
  elite @ fb477e0 is a strict descendant (+195 commits, 423 files,
  +56,262/−955). **Zero conflicts by construction.**
- **Hotfix:** dc36058 is an elite ancestor; elite carries the P1
  user-book fix (7876124) + lease/fencing hardening; mvp's 52a5e3b is a
  duplicate cherry-pick (superseded post-merge, not deleted).
- **Prod line:** release/stage-b1-* content (redaction + ingest
  contracts) byte-contained in elite; one release-only artifact
  (POLYGON_CREDENTIAL_INCIDENT.md) to copy at integration.
- **Migrations 101–121:** single linear head, additive-only, downgrades
  present; prod verified at 109 (2026-07-13 read-only check).
- **Deps:** Python unchanged (no statsmodels/Optuna/AGPL); web adds test
  tooling only. No Elite flag in any deployment template.
- **Verdicts:** conflicts ZERO · hotfix NO CONFLICT · compatibility
  matrix has no blocked state (G6 feature-off parity + G7 code-on-109
  are the required new proofs) · risk **LOW** · strategy = --no-ff merge
  via short-lived `integration/elite-arthos-consolidation` ·
  **READY FOR CONSOLIDATION BRANCH** — execution awaits explicit
  approval.

### Consolidation EXECUTED — 2026-07-14 (Integrated on review branch; PR pending)
- Tags `pre-elite-consolidation-ledger` (d4286e7) + `-elite` (a055c63)
  pushed. Branch `integration/elite-arthos-consolidation`: merge commit
  `acb6eb6` (--no-ff, ZERO conflicts; merge tree OID == elite tree OID —
  identity-proof) + `4d26523` (release-line incident doc carried).
- Gates: G1 PASS (ephemeral 109→121→109→121 with data-survival; single
  head; ORM ⊆ migrations) · G2 PASS w/ 4 pre-existing failures
  (paired-run proven: 480+12+63 passed) · G3 PASS (tsc/eslint/
  lint:portfolio/build/Vitest 287) · G4 PASS (zero credential findings)
  · G5 PASS (rec endpoint parity 66-87ms vs 65-70ms) · G6 PASS WITH
  EXPLAINED BASELINE DIFFERENCES (18 inherited always-on routes; zero
  Elite routes; 2 inert registry entries; zero Elite writes; identical
  rec sets +name/sector from approved UX commits) · G7 PASS (boots on
  109-only DB, flags off, zero errors) · G8 this report.
- **NOT merged into phase-1/ledger. NOT deployed. Prod at 109/1fb6e28.**
  Evidence: `docs/roadmap/ELITE_INTEGRATION_REPORT.md`.
