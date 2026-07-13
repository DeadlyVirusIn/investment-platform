# Decision Replay Timeline (Wave 1D)

Status: BUILT in dev, flag-off · zero-migration, read-only · rule set
`replay-1` · Branch `feature/elite-arthos-provable-ideas`.
Companions: pf-2 preflight, Research Safe Mode, delta-1 contract.

## Purpose

Reconstruct, for one idea, what ArthOS believed, what evidence/risks were
visible, how it was published, the system's health posture, the user's own
practice activity, the resolution, and any recorded lesson — from immutable
stored artifacts only. Hindsight rewriting is impossible by construction.

## Pinned identity rule

Public flow: symbol resolves to the latest recommendation ONCE
(`resolve_pinned`, `(generated_at DESC, id DESC)`), then the entire replay
is pinned to that recommendation id + asset id. A later recommendation on a
DIFFERENT asset reusing the symbol never changes an existing replay
(pg-pinned); it merely becomes the target of NEW symbol resolutions. The
owner route accepts the exact recommendation id.

## Lifecycle boundary (from inspected data)

Start = pinned generation. Updates = later rows for the SAME asset,
summarized through the Delta service (no separate rules; meaningful+ only,
capped at 6), bounded by the pinned row's outcome resolution
(`barrier_first_touch_at`) when it exists. Terminal states: target (1),
exit (-1), time (0) barriers; otherwise `open`. Unrelated later ideas are
never merged by symbol; with nothing reliable the replay stays conservative
for the pinned row alone.

## Artifact links (Phase-0 verified)

Reliable (stored identifiers): `recommendation_outcome.recommendation_id` ·
`recommendation_preflight.recommendation_id` · posture event current at the
verdict's created_at (temporal, labeled as applicable-at-time) ·
`paper_position.opened_by_recommendation_id` + `opening_trade_id` /
`closed_by_trade_id` · `paper_trade.recommendation_id` +
`execution_cost_json` (migration-115 stamp) · `lesson.recommendation_id`.
Asset-level only: `thesis.asset_id` → included ONLY as "Related asset
thesis … not necessarily the exact thesis used for this decision"
(partial). Unavailable: research reports (no structured link — deferred to
Wave 2 entity linking; listed in `unavailable_sections`, never inferred
from symbol text).

## Event model + ordering

Events: stable public key (no UUIDs), type, occurred_at, title,
beginner-safe summary (server templates only), honesty label
(EvidenceBadge vocabulary), source, detail_status (complete | partial |
unavailable | not_evaluated | not_recorded), public-safe details.
Ordering: occurred_at → semantic priority (generated 0, preflight 1,
posture 2, update 3, paper 4, outcome 5, thesis 6, lesson 7 — same-timestamp
rows are common in history; order pinned by test) → stable key. Cap 40.

## Historical wording

Reuses the Delta service's `presentation_for`: pre-cutover rows render
"high/medium/low confidence"; post-cutover High/Medium render "meets the
buy bar". History is never re-labeled with today's copy (unit-pinned).

## Completeness model

Absence is reported as absence: `completeness` = complete | partial with a
plain note ("This idea predates publication-preflight recording."), a
`unavailable_sections[]` list, and per-event detail_status (e.g.
"Execution-cost detail was not recorded for this practice trade."). Absence
never renders as success or health.

## User isolation (security-critical)

Practice events come ONLY from the authenticated principal resolved
server-side from the session cookie (no caller parameter), matched via the
established `user:<uid>:...` book naming + stored recommendation links.
Anonymous → zero paper events. Another user's or the engine/demo book's
activity never appears (pg-pinned: user A vs user B, anonymous, engine
book). Cache keys include the principal + owner flag + all mutable-artifact
identities, so cross-principal sharing and stale replays after a new
trade/verdict/posture/outcome/lesson are impossible by construction
(mixed-principal cache test).

## Hindsight firewall

`domain/recommendations/replay.py`: stored rows only; no scoring-engine
imports, no `evaluate_and_record`/`run_preflight` calls, no network, no
current-price lookups, no INSERT/UPDATE/DELETE, no LLM — source- and
behavior-pinned (row-count invariance across a full timeline build).

## API

