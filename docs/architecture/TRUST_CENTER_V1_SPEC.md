# Trust Center v1 — Spec (Sprint 7)

Status: PROPOSAL — no code written. Source context:
`docs/research/EXTERNAL_QUANT_AI_REVIEW_2026.md` §8 Pillar E, §9 opportunity
#4, §11 M3. Style anchors: `apps/api/src/api/freshness.py`,
`apps/api/src/build_provenance.py`, `apps/api/src/api/admin_guard.py`,
`apps/api/src/api/admin_observability.py`, `apps/api/src/db/models.py`.

## 1. Principle

The Trust Center **assembles what already exists and labels it honestly**.
It computes no new metrics, and it NEVER manufactures one: every section
carries exactly one status label from the enum below, and when the
underlying data does not exist yet, the section says so in plain English
instead of showing a number.

### Status label enum

`proven` · `preliminary` · `insufficient_data` · `not_yet_evaluated` ·
`degraded` · `unavailable`

- `proven` — metric exists, sample ≥ its stated threshold, pipeline fresh.
- `preliminary` — metric exists but below threshold or short history;
  shown WITH the caveat, never without.
- `insufficient_data` — pipeline works, sample too small to show any number.
- `not_yet_evaluated` — the measurement itself hasn't been built/run yet.
  (Honest default for new sections.)
- `degraded` — source exists but is stale/erroring right now.
- `unavailable` — source unreachable at render time (DB error, missing
  table); section renders its label + nothing else, endpoint still 200s.

Label logic is per-section and deterministic (§3). A section may never
"fall back" to a cached number without flipping to `degraded`.

## 2. Rollout: owner-facing v1 first, public-safe v2 second

- **v1 (this sprint)**: `/v2/admin/trust-center` page + owner-only API,
  guarded by `require_owner` (`admin_guard.py`, 404 posture). Full detail,
  including flag names and incident internals.
- **v2 (separate approval)**: public `/v2/trust` page + redacted API (§6).
  Exposing it is a user-facing production change ⇒ HARD STOP approval per
  global policy. Nothing in v1 creates a public route.

Zero migrations for v1: every feed below is an existing table, endpoint, or
a curated file checked into the repo. (The "promoted experiment history"
section reads `research_run` if Sprint 5's migration has been applied;
until then it is `not_yet_evaluated` — the spec does not depend on ordering.)

## 3. Sections — feed + label logic (exact)

Each section returns `{key, title, status_label, as_of, data, note}`.

### 3.1 System status
- **Feed**: `/api/health`; `job_schedule`/`job_run` tables (stuck-job logic
  already in `apps/api/src/api/admin_console.py` + `admin_observability.py`).
