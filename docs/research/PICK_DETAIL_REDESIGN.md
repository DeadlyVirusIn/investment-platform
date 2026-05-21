# Pick Detail Redesign — Calm Analyst Briefing

**Date**: 2026-05-21
**Status**: PLAN ONLY — no implementation, no scope expansion
**Predecessors**:
- `PRODUCT_EXPERIENCE_REFINEMENT.md` (sequencing: PR-4 = Pick Detail)
- `FULL_PRODUCT_PAGE_DESIGN_MAP.md` (Page 4 spec)
- PR-1 + PR-2 + PR-3 shipped (Today / Today Portfolio / What changed)

## North star

> "A calm investment analyst explaining an idea to a beginner."

NOT: trading terminal · AI dashboard · quant console · chart-first
casino · marketing landing page.

The Pick Detail page is the single highest-trust surface in the
product. Today the user enters here from "One thing to look at" on the
calm /today page. If this view still has glow, lifts, and engine
vocabulary, the calm narrative breaks at the exact moment the user
decides whether to trust the system.

## Hard locks (locked across every section below)

| Lock | Enforcement |
|---|---|
| No fake confidence % | Tier-A lint (30 phrases) |
| No agency claims ("AI sees / AI thinks / AI proposed") | Tier-A lint |
| Reasoning prose only from backend renderer (Phase L) | UI-1 lock |
| No emotional market language ("panic / surge") | Tier-A lint |
| No fake certainty ("will rise") | observation only |
| Losses equal weight to gains | design |
| Paper-only labeling stays | design |
| Reference prices are utility numbers, not theatre | design |

---

## What disappears from the current Pick Detail

| Element | File:line | Why removed |
|---|---|---|
| "AI Research Cockpit" eyebrow                | `PickModal.tsx:180`             | operator vocabulary; novice doesn't need cockpit framing |
| `engine ${pick.engine_version}` sub-line     | `PickModal.tsx:185` region      | Layer-3 leak |
| `composite_score` in technical detail        | `PickModal.tsx:336-388`         | engineering shrapnel; moved fully behind expander |
| `family_scores`                              | `PickModal.tsx:336-388`         | engineering shrapnel |
| `raw_action` / `raw_adjusted_action`         | `PickModal.tsx:336-388`         | engineering shrapnel |
| Large filled colored action badge            | `PickModal.tsx:208-214`         | casino theatre — replaced with dot + word |
| Radial gradient top wash on modal             | `picks.css:236-260, 477-490`    | theatrical color — kept on legacy via shellVariant |
| Hover lift on cards                           | `picks.css:264-265, 971`         | startup-SaaS energy |
| Uppercase 0.18em "RECOMMENDATION" label       | `PickModal.tsx` section H4       | section header → sentence-case |

## What gets de-emphasized

| Element | Current weight | New weight |
|---|---|---|
| Action badge (Buy / Sell / Trim / Hold)        | hero-sized colored pill | small dot + sentence-case word inline with thesis |
| Reference price (entry/target/stop)             | Top of modal, large numerics | body-text-sized utility line below thesis |
| Catalysts                                       | persistent section even when empty | conditional render — omit when no catalysts |
| Conviction band ("Medium conviction")           | inline next to action  | small caption under thesis |
| Symbol header                                   | hero size with monospace | serif title, calm scale |

## What becomes the emotional center

**Thesis Summary** (Section 1). This is the one block that defines whether
the user trusts the system. Everything else is supporting context. It
gets the largest typography, the most vertical space, the slowest reading
rhythm, and the only serif treatment on the page.

---

## Section-by-section design

### Section 1 — Thesis Summary

**Purpose**: A novice reads this in 8 seconds and understands what the
AI is flagging and why, in plain English.

**Source**: backend reasoning envelope (`reasoning_audit.skeleton_id`
+ `slot_fills_json`) rendered by `ReasoningCard`. Honest absence when
no envelope exists.

**Information hierarchy**:
1. Symbol + nature ("NVDA · Buy signal" — sentence case, single dot)
2. One-sentence thesis (serif, 22-24px, max 2 lines)
3. Small "as of <date>" meta line beneath

**Desktop layout**:
- Full reading-width column (max 720px)
- Symbol left, "as of" right, both small (13-14px)
- Thesis below: serif, generous line-height (1.4), padded top 16px

**Mobile (390×844)**:
- Symbol + "as of" stack vertically
- Thesis remains serif, scales to 19-20px
- No truncation; allow soft wrap

