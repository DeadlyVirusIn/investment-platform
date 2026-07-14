# Post-Elite Implementation Plan (for Claude Opus)

Date: 2026-07-12 · Branch baseline: `feature/elite-arthos-provable-ideas`
@ `e401d53` · Dev DB at migration **118** · Prod at **109**.
Research inputs: `docs/research/FINAL_EXTERNAL_REPO_GAP_REVIEW_2026.md`
(licensing table + clean-room statement there governs everything here — no
AGPL-derived implementation exists or may be introduced).

**Global hard stops (every wave):** no deploy · no merge to prod branches ·
no production migration · no production flag change · no live trading or
broker/exchange code · no public leaderboard · no LLM able to override a
deterministic gate · no new infrastructure service (Postgres + FastAPI +
existing web only) · smallest auditable diffs · every feature behind its own
default-off flag · additive migrations only, each with tested downgrade.

**Migration numbering:** numbers below are PROPOSALS continuing after 118.
Before generating any migration, run `alembic heads` and verify the actual
head; renumber if the branch has moved. One linear chain, no branches.

**Shared conventions (reuse, do not reinvent):**
- Owner gating: `apps/api/src/api/admin_guard.require_owner` (404 posture).
- Flags: `apps/api/src/config/__init__.py` settings booleans, default False;
  routers mounted conditionally in `main.py` (fail-closed like
  `RESEARCH_INBOX_ENABLED`).
- Honesty labels: the six-state vocabulary from `trust_center.py` /
  `EvidenceBadge` (`proven … unavailable`).
- Frontend primitives: `StatusPanel`, `EvidenceBadge`, `freshnessInfo`,
  `RouteErrorBoundary`, `ArthosPage`; tests via the Vitest suite
  (`npm test`, 241 passing at baseline).
- Backend tests: pg-marked pytest files beside existing
  `test_research_inbox_pg.py` patterns; ephemeral-alembic harness for
  migration up/down proofs.

---

## Wave 1 — trust-control spine (dev-only, ~4 features, no new deps)

### 1. Recommendation Publication Preflight — **BUILT 2026-07-12** (dev, flag-off)

Shipped as specified with two deltas: flag named
`RECOMMENDATION_PREFLIGHT_ENABLED`; table named `recommendation_preflight`.
Authoritative record: `docs/architecture/RECOMMENDATION_PUBLICATION_PREFLIGHT.md`.
Original spec retained below for provenance.

#### Original spec — flag `PUBLICATION_PREFLIGHT_ENABLED`

**Problem.** Publication checks exist but are scattered; nothing produces an
auditable verdict of "why this idea was allowed on Discover."
**User value.** Beginner sees honest limitation chips; owner gets a
provable gate; Trust Center gets a `proven`-grade feed.
**Scope.** Deterministic service evaluating a recommendation row at
publication time; persist verdict; expose in APIs; render chips.
**Non-goals.** No blocking of the engine's generation; no LLM involvement;
no re-scoring; no production wiring.

