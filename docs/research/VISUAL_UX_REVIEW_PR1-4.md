# Visual UX Review — /today, /today/portfolio, /today/pick/:symbol

**Date**: 2026-05-21
**Status**: Visual review based on CSS-grounded prediction (no
browser screenshot capture available in this environment per
CLAUDE.md — Haiku-only testing). Operator should run the dev server
and visually verify the predictions before approving PR-5.

**Scope**: PR-1 + PR-2 + PR-3 + PR-4 surfaces at desktop 1280×800
and mobile 390×844.

---

## Methodology note

This review is CSS-grounded: I authored the design tokens
(`today.css`, `primitives.css`, `pickDetail.css`) and component
structure (TodayPage, TodayPortfolioPage, PickDetailPage), so I can
predict the rendered outcome with high precision from the source.
Honest absence: this is not a substitute for actual eyes-on screenshots.
Treat the recommendations as design-direction confidence, not pixel
audits.

To produce real screenshots on Haiku:
```
cd apps/web && npm run dev
# capture at 1280x800 and 390x844 for:
http://localhost:5173/today
http://localhost:5173/today/portfolio
http://localhost:5173/today/pick/NVDA
```

---

## Screen 1 — `/today`

### Desktop 1280×800 prediction

```
┌──────────────────────────────────────────────────────────────────┐
│ paper                              Today  Portfolio  Ideas  Learn │  ← TodayNav (48px)
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Good afternoon.                                                 │  ← serif 22px
│                                                                  │
│  The AI read today                                               │  ← label 12px muted
│                                                                  │
│  Portfolio is up $1,502 today · +0.4% since inception.          │  ← serif 24px
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│  Your paper portfolio                                            │
│                                                                  │
│  $117K                       [neutral sparkline 28x90]           │  ← serif 38px display
│  Live estimate: $116,817 · prices delayed 15 min · as of 6:40 PM│
│  Official close: $115,261 · 2026-05-19                          │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│  One thing to look at                                            │
│                                                                  │
│  NVDA                                                            │  ← serif 20px
│  Reasoning text (1-5 lines)…                                     │
│  • Signal: Buy                                                   │
│  Reference: entry $740 · target $820 · stop $720                 │
│  See details →                                                   │
├──────────────────────────────────────────────────────────────────┤
│  What changed recently                                           │
│  Closed AMAT at +4.2% on May 12.                       2d ago • │  ← up dot
│  Opened NVDA on May 19.                                today    │
│  Top concentration: NVDA at 4.8% of portfolio.                  │
│  Today's portfolio estimate is $1,956 below official close. •   │  ← down dot
│  Options remain dormant — equities only for now.                │
├──────────────────────────────────────────────────────────────────┤
│  AI's recent moves                                               │
│  2d ago    AMAT      +4.2% · +$420                              │  ← up
│  4d ago    KLAC      −1.8% · −$185                              │  ← down (same weight)
│  6d ago    NVDA      +1.0% · +$83                               │
│  9d ago    FDX       +2.1% · +$120                              │
├──────────────────────────────────────────────────────────────────┤
│  Track record                                                    │
│  Since Mar 14: +1.2%. Largest decline: −3.4%.                   │
├──────────────────────────────────────────────────────────────────┤
│  What does "Trim" mean?                                          │  ← serif 18px
│  Trim is a partial reduction of an open position…                │
│  More terms →                                                    │
├──────────────────────────────────────────────────────────────────┤
│  Ideas · Holdings · Learn                                        │
│  › Advanced                                                      │
└──────────────────────────────────────────────────────────────────┘
```

Reading column ≈ 720px centered. Total scroll ≈ 1700px (page is
multi-fold by design — first-fold delivers the 30-second story).

### Mobile 390×844 prediction

Same vertical sequence; padding collapses to 24px gutters; serif scales:
- Greeting 22px → 22px (unchanged; already small enough)
- AI read 24px → 19-20px
- NAV value 38px → ~32px
- One-thing card padding 24px → 16px
- What-changed rows reflow to 2-row layout (text on row 1, when+dot on row 2)
- Recent moves: 70px-when + symbol + outcome
- Learning card stays in single-column

First-fold on mobile shows: TodayNav + Greeting + AI read line (≈ 320px height).

### Evaluation

