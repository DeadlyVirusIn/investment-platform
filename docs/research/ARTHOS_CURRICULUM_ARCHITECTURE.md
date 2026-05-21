# ArthOS Curriculum Architecture (PR-5 design)

**Date**: 2026-05-21
**Status**: CURRICULUM DESIGN — no implementation, no UI code
**Identity (locked)**: "Learn how to invest by watching an AI invest, explain itself, and admit mistakes."
**Locked navigation**:
- Desktop: Briefing · Learn · Journal · Portfolio · Track Record
- Mobile bottom-tab: `[Briefing] [Learn] [Portfolio] [Journal] [More]` — Track Record + Operator + Settings live in More
**Briefing publication model**: Daily 7am ET frozen artifact + "Since publication" addendum for material events after publication

This document designs the curriculum behind `/learn`. The product
must feel like a structured investing education system — not a
collection of articles.

---

## 1. Learning paths — 8 paths total

### Tier 1 — Foundational (entry, no prerequisites)

| # | Path name | Lessons | Total time | Outcome |
|---|---|---|---|---|
| 1 | **How this AI thinks**                  | 5 | 16 min | You understand the AI flags patterns, not predictions |
| 2 | **Reading your portfolio**              | 5 | 17 min | You can read a paper portfolio dashboard unaided |
| 3 | **Paper trading fundamentals**          | 4 | 13 min | You know what's simulated and what's not |

### Tier 2 — Risk + reflection (needs Tier 1)

| # | Path name | Lessons | Total time | Outcome |
|---|---|---|---|---|
| 4 | **Risk literacy**                        | 5 | 18 min | You know what protects a position and what doesn't |
| 5 | **Portfolio psychology**                | 5 | 17 min | You can spot your own emotional reactions before they affect decisions |

### Tier 3 — Skill (intermediate, needs Tier 1 + 2)

| # | Path name | Lessons | Total time | Outcome |
|---|---|---|---|---|
| 6 | **Reading signals like an analyst**     | 5 | 20 min | You can read a Pick Detail page without the Learn chips |
| 7 | **When the AI is wrong**                | 5 | 18 min | You can distinguish bad signals from bad market regimes |

### Tier 4 — Locked + mastery

| # | Path name | Status | Outcome |
|---|---|---|---|
| 8 | **Options basics**                       | LOCKED until canary lifecycle proves | (deferred) |
| — | **Mastery articles** (no path, monthly) | independent essays | continual literacy |

### Path completion model

- 5 lessons per Tier-1-2-3 path (4 for Paper Trading Fundamentals)
- Each lesson is 3-4 minutes (200-400 words + one example from real ArthOS data)
- Path complete = all lessons read (read-tracked client-side via localStorage initially)
- **No streaks**, **no hearts**, **no XP** — completion is the only state we track

---

## 2. Lesson progression

### Within a path — linear with optional skip-ahead

Lessons display in fixed order. User can skip any single lesson, but a
path-completion checkmark requires all lessons. Skipping is allowed
because forced-order pedagogy contradicts the "calm mentor" tone — but
the order exists for a reason.

### Across paths — free, with soft recommendations

Each path declares prerequisites. The Learn home page surfaces them
as soft recommendations ("Paths 4-5 work best after Paths 1-3"), not
hard gates.

```
Path 1 (entry) ─┬─► Path 2 ─┬─► Path 4 ─► Path 5
                │            │
                └─► Path 6 ◄─┘
                       │
                       └─► Path 7

Path 3 (entry, parallel — no prereq)
```

### Pedagogical principles

| Principle | How it manifests |
|---|---|
| **One concept per lesson**          | Single-idea title; no "and also" subtopics |
| **Real example from this week**     | Every lesson cites a real ArthOS signal/trade from the past 30 days |
| **Reflection prompt, not quiz**     | Each lesson ends with one question for the reader; no right answers |
| **Spiral curriculum**               | Drawdown appears in Path 2 (definition), Path 3 (how it feels), Path 4 (anchoring), Mastery (math). Concepts deepen across paths. |
| **Honest absence**                  | If a concept is too advanced for a path's tier, the lesson says so explicitly and links forward |
| **Single CTA per lesson**            | "Next lesson" or "Back to briefing" — never both as equal options |