**Architecture.** New module `apps/api/src/domain/publication/preflight.py`:
pure function `run_preflight(db, recommendation) -> PreflightResult` with an
ordered check list; each check returns `(check_id, status: pass|limit|fail,
detail: str)`. Verdict derivation: any `fail` → BLOCKED (data-integrity
class) or HOLD (transient class, e.g. freshness); any `limit` →
READY_WITH_LIMITATIONS; else READY. Checks (initial set, all reading
existing signals): `freshness_ok` (reuse freshness engine thresholds),
`ingest_contract_ok` (contracts report when `INGEST_CONTRACTS_ENABLED`,
else `limit` "contracts off"), `enough_data`, `stale_data_flag`,
`evidence_present` (family_scores non-empty), `counter_evidence_present`
(at least one negative-family signal or explicit risk), `falsifier_present`
(exit-if-wrong derivable from plan fields), `confidence_label_valid`,
`calibration_disclosed` (chip data available), `provenance_present`
(engine_version + snapshot_hash non-null), `no_open_incident` (posture from
feature 2 ≠ SAFE), `no_duplicate_open_idea` (no other live rec same symbol
+ action Buy), `plan_consistent` (Buy: exit < entry_low ≤ close ≤ entry_high
< target), `prohibited_language` (server-side scan of thesis/plan text
against the existing copy-lint deny list, ported list not logic).
**Schema (migration 119, proposed).** Table `publication_preflight`:
`id uuid pk · recommendation_id fk recommendations.id (unique) · verdict
text CHECK in (READY, READY_WITH_LIMITATIONS, HOLD, BLOCKED) · checks jsonb
· engine_version text · created_at timestamptz default now()`. Immutable:
no UPDATE path in service; re-evaluation inserts is FORBIDDEN (one verdict
per recommendation row; a new engine run creates a new recommendation).
**API.** `GET /recommendations/{id}/preflight` (public read, flag-gated);
list embed: `preflight_verdict` field on `/recommendations` responses when
flag on. Owner rollup `GET /admin/preflight/summary` (counts by verdict,
last N failures).
**Frontend.** PickPage + Discover card: chip for
READY_WITH_LIMITATIONS ("Published with limitations — see why") opening a
disclosure listing `limit` checks in plain English; HOLD/BLOCKED ideas are
NOT rendered (engine still records them). Reuse EvidenceBadge tones.
**State machine.** Verdicts are terminal; no transitions.
**Audit.** The row IS the audit. Include in Decision Replay.
**Security.** No user input; owner rollup behind require_owner. Threat:
prohibited-language list must live server-side (not user-editable).
**Performance.** One SELECT per check batch; evaluate lazily at publication
(hook where recommendations become visible — `api/recommendations.py` list
path) with per-request memoization; target < 20 ms per idea.
**Failure behavior.** Preflight service error → treat as HOLD (fail
closed), log bounded error.
**Rollback.** Flag off → no verdicts computed, UI hides chips; downgrade
drops table.
**Tests.** Unit: each check pass/limit/fail + verdict derivation matrix +
immutability. Integration (pg): end-to-end verdict on seeded rec; duplicate-
idea check; fail-closed on service exception. Web: chip rendering, hidden
HOLD ideas (Vitest, mock API).
**Evidence before prod.** 2 weeks of dev verdicts with zero false BLOCKED
on known-good nightly runs; Trust Center section wired.
**Order/effort.** First. ~2–3 sessions.

### 2. Research Safe Mode (system posture)  — flag `SYSTEM_POSTURE_ENABLED`

**Problem.** Degraded inputs currently rely on guard-absorption + human
noticing; publication should stop itself.
**Scope.** Posture service + event log + automatic evaluation + owner
recovery + calm user banner. Postures: `NORMAL / RESTRICTED / SAFE`.
**Non-goals.** Does not stop ingestion, outcome scoring, paper exits, or
reads. Never deletes/hides existing ideas.

