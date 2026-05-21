# PR-5 Implementation Build Plan

**Date**: 2026-05-21
**Status**: BUILD PLAN — no further strategy/review
**Architecture**: finalized
**Curriculum**: finalized (48 lessons across 9 paths · Options hidden)

---

## 1. Exact implementation breakdown

### 1a. Routes (7 new)

| Route | File |
|---|---|
| `/learn`                                       | `apps/web/src/pages/learn/LearnHomePage.tsx` |
| `/learn/path/:slug`                            | `apps/web/src/pages/learn/LearnPathPage.tsx` |
| `/learn/path/:slug/:lesson_n`                  | `apps/web/src/pages/learn/LessonPage.tsx` |
| `/learn/term/:slug`                            | `apps/web/src/pages/learn/TermPage.tsx` |
| `/learn/concept/:slug`                         | `apps/web/src/pages/learn/ConceptPage.tsx` |
| `/learn/glossary`                              | `apps/web/src/pages/learn/GlossaryPage.tsx` |
| `/learn/reflection`                            | `apps/web/src/pages/learn/ReflectionPage.tsx` |

### 1b. Components (route-private, new)

```
apps/web/src/components/learn/
├── LearnHero.tsx                       (identity sentence + degrade-gracefully)
├── WhereYouAreCard.tsx                 (continuation vs "Start here" branch)
├── FeaturedTermCard.tsx
├── ThisWeeksConceptCard.tsx
├── PathList.tsx                        (grouped by tier)
├── PathListItem.tsx                    (one row · ✓ when complete)
├── PathOutcomeBlock.tsx                ("After this path")
├── RelatedConceptsChips.tsx
├── LessonContentRenderer.tsx           (renders structured content)
├── LessonReflectionPrompt.tsx
├── LessonNextCTA.tsx                   (primary + secondary)
├── TermDefinitionBlock.tsx
├── TermRelatedChips.tsx
├── TermLessonsList.tsx
├── ConceptExplanation.tsx
├── ConceptHowAIUses.tsx
├── ConceptRecentSignals.tsx            (pulls from real picks data)
├── ConceptLessonsList.tsx
├── GlossarySearchInput.tsx
├── GlossaryFilterChips.tsx
├── GlossaryAlphabeticalList.tsx
├── GlossaryTermRow.tsx
├── ReflectionQuestion.tsx              (4 instances per page)
├── ReflectionLiveContext.tsx           (computes Q2/Q3 facts from data)
├── ReflectionHistoryList.tsx
├── TierCompletionScreen.tsx
├── PathCompletionScreen.tsx
└── BackToLink.tsx                      (← Back to … helper)
```

### 1c. Logic / data modules (non-rendering)

```
apps/web/src/lib/learn/
├── curriculum.ts                       (path + lesson schema; reads from content)
├── lessonSelector.ts                   (Briefing → lesson selector logic)
├── thisWeeksConcept.ts                 (deterministic concept rotation)
├── progress.ts                         (localStorage adapter: read flags per lesson)
└── reflectionStorage.ts                (localStorage adapter: weekly reflection save)
```

### 1d. Content files (data-only, ~80 files)

```
apps/web/src/content/learn/
├── paths/
│   ├── investing-basics.json
│   ├── how-markets-actually-work.json
│   ├── how-this-ai-thinks.json
│   ├── reading-what-you-own.json
│   ├── paper-trading-fundamentals.json
│   ├── risk-literacy.json
│   ├── portfolio-psychology.json
│   ├── reading-signals-like-an-analyst.json
│   └── when-the-ai-is-wrong.json
│
├── lessons/
│   ├── investing-basics/             (4 lessons)
│   ├── how-markets-actually-work/    (6 lessons)
│   ├── how-this-ai-thinks/           (6 lessons)
│   ├── reading-what-you-own/         (7 lessons)
│   ├── paper-trading-fundamentals/   (4 lessons)
│   ├── risk-literacy/                (6 lessons)
│   ├── portfolio-psychology/         (5 lessons)
│   ├── reading-signals-like-an-analyst/  (5 lessons)
│   └── when-the-ai-is-wrong/         (5 lessons)
│
├── terms/                            (40+ MD/JSON term files)
│
├── concepts/                          (9 concept files: momentum, mean-reversion,
│                                       valuation, quality, defensive, growth,
│                                       compound-interest, time-horizon, diversification)
│
└── reflectionPrompts.json            (5 rotating questions)
```

Lesson data shape:

```typescript
interface Lesson {
  slug: string;
  pathSlug: string;
  order: number;
  title: string;
  minutes: number;
  openingLine: string;
  body: Array<
    | { type: "paragraph"; text: string }
    | { type: "subhead"; text: string }
    | { type: "liveData"; query: string }    // selector for real ArthOS data
  >;
  reflectionPrompt: string;
  conceptTags: string[];                      // for cross-linking
  termsReferenced: string[];                  // for glossary "lessons that cover this"
}
```

### 1e. Shared primitives needed (extensions to existing primitives.css)

Already shipped in PR-2: `.calm-card`, `.calm-card-stack`, `.calm-btn`, `.calm-chip`, `.calm-badge`.

