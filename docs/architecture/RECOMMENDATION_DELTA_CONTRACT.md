# Recommendation Delta Contract — "What changed?" (Wave 1C)

Status: BUILT in dev, flag-off · zero-migration, read-only ·
Branch `feature/elite-arthos-provable-ideas` · Rule set `delta-1`.
Companions: `RECOMMENDATION_PUBLICATION_PREFLIGHT.md` (pf-2),
`RESEARCH_SAFE_MODE.md` (posture facts consumed here).

## Purpose

One read endpoint that lets a beginner answer: is this new? did the action
change? did evidence strengthen or weaken? did risk increase? how did the
stored price move between reads? did freshness/limitations/posture change?
Never implies causation, certainty, or hindsight not stored at the time.

## Authoritative prior-selection rule

Canonical asset for a symbol = the asset of the LATEST recommendation among
assets sharing that symbol, ordered by `(generated_at DESC, id DESC)`.
Prior = the recommendation for the SAME asset_id strictly earlier by the
tuple: `(generated_at, id) < (cur.generated_at, cur.id)`, same ordering,
LIMIT 1.
Why the tuple: dev history contains 14k+ real same-timestamp sibling groups
(historical dual-scheduler era); calendar-day or timestamp-only selection is
ambiguous there. The tuple is total and deterministic, stable under
pagination and concurrent inserts, can never select the row itself, a newer
sibling, or a cross-asset row (pinned by pg tests incl. same-timestamp
tie-break, three-row chains, duplicate symbols across assets, future-dated
rows).

## Delta categories (all server-owned templates; stored narrative never echoed)

1. **First appearance** — no prior → `first_seen`, "This is a new idea from
   ArthOS.", zero invented changes.
