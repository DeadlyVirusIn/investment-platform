# ArthOS PR-5 Learn — UX Architecture + Wireframes

**Date**: 2026-05-21
**Status**: UX DESIGN — no implementation
**Identity (locked)**: "Learn how to invest by watching an AI invest, explain itself, and admit mistakes."
**Design language (locked)**: calm · editorial · mentor-like · no gamification · no dashboards · no metric walls

This document applies the 5 approved curriculum refinements and
specifies wireframes for the 5 Learn surfaces.

---

## Refinements applied

### 1. New foundational path — "How Markets Actually Work"

Added as **Tier 0**, no prerequisite. Sits ABOVE "How this AI thinks"
because markets are the universe; the AI is a participant in that
universe. A learner needs to know how prices move before learning how
ArthOS reads price moves.

| Path | Position | Lessons |
|---|---|---|
| **How Markets Actually Work** (NEW) | Tier 0 — first foundational | 5 |
| How this AI thinks                   | Tier 1                       | 5 |
| Reading what you own (renamed)        | Tier 1                       | 5 |
| Paper trading fundamentals            | Tier 1                       | 4 |
| Risk literacy                          | Tier 2                       | 5 |
| Portfolio psychology                   | Tier 2                       | 5 |
| Reading signals like an analyst        | Tier 3                       | 5 |
| When the AI is wrong                   | Tier 3                       | 5 |
| ~~Options basics~~                     | HIDDEN ENTIRELY               | — |

**Total paths visible: 8** (was 7 with locked Options).

### 2. Weekly reflection artifact

New surface: `/learn/reflection` (linked from Learn home).

Four questions, ~5 minutes, Saturday or Sunday morning:
1. What surprised you?
2. What the AI got right (with deterministic context shown)
3. What the AI got wrong (with deterministic context shown)
4. What you learned

User answers two open-text; the AI auto-renders deterministic context
for the "right" and "wrong" prompts (drawn from real paper_trade +
journal data). Saved to localStorage initially; no DB schema in PR-5.

### 3. "Reading Your Portfolio" renamed

| Considered | Verdict |
|---|---|
| Reading Your Portfolio | operator-y, too literal |
| Understanding your account | Wealthfront-y, robo-advisor flavor |
| Knowing your portfolio | neutral, weak |
| What's in your portfolio | too literal |
| **Reading what you own** | **chosen** — accessible, mentor-tone, evokes literacy; mirrors "Reading signals like an analyst" |

### 4. Options path hidden entirely

Not "LOCKED" — **removed from the Learn home path list** until the
canary lifecycle is operational. No card. No placeholder. Honest
absence: if the product doesn't trade options yet, the curriculum
doesn't pretend to teach them yet.

When canary proves, a separate PR adds the path. Until then, glossary
entries for options terms (calls, puts, premium) can exist as standalone
term entries (educational reference) but no PATH points at them.

### 5. New lesson — "Why Great Investors Do Nothing Most Days"

Placed as **Path 1 (How Markets Actually Work) Lesson 3**, not in the
AI-thinking path. The principle is a market truth, not an AI behavior.

This lesson teaches: action ≠ progress in investing; restraint compounds;
holding is a decision; the asymmetry of opportunity-cost-of-action.

---

## Updated First 25 lessons

Lessons 1-5 are the new "How Markets Actually Work" path. Lessons 6-25
are the previously-approved first 20.

| # | Lesson | Min |
|---|---|---|
| 1 | Why prices move when nothing happens                            | 3 |
| 2 | Why most days are quiet                                          | 3 |
| 3 | Why great investors do nothing most days                         | 4 |
| 4 | What an index actually is                                        | 3 |
| 5 | Why timing isn't the lever                                       | 3 |
| 6 | What is a signal — and why isn't it a prediction?                 | 3 |
| 7 | Why the AI doesn't tell you it's confident                       | 3 |
| 8 | How the AI decides when to act                                   | 4 |
| 9 | When the AI goes quiet — and why                                  | 3 |
| 10 | How the AI changes its mind                                      | 3 |
| 11 | NAV, cash, and holdings: the three numbers                      | 3 |
| 12 | Cost basis: what you paid vs what it's worth                    | 3 |
| 13 | Realized vs unrealized — money on paper vs money in the bank    | 4 |
| 14 | Live estimate vs official close: why two numbers, not one        | 3 |
| 15 | Drawdown: the most honest chart in investing                    | 4 |
| 16 | Why paper first                                                   | 3 |
| 17 | What's simulated and what's not                                  | 3 |
| 18 | Replay vs live: why your portfolio shows both                    | 4 |
| 19 | When paper P&L matters and when it doesn't                       | 3 |
| 20 | Position sizing: why all-in is rare                              | 4 |
| 21 | Concentration: when two stocks become one                         | 3 |
| 22 | Why stop-losses protect against you, not the market              | 4 |
| 23 | How drawdowns actually feel                                      | 3 |
| 24 | Paper vs real: what's the same, what's not                       | 4 |
| 25 | Anchoring on your entry price                                    | 3 |

