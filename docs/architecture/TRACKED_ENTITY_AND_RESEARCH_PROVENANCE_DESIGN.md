# Tracked Entities & Research Provenance — Wave 2C Design Review

**Status: migration-121 scope IMPLEMENTED (2026-07-13) — see
`RESEARCH_EXECUTION_PROVENANCE.md` for the implementation record.
Migration-122 scope (themes, task↔asset, report↔recommendation links)
remains design-only, gated on 121-usage evidence.**
Branch `feature/elite-arthos-provable-ideas @ 82c8b75` (local == origin).
Alembic single head `120_system_posture_event`; dev DB at 120; prod at 109,
untouched. Review roles: Principal Architect, DB Architect, Security,
Data Integrity, Product Strategy, SRE, migration safety.

---

## 0. Phase-0 verified schema truth

Everything below was read from `models.py` / migration sources / the live
dev DB — not from prior docs.

| Table | Facts that constrain this design |
|---|---|
| `research_task` | `follow_up_of_task_id` FK → self **RESTRICT**; status open/paused/closed; `scope` is FREE TEXT ("NVDA,TSM" or theme prose) — no structured asset/theme link; no source-report field |
| `research_report` | **UNIQUE(task_id, version)**; `supersedes_report_id` FK → self RESTRICT; `generated_by` = `agent:<name>` \| owner email \| NULL; **no job/run linkage**; append-only via service |
| `agent_job` | migration **116** (Wave 2B docs said 115 — errata, corrected). **No task column.** `research_run_id` = soft ref, no FK. `job_uid` UNIQUE. Status enum queued/running/succeeded/failed/cancelled; terminal immutable (service). Raw-SQL service layer, NOT ORM-mapped. No delete path exists |
| `agent_job_event` | FK → agent_job **CASCADE** (the only cascade here) — deleting a job would erase its event audit; mitigated by "no job delete path", and this design adds a RESTRICT inbound FK that hard-blocks task deletion from erasing execution history |
| `agent_idempotency` | UNIQUE(token_prefix, idem_key); `kind ∈ {job, draft}`; `ref_id` soft → **draft→report provenance already exists here** (plus `generated_by`) |
| `recommendation` | `asset_id` FK NOT NULL; UNIQUE(asset, model_version, snapshot_hash); already asset-scoped |
| `thesis` | `asset_id` FK nullable; `scope ∈ {company, sector, theme, macro}` with CHECK company⇒asset; already asset-scoped |
| `thesis_evidence` | **the authoritative supports/contradicts structure**: stance CHECK, provenance, review workflow (generated⇒pending, generated⇒source_url), RESTRICT, no delete |
| `thesis_link` | existing **polymorphic** link (target_type CHECK ∈ recommendation/paper_trade/outcome/lesson, id-only, service existence-check, UNIQUE(thesis, type, id)) — the in-repo precedent for what polymorphism costs: no FK, integrity lives in one service |
| `lesson` | hard typed FKs (recommendation RESTRICT, paper_trade SET NULL, thesis RESTRICT), `outcome_ref` soft |
| `research_run` | append-only registry; `parent_run_id` RESTRICT; approvals append-only |
| `paper_position` | `opened_by_recommendation_id` FK SET NULL (migration 100) — Replay's paper linkage |
| `asset` | **UNIQUE(symbol, exchange)** — a symbol alone is NOT unique; `sector` is already a column on asset. Asset is the symbol master |
| D-scope drafts | reports are created **synchronously** by `POST /agent/drafts` — **no job produces a report today**; the four job kinds are offline analytics (calibration/walk-forward/drift/attribution) |

Deletion-behavior inventory: everything trust-relevant in this domain is
RESTRICT or has no delete path; the sole CASCADE is job→events.

---

## 1. Verdict on proposed migration 121 (`tracked_entity` + polymorphic `entity_link`)

**REJECT.**

The proposed `entity_link(target_kind, target_id, relation)` fails the
review checklist on structural grounds, not taste:

1. **Referential integrity impossible.** PostgreSQL cannot FK one
   `target_id` to several unrelated tables. Every guarantee (existence,
   type correctness, no dangling links, deletion behavior) moves to
   service code — and unlike `thesis_link` (one table, one service, four
   target kinds, existence-checked at link time), this table would be the
   integrity point for the *entire* research domain.