2. **Action change** — neutral copy ("ArthOS moved from Buy to Hold. The
   recommended action became more cautious/constructive"); no causal market
   claims. Rank Buy>Hold>Trim>Sell decides cautious vs constructive.
3. **Confidence presentation** — labels compared through the wording policy
   IN FORCE AT EACH ROW'S generated_at (`WORDING_CUTOVER = 2026-07-11`):
   pre-cutover rows render legacy "high/medium/low confidence"; post-cutover
   High/Medium render "meets the buy bar". History is never rewritten with
   today's copy (pinned).
4. **Evidence families** — stored `family_scores` only (verified live set:
   `trend_momentum`, `volatility_risk`, `exposure`; unknown keys degrade to
   de-underscored names). Uniform engine sign convention: >0 supportive,
   <0 cautionary. Direction from delta sign; magnitude buckets below; new
   family → "New supporting/cautionary evidence appeared…"; removed →
   "…no longer part of the case"; missing ≠ zero (zero compares normally);
   NaN/Infinity/malformed → explicit `family_unavailable`, never a
   direction.
5. **Evidence balance** — more_supportive / more_cautious / mixed /
   unchanged from the count of material family moves; never converted into
   a return forecast.
6. **Price context** — the honest slice: each row's own STORED price
   (`recommendation_outcome.price_at_recommendation`, else the newest
   stored 1d bar at-or-before its generated_at) compared between the two
   reads, bucketed. **Plan-zone comparisons (entry/target/exit proximity)
   are UNAVAILABLE by design in this slice**: plan corridors are derived
   client-side and not persisted — recomputing them server-side would be
   present-day recomputation. Documented limitation; revisits when plan
   values are persisted. Exit/target *crossings* ARE covered via stored
   outcome barriers (below). Never fetches live prices.
7. **Freshness/system state** — stored `stale_data` flag change; persisted
   preflight limitation set added/removed; persisted posture change
   (posture event current at each verdict's evaluated_at). Absent persisted
   facts → silent/"not evaluated" — the delta service NEVER triggers a
   preflight or posture evaluation and never writes (pinned: row counts
   unchanged + module-source assertion).
8. **Thesis revision** — OMITTED: theses link to assets, not to
   recommendation revisions; no reliable stored link exists, so the
   category is absent rather than fabricated (`thesis_revision: null`).
9. **Outcome status** — stored barrier only: 1 → "reached its target
   zone", -1 → "reached its exit condition", 0 → "resolved by reaching its
   time limit", NULL → open (silent). Anything richer belongs to Decision
   Replay (Wave 1D).

## Materiality policy (`delta-1`; changing thresholds bumps the version)

Family score |Δ|: <0.05 unchanged · <0.15 small · <0.35 meaningful · else
large. Stored-price move %: <0.3 unchanged · <1.5 small · <4 meaningful ·
else large. Change cap: 8. Ordering: fixed priority (action=1,
outcome/large-price=2, evidence-balance=3, posture/freshness/limitation=4,
confidence/family-appearance=5, family moves=6) then significance then id —
byte-deterministic (pinned).

## Summary selection

Top ordered change decides one sentence (action → "ArthOS became more
cautious/constructive…", outcome → its text, balance → "The main action is
unchanged, but the evidence …", posture/freshness/limitation → its text,
price → its text); zero material changes → "The evidence is broadly
unchanged since the previous update."; no prior → new-idea copy. Never a
concatenated list.

## API

`GET /api/recommendations/{symbol}/delta` — mounted only when
`REC_DELTA_ENABLED` (default False: route absent, recommendation responses
byte-compatible, zero extra queries, no frontend section). Symbol shape is
validated before any query (enumeration probes 404 cheaply). Response:
`{symbol, rule_set_version, current_as_of, prior_as_of, first_seen,
summary, changes[{id, kind, direction, significance, beginner_text,
source}], evidence_balance, price_context, freshness_context, limitations,
thesis_revision:null}` — never recommendation UUIDs, asset ids, snapshot
hashes, git SHAs, job ids, raw preflight checks, raw family-score maps,
provider errors, or owner identity (pinned unit + pg redaction tests).

## Caching & performance (measured on the real dev dataset)

Identity-keyed bounded LRU (256 entries): key = rule-set version + current
rec id + verdict + limitations + posture + outcome states + prior rec id —
a new recommendation/verdict/posture/outcome produces a NEW key, so a stale
cache is impossible by construction (pinned: new insert invalidates).
Query bound per delta ≤10 (event-listener test). Measured: **127 ms cold /
7–9 ms warm** on GE (447-row history).
Related read-path fix shipped with this slice: the preflight per-request
cap now bounds COLD EVALUATIONS only — verdict lookups are uncapped and
capped-out candidates fail closed to HOLD instead of being silently
dropped (found live: the confidence-sorted 500-limit Discover request was
truncating the desk to 250; regression-pinned).

## Frontend

PickPage: "What changed since the previous update" section in narrative
slot 4 — one summary, compared-with line, top 3 changes with glyph+sr-only
direction labels (never color-only), `<details>` for the rest (keyboard
native), no raw metrics, no animation; renders nothing when the flag is
off. Discover: one compact note on the FEATURED card only, only when
genuinely meaningful (`compactChangeNote`). Today/Briefing: the
what-changed strip gains the top idea's real one-liner; aggregate counts
untouched. Research Inbox: `formatSupersedesNote` helper exported for Wave
2 — Inbox workflow not expanded here. Mobile 390 px verified (no
horizontal overflow); 200 % zoom inherits the earlier verified layout.

## Security review

Symbol-shape gate; comparisons locked to one canonical asset; stored score
maps strict-parsed (NaN/Infinity → unavailable); future-dated rows simply
become "current" (never a prior of themselves — pinned); same-timestamp
duplicates tie-broken by id; cache staleness impossible by identity key;
no hidden diagnostics in the payload; all user-facing text from server
templates (stored thesis/evidence narrative never echoed → no language
injection); historical wording preserved; zero recomputation with
present-day data (module has no engine imports, no provider calls, no
INSERT/UPDATE/DELETE — source-pinned).

## Rollback

Flag off → route unmounted, sections/notes absent, zero queries. No
migration to reverse.

## Production evidence gates

1. Existing promotion plan Stage B first (unchanged critical path).
2. Preflight + Safe Mode promoted (delta consumes their persisted facts;
   without them freshness/posture categories stay honestly silent).
3. One week of dev deltas over real nightly generations with owner copy
   review of every emitted template.
4. Separate approval for the prod flag.

## Tests (green 2026-07-13)

39 unit (first-seen, action matrix, historical wording, score + price
threshold boundaries exact, family add/remove/missing-vs-zero/malformed,
balance summaries, outcome statuses, freshness/limitation/posture changes,
deterministic ordering + cap, redaction, no-material-change) · 12 pg
(prior-selection chains, same-timestamp tie-break, cross-asset isolation,
future-dated rows, first-seen, no-writes + source pin, persisted
preflight/posture association without evaluation, not-evaluated fallback,
cache invalidation on new insert, payload redaction with real ids, flag-off
structure, query bound) · +1 preflight-cap regression · 7 web (states,
disclosure visibility, direction sr-labels, compact notes, supersedes
helper, no diagnostics). Full gates: tsc, eslint, lint:portfolio,
production build, 256 vitest.
