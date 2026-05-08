# UX-5B — Overview redesign (plan-only review)

**Status:** plan-only. **No code in this phase.** Awaiting
explicit "begin implementation" before any file changes.

UX-5B replaces the homepage with the six-question Layer-1
Copilot surface defined in
`docs/research/UX_5_PROGRESSIVE_ABSTRACTION.md` §6, governed by
the eight architectural locks in §12 of the same document.

The current `/overview` (Bloomberg-style elite terminal, ~85%
Layer 3) moves to `/overview?view=working` unchanged. **No
deletion.**

---

## 0. Locks this plan inherits

(Quoting only the locks that bind UX-5B specifically — full set
in `feedback_ux5_locks.md`.)

* Nav = Today / Holdings / Ideas / Working
* No charts above the fold (Strategic lock C)
* Today answers ONLY 6 questions; 6 blocks max (Strategic lock A)
* Working stays visible top-level (Decision 4)
* "See the working" is the only working-link copy (Decision 7)
* Lint scope expands to every Layer-1 / Layer-2 file (Decision 8)
* Banned vocabulary list (UX-5 §3 + UX-5 §12 Decision 8)

---

## 1. The six questions (and their L1 mapping)

| # | Question | Layer-1 block | Truth source |
|---|----------|---------------|--------------|
| 1 | What matters today? | Greeting + 1-line **today line** | regime + pipeline state |
| 2 | What's open? | **Holdings sentence** + link to /portfolio?view=brief | open paper_position count + simple movement aggregate |
| 3 | What opportunities exist? | **Today's ideas** (≤ 3 cards) | candidate_idea + recommendation top picks |
| 4 | What changed? | **What changed** (1–3 bullets) | day-over-day deltas vs yesterday's snapshot |
| 5 | What risks matter? | **Risk line** (only when triggered) | drawdown ≥ 5% OR stress regime OR paused strategy |
| 6 | What should I watch? | **Watch this week** (compact list, no charts) | upcoming earnings + macro events |

Six blocks, in this order. **Block 5 is conditional** — if
no risk condition triggers, the block is silent (the page
contracts).

---

## 2. Page mockup — desktop (1280px max, 720px column)

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   Good morning.                                       [time] │   greeting only
│                                                              │
│   The system reviewed today's market activity.               │   today line, 2 sentences max
│   Markets are calm today.                                    │
│                                                              │
│   ────────────────────────────────────────                   │
│                                                              │
│   What's open                                                │
│   3 paper positions. Two are quietly working;                │
│   one is approaching its target.                             │
│                                                              │
│   See my holdings →                                          │
│                                                              │
│   ────────────────────────────────────────                   │
│                                                              │
│   Today's ideas                                              │
│                                                              │
│   AAPL  · Day 0                                              │
│   Entry zone reached. Pullback into support held.            │
│                                                              │
│   NVDA  · Day 0                                              │
│   Building a base near the 50-day average.                   │
│                                                              │
│   MSFT  · Day 0                                              │
│   Momentum easing into earnings later this week.             │
│                                                              │
│   See all ideas →                                            │
│                                                              │
│   ────────────────────────────────────────                   │
│                                                              │
│   What changed                                               │
│   • Two new ideas appeared overnight.                        │
│   • One position is approaching its target.                  │
│                                                              │
│   ────────────────────────────────────────                   │
│                                                              │
│   What to watch this week                                    │
│   • Earnings: AAPL Thu, MSFT Wed                             │
│   • Fed minutes Wed                                          │
│                                                              │
│   ────────────────────────────────────────                   │
│                                                              │
│   Read-only research — paper trading only.                   │
│                                                              │
│   See the working →                                          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

When the risk condition triggers (drawdown ≥ 5% / stress regime /
paused strategy), Block 5 inserts between Block 4 and Block 6:

```
   What needs attention                                       
   The account is 7% below its peak this week.                
   Markets remain unstable today.                             
                                                              
   ────────────────────────────────────────                   
```

When EVERYTHING is silent (quiet day, no positions, no ideas,
no risk), the page contracts to:

```
   Good morning.                                       [time]
                                                              
   Quiet day. Nothing pressing today.                          
                                                              
   ────────────────────────────────────────                   
                                                              
   Read-only research — paper trading only.                    
                                                              
   See the working →                                           
```

---

## 3. Mobile mockup (390px)

Same six-block stack. No grid. No multi-column. Same column width
(content area shrinks to ~342px). Idea cards collapse to one line
per card under 480px (symbol + Day + truncated observation).

```
┌────────────────────────────────────┐
│                                    │
│   Good morning.                    │
│                                    │
│   The system reviewed today's      │
│   market activity. Markets are     │
│   calm today.                      │
│                                    │
│   ──────────────────────────────   │
│                                    │
│   What's open                      │
│   3 paper positions. Two are       │
│   quietly working; one is          │
│   approaching its target.          │
│                                    │
│   See my holdings →                │
│                                    │
│   ──────────────────────────────   │
│                                    │
│   Today's ideas                    │
│                                    │
│   AAPL · Day 0                     │
│   Entry zone reached.              │
│                                    │
│   NVDA · Day 0                     │
│   Building a base near 50-day.     │
│                                    │
│   MSFT · Day 0                     │
│   Momentum easing into earnings.   │
│                                    │
│   See all ideas →                  │
│                                    │
│   …                                │
│                                    │
└────────────────────────────────────┘
```

---

## 4. Routing — what changes

| URL | Today | After UX-5B | Behavior |
|-----|-------|-------------|----------|
| `/` | redirects to `/overview` | redirects to `/overview` | unchanged |
| `/overview` | current Elite Terminal | **new Layer-1 Copilot Overview** | flipped |
| `/overview?view=working` | n/a | **current Elite Terminal preserved verbatim** | added |

Pattern matches Phase B's `/portfolio` switch. `OverviewRouteSwitch.tsx` reads `?view=` via `useLocation`, defaults to Layer-1 view, returns the Working view only when `?view=working`.

Default flips immediately in UX-5B (different from Phase F's deferred flip on Portfolio — there's no parallel "Working is the production default" period for Overview because the Layer-1 redesign is the new product reality).

---

## 5. New files

| Path | Purpose |
|------|---------|
| `apps/web/src/pages/copilot/CopilotOverview.tsx` | The new Layer-1 page — six blocks |
| `apps/web/src/pages/copilot/OverviewRouteSwitch.tsx` | `?view=` switcher; default = Copilot, `?view=working` = current Overview |
| `apps/web/src/components/copilot/TodayLine.tsx` | Block 1 — greeting + today line |
| `apps/web/src/components/copilot/HoldingsSummary.tsx` | Block 2 — observation sentence + link |
| `apps/web/src/components/copilot/TodaysIdeas.tsx` | Block 3 — ≤ 3 idea cards (Layer-1, no scores) |
| `apps/web/src/components/copilot/IdeaCard.tsx` | Per-idea card primitive used by Block 3 (and later Phase D options) |
| `apps/web/src/components/copilot/WhatChangedBlock.tsx` | Block 4 — observational deltas |
| `apps/web/src/components/copilot/RiskLine.tsx` | Block 5 — conditional risk surface |
| `apps/web/src/components/copilot/WatchThisWeek.tsx` | Block 6 — earnings + macro events |
| `apps/web/src/lib/copilot/overview_derive.ts` | Pure deterministic composer for the six blocks |
| `apps/web/src/lib/copilot/overview_copy.ts` | Locked strings + templates for Overview |
| `apps/web/src/lib/copilot/__tests__/overview_derive.test.ts` | Unit coverage for the composer |

## 6. Modified files

| Path | Change |
|------|--------|
| `apps/web/src/App.tsx` | `/overview` route swaps to `OverviewRouteSwitch`; `Overview.tsx` import becomes lazy/internal-only |
| `apps/web/scripts/lint-copilot-copy.mjs` | Scope expansion (Decision 8) + new banned tokens (UX-5 §3 + Decisions 6, 7) |
| `apps/web/src/components/shell/Shell.tsx` | Nav retraction → Today / Holdings / Ideas / Working (other items move to a tertiary "Working surfaces" footer block; visible but not in primary nav) |
| `apps/web/src/lib/copilot/copy.ts` | Add `OVERVIEW_COPY` block with locked greeting / today-line / what-changed / risk / watch templates |