2. **Deletion behavior undefinable.** RESTRICT can't be expressed; a
   deleted target silently strands links. The codebase's core rule —
   "no cascade path can silently destroy history" — cannot even be stated.
3. **Relation semantics collapse.** `about` (taxonomy), `supports/
   contradicts` (reviewed evidence claims), `exposed_to` (ambiguous — could
   mean thesis risk, sector membership, or a human tag) are three different
   integrity regimes. `supports/contradicts` ALREADY has a home with a
   review gate (`thesis_evidence`); re-admitting it through an un-reviewed
   generic link would let arbitrary owner links silently become trusted
   evidence — an explicit Wave-1 anti-goal.
4. **Symbol entities duplicate `asset`.** Symbol is not even unique
   (UNIQUE(symbol, exchange)); a `tracked_entity(kind='symbol')` row is a
   second asset master with rename/ticker-change problems asset already
   handles.
5. **Query cost.** Every consumer (Mission Board, Replay, entity page)
   would filter a hot polymorphic table by kind + join per kind — the
   exact "generic joins" degradation the threat model flags.

`thesis_link` survives as-is because it is narrow, existing, and
service-owned. It is a grandfathered precedent, not a license to grow a
second, wider polymorphic table.

---

## 2. Problem decomposition → separate verdicts

The four problems are different integrity regimes and get different
answers. Nothing shares a generic table.

### Problem C — task↔job execution provenance → **GO** (migration 121)

The Mission Board gap with a concrete producer-to-be. Options compared:

- **A. nullable `agent_job.research_task_id` FK — CHOSEN.** One column,
  real FK RESTRICT, one index. A job belongs to at most one task and that
  is a creation-time fact — a link table (B) models a 1:N that cannot
  occur and adds an orphanable row, a second insert in the submit
  transaction, and a join for every Mission Board read. Retries are
  naturally new jobs carrying the same `research_task_id`. The raw-SQL
  service adopts it trivially (one column in the INSERT; `_transition`
  never touches it → immutable-after-insert is service-enforced +
  test-pinned, matching how terminal-status immutability is already
  enforced). Jobs unrelated to research stay NULL. RESTRICT means a task
  with execution history becomes undeletable — desired: provenance
  outlives intent, and it neutralizes the job→event CASCADE risk at the
  task boundary.
- B. `research_task_job_link` — rejected: models nothing A can't, weaker
  (link row can be lost/duplicated independently of the job), more moving
  parts in the submit transaction.
- C. generic entity_link — rejected outright for operational provenance
  (integrity regime argument above).

Creation path: optional `research_task_id` in `POST /agent/jobs` body
(B-scope). Server validates task existence + status ∈ {open, paused}
before insert; unknown → 422. Existence-probe note: gateway tokens are
owner-created in a single-tenant deployment, so task-id probing is
owner-probing-owner; accepted residual, documented. No update path —
association is immutable after insert (test-pinned).

### Follow-up → source-report provenance → **GO** (migration 121)

Wave 2A stores only `follow_up_of_task_id` and echoes the source report
id in the response/audit log (free text — deliberately not parsed back).
The structured link is cheap and the DB can FULLY enforce the hard
requirement "source report belongs to the source task" via a composite FK:

- add UNIQUE index on `research_report(id, task_id)` (id is already PK —
  the composite unique exists only to be an FK target; trivially valid);
- `research_task.source_report_id` VARCHAR(36) NULL;
- `FOREIGN KEY (source_report_id, follow_up_of_task_id) REFERENCES
  research_report (id, task_id) ON DELETE RESTRICT` — a source report can
  never point outside the parent task, by construction, forever;
- `CHECK (source_report_id IS NULL OR follow_up_of_task_id IS NOT NULL)`.

Server-stamped in the existing `POST /admin/inbox/reports/{id}/follow-up`
route (no client field), immutable after creation (task fields have no
update path today; stays that way). Version-exact: the link names the
precise report row (= version) that spawned the follow-up. No free-text
identifiers anywhere.

### Job→report provenance → **DEFER**

