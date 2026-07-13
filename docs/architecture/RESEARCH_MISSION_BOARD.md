# Research Mission Board (Wave 2B)

Owner-only operational overview composed ENTIRELY from existing Research
Inbox and Agent Gateway state. **No migration. No new workflow state
machine. No duplicated source of truth.** Rule set:
`MISSION_BOARD_RULE_SET_VERSION = "mission-board-1"`.

- Service: `apps/api/src/domain/research_inbox/mission_board.py` (pure read)
- API: `GET /api/admin/inbox/mission-board` (owner-gated, flag-mounted)
- UI: `/admin/research-board` (`apps/web/src/v2/pages/AdminResearchBoard.tsx`)
- Flags: reuses `RESEARCH_INBOX_ENABLED` (server) + `VITE_RESEARCH_INBOX`
  (web). Both default OFF. When off: route absent, zero queries, UI absent.

## Source-of-truth mapping (authoritative)

Phase-0 inspection facts this design is pinned to:

1. `research_task`: `status ∈ {open,paused,closed}`, `schedule_expr` is a
   **definition only** (nothing parses or executes it), `follow_up_of_task_id`
   is task-level (populated by Wave 2A), immutable after creation except
   status.
2. `research_report`: append-only versions per task
   (`UNIQUE(task_id,version)`), `review_status ∈ {pending,approved,rejected}`,
   corrections insert `version+1` with `supersedes_report_id`; staleness is
   derived (`service.report_state`, 7-day citation-age boundary =
   `DEFAULT_MAX_CITATION_AGE_DAYS`); citations carry `observed_at` (the only
   market as-of fact); `expires_at` optional.
3. `agent_job` (migration 115, raw SQL — not ORM-mapped): status enum is
   exactly `queued | running | succeeded | failed | cancelled` (no
   "claimed", no "cancellation requested"). Job types are four frozen
   offline **analytics** kinds. **`agent_job` has NO task linkage — there
   is no `task_id` column.** Cancel exists only for `queued` jobs and only
   via the agent-token B-scope route (Bearer), NOT the owner cookie session.
4. There is **no stored fact** for "task execution failed" or "report
   generation failed", and **no owner UI** for gateway jobs.

| Board column | Source facts | Derivation | Navigation target |
|---|---|---|---|
| Queued | `research_task`, absence of reports | task (open/paused) with zero reports, OR all versions rejected ("vN was rejected" context). Sub-states: scheduled (`schedule_expr` set — labelled "nothing runs automatically"), follow-up (`follow_up_of_task_id`), unscheduled | `/admin/research-inbox` |
| Running | `agent_job.status ∈ {queued, running}` | **job cards** (kind `gateway_job`), explicitly labelled "not linked to a research task". Stuck advisory: running > 60 min → freshness `stale`, card STAYS in Running (no failure fact) | none (no owner job UI exists; documented gap) |
| Review needed | latest report `review_status='pending'` | max-version report pending; review age shown | `/admin/research-inbox` (approve/reject there) |
| Delivered | latest report approved, single-version chain, not stale | approved v1, evidence not stale | `/admin/research-inbox` |
| Corrected | any chain row with `supersedes_report_id` | corrected chain whose latest is approved (or rejected-after-approved), not stale, not pending. **Product policy (pinned): a corrected approved chain lives in Corrected, not Delivered** — correction history is the primary story; the card states "current vN is approved" | `/admin/research-inbox` |
| Stale | `report_state` / mission-board-1 thresholds | latest approved but evidence stale, expiry passed, or scheduled-overdue | `/admin/research-inbox` |
| Failed | `agent_job.status='failed'` without newer retry | **job cards**; retry = newer job, same `job_type` + byte-identical `params` (any of queued/running/succeeded) suppresses the failure. `cancelled` is owner-initiated pre-start — NOT a failure, excluded | none |

**No "Blocked" column** (no producer). **Tasks never appear in Running or
Failed** — no producer links a task to an execution. Both are deliberate,
tested deviations from the generic kanban shape.

## Card identity, deduplication, precedence

Task cards: `card_id = task:<id>`; one card per task, always the LATEST
version as current (two versions never become two cards). Job cards:
`card_id = job:<job_uid>`.

Task precedence (pinned in `test_mission_board_unit.py`):

```
review_needed > stale > corrected > delivered > queued
```

Validated scenarios:
- approved v1 + pending v2 → **Review needed** (chain context on the card).
- corrected approved v3 → **Corrected** (policy above).
- stale delivered report → **Stale**, never Delivered; stale corrected
  chain → Stale (stale beats corrected).
- failed old job + running identical retry → retry in **Running**, failure
  suppressed.
- closed task with zero delivered reports → off-board; closed task with an
  approved report stays visible (research remains current).
- single rejected v1 → **Queued** with "v1 was rejected" context (still
  waiting for a usable answer; not Delivered, not Failed — no failure fact).

## Staleness policy (mission-board-1, advisory only)

Vocabulary: `fresh | aging | stale | unknown`.