## 7. Files explicitly NOT touched

* `apps/web/src/pages/Overview.tsx` — preserved verbatim, becomes Working view
* `apps/web/src/pages/PortfolioTerminal.tsx`
* `apps/web/src/pages/Decisions.tsx`, `AlphaLab.tsx`, `MLLab.tsx`, `RiskDashboard.tsx`, `Ops.tsx`, `ResearchLab.tsx`, `AgentWorkflows.tsx`
* `apps/web/src/pages/options/*` — every options sub-page
* All non-frontend code (no backend, no DB, no schema, no migration, no scheduler, no execution logic)

---

## 8. Block-by-block deterministic composition

Every Layer-1 sentence on the new Overview is composed by a pure
function from existing engine state. **No LLM. No fabrication.**
Each output carries a `data-source` attribute naming the inputs.

### Block 1 — today line

Input: `regime.label`, `pipeline.status`, `as_of_date`.

Templates (regime → calm sentence):

```
calm        → "Markets are calm today."
trending    → "Markets are moving with direction today."
choppy      → "Markets are bouncing around today."
stress      → "Markets remain unstable today."
unknown     → (omit)
```

If `pipeline.status == failed`: replace today line with
"We're catching up. Open *See the working* below."

Greeting: time-of-day from user's local clock, three values:
`Good morning.` (00:00 – 11:59), `Good afternoon.` (12:00 – 17:59),
`Good evening.` (18:00 – 23:59).

### Block 2 — holdings summary

Input: `count(open paper_position)`, `count(approaching_target)`,
`count(stable)`.

Templates:
```
0 positions     → "No open paper positions today."
1 position      → "1 paper position. {state-clause}."
N positions     → "{N} paper positions. {state-clause}."

state-clause variants (deterministic by counts):
  all stable                  → "All quietly working"
  one approaching target      → "Two are quietly working; one is approaching its target"
  all approaching             → "All are approaching their targets"
  one needs attention         → "One needs attention"
```

The "approaching target" computation depends on mark prices being
wired. Until then the state-clause omits and renders only the
count.

### Block 3 — today's ideas

Input: top N=3 candidate_ideas where `accepted=true` AND
`buy=true` AND symbol not in any open holding.

Per idea card composition:
```
Symbol  · Day 0
{observed-state-sentence}.
```

Banned per-idea content: scores, confidence percentages, engine
identifier, signal name, regime label, gate status. **Only an
observational sentence about the chart context.**

