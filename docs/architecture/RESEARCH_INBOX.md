# Research Inbox (backend + Wave 2A completeness)

Status: BUILT in dev, flag-off · Flag `RESEARCH_INBOX_ENABLED` (API) +
`VITE_RESEARCH_INBOX` (web) · migrations 112 (`research_task`,
`research_report`) + 117 (`generated_by`) — **no new migration in Wave 2A**.

## What it is

Owner-only research review workflow: tasks deliver reports; generated
reports land `pending` and are never treated as truth until the owner
approves; corrections arrive as new immutable versions; history is never
overwritten. Research never touches recommendations or trades.

## Immutable correction semantics (Wave 2A)

`POST /api/admin/inbox/reports/{report_id}/correct` (owner-only, 404
posture). ALWAYS inserts version N+1 via `inbox_service.correct_report`;
the prior row stays byte-identical (service- and pg-pinned with
`row_to_json` compare). The corrected row links the chain via
`supersedes_report_id`; `report_state` derives `superseded` for older
versions. No inline-edit path exists anywhere (UI or service).

### Review state after correction

Corrections are authored by the authenticated HUMAN owner: the route forces
`provenance="human"`, and the existing service contract records human
reports as **approved with the author as reviewer**. This is the
fail-closed-appropriate outcome here — a correction is a deliberate owner
act, not machine output, so it does not re-enter `pending`; and generated
content can never ride this path (provenance is server-set, not caller-set;
Gateway agent tokens have no session and no correction route — pinned).

### Version chain presentation

Reports group by task into v1 → v2 → v3 …; the latest is actionable, older
versions show a `Superseded` chip + "Supersedes vN — earlier versions
remain available" note (reusing the Wave 1C `formatSupersedesNote` concept).
Rejected versions are retained and labeled, never shown as current; a
generated pending report is never shown as approved; a correction is never
shown as an in-place edit; raw ids are never primary UI.

## Correction concurrency

Version numbers are allocated under the DB `UNIQUE(task_id, version)`
constraint. Two concurrent corrections that both compute version N+1 cannot
both commit — the loser's insert raises `IntegrityError`, which the route
maps to **409** ("a concurrent correction created this version first"). The
route also rejects correcting a non-latest (already superseded) version with
409 up front. No application-only sequencing is relied upon, so no new
migration is required (reported per the mission's race-safety gate).

## Follow-up task provenance (limitation, documented)

`POST /api/admin/inbox/reports/{report_id}/follow-up` creates a task via the
existing `create_task(follow_up_of_task_id=…)`. The structured stored link
is **task-level** (`follow_up_of_task_id` — the schema's supported field).
Report-ID and report-version provenance are echoed in the response and the
bounded audit log but are **not** hidden inside free-text fields to simulate
a relationship. Structured report-level provenance is explicitly DEFERRED to
entity linking (migration 121, Wave 2 tracked-entity slice). The follow-up
never mutates the source report and never launches any agent job.

## Authorization + safety

Every mutating inbox route is `Depends(require_owner)` (session-cookie owner,
404 posture). Agent Gateway tokens carry no session and the gateway exposes
no inbox-correction route (pinned). Correction reason and follow-up fields
are bounded (Pydantic `Field` max lengths); oversized content → 422.
Citations are re-validated by the existing service on every correction
(each needs url + observed_at); stored citations on old versions are
immutable. Audit lines log identities + bounded reason only — never report
content or secrets. Body/citations are rendered as text (React escaping) —
no stored-narrative HTML execution.

## Rollback

Flag off → all inbox routes unmounted, UI surface hidden. No migration to
reverse (Wave 2A added zero schema).

## Production evidence gates

1. Existing promotion plan Stage B (unchanged critical path).
2. Owner review of the correction + follow-up copy.
3. A week of dev use exercising real correction chains.
4. Separate approval for `RESEARCH_INBOX_ENABLED` + `VITE_RESEARCH_INBOX`
   in prod.

## Tests (green 2026-07-13)

Backend: `test_research_inbox_completeness_pg.py` (11) — v1→v2→v3 chains
with byte-identical old rows, superseded-non-latest 409, missing 404,
concurrent-race 409 on the unique constraint, agent-generated corrected by
human (original stays pending), citation re-validation + carry-forward,
bounds, owner-gated + agent-free, follow-up task-level provenance with zero
report mutation / zero job launch, follow-up 404 — plus the legacy
`test_research_inbox_pg.py` (12) still green. Web:
`AdminResearchInbox.completeness.test.tsx` (5) — version chain, immutability
copy, success announcement + focus, follow-up prefill + no-mutation copy,
citation-JSON validation surfaced. Full web suite 265; tsc/eslint/
lint:portfolio/build green.

Live dev drill (owner session): task → generated v1 (pending) → approve →
owner correct v2 (approved, human) → duplicate correct 409 → v3 → follow-up
task (task-level provenance, report unchanged). Fixtures + smoke owner
removed after capture; version-chain + correction-dialog screenshots in
`docs/ux/screenshots/elite-webui/inbox-*.jpeg`.

## Related surfaces

Wave 2B added the **Research Mission Board** (`/admin/research-board`,
`GET /api/admin/inbox/mission-board`) — a read-only operational overview
that sits ABOVE this Inbox (same flags, same owner gate). It aggregates
task/report/version-chain state plus gateway job status into seven columns
and links every action back here; it stores nothing and can never diverge
from Inbox truth. Spec: `docs/architecture/RESEARCH_MISSION_BOARD.md`.
Owner navigation: the Inbox header links to the Board and vice versa;
neither appears in public navigation.
