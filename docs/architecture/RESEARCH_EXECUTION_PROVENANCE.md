# Research Execution & Origin Provenance — Wave 2C Implementation (migration 121)

Implements the migration-121 scope of
`TRACKED_ENTITY_AND_RESEARCH_PROVENANCE_DESIGN.md` (approved design of
record). Migration 122 (themes, task↔asset, report↔recommendation links)
remains OFF-LIMITS and unimplemented.

## Schema (migration `121_research_exec_provenance`)

- `agent_job.research_task_id VARCHAR(36) NULL` — FK →
  `research_task(id)` **ON DELETE RESTRICT**; partial index
  `ix_agent_job_research_task (research_task_id) WHERE NOT NULL`.
  One job belongs to zero or one task; retries are separate jobs carrying
  the same task id; NULL = non-research job. NO backfill — historical
  jobs stay NULL and absence of a link is honest state.
- `research_report` gains `UNIQUE (id, task_id)`
  (`uq_research_report_id_task`) — redundant with the PK, exists solely
  as the composite-FK target below.
- `research_task.source_report_id VARCHAR(36) NULL` — composite FK
  `(source_report_id, follow_up_of_task_id)` →
  `research_report (id, task_id)` **ON DELETE RESTRICT** + CHECK
  `source_report_id IS NULL OR follow_up_of_task_id IS NOT NULL`.
  The database itself makes a cross-task source report impossible and
  keeps a referenced source report undeletable.

## Database-level immutability (triggers)

Route absence and service whitelists are NOT the only line of defense.
Two scoped plpgsql triggers (installed/dropped by the migration; DDL
exported as module constants so the pg test-suite installs the exact
same SQL — no drift):

- `trg_arthos_agent_job_provenance` — any UPDATE changing
  `research_task_id` raises (`set→other`, `set→NULL`, and `NULL→set`
  all refused; only INSERT may populate).
- `trg_arthos_research_task_provenance` — any UPDATE changing
  `source_report_id` raises; once `source_report_id` is set,
  `follow_up_of_task_id` is frozen too. Unrelated updates (status,
  transition stamps) pass untouched.

Triggers were chosen per the design's preference; no architectural
conflict found (the codebase already uses DB CHECKs for invariants and
has no UPDATE path for these columns — the triggers add depth, not
contradiction).

## Migration evidence

- Ephemeral postgres:16-alpine: upgrade 120→121, downgrade→120 (exact
  schema restore verified: zero 121 columns/triggers/functions/
  constraints remain; data rows intact), re-upgrade, plus the 16-point
  behavioral matrix (valid link, unknown-task FK reject, RESTRICT
  deletes, all trigger refusals, composite-FK cross-task reject, CHECK
  reject) — 16/16 PASS.
- Note: alembic revision ids are capped at VARCHAR(32) —
  `121_research_exec_provenance` (29 chars) fits; the longer draft name
  did not.
- Dev apply (backup first): `.backups/devdb_full_20260713_pre121.dump`
  (405 MB, pg_restore --list readable, 1037 entries). Row counts
  before == after (agent_job 0, research_task 2, research_report 4);
  head 120 → 121. **Prod verified untouched at `109_research_run`**
  (read-only SSH check, vm-guard marker flow).

## Gateway submission contract

`POST /api/agent/jobs` (B scope) gains optional `research_task_id`:

- server validates existence + status: **open and paused tasks accept
  jobs** (paused pauses scheduling intent, not manual/agent execution);
  **closed → 422 "research task is closed"**; unknown → 422 "unknown
  research_task_id" (single-tenant: task-id probing is owner-probing-
  owner; accepted, documented residual).
- **Idempotency**: `research_task_id` joins the request fingerprint
  ONLY when present (pre-121 hashes unchanged). Same key + same task →
  replay of the original job with its original link; same key +
  different task (or task vs no-task) → 409 IdempotencyConflict; the
  original job is never modified.
- The queued event carries a bounded provenance identity
  (`task <id8>…`) — never task title/question/scope.
- `get_job` echoes `research_task_id` back to its owner.