**NEW in PR-5**:
- `.calm-input` (single-line + textarea variants for search + reflection)
- `.calm-divider` (1px sand-300 horizontal rule between learn sections)
- `.calm-letter-divider` (glossary alphabetical section labels)
- `.calm-checkmark` (✓ for completed lessons; not a badge)

All scoped to `.today-root`. Token-driven.

### 1f. Cross-link wiring (existing → new)

| Existing surface | Modification | New target |
|---|---|---|
| BriefingPage (PR-6 in progress) | adds `<TodaysLessonCard/>` calling `lessonSelector` | `/learn/path/:slug/:n` |
| PickDetailPage (PR-4) — concept tag | already points to `/learn/concept/:slug` — no change | URL now resolves |
| PickDetailPage (PR-4) — learn chips | already points to `/learn/term/:slug` — no change | URL now resolves |
| TodayPage (PR-1) | Featured term in Learning card section now wired to real glossary | `/learn/term/:slug` |
| App.tsx | mount 7 new routes | — |
| TodayNav.tsx | unchanged — Learn link already in nav | — |

---

## 2. Build order (8 slices)

| Slice | Scope | Deliverable verifiable by |
|---|---|---|
| **S1** | Routes + skeleton pages (no content) | navigating to all 7 routes renders empty calm shell without errors |
| **S2** | Content schema + 4 Investing basics lessons | `/learn/path/investing-basics/1` renders real lesson content |
| **S3** | 6 Markets path lessons + path landing for both paths shipped | both first two paths fully populated |
| **S4** | 17 Tier-1 lessons (How AI thinks + Reading what you own + Paper trading) | all foundational paths complete |
| **S5** | 11 Tier-2 lessons (Risk + Psychology) | midway-curriculum complete |
| **S6** | 10 Tier-3 lessons | full 48-lesson curriculum complete |
| **S7** | Glossary (40+ terms) + 9 concept pages + glossary index | glossary searchable; concept routes resolve |
| **S8** | Reflection page + localStorage + This Week's Concept module + Tier/Path completion screens | full PR-5 surface |

Each slice independently revertable. CI lint runs at every slice.

---

## 3. Dependency graph

```
PR-2 primitives.css (.calm-*)
   │
   ▼
S1 routes + skeleton (LearnHomePage, paths, lessons, term, concept, glossary, reflection)
   │
   ├── S2 lesson content schema + Investing basics 4 lessons
   │       │
   │       └── S3 Markets path 6 lessons
   │              │
   │              ├── S4 Tier-1 17 lessons ──┐
   │              │                          │
   │              ├── S5 Tier-2 11 lessons ──┤
   │              │                          │
   │              └── S6 Tier-3 10 lessons ──┤
   │                                          │
   │                                          ▼
   ├── S7 glossary 40+ terms + 9 concept pages
   │       │
   │       └── concept tag routes from PR-4 resolve
   │
   └── S8 reflection page + This Week's Concept module + completion screens

PR-6 BriefingPage (in parallel)
   │
   ▼
   integrates lessonSelector + ThisWeeksConcept (after S2 + S8 land)
```

**Critical dependency**: lesson content schema (S2) blocks every subsequent content slice. Author it first; rest fills the template.

---

## 4. Effort by task

| Task | Hours |
|---|---|
| S1 — Routes + skeleton                                 | 1.5 |
| S2 — Lesson schema + Investing basics (4 lessons)      | 1.5 |
| S3 — Markets path (6 lessons)                          | 2.0 |
| S4 — Tier-1 paths (17 lessons)                         | 4.5 |
| S5 — Tier-2 paths (11 lessons)                         | 3.0 |
| S6 — Tier-3 paths (10 lessons)                         | 2.5 |
| S7 — Glossary (40+ terms) + 9 concept pages + index    | 4.0 |
| S8 — Reflection + This Week's Concept + completion screens | 2.5 |
| Cross-link wiring + Briefing integration               | 1.0 |
| Validation + lint cleanup                              | 1.0 |
| **Total**                                              | **~23.5 hours** |

Roughly **2.5–3 focused days** wall-clock.

---

## 5. Lowest-risk incremental slices

Each slice can ship to a branch and be merged independently. Order matches §2.

| Slice | Risk | Mitigation |
|---|---|---|
| S1 routes/skeleton             | very low — no content, no logic | TypeScript will catch missing imports |
| S2 schema + 4 lessons          | low — schema decisions reverberate; commit early to lock | review schema before authoring more content |
| S3-S6 content fills            | low — content-only; no logic change | run forbidden-phrase lint per slice |
| S7 glossary + concepts         | low | concept routes must match PR-4 chip targets exactly |
| S8 reflection + module         | medium — localStorage shape is forward-compatible | keep schema simple JSON object |

**Risk-reduction discipline**:
- Run `python infra/ci/constitutional_checklist/forbidden_phrases.py` after every content slice
- Each slice merges only after CI green
- Lesson content authored as data files, not React components — easier to lint + refactor
- Lessons reference `liveData` queries by selector string, not inline SQL — keeps content separate from data access

---