- **Label**: API up + no enabled job overdue > 24h → `proven` ("operating
  normally"). Overdue/stuck jobs or recent `job_run.status='failed'` →
  `degraded` with the list. Health check fails → `unavailable`.

### 3.2 Data freshness
- **Feed**: existing freshness engine, `GET /api/freshness`
  (`apps/api/src/api/freshness.py` — channels: recommendations, portfolio,
  events, options, risk, ml; `_aggregate_overall`).
- **Label**: overall fresh → `proven`; any user-facing channel stale →
  `degraded` listing channels with `_human_age` strings; endpoint error →
  `unavailable`. This section re-serves the engine's own classifications —
  no re-derivation.

### 3.3 Model version
- **Feed**: `get_build_provenance()` (`apps/api/src/build_provenance.py`:
  GIT_SHA/GIT_BRANCH/GIT_DIRTY/BUILD_TS baked into images) + latest
  `recommendation.model_version` (models.py:317).
- **Label**: sha known + not dirty → `proven`. `unknown_sha` or
  `dirty_build` flag → `degraded` (say it plainly: "this build's exact code
  version is not verifiable"). That honesty IS the feature — those flags
  exist because of the 06-04..06-10 double-fill image-drift incident.

### 3.4 Feature schema version
- **Feed**: none exists today. Future feed: `research_run.feature_schema_version`
  of the latest promoted run (Sprint 5).
- **Label**: `not_yet_evaluated` at launch, with the note "feature schema
  versioning ships with the experiment registry". Never invent a version
  string.

### 3.5 Recommendation sample size
- **Feed**: `SELECT count(*) FROM recommendation` + distinct assets +
  earliest `generated_at`.
- **Label**: counts are facts → `proven` (of the count itself). Copy states
  the number is volume, not skill: "ArthOS has published N ideas since
  <date>. Volume is not accuracy — see the next two sections."

### 3.6 Resolved vs unresolved outcomes
- **Feed**: `recommendation_outcome` (models.py:363): resolved = rows with
  `realized_30d_return IS NOT NULL` (and/or `barrier_label IS NOT NULL`);
  unresolved = recommendations past their 30d window with no outcome row —
  that gap is *shown*, not hidden.
- **Label**: outcome job current (gap ratio < 10%) → `proven`; job running
  but backlogged → `degraded` ("outcome grading is behind by ~K ideas");
  fewer than 10 resolved → `insufficient_data` (the existing "accuracy
  publishes at 10 closed outcomes" floor, made systematic).

### 3.7 Confidence calibration status
- **Feed**: latest completed `research_run` with `run_type='calibration'`
  (Sprint 5 §6 example row: Brier, per-band coverage).
- **Label**: no such run → `not_yet_evaluated` ("we have not yet verified
  that our confidence numbers mean what they say — we will publish this
  either way"). Run exists, n_resolved < 100 → `preliminary` with bands +
  caveat. ≥ 100 and refreshed within 90 days → `proven`. Older than 90
  days → `degraded` (stale study). Publishing a bad calibration result
  verbatim (e.g. "overconfident above 70") is required behavior, not a
  bug.

### 3.8 Paper record
- **Feed**: canonical stock portfolio (`/api/paper/canonical/stock`;
  `paper_equity_snapshot` filtered `source='live'` — the M079/M083 truth
  contract in models.py:519-529) + closed `paper_position.realized_pnl`
  rows (MP1S attribution, migration 100).
- **Label**: snapshots fresh per freshness engine → `preliminary` until the
  record spans ≥ 12 months AND ≥ 100 closed positions, then `proven`.
  Copy always states: paper trading, simulated fills, no real money, past
  results ≠ future returns.

### 3.9 Benchmark comparison
- **Feed**: canonical equity curve vs SPY total return from `price_bar`
  over the same window (buy-and-hold benchmark; the 12-1 momentum
  benchmark joins when the M4 harness produces it).
- **Label**: both series complete over the window → same
  `preliminary`/`proven` thresholds as 3.8 (a record is only as proven as
  its comparison). SPY bars stale → `degraded`. Never show ArthOS's curve
  without the benchmark on the same chart — that is the whole point.

### 3.10 Known limitations
- **Feed**: curated file `docs/trust/limitations.md` (checked in, versioned
  by git, rendered verbatim). Seed list: paper-only; small closed-outcome
  sample; universe breadth (~63 deep-history names — BP8–BP27B root
  bottleneck); daily bars, no intraday execution realism; options
  subsystem dormant (`OPTIONS_ENABLED=false`); confidence not yet
  calibrated (until 3.7 flips); single-operator review process.
- **Label**: file present → `proven` (it is a statement, not a metric);
  missing → `unavailable`.

### 3.11 Recent incidents
- **Feed**: curated registry `docs/trust/incidents.json` — array of
  `{id, date, severity, title, what_happened, impact, fix, verified_by,
  status}`. Seeded honestly with:
  - **2026-07-08 — P1 — Engine jobs traded user practice books.** What
    happened: the nightly auto-trader (and weekly rebalance / exit cycle)
    selected every active paper portfolio, including per-user practice
    books (`user:<id>:stock`), and deployed each new user's full $100,000
    starting practice cash into engine picks. Impact: affected users'
    "Add to paper" failed with "insufficient cash: have 0"; user books
    showed engine positions the user never chose. Paper money only — no
    real funds exist in ArthOS — but it broke the product's core promise
    that *only you act on your book*. Fix: ownership boundary on the
    portfolio name prefix; every scheduled engine job now selects through
    a single guarded statement that excludes user books
    (`apps/api/src/domain/paper_trading/paper_service.py` —
    `is_user_paper_book` / `engine_tradable_portfolios_stmt`, NOT LIKE
    'user:%'); exit-cycle and pending-replay paths patched the same day.
    Verified by: `apps/api/tests/unit/test_user_book_guard.py`,
    `apps/api/tests/integration/test_paper_user_portfolio_pg.py`,
    `apps/api/tests/integration/test_exit_cycle_scoped_pg.py`. Status:
    resolved; user-book restoration handled per affected book.
  - (Optional back-history, owner's call: 2026-06-04..10 double-fill /
    image-drift incident; 2026-05-08 scheduler trust incident — both
    already written up in repo docs.)
- **Label**: registry present → `proven`; any incident with
  `status!='resolved'` → also render a banner. Empty array is valid and
  says "no incidents recorded since <registry start date>" — with the
  start date, so it can't imply a longer clean history than we can prove.

### 3.12 Model / research change log
- **Feed**: distinct `recommendation.model_version` values with first/last
  `generated_at` + curated `docs/trust/changelog.md` for human-written
  entries (model_scorecard rows referenced where they exist).
- **Label**: `proven` for the version list (facts); changelog file missing
  → the human-notes subsection is `unavailable`, version list still shows.

### 3.13 Promoted experiment history
- **Feed**: `research_run` where `promotion_status IN
  ('promoted','rolled_back')` + `research_run_approval` rationale rows
  (Sprint 5); options-canary governance shown from
  `v2_promotion_snapshot`/`v2_promotion_approval` (models.py:1393-1499) as
  the pre-registry precedent.
- **Label**: registry table absent or empty → `not_yet_evaluated`
  ("no experiments have been promoted through the registry yet").
  Rows exist → `proven` (decisions with rationale are facts).

### 3.14 Current feature flags
- **Feed**: `apps/api/src/config/__init__.py` settings booleans
  (`OPTIONS_ENABLED`, `OPTIONS_CANARY_ENABLED`, `ML_HYBRID_ENABLED`,
  `RESEARCH_RO_ENABLED`, `AGENT_INSIGHTS_ENABLED`, …) read at render time
  from the live settings object — names + values + one-line meaning, so
  the owner page always states which subsystems are actually on.
- **Label**: `proven` (runtime facts). NOTE: values only — never render
  flag-adjacent secrets/keys; the section serializer allowlists boolean
  flags explicitly rather than dumping settings.

## 4. API aggregation endpoint proposal

```
GET /api/admin/trust-center            (v1, Depends(require_owner))
GET /api/trust-center                  (v2 later, public-safe, flag-gated)
```

Response shape:

```jsonc
{
  "generated_at": "2026-07-20T14:03:11Z",
  "build": { "git_sha": "…", "git_branch": "…", "flags": [] },   // build_provenance
  "sections": [
    { "key": "data_freshness", "title": "Data freshness",
      "status_label": "proven", "as_of": "…",
      "data": { /* section-specific, schema documented per §3 */ },
      "note": "plain-English caveat or empty" },
    …
  ]
}
```

Implementation notes:
- One router module `apps/api/src/api/trust_center.py`, one collector
  function per section, each wrapped so an exception yields
  `status_label:'unavailable'` for that section only — the endpoint never
  500s because one feed broke (same defensive posture as
  `_safe_max_ts` in freshness.py).
- Aggregation is read-only; no caching in v1 (owner traffic ≈ 1 user). If
  the public v2 needs caching, 60s in-process TTL, marked `as_of` so
  staleness is visible.
- Label thresholds (`10 closed outcomes`, `100 resolved`, `12 months`,
  `90-day calibration staleness`) live in one constants block at the top
  of the module with the spec section number cited — they are product
  promises, not tuning knobs.

## 5. UI layout sketch (text)

`/v2/admin/trust-center` — single scrolling page, existing admin styling:

```
TRUST CENTER (owner view)                      build 5cdb099 · main · clean
  [banner: only if any section degraded/unavailable or unresolved incident]

  ── The record ─────────────────────────────
  Paper record        [preliminary]  +6.2% since Jan · vs SPY +4.1% (same chart)
  Outcomes            [proven]       312 graded · 41 pending · 9 overdue
  Sample size         [proven]       1,841 ideas across 63 companies since 2025-11
  Calibration         [not_yet_evaluated] "confidence honesty study not yet run"

  ── The system ─────────────────────────────
  System status       [proven]       all jobs on schedule
  Data freshness      [degraded]     options quotes 3d old (dormant subsystem)
  Model version       [proven]       lgbm_v3 · image sha verified
  Feature schema      [not_yet_evaluated]
  Feature flags       [proven]       4 of 17 subsystems enabled  [expand: names]

  ── The history ────────────────────────────
  Incidents           [proven]       1 in last 90 days  [P1 2026-07-08 card, expandable]
  Change log          [proven]       model versions timeline + notes
  Promoted experiments[not_yet_evaluated]
  Known limitations   [proven]       7 items, rendered verbatim
```

Every label chip has a fixed color + icon (proven green check,
preliminary amber, insufficient_data / not_yet_evaluated grey,
degraded orange, unavailable red) and a hover/tap explainer of the label's
exact meaning — the enum definitions from §1, verbatim, so labels are
self-auditing.

## 6. Public-safe v2 (spec now, ship later, separate approval)

What v2 redacts relative to v1:

| v1 (owner) | v2 (public) |
|---|---|
| Flag **names + values** | Count + plain categories only ("options trading: off", "live trading: does not exist") — internal flag names (`OPTIONS_CANARY_ENABLED`, …) never leave the owner view |
| Incident **internals** (file paths, table names, portfolio names/ids, test file names) | Date, severity, plain-English what/impact/fix summary, resolved status. The P1 entry stays public — honesty is the point — but says "our nightly automation traded users' practice portfolios; only the user may act on their practice book now", not `NOT LIKE 'user:%'` |
| git_branch, dirty flag, BUILD_TS | model version name + "build verified: yes/no" |
| Job names / overdue lists | "operating normally / partial issue / known issue" only |
| research_run uids, hashes, parameters | promoted-experiment count + dates + one-line descriptions |
| Exact thresholds & internal notes | The same status labels (labels themselves are public vocabulary by design) |

Redaction is implemented as a **serializer allowlist per section** (public
schema is a strict subset built field-by-field), never a denylist filter
over the owner payload — a new internal field can then never leak by
default. v2 endpoint additionally rate-limited and flag-gated
(`TRUST_CENTER_PUBLIC_ENABLED: bool = False`, fail-closed).

## 7. Test plan

- Unit: label logic per section — table-driven cases hitting every enum
  value for every section (incl. thresholds ±1: 9 vs 10 outcomes, 99 vs
  100 resolved); section collector exception → `unavailable`, siblings
  unaffected; endpoint never 500s with a broken DB feed (mock session
  raising).
- Honesty pins (regression-critical): calibration section with no
  calibration run MUST NOT contain any numeric field; empty incident
  registry MUST include registry start date; paper-record payload MUST
  contain the paper-only disclaimer string; benchmark section MUST be
  absent-or-paired (no ArthOS curve without SPY).
- Guard: `/api/admin/trust-center` → 404 anonymous + non-owner
  (`make test-auth` surface).
- Public-schema test (written now, even though v2 ships later): serialize
  a fully-populated owner payload through the v2 allowlist and assert the
  output contains no flag names, no file paths, no portfolio ids, no
  hashes, no branch names (regex denylist as the *test*, allowlist as the
  *code*).
- Snapshot: owner page renders all 14 sections with seeded fixture data;
  degraded banner appears iff a section is degraded/unavailable.
- Manual verification (per repo verification rules): screenshot of
  `/v2/admin/trust-center` on dev with real data before calling it done.

## NON-GOALS

- No new metrics computation — the Trust Center reads; the Lab, freshness
  engine, and outcome jobs compute. If a number doesn't exist, the label
  says so; we never backfill a flattering placeholder.
- No public exposure in this sprint — v2 is specified, not shipped;
  shipping it is a separate HARD-STOP approval (user-facing production
  change + `make public-beta-preflight`).
- No migrations, no new tables (reads existing tables + curated repo files;
  `research_run` sections degrade gracefully to `not_yet_evaluated` if
  Sprint 5 hasn't landed).
- No marketing copy: no "win rate" framing, no cherry-picked windows, no
  hiding the dormant options subsystem's staleness.
- No real-time dashboards/streaming; render-time reads are sufficient at
  this scale.
- Not an admin observability replacement — `/v2/admin/observability` stays
  the operator debugging surface; the Trust Center is the *accountability*
  surface.