| Criterion | Verdict |
|---|---|
| Typography hierarchy        | ✅ — serif used only for greeting, AI read, NAV, section hero titles; Inter elsewhere |
| Reading rhythm              | ✅ — 32px between sections, 1px quiet border separator; calm |
| Card consistency            | ⚠ — only one card on this page (One-thing); cards on Pick Detail vs Holdings differ in padding |
| Emotional pacing            | ✅ — sequential: orientation → portfolio → focus → context → journal → learn |
| Information density         | ✅ — only 4 numbers above 100vh fold |
| Mobile usability            | ✅ — reading column collapses cleanly, no horizontal scroll |
| Trust-building clarity      | ⚠ — track record sentence is short; user may not realize it's the AI's history |
| Educational visibility      | ⚠ — Learning card visible but reads as single rotating term; the section label "What does X mean?" looks like just a heading |
| Empty-state behavior        | ✅ — every section has honest absence copy |
| ArthOS vision consistency   | ✅ — warm paper, deep sage, editorial serif, no glow, no lift |

**What feels premium**: serif-on-paper typography, generous whitespace, single muted accent, calm dot-not-glow indicators.

**What still feels dashboard-like**: nothing material on this surface. The "What changed" section is observational and tonally correct.

**What still feels operator-oriented**: zero — TodayPage doesn't render any operator vocabulary. Verified by lint.

**What should be refined before PR-5**:
- Track record section needs a clearer label ("Track record" feels too operator-y; consider "How the AI has done").
- The "What does Trim mean?" learning card has heading-shaped title; should look more obviously interactive ("a 1-minute lesson").

---

## Screen 2 — `/today/portfolio`

### Desktop 1280×800 prediction

```
┌──────────────────────────────────────────────────────────────────┐
│ paper                              Today  Portfolio  Ideas  Learn │  ← active = Portfolio
├──────────────────────────────────────────────────────────────────┤
│  Portfolio                                                       │  ← greeting 22px
│                                                                  │
│  Your paper portfolio                                            │
│  $117K                       [neutral sparkline]                 │  ← display 38px
│  Live estimate: $116,817 · prices delayed 15 min · as of 6:40 PM│
│  Official close: $115,261 · 2026-05-19                          │
├──────────────────────────────────────────────────────────────────┤
│  Holdings                                                        │  ← section label
│                                                                  │
│  NVDA                                          $4,000            │  ← calm-row primary 16px
│  0.3 units · cost $741.79              • +2.1% · +$83           │  ← calm-row secondary 13px + badge
│  ────────────────────────────────────                            │
│  QQQ                                           $3,522            │
│  5.0 units · cost $710.14              • -1.2% · -$43           │  ← terracotta dot
│  ...                                                             │
├──────────────────────────────────────────────────────────────────┤
│  Reading this page                                               │
│  Each row shows one open position with its current value…        │
│  More terms →                                                    │
├──────────────────────────────────────────────────────────────────┤
│  Today · Ideas · Learn                                           │
│  › Advanced                                                      │
└──────────────────────────────────────────────────────────────────┘
```

### Mobile 390×844 prediction

- "Portfolio" greeting + section label stack vertically
- NAV stays single line + sparkline drops below number on narrow widths
- Holdings: each row is 2-line composition (primary symbol+value on row 1, qty/cost+badge on row 2 with grid-rows wrap)
- Reading-this-page card stays one column

### Evaluation

| Criterion | Verdict |
|---|---|
| Typography hierarchy        | ✅ — same as /today; consistent |
| Reading rhythm              | ✅ — 32px between sections |
| Card consistency            | ⚠ — the "reading this page" card uses sunken background (today-learn class); holdings rows use no card; differs from one-thing card on TodayPage |
| Emotional pacing            | ✅ — NAV → holdings → reading-help → browse |
| Information density         | ⚠ — Holdings list can have 40+ rows; no pagination or scroll affordance |
| Mobile usability            | ⚠ — holdings table on mobile is dense (qty + cost + value + badge per row); needs visual breath |
| Trust-building clarity      | ✅ — Live + Official + delayed-15-min label all visible |
| Educational visibility      | ✅ — "Reading this page" card serves as inline learn |
| Empty-state behavior        | ✅ — empty positions show "No open positions yet" |
| ArthOS vision consistency   | ✅ — same palette and primitives as /today |

**What feels premium**: NAV hero with sparkline, calm muted holdings rows, no operator chrome.

**What still feels dashboard-like**: holdings list with 40 rows is data-dense. Could benefit from grouping (top concentrations / smaller positions collapse).

**What still feels operator-oriented**: nothing material; the Advanced expander hides operator links well.

