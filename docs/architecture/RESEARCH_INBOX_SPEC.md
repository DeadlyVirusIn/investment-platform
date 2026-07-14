# Research Inbox — Spec (Sprint 8)

Status: PROPOSAL — no migration generated, no code written, no scheduler
changes. Approval-gated per `CLAUDE.md` (Alembic migrations require explicit
approval). Source context: `docs/research/EXTERNAL_QUANT_AI_REVIEW_2026.md`
§3B (OpenAlice Inbox/workspace concepts — **clean-room, concepts from the
review doc only, zero source contact**), §8 Pillar B, §9 opportunity #10,
§11 M6. Style anchors: `apps/api/src/db/models.py`,
`docs/architecture/RESEARCH_RUN_REGISTRY_SPEC.md` (Sprint 5),
`apps/worker/src/scheduler/tick_loop.py`, `apps/api/src/api/admin_guard.py`.

## 1. Problem

Research today is delivered into chat sessions and memory files: the answer
to "what did we find out about semiconductor capex last month?" lives
nowhere queryable. The Research Inbox makes research **durable**: a
`research_task` states a question once (with scope, tracked symbols, and an
optional schedule); every execution produces a **versioned, immutable
`research_report`** with cited, timestamped evidence, landing in one
reviewable feed. Reports never vanish into chat; corrections never rewrite
history; nothing in this system can act on a portfolio.

Trust posture (binding):

1. **Durable** — every delivered report is a DB row forever.
2. **Immutable once delivered** — corrections create a new version that
   supersedes, never edits, the old one (the `reasoning_audit` append-only
   contract, applied to research).
3. **Honest about age** — every report carries "as of" stamps and turns
   visibly stale; staleness is computed, never hidden.
4. **Human-gated** — a report is *input to a human*, not to the engine.
   Any paper action stemming from a report happens through the existing
   human-driven paper flows, after the report is explicitly reviewed.
   **No autonomous execution exists in this design.**

## 2. Entities

### research_task — the standing question

One row per question the owner wants answered (once, on a schedule, or on
demand). Human-editable while active; archiving preserves it and its
reports forever.

### research_report — the versioned answer

One row per completed execution of a task. `(task_id, version)` is unique
and monotonically increasing. Reports store the rendered body, structured
evidence with citations + timestamps, provenance (which code/model
produced it), and review state. A report is frozen at delivery
(`content_hash` computed server-side); the only mutable fields afterward
are the review fields — and those move only through the review endpoint.

### research_report_evidence — citations as rows

