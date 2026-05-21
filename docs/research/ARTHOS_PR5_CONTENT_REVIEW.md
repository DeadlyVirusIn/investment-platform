# ArthOS PR-5 Final Content + Learning Review

**Date**: 2026-05-21
**Status**: EDUCATIONAL REVIEW — no implementation
**Identity (locked)**: "Learn how to invest by watching an AI invest, explain itself, and admit mistakes."

Five-lens review of the 25-lesson curriculum approved in the prior PR-5 UX doc, plus design for 4 specific Learn surfaces.

---

## 1. Five-lens review of the curriculum

### Lens 1 — Complete beginner (has never invested)

| Strength | Weakness |
|---|---|
| Lesson 3 "Why great investors do nothing most days" is sticky | L1 "Why prices move when nothing happens" assumes the reader knows what a STOCK is |
| Reflection prompts are accessible | "NAV" introduced as acronym before defining |
| Mentor tone holds | "Cost basis" is a tax term — heavy for non-investors |
| | "Random walk" / "noise" terminology too jargony for absolute beginner |

**Critical hole**: NO lesson on what investing IS. Curriculum jumps to market behavior without "what's a stock". A complete beginner bounces in the first 60 seconds.

### Lens 2 — New ArthOS user (signed up, never traded)

| Strength | Weakness |
|---|---|
| Lessons 11-15 cover the dashboard's vocabulary | No lesson on "How to read the briefing" — the most-used surface |
| Real-data examples ground the abstractions | No lesson on "What does Pick Detail show you?" — second-most-trust surface |
| | No lesson on "How journal entries work" (PR-7 surface) |

The curriculum teaches investing concepts well but misses the surface-specific reading skills new users need on day 1.

### Lens 3 — Teacher

| Strength | Weakness |
|---|---|
| Tier structure has clear cognitive scaffolding | L20 "Position sizing" appears too late — most novice mistakes happen in week 1 |
| Spiral curriculum on Drawdown is exemplary | Stop-loss appears once (P4L17), never returns; no spiral |
| One-concept-per-lesson discipline holds | No formative checks — the system can't tell whether the lesson landed |
| Reflection prompts invite metacognition | Markets path (Tier 0) requires abstract thinking first; some learners need a concrete hook earlier |

### Lens 4 — Behavioral psychologist

| Strength | Weakness |
|---|---|
| Reflection prompts are well-designed metacognition triggers | **No spaced-repetition mechanic** — concepts will fade without resurfacing |
| Cognitive load (3-4 min, ~2 lessons/week) is sustainable | No "you've encountered this before" cue — knowledge feels new each visit even when it's not |
| No gamification (per design) | Without external reinforcement, retention relies entirely on intrinsic motivation |
| Single primary CTA per surface | No "concept-of-the-week" surface that re-activates older lessons |

**Critical mechanic missing**: spaced repetition. Lessons exist; reinforcement does not.

### Lens 5 — Successful long-term investor

| Strength | Weakness |
|---|---|
| L3 "Why great investors do nothing most days" captures the most important truth | **Compound interest is COMPLETELY ABSENT.** The single most important concept in long-term investing has no lesson. |
| Anchoring lesson (L25) is emotionally accurate | "Diversification" appears only as concentration's negative; never as a positive principle |
| Risk literacy path is solid | No "Time in market vs timing the market" — alluded to in L5 but not directly named |
| Honest losses framing is right | No lesson on fees / costs / drag — n/a for paper but a real-world prep |

---

## 2. Specific question answers

### Q1 — Are any lessons missing?

**Yes — 8 missing**, in priority order:

| # | Missing lesson | Belongs in | Why missing matters |
|---|---|---|---|
| 1 | **What is a stock?** | Lesson 0 (new pre-path "Investing basics" — see §3) | Complete beginner needs this; without it the whole curriculum is unfounded |
| 2 | **What is compound interest?** | Investing basics (new Tier 0a) | THE most important long-term concept; absent is a structural failure |
| 3 | **Time in the market vs timing the market** | Markets Path · Lesson 6 (extend Markets path) | Sits next to L3 thematically; reinforces the discipline |
| 4 | **Why diversification matters** | Risk literacy Path · Lesson 6 (extend Risk path) | The positive twin of concentration; currently only the negative is taught |
| 5 | **How to read the briefing** | Reading-what-you-own Path · Lesson 6 | The most-used surface deserves an explicit reading guide |
| 6 | **What does Pick Detail show you?** | How-this-AI-thinks Path · Lesson 6 | The trust surface needs orientation |
| 7 | **How journal entries work** | Reading-what-you-own Path · Lesson 7 | PR-7 surface needs prep; can ship alongside Journal |
| 8 | **Why fees compound** | Real-world preparation; later path | Paper doesn't need this but real-money companion eventually will |