**Architecture.** `apps/api/src/domain/publication/posture.py`.
`evaluate_posture(db) -> (posture, reasons[])` from: freshness beyond
threshold → RESTRICTED; ingest contract quarantine/abort (when enabled) →
SAFE; scheduler health red (`ops/scheduling_health.py` stuck>0 or overdue>0
beyond grace) → RESTRICTED; drift breach (monitoring/drift.py thresholds) →
RESTRICTED; provenance unknown (git_sha unresolved) → RESTRICTED; outcome
labeling stalled > 48h → RESTRICTED; owner-declared incident → SAFE.
Evaluated by the existing tick loop (new registry job `evaluate_posture`,
claim-based like others) and lazily on read with 60s cache.
**Transitions.** Automatic downgrade any time. Upgrade: signals must be
clean for one full evaluation cycle AND — for SAFE→NORMAL only — an owner
acknowledgment (POST). Every transition writes an event row.
**Schema (migration 120, proposed).** `system_posture_event`: `id uuid pk ·
posture text CHECK · reasons jsonb · triggered_by text (auto|owner:<email>)
· created_at timestamptz`. Current posture = latest row (no mutable state).
**API.** `GET /system/posture` (public, cached — feeds banner + preflight
check `no_open_incident`); owner: `POST /admin/posture/incident`
(declare, with reason), `POST /admin/posture/acknowledge` (SAFE→NORMAL
half), `GET /admin/posture/events`.
**Frontend.** Discover/Today banner in SAFE: StatusPanel-warn "New ideas
paused while data heals — nothing you hold is affected." Trust Center
System-health section shows posture with EvidenceBadge (degraded ↔
RESTRICTED, unavailable ↔ SAFE). Control Room (Wave 3) gets the levers.
**Security.** Owner endpoints behind require_owner; incident reason length-
capped; no secrets in reasons.
**Failure.** Posture evaluation error → RESTRICTED (fail closed), logged.
**Rollback.** Flag off → posture endpoints 404, preflight check returns
pass, banner absent. Downgrade drops event table.
**Tests.** Unit: trigger matrix, hysteresis (clean-cycle re-arm), owner-ack
requirement. Integration: event rows on transition; preflight coupling.
Web: banner render on SAFE.
**Evidence before prod.** Simulated degradations in dev produce correct
posture + recovery; no flapping across 1 week of nightly cycles.
**Order.** Second (preflight consumes it). ~2 sessions.

### 3. "What changed?" delta contract  — flag `REC_DELTA_ENABLED`

**Problem.** Audit M3: beginners can't see what changed since yesterday.
**Scope.** Read-only comparison of latest vs previous recommendation row per
symbol. **No migration.**
**Architecture.** `domain/recommendations/delta.py`:
`compute_delta(db, symbol) -> RecDelta` with: prior row lookup (previous
generated_at for symbol), `action_changed`, `confidence_label_changed`,
`family_deltas` (per family: direction + plain-English phrase via the
existing `ideaSignals` vocabulary server-side equivalent), `price_vs_plan`
(close vs entry corridor/exit/target), `freshness_delta`,
`thesis_revision_ref` (when ledger flag on), `first_seen` boolean.
**API.** `GET /recommendations/{symbol}/delta` → `{as_of, prior_as_of,
changes: [{kind, direction, text}], first_seen}`. 15-min cache.
**Frontend.** PickPage "What changed" section (slots into the existing
narrative order position 4); Discover card one-line change note when
non-empty; Briefing strip enrichment; Inbox report supersedes note reuses
the same phrasing helpers.
**Failure.** No prior row → `first_seen: true`, UI says "New idea today."
**Tests.** Unit: each change kind, no-prior, unchanged (empty list).
Integration: two seeded generations. Web: section render states.
**Evidence before prod.** Copy review (owner) — user-facing language gate.
**Order.** Third. ~1–2 sessions.

### 4. Decision Replay Timeline  — flag `DECISION_REPLAY_ENABLED`

**Problem.** All decision artifacts are immutable but scattered; no
hindsight-proof reconstruction surface.
**Scope.** Read-only aggregation endpoint + user page + owner deep view.
**No migration.**
**Architecture.** `domain/recommendations/replay.py`: for a symbol (user)
or recommendation id (owner), assemble ordered events from EXISTING rows
only: recommendation generated (engine_version, snapshot_hash, confidence
presentation as-of-then — derive from stored label + the wording-decision
date table in code), preflight verdict (Wave-1 #1), posture at publication,
paper trade opened/closed (+cost stamp), thesis revisions, outcome
resolution, lesson (Learning Loop, when flag on). STRICT rule: render
stored values only; never recompute signals with today's code (hindsight
firewall — enforced by module docstring + test that asserts no imports from
engine scoring).
**API.** `GET /recommendations/{symbol}/timeline` (user-safe fields);
`GET /admin/replay/{recommendation_id}` (full: family_scores, checks).
**Frontend.** PickPage link "See this idea's full history →" →
`/today/pick/:symbol/history` (timeline of StatusPanel-like cards); owner
view inside admin.
**Tests.** Unit: ordering, missing-artifact tolerance (partial timelines
render with explicit "not recorded" entries, never invented). Integration:
seeded lifecycle. Web: page render + a11y heading order.
**Order.** Fourth. ~2 sessions.

