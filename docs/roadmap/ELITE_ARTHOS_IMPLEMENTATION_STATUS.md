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
- **Known small backend gap**: `research_inbox.correct_report` has no HTTP
  route (service + pinned tests exist) — scheduled Wave 2 of the post-Elite
  plan.
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
- **Tests:** 15 unit + 12 pg + 4 web; suite totals 158 backend Wave-1 /
  260 web. **Prod:** not deployed; gates in spec.