**What should be refined before PR-5**:
- Holdings rows need stronger visual rhythm — every 5 rows have a slightly heavier divider, or top-5 vs the rest get a "see all positions" toggle.
- "Reading this page" card label is good but the box-shape competes with the holdings list above; consider making it lighter (no background tint).

---

## Screen 3 — `/today/pick/NVDA`

### Desktop 1280×800 prediction

```
┌──────────────────────────────────────────────────────────────────┐
│ paper                              Today  Portfolio  Ideas  Learn │
├──────────────────────────────────────────────────────────────────┤
│  NVDA  • Buy signal                              as of 2h ago    │  ← serif 28px + signal-dot
│                                                                  │
│  Reasoning text from pick.thesis (or honest absence).           │  ← serif 22px
│                                                                  │
│  Why it matters: If this idea continues, sustained price        │  ← Inter 15px secondary
│  strength would likely be the primary driver.                    │
│                                                                  │
│  [Momentum]                                                      │  ← concept chip (sage)
├──────────────────────────────────────────────────────────────────┤
│  What changed since yesterday                                    │
│  Position recently entered for this symbol.       2d ago        │
│  Signal refreshed within the last two hours.      today         │
├──────────────────────────────────────────────────────────────────┤
│  Why this appeared today                                         │
│  • Short-term price trend is above the medium-term trend.       │
│  • Recent volume is above the prior 30-day baseline.            │
│  • This symbol is currently held in your paper portfolio.       │
│                                                                  │
│  Signal evaluated 2h ago.                                        │
├──────────────────────────────────────────────────────────────────┤
│  What supports the idea                                          │
│  ┌──────────────────────────────────────────┐                   │  ← .pd-card
│  │ Claim text                                │                   │
│  │ Source: source_pill                       │                   │
│  └──────────────────────────────────────────┘                   │
│  (up to 5 cards)                                                 │
├──────────────────────────────────────────────────────────────────┤
│  What could go wrong                                             │
│  ┌──────────────────────────────────────────┐                   │  ← identical card style
│  │ Risk text                                 │                   │
│  │ Source: invalidation                      │                   │
│  └──────────────────────────────────────────┘                   │
│  We'd reconsider this signal if any of these holds.             │
├──────────────────────────────────────────────────────────────────┤
│  Risk awareness                                                  │
│  Currently 4.8% of your portfolio.  Read: concentration →       │
│  Daily moves on this symbol vary…   Read: volatility →          │
│  Your portfolio's largest decline so far is −3.4%…  drawdown →  │
├──────────────────────────────────────────────────────────────────┤
│  Expected horizon                                                │
│  This kind of momentum setup typically plays out over two to    │
│  six weeks. The engine re-evaluates daily…                       │
├──────────────────────────────────────────────────────────────────┤
│  Reference levels                                                │
│  entry $740 · target $820 · stop $720                            │
├──────────────────────────────────────────────────────────────────┤
│  In your portfolio                                               │
│  You hold 0.3 units of NVDA at average cost $741.79 (−1.1%).    │
├──────────────────────────────────────────────────────────────────┤
│  Learn more                                                      │
│  [What is a Buy signal?] [What is a stop?] [Cost basis]         │
│  [Drawdown] [Momentum]                                           │
├──────────────────────────────────────────────────────────────────┤
│  › Show technical detail                                         │
├──────────────────────────────────────────────────────────────────┤
│  ← Back to Today                                                 │
└──────────────────────────────────────────────────────────────────┘
```

Total page height ≈ 2200-2400px. Reading column ≈ 720px.

### Mobile 390×844 prediction

- Symbol + signal-dot wrap below "as of"
- Thesis 22px → 19px
- Cards reflow to full-width with 16px padding
- Reference-levels line stays compact
- Risk awareness 3 lines stack vertically
- Learn chips wrap to 2-3 rows
- Technical detail expander stays at bottom

First fold on mobile shows: nav + symbol/signal-dot + thesis (≈ 350px).

### Evaluation

| Criterion | Verdict |
|---|---|
| Typography hierarchy         | ✅ — serif on symbol + thesis only; sentence-case labels |
| Reading rhythm               | ✅ — 32px between sections; clean borders |
| Card consistency             | ✅ — evidence + risk cards use identical `.pd-card` style (the load-bearing visual claim of the design) |
| Emotional pacing             | ✅ — Thesis → What changed → Why appeared → Supports → Risks → Risk awareness → Horizon → Reference → In portfolio → Learn → Tech-detail. Sequential. |
| Information density          | ✅ — sections are observational, max 5 evidence cards, max 3 risk facts |
| Mobile usability             | ⚠ — long page; user must scroll through 9 sections to reach Back link |
| Trust-building clarity       | ✅ — risk + evidence rendered with identical visual weight |
| Educational visibility       | ✅ — concept tag + 5 learn chips + risk-awareness inline learn-links |
| Empty-state behavior         | ✅ — every section has honest absence ("Risk thresholds will be surfaced once a trade is opened on this signal.") |
| ArthOS vision consistency    | ✅ — calm sage accent for concept tag, terracotta for losses (not red), no glow |