| Signal | Rule |
|---|---|
| citation evidence | newest `observed_at` age ≤3d `fresh`, ≤7d `aging`, >7d `stale` (7d = the Inbox's own boundary — board and Inbox always agree on stale) |
| `expires_at` only | future → `fresh`; past → `stale` |
| neither fact | `unknown` — delivery time alone NEVER claims freshness |
| scheduled overdue | `schedule_expr` set AND newest approved report older than **14 days** → `stale` ("scheduled task with no report in Nd"). ≥ 2 weekends wide, so weekends can't trip it |
| running job stuck | `started_at` > **60 min** ago → freshness `stale`, stays in Running |
| malformed timestamps | ignored per-citation; no valid facts → `unknown` (never a crash) |

## API contract

`GET /api/admin/inbox/mission-board` — owner-only (`require_owner`, 404
posture), mounted only under `RESEARCH_INBOX_ENABLED`.

Query params (all validated at the route, `q` never reaches SQL):
`column` (enum), `q` (≤64 chars, title/job-type substring), `provenance`
(`generated|human`), `freshness` (enum), `per_column` (1–100, default 30).

Response: `rule_set_version`, `generated_at`, `gateway_enabled`,
`counts` (per column, pre-cap), `columns[]` (`key,title,help,total,shown,
overflow,cards[]`), `board_health` (`complete`, `notes[]` — every cap/
degradation is reported, never silent), `source_freshness` (newest
task/report/job timestamps).

Never returned (pinned by redaction tests): report bodies, raw citation
payloads (only `citation_count`), token secrets/hashes, `request_hash`,
gateway `created_by`, stack traces, emails (labels: `owner` /
`agent:<name>` / `generated`), unbounded text (all fields clipped; status
text ≤160 chars).

## Performance

At most **4 bounded SELECTs** per board build (tasks ≤500, reports ≤2000
for those tasks, follow-up parents by id, jobs ≤200) — pinned by a
statement-counting test (no N+1). All ordering deterministic
(`sort_ts, card_id` tiebreak; review_needed oldest-first, others
newest-first). Real dev dataset measurement: see verification section of
the session report (single-digit-ms queries at current dev volumes). No
cache: bounded queries meet latency targets; if one is ever added it must
be owner-keyed and invalidated on task/report/review/job/follow-up writes.

## Gateway-off / degraded behavior

- `RESEARCH_INBOX_ENABLED=false` → route absent (router not mounted),
  zero queries, UI route not registered.
- `AGENT_GATEWAY_ENABLED=false` → **zero** `agent_job` queries (pinned by
  test), Running/Failed empty, explicit health note "Agent Gateway is off —
  … (tasks are unaffected)"; tasks are never mislabelled failed.
- `agent_job` table missing (pre-115 envs) → same degradation via rollback
  + note, never a 500.

## Follow-up + version-chain handling

Follow-up: task-level (`follow_up_of_task_id`), parent title resolved with
one bounded lookup; depth walk capped at 5 with cycle detection → safe
"relationship unavailable (cycle detected)" label. Follow-up NEVER
completes or moves the parent.

Version chains: latest version is current; `chain` summary carries
`versions`, `prior_retained`, `corrections`, `current_version`,
`current_status`, `last_corrected_by_label`. Distinguished states covered
in tests: pending v1, approved v1, pending corrected v2, approved corrected
v2/v3, rejected corrected version, multiple corrections.

## Security review (threat model outcomes)

- Cross-user leakage: single-owner surface; `require_owner` 404 posture;
  no user-scoped data on the board.
- Report-body leakage: bodies and raw citations never serialized (pinned).
- Token exposure: only the public `token_prefix`; no hash, no created_by.
- Exception leakage: job `error_summary` is already capped server-side
  (type + 200 chars, no stack) and re-clipped to 160; task cards carry no
  provider errors.
- Stored XSS: all board text is bounded server-side and rendered through
  React text nodes (no `dangerouslySetInnerHTML`).
- Enumeration: route is owner-404; card ids are the same already-owner-
  visible task/report/job ids.
- Disabled-feature confusion: explicit `gateway_enabled` + health notes.
- Caching staleness: no cache.
- Cycles/duplicates: cycle-safe follow-up walk; one-card-per-task pinned.
- Board vs Inbox divergence: staleness derives from the same 7-day
  boundary and the same stored facts; no copies stored.
- Action bypass: the board has ZERO mutation surface — every action is a
  link into the existing Inbox.

## Rollback

UI + one GET route + one pure service module, all behind
`RESEARCH_INBOX_ENABLED`/`VITE_RESEARCH_INBOX` (default off). Rollback =
revert the commit(s); no schema, no data, no flag changes needed.

## Production promotion gates

1. `RESEARCH_INBOX_ENABLED` promotion is governed by the existing Inbox
   plan (PRODUCTION_PROMOTION_PLAN) — the board rides it, never leads it.
2. Before enabling in prod: re-measure the 4 queries against prod volumes;
   confirm migration 115 (`agent_job`) present or accept the degraded note.
3. Owner smoke: board renders, counts match Inbox, no body text anywhere
   in the payload (`curl … | grep -c body` = 0).

## Known limitations

- Gateway jobs cannot be tied to tasks (schema fact). A future tracked-
  entity design (Wave 2C, design review first) could add linkage.
- "View gateway job" / cancel actions are absent by design: no owner job
  UI or owner-session cancel route exists today.
- `schedule_expr` is not parsed (definition-only); overdue detection uses
  the 14-day report-age heuristic, not the cron expression.
- Report-level follow-up provenance remains deferred to migration 121.