Public `GET /api/recommendations/{symbol}/timeline` (flag
`DECISION_REPLAY_ENABLED`, default off → routes absent, zero queries, no
links rendered). Payload: symbol, recommendation_as_of, lifecycle_status,
completeness(+note), events[], unavailable_sections[], sections_present,
user_scoped, generated_at — never UUIDs/asset ids/db ids/snapshot hashes/
git SHAs/raw score maps/raw checks/raw signals/emails/trade ids (pinned
with real ids).
Owner `GET /api/admin/replay/{recommendation_id}` (require_owner 404
posture): adds exact recommendation identity, preflight rule-set version +
full ordered checks, draft/rejected lessons. Still no secrets, provider
errors, or other users' paper activity (cross-user support access would be
a separate audited workflow — not built).

## Performance (measured, real dev data)

GE (447-row asset history): anonymous timeline **157 ms cold / 7 ms warm**;
≤12 queries per build (listener test), no N+1 (single positions join,
single later-rows scan). Bounded events (40) + updates (6).

## Frontend

`/today/pick/:symbol/history`: paper-only disclosure, lifecycle +
completeness StatusPanel, semantic `<ol>` timeline with EvidenceBadge
labels, native `<details>` per event, "Not recorded" section, back-link.
PickPage "See this idea's full history →" renders only when a replay
exists (flag on + recorded lifecycle). Owner deep link ("Owner replay →")
from the Preflight console verdict cards. Mobile 390 px verified; no
horizontal scroll; no animation.

## Rollback

Flag off → routes unmounted, page fails closed to a calm unavailable
state, PickPage link absent. Nothing to migrate.

## Production evidence gates

1. Existing promotion plan Stage B (unchanged critical path).
2. Preflight + Safe Mode + Delta promoted first (replay renders their
   persisted facts; without them it stays honestly partial).
3. Owner copy review of every event template + a week of dev replays over
   real nightly generations.
4. Separate approval for the prod flag.

## Tests (green 2026-07-13)

15 unit (every category incl. cost-stamp present/absent, historical
wording, pre-preflight unavailability, owner-vs-public projections,
same-timestamp semantic ordering pin, caps, redaction, firewall source
pins) · 12 pg (pinned identity vs cross-asset same-symbol, update
window scoping, same-timestamp siblings, user A/B/anonymous isolation,
engine-book exclusion, cost stamps, persisted preflight/posture
association with row-count invariance, thesis/lesson flag + review
gating, no-writes + ≤12-query bound, real-id redaction, flag-off
structure) · 4 web (flag-off state, partial pre-preflight timeline,
complete resolved ordering, no raw diagnostics). Full web gate 260
vitest + tsc/eslint/lint:portfolio/build green.

---

## replay-2 addendum (2026-07-13) — lifecycle continuity fix (HIGH)

replay-1 defect: with no terminal outcome, later same-asset rows entered
the pinned lifecycle unbounded — unrelated later idea cycles could be
misrepresented as updates to the original idea.

replay-2 separates four concepts explicitly:
* **Pinned identity** — one recommendation id + asset id, immutable
  (unchanged from replay-1).
* **Lifecycle continuity** — later rows enter ONLY when PROVEN by stored
  facts, in hierarchy: (1) an explicit recommendation supersession/
  predecessor link — none exists in the schema (verified), skipped;
  (2) the pinned row's RESOLVED outcome (`barrier_first_touch_at`) bounds
  a run-to-resolution window; (3) a paper position with
  `opened_by_recommendation_id` = pinned rec that is open at the later
  row's generation (closed_at bounds the window when closed) — the stored
  LINK is the proof; per-user visibility of paper events stays isolated;
  (4) otherwise STOP. Same asset, same action, and elapsed time are never
  proof; no fixed-day timeout is used (none is evidence-supported).
* **Duplicate generation** — historical same-timestamp scheduler siblings
  flow through the Delta comparison, which yields no meaningful change for
  identical rows → no phantom update events (pg-pinned; a sibling pair
  straddling the wording cutover legitimately emits one
  confidence-presentation change and that is correct history).
* **Lifecycle termination** — resolved target/exit/time outcome or the
  linked position's closure ends the window; a later recommendation after
  termination is a NEW lifecycle (pg-pinned).

When continuity is unproven the replay returns `updates_complete=false`,
adds an unavailable-section explanation ("Later recommendations for this
company could not be proven to belong to this exact idea…"), and shows no
later recommendation events. Completeness becomes `partial`. All prior
replay behavior (pinning, isolation, redaction, firewall, ordering) is
regression-pinned.