## Transition safety

`_transition` updates an explicit whitelist (status, stamps,
summaries) — `research_task_id` is untouchable there; pg tests prove
queued→running→succeeded, failure, and cancellation all preserve the
link, and the trigger blocks any direct SQL mutation besides.

## Follow-up version policy (pinned)

`POST /admin/inbox/reports/{id}/follow-up` server-stamps BOTH
`follow_up_of_task_id = source.task_id` AND `source_report_id =
source.id`. No client-supplied ids. **A follow-up may be created from
ANY retained version** — pending, approved, rejected, or superseded
(the UI offers the action on every retained card; asking a new question
about an old version is legitimate research). Surfaces render the exact
version and say "superseded — a newer version exists" when applicable;
historical follow-ups (pre-121) render "source version was not
recorded" — never guessed, never backfilled.

## Execution-history API

`GET /api/admin/inbox/tasks/{task_id}/execution-history` — owner-only
(404 posture), read-only, deterministic newest-first
(`created_at DESC, job_uid`), hard cap 50 + `overflow`, graceful note
when the gateway store is absent. Payload per attempt: job_uid,
job_type, status, queued/started/finished timestamps, attempt number
(oldest = 1), `is_retry`, token display prefix, result/error summaries
re-clipped to 160. NEVER: request_hash, params payload, token hash,
created_by, stack traces. No cancel action exists on this surface.

## Mission Board `mission-board-2`

Task precedence (pinned in unit+pg tests):

```
running (active linked job)
  > review_needed (latest report pending)
  > failed (latest linked failure not superseded by a newer linked
    attempt in queued/running/succeeded OR any report delivered after
    the failure)
  > stale > corrected > delivered > queued
```

Policy calls (each pinned by a test):
- running retry + pending report → **Running** (in-flight work is the
  truthful state; pending-review context stays on the card);
- failed job + report delivered AFTER it → report's column (the work
  landed; approved → Delivered, pending → Review needed);
- failure AFTER an approved report → **Failed** (latest attempt truth);
- stale report + running job → **Running** (refresh in flight);
- closed task + active linked job → stays on board in Running;
- linked-job retry supersession is **task-linkage based** — parameter
  matching remains ONLY for historical NULL-linked jobs, which keep
  their mission-board-1 standalone job cards ("recorded before task
  links existed; never guessed onto a task").

Task cards gain a bounded `execution` summary (attempts, retries,
active status, last attempt time, last error) and the follow-up block
gains `source_version` / `source_superseded`. One card per task always;
a linked job never also appears as a job card. Query bound: ≤5 SELECTs
(tasks, reports, follow-up parents, jobs, source-report versions) —
pinned.

## Security findings

Structural: cross-task source forged ids impossible (composite FK);
link reassignment/removal impossible (triggers); task deletion cannot
erase execution history (RESTRICT); retries never overwrite originals
(new rows); one job cannot serve two tasks (single column). Gates:
agent tokens cannot reach owner history route (cookie-only
`require_owner`, authz-matrix suite); idempotency-key cross-task reuse
409s; history payload redaction pinned (no request_hash/created_by/
params/token hash). Residuals accepted + documented: owner-token task-id
existence probing (single tenant); stuck-running advisory can fire on
legitimately long jobs (advisory only, never Failed).

## Rollback

`alembic downgrade 120_system_posture_event` (removes triggers,
functions, constraints, columns; verified). Data loss on downgrade =
only the new provenance links. App code degrades: models tolerate the
column's absence only after code revert — roll back code and schema
together (revert commits + downgrade). Dev backup:
`devdb_full_20260713_pre121.dump`.

## Promotion gates (prod stays 109)

1. Rides the Research Inbox / Agent Gateway promotion plan — never
   leads it. Migrations 110–121 apply in sequence during promotion.
2. Before prod flags: re-run the 16-point validation matrix against a
   prod-clone; verify trigger presence; owner smoke of board v2 +
   execution history.
3. `mission-board-2` ships with this code; no separate flag (board
   already rides `RESEARCH_INBOX_ENABLED`).
