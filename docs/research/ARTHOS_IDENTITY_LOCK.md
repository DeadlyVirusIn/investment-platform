# ArthOS Identity Lock — Final Review

**Date**: 2026-05-21
**Status**: STRATEGIC DECISION REVIEW — no implementation

Five-lens evaluation: Founder · PMF reviewer · UX strategist · Fintech
product leader · Competitive analyst.

---

## Candidate identities — 4-way comparison

### A. AI Investing Mentor

| Dimension | Detail |
|---|---|
| Target user            | Nervous beginner 25-35, wants guidance |
| Emotional outcome      | Reassurance — "someone smart is watching for me" |
| Retention mechanism    | Daily check-in: "what does my mentor say today" |
| Regulatory considerations | **HIGH risk** — "mentor" implies advisor relationship; SEC scrutiny; potential RIA registration; "personalized recommendations" framing |
| Competitive position   | Direct collision with Wealthfront / Betterment (both licensed RIAs); we get squashed |
| UX implications        | Hero AI voice; conversational tone; daily briefing as primary surface |
| Strengths              | Emotionally resonant; intuitive market framing; clear value prop |
| Weaknesses             | Regulatory ceiling; cannot operationalize without RIA license; indistinguishable from existing robo-advisors; risks "advice without license" enforcement |

### B. Learning Platform

| Dimension | Detail |
|---|---|
| Target user            | Curious learner 22-40, wants to understand markets BEFORE risking money |
| Emotional outcome      | Empowerment — "I'm getting smarter; I understand the game" |
| Retention mechanism    | Spaced lessons + path progress + daily new-thing ("Duolingo for investing") |
| Regulatory considerations | **LOWEST risk** — education is protected speech, not advice; no fiduciary duty |
| Competitive position   | vs Coursera/Khan/Duolingo (none focused on investing); vs Investopedia (text-heavy, static); **open lane** |
| UX implications        | Lessons-first home; paths visible; AI portfolio is the LIVING EXAMPLE (textbook becomes alive) |
| Strengths              | Duolingo-style retention compound; no regulatory risk; unique positioning; "Duolingo of investing" is a fundable narrative; teacher-not-advisor frame |
| Weaknesses             | Slower monetization path than advisor; education may feel "less urgent" to some segments; needs strong lesson library to be credible |

### C. AI Investing Journal

| Dimension | Detail |
|---|---|
| Target user            | Reflective investor 28-45, already trades or holds positions, wants structured thinking |
| Emotional outcome      | Clarity + reflection — "I see my own patterns now" |
| Retention mechanism    | Journal habit (Day One / Daylio / YNAB pattern) |
| Regulatory considerations | LOW — journaling about an AI's behavior is not advice |
| Competitive position   | Nobody positioned here; novel category; "AI's portfolio is the journal" angle is fresh |
| UX implications        | Chronological narrative is the home; calm cards; per-trade retrospective |
| Strengths              | Novel category; defensible; deep moat in narrative quality; very ArthOS-tone |
| Weaknesses             | Appeals to a smaller segment (people who already invest); less viral than learning; "journal" may feel passive/historical |

### D. AI Investment Copilot

| Dimension | Detail |
|---|---|
| Target user            | Active retail investor 25-40; already invests, wants assistance not replacement |
| Emotional outcome      | Confidence — "I have a second brain" |
| Retention mechanism    | Query-based — opened when user has a specific question |
| Regulatory considerations | MEDIUM — "copilot" implies guidance; less than advice but more than education; depends on response framing |
| Competitive position   | Direct collision with FinChat, Magnifi, and every "AI for finance" startup launching in 2026; ChatGPT eats this lane within 12 months as it adds finance plugins |
| UX implications        | Chat-first home; conversational; search-driven; relies on a hallucination-safe backend that does not yet exist |
| Strengths              | Tech-zeitgeist; rides the "every product is a Copilot" wave |
| Weaknesses             | Hallucination risk is existential; every product is becoming a Copilot, so the category is commoditizing; ChatGPT's roadmap eats this lunch; needs serious backend investment before UX makes sense |

---

## 1. Chosen identity

**B. Learning Platform — with Journal elements (C) folded in as living textbook.**

The AI's daily activity becomes the lesson material. The user learns BY watching an AI invest, not BY being advised. The journal is the textbook; the learner is the protagonist.

