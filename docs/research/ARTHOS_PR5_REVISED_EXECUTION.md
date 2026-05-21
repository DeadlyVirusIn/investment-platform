# PR-5 Revised Execution Plan — Validation-First, Not Content-First

**Date**: 2026-05-21
**Status**: BUILD PLAN — revised per directive (split into 3 PRs, validate after PR-5A)
**Constraint**: ship something users experience sooner; not a giant content dump

---

## Three-PR split

| PR | Scope | Lessons | Validation gate |
|---|---|---|---|
| **PR-5A** | Infrastructure + Learn Home + Path/Lesson/Term/Glossary pages + 3 foundational paths + Glossary MVP + Concept STUBS | **16 lessons** (Investing Basics 4 + Markets 6 + How AI thinks 6) | **REQUIRED**: visual review on Haiku before PR-5B |
| **PR-5B** | Remaining 6 paths + remaining 25+ glossary terms + 9 full concept pages | **32 lessons** | standard lint + visual check |
| **PR-5C** | Reflection page + This Week's Concept module + Tier/Path completion screens | 0 (logic + UX only) | standard lint + behavior check |

Total: 48 lessons + 40+ terms + 9 concepts shipped across 3 PRs.

---

## PR-5A — Learn MVP

### Scope

**Infrastructure**:
- 7 routes (skeleton in PR-5A; reflection route ships skeleton, full page in PR-5C)
- `apps/web/src/lib/learn/curriculum.ts` (schema)
- `apps/web/src/lib/learn/progress.ts` (localStorage progress)
- Primitives extension: `.calm-input`, `.calm-divider`, `.calm-letter-divider`, `.calm-checkmark`

**Pages**:
- `LearnHomePage.tsx` — hero + WhereYouAre + FeaturedTerm + PathList + Glossary link
  - NO "This Week's Concept" card yet (deferred to PR-5C)
  - NO "Weekly reflection" link yet (deferred to PR-5C)
- `LearnPathPage.tsx` — path landing with lesson list + outcomes + related concepts
- `LessonPage.tsx` — full lesson rendering with reflection prompt + next/back CTAs
- `TermPage.tsx` — term definition + related + lessons-that-cover-this
- `ConceptPage.tsx` — **stub variant** (1 paragraph + lesson links; full content in PR-5B)
- `GlossaryPage.tsx` — alphabetical list + search + filter chips