---

## Wireframe 1 — Learn home (`/learn`)

```
┌─────────────────────────────────────────────────────────────┐
│ Briefing  ·  Learn  ·  Portfolio  ·  Journal  ·  More       │  ← top nav (active = Learn)
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Learn                                                      │  ← serif 28px page title
│                                                             │
│  Where you are                                              │  ← section label 12px muted
│  Reading what you own · Lesson 3 of 5         [Continue →]  │  ← serif 17px + accent CTA
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  Featured term of the day                                   │
│  Drawdown                                                   │  ← serif 18px
│  The peak-to-trough decline of an investment.                │  ← Inter 15px muted
│  [Read full entry →]                                         │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  Learning paths                                             │
│                                                             │
│    Foundations                                              │  ← group label, faint
│    ▢ How Markets Actually Work          (5 · 16 min)        │  ← row, hover border-color
│    ▢ How this AI thinks                  (5 · 16 min)        │
│    ✓ Reading what you own                 (5 · 17 min)        │  ← ✓ = completed
│    ▢ Paper trading fundamentals          (4 · 13 min)        │
│                                                             │
│    Risk + reflection                                        │
│    ▢ Risk literacy                        (5 · 18 min)        │
│    ▢ Portfolio psychology                 (5 · 17 min)        │
│                                                             │
│    Skill                                                    │
│    ▢ Reading signals like an analyst    (5 · 20 min)        │
│    ▢ When the AI is wrong                 (5 · 18 min)        │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  Weekly reflection                                          │
│  Saturday, May 18 · 4 questions · 5 minutes                  │
│  [Open this week's reflection →]                            │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  Glossary                                                   │
│  30+ terms, alphabetical and searchable                     │
│  [Browse glossary →]                                         │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  Browse: Briefing · Journal · Portfolio · Track Record      │
│  › Operator                                                  │
└─────────────────────────────────────────────────────────────┘
```

**Information hierarchy**:
1. Where you are (continuation hook — drops user back into in-progress path)
2. Featured term (daily novelty for users who completed everything)
3. Path index, grouped by tier
4. Weekly reflection (Sunday/Saturday hook)
5. Glossary
6. Browse footer

**Forbidden on Learn home**:
- Streak counters
- "Day N of N" counters
- Progress percentages
- Quizzes
- Badges
- Leaderboards
- Path-completion celebrations beyond a single `✓` checkmark

**Mobile (390×844)**:
- Path rows stack full-width
- "Continue →" CTA on its own line below "Where you are"
- Group labels (Foundations / Risk / Skill) stay; spacing tightens 32→24px
- Bottom-tab nav: `[Briefing] [Learn] [Portfolio] [Journal] [≡ More]`

---

## Wireframe 2 — Path page (`/learn/path/:slug`)