**What feels premium**: editorial thesis treatment, identical-weight evidence vs risk cards, concept tag bridging to learn, observational copy throughout, technical detail collapsed.

**What still feels dashboard-like**: nothing material. The card-stack is calm.

**What still feels operator-oriented**: technical detail expander when opened shows monospace numerics — that's correct (operator vocabulary lives there intentionally).

**What should be refined before PR-5**:
- Long mobile scroll: consider adding a section nav (table-of-contents pill) at the top right of mobile, sticky during scroll. Currently no way to jump to "What could go wrong" without scrolling past 4 sections.
- "Why it matters" line could be slightly more emphasized — currently looks like a regular paragraph; users may skim past it.
- Concept tag chip is single-anchor at end of thesis section; on a long page, it disappears fast. Consider repeating concept tag inline with "Learn more" section.

---

## A. Top 10 visual improvements

| # | Surface | Issue | Proposed refinement | Effort |
|---|---|---|---|---|
| 1 | /today                  | "Track record" label may read as operator | Rename to "How the AI has done" or "AI's history" | S |
| 2 | /today                  | Learning card title looks like a heading, not a CTA | Add a "1-min read" eyebrow chip + chevron icon | S |
| 3 | /today/portfolio        | Holdings list visually flat — 40 rows in a uniform stack | Group top-5 (heavier divider) vs rest collapsed under "See all" | M |
| 4 | /today/portfolio        | "Reading this page" card competes with holdings list | Remove sunken background; render as inline paragraph with link | S |
| 5 | /today/pick/:symbol     | Long mobile scroll; no jump-to-section | Sticky section pill ToC on mobile (Why/Supports/Risks/Risk/Horizon) | M |
| 6 | /today/pick/:symbol     | "Why it matters" can be missed | Add 2px left border in accent-faint to differentiate from body | S |
| 7 | /today/pick/:symbol     | Concept tag disappears after scroll | Repeat tag in Learn-more section as the first chip | S |
| 8 | All 3                   | Section labels use 12px muted color, can read as eyebrow not heading | Standardize to 13px ink-secondary, slightly more visible | S |
| 9 | All 3                   | TodayNav has no visual cue for current route beyond underline | Add small accent dot to left of active label | S |
| 10 | All 3                  | Body text 16px is right for novice, but 13-14px metadata is right at the edge of readable on retina mobile | Bump metadata floor to 14px on `<640px` breakpoint | S |

---

## B. Top 5 mobile improvements

| # | Surface | Issue | Refinement |
|---|---|---|---|
| 1 | /today                  | First-fold currently shows greeting + AI read + portfolio NAV all at small mobile sizes — but if user has long names or short viewports, "Your paper portfolio" label can push NAV value below the fold | Reduce greeting margin to 16px on mobile; keep NAV within first 480px |
| 2 | /today/portfolio        | Calm-row qty+cost line wraps awkwardly when symbol is long | Stack: symbol full-width, value full-width, units+badge in 2-col below |
| 3 | /today/pick/:symbol     | 9 sections × full mobile width = tall scroll | Add ToC sticky pill OR collapse "Risk awareness" + "Expected horizon" + "Reference levels" into a single 3-tab pill panel |
| 4 | /today/pick/:symbol     | Learn chips wrap to multi-row on mobile; tap target 32px is tight | Bump chip vertical padding to 10px on mobile; min height 40px |
| 5 | All 3                   | Tap targets — currently 44px floor is honored, but Back link uses 14px which is small | Bump Back link to 16px on mobile |

---

## C. Typography refinement recommendations