---

## 3. Beginner → Intermediate journey

### Day 1 (signup)

Briefing teaser hook → click "Learn" once. Lands on `/learn`. Sees
"Start with: How this AI thinks · 5 lessons · 16 min." Reads Lesson 1
("What is a signal — and why isn't it a prediction?"). 3 minutes.

**End of Day 1**: 1 lesson complete. User has the foundational mental
model. They know the AI doesn't predict.

### Days 2-7

Daily briefing → "Today's lesson" chip pulls a lesson contextual to
today's signal type. User completes 1 lesson per day.

**End of Week 1**: 5-7 lessons complete. User has finished Path 1.

### Weeks 2-4

User completes Paths 2-3 in parallel (Reading your portfolio + Paper
trading fundamentals). Briefing references concepts from completed
lessons.

**End of Month 1**: 12-14 lessons complete. User can read every
ArthOS surface unaided.

### Months 2-3

Tier 2 paths (Risk literacy + Portfolio psychology) → 10 more lessons.

**End of Q1**: 22+ lessons complete. User is "beginner-complete" —
they understand the product and the basics of investing well enough
to translate to their own decisions.

### Months 4-6

Tier 3 paths (Reading signals like an analyst + When the AI is wrong).

**End of M6**: 32+ lessons complete. User is "intermediate-complete"
— they can interrogate the AI's reasoning critically.

### Months 7-12

Monthly mastery articles + path completion of remaining tiers. No
hard endpoint — literacy compounds.

---

## 4. Concept dependency map

Concepts that ladder through multiple paths:

| Concept | First introduction | Deepens at | Mastery |
|---|---|---|---|
| Signal (≠ prediction)   | P1L1                                | P6L1 (signal taxonomy)              | M article on signal generation |
| Confidence band         | P1L2                                | P6L4                                | — |
| Position sizing          | P3L3 (Paper)                        | P4L1 (Risk)                         | — |
| Cost basis              | P2L2                                | P5L1 (anchoring)                    | — |
| Drawdown                | P2L5                                | P4L4 (how it feels)                 | M article on drawdown math |
| Trim                    | P4L4? (or P5L2)                     | P6L3                                | — |
| Concentration           | P4L2                                | P6L2                                | — |
| Stop-loss               | P4L3                                | P5L4                                | — |
| Mean reversion          | P6L2                                | P7L3                                | M article on reversion arithmetic |
| Momentum                | P6L1                                | P7L1                                | M article on momentum durability |
| Volatility              | P4L4                                | P6L5                                | — |
| Regime                  | P7L4 (intermediate)                 | M article                           | — |
| Quality factor          | P6L4                                | M article                           | — |
| Honest losses           | P5L5                                | P7L5                                | M article on loss psychology |
| Replay vs live          | P3L3                                | P3L4                                | — |

**Spiral discipline**: a concept that appears in 2+ paths must say
something **different** in each. P2L5 introduces drawdown as a number.
P4L4 introduces it as a feeling. M articles introduce it as math.
Same word, three levels of depth.

---

## 5. First 20 lessons — full specification

### PATH 1 — How this AI thinks (5 lessons · 16 min total)

**Lesson 1: "What is a signal — and why isn't it a prediction?"** (3 min)
- Concept: signals are pattern observations, not forecasts
- Real example: today's Pick Detail symbol — show the engine flagged it from a momentum pattern
- Reflection: "Have you ever confused a pattern with a prediction in your own thinking?"

**Lesson 2: "Why the AI doesn't tell you it's confident"** (3 min)
- Concept: conviction band (Low/Medium/High) vs false-precision percentages
- Real example: yesterday's strongest signal — show that "High" doesn't mean 87.3%
- Reflection: "When someone says they're 73% confident in a stock pick, what does that actually mean?"

**Lesson 3: "How the AI decides when to act"** (4 min)
- Concept: thresholds → signal → eligibility filter → execution
- Real example: walk through one recent buy from filter → fill
- Reflection: "What threshold would have to be crossed for you to act on a hunch?"

**Lesson 4: "When the AI goes quiet — and why"** (3 min)
- Concept: no-signal days are a feature, not a bug
- Real example: most recent quiet day from briefing history
- Reflection: "What does it mean when a strategy refuses to trade?"