Reasoning:
- **Lowest regulatory ceiling** — education is protected speech
- **Highest defensible moat** — literacy compounds over years; competitors cannot speedrun a 6-month-old user
- **Most fundable narrative** — "Duolingo of investing" is a known-good investor pitch
- **Hardest for coalition to copy** — Wealthfront/Betterment/FinChat/Magnifi/Robinhood are advisors/tools/chats, none are *teachers*
- **Compounds with our existing infrastructure** — Phase L envelopes ARE the curriculum; honest-losses ARE the lesson; HONEST-BANNER stays load-bearing
- **No PR-1..PR-4 work wasted** — Pick Detail becomes a lesson surface; Today becomes a daily lesson + briefing artifact; Track Record becomes the proof

Identity sentence:

> **"Learn how to invest by watching an AI invest, explain itself, and admit mistakes."**

---

## 2. Tagline

Single-line market-facing tagline:

> **"Watch an AI invest. Learn how it thinks."**

Subhead (when more room):
> "Every decision explained. Every mistake shown. No real money involved."

---

## 3. Product promise

**The promise to a new user**:

> In 90 days, you'll understand how an AI investor thinks about risk, sizing, momentum, and when to be wrong — well enough to translate it to your own decisions.

This promise is:
- **Time-bounded** (90 days — calibrates expectation)
- **Outcome-specific** (understand, not "make money")
- **Defensible** (we don't promise returns; we promise literacy)
- **Falsifiable** (user can self-assess at day 90)
- **Honest** (no real money is part of the promise itself)

---

## 4. Primary user

**Curious beginner, 22-35**, with these characteristics:
- Some disposable income (~$5K-$50K eventually for real investing)
- Currently intimidated by brokerages or burned by gambling-tone products
- Reads NYT / Morning Brew / Substack / Atlantic
- Already uses one daily-habit product (Duolingo / Calm / Headspace / NYT The Daily)
- Trusts content over influencer-pitched products
- Will return if they feel smarter each visit; will leave if they feel sold-to

Secondary user: **Intermediate investor** who wants a methodological second opinion + a transparent AI-portfolio to compare against — but the primary product decisions are made for the beginner.

---

## 5. Core habit loop

### Daily loop (target: 3-5 min per session, 4+ sessions per week)

```
Open app
   ↓
[/learn home]
"Today's lesson: What does 'trim' mean?"  (3 min read)
   ↓
"While you were away, the AI…"
"Trimmed AMAT after a +4% move."
[See briefing →]
   ↓
[/briefing]
Narrative card — what the AI did, why, what we noticed
   ↓
"Continue your path: Reading your portfolio · Lesson 3 of 5"
   ↓
User closes — feels +1 concept smarter, with a real example
```

### Weekly loop (target: 1× per week, 8-10 min)

```
Sunday morning
   ↓
[/review/weekly]
"This week the AI did 6 things. Here's the one that matters."
"You learned 3 new terms this week. Quiz?"
"Your portfolio psychology score moved from 'anchoring on entry' to 'tolerating drawdown' — keep going."
   ↓
User feels +1 layer wiser; books next week's reading commitment
```

### Lifetime loop (the moat)

```
After 90 days:
   - 60+ lessons completed
   - 200+ AI decisions journaled and read
   - Self-assessment: "I now understand what a stop-loss is, when to trim, why concentration matters"
   - Optional: start a real brokerage account elsewhere — but ArthOS is still the daily learning ritual

After 1 year:
   - Multi-year learning paths visible
   - User has a "thinking like an investor" identity
   - High switching cost: nowhere else has the AI-portfolio-as-textbook + 1-year history
```

The retention compound: **you cannot graduate**. Literacy is infinite. Every new market regime is new lesson material.

---

## 6. Final navigation

### Primary (5 slots, ordered left-to-right desktop / bottom-tab mobile)

```
1. Learn         (HOME — paths + today's lesson + glossary)
2. Briefing      (the daily artifact — what the AI did today)
3. Journal       (chronological AI decisions, browsable)
4. Portfolio     (state check; demoted from previous "Today" status)
5. Track Record  (lifetime + honest losses + drawdown narrative)
```

### Mobile (bottom-tab, 4 visible + More drawer)

```
[Learn] [Briefing] [Journal] [Track Record]    [≡ More]
```

`Portfolio` lives in the More drawer alongside Operator, Settings. Reasoning: on mobile a beginner doesn't need a portfolio check most sessions; they need the lesson + briefing.

### Floating

`Ask` (Copilot) — feature button, reachable from any page, **deferred** until hallucination-safe backend lands. Not a destination.

### Hidden (operator escape)

`Operator` accessed via More drawer or direct URL. Engineering surfaces (Decisions / Signal Lab / Alpha Lab / Ops / Risk / Diagnostics) live here. Never primary.

---

## 7. Homepage structure

Route: `/learn` (the new home after login).

```
┌─────────────────────────────────────────────────────────────┐
│ ArthOS                Learn  Briefing  Journal  Portfolio  Track Record │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Your path                                                  │
│  Reading your portfolio · Lesson 3 of 5    [Continue →]    │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  Today's lesson                                             │
│  What does "trim" actually mean?               (3 min)     │
│  Trim is a partial reduction of an open position…           │
│  [Read today's lesson →]                                    │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  The AI's day so far                                        │
│  Trimmed AMAT after a +4% move.                             │
│  [See today's briefing →]                                   │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  All paths                                                  │
│                                                             │
│  ▢ How this AI thinks                  (5 lessons · 12 min)│
│  ▢ Reading your portfolio              (5 lessons · 15 min)│
│  ▢ Risk literacy                       (5 lessons · 18 min)│
│  ▢ Portfolio psychology                (5 lessons · 14 min)│
│  ▢ Paper trading fundamentals          (4 lessons · 10 min)│
│  ▢ Options basics                      LOCKED              │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  Glossary  ·  Featured term: "Drawdown"                     │
│  [Browse all terms →]                                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**First-fold contract**: every visitor sees at minimum (1) their current path position, (2) today's lesson title + 1-line preview, (3) a single CTA. Nothing else competes for attention.

**No NAV number on home**. NAV lives on `/portfolio`. Home is for learning.

**Below fold**: AI's day so far (1 narrative card) + path index + glossary entry point.

---

## 8. 12-month product vision

### Months 1-3 — Foundation

- Identity locked (PR-0)
- Design system locked (PR-4.5)
- `/learn` home with paths + glossary + today's lesson (PR-5)
- `/briefing` daily artifact (PR-6 — replaces dashboard Today)
- `/journal` chronological AI decisions (PR-7)
- `/track-record` honest history (PR-8)

End of Q1: a beginner can complete one full path, read the AI's daily output for 30 days, and have a track-record view that shows wins + losses at equal weight.

### Months 4-6 — Differentiation

- `/compare` AI vs Me — the moat (PR-9)
- `/review/weekly` weekly recap (PR-10)
- Mobile bottom-tab nav (PR-11)
- Marketing landing page (PR-12) — first visitor surface
- Onboarding / risk profile (PR-13)

End of Q2: new visitors have a calm landing → 3-question onboarding → first lesson; existing users get a Sunday recap email; AI-vs-Me comparison gives intermediate users a reason to stay.

### Months 7-9 — Depth + retention

- Settings + AI Identity page (PR-14)
- Operator containment (PR-15)
- Lessons library expansion (12 → 30 lessons; 3 paths → 6 paths)
- Per-trade retrospective lessons (lesson tied to a closed paper trade)
- Premium content tier consideration (deep lessons, options literacy, real-money companion content)

End of Q3: the product has 6 paths · 30+ lessons · ~180 AI decisions journaled · mobile-first usable.

### Months 10-12 — Conversational layer (only when ready)

- Copilot UI shell with hallucination-safe backend (PR-16) — gated on Phase L+ extensibility research
- "Ask the tutor" framing (not advisor)
- Cited answers sourced from envelope + decision_log + glossary

End of Q4: ArthOS is a daily learning ritual, weekly reflection, lifetime journal, and AI tutor — in that order of dominance.

### Year 2 outlook (not in this 12-month plan)

- Real-money companion product? (regulatory gate — separate research)
- Mobile-native iOS / Android (if web is validated)
- Community / journal-sharing (controversial — risks losing calm tone)
- Per-language localization (after EN literacy library is mature)

---

## 9. Updated roadmap — ranked by business value

| Rank | PR | Scope | Business value rationale | Effort |
|---|---|---|---|---|
| **0** | Identity lock | Adopt §1 sentence + §2 tagline + §3 promise as constitutional locks | Defines every downstream PR; without this nothing else has direction | none (decision) |
| **1** | PR-4.5 | Token + Fraunces upgrade (CSS only) | Survives any identity; compounds across every page; cheapest leverage | S |
| **2** | PR-5 | `/learn` home + 5 paths + 20 lessons + glossary (concept routes + term routes) | **Closes 16 dead chip links from PR-4**; makes the identity visible; primary home route | M (1d) |
| **3** | PR-6 | `/briefing` daily artifact (replaces dashboard Today) | Daily habit loop; biggest retention lever | M (1d) |
| **4** | PR-7 | `/journal` chronological AI narrative | Highest "feel smarter" surface; depth retention | M (1d) |
| **5** | PR-8 | `/track-record` honest history with drawdown | Trust narrative; equal-weight losses are the moat signal | S (3-4h) |
| **6** | PR-9 | `/compare` AI vs Me | **Unique moat — coalition cannot replicate cheaply** | M-L (1-2d, needs user paper-pick capture) |
| **7** | PR-10 | `/review/weekly` recap + optional email digest | Industry-proven retention pattern; defends against email-only competitors | M (1d) |
| **8** | PR-11 | Mobile bottom-tab nav | Mobile-first novice persona; reach | S (4-6h) |
| **9** | PR-12 | Marketing landing page | First visitor surface — currently zero coverage | M (1d) |
| **10** | PR-13 | Onboarding + risk profile | Conversion gate; only meaningful AFTER Learn is the home | M (1d) |
| **11** | PR-14 | Settings + AI Identity page | Utility + methodology transparency | S (4-6h) |
| **12** | PR-15 | Operator containment + rename Advanced→Operator | Cleanup; hide operator surfaces from default | S (3h) |
| **13** | PR-16 | Copilot UI shell — only after hallucination-safe backend research | Deferred; high risk if backend forced; nice-to-have not need-to-have | M (1d UI; backend separate Phase) |

### What's removed from prior plan

- **Today as dashboard home** — replaced by `/learn` as home, `/briefing` as daily artifact
- **Ideas page** — folded into Briefing's "today's signals" section
- **Copilot in primary nav** — moved to floating button, deferred to PR-16
- **Decisions audit** — moved to Operator containment

### What's added vs prior plan

- **PR-0 Identity lock** (decision doc)
- **PR-5 expanded** — `/learn` home, not just a hub; 16-chip route coverage included
- **PR-7 Journal** — new page, was missing
- **PR-9 Compare AI vs Me** — new page, was missing
- **PR-10 Weekly Review** — new page, was missing
- **PR-11 Mobile bottom-tab** — was secondary, now first-class

### Total wall-clock estimate

PR-4.5 → PR-12: roughly **9-11 focused days** to ship the foundation + differentiation. After PR-12 the product can be promoted publicly. PR-13 onward is post-launch polish.

---

## What this lock means for already-shipped PRs

PR-1 / PR-2 / PR-3 / PR-4 are **not wasted**:

| Shipped | Where it goes in new architecture |
|---|---|
| PR-1 TodayPage (calm shell + tokens + nav) | Tokens stay (PR-4.5 upgrades them); shell pattern reused on every new route; "Today" route becomes `/briefing` |
| PR-2 TodayPortfolioPage + primitives.css + PickModal calm variant | TodayPortfolioPage becomes `/portfolio` (demoted from primary slot but functional); primitives.css stays; PickModal calm variant stays |
| PR-3 WhatChangedCard + RecentMovesStrip + AITrackRecord | All three components move onto `/briefing`; AITrackRecord block becomes a smaller link to full `/track-record` page (PR-8) |
| PR-4 PickDetailPage (9 sections) | Stays as-is; reachable from `/journal` entries + `/briefing` "today's trade" links |

No code is thrown away. The route SLOTS change; the components don't.

---

## What the user must explicitly approve before any more code ships

1. **Identity sentence**:
   > "Learn how to invest by watching an AI invest, explain itself, and admit mistakes."
2. **Tagline**:
   > "Watch an AI invest. Learn how it thinks."
3. **Product promise**:
   > "In 90 days, you'll understand how an AI investor thinks well enough to translate it to your own decisions."
4. **Primary user**: curious beginner 22-35, lower-stakes ($5K-$50K eventually)
5. **Core daily loop**: lesson → briefing → continue path (3-5 min)
6. **Final navigation**: Learn / Briefing / Journal / Portfolio / Track Record + floating Ask + hidden Operator
7. **Homepage**: `/learn` is the route after login, not `/today`
8. **12-month vision**: foundation Q1, differentiation Q2, depth Q3, conversational Q4
9. **Revised roadmap order** (the table in §9)
10. **PR-1..PR-4 retention** — keep all shipped code, repurpose slot semantics

---

## Stopping

No code in this review. No diffs. No components. Awaiting decision on the 10 explicit approvals above.