**Wave 1 production gates.** None of these ship to prod until: Stage B of
the existing promotion plan completes for the current Elite stack; then
preflight+posture promote together (they are the trust spine), delta/replay
follow as web+read-only API (lower risk).
**Parallelizable.** #3 and #4 are independent of each other (both depend
lightly on #1's table for enrichment but degrade gracefully without it).

---

## Wave 2 — research workspace (owner-facing, small)

### 5. Research Inbox completeness
Correction route: `POST /admin/inbox/reports/{id}/correct` → existing
`inbox_service.correct_report` (body, citations optional, provenance
`human`); 409 on correcting a superseded row. UI: "Correct" action on
approved/pending reports (owner) opening a body editor that ALWAYS creates
v+1 (no edit-in-place affordance anywhere). Follow-up: "Create follow-up
task" button pre-filling `POST /admin/inbox/tasks` from a report. Tests:
route (pg) incl. version chain + old-row byte-identity reuse of existing
pinned test; web tests for both actions. No migration. Flags: existing
`RESEARCH_INBOX_ENABLED` + `VITE_RESEARCH_INBOX`.

### 6. Research Mission Board  — flag `VITE_RESEARCH_INBOX` (same surface)
**SHIPPED 2026-07-13 (Wave 2B).** Owner page `/admin/research-board` over
`GET /api/admin/inbox/mission-board` (rule set `mission-board-1`; spec
`docs/architecture/RESEARCH_MISSION_BOARD.md`). Columns Queued / Running /
Review needed / Delivered / Corrected / Stale / Failed. Pure server-side
aggregation service (`domain/research_inbox/mission_board.py`, ≤4 bounded
SELECTs, zero writes). Plan corrections discovered in Phase 0 and pinned:
`agent_job` has NO task linkage, so Running/Failed carry labelled JOB
cards (tasks never enter them); there is no owner gateway-job UI or
owner-session cancel route, so those card actions are absent by design;
corrected approved chains live in Corrected (not Delivered). Mobile:
segmented column tabs. Tests: 34 unit + 12 pg + 9 web.