**Lesson 5: "How the AI changes its mind"** (3 min)
- Concept: thesis invalidation → action change → audit trail
- Real example: a closed position from journal — show the Buy → Trim → Close chain
- Reflection: "How often have you held an opinion past its expiration date?"

### PATH 2 — Reading your portfolio (5 lessons · 17 min)

**Lesson 6: "NAV, cash, and holdings: the three numbers"** (3 min)
- Concept: equity = cash + sum of position market values
- Real example: today's actual NAV breakdown
- Reflection: "If your NAV changes but no trades happened, what caused the change?"

**Lesson 7: "Cost basis: what you paid vs what it's worth"** (3 min)
- Concept: cost basis is anchor; market value is current; difference is unrealized P&L
- Real example: a current open position
- Reflection: "Why does cost basis matter for taxes but not for whether to hold the position?"

**Lesson 8: "Realized vs unrealized — money on paper vs money in the bank"** (4 min)
- Concept: only realized P&L is durable; unrealized can vanish
- Real example: a closed trade with realized P&L vs an open one with unrealized
- Reflection: "When does unrealized profit feel real? Should it?"

**Lesson 9: "Live estimate vs official close: why two numbers, not one"** (3 min)
- Concept: live (Polygon delayed 15 min) vs official EOD snapshot; both are honest
- Real example: today's gap between live and official
- Reflection: "If both numbers are correct, why aren't they equal?"

**Lesson 10: "Drawdown: the most honest chart in investing"** (4 min)
- Concept: drawdown is the peak-to-trough percent decline
- Real example: ArthOS's actual track record drawdown
- Reflection: "If a strategy has a 30% max drawdown, how does that change how much you invest in it?"

### PATH 3 — Paper trading fundamentals (4 lessons · 13 min)

**Lesson 11: "Why paper first"** (3 min)
- Concept: paper trading is a practice rehearsal; not a toy
- Real example: ArthOS's setup — paper-only by design
- Reflection: "If a chef practices recipes before cooking for guests, why don't most investors practice before risking real money?"

**Lesson 12: "What's simulated and what's not"** (3 min)
- Concept: prices = real market; fills = simulated at mid-price; commissions = simulated
- Real example: this week's actual fills
- Reflection: "Which of these would be different in a real brokerage account?"

**Lesson 13: "Replay vs live: why your portfolio shows both"** (4 min)
- Concept: replay = historical rebuild; live = forward; ArthOS shows both, honestly labeled
- Real example: the Replay Recovery Account line on the dashboard
- Reflection: "If a strategy looks great in replay but doesn't trade live yet, what should you trust?"

**Lesson 14: "When paper P&L matters and when it doesn't"** (3 min)
- Concept: paper P&L is useful as proof-of-process, not as a future return promise
- Real example: ArthOS's paper returns disclosed alongside the disclaimer
- Reflection: "If you saw a paper-trading account up 200%, what's the first question to ask?"

### PATH 4 — Risk literacy (5 lessons · 18 min)

**Lesson 15: "Position sizing: why all-in is rare"** (4 min)
- Concept: even high-conviction ideas get capped; sizing is a discipline
- Real example: today's largest position as % of NAV
- Reflection: "If you found a stock you were 90% sure about, how much would you put in it? Why is that wrong?"

**Lesson 16: "Concentration: when two stocks become one"** (3 min)
- Concept: correlated positions are effectively one position
- Real example: ArthOS positions in same sector
- Reflection: "If you own three semiconductor stocks, how many positions do you really have?"

**Lesson 17: "Why stop-losses protect against you, not the market"** (4 min)
- Concept: a stop-loss is a pre-commitment to abandon a wrong thesis
- Real example: a recent stop-loss exit from journal
- Reflection: "Have you ever held a losing position past the point where you knew the thesis was wrong?"

**Lesson 18: "How drawdowns actually feel"** (3 min)
- Concept: drawdown psychology — the math says 20%, the feeling says ruin
- Real example: the worst day from ArthOS history
- Reflection: "How would you behave during the third week of a 15% drawdown?"