Evidence is not prose buried in the body: each source is a row with
`source_url`, provider, excerpt, `observed_at` (when the underlying fact
was true) and `retrieved_at` (when we fetched it). This extends the
existing `recommendation_evidence` shape (`evidence_type`, `source`,
`summary`, `weight` — `models.py:340`) with the timestamps the review
demands (§5: "provenance (source URL + timestamp) stored with every
evidence row"). Fetched text is **data, never instructions** — evidence
ingestion must never execute or obey content found in fetched documents.

## 3. Schema proposal (CREATE TABLE text only — do not generate migrations without approval)

Revision slots: `109` is reserved by the Sprint 5 `research_run` proposal
and `110`–`111` by the Thesis Ledger proposal (`110_thesis_core`,
`111_thesis_satellites`); this spec proposes **`112_research_inbox`**. House style throughout:
`VARCHAR(36)` uuid4 PK (`models.py _uuid`), `TIMESTAMPTZ` + `now()`
defaults, snake_case singular table names, short public `*_uid`
identifiers, `ON DELETE RESTRICT` everywhere (the ledger never loses
lineage).

```sql
-- 112_research_inbox.sql (PROPOSAL)

CREATE TABLE research_task (
    id                  VARCHAR(36)  PRIMARY KEY,          -- uuid4
    task_uid            VARCHAR(32)  NOT NULL,             -- 'rt_20260712_a1b2c3'
    question            TEXT         NOT NULL,             -- plain-English standing question
    scope_type          VARCHAR(24)  NOT NULL,             -- company|sector|theme|portfolio|market|other
    tracked_symbols     JSONB        NOT NULL DEFAULT '[]'::jsonb,  -- ["NVDA","TSM"] (validated tickers)
    tracked_themes      JSONB        NOT NULL DEFAULT '[]'::jsonb,  -- ["semi capex","GLP-1"]
    schedule_kind       VARCHAR(16)  NOT NULL DEFAULT 'manual',     -- manual|once|recurring
    cron_expr           VARCHAR(64),                       -- recurring only; croniter syntax (job_schedule vocabulary)
    next_run_at         TIMESTAMPTZ,                       -- claim column, same mechanics as job_schedule (§6)
    freshness_hours     INTEGER      NOT NULL DEFAULT 168, -- data older than this ⇒ report shows stale (7d default)
    status              VARCHAR(16)  NOT NULL DEFAULT 'active',     -- draft|active|paused|archived
    created_by          VARCHAR(64)  NOT NULL,             -- app_user.id (server-resolved, never client-supplied)
    follow_up_of_report_id VARCHAR(36),                    -- FK added below (research_report created after this table)
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT uq_research_task_uid UNIQUE (task_uid),
    CONSTRAINT ck_research_task_scope CHECK (scope_type IN
        ('company','sector','theme','portfolio','market','other')),
    CONSTRAINT ck_research_task_schedule CHECK (schedule_kind IN ('manual','once','recurring')),
    CONSTRAINT ck_research_task_status CHECK (status IN ('draft','active','paused','archived')),
    -- recurring tasks must have a cron; manual/once must not
    CONSTRAINT ck_research_task_cron CHECK
        ((schedule_kind = 'recurring') = (cron_expr IS NOT NULL)),
    CONSTRAINT ck_research_task_symbols_size CHECK (pg_column_size(tracked_symbols) <= 8192),
    CONSTRAINT ck_research_task_themes_size  CHECK (pg_column_size(tracked_themes)  <= 8192)
);
CREATE INDEX ix_research_task_status_next ON research_task (status, next_run_at);
CREATE INDEX ix_research_task_created_by  ON research_task (created_by);

CREATE TABLE research_report (
    id                  VARCHAR(36)  PRIMARY KEY,
    report_uid          VARCHAR(32)  NOT NULL,             -- 'rr…' is taken by research_run; use 'rpt_20260712_a1b2'
    task_id             VARCHAR(36)  NOT NULL REFERENCES research_task(id) ON DELETE RESTRICT,
    version             INTEGER      NOT NULL,             -- 1..n per task, server-assigned
    title               VARCHAR(256) NOT NULL,
    summary             TEXT,                              -- 2-3 sentence plain-English answer
    body_md             TEXT         NOT NULL,             -- the report artifact (markdown)
    data_as_of          TIMESTAMPTZ  NOT NULL,             -- max(observed_at) across evidence; the honesty stamp
    data_oldest         TIMESTAMPTZ,                       -- min(observed_at); UI shows the range
    completed_at        TIMESTAMPTZ  NOT NULL,
    expires_at          TIMESTAMPTZ,                       -- optional hard expiry (earnings-dated research etc.)
    generated_by        VARCHAR(64)  NOT NULL,             -- 'job:run_research_tasks' | app_user.id
    model_version       VARCHAR(64),                       -- LLM/model provenance if generated
    git_sha             VARCHAR(64),                       -- code provenance (build_provenance vocabulary)
    research_run_uid    VARCHAR(32),                       -- optional link into the Sprint-5 experiment ledger
    content_hash        VARCHAR(64)  NOT NULL,             -- sha256 over canonical(title,body_md,evidence set); freeze seal
    supersedes_report_id VARCHAR(36) REFERENCES research_report(id) ON DELETE RESTRICT,
    superseded_by_report_id VARCHAR(36) REFERENCES research_report(id) ON DELETE RESTRICT,
    change_summary      TEXT,                              -- "what changed vs the version I supersede" (§7)
    reviewer_status     VARCHAR(16)  NOT NULL DEFAULT 'new',   -- new|reviewed|dismissed
    reviewed_at         TIMESTAMPTZ,
    reviewed_by         VARCHAR(64),                       -- app_user.id
    follow_up_notes     TEXT,                              -- reviewer's notes; the ONLY free-text mutable post-delivery
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT uq_research_report_uid UNIQUE (report_uid),
    CONSTRAINT uq_research_report_task_version UNIQUE (task_id, version),
    CONSTRAINT ck_research_report_review CHECK (reviewer_status IN ('new','reviewed','dismissed')),
    CONSTRAINT ck_research_report_reviewed CHECK
        (reviewer_status = 'new' OR (reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)),
    -- a superseding report must explain itself
    CONSTRAINT ck_research_report_change CHECK
        (supersedes_report_id IS NULL OR change_summary IS NOT NULL),
    CONSTRAINT ck_research_report_body_size CHECK (pg_column_size(body_md) <= 1048576)  -- 1 MiB backstop
);
CREATE INDEX ix_research_report_task     ON research_report (task_id, version DESC);
CREATE INDEX ix_research_report_inbox    ON research_report (reviewer_status, completed_at DESC);
CREATE INDEX ix_research_report_expires  ON research_report (expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE research_report_evidence (
    id                  VARCHAR(36)  PRIMARY KEY,
    report_id           VARCHAR(36)  NOT NULL REFERENCES research_report(id) ON DELETE RESTRICT,
    ordinal             INTEGER      NOT NULL,             -- citation number [1], [2] … in body_md
    source_kind         VARCHAR(24)  NOT NULL,             -- price_data|filing|news|fundamental|internal|other
    provider            VARCHAR(64)  NOT NULL,             -- must be on the provider allowlist at fetch time
    source_url          VARCHAR(1024),                     -- NULL only for internal sources (e.g. our own price_bar)
    excerpt             TEXT,                              -- the quoted fact, ≤ 2 KiB
    observed_at         TIMESTAMPTZ  NOT NULL,             -- when the fact was true (bar date, filing date)
    retrieved_at        TIMESTAMPTZ  NOT NULL,             -- when we fetched it
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT uq_research_report_evidence UNIQUE (report_id, ordinal),
    CONSTRAINT ck_research_evidence_kind CHECK (source_kind IN
        ('price_data','filing','news','fundamental','internal','other')),
    CONSTRAINT ck_research_evidence_excerpt CHECK (pg_column_size(excerpt) <= 4096)
);

-- circular FK resolved after both tables exist (task ⇄ report)
ALTER TABLE research_task
    ADD CONSTRAINT fk_research_task_follow_up
    FOREIGN KEY (follow_up_of_report_id)
    REFERENCES research_report(id) ON DELETE RESTRICT;
```

Deliberate choices:

- **No `body` mutation path exists.** `content_hash` is computed at insert;
  the admin console re-hashes on render and flags mismatch as tamper
  (the `snapshot_content_hash` trick from `V2PromotionSnapshot`).
- **`superseded_by_report_id` is the one non-review field written later** —
  set in the same transaction that inserts the superseding version (both
  sides of the link, or neither).
- **Staleness is derived, not stored**: `stale = now() > data_as_of +
  freshness_hours` (task-level threshold) `OR now() > expires_at`. No
  cron flips a flag; the truth is computable at read time forever.
- Evidence rows are frozen with their report (no UPDATE path at all).

## 4. Report lifecycle & version semantics

```
task: draft → active ⇄ paused → archived        (archive keeps all reports)
report: (insert, frozen) → reviewer_status new → reviewed | dismissed
version: v1 → v2 (supersedes v1) → v3 …          (corrections & scheduled refreshes both bump version)
```

Rules:

1. **Delivery = freeze.** After insert + `content_hash`, no field of the
   report body or evidence ever changes.
2. **Corrections are versions.** A wrong number, a broken citation, new
   information — all produce `version+1` with `supersedes_report_id` set
   and a mandatory `change_summary`. The old version stays readable,
   badged "superseded".
3. **Scheduled refreshes are versions too** — same mechanism, so "what
   changed since last week" falls out of the version chain for free.
4. **Review is metadata.** `reviewer_status/reviewed_at/reviewed_by/
   follow_up_notes` are the only post-delivery writes, via one endpoint,
   identity server-resolved.
5. **Review gates action.** Product rule (enforced in UI and by the
   absence of any API path): nothing in the Inbox can place, stage, or
   suggest-with-one-click a paper trade. The bridge to action is a human
   reading a reviewed report and using the existing paper flows. A
   *future* integration (post-Sprint-10 gateway `D` scope drafts) still
   terminates at human review, never at execution.

## 5. API proposal

Owner-gated first (`Depends(require_owner)`, 404 posture,
`apps/api/src/api/admin_guard.py`); the router graduates to
authenticated-user access (M1 session identity via `resolve_identity`,
`apps/api/src/auth/identity.py` — `arthos_session` cookie; NOT the
Phase-G tier resolver) only after the beta review. Mount:
`APIRouter(prefix="/research", tags=["research-inbox"])` (house prefix
style, cf. `apps/api/src/api/alerts.py`). Fail-closed settings flag:
`RESEARCH_INBOX_ENABLED: bool = False` (matching `RESEARCH_RO_ENABLED`
style in `apps/api/src/config/__init__.py`).

| Method & path | Purpose | Semantics |
|---|---|---|
| `POST /research/tasks` | Create task | Body: question, scope_type, tracked_symbols?, tracked_themes?, schedule_kind, cron_expr?, freshness_hours?. Server assigns `task_uid`, validates cron via croniter, validates tickers against `asset`. `created_by` = resolved identity. |
| `GET /research/tasks` | List tasks | Filters: status, scope_type; each row carries latest report summary + next_run_at. |
| `PATCH /research/tasks/{task_uid}` | Edit/pause/archive | Editable: question, tracked_*, cron_expr, freshness_hours, status. Archived tasks reject further edits (409). Editing cron recomputes `next_run_at` (never to "now" — no immediate mass-fire, the `_heal_null_schedules` rule). |
| `POST /research/tasks/{task_uid}/run` | Manual trigger | Sets `next_run_at = now()` for the dispatcher to claim (§6). Rate-limited: one pending manual run per task (409 if already due). |
| `GET /research/inbox` | The feed | Reports ordered `completed_at DESC`; filters: reviewer_status, stale, task_uid, scope_type. Each row: report_uid, title, summary, badges (§8), data_as_of, version. Paginated, limit ≤ 100. |
| `GET /research/reports/{report_uid}` | Detail | Full body + evidence rows + version chain (uids only) + computed staleness + change_summary. |
| `GET /research/reports/{report_uid}/diff` | What changed | vs `supersedes_report_id` by default, or `?against=<uid>` within the same task. Returns: change_summary, evidence added/removed/updated (by url+observed_at), data_as_of delta, summary text diff (server-computed, UI renders). |
| `POST /research/reports/{report_uid}/review` | Review | Body: reviewer_status ('reviewed'|'dismissed'), follow_up_notes?. Sets reviewed_at/by server-side. Only 'new' → terminal transitions allowed (409 otherwise). |
| `POST /research/reports/{report_uid}/follow-up` | Follow-up task | Body: question + optional scope overrides. Creates a `research_task` with `follow_up_of_report_id` set (provenance chain: question → report → sharper question). Requires the source report be `reviewed` (a human read it before spawning more work). |

Report *creation* has **no public POST**: reports are inserted only by the
worker job (§6) or by an owner-run script through the same internal writer
module (one write path, two entry points — the Sprint 5 pattern).

## 6. Scheduler integration design (design only — NO scheduler implementation in this sprint)

Constraint: reuse the existing exactly-once claim mechanics, don't fork
them. Two options considered:

**Option A — one `job_schedule` row per recurring task.** Rejected:
`job_schedule.name` is a static registry key (`REGISTRY` dict,
`apps/worker/src/jobs/registry.py` — names map to handler functions at
import time); dynamic per-task rows would need a naming convention +
registry indirection + lifecycle GC when tasks are archived. That churn
lives in trust-critical scheduler code for no gain.

**Option B — one dispatcher job + task-level claims (CHOSEN).**

- One new registry entry `run_research_tasks` + one migration-seeded
  `job_schedule` row (cron e.g. `*/10 * * * *`). The row is claimed by
  `_claim_due_job` (`tick_loop.py:42`) exactly like every other job —
  both worker containers race, one wins, P0-5A holds.
- The handler then scans `research_task WHERE status='active' AND
  next_run_at <= now()` and claims **each task** with the same guarded
  UPDATE…RETURNING idiom, advancing `next_run_at` to the next croniter
  slot (or NULL for `once`/manual tasks after firing):

  ```sql
  UPDATE research_task SET next_run_at = :next
  WHERE id = :id AND status = 'active' AND next_run_at <= :now
  RETURNING id
  ```

  Same race-safety proof as the scheduler: a sibling's identical UPDATE
  matches 0 rows. NULL `next_run_at` on active recurring tasks is healed
  by the dispatcher exactly as `_heal_null_schedules` does (P0-5B) —
  computed from the task's own cron, never "now".
- Each task execution writes a `job_run`-style trail: the dispatcher's
  own `job_run` row (existing behavior) plus per-report provenance
  (`generated_by='job:run_research_tasks'`, `git_sha`). Failures follow
  the `_result_reports_failure` contract (`tick_loop.py:30`): a task that
  fails returns `{"status": "error"}` detail in the job summary — never
  a silent success.
- Failed generation writes **no report row** (no half-frozen artifacts);
  the failure is visible in `/v2/admin/jobs` via the existing job_run
  surface, and the task's next_run_at has already advanced (no
  crash-loop refire).