**Visual treatment**:
- Serif (`Source Serif 4` 22px desktop, 19px mobile)
- Ink primary
- No badge, no glow, no border highlight
- Single tone-dot to left of "Buy" / "Sell" / "Trim" / "Hold" (8px sage / terracotta / amber / neutral)

**Copy examples** (rendered by backend; never frontend-authored):

| Action | Example sentence |
|---|---|
| Buy   | "NVDA shows a momentum breakout with above-average volume after a calm consolidation." |
| Sell  | "KLAC has broken its 50-day trend and key risk thresholds are now exceeded." |
| Trim  | "AMAT has reached the upper end of its expected range; momentum is fading." |
| Hold  | "FDX is moving sideways with no breach of either entry or exit thresholds." |

**Forbidden in this section**:
- "AI thinks / sees / suggests" anywhere
- "We're confident / expect"
- Confidence percentages
- Probability statements ("likely to rise")

---

### Section 2 — Why This Appeared

**Purpose**: Transparency. Show the deterministic signal that triggered
the engine to surface this row, without mystifying.

**Source**: `decision_log` action + `signal_v1.json` mapping
(skeleton_id ↔ signal vocabulary). Observational only.

**Information hierarchy**:
- Section label: "Why this appeared today" (sentence case)
- Two or three observational bullets describing the trigger
- Date the signal fired (small meta)

**Desktop**:
- Full-width, no card border, sits under thesis
- Bullets use `•` indent, 16px body, 24px line-height
- 32px vertical breathing above and below

**Mobile**:
- Same; reading column already mobile-tight

**Visual treatment**:
- Body sans (Inter 16px)
- Ink primary for fact, ink-muted for the date
- No icons, no chips, no colored backgrounds

**Copy examples** (each line is one fact, observational):

```
Why this appeared today

• The 20-day price trend crossed above the 60-day trend on Mon 19 May.
• Average daily volume over the last 5 sessions is 38% higher than
  the prior 30-day baseline.
• The position is not currently held in your paper portfolio.

Signal fired 19 May, 04:00 UTC.
```

**Forbidden**:
- "Our model predicts"
- "Confidence band: medium"
- "Risk/reward looks favorable"
- "Asymmetric upside"
- Composite scores, family scores

---

### Section 3 — What Supports The Idea

**Purpose**: Group the evidence. Calm reader sees 3-5 supporting facts,
each one falsifiable, none rhetorical.

**Source**: envelope `evidence` array (already exists per Phase L). Each
evidence item is a sourced fact with a `source_pill` (existing
`SourcePill` component).

**Information hierarchy**:
- Section label: "What supports the idea"
- 3-5 evidence cards (calm cards, not glow cards)
- Each card: claim + source pill + one-line context