**Lesson 19: "Paper vs real: what's the same, what's not"** (4 min)
- Concept: emotional volatility is the part paper can't simulate
- Real example: ArthOS's calmest week vs its worst — same numbers, different feeling if real
- Reflection: "What's the one thing you'd need to test in real money that paper can't show?"

### PATH 5 — Portfolio psychology (Lesson 20)

**Lesson 20: "Anchoring on your entry price"** (3 min)
- Concept: cost basis is a number, not a destiny; the market doesn't know what you paid
- Real example: a position currently under cost — show that the AI doesn't reference the entry when deciding whether to hold
- Reflection: "If you bought NVDA at $700 and it's now $720, would you sell at $720 'just to break even' if you suddenly didn't own it?"

---

## 6. Completion outcomes

| Path | After completing, the user can… |
|---|---|
| 1. How this AI thinks                 | Explain to a friend why signals ≠ predictions |
| 2. Reading your portfolio              | Read every number on `/portfolio` unaided |
| 3. Paper trading fundamentals          | Articulate what's real and what's simulated |
| 4. Risk literacy                       | Explain why position sizing > stock picking |
| 5. Portfolio psychology                | Notice anchoring bias in their own thinking |
| 6. Reading signals like an analyst    | Read a Pick Detail page without the Learn chips |
| 7. When the AI is wrong               | Distinguish a bad signal from a bad regime |
| 8. Options basics (locked)            | (deferred until canary proves) |

**Beginner-complete** (Paths 1-5, ~22 lessons, ~3 months): user has
the language and discipline to be a thoughtful paper-trading observer.

**Intermediate-complete** (Paths 1-7, ~32 lessons, ~6 months): user
can critique the AI's reasoning and identify when the methodology is
mismatched to the market.

---

## 7. How lessons connect to other surfaces

### Briefing → Learn

**Mechanism**: the daily briefing's "Today's lesson" section pulls a
lesson keyed to today's primary story type.

| Briefing story type | Suggested lesson |
|---|---|
| AI opened a new position    | Path 1 Lesson 3 ("How the AI decides when to act") |
| AI closed a position        | Path 1 Lesson 5 ("How the AI changes its mind") |
| AI trimmed a position       | Path 6 Lesson 3 (or P4 Lesson 17 "Why stop-losses protect against you") |
| Quiet day (no signals)      | Path 1 Lesson 4 ("When the AI goes quiet") |
| Position approaching target | Path 5 Lesson 1 ("Anchoring on your entry price") |
| Drawdown reached            | Path 4 Lesson 18 ("How drawdowns actually feel") |
| Concentration rose          | Path 4 Lesson 16 ("Concentration: when two stocks become one") |

**Selector logic**: a small deterministic mapping at briefing render
time picks the lesson. Same backend pattern as the concept tag on
PR-4 Pick Detail.

### Journal → Learn

**Mechanism**: each journal entry (one AI decision) has a "What this
trade can teach you" link.

| Journal entry | Linked lesson |
|---|---|
| Closed at stop-loss          | P4L17 "Why stop-losses protect against you" |
| Closed at target              | P5L1 "Anchoring on your entry price" |
| Closed at max-hold expiry    | P1L5 "How the AI changes its mind" |
| Trimmed                       | P6L3 |
| Opened on momentum signal    | P6L1 |
| Opened on mean-reversion     | P7L3 |

### Pick Detail → Learn (already wired in PR-4)

- Concept tag → `/learn/concept/:slug`
- Learn-more chips → `/learn/term/:slug`
- "What could go wrong" → optional link to a related psychology lesson

### Track Record → Learn

| Track Record element | Linked lesson |
|---|---|
| Drawdown chart                | P2L10 "Drawdown: the most honest chart in investing" + P4L18 |
| Win/loss ratio                | P5L5 (psychology of losses) |
| Realized P&L total           | P2L8 "Realized vs unrealized" |
| Worst trade                   | P7L5 "Learning from losses" |
| Best trade                    | P5L1 "Anchoring on your entry price" |

### Cross-surface principle

**Every other ArthOS surface eventually points at Learn.** Briefing
points daily. Journal points per-entry. Pick Detail points per-concept.
Track Record points per-metric. The result: a user encountering a
concept anywhere in the product can deepen it with one click.