**Recommendation**: add a **new Tier 0a pre-path "Investing basics"** (3-4 lessons), bringing total to 9 paths visible. The product's beginner persona is non-negotiable; "investing basics" cannot be assumed.

### Q2 — Are any lessons redundant?

Two near-overlaps; both stay but should explicitly cross-reference:

| Pair | Overlap | Action |
|---|---|---|
| L2 "Why most days are quiet" + L9 "When the AI goes quiet — and why" | Both about quietness; one is markets, one is AI behavior | Keep both. L9 must reference L2 explicitly: "As you learned in Markets Lesson 2…" |
| L5 "Why timing isn't the lever" + L18 "How drawdowns actually feel" | Both touch on panic-sell psychology | Keep both. L18 must reference L5: "You read in Markets Lesson 5 that timing isn't the lever — this is what that feels like during a drawdown." |

No outright redundancies. Spiral curriculum requires concepts to revisit; the cross-references make that explicit.

### Q3 — Biggest "aha" moments

Ranked by sticky-memory potential:

1. **L3 "Why great investors do nothing most days"** — counter-intuitive; most novice investors believe activity = progress
2. **L7 "Why the AI doesn't tell you it's confident"** — re-frames the whole concept of confidence
3. **L13 "Realized vs unrealized — money on paper vs money in the bank"** — most retail investors don't internalize this
4. **L20 "Position sizing: why all-in is rare"** — confronts a real bias the user has already
5. **L25 "Anchoring on your entry price"** — emotionally loaded; lands during real portfolio dips

These five carry the curriculum. They should each be the **featured-term-of-the-day** rotation at least 4× per year on Learn home.

### Q4 — Likely to be forgotten

Ranked by fade-risk:

1. **L4 "What an index actually is"** — abstract, hard to anchor without follow-up use in the briefing
2. **L11 "NAV, cash, and holdings: the three numbers"** — definition-heavy; will fade unless reinforced weekly in briefing copy
3. **L16 "Why paper first"** — meta-lesson clear on first read but not deeply held
4. **L19 "When paper P&L matters and when it doesn't"** — important but easily skimmed
5. **L17 "What's simulated and what's not"** — fades because users settle into trusting the simulation

**Mitigation** (no gamification): the **"This Week's Concept"** module (§3.C) explicitly resurfaces forgettable lessons via spaced repetition.

### Q5 — Format recommendations

| Should become | Topic | Why |
|---|---|---|
| **LESSON** | What is a stock?                    | Lesson 0 / Investing basics |
| **LESSON** | What is compound interest?          | Investing basics |
| **LESSON** | Time in market vs timing the market | Markets path L6 |
| **LESSON** | Why diversification matters        | Risk path L6 |
| **LESSON** | How to read the briefing            | Reading-what-you-own L6 |
| **LESSON** | What does Pick Detail show you?    | How-AI-thinks L6 |
| **LESSON** | How journal entries work            | Reading-what-you-own L7 |
| **LESSON** | Why fees compound                   | Future real-world path |
| **GLOSSARY TERM** | Compound interest, Stock, Diversification, Income statement, P/E ratio, ETF, Index fund, Fee, Bid/ask, Liquidity | reference depth |
| **CONCEPT PAGE** | Compound interest, Time horizon, Diversification | first-class concept entries |
| **WEEKLY REFLECTION TOPIC** | "Was there a moment this week I wanted to act and didn't?" | restraint |
| **WEEKLY REFLECTION TOPIC** | "What concept from a recent lesson did the AI illustrate this week?" | concept-application |
| **WEEKLY REFLECTION TOPIC** | "How would I have reacted to today's worst position if it were my money?" | emotional rehearsal |
| **WEEKLY REFLECTION TOPIC** | "What did the AI hold longer than I would have?" | comparison to instinct |
| **WEEKLY REFLECTION TOPIC** | "Which decision this week, if reversed, would have changed my opinion of the AI?" | falsification thinking |