No producer exists: reports are born from synchronous D-scope drafts
(provenance already captured — `generated_by='agent:<name>'` +
`agent_idempotency(kind='draft', ref_id=report_id)` records token,
request hash, timestamp) or from humans. None of the four job kinds
writes a report. Adding `research_report.source_agent_job_id` today is a
column nothing can populate honestly. **Design decision recorded for the
future migration that introduces a report-producing job kind:** nullable
`source_agent_job_id` FK RESTRICT on `research_report`, server-stamped in
the runner transaction only, NULL on human corrections (corrections
retain origin history through the supersession chain — v2 does not
inherit v1's job; the chain itself is the origin record), agents cannot
supply it. Not in 121/122.

### Problem A — tracked entities → **REDESIGN**, implementation deferred to migration 122

Kind-by-kind:

- **symbol — REJECTED as an entity kind.** `asset` is the master;
  symbol-alone isn't unique; ticker history is an asset-domain problem.
  Association goes through `asset_id` FKs, never a symbol string.
- **sector — REJECTED as an entity kind (v1).** `asset.sector` already
  exists; sector navigation = group linked assets by their sector column.
  A sector vocabulary table becomes worthwhile only if sectors need
  owner-curated definitions — no evidence yet.
- **theme — the one genuine gap.** Free-text `research_task.scope` is the
  only theme record today. Redesigned slice:
  - `research_theme`: owner-created controlled vocabulary. `key`
    (lowercase slug, immutable, UNIQUE), `display_name` (renameable
    without rewriting history — key is the identity), `created_by`,
    `created_at`, `archived_at` NULL (archive, never delete; archived
    themes stay attached to history but can't be newly attached).
    Global (single-tenant), owner-only creation. Bounded: key ≤ 48
    `[a-z0-9-]`, display ≤ 80.
  - `research_task_theme(task_id FK RESTRICT, theme_id FK RESTRICT,
    created_by, created_at, UNIQUE(task_id, theme_id))` — append/detach
    by owner; detach is allowed (tags are navigation, not provenance).
  - `research_task_asset(task_id FK RESTRICT, asset_id FK RESTRICT,
    created_by, created_at, UNIQUE(task_id, asset_id))` — replaces
    symbol-CSV-in-scope for structured navigation; `scope` text stays as
    display prose.
  - **Task-level, not report-level:** a report chain belongs to one task;
    task tags survive corrections without re-tagging every version.
- macro factor / industry / catalyst / risk — out of scope; catalysts and
  risks already live on the thesis; no producer for the rest.

Why deferred to 122 (not in 121): tagging has real UI + vocabulary-
governance surface and zero Mission-Board/Replay blocking power, while
121's provenance columns are pure integrity wins with existing consumers.
122 proceeds after 121 lands and the owner actually uses execution
provenance — or is dropped if theme navigation never gets pulled.

### Problem B — artifact relationships → mostly ALREADY OWNED, one new link

- report supersedes report — exists (`supersedes_report_id`). No change.
- follow-up from report — GO above.
- thesis/recommendation "about" entity — **redundant**: both already carry
  `asset_id`; theme association for them is NOT created in v1 (no
  workflow needs it; adding it would be diagram-completion).
- report supports/contradicts thesis — **stays in `thesis_evidence`**,
  the reviewed structure. If a research report should count as thesis
  evidence, the owner creates a thesis_evidence row (optionally citing
  the report URL/id in source fields). No parallel un-reviewed channel.
- "exposed_to" — REJECTED: ambiguous semantics (taxonomy vs risk vs
  evidence); each real meaning already has a typed home.

### Problem D — Replay research-report linkage → **GO with conditions** (migration 122)

Replay's standard is "reliable links only — no inference". Asset/theme
association is symbol-level, not decision-level → insufficient. Smallest
honest structure, typed:

- `report_recommendation_link(id, report_id FK → research_report
  RESTRICT, recommendation_id FK → recommendation RESTRICT, note
  VARCHAR(200) NULL, created_by, created_at,
  UNIQUE(report_id, recommendation_id))`.
- Relation is implicitly and only **"context"** — deliberately NO
  supports/contradicts here (evidence claims stay review-gated in
  thesis_evidence). One fixed meaning ⇒ no relation column to misuse.
- Owner-only creation via a typed route; append-only (unlink = no delete;
  if a link was wrong, owner notes it — or we accept delete-with-audit-log
  as the one exception, decided at implementation review; default:
  append-only, no delete).
- Replay renders it as an explicitly labelled **"Owner-linked research
  (human-curated context)"** section: never engine evidence, never a
  conviction input, pending/rejected/superseded state of the report shown
  from existing derivations (linking cannot upgrade review status).
- Links name a specific report row (version). Replay displays
  chain-current truth alongside ("v1 linked; current is v3").

This closes DECISION_REPLAY_TIMELINE's documented research-report
limitation without inference.

---

## 3. Chosen schema (design of record — no migration generated)

### Migration 121 — "research execution & origin provenance" (typed, additive)

```sql
-- 1. task ↔ job (Problem C)
ALTER TABLE agent_job ADD COLUMN research_task_id VARCHAR(36)
    REFERENCES research_task(id) ON DELETE RESTRICT;   -- NULLable
CREATE INDEX ix_agent_job_research_task
    ON agent_job (research_task_id) WHERE research_task_id IS NOT NULL;

-- 2. follow-up ← source report (typed, DB-enforced same-task)
CREATE UNIQUE INDEX ux_research_report_id_task
    ON research_report (id, task_id);                   -- FK target only
ALTER TABLE research_task ADD COLUMN source_report_id VARCHAR(36);
ALTER TABLE research_task ADD CONSTRAINT fk_research_task_source_report
    FOREIGN KEY (source_report_id, follow_up_of_task_id)
    REFERENCES research_report (id, task_id) ON DELETE RESTRICT;
ALTER TABLE research_task ADD CONSTRAINT ck_research_task_source_needs_parent
    CHECK (source_report_id IS NULL OR follow_up_of_task_id IS NOT NULL);
```

Downgrade: drop constraint/column/index in reverse; both columns nullable
⇒ downgrade loses only the new provenance, never other data. Lock
profile: `ADD COLUMN` nullable no-default + `ADD CONSTRAINT` FK = brief
ACCESS EXCLUSIVE + validation scan of small tables (dev: agent_job and
research_task are tens of rows; prod: tables don't exist yet at 109 —
121 runs after 110–120 in sequence). Row counts unchanged (columns only).
Backfill: **none** (below). Ephemeral validation: postgres:16-alpine,
`upgrade head` → `downgrade 120` → `upgrade head`, plus validation
queries: composite-FK rejection of a cross-task report, RESTRICT proof
(task with linked job refuses delete), CHECK proof (source without
parent refused). Dev application (separate approval): backup
`devdb_full_<date>_pre121.dump` first. Prod: stays 109, untouched.

### Migration 122 — "research themes & curated links" (gated: after 121 + owner-workflow evidence)

```sql
CREATE TABLE research_theme (
  id VARCHAR(36) PRIMARY KEY,
  key VARCHAR(48) NOT NULL UNIQUE,          -- immutable slug, ^[a-z0-9-]+$
  display_name VARCHAR(80) NOT NULL,        -- renameable
  created_by VARCHAR(64) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  archived_at TIMESTAMPTZ,                  -- archive, never delete
  CONSTRAINT ck_research_theme_key CHECK (key ~ '^[a-z0-9][a-z0-9-]{0,46}$')
);
CREATE TABLE research_task_theme (
  id VARCHAR(36) PRIMARY KEY,
  task_id VARCHAR(36) NOT NULL REFERENCES research_task(id) ON DELETE RESTRICT,
  theme_id VARCHAR(36) NOT NULL REFERENCES research_theme(id) ON DELETE RESTRICT,
  created_by VARCHAR(64) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_research_task_theme UNIQUE (task_id, theme_id)
);
CREATE TABLE research_task_asset (
  id VARCHAR(36) PRIMARY KEY,
  task_id VARCHAR(36) NOT NULL REFERENCES research_task(id) ON DELETE RESTRICT,
  asset_id VARCHAR(36) NOT NULL REFERENCES asset(id) ON DELETE RESTRICT,
  created_by VARCHAR(64) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_research_task_asset UNIQUE (task_id, asset_id)
);
CREATE TABLE report_recommendation_link (
  id VARCHAR(36) PRIMARY KEY,
  report_id VARCHAR(36) NOT NULL REFERENCES research_report(id) ON DELETE RESTRICT,
  recommendation_id VARCHAR(36) NOT NULL REFERENCES recommendation(id) ON DELETE RESTRICT,
  note VARCHAR(200),
  created_by VARCHAR(64) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_report_recommendation UNIQUE (report_id, recommendation_id)
);
```

Indexes: FK columns (task_id/theme_id/asset_id/report_id/
recommendation_id). Downgrade: drop four tables (link data only — the
artifacts they join are untouched). All-new tables ⇒ no locks on existing
data, no backfill.

### State & immutability matrix

| Object | Mutable? | Create | Delete | FK action | Notes |
|---|---|---|---|---|---|
| `agent_job.research_task_id` | immutable after insert (service + test-pinned; `_transition` whitelist untouched) | gateway submit (server-validated) | no job delete path | RESTRICT | NULL = non-research job |
| `research_task.source_report_id` | immutable after insert | server-stamped in follow-up route | task delete already blocked by report RESTRICTs | composite RESTRICT | DB enforces same-task |
| `research_theme` | display_name renameable; key immutable; archive-only | owner | never (archive) | — | vocabulary, global |
| `research_task_theme` / `research_task_asset` | rows immutable; attach/detach = insert/delete of tag rows (tags are navigation, not provenance — delete allowed, audit-logged) | owner | owner (logged) | RESTRICT both sides | UNIQUE prevents dupes |
| `report_recommendation_link` | append-only, no delete (default; revisit at impl review) | owner | none | RESTRICT both sides | fixed relation "context" |

### Authorization

- All owner routes: `require_owner` (404 posture), same as every
  /api/admin surface.
- Agent Gateway: may set ONLY `research_task_id` at job submit (validated
  existence, immutable); agents can NEVER create theme/asset/
  recommendation links, never touch review status, never publish.
  Generated reports stay pending regardless of any link.
- Entity creation: themes owner-only; NO system-created symbol entities
  (symbol entities don't exist — asset is the master).
- Links cannot upgrade review status, cannot publish, cannot cross users
  (all tables are owner-domain; no user-scoped data involved).

### Threat-model findings (full list assessed)

Structurally eliminated by the typed design: forged target ids, dangling
links, wrong target_kind, relation misuse, cascade-deleting audit
history, job linked to two tasks (single column), link reassignment
(no update path), retries overwriting originals (retries are new rows),
generic-join performance decay. Handled by existing gates: agents forging
evidence links (no route), linking rejected/superseded reports as current
(Replay/Board render state from existing derivations; links never carry
state), correction chains losing provenance (supersession chain IS the
record; corrections never inherit job/run identity). Residual + accepted:
task-id existence probing by owner-created gateway tokens (single-tenant;
422 responses; audit-logged); malicious theme labels / stored XSS
(bounded + regex key, display escaped by React — same posture as every
owner text field); identifier enumeration (owner-only surfaces, 404
posture). Migration backfill errors: eliminated by doing **no backfill**.

### Backfill decision: **NONE**

- task↔job: no structured historical fact exists (job params never
  carried a task id) — nothing to backfill.
- follow-up source report: Wave 2A echoed report ids only into responses
  and audit LOG LINES — parsing logs/free text to invent links is
  explicitly forbidden; historical follow-ups remain unlinked and render
  as today ("Follow-up to <task>" without version).
- recommendations/theses already have asset_id — nothing needed.
- Unlinked history stays visibly unlinked; absence of a link is honest
  state, surfaced as such.

### API design (typed routes only — no generic {target_kind, target_id})

121 scope:
- `POST /agent/jobs` — body gains optional `research_task_id` (B-scope;
  server validates; recorded immutably; audit row unchanged).
- `GET /admin/inbox/tasks/{id}/execution-history` — owner; bounded list
  of that task's jobs (status, timestamps, capped summaries; no
  request_hash/created_by, Mission Board redaction rules reused).
- `POST /admin/inbox/reports/{id}/follow-up` — unchanged shape;
  additionally server-stamps `source_report_id` (no client field).
- Mission Board: task cards gain `jobs` summary (linked active/failed
  counts); linked jobs stop being task-less cards → task-aware Running/
  Failed becomes possible for NEW jobs; old unlinked jobs keep the
  labelled job-card behavior (mission-board rule set bumps to
  `mission-board-2` when implemented).

122 scope:
- `GET/POST /admin/inbox/themes`, `POST .../themes/{id}/archive`
- `POST/DELETE /admin/inbox/tasks/{id}/themes/{theme_id}`
- `POST/DELETE /admin/inbox/tasks/{id}/assets/{asset_id}`
- `POST /admin/recommendations/{rec_id}/research-links` (report_id +
  note) — typed; no generic link endpoint anywhere.
- `GET /admin/inbox/themes/{id}/tasks` — entity navigation (bounded).

### UI design (smallest useful; no graph viz; owner-only)

121: Mission Board task card "1 job running / last failed 2d ago";
follow-up cards gain "from v2"; task execution-history list (attempts +
retries) linked from Inbox. 122: theme chips + asset chips on Inbox task
cards with a picker; theme filter on Mission Board; Replay gains the
"Owner-linked research (human-curated context)" section. No entity
management for beginners — all behind existing owner flags.

### Test plan (exact, for the implementation wave)

Unit: submit-with-task validation (unknown 422, closed-task 422,
immutability — `_transition` cannot alter it); follow-up stamps
source_report_id server-side; board classification with linked jobs
(task-aware Running/Failed precedence vs job cards, mission-board-2);
theme key normalization + archive rules; typed-route input bounds.

PostgreSQL integration: composite-FK rejects cross-task source report;
CHECK rejects source without parent; RESTRICT proofs (delete task with
linked job / linked theme / linked report fails); one job cannot carry
two tasks (single column — assert schema, not just service); duplicate
link UNIQUE collisions (concurrent insert → one winner, loser 409);
agent token cannot reach any link route (authz matrix extension);
generated report stays pending after linking; rejected/superseded report
linked → Replay shows true state; no historical rows gain links after
migration (count before == after; backfill absence pinned); Mission Board
query bound stays ≤4 with the jobs join folded in; payload redaction
(no request_hash/created_by/emails); ephemeral up/down/up; downgrade
drops cleanly with links present (122 tables) / restores 120 shape (121).

Web: execution-history rendering; follow-up "from v2" label with missing-
version fallback; theme picker bounds + archive behavior; Replay curated-
context section labelled human-curated; gateway-disabled unchanged.

### Implementation order

1. Migration 121 (ephemeral-validate → dev backup → dev apply, separate
   approval) → gateway submit + follow-up stamping + execution-history
   route → Mission Board `mission-board-2` task-aware columns → tests.
2. Owner uses it; collect evidence that theme navigation is actually
   pulled.
3. Migration 122 + typed link routes + Replay section (own approval gate),
   or drop 122 if never pulled.

### Hard stops (unchanged)

No prod change (stays 109) · no migration generated/applied in this wave ·
additive-only with tested downgrade when it is generated · no agent
auto-execution · no LLM · no report/audit deletion · every feature behind
default-off flags · smallest auditable diffs.

---

## 4. Final verdicts

| Question | Verdict |
|---|---|
| Proposed 121 (`tracked_entity` + polymorphic `entity_link`) | **REJECT** (replaced by the typed design above) |
| 1. TRACKED ENTITY | **REDESIGN** — theme-only vocabulary + typed task↔theme/task↔asset tables; symbol & sector entity kinds rejected; implementation deferred to migration 122 behind owner-workflow evidence |
| 2. TASK-JOB PROVENANCE | **GO** — nullable `agent_job.research_task_id` FK RESTRICT (migration 121) |
| 3. JOB-REPORT PROVENANCE | **DEFER** — no producing path exists; draft provenance already recorded; design reserved for the migration introducing a report-producing job kind |
| 4. FOLLOW-UP REPORT PROVENANCE | **GO** — `research_task.source_report_id` with composite FK enforcing same-task (migration 121) |
| 5. REPLAY REPORT LINKAGE | **GO (conditions)** — typed `report_recommendation_link`, fixed "context" relation, owner-curated, never evidence (migration 122) |

## Overall: **WAVE 2C DESIGN APPROVED FOR IMPLEMENTATION**

Scope of that approval: migration 121 as designed here (execution + origin
provenance) plus its API/board/tests; migration 122 remains gated on
121-usage evidence and its own approval. Implementation begins only when a
later prompt explicitly authorizes it.
