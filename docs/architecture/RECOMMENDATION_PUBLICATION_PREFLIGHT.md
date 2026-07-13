# Recommendation Publication Preflight (Wave 1A)

Status: BUILT in dev, flag-off · Branch `feature/elite-arthos-provable-ideas`
· Migration **119_recommendation_preflight** (dev applied 2026-07-12 after
backup `.backups/devdb_full_20260712_pre119.dump`; ephemeral up/down/up
validated; **prod untouched at 109**). Plan source:
`docs/roadmap/POST_ELITE_OPUS_IMPLEMENTATION_PLAN.md` (Wave 1 #1).

## What it is

The deterministic trust gate between the engine and every beginner surface.
Before a candidate recommendation may appear on `/discover`, `/today`, or an
idea detail page, it must hold a persisted verdict computed ENTIRELY from
stored system facts:

`READY · READY_WITH_LIMITATIONS · HOLD · BLOCKED`

No LLM, prompt, model narrative, or administrator can override a verdict
silently: the evaluator is a pure function, verdict rows are immutable and
append-only, and the only "override" that exists is honest — change the
facts (or the versioned rule set) and a NEW evaluation is appended beside
the old one.

## The authoritative publication seam

Established by inspection before implementation: recommendations become
user-visible exclusively through `GET /api/recommendations`
(`apps/api/src/api/recommendations.py::list_recommendations`, typically
`latest=true` via `list_latest_per_asset`). Discover, Today, and PickPage all
consume this one endpoint (`useTodaysRecommendations`). No equivalent
preflight existed — checks were scattered (`enough_data`/`stale_data` flags,
freshness engine, web-side copy lint) with no verdict artifact. The gate is
integrated at exactly this seam and nowhere else; the nightly engine, paper
execution, exits, outcome scoring, and portfolio reads are untouched
(pinned by test).

## Verdict semantics

Each check carries a fixed severity; failures roll up:

| Any failed severity | Verdict | Publication |
|---|---|---|
| block | BLOCKED | never published (data-integrity class) |
| hold (no block) | HOLD | not published now (transient class) |
| limitation (no hold/block) | READY_WITH_LIMITATIONS | published WITH honest beginner chips |
| none | READY | published |

Deliberate honesty property: `calibration_disclosed` and
`schema_version_present` fail as limitations on EVERY candidate until their
promotion gates clear (production reliability curve; engine schema
stamping). A plain READY is therefore currently unreachable — by design, not
by accident. The two flips are documented promotion gates, not code changes.

## Check registry (rule set `pf-1`, ordered; order is part of the version)

Data/freshness: `price_data_exists`(block) · `price_freshness`(hold, bar ≤ 5
calendar days) · `provider_state`(hold, last `ingest_prices_daily` run
success ≤ 30 h; missing history fails closed) · `ingest_contract`(limitation
while `INGEST_CONTRACTS_ENABLED` is off; contracts abort upstream when on).
Integrity: `enough_data`(block) · `engine_stale_flag`(hold) ·
`action_publishable`(block, {Buy,Hold,Trim,Sell}) · `plan_inputs_valid`(hold,
positive finite close + finite volatility input — entry/target/exit are
derived deterministically from these) · `identity_normalized`(block) ·
`no_duplicate_open_idea`(block: candidate must be the latest for its asset
and its symbol unique across assets) · `timestamp_coherent`(block,
future-skew only; staleness lives in price_freshness).
Evidence: `evidence_present`(block) · `counter_evidence_present`(limitation)
· `falsifier_present`(block: exit-if-wrong derivable = close + volatility
family present) · `evidence_review_state`(block on families outside the
trusted engine set — generated/unknown evidence fails closed) ·
`evidence_provenance`(block: engine_version + snapshot_hash) ·
`payload_wellformed`(block: strict JSON, NaN/Infinity rejected).
Confidence/language: `confidence_label_valid`(block, {High,Medium,Low}) ·
`wording_consistent`(limitation; buy-bar mapping) ·
`no_probability_claim`(block, regex) · `calibration_disclosed`(limitation,
permanent until production calibration) · `prohibited_language`(block,
server-owned deny list incl. guaranteed-return phrases) ·
`beginner_summary_present`(hold).
Provenance/posture: `schema_version_present`(limitation, permanent until
stamping ships) · `git_sha_known`(limitation) · `system_posture`(SAFE →
hold, RESTRICTED → limitation, via `domain/publication/posture.py`).

## Evaluation record (immutable)

Table `recommendation_preflight` (migration 119): id ·
recommendation_id (FK, no cascade — deleting a recommendation with verdicts
is refused) · verdict (CHECK) · rule_set_version · input_hash ·
checks_json/limitations_json/blocking_reasons_json (CHECK-bounded sizes) ·
evaluated_at · evaluator_git_sha · source_freshness_at · created_at.
Unique `(recommendation_id, rule_set_version, input_hash)` = idempotency
key; concurrent identical evaluations resolve to one row (ON CONFLICT DO
NOTHING + re-select). The service exposes no UPDATE/DELETE path (pinned by
introspection test). `input_hash` = sha256 of the canonical frozen input
with `now` quantized to its calendar date (freshness policies are
day-granular), so same-day unchanged-fact re-evaluations are idempotent
while a new day legitimately appends.

## Fail-closed rules

* Missing mandatory fact → its check fails (never skips).
* Unknown evidence family → block (unreviewed provenance is untrusted).
* No ingest history → hold.
* Evaluator exception anywhere → the publication path receives a synthetic
  HOLD (`ensure_current_verdict`) and the candidate is not published.
* Publication-transaction guarantee: at read time the verdict used is the
  one matching the candidate's EXACT current input hash — if facts moved, a
  fresh evaluation is appended and used; a stale verdict can never publish a
  changed candidate.

## Flag + behavior

`RECOMMENDATION_PREFLIGHT_ENABLED` (default **False**).
Off: router unmounted, zero evaluations, `GET /recommendations`
byte-identical to legacy (pinned by test).
On (dev): only READY / READY_WITH_LIMITATIONS appear in the list; each
carries a redacted projection `{verdict, limitations[beginner text only],
evaluated_at, freshness_summary}`. HOLD/BLOCKED candidates remain in the
ledger and owner surfaces — never deleted, never rewritten. Paper exits,
portfolio reads, outcome processing, existing positions: unaffected (the
gate lives only in the publication read path).

## API

Owner (require_owner, 404 posture, flag-mounted):
`POST /api/admin/preflight/recommendations/{id}/evaluate` ·
`GET  /api/admin/preflight/recommendations/{id}` (latest + history) ·
`GET  /api/admin/preflight/verdicts?verdict=&limit=` ·
`GET  /api/admin/preflight/recommendations/{id}/explain` (failed checks).
Public: no route — only the embedded projection on published ideas; it never
contains ids, hashes, raw checks, shas, provider diagnostics, or stack
traces (pinned by unit + pg tests).

## UI

Owner console `/admin/preflight` (verdict chips, ordered checks with
severity, provenance line, re-evaluate = append). Beginner surfaces: a calm
amber "Published with limitations ▾" chip on Discover cards + PickPage that
discloses only the beginner-text lines; no developer diagnostics anywhere.
Reuses StatusPanel/EvidenceBadge language, freshnessInfo, route error
boundary.

## Security review (threat → mitigation)

* Forged READY: verdicts only via the evaluator service; rows immutable;
  reads join on the idempotency key incl. input_hash.
* Stale verdict reuse: `ensure_current_verdict` hash-match at publication.
* Check omission: registry order + ids pinned by unit test; RULE_SET_VERSION
  bump required for any change (downgrade of the rule set = a different
  version string recorded on every row — visible, not silent).
* Owner bypass: owner routes can only APPEND evaluations of the same pure
  function; there is no accept/override input anywhere.
* Publication outside the gate: single seam integration; diagnostics
  endpoint exposes analysis, not publishable payloads; grep-level test
  guards coupling.
* Tampered checks JSON: bounded CHECKs; content is derived, never parsed
  back into decisions (verdict column is authoritative).
* Race evaluation-vs-publication: same-transaction hash check (above);
  concurrent evaluators collapse via unique key.
* Fail-open exceptions: explicit fail-closed boundary returns synthetic
  HOLD; pinned by test with a poisoned loader.

## Tests (all green 2026-07-12)

44 unit (`test_publication_preflight.py`): verdict matrix (26 param cases),
determinism/hash stability, check-order pin, strict-JSON NaN/Infinity,
projection redaction, purity introspection, frozen input.
18 pg (`test_publication_preflight_pg.py`): idempotency, concurrency-shaped
double insert, append-only history with byte-stable first row, no
UPDATE/DELETE path, verdict CHECK, FK refusal, hash-match re-evaluation,
poisoned-loader fail-closed HOLD, real-fact verdicts (missing bar → BLOCKED,
stale bar → HOLD, no ingest history → HOLD, newer sibling → BLOCKED, SAFE
posture → HOLD, prohibited language → BLOCKED), flag-off byte-parity with
zero evaluations, flag-on hide+projection redaction, paper/portfolio
decoupling, ORM/migration parity.
4 web (`PreflightLimitations.test.tsx`): no-projection/READY render nothing,
chip + disclosure, no diagnostics leak. Web suite total 245; tsc/eslint/
build/lint:portfolio green. Local API unit sweep: failure set byte-identical
to clean HEAD (147 pre-existing env-dependent), +62 new passing.
Migration: ephemeral up/down/up validated; dev applied.

Live smoke (dev, flag on): 200 candidates → 200 truthful HOLDs on 50 h-stale
dev ingest; with a fresh ingest signal → 200 READY_WITH_LIMITATIONS
published with exactly the two honest limitations (contracts off,
calibration preliminary); append-only history (2 rows per candidate)
observed; owner console + beginner chip screenshots in
`docs/ux/screenshots/elite-webui/preflight-*.jpeg`.

## Rollback

Flag off → behavior byte-identical to legacy, table dormant. Full removal:
`alembic downgrade 118_execution_lease` drops the table (additive-only).

## Production promotion gates

1. Existing Elite promotion plan Stage B completes (unchanged critical path).
2. ≥2 weeks of dev verdicts with zero false BLOCKED on known-good nightly
   runs (HOLD on genuinely stale data is correct behavior, not a false
   positive).
3. Owner copy review of every beginner_text line.
4. Trust Center section wired to the verdict feed.
5. Separate approval to enable the flag in prod (standard hard stop).

## Relationship to Research Safe Mode (Wave 1B)

Preflight consumes `domain/publication/posture.py::current_posture` — today
a fixed interface (override env → else NORMAL) whose semantics are frozen:
SAFE holds all new publications, RESTRICTED caps at
READY_WITH_LIMITATIONS, existing ideas/portfolios always readable. Wave 1B
implements signal-derived posture + the audited event log behind the SAME
signature; nothing in preflight changes when it lands.