### 7. Tracked-entity thin slice — DESIGN REVIEW DONE (Wave 2C, 2026-07-13)
**Original proposal (tracked_entity + polymorphic entity_link) REJECTED**
by the Wave 2C design review — Postgres cannot FK a polymorphic
target_id; supports/contradicts would bypass the reviewed
thesis_evidence gate; symbol entities duplicate `asset`
(UNIQUE(symbol, exchange) — symbol alone isn't unique). Replacement
design of record:
`docs/architecture/TRACKED_ENTITY_AND_RESEARCH_PROVENANCE_DESIGN.md`.
Verdicts: task↔job provenance GO (nullable
`agent_job.research_task_id` FK RESTRICT, migration 121); follow-up
source-report provenance GO (`research_task.source_report_id` with
composite FK enforcing same-task, migration 121); job→report DEFER (no
producing path exists); tracked entities REDESIGNED to theme-only
vocabulary + typed task↔theme/task↔asset tables (migration 122, gated
on 121-usage evidence); Replay report linkage GO-with-conditions
(typed `report_recommendation_link`, fixed "context" relation, never
evidence, migration 122). No backfill anywhere. Overall: **WAVE 2C
DESIGN APPROVED FOR IMPLEMENTATION** — implementation awaits explicit
authorization; nothing generated or applied (heads verified at 120,
prod 109).
**Migration-121 scope IMPLEMENTED 2026-07-13** (dev at 121, prod 109;
record: `RESEARCH_EXECUTION_PROVENANCE.md`): task↔job link + follow-up
source-report composite FK + DB immutability triggers + gateway
submission field + execution-history route + Mission Board
`mission-board-2`. Migration 122 remains gated on owner-usage evidence.

**Wave 2 gates.** Dev-only until Inbox itself is promoted; board and links
ride the same flags. Parallel: #5 and #6 independent; #7 after design
sign-off (owner).

---

## Wave 3 — evidence operations

### 8. Experiment Lab harness (the anchor; pre-existing Elite commitment)
Build per `RESEARCH_RUN_REGISTRY_SPEC.md` + roadmap 31–90d: purged
walk-forward harness (extend `scripts/research/walk_forward_baseline.py`
into `domain/evaluation/lab.py`), cost/slippage sweeps reusing
`execution_costs.py`, benchmarks (buy-and-hold, 12-1 momentum), writes every
run to `research_run` (git_sha, config_hash, seed, metrics hash).
Dependencies to ADD at this point (verified 2026-07-12, see gap review §2D):
`statsmodels` (multipletests/BH), `Optuna` (sweeps, Postgres storage).
`statsforecast` only if its `scipy<1.16` pin has relaxed — re-verify.
Flag `EXPERIMENT_LAB_ENABLED` (job registration only; no user surface).

### 9. Experiment Comparison Arena (owner UI)
`/admin/experiments`: table over research_run rows — OOS windows,
Brier/reliability, AUC, drawdown, turnover, cost-adjusted return, N,
stability, reproducibility check (re-hash), promotion status. Winner
banner ONLY when registry promotion gates pass (min N, OOS, cost-adjusted,
benchmark-relative — enforce in service, not UI). No migration (registry
exists). Tests: gate logic unit tests; web render.

### 10. Promotion queue + audit viewer + Control Room
- Promotion queue: owner list of runs awaiting promotion decision +
  approve/deny via existing `research_run_approval` (route exists? verify;
  add thin routes if not).
- Audit viewer: `/admin/audit` paging over gateway audit + posture events +
  preflight failures (read-only, filterable, no export v1).
- Control Room `/admin/control-room`: composition of existing endpoints +
  Wave-1 posture/preflight rollups; division per gap review §4.7 (Trust
  Center = evidence; Control Room = readiness/action). Actions exposed:
  posture acknowledge/incident, job trigger links (existing admin), flag
  READ-ONLY display.

**Wave 3 gates.** Lab runs must reproduce the calibration study's numbers
before Arena ships; promotion decisions remain owner-manual.

---

## Wave 4 — statistical depth (each requires the stated evidence gate)

11. **Survival/censored outcomes** (`lifelines`): KM time-to-TP/SL curves +
    censored-aware hold-time stats on resolved+open positions. Gate: ≥100
    resolved trades in the analyzed book. Owner-only Lab report first;
    beginner copy only after owner review.
12. **Significance + multiple testing everywhere in Lab reports**
    (statsmodels BH; report q-values beside every comparison).
13. **Portfolio-level attribution rollup**: SQL view aggregating existing
    per-position attribution to book level; Arena panel.
14. **MAPIE prediction intervals**: only when the calibrator data-block
    clears (≥3 quarters live decisions — trigger already documented);
    intervals appear in owner surfaces first, never as beginner-facing
    precision theater.
15. **Cost-model application** (`PAPER_COST_MODEL_ENABLED` on in dev):
    apply stamps to fills + track-record math with a side-by-side
    with/without-costs view; promote only with Lab sensitivity evidence.

---

## Execution order for Opus (first feature first)

1. **Recommendation Publication Preflight** (Wave 1 #1) — start here.
2. Research Safe Mode — **BUILT 2026-07-13** → 3. What-changed — **BUILT 2026-07-13** → 4. Replay Timeline — **BUILT 2026-07-13** (docs/architecture/DECISION_REPLAY_TIMELINE.md) — **WAVE 1 COMPLETE** →
5/6 Inbox completeness + Mission Board → 7 entity slice (after design OK) →
8 Experiment Lab → 9 Arena → 10 ops surfaces → Wave 4 by evidence gates.

Before ANY migration: `alembic heads` — verify 118 is still head; renumber
proposals if not. Before ANY user-visible copy: owner review. Before ANY
production step: the existing promotion plan's stage gates.