`observed-state-sentence` library (deterministic from the
candidate row's existing fields):
- "Entry zone reached." (price within entry range)
- "Pullback into support held." (recent low close to a moving avg)
- "Building a base near the {N}-day average." (consolidation)
- "Momentum easing into earnings later this week." (earnings within 5 days)
- "Recently moved." (significant 1-day price change)

If the row's data does not match any template, the card is silent
(omitted, not "—" or placeholder).

### Block 4 — what changed

Input: yesterday's snapshot vs today's. At most 3 deterministic
deltas.

Templates:
- `new_ideas_24h > 0` → "{N} new idea(s) appeared overnight."
- `position_state_changed` → "One position is approaching its target."
- `position_closed_today > 0` → "{N} position(s) closed today."
- `regime_changed` → "Markets shifted from {prev} to {now}."

If no delta condition triggers, Block 4 renders one
observational sentence: "Today looks much like yesterday." (Once
per quiet day; suppressed under one-time `ux_seen_quiet_what_changed`
onboarding flag — see UX-3D's onboarding pattern.)

### Block 5 — risk line (conditional)

Triggers (any one):
- `drawdown_from_peak ≤ -0.05` → "The account is {abs}% below its peak this week."
- `regime == stress` → "Markets remain unstable today."
- `paused_strategy_count > 0` → "{N} strategy paused itself today."

Multiple triggers → up to 2 sentences, then truncate.

If no trigger: block does not render. Empty space, not silence
chip.

### Block 6 — watch this week

Input: upcoming earnings + macro events from existing data
(catalyst_calendar table or similar). Filter to next 7 days.

Format:
```
Earnings: {SYM1} {Day1}, {SYM2} {Day2}
{Macro event} {Day}
```

Cap at 3 lines. If empty: block omitted.

---

## 9. Lint expansion (UX-5A, bundled into UX-5B PR)

Current scope: `apps/web/src/lib/copilot/` + `apps/web/src/components/copilot/`.

New scope (Layer-1 / Layer-2 surfaces):
- `apps/web/src/pages/copilot/**` (Brief view, new Overview)
- `apps/web/src/components/copilot/**`
- `apps/web/src/lib/copilot/**`

Working exemption (preserved):
- `apps/web/src/pages/Overview.tsx` (now `?view=working`)
- `apps/web/src/pages/PortfolioTerminal.tsx`
- `apps/web/src/pages/Decisions.tsx`, `AlphaLab.tsx`, `MLLab.tsx`, `RiskDashboard.tsx`, `Ops.tsx`, `ResearchLab.tsx`, `AgentWorkflows.tsx`
- `apps/web/src/pages/options/**`
- `apps/web/src/components/operator/**`
- `apps/web/src/components/overview/**` (legacy Overview pieces)
- All other components used only by Working surfaces

New banned tokens (extends current list):
```
signal, batch, regime, gate, anomaly, pipeline, ingest, replay,
fill, guard, scheduler, cron, snapshot, advisory, engine, pending,
cycle, runner, stage, module, as_of, submitted_at,
days held, days in,
View the analysis, Open the rationale, See details,
Open diagnostics, Read rationale,
Read the full reasoning  (already banned)
```

Rule the lint enforces: a banned token in a non-exempt path
fails the build.

Doc-reference exemption stays the same — lines containing
`banned`, `forbidden`, `never`, `avoid`, `anti-` are allowed to
mention the token for documentation purposes.

---

## 10. Implementation phasing within UX-5B

Each row is a separate commit. Reversible. Visually testable.

| Step | Scope | Risk |
|------|-------|------|
| **B-1** | `OVERVIEW_COPY` + `overview_derive.ts` + tests (no UI mounted) | None — additive |
| **B-2** | All 6 block components + IdeaCard primitive (still no page mount) | Greenfield UI; tested in isolation |
| **B-3** | `CopilotOverview.tsx` + `OverviewRouteSwitch.tsx` (mounted; `?view=working` available) | Route swap on `/overview` |
| **B-4** | Lint scope expansion + new banned tokens + exemption list | Catches regressions; build-time |
| **B-5** | `Shell.tsx` nav retraction → 4 items; legacy items move to footer | Nav-level UX change |
| **B-6** | Responsive verify (390 / 768 / 1280) + lint:copy + build + backend tests | Verification only |

B-1 through B-3 ship the new Overview live behind the route
swap. B-4 + B-5 lock the discipline. B-6 is verification.

Stash from UX-2 Phase C-2 (typography ramp) does NOT resume here.
It resumes inside UX-5C (Portfolio Phase F + leakage purge) per
the UX-5 phase order.

---

## 11. Truthful fallbacks (UX-5B specific)

| Data missing | Behavior |
|--------------|----------|
| `regime.label` unavailable | omit today-line second sentence; render greeting + Block 2 normally |
| `pipeline.status` unavailable | treat as "ok" — never falsely surface a "we're catching up" warning |
| Position counts unavailable | Block 2 absent (the link to /portfolio still appears via nav) |
| candidate_idea empty | Block 3 absent |
| What-changed deltas unavailable | Block 4 absent (no "—") |
| Risk triggers absent | Block 5 absent (correct intended behavior) |
| Catalyst data unavailable | Block 6 absent |
| ALL absent | Page renders Greeting + "Quiet day. Nothing pressing today." + footer |

NEVER renders placeholder copy. NEVER fills with "—". NEVER pads
the page.

---

## 12. Banned content on the new Overview

Direct lint enforcement plus visual review during B-3:

- No charts, no equity curves, no drawdown sparklines
- No counters / chips / badges
- No tickers list
- No P/L numbers above the fold (P/L appears later in Block 2's
  state-clause if at all, and only in proportional language —
  never raw $)
- No engine identifiers (engine A / B)
- No regime label as raw word ("stress", "trending") — only as
  composed sentence
- No gate counts ("3/4 passing")
- No "advisory" / "shadow" / "pending"
- No replay vocabulary
- No scheduler vocabulary

---

## 13. Observation discipline reminder

UX-5B is the abstraction landing. Per
`feedback_observe_before_polish.md`, after UX-5B ships:

1. Observe `/overview` over at least one full daily-loop cycle
   on real fresh data (scheduler stable since 2026-05-08 fix).
2. Watch:
   - greeting appropriateness (do users see "Good evening" at
     the right local time?)
   - today-line tone across regime states
   - idea-card observed-sentence quality (do the templates
     pick the right one?)
   - what-changed cadence (does it feel calm or noisy?)
   - quiet-day collapse rhythm
   - mobile pacing at real list lengths
3. Only resume UX-5C (Portfolio Phase F + UX-2 C-2 typography
   ramp) after observation.

---

## 14. Success criteria

UX-5B succeeds when:

- Default `/overview` shows greeting + at most 5–6 short blocks.
- No engine vocabulary anywhere on the page.
- `/overview?view=working` preserves the existing Elite Terminal
  verbatim.
- Lint scope expanded; banned tokens ship in the same PR.
- 4-item nav (Today / Holdings / Ideas / Working) renders with
  Working visually secondary.
- Quiet-day fallback collapses cleanly.
- All build / lint / unit tests pass.
- No backend changes, no DB changes, no schema drift.

UX-5B fails if:

- Any banned token reaches a Layer-1 file.
- Any chart appears above the fold on default `/overview`.
- The page surfaces more than the six approved blocks.
- The Working view becomes inaccessible.

---

## 14b. Locked refinements (applied 2026-05-08 after approval)

These refinements were approved alongside the six asks. They
override anything earlier in this document.

### R-A — Block 3 stays observational ALWAYS

The "Today's ideas" block carries the highest emotional risk.
Banned absolutely — even with deterministic derivation:

* scores (numeric or letter)
* rankings ("top pick", "best idea", "ranked #1")
* confidence percentages
* "high-confidence", "strong setup", "high-conviction"
* urgency language ("act now", "today only", "limited window")
* superlatives ("strongest", "biggest", "hottest")

Allowed observational templates (chart-context, not directive):
* "Energy stocks continued strengthening."
* "Healthcare remained stable during today's weakness."
* "Pullback into support held."
* "Building a base near the {N}-day average."
* "Momentum easing into earnings later this week."
* "Recently moved."

### R-B — Quiet days are first-class (NOT an edge case)

Quiet-day behavior may become the defining emotional trait of
the product. Most investing products feel anxious, performative,
desperate for activity. This product should feel **comfortable
being quiet**.

Implementation contract:
- Quiet day output is NOT a fallback. It is a first-class
  rendering path with its own deterministic templates.
- The quiet-day greeting + sentence varies by date (cadence
  rotation per UX-3D pattern) so a returning user does not see
  the same exact line two days running.
- The page width, spacing, and footer still feel intentional —
  not "loading", not "empty state", not "skeleton".

### R-C — Block 4 stays tiny

What-changed renders 1–3 sentences max. Each sentence ≤ 80
characters. Banned in this block:
- changelog format ("Added X. Removed Y. Updated Z.")
- analytics summaries ("Realized vol fell 12%, breadth widened
  to 64%, …")
- commentary paragraphs

Allowed style:
* "Technology exposure increased slightly."
* "Two positions closed this week."
* "Most holdings stayed near recent ranges."

### R-D — Block 6 translates events to watchfulness

NEVER expose:
- raw earnings calendar entries
- macro event codes (CPI, FOMC, NFP)
- economic schedule infrastructure

Translation map (lives in `overview_copy.ts`):

| Event code | Watchfulness phrase |
|------------|---------------------|
| CPI | "Inflation data arrives {Day}." |
| FOMC | "The Fed meets {Day}." |
| NFP | "Jobs data lands {Day}." |
| ECI | "Wage data updates {Day}." |
| GDP | "Growth figures publish {Day}." |
| Earnings ({SYM}) | "{SYM} reports {Day}." |
| ECB | "The European central bank meets {Day}." |
| BOJ | "The Japanese central bank meets {Day}." |

Anything not in the map omits silently. NEVER fall back to the
raw event code.

### R-E — Empty blocks collapse, never render placeholder

If a block has nothing truthful to render, it does not render.
Specifically forbidden:
- empty card with header + "Nothing to show"
- skeleton loader after data resolves to nothing
- "No ideas yet" / "Check back later" copy
- divider + empty space

Acceptable:
- block + content gone entirely; subsequent block moves up
- on a fully-quiet day, the page collapses to just greeting +
  one sentence + footer (per R-B)

Implementation contract: every block component returns `null`
when its data is empty. The parent page composes via
conditional fragments, NOT via constant headers + variable bodies.

### R-F — 30-second scan target

The Today page should feel:
* fast to scan
* emotionally light
* low-pressure
* low-anxiety
* low-fatigue

Specific implications:
- Total reading length on a normal day: ≤ 200 words above the
  fold, ≤ 350 total.
- Block 3 (ideas) caps at 3 cards, each ≤ 60 chars observation.
- Block 4 caps at 3 sentences.
- Block 6 caps at 3 watchfulness lines.
- No nested expansion within Today (all detail lives via the
  links to Holdings / Ideas / See the working).

### R-G — Cadence variation (deterministic, sparse, subtle)

Deterministic does NOT mean emotionally repetitive. Each
template family has 2–4 variants. The variant index is a pure
function of the local date so a returning user sees subtle day-
to-day variation. Same pattern as UX-3D §3 quiet-hero variants.

Variation rules:
- ROTATES: greeting alternates per day (`Good morning.` /
  `Morning.` — 2 variants)
- ROTATES: today-line for each regime has 2 variants
- ROTATES: quiet-day sentence has 3 variants
- DOES NOT ROTATE: idea observations (each idea picks the one
  template matching its data; rotation across days would feel
  random)
- DOES NOT ROTATE: what-changed deltas (deterministic from data,
  variation comes from the data itself)

### R-H — Temporal cue locked: "Today" for ideas, "Day N" for held

Per Decision 6 + the post-review refinement:

| Context | Cue |
|---------|-----|
| Held position, opened today | "Opened today" |
| Held position, N days held | "Day N" |
| Fresh idea on Today page | "Today" |
| Fresh idea, no temporal context computable | (omit) |

"Day 0" is BANNED — too mechanical for ideas that haven't yet
become commitments. The lint adds it to the banned list.

---

## 15. Awaiting approval

This is a plan-only review. No code changes have been made.

Please confirm:

1. **Approve the six-block structure** as drafted (greeting +
   today line / holdings / ideas / what changed / risk
   conditional / watch).
2. **Approve the file scope** (10 new files, 4 modified, 0
   deletions).
3. **Approve the deterministic composition rules** (regime →
   today line; counts → state-clause; conditional Block 5;
   quiet-day collapse).
4. **Approve the lint expansion list** (new banned tokens +
   exempted Working paths).
5. **Approve the B-1 → B-6 phasing** (each as a separate
   reversible commit).
6. **Confirm "Day 0" is the right cue for fresh ideas** (per
   Decision 6 — Day N applies to held positions; do ideas use
   Day 0, "Today", or omit the temporal cue altogether?).

Refinements welcome inline. After approval I implement B-1 →
B-6 sequentially with stop-points between commits.

UX-2 Phase C-2 typography stash remains intact, awaiting
UX-5C.