## 6. Validation checklist

Run at end of every slice + at PR-5 final:

### Constitutional gates
- [ ] `forbidden_phrases.py` exit 0 (30 phrases × all new content)
- [ ] `resolver_anchor_lint.py` exit 0
- [ ] `canary_gateway_lint.py` exit 0
- [ ] `test_reasoning_envelope_snapshots.py` 9/9 PASS

### Build gates
- [ ] `cd apps/web && npm run typecheck` clean
- [ ] No new ESLint warnings

### Functional gates
- [ ] All 7 Learn routes render without console error
- [ ] `/learn/path/:slug` for each of the 9 paths renders
- [ ] `/learn/path/:slug/:n` for each of the 48 lessons renders
- [ ] `/learn/term/:slug` for each of the 40+ terms renders
- [ ] `/learn/concept/:slug` for each of the 9 concepts renders
- [ ] **Zero PR-4 Pick Detail chip targets 404** (16 routes verified)
- [ ] Glossary search filters correctly
- [ ] Glossary filter chips switch view correctly
- [ ] Lesson "Next lesson" CTA resolves to correct sibling
- [ ] Lesson "Back to today's brief" CTA resolves to `/briefing` (or current home until PR-6 ships)
- [ ] Reflection saves to localStorage; reloads on revisit
- [ ] Reflection live-context block renders real numbers from existing endpoints
- [ ] This Week's Concept card resolves to real concept page
- [ ] Tier-completion + Path-completion screens render at correct trigger

### Truth gates
- [ ] API payloads byte-identical (`/api/paper/summary.equity` unchanged)
- [ ] Row counts unchanged (paper_trade · paper_position · paper_equity_snapshot · options_paper_position · options_trade_lifecycle_event · options_canary_lifecycle_run)
- [ ] No new backend files modified
- [ ] No schema / migration changes

### Visual gates
- [ ] Desktop 1280×800: reading column 720px, calm spacing held
- [ ] Mobile 390×844: bottom-tab nav present, reading column scales
- [ ] No glow / lift / uppercase / streak / badge anywhere
- [ ] Serif used only for hero / page titles / opening lines / featured terms
- [ ] All lesson content under 400 words

---

## 7. Recommended PR sequence

**Single PR**, 8 slices merged sequentially to one branch, opened as one PR for review.

| Branch | Commits | Scope |
|---|---|---|
| `pr5-learn` | commit per slice (S1-S8) + lint fixes | full Learn surface |

**Why one PR**:
- Atomic rollback (`git revert <merge>` undoes everything cleanly)
- Single visual review pass on staging
- No half-shipped state where PR-4 Learn chips 404 but reflection exists
- Content load is the bulk; logic is thin

**Within the PR**, slices are commit boundaries:
- Reviewer can examine slice-by-slice
- Each commit ships cleanly even if subsequent commits drop
- Operator can stop after S6 if content quality is in question, ship S1-S6 only

**Alternative split** (only if review bandwidth requires):
- `pr5a-learn-shell-and-basics` — S1 + S2 + S7 partial (terms) + S8 partial (reflection routing). Ships routes + first 4 lessons + reflection skeleton. Stocks-side never touched.
- `pr5b-learn-content-fill` — S3 + S4 + S5 + S6 + S7 complete + S8 complete. Pure content + module fill.

Default: **single PR** unless reviewer requests split.

---

## What this PR does NOT do

- ❌ No backend endpoints
- ❌ No schema or migrations
- ❌ No accounting / trading / Phase L renderer / options lifecycle changes
- ❌ No new state in DB (reflection is localStorage)
- ❌ No `BriefingPage` rewrite (PR-6 handles Briefing) — only adds a `<TodaysLessonCard/>` slot if PR-6 already merged; otherwise the slot is wired in PR-6
- ❌ No streaks / badges / XP / gamification
- ❌ No social / sharing
- ❌ No premium content / paywall
- ❌ No user-generated content
- ❌ No options-related paths

---

## Rollback command (if PR-5 lands and something visual breaks)

```bash
git revert <pr5-merge-sha>
# routes disappear, PR-4 Pick Detail chips 404 again
# (back to the pre-PR-5 state cleanly)
```

Zero residue. No schema to roll back. No backend changes to undo.

---

## Definition of done

PR-5 is done when:
1. All 7 Learn routes resolve and render
2. All 48 lessons authored (content) AND lint-clean
3. All 40+ glossary terms authored AND lint-clean
4. All 9 concept pages authored AND lint-clean
5. Reflection page saves + reloads from localStorage
6. This Week's Concept card on Learn home renders deterministically
7. Tier-completion + Path-completion screens trigger correctly
8. All 16 PR-4 Pick Detail chip targets resolve (zero 404)
9. All 4 constitutional lints PASS
10. TypeScript build clean
11. Operator visual review on Haiku: `/learn` + `/learn/path/markets-actually-work` + `/learn/path/markets-actually-work/3` + `/learn/term/drawdown` + `/learn/concept/momentum` + `/learn/glossary` + `/learn/reflection` all visually correct on desktop 1280×800 + mobile 390×844

Begin S1.