**Desktop**:
- Stacked cards, full reading-column width
- 12px gap between cards
- Card padding 16px (compact — they're informational, not hero)

**Mobile**:
- Same stack
- Source pill wraps to its own line if needed

**Visual treatment**:
- `.calm-card` from primitives.css (1px border, no shadow, sand background)
- Source pill is the existing component, calm-tone variant
- No icons except optional 12px chevron when card is expandable

**Copy examples**:

```
What supports the idea

┌──────────────────────────────────────────────────────┐
│ NVDA's price has held above its 200-day average for │
│ 14 consecutive sessions.                              │
│ Source: price_bar (Tiingo daily)                     │
└──────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────┐
│ Volume in the last 5 sessions averaged 142% of the  │
│ prior 30-day baseline.                                │
│ Source: price_bar.volume                              │
└──────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────┐
│ The asset is in the engine's eligible universe and  │
│ passes the standard liquidity filter.                │
│ Source: universe_filter                               │
└──────────────────────────────────────────────────────┘
```

**Forbidden**:
- "The chart looks constructive"
- "Setup forming"
- "Strength building"
- Pure adjectives without numbers
- Statements without source attribution

---

### Section 4 — What Could Go Wrong

**Purpose**: Equally prominent counterweight. The user must see the
risks at the same visual weight as the supporting evidence. **This is
the section that earns long-term trust.**

**Source**: envelope `invalidation` + `triggers` fields (existing Phase
L structure) — every envelope has them.

**Information hierarchy**:
- Section label: "What could go wrong" (sentence case)
- 2-3 falsifiable risk statements
- One small line: "We'd reconsider this if any of these happens."

**Desktop**:
- Same stack and card style as Section 3
- Identical visual weight — same card type, same typography
- Lives immediately under Section 3 with same vertical rhythm

**Mobile**:
- Same as desktop pattern

**Visual treatment**:
- IDENTICAL card style as supporting evidence — no red border, no
  warning icon, no caution chip
- The honesty IS the treatment; visual punishment would be theatre

**Copy examples**:

```
What could go wrong

┌──────────────────────────────────────────────────────┐
│ If the price closes below $720 — the recent base   │
│ — the breakout setup is no longer intact.            │
│ Source: invalidation.price_floor                      │
└──────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────┐
│ If 5-session volume falls below the 30-day baseline,│
│ the momentum signal is weaker than thought.          │
│ Source: invalidation.volume_floor                     │
└──────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────┐
│ Earnings on 22 May may move the price more than the │
│ engine's normal range expects.                       │
│ Source: catalyst.earnings                             │
└──────────────────────────────────────────────────────┘

We'd reconsider this position if any of these happens.
```

**Forbidden**:
- "Limited downside"
- "Low risk"
- "Defined risk" without a price
- Statements with no falsifier

---

### Section 5 — Expected Holding Horizon

**Purpose**: Calibrate time expectations. A novice often expects
overnight results; a calm analyst tells them this is a multi-week idea.

**Source**: skeleton_id → horizon mapping (exists in
`reasoning/skeletons` catalog). Optional `pick.policy.horizon_days`
field.

**Information hierarchy**:
- One sentence in body text
- Optional small line: "How we measure the horizon"

**Desktop**:
- Inline below Section 4
- No card, just a paragraph
- Italic optional for "How we measure" link

**Mobile**:
- Same

**Visual treatment**:
- Body sans, ink primary
- Short — 1-2 lines max
- Educational, not prescriptive

**Copy examples**:

```
Expected horizon

This kind of momentum setup typically plays out over 2 to 6 weeks.
The engine re-evaluates daily; if the thesis no longer holds, you'll
see a Trim or Sell signal in your portfolio.
```

**Forbidden**:
- "Should hit target by"
- "Will play out within"
- Definite outcomes

---

### Section 6 — Risk Awareness

**Purpose**: Portfolio-level context. Surface concentration, volatility,
and drawdown reality WITHOUT scaring the user. Honest, not alarming.

**Source**:
- Concentration: % of current NAV the position would represent if sized
  per the engine's standard rule
- Volatility: rolling 20-day stdev from existing price_bar
- Drawdown context: max drawdown of historical equity for the user's
  paper portfolio

**Information hierarchy**:
- Section label: "Risk awareness" (sentence case)
- Three small inline facts, each one sentence
- One optional Learn link per fact

**Desktop**:
- Two-column 1fr 1fr on wide viewports (each cell is one fact)
- Light bottom border between sections

**Mobile**:
- Stack vertically; each fact on its own line

**Visual treatment**:
- Body text 15px
- No charts; numbers inline with prose
- Each fact ends with a quiet "What is this?" link to glossary

**Copy examples**:

```
Risk awareness

If the engine opens this at its standard size, it would represent
about 4% of your portfolio. Read: position sizing →

NVDA's daily price moves have averaged ±2.1% over the last month —
a bit higher than the broad market. Read: volatility →

Your portfolio's largest drawdown has been −3.4% so far. A buy
signal does not change that history. Read: drawdown →
```

**Forbidden**:
- "Worst case scenario"
- "Maximum loss"
- "Risk score: 7/10"
- Vague risk levels without a number

---

### Section 7 — Learn More

**Purpose**: Inline education. The user clicks once and learns a term
without leaving the page.

**Source**: `lib/novice/glossary` (already exists).

**Information hierarchy**:
- Section label: "Learn more"
- 3-5 chips, each linking to a glossary entry relevant to this signal
- Optional: "View full glossary" link

**Desktop**:
- Horizontal flex row of chips, wraps to next line
- Each chip uses `.calm-chip` quiet tone

**Mobile**:
- Wraps to multi-row chip grid

**Visual treatment**:
- Sand background chip, ink secondary text
- Hover/focus: chip border darkens, text becomes ink primary
- Tap opens a side drawer with the glossary entry; never navigates away

**Copy examples**:

```
Learn more
[ What is a Buy signal? ]  [ What is a stop? ]  [ Cost basis ]
[ Position sizing ]  [ Drawdown ]
```

**Forbidden**:
- Chip labels that read as actions ("Buy NVDA")
- Chips that promise courses ("Master investing in 5 days")
- Quiz / streak / gamification chips

---

### Section 8 — Technical Detail (collapsed by default)

**Purpose**: Reachable for operators. Hidden from novices.

**Source**: `engine_version`, `composite_score`, `family_scores`,
`raw_action`, `raw_adjusted_action`, full envelope JSON.

**Information hierarchy**:
- `<details>` element with summary "Show technical detail"
- Inside: definition-list layout (term → value), 2-column on desktop,
  stacked on mobile
- Each row monospace numerics but body sans labels
- A final "View raw envelope" link that opens the JSON in a drawer

**Desktop**:
- Indented under the disclosure triangle
- Sunken background to signal "different mode"
- Definition list 200px label column + value column

**Mobile**:
- Stacked rows; label small (12px), value (15px)

**Visual treatment**:
- Closed by default
- Open state still uses calm tones; no glow even when expanded
- Operator chrome (legacy tone) appears INSIDE the expander only

**Copy examples**:

```
› Show technical detail

When expanded:
  Engine version       phase-l-v3.2
  Composite score      0.74
  Family scores        trend 0.61 · momentum 0.83 · volatility 0.52
  Raw action            BUY_STRONG
  Adjusted action       buy
  Envelope hash         97dfb0216608b7ad…
  View raw envelope     →
```

**Forbidden**:
- Auto-expanded on first visit
- Tooltip popups inside (force a Learn drawer instead)
- "Operator only" warning chips — the expander itself is enough signal

---

## Wireframe hierarchy

```
┌─────────────────────────────────────────────────────────┐
│ Today  Portfolio  Ideas  Learn          [user menu]    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  NVDA · Buy signal                            as of …  │  ← Section 1
│                                                         │
│  NVDA shows a momentum breakout with above-             │
│  average volume after a calm consolidation.             │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Why this appeared today                                │  ← Section 2
│                                                         │
│  • The 20-day trend crossed above the 60-day trend     │
│  • Volume in the last 5 sessions is 38% above baseline │
│  • Not currently held in your paper portfolio          │
│                                                         │
│  Signal fired 19 May, 04:00 UTC.                       │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  What supports the idea                                 │  ← Section 3
│  [calm card]                                            │
│  [calm card]                                            │
│  [calm card]                                            │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  What could go wrong                                    │  ← Section 4
│  [calm card]                                            │
│  [calm card]                                            │
│  [calm card]                                            │
│  We'd reconsider this position if any of these happens.│
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Expected horizon                                       │  ← Section 5
│  This kind of momentum setup typically plays out over  │
│  2 to 6 weeks…                                          │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Reference levels                                       │  ← (small block)
│  entry $740  ·  target $820  ·  stop $720              │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  In your portfolio                                      │  ← (conditional)
│  Not currently held.                                    │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Risk awareness                                         │  ← Section 6
│  About 4% of your portfolio if opened at standard size.│
│  Daily moves have averaged ±2.1% over last month.      │
│  Your portfolio's largest drawdown so far is −3.4%.    │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Learn more                                             │  ← Section 7
│  [What is a Buy signal?] [What is a stop?] [Cost basis]│
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  › Show technical detail                                │  ← Section 8
│                                                         │
└─────────────────────────────────────────────────────────┘
```

Reading column 720px. Generous vertical rhythm. Sections separated by
1px quiet borders. No card overflow, no shadow at rest, no glow, no
hover lift.

---

## Component map

| Component | Type | Existing or new | Notes |
|---|---|---|---|
| `<PickDetailPage/>`                | new route page (`/today/pick/:symbol`)  | new | composes the whole experience |
| `<PickThesis/>`                    | section 1 hero                           | new | wraps `<ReasoningCard/>` honest-absence path |
| `<WhyThisAppeared/>`               | section 2                                | new | sources decision_log + signal_v1 mapping |
| `<EvidenceCard/>`                  | section 3 item                            | new | uses `.calm-card` primitive from PR-2 |
| `<RiskCard/>`                       | section 4 item                            | new | same shape as `<EvidenceCard/>` (deliberate parity) |
| `<HorizonNote/>`                   | section 5                                 | new | one paragraph |
| `<ReferenceLevels/>`               | small inline block                        | new | three tabular numbers |
| `<InPortfolioContext/>`            | conditional                                | new | conditional on `paper_position` lookup |
| `<RiskAwareness/>`                 | section 6                                 | new | three inline facts + glossary links |
| `<LearnChips/>`                    | section 7                                 | new | chip primitive from PR-2 + glossary fetch |
| `<TechnicalDetail/>`               | section 8                                 | new | `<details>` element; legacy operator content |
| `<ReasoningCard/>`                 | existing (Phase L)                        | reuse  | calm-shell variant via class |
| `<SourcePill/>`                    | existing                                  | reuse  | inside `<EvidenceCard/>` |

All sit inside `.today-root` so primitives.css from PR-2 cascades.

---

## Mobile flow

| Section | Mobile treatment |
|---|---|
| 1. Thesis            | full-width, serif 19px, generous breath |
| 2. Why this appeared | bullet list; "Signal fired" line on its own line |
| 3. Supporting evidence | stacked cards, full-width, 16px padding |
| 4. What could go wrong | stacked cards, same as #3 (identical weight) |
| 5. Horizon           | single paragraph |
| Reference levels     | three numbers on one line; wrap to two lines if needed |
| In your portfolio    | conditional one-liner |
| 6. Risk awareness    | vertical stack of three lines |
| 7. Learn chips       | wrap to multi-row grid |
| 8. Technical detail  | collapsed; expander opens with vertical key/value stack |

**Sticky elements**: NONE. No sticky header on mobile. No sticky CTA.
The page reads top-to-bottom; user scrolls back when they want to act.

**Action surface**: a single quiet "Back to Today" link at the bottom
of the page (no floating button, no toolbar).

---

## Trust-building rationale

| Design choice | Trust mechanism |
|---|---|
| Thesis FIRST, before any price or badge | The reader sees the AI's reasoning before judgement |
| Identical card style for evidence vs risk | Visual parity = honest framing; the system isn't hiding the downside |
| Sourced facts with `<SourcePill/>` | Every claim is falsifiable and traceable to a backend row |
| No confidence percentages | False precision broken; conviction band is structured state |
| No big colored action badge | Removes the casino-trigger; action is informational, not emotional |
| Expected horizon in plain English | Calibrates novice expectations against AI's true cadence |
| Risk awareness with portfolio context | Makes the user the subject, not the AI |
| Inline learn-chips | Build literacy alongside trust; user feels smarter after each visit |
| Technical detail collapsed | Operator surface exists but does not impose itself |
| No back-to-list breadcrumb on mobile | Page is destination, not transient; encourages dwell |
| No imperative copy anywhere | "We'd reconsider" not "you should sell" — user owns the decision |
| Honest absence when envelope missing | The system refuses to fake reasoning — high-trust signal |

The dominant principle: **the AI is a transparent analyst, not a black
box advisor.** Every section reveals more of how the engine reached the
signal, never less.

---

## PR-4 implementation scope

### Goal

Build the calm Pick Detail page as a new parallel route. Existing
`PickModal` legacy variant stays intact. The new route is mounted at
`/today/pick/:symbol` and is reachable from:
- `/today` "One thing to look at" card (CTA already exists, will be
  redirected from `/ideas` to `/today/pick/:symbol`)
- Future PR-N Ideas page

### Files (new)

| File | Purpose | Lines (est.) |
|---|---|---|
| `apps/web/src/pages/today/pick/PickDetailPage.tsx` | route page composing 8 sections | ~250 |
| `apps/web/src/pages/today/pick/pickDetail.css` | section-specific layout + typography | ~180 |
| `apps/web/src/components/today/pick/PickThesis.tsx` | section 1 | ~50 |
| `apps/web/src/components/today/pick/WhyThisAppeared.tsx` | section 2 | ~60 |
| `apps/web/src/components/today/pick/EvidenceList.tsx` | section 3 (renders calm-card per item) | ~80 |
| `apps/web/src/components/today/pick/WhatCouldGoWrong.tsx` | section 4 | ~80 |
| `apps/web/src/components/today/pick/HorizonNote.tsx` | section 5 | ~40 |
| `apps/web/src/components/today/pick/ReferenceLevels.tsx` | small block | ~40 |
| `apps/web/src/components/today/pick/InPortfolioContext.tsx` | conditional | ~50 |
| `apps/web/src/components/today/pick/RiskAwareness.tsx` | section 6 | ~80 |
| `apps/web/src/components/today/pick/LearnChips.tsx` | section 7 | ~50 |
| `apps/web/src/components/today/pick/TechnicalDetail.tsx` | section 8 (operator-content expander) | ~80 |

### Files (modified, additive)

| File | Change |
|---|---|
| `apps/web/src/App.tsx` | mount `/today/pick/:symbol` route |
| `apps/web/src/pages/today/TodayPage.tsx` | One thing CTA → `/today/pick/${topPick.symbol}` (was `/ideas`) |
| `apps/web/src/components/today/TodayNav.tsx` | unchanged |

### Files NOT modified

- `apps/web/src/components/picks/PickModal.tsx` — legacy modal untouched
- `apps/web/src/lib/picks/picks.css` — untouched
- `apps/web/src/pages/PicksPage.tsx`, `ActionQueuePage.tsx` — untouched
- `apps/web/src/pages/Decisions.tsx` — untouched
- All backend code — untouched
- `apps/api/src/reasoning/*` — untouched
- All migrations / Phase L renderer — untouched
- All options lifecycle — untouched

### Data sources (existing endpoints only)

| Endpoint | Used for |
|---|---|
| `/api/picks` (existing)                      | look up the pick by symbol on route load |
| `/api/reasoning/envelope/{trade_id_or_signal}` (existing) | source of `ReasoningCard` content |
| `/api/paper/executed/positions?is_open=true` | "In your portfolio" lookup |
| `/api/paper/equity` (existing)                | portfolio drawdown context for Risk awareness |
| `/api/performance/equity-curve`              | drawdown summary |
| `/api/paper/summary`                          | NAV used for position-sizing % |

NO new endpoints. NO new schema. NO migrations.

### Acceptance criteria

| # | Check | Required |
|---|---|---|
| 1 | forbidden-phrase lint (30 phrases)              | PASS |
| 2 | resolver-anchor lint                            | PASS |
| 3 | canary-gateway lint                             | PASS |
| 4 | reasoning envelope snapshot suite               | PASS |
| 5 | TypeScript                                      | clean |
| 6 | `/today` route unchanged                        | ✓ |
| 7 | `/today/portfolio` route unchanged              | ✓ |
| 8 | `/overview`, `/portfolio`, `/action-queue` legacy untouched | ✓ |
| 9 | `/today/pick/:symbol` renders 8 sections        | ✓ |
| 10 | "One thing to look at" CTA now goes to `/today/pick/${symbol}` | ✓ |
| 11 | PickModal legacy variant on `/overview` unchanged | ✓ |
| 12 | API payloads byte-identical                     | ✓ |
| 13 | Row counts: paper_trade / paper_position / options_* unchanged | ✓ |
| 14 | Mobile layout (390×844) usable                  | operator visual check |
| 15 | Desktop layout (1280×800) usable                | operator visual check |

### Out of scope for PR-4

- No Learn Hub destination (chips link to `/learn/term/:slug` which
  404s until PR-5 ships; chips are inert in PR-4)
- No `<details>` envelope JSON viewer (deferred to operator surface)
- No new endpoints
- No Phase L renderer changes
- No options lifecycle changes
- No legacy PickModal redesign
- No replacement of `/ideas` or `/action-queue`

### Rollback

```bash
git checkout HEAD -- apps/web/src/App.tsx \
                     apps/web/src/pages/today/TodayPage.tsx
rm -rf apps/web/src/pages/today/pick \
       apps/web/src/components/today/pick
```

Zero residue. PR-1+2+3 untouched. Legacy routes untouched.

### Estimated effort

~6-8 hours of focused work (1 day). Component shape is well-specified;
no backend uncertainty; visual rhythm matches PR-1+2+3 precedent.

---

## What does NOT happen in PR-4

- ✅ No backend changes
- ✅ No accounting math
- ✅ No trading logic
- ✅ No options lifecycle
- ✅ No Phase L renderer
- ✅ No schemas / migrations
- ✅ No SideNav / TopStrip / StatusRail edits
- ✅ No global glow/lift removal (still deferred)
- ✅ No copy that fails the 30-phrase Tier-A lint
- ✅ No promotion of `/today` to default `/`
- ✅ No Learn Hub destination yet (PR-5)
- ✅ No replacement of legacy PickModal
- ✅ No replacement of legacy `/action-queue`

## Approval requested

Approve PR-4 scope + 8-section design above. Subsequent PRs (5 Learn,
6 Performance, 7 Onboarding) gated individually after PR-4 ships and
the operator confirms the calm Pick Detail surface on mobile + desktop.

Stop after this proposal.
