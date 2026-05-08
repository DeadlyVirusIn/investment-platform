# UX-6 — AI Investing Copilot Master Plan

**Status:** master synthesis. Locked after a four-way debate
between Gemini 2.5 Pro · Codex · Claude Opus 4.7 · Claude
Sonnet 4.6 (substituting for the requested Sonnet 4.7 — latest
in the family). Three rounds: Round 1 independent positions ·
Round 2 sharp critique + revise · Round 3 challenge the
synthesis. Full transcripts archived at
`.debate/ux6_copilot_20260508-143540/`.

This document supersedes the earlier UX-5 / UX-5B planning
on every point where it differs. UX-2 / UX-3 / UX-4 / UX-5
work shipped to date stays valid; UX-6 is the architectural
capstone the next phases lock against.

---

## 1. Product identity

**A daily editorial briefing with inspectable depth.**

Closer to *Stratechery + Apple Health + a private weekly
analyst letter* than to Bloomberg, Perplexity, or Linear. The
emotional register is **calm authority.** Not excitement.
Not urgency. Not stimulation.

The user comes back daily because the page **respects their
time** — every day's view is short, specific, observed, and
different from yesterday in ways that matter.

The unfair-comparison reference is *not* "Perplexity but for
finance" (chat-driven), *not* "Linear for portfolios"
(workspace-driven), *not* "Robinhood with AI" (engagement-
driven). The product is patient. There are no notifications,
no streaks, no engagement loops, no push.

---

## 2. Primary AI surface — Read · Evidence · Action · See the working

The single load-bearing pattern. Codex Round 2 named it;
Round 3 refined it; all four models converged on it.

Every AI object in Layer 1 has up to four tiers:

```
   ┌─────────────────────────────────────┐
   │  READ                                │  one paragraph, observed prose
   │  ─────                               │
   │  Evidence  ▸                         │  expand → structured proof
   │                                      │
   │  Action  →                           │  one explicit path (or "nothing")
   │                                      │
   │  See the working  →                  │  full operational depth
   └─────────────────────────────────────┘
```

### Object typing (Codex R3 — locked)

Layer 1 objects are typed before they render. Allowed types:

| Type | Action required | Example |
|------|-----------------|---------|
| **Brief** | None | Daily today-line summary |
| **Observation** | None — orientation only | "Cash drag increased this week." |
| **Decision** | One explicit user action + expiry | "AAPL idea — entry zone reached, expires Friday close" |
| **Exception** | One explicit operator action | "One position is approaching its target — review" |

**Action-affordance ban on Briefs and Observations.** The
synthesis previously implied every Read needs an action. It
does not. Manufacturing fake decisiveness is a worse failure
mode than under-action.

### Evidence rules (Opus R3 + Gemini R3 — locked)

When the user clicks the Evidence chevron on any Read, the
expand reveals AT MOST 3 elements:

1. Up to 3 listed source rows in compact sentence form
   ("AAPL +1.4% on May 7", "Position weight: 8% of portfolio",
   "Decision window: closes Friday").