This sprint ships the tables + API + UI only; the registry entry, the
seeded `job_schedule` row, and the dispatcher are a **separate,
approval-gated change** (scheduler code is trust-critical; migration
seeds a schedule row ⇒ DB approval per policy).

## 7. "What changed" between versions

Computed server-side at diff time (never stored beyond `change_summary`):

1. `change_summary` (author/generator-provided, mandatory on supersede) —
   the headline.
2. Evidence delta: added / removed / re-observed (same source_url, newer
   observed_at) citations.
3. `data_as_of` movement and staleness state of each side.
4. Summary/body text diff (line-level; UI renders side-by-side).
5. Comparability banner: diffs across different tasks are refused (400) —
   the UI never implies a comparison the data can't support (Sprint 5
   diff-view rule).

## 8. UX prototype spec — Inbox

Surface: `/v2/research/inbox` (owner-only v1, same guard as `/v2/admin/*`
pages). Beginner-language rules apply the moment this leaves owner-gate
(plain English, no engine vocabulary — UX-5 locks).

**Inbox list**
- Rows: title · task question (muted) · status badge · data_as_of ("as of
  Jul 9") · version chip (v3) · summary line.
- Badges (computed, priority order): `new` (blue) → `reviewed` (green) →
  `stale` (amber, overlays either: "data is N days old") → `superseded`
  (grey, only in task history view, hidden from default feed) →
  `dismissed` (muted).
- Default feed shows only latest versions, unreviewed-first; filter chips
  for New / Reviewed / Stale / All versions.
- Empty state: "No research yet — ask a question" + create-task CTA
  (honest empty states, no fake content).

**Report detail**
- Header: title, "as of" stamp rendered prominently next to the title
  (freshness is a first-class fact, not a footnote), stale warning banner
  when computed-stale: "The data behind this report is older than this
  task's freshness window (7 days). Treat conclusions as unverified."
- Body: markdown with numbered citations; every `[n]` hover/tap reveals
  the evidence row: provider, source link, quoted excerpt, observed_at +
  retrieved_at ("fact from Jul 2, fetched Jul 8").
- Version strip: v1 → v2 → v3 timeline; clicking older versions shows
  them with a persistent "superseded by v3" banner; "What changed" opens
  the §7 diff.
- Review bar (sticky footer): [Mark reviewed] [Dismiss] + notes field.
  Marking reviewed is required before the follow-up button enables —
  reinforcing the human-review gate in the interaction itself.
- **Deliberately absent:** any trade/act button. The report ends in
  understanding, not execution.

**Follow-up flow**
- From a reviewed report: "Ask a follow-up" → modal pre-filled with scope
  from the parent task, empty question field, schedule defaulting to
  `manual`. Creates the linked task (§5); the new task's page shows
  "Follow-up to: <report title>".

## 9. Test plan

- **Unit**: task_uid/report_uid generation; croniter validation (malformed
  cron rejected at API, mirroring the scheduler's don't-claim rule);
  staleness computation (fresh/stale/expired boundaries, DST-safe);
  content_hash canonicalization stability; diff computation (evidence
  add/remove/re-observe).
- **Integration (pg, ephemeral alembic container — MP1S precedent)**:
  migration up/down clean; UNIQUE (task_id, version) race (two inserts,
  one 409/retry); frozen-report write attempts rejected (every non-review
  field); review transitions (new→reviewed, new→dismissed, reviewed→*
  409); supersede transaction sets both link sides atomically;
  change_summary NOT NULL enforced on supersede; RESTRICT on task/report
  delete; follow-up requires reviewed source (409 otherwise).
- **Claim mechanics (design-stage simulation)**: two concurrent fake
  dispatchers against seeded due tasks → each task claimed exactly once
  (the P0-5A test shape, applied to research_task.next_run_at).
- **Guard**: anonymous + authenticated-non-owner → 404 on every route
  (extend `make test-auth` — new gated surface is trust-critical);
  `RESEARCH_INBOX_ENABLED=false` ⇒ router absent.
- **UX**: screenshot proof of badges, stale banner, as-of stamps, version
  diff on dev data before any exposure claim.

## 10. Retention

- `research_task`, `research_report`, `research_report_evidence`:
  **retained indefinitely** — durable research delivery is the product;
  deletion recreates the amnesia problem. Archived tasks and superseded
  versions stay queryable.
- `expires_at` expires *trust in conclusions* (UI badge), never the row.
- Bodies are capped (1 MiB backstop; API enforces 256 KiB first), so
  growth is bounded: at expected volume (a few reports/week) this is
  years from mattering. Revisit policy at ~10k reports.
- Backups ride the existing `make db-backup` discipline; no new artifact
  store (reports are self-contained rows, unlike research_run's dev-disk
  artifacts).

## NON-GOALS

- **No autonomous execution, ever.** No path — API, worker, or UI — from
  a report to a paper trade. Human review is a hard gate, not a default.
- **No scheduler implementation in this sprint** — design only (§6); the
  registry entry + seeded schedule row ship separately, approval-gated.
- **No agent access.** Third-party/agent report drafting waits for the
  Sprint 10 gateway (`D` scope) and still terminates at human review.
- **No web-scale fetching.** Evidence comes from the existing allowlisted
  providers (Tiingo/Polygon/yfinance + filings feeds already integrated);
  no generic URL fetcher is introduced by this spec.
- **No LLM prompt/agent design here** — report *generation* internals are
  out of scope; this spec is the delivery, storage, and review contract.
- **No multi-user collaboration semantics** (comments, assignments,
  sharing) — single-owner review model for v1.
- **No full-text search / pgvector retrieval** — revisit per review §9
  after usage proves the need (image change ⇒ deploy approval).
- **No user-facing (non-owner) exposure in v1** — owner-gated until the
  review flow has run on real reports for a full cycle.