---

## 3. Revised path structure (final)

**9 visible paths after this review** (was 8). Adding Tier 0a:

```
Tier 0a — Investing basics  (NEW)
├─ What is a stock?
├─ What is compound interest?
├─ What is a portfolio?
└─ Why investing matters at all

Tier 0 — Markets foundations
├─ Why prices move when nothing happens
├─ Why most days are quiet
├─ Why great investors do nothing most days
├─ What an index actually is
├─ Why timing isn't the lever
└─ Time in market vs timing the market   (NEW · L6 extension)

Tier 1 — Reading the product
├─ How this AI thinks (now 6 lessons — adds "What does Pick Detail show you?")
├─ Reading what you own (now 7 lessons — adds "How to read the briefing", "How journal entries work")
└─ Paper trading fundamentals (4 lessons unchanged)

Tier 2 — Risk + reflection
├─ Risk literacy (now 6 lessons — adds "Why diversification matters")
└─ Portfolio psychology (5 lessons)

Tier 3 — Skill
├─ Reading signals like an analyst (5 lessons)
└─ When the AI is wrong (5 lessons)

(Options basics — HIDDEN until canary)
```

**Lesson count revision**: 25 → roughly 38 lessons in PR-5 ship.

| Path | Original | After review |
|---|---|---|
| Investing basics                | (none) | 4 |
| How Markets Actually Work       | 5     | 6 |
| How this AI thinks              | 5     | 6 |
| Reading what you own            | 5     | 7 |
| Paper trading fundamentals      | 4     | 4 |
| Risk literacy                    | 5     | 6 |
| Portfolio psychology            | 5     | 5 |
| Reading signals like an analyst | 5     | 5 |
| When the AI is wrong            | 5     | 5 |
| (Options basics)                | 0 (hidden) | 0 (hidden) |
| **Total**                        | **39** | **48** |

PR-5 ships 38 lessons authored + 10 placeholders for later content packs.

---

## A. Learn Home — Hero section design

Currently the Learn home leads with "Where you are" continuation hook. Adding a hero that orients the WHOLE product identity for first-time visitors AND degrades gracefully for returning users.

```
┌──────────────────────────────────────────────────────────────┐
│ Briefing  ·  Learn  ·  Portfolio  ·  Journal  ·  More        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│   Learn                                                      │  ← serif 28px page label
│                                                              │
│   Learn how to invest by watching an AI invest,             │  ← serif 28px italic
│   explain itself, and admit mistakes.                        │     identity sentence
│                                                              │
│   ~38 lessons. ~3 months. A few minutes most days,           │  ← Inter 16px ink-secondary
│   one short reflection on weekends.                          │
│                                                              │
│  ─────────────────────────────────────                       │
│                                                              │
│  Where you are                                               │  ← shown only when user
│  Reading what you own · Lesson 3 of 7        [Continue →]    │     has progress
│                                                              │
│  (OR for first-time visitors:)                              │
│                                                              │
│  Start here                                                  │
│  Investing basics · 4 lessons · 12 min       [Begin →]      │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Hero discipline**:
- Identity sentence is verbatim
- Subhead is concrete (lesson count, time commitment)
- No marketing adjectives
- No "join thousands of users"
- No screenshots in the hero
- Hero degrades automatically: shows continuation row for returning users; shows "Start here" for first-time visitors

**Mobile**: identity sentence stays serif but scales to 22px; subhead stays 16px.

---

## B. Tier-completion milestone screen

Triggered when user finishes ALL paths in a Tier. Not a celebration. A reflective pause.

```
┌──────────────────────────────────────────────────────────────┐
│ Briefing  ·  Learn  ·  Portfolio  ·  Journal  ·  More        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│   You've finished the foundations.                           │  ← serif 32px
│                                                              │     no emoji, no trophy
│                                                              │
│   Tier 1 — Reading the product                               │  ← Inter 14px ink-muted
│                                                              │
│   You spent 62 minutes reading 17 lessons across three       │  ← Inter 17px body
│   paths. You can now read any ArthOS surface without help.   │
│                                                              │
│  ─────────────────────────────────────                       │
│                                                              │
│   A short reflection                                         │
│                                                              │
│   Which concept changed how you think the most?              │  ← serif 18px italic
│                                                              │     reflection prompt
│   ┌──────────────────────────────────────────────────────┐   │
│   │ [text area · 3 lines suggested · saved locally]      │   │
│   └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ─────────────────────────────────────                       │
│                                                              │
│   What's next                                                │
│                                                              │
│   ▢ Risk literacy             (6 lessons · 22 min)           │  ← next tier paths
│   ▢ Portfolio psychology      (5 lessons · 17 min)           │
│                                                              │
│   Or take a week off. That's a discipline too.              │  ← serif 16px ink-secondary
│                                                              │     italic
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Discipline**:
- Header is observational ("You've finished") not celebratory ("Congratulations!")
- Body uses real counts (62 minutes, 17 lessons, three paths) — not vague claims
- Reflection prompt is open-text; saves to localStorage; never shared
- "What's next" presents Tier 2 paths as quiet options, not pressure
- The closing line — "Or take a week off. That's a discipline too." — is the load-bearing trust signal. It tells the user the product isn't trying to keep them engaged at all costs.