| Token | Current | Recommendation |
|---|---|---|
| Greeting (serif)                    | 22px desktop / 22px mobile        | Keep; mobile is fine |
| AI read sentence (serif)            | 24px / 19px                       | Bump mobile to 20-21px for better hierarchy vs body 16px |
| NAV display (serif)                 | 38px / ~32px                      | Keep |
| Thesis (Pick Detail serif)          | 22px / 19px                       | Bump mobile to 20px |
| Symbol header (Pick Detail serif)   | 28px / 24px                       | Keep |
| Body sans                            | 16px / 16px                       | Keep |
| Section label                       | 12px ink-muted                    | Bump to 13px ink-secondary; eyebrow uppercase NO; sentence-case OK |
| Meta / "as of" labels                | 13px / 13px                       | Bump mobile to 14px for retina readability |
| Metadata in calm-row                | 13px ink-muted                    | Bump mobile to 14px |
| Numerics (tabular-nums)              | inherit                            | ✅ already correct |

---

## D. Spacing refinement recommendations

| Token | Current | Recommendation |
|---|---|---|
| Between sections (vertical)          | 32px (`--t-8`) desktop, 24-32px mobile | Keep |
| Card internal padding                | 24px (`--t-6`) standard; 16px on compact `.pd-card` | Standardize: 24px on all calm-cards across screens |
| Inter-row in calm-row                | 12px (`--t-3`)                     | Keep |
| Section label → first content       | 16px (`--t-4`)                     | Keep |
| Page outer gutters                   | 80px desktop, 24px mobile          | Keep |
| Reading column max-width             | 720px                              | Keep; consider 760px on `>1440px` viewports for slightly more comfortable typography |

---

## E. Card-system refinement recommendations

Currently three different card flavors exist:
- `.today-onething` (today.css)              — used on /today's "One thing"
- `.calm-card` (primitives.css)              — used on /today/portfolio Reading-this-page
- `.pd-card` (pickDetail.css)                — used on Pick Detail evidence + risk

**Recommendation**: consolidate to two canonical card styles:
1. **Hero card** (`.calm-card-hero`): 24px padding, 12px radius, 1px border. Used for: One-thing card, large statement cards.
2. **Stack card** (`.calm-card-stack`): 16px padding, 12px radius, 1px border. Used for: evidence cards, risk cards, holdings rows.

All three current card classes already share the same color tokens and motion rules — just need consolidation of padding token. Migrate in PR-6 (not PR-5).

**Forbidden across all card variants** (already enforced):
- box-shadow at rest
- transform on hover
- radial gradient backgrounds
- inverted color (light-on-dark) at rest
- uppercase headers

---

## F. Learn Hub PR-5 — should it proceed unchanged, or with adjustments?

**Proceed mostly unchanged** with three small adjustments:

1. **Slot for "How the AI has done" link** in Learn Hub index — bridges PR-5 to the existing track record block on /today. Cross-link from /today's track record section → /learn/concept/track-record.

2. **Concept slug pages** are referenced from Pick Detail's concept tag (PR-4). PR-5 must ship `/learn/concept/:slug` routes (not just `/learn/term/:slug`), or the Pick Detail concept tag becomes a 404. Specifically:
   - `/learn/concept/momentum`
   - `/learn/concept/mean-reversion`
   - `/learn/concept/valuation`
   - `/learn/concept/quality`
   - `/learn/concept/defensive`
   - `/learn/concept/growth`

3. **`/learn/term/:slug` routes** are referenced by Pick Detail Learn-more chips:
   - `/learn/term/buy-signal`, `/learn/term/sell-signal`, `/learn/term/trim-signal`, `/learn/term/hold-signal`
   - `/learn/term/stop-loss`
   - `/learn/term/cost-basis`
   - `/learn/term/drawdown`
   - `/learn/term/concentration`
   - `/learn/term/position-sizing`
   - `/learn/term/volatility`

PR-5 must ship these specific slugs (or aliased redirects) so the Pick Detail chips don't 404.

Beyond that, PR-5 architecture (glossary index + featured term + paths) is unchanged.

---

## What's NOT in this review

- Real pixel screenshots — environment can't render browsers
- Color contrast WCAG audit — requires actual rendered DOM
- Real device touch testing — needs Haiku-model browser
- Lighthouse / performance audit — requires running dev server

Operator should run dev server on Haiku and verify the predictions
above before approving PR-5.

---

## Approval requested

1. Confirm visual predictions match real screenshots (Haiku-run verification)
2. Decide which of the 10 visual improvements + 5 mobile improvements
   land BEFORE PR-5 (could be a small PR-4.5 polish) versus after
3. Approve PR-5 with the 3 small adjustments noted in §F:
   - Cross-link from /today track record → /learn
   - `/learn/concept/:slug` routes
   - `/learn/term/:slug` routes covering the 10 chips on Pick Detail