```
┌─────────────────────────────────────────────────────────────┐
│ Briefing · Learn · Portfolio · Journal · More               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ← Back to Learn                                            │
│                                                             │
│  How Markets Actually Work                                  │  ← serif 32px
│  Foundations · 5 lessons · 16 min                            │  ← Inter 13px ink-muted
│                                                             │
│  A short orientation to how markets behave when no one      │  ← serif 18px italic
│  is watching. Not how to predict them — how they actually   │     subtle weight
│  move.                                                       │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  Lessons                                                    │
│                                                             │
│    1. Why prices move when nothing happens         (3 min)  │  ← linked row
│    2. Why most days are quiet                       (3 min)  │
│    3. Why great investors do nothing most days      (4 min)  │
│    4. What an index actually is                     (3 min)  │
│    5. Why timing isn't the lever                    (3 min)  │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  After this path                                            │
│  You'll understand why most market days are noise, why      │
│  discipline matters more than activity, and why most         │
│  attempts to time the market underperform doing nothing.    │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  Related concepts                                           │
│  [Drawdown]  [Volatility]  [Index]                          │  ← chips → /learn/concept
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Information hierarchy**:
1. Back link (always top-left)
2. Path title (serif, 32px)
3. Path meta (tier · lessons · time)
4. One-paragraph italic synopsis
5. Lesson list (linear)
6. "After this path" outcome
7. Related concepts chips

**Lesson row affordances**:
- Already-read lessons show `✓` instead of number
- Currently-reading lesson is bold ink-primary
- Unread lessons are ink-secondary
- Hover changes ink color only — no underline, no chevron, no shadow

**Mobile**:
- Lesson rows stack with 12px gap
- "After this path" sits below lessons
- Concept chips wrap to 2-3 rows

---

## Wireframe 3 — Lesson page (`/learn/path/:slug/:lesson_n`)

```
┌─────────────────────────────────────────────────────────────┐
│ Briefing · Learn · Portfolio · Journal · More               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ← Back to How Markets Actually Work · Lesson 3 of 5        │
│                                                             │
│  Why great investors do nothing most days                   │  ← serif 32px
│  4 min · Foundations                                         │  ← Inter 13px muted
│                                                             │
│  Warren Buffett famously sits in Omaha most days reading.   │  ← serif 18px opening
│  He does not look at his portfolio. He does not check       │     line, italic optional
│  prices. He is not bored.                                   │     leading sentence
│                                                             │
│  In a normal year, the U.S. market is open about 252 days.   │  ← Inter 17px body
│  Most of those days are noise — small moves that average     │     line-height 1.7
│  out, with no actionable change to any well-formed thesis.   │
│  An investor who acts on every move is mostly trading        │
│  noise, not information.                                     │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  What the AI does on a quiet day                            │  ← Inter 18px subhead
│                                                             │
│  ArthOS fires roughly one to three signals per week in a    │
│  typical market regime. On most days, it does nothing. In   │
│  the last 30 days, the engine evaluated [N] symbols and     │
│  produced [M] new signals — that's [pct]%.                   │  ← real numbers
│                                                             │
│  When the AI is quiet, the user often feels something is     │
│  broken. Nothing is. The quiet is the discipline.            │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  Why this matters                                            │
│                                                             │
│  Every action has an opportunity cost. The cost isn't only  │
│  the trade fee — it's also the cognitive load, the          │
│  anchoring on entry prices, the temptation to revisit, and  │
│  the loss of attention for actually important things.       │
│                                                             │
│  Holding is a decision. Doing nothing is a discipline.       │
│  Restraint compounds.                                        │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  A question for you                                          │  ← Inter 17px italic
│                                                             │     ink secondary
│  Think back to the last time you opened your brokerage app   │
│  three times in one day. What did you do that you wouldn't   │
│  have done if you'd only opened it once? Was that better,    │
│  or just busier?                                             │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  [Next lesson: What an index actually is →]                  │  ← primary CTA
│                                                             │
│  [Back to today's brief]                                    │  ← secondary, quiet
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Information hierarchy**:
1. Back link with breadcrumb ("Lesson 3 of 5")
2. Lesson title (32px serif)
3. Meta (time + path)
4. Opening line (memorable, 18px serif, sometimes italic)
5. Body paragraphs (17px Inter, 1.7 line-height, 400 words max)
6. One subhead splitting the lesson at ~middle
7. Live-data section (renders real ArthOS numbers in context)
8. Reflection prompt (italic, secondary tone)
9. Single primary CTA (next lesson)
10. Single secondary CTA (back to brief)

**Pedagogical structure**:
- Opening line is memorable (the Buffett-Omaha line)
- Body explains the concept in 2-3 paragraphs
- Subhead breaks to a live-data section
- Final paragraph delivers the principle in tight summary
- Reflection prompt sends the user away with a question, not an answer

**Forbidden on lesson page**:
- Quizzes
- Multiple-choice
- Right/wrong answers
- Streak indicators
- "You're 60% through this path" progress bars
- Trophies / badges / confetti
- Reading-time tickers

**Mobile**:
- Type scales (32→26px title; 18→17px opening; 17→16px body)
- Single-column always
- "Next lesson" CTA bottom-anchored (not floating)

---

## Wireframe 4 — Weekly reflection (`/learn/reflection`)

```
┌─────────────────────────────────────────────────────────────┐
│ Briefing · Learn · Portfolio · Journal · More               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ← Back to Learn                                            │
│                                                             │
│  Weekly reflection                                          │  ← serif 28px
│  Saturday, May 18 — Week ending Friday, May 17              │  ← Inter 14px muted
│                                                             │
│  A short pause. Four questions, five minutes.               │  ← Inter 17px italic
│  Saves locally to your device. Nobody sees this except you. │     secondary tone
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  1. What surprised you this week?                           │  ← Inter 17px ink-primary
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ [text area · 3 lines suggested · ink-primary text]  │    │  ← .calm-card-stack input
│  │                                                     │    │
│  │                                                     │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  2. What the AI got right                                   │
│                                                             │
│  This week the AI opened 2 positions, closed 1, and held    │  ← live data block, Inter 15px
│  the rest. The closed position (AMAT) realized +4.2%.       │     ink-secondary
│                                                             │
│  Your take:                                                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ [text area]                                          │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  3. What the AI got wrong                                   │
│                                                             │
│  This week, no signal that opened in the last 30 days has   │  ← live data
│  closed at a loss yet. The AI's worst open position is      │
│  currently NVDA at −1.1% unrealized.                        │
│                                                             │
│  Your take:                                                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ [text area]                                          │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  4. What you learned                                         │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ [text area · 3 lines suggested]                      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│                                            [Save reflection]│  ← primary button
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  Previous reflections                                       │
│                                                             │
│  Sat 11 May — "Surprised by how quiet the week was…"        │  ← linked rows
│  Sat 04 May — "Learned about drawdown psychology…"          │     to a per-week
│  Sat 27 Apr — "Was anchoring on NVDA entry price…"           │     read-only view
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Honesty constraints**:
- Live data shown for Q2 + Q3 must be deterministic and sourced from real
  paper_trade / paper_position / journal data
- If "got wrong" data shows no losses ("no signal has closed at a loss"),
  the system must surface the WORST open unrealized position — even if it's small.
  No hiding.
- No emoji buttons. No reaction selectors. No "skip this week".
- Save is local-only (localStorage); the data never leaves the device in PR-5.

**Forbidden on reflection page**:
- Sharing widgets
- "Compare your reflection to other users"
- Word-count counters
- Reading-time estimates
- Sentiment auto-classification
- Daily-streak indicators

**Mobile**:
- Single column
- Text areas span full width
- "Save reflection" sticks to bottom of viewport while scrolling

---

## Wireframe 5 — Glossary (`/learn/glossary`)

```
┌─────────────────────────────────────────────────────────────┐
│ Briefing · Learn · Portfolio · Journal · More               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ← Back to Learn                                            │
│                                                             │
│  Glossary                                                   │  ← serif 28px
│  30 terms across investing, the AI, and your portfolio.      │  ← Inter 14px muted
│                                                             │
│  ┌──────────────────────────────────┐    Filter:            │
│  │ Search terms…                     │    [All] [AI]        │  ← search input +
│  └──────────────────────────────────┘    [Portfolio] [Risk] │     calm chips
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  A                                                          │  ← letter divider
│  Anchoring · The tendency to fixate on a number — like…     │  ← term row
│  Average cost · The mean price you paid for a position…      │
│                                                             │
│  B                                                          │
│  Buy signal · An observation by the engine that a pattern…  │
│                                                             │
│  C                                                          │
│  Concentration · When two or more positions move together…  │
│  Conviction band · The AI's structured confidence tier…     │
│  Cost basis · What you paid for an open position…            │
│                                                             │
│  D                                                          │
│  Drawdown · The peak-to-trough decline of an investment…    │
│                                                             │
│  …(continues alphabetically through W)…                     │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  Featured today                                             │
│  Drawdown                                                   │  ← serif 18px
│  A drawdown is the percent decline from a recent peak in     │
│  value. Every investor experiences drawdowns…                │
│  [Read full entry →]                                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Term row anatomy**:
- Term (Inter 16px ink-primary, semibold)
- · separator
- One-sentence definition (Inter 15px ink-secondary, truncates with ellipsis)
- Whole row is a link to `/learn/term/:slug`
- Hover: row ink darkens, no background change

**Filter chip mechanics**:
- 4 chips: All / AI / Portfolio / Risk
- Chips use `.calm-chip` primitive (PR-2)
- Active chip uses accent-faint background
- Clicking shows only terms in that category
- Search input filters by prefix match

**Term page** (`/learn/term/:slug`) sub-template:

```
← Back to Glossary

Drawdown                                                       ← serif 28px
4 min read                                                     ← Inter 13px muted

A drawdown is the percent decline from a recent peak in
value.                                                          ← serif 18px definition

Why it matters
[Inter 17px body, 200-300 words on what makes the concept
load-bearing for an investor]

How the AI uses it
[Inter 17px body, 100-150 words on how ArthOS internally
references this concept]

Related terms
[Volatility]  [Recovery]  [Peak]  [Trough]                   ← chips

Lessons that cover this
• How Markets Actually Work · Lesson 1
• Reading what you own · Lesson 5
• Risk literacy · Lesson 4

[Back to Glossary]
```

**Mobile**:
- Search input full-width
- Filter chips wrap to second row
- Letter dividers retain spacing
- Term rows compress to symbol + one-line definition

---

## Cross-surface integration recap

| From | To | Mechanism |
|---|---|---|
| Briefing "Today's lesson"    | `/learn/path/:slug/:n`            | deterministic mapping |
| Pick Detail concept tag       | `/learn/concept/:slug`            | already wired (PR-4) |
| Pick Detail Learn-more chips  | `/learn/term/:slug`               | already wired (PR-4) |
| Journal entry "Learn from"   | `/learn/path/:slug/:n` (matched lesson) | PR-7 wires this |
| Track Record drawdown chart   | `/learn/term/drawdown`            | PR-6 wires this |
| Learn home Featured term     | `/learn/term/:slug`               | this PR |
| Learn home Weekly reflection | `/learn/reflection`               | this PR |
| Term page → lessons          | `/learn/path/:slug/:n`            | this PR |
| Lesson page → next lesson    | `/learn/path/:slug/:next_n`       | this PR |
| Lesson page → back to brief  | `/briefing`                       | this PR |

Every Learn surface has at most one primary CTA and one secondary
return link. No surface ever exits the user into the wild.

---

## What PR-5 ships

| Asset | Count |
|---|---|
| `/learn` home page                                       | 1 |
| `/learn/path/:slug` path landing                         | 8 templates (8 paths) |
| `/learn/path/:slug/:n` lesson page                       | 25 lessons + 13 placeholder lessons |
| `/learn/term/:slug` term page                            | ~30 terms |
| `/learn/concept/:slug` concept page                      | 6 concepts |
| `/learn/glossary` glossary index                         | 1 |
| `/learn/reflection` weekly reflection                    | 1 |
| Briefing↔Learn selector module                          | 1 deterministic mapping |
| Reflection localStorage adapter                          | 1 read/write helper |
| Cross-link wiring (Pick Detail, Track Record, Journal)   | hooks where surfaces exist; defer others |

**Total files**: ~25-30 React route components + content data files.
**Lines**: ~3000-3500 (content-heavy).

---

## What PR-5 does NOT do

- ❌ No backend endpoints
- ❌ No schemas / migrations
- ❌ No real-time anything
- ❌ No quizzes / streaks / badges / hearts / XP
- ❌ No social / sharing
- ❌ No premium / paid tier
- ❌ No user-generated content
- ❌ No options-related path (hidden until canary)
- ❌ No mobile-app native build (web responsive only)

---

## Approval requested

1. New foundational path "How Markets Actually Work" (5 lessons specified)
2. "Reading Your Portfolio" → **"Reading what you own"**
3. Options path **hidden entirely** until canary proves
4. "Why Great Investors Do Nothing Most Days" placed as **Path 1 Lesson 3**
5. Weekly reflection at `/learn/reflection` with 4 questions, localStorage save
6. 5 wireframes above (Learn home · Path · Lesson · Reflection · Glossary)
7. PR-5 ship list — 8 paths · 25+13 lessons · ~30 terms · 6 concepts · glossary · reflection · cross-link wiring

No code. No implementation. Stopping per directive.