**Forbidden on this screen**:
- Badges, trophies, confetti, animations
- "Day N of N streak"
- Progress bars showing % of total curriculum
- "Share your milestone"
- "Tell a friend"

---

## C. This Week's Concept module

The spaced-repetition mechanic without gamification. Each week one concept from the lesson library gets re-surfaced across three places.

### Where it appears

| Surface | How |
|---|---|
| Learn home                | Featured card immediately under hero |
| Briefing                  | One sentence references "this week's concept" within the daily narrative |
| Weekly reflection        | One of the four questions ties to this week's concept |

### How concepts get selected

Deterministic rotation. Each week's concept is picked by a small module that considers:
1. Concepts user has read but not encountered in a briefing in >14 days
2. Concepts relevant to the current portfolio state (e.g., if drawdown is deep this week, surface "drawdown")
3. Concepts the user just read (NOT — give them a week to settle before re-surfacing)

The selection is recorded weekly so the system never picks the same concept two weeks in a row.

### Wireframe — Learn home module

```
This week's concept

Drawdown

You first encountered this in Reading what you own · Lesson 5.
We're returning to it this week because the portfolio is in its
deepest decline of the past month.

How the AI uses it
ArthOS measures drawdown daily and shows it on Track Record.

Where you'll see it this week
In tomorrow's briefing and Saturday's reflection.

[Read full entry →]                                            ← single CTA
```

**Discipline**:
- The reason ("we're returning to it this week because…") must be a real, observable fact — never invented
- "Where you'll see it this week" is a concrete promise that the briefing and reflection follow through on
- No "concept of the day" — once a week is enough; daily would overwhelm
- No quiz on "do you remember this?" — that's gamification

### Briefing integration

Tomorrow's briefing copy (deterministic mapping) might read:

> "AMAT is currently down −2.1% from its recent peak in your portfolio. That's a small drawdown — a concept this week is revisiting."

The italic phrase is a soft inline link to `/learn/term/drawdown`.

### Reflection integration

That Saturday's reflection question (Q4 "What you learned") gets pre-filled with the concept:

> "This week we revisited drawdown. Did anything you saw in the portfolio make the concept feel real?"

User can answer or skip.

---

## D. Path-completion experience

Lighter than Tier completion. Same discipline.