2. ONE sentence stating the rule that fired ("Pullback into
   support held when day low touches the moving average and
   closes above it").
3. The deterministic origin string from the composer's
   `dataSource` (audit trail, small text).

**Evidence is data-driven micro-disclosure, NOT more prose.**
Allowed inside Evidence: dates, percentages, source rows,
sparkline ≤ 80px wide, position weight, decision-window
countdown. Banned: scores, confidence percentages, ranked
attribution, "AI thinks" framing, compound narrative paragraphs.

### Numeric visibility contract (Codex R3 — locked)

Layer 1 may show **at most ONE numeric anchor per Read**, only
when the number changes the interpretation of the sentence.

| Allowed Layer-1 numeric roles | Banned in Layer 1 |
|-------------------------------|-------------------|
| Distance from threshold | Comparative ranks |
| Time remaining in decision window | Scores |
| Position concentration | Model confidence |
| Drawdown from recent peak | Raw table values |
| Data freshness ("data through 2026-05-07") | Decorative metrics |

Evidence may show compact numeric facts in sentence form.
Working may show full tables, charts, raw values, operator
vocabulary.

Lint enforcement: the lint script gains rules to detect
numeric-density violations (>1 numeric token per Read on
Layer-1 surfaces).

---

## 3. Information hierarchy

### First sight

* **Greeting** + a one-paragraph composed Read for today
  (1–5 sentences depending on signal density — see
  composer triage rules below).
* No charts. No counters. No chips. No dashboard tiles.

### Below

* ≤ 4 short editorial sections (holdings sentence ·
  ideas · what changed · optional risk · watch).
* Each section is a Read; each expandable to Evidence.
* Page contracts on quiet days (Opus contribution — locked).

### Hidden deeper

* Every numeric output beyond Layer-1 anchors → Evidence or
  Working.
* Every chart → Working (no charts in Layer 1, ever).
* Every chip / badge / counter → removed.
* Every operator vocabulary item → Working.

### Visual emphasis

* Verbs in the prose ("approached," "softened," "held,"
  "appeared," "cooled").
* Numbers ONLY when semantically load-bearing (per the
  numeric visibility contract above).

---

## 4. Composer triage rules (Sonnet R3 — locked)

The "observed not authored" phrase needs operational rules.
On any contested day (no single dominant signal), the composer
applies this priority order:

1. **Open risk events** (earnings within 48h, expiry within 2
   sessions, position approaching max-loss threshold) take
   precedence over everything else.
2. **Largest absolute P&L change today** (NOT largest
   percentage — absolute dollar impact on the portfolio).
3. If neither (1) nor (2): the Read leads with **what changed
   versus yesterday's Read**, not with what is currently true.

### Density rules

* Quiet, unchanged day → 1 sentence Read.
* Normal day → 2–3 sentences.
* High-signal day → 4–5 sentences max.
* The composer must **never pad** a low-signal day to reach
  3 sentences. Sentence count IS a signal of information
  density — not a style choice.

### AI personality

* The AI never says "I."
* Observed-third-person prose only.
* Action verbs as voice signature.
* The AI declines to recommend on quiet days (Sonnet's
  "ideas expire" + Opus's "page contracts").

---

## 5. Navigation — 4 primary items + Working access model

### Primary nav (Layer 1 — locked at UX-5 D1)

```
Today  ·  Holdings  ·  Ideas  ·  Working
```

* **Today** — the editorial briefing
* **Holdings** — per-position story cards (existing Brief view)
* **Ideas** — curated daily opportunities with decision windows
* **Working** — transparent systems layer

Watchlist / Risk / Options do NOT have primary nav items.
Watchlist surfaces inside Today's "watch this week"; Risk
surfaces contextually inside Today / Holdings; Options idea
surfaces inside Ideas labelled "Higher-risk."

### Working access model (synthesis of Codex R3 + Sonnet R3 + Opus R3)

The Working page exposes a **focused subnav**, NOT a flat
10-item menu. Layout:

```
Working
─────────────────────────────────────
PRIMARY OPERATIONAL  (always visible, 4 items)
  Risk  ·  Watchlist  ·  Options  ·  Decisions

ADVANCED  ▸  (collapsed disclosure, default closed)
  Alpha Lab · Risk Dashboard · Ops · ML Lab · Research · Agents
```

### Routing + deep-link contract

* Each Working surface retains its existing URL as the
  canonical route. `/options`, `/options/chain`, `/decisions`,
  `/risk`, `/ml-lab`, etc. all continue to work.
* Deep links bypass the Working page entirely — power users
  bookmark `/options/chain` and reach it without trekking
  through Working.
* Back-navigation from a Working subnav page returns to the
  referring context (either Working overview OR the Layer-1
  page that triggered the link), not always to Working.
* State on Working subnav pages is NOT reset on subnav
  navigation — only on full page load to the canonical URL.

### Behaviour-pinned shortcut (Codex R3 — adopted)

If telemetry shows a user opens the same Working surface on
3 separate days within a 7-day window, that surface may appear
as a pinned secondary affordance from Today, **below** the
editorial Read and **outside** the primary nav. Pinned
affordances are user-behavioural, never globally promoted, and
must not use urgency copy.

This honours the active-options-trader 9:28am workflow without
bloating the primary nav and without permanent Working
promotion.

---

## 6. Screen-by-screen blueprint

### Today (`/overview`)

* **Purpose:** orient · decide if anything needs you today.
* **Emotional goal:** calm authority.
* **Layout:** 720px editorial column, single. Greeting →
  composed Read paragraph → ≤ 4 short editorial sections →
  footer with *See the working*.
* **Primary visual anchor:** the composed Read paragraph.
* **Glanceable:** Read (5-second scan).
* **Secondary:** ideas + what changed (15-second deepen).
* **Disappears:** every chart, table, counter, chip, badge.

### Holdings (`/portfolio?view=brief`)

* **Purpose:** see what's open + how each is evolving.
* **Emotional goal:** confident continuity.
* **Layout:** vertical list of position story cards (UX-2
  Phase B work, ready for Phase F default flip + UX-2 C-2
  typography ramp).
* **Glanceable:** symbol + Day N + one-line position state.
* **Secondary:** lifecycle ribbon + observation paragraph on
  expand.
* **Working access:** `/portfolio?view=working` →
  PortfolioTerminal preserved verbatim.

### Ideas (`/ideas` — to be built)

* **Purpose:** curated daily opportunities.
* **Emotional goal:** editorial curiosity, not urgency.
* **Layout:** ≤ 5 cards, each = symbol + one-sentence
  observation + visible decision window. Read · Evidence ·
  Action · See the working per card.
* **Glanceable:** symbol + 1-sentence observation + expiry
  date.
* **Disappears:** scores, confidence percentages, ranked
  positions, "top pick," conviction language. Sectors +
  earnings proximity stay (chart-context observations only).

### Watchlist — does not exist as a page

Folded into Today's "watch this week" block + per-symbol
catalyst chips on individual cards.

### Risk — does not exist as a page

Surfaces contextually as one sentence inside Today when a
trigger fires (drawdown ≥ 5%, paused strategy, stress context),
and one sentence inside Holdings when a position individually
crosses a threshold. Risk dashboards live in Working.

### Options — does not exist as a Layer-1 page

Surfaces inside Ideas labelled "Higher-risk." Full options
infrastructure (chain, observatory, framing, decisions, replay,
diagnostics, evaluation, performance) lives in Working.

### Working (`/overview?view=working` + subnav)

* **Purpose:** transparent systems layer for advanced users +
  operators.
* **Emotional goal:** precision, not calmness. Working is
  ALLOWED to feel terminal-like.
* **Preserved verbatim:** Elite Terminal at
  `/overview?view=working`. Decisions, Alpha Lab, Risk
  Dashboard, Options/* (13 pages), Ops, ML Lab, Research,
  Agents — all reachable via the Working subnav OR direct URL.
* **Visually distinct:** tertiary nav weight, slightly
  different background, NO editorial column constraint, full
  operator vocabulary. Reads as "the inspectable engine room."

---

## 7. AI personality + interaction model

### What the AI IS

* The composition of the page (Opus R1).
* The selection of which blocks render today and in what order
  (Opus R1).
* The voice in the prose templates + the cadence rotation.
* The discipline to omit when nothing truthful can be said.

### What the AI is NOT

* A chat dock.
* An "Ask AI" empty box.
* An animated insight carousel.
* A floating assistant button.
* A pulsing AI orb.
* A reasoning-timeline panel.
* A suggested-question chip rail.

### "Ask" / contextual query — explicitly cut from this scope

The synthesis no longer ships a per-position contextual Ask.
Round 3 critique (Opus + Gemini) flagged it as either an
unspecified behavioural-trigger or a chat-trojan-horse. If a
future phase needs scoped queries, Gemini's structured
Drill-down (3 pre-generated questions surfaced from an Evidence
card, no free-text input) is the only acceptable shape — but
that is a separate decision in a future phase, not in UX-6.

The single Layer-3 escape route remains *See the working* at
the page footer.

---

## 8. Visual language

* **Editorial column 720px** on every Layer-1 surface
  (centered, single column, eye flows downward).
* **Working surfaces** are NOT constrained to 720px. They
  retain full multi-column layouts.
* **Typography-dominant + dark-grounded** (Sonnet stance).
  Greeting is the only h1 per page; block headers are
  uppercase 11px tertiary; body 15px / 1.55.
* **Motion only when data-bound.** A 200ms text reveal when
  the morning Read recomposes after a regime shift. A delta
  value animating on a position card. NO decorative motion,
  NO parallax, NO ambient pulse, NO floating widgets.
* **No glassmorphism, no glow, no atmospheric gradients.** One
  near-imperceptible tint (≤ 0.025 alpha) on Featured surfaces
  only. The page must read beautifully with all atmosphere
  stripped.
* **One muted green and one muted red** — P/L only, Layer 2
  and below. Layer 1 has zero green / red.
* **Cards exist but look like blockquotes, not tiles.** A
  position story card is paragraph + hairline divider, not a
  boxed surface.

---

## 9. What makes the product "wow" without being gimmicky

* **The first paragraph composes differently every day** based
  on real engine state. The user feels read, not served.
* **The page contracts on quiet days** to one greeting + one
  sentence. Unprecedented in fintech UI; quiet days feel
  intentional.
* **Ideas expire** with visible decision windows. "This was
  better last week" is honest and builds trust faster than
  conviction percentages.
* **Read · Evidence · Action · See the working.** Four-tier
  transparency: ordinary users see the prose, careful users
  expand the evidence, operators see the working.
* **No notifications, no streaks, no engagement loops.** This
  alone differentiates from every other fintech product.
* **Working is allowed to feel like an engine.** The
  transparent depth IS the wow — users see the machinery is
  real.

What kills wow: gradients, glassmorphism, animated AI orbs,
suggested-question chips, "Powered by AI" anywhere, sparklines
above the fold, conviction percentages, ranked positions,
swipe gestures on financial decisions, "Start this story" /
"Conclude this chapter" copy on action buttons.

---

## 10. Migration roadmap

### Already shipped (UX-5B)

* B-1 — overview composers + copy ✓
* B-2 — six block components + IdeaCard primitive ✓
* B-3 — CopilotOverview mounted at `/overview` ✓
* OverviewRouteSwitch with `?view=working` preserving Elite
  Terminal verbatim ✓

### Next phases (UX-6)

| # | Scope | Risk |
|---|-------|------|
| **6A** | Lint scope expansion (UX-5 D8) + new banned tokens (object-typing names that are NOT user-facing, numeric-density check) | None — additive |
| **6B** | Nav retraction in `Shell.tsx` to 4 primary items (Today / Holdings / Ideas / Working). Routes to current legacy items move to Working subnav OR direct URL only. | Nav UX change |
| **6C** | Working subnav: 4 always-visible primary (Risk · Watchlist · Options · Decisions) + collapsed Advanced disclosure (6 items). Routing contract preserves all existing URLs. | UI change inside Working |
| **6D** | Object typing in `overview_derive.ts`: every composer output gains `kind: 'brief' | 'observation' | 'decision' | 'exception'`. Block components use `kind` to gate the action affordance. | Type-only change |
| **6E** | Composer triage rules: implement the priority order (open risk events → absolute P&L change → delta vs yesterday) and the density rules (1 sentence quiet, 2-3 normal, 4-5 max). | Logic-only |
| **6F** | Wire today's-ideas data into `TodaysIdeas` block. Each idea row from `candidate_idea` × `recommendation` mapped to `IdeaInput` with the existing observation templates. **Intermediate-state contract:** until the dedicated `/ideas` page lands (6H), each idea must include a visible decision window or be suppressed. (Sonnet R3 repair.) | Backend wiring |
| **6G** | Wire what-changed deltas from a new `daily_snapshot` table OR derive from `paper_run_log` row diffs. Cap at 3 sentences per the lock. | Backend feature |
| **6H** | Build `/ideas` page with full Read · Evidence · Action structure. ≤ 5 cards. Decision windows always visible. | New Layer-1 page |
| **6I** | Wire watch-this-week translations from existing catalyst data. Apply `WATCH_TRANSLATIONS` map; omit unknown codes silently. | Backend wiring |
| **6J** | Holdings Brief view → Phase F default flip. Resume UX-2 C-2 typography ramp + C-3 Featured archetype (currently stashed). | Visual polish |
| **6K** | Tone audit + lint sweep across every Layer-1 / Layer-2 surface against the locked banned-vocab list. | Verification |
| **6L** | Behaviour-pinned shortcut — telemetry instrumentation for `working_surface_opened` per route per day. Pin shortcut surfaces after 3 visits in 7 days. | Telemetry + UI |

### Rules binding every phase

* Plan-only review before each phase implements (UX-5
  discipline preserved).
* Each commit reversible, observable on real data, ≤ 1 day of
  work.
* No backend changes that alter trading invariants. Same-bar
  fills remain forbidden.
* C-2 typography ramp + C-3 Featured archetype DO NOT resume
  until 6A through 6E land — visual polish on a Layer-1
  surface that exposes the wrong abstraction is wasted.

---

## 11. Anti-patterns explicitly rejected

(Lint-enforceable banned list)

* Chat dock as primary AI surface.
* Cinematic hero panel.
* Ambient health Orb.
* Swipeable Instagram-stories Ideas.
* Conviction percentages, scores, "top pick" labels.
* Streaks, notifications, push, engagement counters.
* Equal-card dashboards.
* Multi-zone grids on Layer 1.
* Glassmorphism, atmospheric gradients, glow effects.
* Decorative motion of any kind.
* Suggested-question chips.
* "Powered by AI" anywhere.
* Empty placeholder blocks on quiet days.
* Same-bar paper fills (paper trading invariant).
* "Day 0" temporal cue (banned by UX-5 D6).
* Free-text "Ask the AI" input.
* "AI sticker on a dashboard" — adding a `<NarrativeBlock>`
  above an unchanged table is a regression. Lint failure
  (Opus R3 — adopted).
* Subnav menu inside Working with > 4 always-visible items
  and no Advanced disclosure.

---

## 12. Day-30 acceptance test (lock condition)

The synthesis ships when, on day 30 after UX-6 lands:

* **Linguistic test (Sonnet R3).** The full text of every
  composed Read across the prior 7 days passes the banned-
  vocab lint script with zero violations. Quiet days produce
  ≤ 2-sentence Reads; high-signal days produce ≤ 5-sentence
  Reads. No padding, no inflation.
* **Comprehension test (Opus R3).** Show a new user the
  default `/overview` for 10 seconds; hide the screen; ask
  *"what happened today and what (if anything) needs your
  attention?"* The user answers correctly without using
  *signal · pipeline · engine · regime · gate · advisory ·
  scheduler · ingest · replay*.
* **Operational-access test (Codex R3).** A returning user
  reaches their most-used Working surface in under 2 minutes
  without using chat. (No chat exists in this product, so
  this collapses to "the operational surface is reachable
  without trekking through the editorial column.")
* **Inspection test (Gemini R3).** On days where the
  composed Read produces a Decision-typed action, the
  Evidence-expand click rate is ≥ 2× the rate on days where
  the Read is a Brief or Observation only. Proves users use
  inspection to validate decisions and skip it when no
  decision is offered.

All four tests must pass for UX-6 to be considered shipped.

---

## 13. What survives from prior UX work

* All UX-2 (Brief view, position story cards) ✓
* All UX-3 (calmness vocabulary, single-link footer) ✓
* All UX-4 (composition principles — re-applied at UX-6
  scale) ✓
* All UX-5 (three-layer abstraction — UX-6 is the lock) ✓
* The composer pattern in `apps/web/src/lib/copilot/`
* The lint script + anti-AI-theater rules
* CopilotOverview already mounted at `/overview` — extends to
  the Read · Evidence · Action structure in 6D + 6E

---

## 14. Out of scope for UX-6

(captured for future phases, NOT shipped here)

* Crypto / forex / commodities expansion.
* Per-position contextual Ask / structured Drill-down.
* Voice interface.
* Mobile-native app.
* Personalised opportunity feed (the AI ranks ideas based
  on your historical preferences) — explicitly REJECTED at
  this scope; would re-introduce ranking psychology.
* Operator login or PIN gating Working access.
* Notifications, push, email digest.
* Streaks, gamification, engagement metrics.

---

## 15. Debate transcripts

Full Round 1 / Round 2 / Round 3 transcripts archived at:

```
.debate/ux6_copilot_20260508-143540/
├── _prompt_round1.md
├── _prompt_round2.md
├── _prompt_round3.md
├── _synthesis_draft.md
├── round1/
│   ├── gemini.md
│   ├── codex.md
│   ├── sonnet.md
│   └── opus.md
├── round2/
│   ├── gemini.md
│   ├── codex.md
│   ├── sonnet.md
│   └── opus.md
└── round3/
    ├── gemini.md
    ├── codex.md
    ├── sonnet.md
    └── opus.md
```

Each model contributed differentiated load-bearing positions.
Final master plan credits per section:

| Contribution | Credit |
|--------------|--------|
| "Translate, don't migrate" principle | Codex R1 |
| Read · Evidence · Action · See the working | Codex R2 |
| Object typing (Brief / Observation / Decision / Exception) | Codex R3 |
| Numeric visibility contract | Codex R3 |
| Behaviour-pinned shortcut | Codex R3 |
| AI as the layout engine | Opus R1 |
| Page contracts on quiet days | Opus R1 |
| Editorial column 720px | Opus R1 |
| Evidence expansion rules (≤ 3 sources + 1 rule sentence + dataSource) | Opus R3 |
| "AI sticker on a dashboard" anti-pattern | Opus R3 |
| Three narrative registers (Brief / Position / Opportunity) | Sonnet R1 |
| Ideas expire with visible decision windows | Sonnet R1 |
| Composer triage hierarchy on contested days | Sonnet R3 |
| Density rules (sentence count = signal) | Sonnet R3 |
| Working subnav 4-primary + Advanced disclosure | Sonnet R3 |
| Routing + deep-link preservation contract | Sonnet R3 |
| Intermediate-state contract for Ideas | Sonnet R3 |
| Linguistic + density day-30 test | Sonnet R3 |
| "Ritual matters" — Morning / Evening cadence framing | Gemini R1 |
| Thesis-tied narrative ("strengthens your Innovation Leader thesis") | Gemini R1 |
| Evidence as data-driven micro-disclosure (not more prose) | Gemini R3 |
| Inspection-rate day-30 test | Gemini R3 |

The synthesis is the formal capstone. Lock and execute.