**Content — 3 foundational paths only**:
- Investing Basics (4 lessons: stock · compound interest · portfolio · why investing)
- How Markets Actually Work (6 lessons: prices move · quiet days · do nothing · what is index · timing isn't lever · time-in vs timing)
- How this AI thinks (6 lessons: what is a signal · why no confidence · how AI decides · when AI goes quiet · how AI changes mind · what Pick Detail shows)

**Glossary MVP — 16 terms** (specifically chosen to resolve PR-4 chip targets):
- buy-signal · sell-signal · trim-signal · hold-signal
- stop-loss · cost-basis · drawdown · concentration · position-sizing · volatility
- nav · paper-trading · live-estimate · official-close · realized · unrealized

**Concept stubs — 6 short pages** (1 paragraph each, to close the PR-4 chip 404 gap):
- momentum · mean-reversion · valuation · quality · defensive · growth

Each concept stub: definition + "Deeper content in next release" placeholder + lessons-that-cover-this (currently empty until PR-5B).

**Cross-link wiring**:
- App.tsx mounts 7 routes
- Pick Detail term chips (10) all resolve to real term pages
- Pick Detail concept tags (6) resolve to stub pages (no 404)
- Learn home featured term wired to real glossary entry

### What PR-5A does NOT include

- ❌ Reflection page content (route exists; renders "Available next release" placeholder)
- ❌ This Week's Concept module
- ❌ Tier-completion screen
- ❌ Path-completion screen
- ❌ Remaining 6 paths (32 lessons)
- ❌ Full concept pages (stubs only)
- ❌ 25+ additional glossary terms
- ❌ BriefingPage integration (waits for PR-6 BriefingPage to land; otherwise lessonSelector module ships dormant)

### Effort breakdown

| Task | Hours |
|---|---|
| Routes + skeleton + primitives extension                            | 1.5 |
| Lesson schema (`curriculum.ts`)                                     | 1.0 |
| LearnHomePage (without ThisWeeksConcept + Reflection link)         | 1.5 |
| LearnPathPage template                                              | 1.0 |
| LessonPage template (handles all content types)                     | 1.5 |
| TermPage + GlossaryPage + search + filter chips                     | 2.5 |
| ConceptPage stub variant + 6 concept stubs                          | 1.5 |
| Reflection route skeleton (placeholder copy)                        | 0.5 |
| Content: Investing Basics (4 lessons × ~20 min)                     | 1.5 |
| Content: Markets (6 lessons × ~20 min)                              | 2.0 |
| Content: How AI thinks (6 lessons × ~20 min)                        | 2.0 |
| Content: 16 glossary terms (definition + why-matters + how-AI-uses) | 2.5 |
| Cross-link verification (PR-4 chips resolve, no 404)                | 0.5 |
| Validation + lint cleanup                                            | 1.0 |
| **PR-5A total**                                                      | **~20 hours** |

**~2.5 focused days** wall-clock for PR-5A.

### PR-5A success criteria

| # | Criterion |
|---|---|
| 1 | All 7 Learn routes render without console error |
| 2 | 3 paths fully populated (Investing Basics + Markets + How AI thinks) |
| 3 | 16 lessons render with real content |
| 4 | 16 glossary terms render with full definitions |
| 5 | 6 concept stubs render (no 404) |
| 6 | **All 10 PR-4 Pick Detail term-chip targets resolve** |
| 7 | **All 6 PR-4 Pick Detail concept-tag targets resolve** (stubs, not 404) |
| 8 | Reflection route renders "Available next release" placeholder |
| 9 | All 4 constitutional lints PASS |
| 10 | TypeScript clean |
| 11 | Mobile (390×844) + desktop (1280×800) usable |
| 12 | Zero PR-4 chip 404 |

---

## **Validation gate between PR-5A and PR-5B** (REQUIRED)

Before PR-5B begins:

1. Operator runs `cd apps/web && npm run dev` on Haiku
2. Captures screenshots for desktop 1280×800 + mobile 390×844 of:
   - `/learn` (home)
   - `/learn/path/investing-basics` (path)
   - `/learn/path/investing-basics/1` (lesson)
   - `/learn/glossary` (glossary)
   - `/learn/term/drawdown` (term)
   - `/learn/concept/momentum` (concept stub)
3. Reviews against 6 criteria:
   - reading rhythm (calm pacing, generous whitespace)
   - typography (serif/sans balance correct)
   - educational pacing (lesson length feels right)
   - emotional feel (calm mentor, not dashboard)
   - comprehension (a complete beginner can follow Lesson 1)
   - mobile usability (no horizontal scroll, tap targets ≥44px)
4. Issues block PR-5B until resolved
5. Approve gate → proceed to PR-5B

**This gate is the entire reason for the split. The remaining 32
lessons inherit whatever visual/pedagogical decisions land here.**

---

## PR-5B — Curriculum fill

### Scope

**Lessons (32 new)**:
- Reading what you own (7 lessons)
- Paper trading fundamentals (4 lessons)
- Risk literacy (6 lessons)
- Portfolio psychology (5 lessons)
- Reading signals like an analyst (5 lessons)
- When the AI is wrong (5 lessons)

**Glossary expansion (~25 more terms)**:
- Compound interest · Stock · Diversification · Income statement
- P/E ratio · ETF · Index fund · Fee · Bid/ask · Liquidity
- Anchoring · Average cost · Conviction band · Equity · EOD snapshot
- Fill · Factor · Invalidation · Open position · Regime · Replay
- Sell signal · Track record · Universe filter · Watchlist
- (and a few additional as content authoring identifies needs)

**Concept pages full content** (replaces 6 PR-5A stubs + adds 3 new):
- Momentum · Mean-reversion · Valuation · Quality · Defensive · Growth (full)
- NEW: Compound interest · Time horizon · Diversification

### What PR-5B does NOT include

- ❌ Reflection page content (still placeholder; ships in PR-5C)
- ❌ This Week's Concept module (PR-5C)
- ❌ Tier/Path completion screens (PR-5C)

### Effort

| Task | Hours |
|---|---|
| 32 lessons × ~20 min avg                              | 11.0 |
| 25 additional glossary terms                          | 3.0 |
| 6 concept stubs upgraded to full content              | 2.0 |
| 3 new concept pages (compound interest, time horizon, diversification) | 1.5 |
| Cross-link audit (lessons-that-cover-this populated)  | 1.0 |
| Validation + lint                                      | 1.0 |
| **PR-5B total**                                        | **~19.5 hours** |

**~2 focused days** wall-clock.

### PR-5B success criteria

| # | Criterion |
|---|---|
| 1 | All 9 paths populated (full 48-lesson curriculum) |
| 2 | All 40+ glossary terms render with full content |
| 3 | All 9 concept pages render with full content (6 stubs upgraded + 3 new) |
| 4 | "Lessons that cover this" populated on every term page |
| 5 | All 4 constitutional lints PASS |
| 6 | TypeScript clean |
| 7 | No regression in PR-5A surfaces |

---

## PR-5C — Reflection + retention mechanics

### Scope

**Reflection page** (`/learn/reflection`):
- 4 questions with text areas
- Live-data context for Q2 + Q3 (sourced from `/api/paper/executed/trades` + `/api/paper/executed/positions`)
- `reflectionStorage.ts` localStorage adapter
- Previous reflections list (from localStorage history)

**This Week's Concept module**:
- `thisWeeksConcept.ts` deterministic selector
- Learn home card (renders selected concept with reason)
- Briefing integration (only if PR-6 BriefingPage has merged; else dormant slot)
- Reflection page Q4 prefill keyed to current week's concept

**Tier-completion + Path-completion screens**:
- `TierCompletionScreen.tsx` — triggered when user reads all lessons in a Tier (via localStorage progress flags)
- `PathCompletionScreen.tsx` — triggered when user reads all lessons in a path
- Both render observational copy (no celebration), reflection prompt, single primary CTA

### Effort

| Task | Hours |
|---|---|
| Reflection page + localStorage adapter                       | 2.5 |
| This Week's Concept selector + Learn home card               | 1.5 |
| Briefing integration (if PR-6 merged; else slot prep)         | 0.5 |
| Tier-completion + Path-completion screens                    | 1.5 |
| Validation + lint                                              | 0.5 |
| **PR-5C total**                                                | **~6.5 hours** |

**~1 focused day** wall-clock.

### PR-5C success criteria

| # | Criterion |
|---|---|
| 1 | Reflection page saves + reloads from localStorage |
| 2 | Live-data context renders real numbers from existing endpoints |
| 3 | This Week's Concept card resolves deterministically |
| 4 | Tier-completion screen triggers when expected |
| 5 | Path-completion screen triggers when expected |
| 6 | All 4 constitutional lints PASS |
| 7 | TypeScript clean |
| 8 | Reflection prompt rotates through 5 specified topics |

---

## Recalculated dependencies

```
PR-2 primitives.css (.calm-*)
   │
   ▼
PR-5A
   │  ├─ Infrastructure (routes, schema, progress)
   │  ├─ Page templates (Learn home, Path, Lesson, Term, Concept, Glossary)
   │  ├─ 16 lessons (3 foundational paths)
   │  ├─ 16 glossary terms (resolves PR-4 term chips)
   │  └─ 6 concept stubs (resolves PR-4 concept tags)
   │
   ▼  ────────  VALIDATION GATE  ────────
   │
   ▼
PR-5B
   │  ├─ 32 remaining lessons
   │  ├─ 25 additional glossary terms
   │  └─ 9 full concept pages
   │
   ▼
PR-5C
   ├─ Reflection page + localStorage
   ├─ This Week's Concept module
   └─ Tier/Path completion screens

PR-6 BriefingPage  ─── parallel; integrates with PR-5A lessonSelector after merge
```

**Critical**: nothing in PR-5B or PR-5C blocks PR-6. BriefingPage can ship at any time after PR-5A merges.

---

## Smallest Learn release that still feels complete

**PR-5A alone** delivers a functional Learn product:

- Identity visible (hero)
- 3 paths with 16 real lessons (~55 minutes of reading)
- Glossary with 16 terms + search
- All Pick Detail chip routes resolve (0 dead links)
- Continuation hook works (localStorage progress)

What's missing without PR-5B+5C:
- 32 more lessons (deeper paths)
- Full concept page bodies
- Weekly reflection
- This Week's Concept retention mechanic
- Completion screens

**Verdict**: PR-5A IS a shippable product. A new user lands at `/learn`,
sees the identity, picks a path, reads lessons, looks up terms. Trust
narrative holds; product story works.

PR-5B+5C are **depth + retention enhancements**, not blockers.

---

## Total effort across the 3-PR split

| PR | Wall-clock |
|---|---|
| PR-5A | ~2.5 days |
| Validation gate (operator review) | 0.5 day |
| PR-5B | ~2 days |
| PR-5C | ~1 day |
| **Total** | **~6 days** (was ~3 in single-PR plan) |

The split adds wall-clock but **validates before content fill**. If
PR-5A visual review finds layout issues, the 32 PR-5B lessons inherit
the fix once. If single-PR plan ran into the same issue, 48 lessons
would need rework.

**Validation-first is cheaper in expected effort.**

---

## Recommended PR branch sequence

| Branch | PR |
|---|---|
| `pr5a-learn-mvp` | PR-5A |
| `pr5b-curriculum-fill` | PR-5B (branched from `main` after 5A merges + visual review) |
| `pr5c-reflection-retention` | PR-5C (branched from `main` after 5B merges) |

Each PR independently revertable. Validation gate ENFORCED between A and B.

---

## What's NOT in any PR-5 PR

- ❌ Backend endpoints
- ❌ Schema or migrations
- ❌ Accounting / trading / Phase L renderer changes
- ❌ Options lifecycle work
- ❌ New DB state (reflection is localStorage)
- ❌ Streaks / badges / XP / gamification
- ❌ Social / sharing / community
- ❌ Premium / paywall
- ❌ User-generated content
- ❌ Options-related paths

---

## Begin PR-5A

Awaiting explicit approval to start S1 of PR-5A (routes + skeleton).
After PR-5A merges, **STOP for visual review** before authoring PR-5B.

No code in this plan. No further strategy. Build planning final.