```
┌──────────────────────────────────────────────────────────────┐
│ Briefing  ·  Learn  ·  Portfolio  ·  Journal  ·  More        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│   Path complete: Risk literacy.                              │  ← serif 28px
│                                                              │
│   6 lessons. ~22 minutes of reading.                         │  ← Inter 15px ink-muted
│                                                              │
│  ─────────────────────────────────────                       │
│                                                              │
│   You now understand position sizing, concentration,        │  ← Inter 17px body
│   diversification, drawdown psychology, why stops protect    │     real concrete list
│   against you, and what real money would feel different.    │
│                                                              │
│  ─────────────────────────────────────                       │
│                                                              │
│   A short reflection                                         │
│                                                              │
│   Which lesson surprised you most?                           │  ← reflection prompt
│                                                              │
│   ┌──────────────────────────────────────────────────────┐   │
│   │ [text area · saved locally]                          │   │
│   └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ─────────────────────────────────────                       │
│                                                              │
│   Continue                                                   │
│   [Next path: Portfolio psychology →]                        │  ← single primary CTA
│                                                              │
│   Or pause. Restraint compounds.                             │  ← italic ink-secondary
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Discipline**:
- Same "no celebration" pattern as Tier completion, scaled smaller
- Body is concrete — lists the actual concepts the user now understands, sourced from the path's lesson titles
- Reflection prompt is per-path; localStorage save
- "Or pause. Restraint compounds." — closing line reinforces the identity (the AI's L3 lesson applied to the user)

**No** progress bar showing N/M paths complete. No tier-completion preview ("3 more paths until next tier!"). The user finds the next tier when they're ready.

---

## Summary of additions vs prior PR-5 plan

| Change | Source |
|---|---|
| **New Tier 0a "Investing basics"** with 4 lessons (What is a stock? · Compound interest? · What is a portfolio? · Why investing matters at all) | Beginner + investor lens |
| **Markets path extended** — adds "Time in market vs timing the market" (L6) | Investor lens |
| **How this AI thinks extended** — adds "What does Pick Detail show you?" (L6) | New-user lens |
| **Reading what you own extended** — adds "How to read the briefing" (L6) + "How journal entries work" (L7) | New-user lens |
| **Risk literacy extended** — adds "Why diversification matters" (L6) | Investor lens |
| **L9 cross-references L2** explicitly; **L18 cross-references L5** explicitly | Teacher lens |
| **"This Week's Concept"** spaced-repetition module designed across Learn home + Briefing + Reflection | Behavioral psychologist lens |
| **Tier-completion screen** designed (observational, no celebration) | All lenses |
| **Path-completion screen** designed (lighter, same discipline) | All lenses |
| **Learn home Hero** with identity sentence + degrade-gracefully behavior | Beginner + new-user lens |
| **New glossary terms**: Compound interest · Stock · Diversification · Income statement · P/E ratio · ETF · Index fund · Fee · Bid/ask · Liquidity | Investor + beginner lens |
| **New concept pages**: Compound interest · Time horizon · Diversification | Investor lens |
| **5 weekly reflection topics specified** | Behavioral psychologist lens |

---

## Final PR-5 ship list (revised)

| Asset | Count |
|---|---|
| Routes                              | unchanged (Learn home · Path · Lesson · Term · Concept · Glossary · Reflection) |
| Paths visible                       | **9** (was 8 — Investing basics added) |
| Lessons authored in PR-5           | **38** (was 25 — added 13 new lessons across 5 paths) |
| Lesson placeholders                  | 10 (for later content packs) |
| Glossary terms                       | **40+** (was 30 — added 10 missing terms) |
| Concept pages                        | **9** (was 6 — added Compound interest · Time horizon · Diversification) |
| Tier-completion milestone surface   | 1 (new) |
| Path-completion milestone surface   | 1 (new) |
| This Week's Concept module          | 1 (new — Learn home component + Briefing integration + Reflection integration) |
| Learn home Hero                      | 1 (new, with degrade-gracefully behavior) |
| Briefing↔Learn selector             | enhanced to feed This Week's Concept |
| Reflection localStorage              | enhanced with concept-of-the-week question |

**Total lines** (estimate): ~5000-6000 lines (content-heavy; ~300 words per lesson × 38 lessons + glossary entries + concept pages + UI shell).

---

## What stays locked from prior PR-5 plan

- No quizzes, streaks, XP, badges, social, gamification
- No backend endpoints
- No schema changes
- No options-related path
- Reflection localStorage-only
- All copy passes Tier-A 30-phrase lint
- 5 wireframes from prior PR-5 doc unchanged
- Cross-surface integration unchanged

---

## Final approval needed before implementation

1. **Add Tier 0a "Investing basics" path** (4 lessons: stock · compound interest · portfolio · why investing matters)
2. **Add 5 extension lessons** to existing paths (per §3 table)
3. **Cross-reference L9↔L2 and L18↔L5** explicitly in lesson copy
4. **This Week's Concept module** at Learn home + Briefing + Reflection
5. **Tier-completion milestone surface** per §B wireframe
6. **Path-completion milestone surface** per §D wireframe
7. **Learn home Hero** with identity sentence per §A wireframe
8. **10 new glossary terms** authored in PR-5
9. **3 new concept pages** authored in PR-5
10. **5 weekly reflection topics** rotated deterministically

Total PR-5 effort revised: **~2 focused days** (was ~1 day; content load doubled).

No code. No implementation. Stopping per directive.