Reverse direction: every Learn lesson ends with a single CTA that
returns to the surface they came from — `Back to today's brief →` or
`Back to Journal →`. The user never gets lost.

---

## 8. Glossary structure (parallel to paths)

`/learn` also exposes a glossary, alphabetical + searchable. Terms map
to a subset of concepts from the paths:

```
A  Anchoring · Average cost
B  Buy signal
C  Concentration · Conviction band · Cost basis
D  Drawdown
E  Equity · EOD snapshot
F  Fill · Factor
G  Growth
H  Hold signal · Honest losses
I  Invalidation
L  Live estimate
M  Mean reversion · Momentum
N  NAV
O  Open position · Operator
P  Paper trading · Position sizing
Q  Quality
R  Realized · Replay · Regime
S  Sell signal · Signal · Stop-loss · Snapshot
T  Trim signal · Track record
U  Unrealized · Universe filter
V  Valuation · Volatility
W  Watchlist
```

Each term page (`/learn/term/:slug`):
- The term
- One-sentence definition
- "Why it matters" paragraph
- "How the AI uses it" (where applicable)
- "Related terms" links
- "Lessons that cover this" — list of lessons referencing the term

Each concept page (`/learn/concept/:slug`):
- The concept (Momentum / Mean reversion / Valuation / Quality / Defensive / Growth)
- 2-3 paragraph explanation
- "How ArthOS uses this concept" — real examples
- "Lessons in this concept" — which path lessons cover it
- "Recent signals using this concept" — pulled from real ArthOS data

---

## 9. Authorship + maintenance discipline

| Concern | Approach |
|---|---|
| Voice consistency           | All lessons written or edited by one operator initially; locked Tier-A lint enforces tone |
| Constitutional compliance   | Every lesson runs through `forbidden_phrases.py` before merge |
| Real-example freshness      | Lessons reference "this week's" or "today's" examples — refreshed quarterly OR auto-derived from live data at render time |
| Honest-loss discipline       | Every path with a "success" example includes one "this is what going wrong looks like" example |
| No quizzes                   | Reflection prompts only; no right/wrong answers |
| No streaks / no XP / no badges | Completion is the only state |
| Length cap                  | 400 words max per lesson; enforced at lint time |

---

## 10. What PR-5 ships

| Asset | Count | Status |
|---|---|---|
| Path index page (`/learn`)             | 1 | new |
| Path landing page (`/learn/path/:slug`) | 7 templates | new |
| Lesson page (`/learn/path/:slug/:n`)   | 20 first-lesson contents + 13 placeholders for paths 1-7 | new |
| Term pages (`/learn/term/:slug`)        | ~30 terms | new |
| Concept pages (`/learn/concept/:slug`)  | 6 concepts | new |
| Glossary index                           | 1 | new |
| Briefing↔Learn selector logic          | 1 small mapping module | new |
| Cross-link contracts                      | from Journal / Pick Detail / Track Record | wired (some already exist) |
| Tier-A lint over every lesson           | enforced in CI | already in place |
| localStorage progress tracking          | per-user reading state | new (no schema change) |

Total lessons authored at PR-5 ship: **20 (first batch)**. Remaining
~12 ship in PR-5a/b as content packs.

---

## 11. What this does NOT do

- ❌ No new backend endpoints
- ❌ No new schema or migrations
- ❌ No accounting / trading / Phase L touches
- ❌ No options lifecycle changes
- ❌ No real-time / streaming
- ❌ No quizzes / hearts / XP / streaks / gamification
- ❌ No paid tier / premium-only lessons (defer)
- ❌ No user-generated content
- ❌ No social features

PR-5 is **content + routing + cross-linking only**. The curriculum is
the product, not a feature.

---

## Stopping

No code. No UI implementation. Awaiting approval on:

1. 8-path structure (§1)
2. Spiral curriculum discipline (§2)
3. Beginner→Intermediate journey (§3)
4. Concept dependency map (§4)
5. First-20-lessons specification (§5)
6. Completion outcomes (§6)
7. Cross-surface link contracts (§7)
8. Glossary structure (§8)
9. Authorship discipline (§9)
10. PR-5 scope (§10)
