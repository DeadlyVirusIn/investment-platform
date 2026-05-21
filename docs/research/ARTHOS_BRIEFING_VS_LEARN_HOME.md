# ArthOS — Briefing vs Learn as Home

**Date**: 2026-05-21
**Status**: STRATEGIC DECISION REVIEW — no implementation
**Identity (fixed)**: "Learn how to invest by watching an AI invest, explain itself, and admit mistakes."

---

## Comparison — Home = Learn vs Home = Briefing

| Dimension | Home = Learn | Home = Briefing |
|---|---|---|
| **Retention** | Weekly studious cadence; users skip days when no new lesson appeals; lower daily-active | **Daily ritual** — fresh artifact every weekday; every visit has novelty; pattern matches Morning Brew · NYT The Daily · Calm · Strava recap. **High daily-active** |
| **Onboarding** | First impression = "school"; can feel duty-bound on day 1 | First impression = "today's story is waiting for me"; lower cognitive entry cost; calm hook |
| **Daily habit formation** | Lesson-driven habit forms slowly; needs streak counter (gamification we want to avoid) to enforce daily | **Daily habit forms naturally** because the artifact changes daily without external pressure; same psychology as a morning newspaper |
| **Beginner comprehension** | A lesson can feel overwhelming on a busy morning; user may bounce when title doesn't match mood | Narrative briefing is easier to scan; user can skim or read deeply; **lower friction** |
| **Educational outcomes** | Direct path-completion; structured, measurable | Indirect but compounding — each briefing ends with one lesson woven into context; concepts are encountered in the wild before being studied formally |
| **Long-term engagement** | High once committed; lower entry conversion; "I'll read it later" risk | **Higher long-term retention** because daily ritual sustains itself; lessons follow the curiosity the briefing creates |
| **Risk** | Identity-aligned but psychology-misaligned (feels like school) | Identity-aligned AND psychology-aligned (feels like a thoughtful daily artifact) |
| **Industry pattern** | Duolingo (works only with hardcore gamification — streaks, hearts) | NYT The Daily · Morning Brew · Substack · Calm Daily — proven daily-artifact retention |

---

## 1. Recommendation

**Home = Briefing.**

Reasoning:
- The user explicitly stated ArthOS must function as a **daily ritual**. Daily-artifact products (briefings, papers, podcasts) sustain higher daily-active retention than lesson-platform products without gamification.
- The identity ("learn by watching") naturally fits: **you watch first, then learn**. The briefing is the watching. The lesson is the closing reflection.
- Lesson-platform products that work daily (Duolingo, Brilliant) rely on streaks/hearts/gems — **gamification we explicitly excluded** from ArthOS tone. Removing those crutches makes Learn-as-home psychologically weaker.
- Briefing-as-home + Learn-as-slot-2 lets the user encounter concepts in context (briefing) and study them depth-first (learn) — two-channel literacy is stronger than either alone.

The identity sentence still holds. Briefing is HOW the user watches the AI invest each day. Learn is WHERE the concepts get internalized.

---

## 2. Briefing homepage wireframe

Route: `/` (after login) → renders `/briefing`. Mobile + desktop share the same single-column reading layout.

```
┌─────────────────────────────────────────────────────────────┐
│  ArthOS · Briefing            Tuesday, May 21               │
│  (nav row, single line, calm)                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Today, in a sentence.                                      │
│                                                             │
│  The AI added NVDA and is watching one position             │ ← serif 24px
│  closely.                                                   │   ink primary
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  The story                                                  │ ← section label
│                                                             │
│  Yesterday afternoon the engine's momentum filter           │
│  flagged NVDA after fourteen consecutive sessions          │ ← serif 17px
│  above the 200-day average. Volume in the last week         │   ink primary
│  came in 38% above the prior month's baseline. The         │   line-height 1.6
│  AI opened the position at the regular open.                │   max 4 paragraphs
│                                                             │
│  Separately, AMAT — held since early April — has            │
│  reached the upper end of its range. The AI is              │
│  watching but hasn't trimmed yet. The signal will           │
│  fire again if the price closes above $445.                 │
│                                                             │
│  Nothing was sold today.                                    │ ← single short line
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  Today's lesson                                             │
│                                                             │
│  What does "trim" actually mean?                            │ ← serif 18px
│  Trim is a partial reduction of an open position.           │ ← Inter 15px
│  It appears when momentum weakens but the thesis            │   muted body
│  is still intact.                                           │
│                                                             │
│  [Continue today's reading →]                               │ ← single CTA
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  The AI is watching                                         │
│                                                             │
│  NVDA  ·  Buy signal                                        │ ← Pick teaser card
│  Today's full thinking on why this signal exists.           │   calm-card style
│  [See full thinking →]                                       │   one CTA
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  While you were away                                        │
│                                                             │
│  •  AMAT closed at +4.2% last Friday.            5d ago     │ ← max 3 observational
│  •  Top concentration: NVDA at 4.8% of portfolio. today    │   rows; no dot wash
│  •  Options remain dormant — equities only.       —        │
│                                                             │
│  ─────────────────────────────────────                      │
│                                                             │
│  Tomorrow's brief lands at 7am ET.                          │ ← anticipation hook
│                                                             │
│  Learn  ·  Journal  ·  Portfolio  ·  Track Record           │ ← quiet browse footer
│  › Operator                                                 │ ← collapsed expander
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**One artifact. One story. One lesson. One next action. One anticipation hook.**

---

## 3. Information hierarchy

| Slot | Section | Purpose | Required? |
|---|---|---|---|
| 1 | Date + brand                       | Orientation                                | always |
| 2 | Today, in a sentence              | TL;DR for the scanner                     | always |
| 3 | The story                          | The actual briefing artifact (2-4 paragraphs) | always |
| 4 | Today's lesson                    | Educational close + one CTA to Learn      | always |
| 5 | The AI is watching                | Single Pick teaser card (linked to Pick Detail) | conditional — only when there's a fresh signal worth highlighting |
| 6 | While you were away               | 2-3 observational rows since last visit  | always |
| 7 | Tomorrow's brief lands at 7am ET  | Anticipation hook                          | always |
| 8 | Browse footer + Advanced expander | Secondary navigation                       | always |

**Order discipline**:
- TL;DR sentence is ALWAYS the first thing after date — scanner gets value immediately
- The story is the longest block — pacing for deep readers
- Today's lesson follows the story so the lesson lands while context is fresh
- "The AI is watching" comes AFTER the lesson so the lesson primes the reader to engage deeper
- "While you were away" is utility data, demoted near the bottom
- Tomorrow promise is the closing line — small but emotionally important

**Forbidden on Briefing home**:
- NAV number
- Live MTM ticker
- Holdings table
- Performance metrics
- Daily P&L number
- Sparkline charts
- Action chips (Buy/Sell/Trim)
- Confidence percentages
- Any UPPERCASE labels

---

## 4. Mobile layout (390×844)

Same vertical sequence. Reading column = viewport width minus 24px gutters. Type scales:

| Element | Desktop | Mobile |
|---|---|---|
| Date eyebrow                      | 13px ink-muted | 12px |
| TL;DR sentence                    | 24px serif     | 20px serif |
| The story                          | 17px serif     | 16px serif (line-height 1.65) |
| Today's lesson title              | 18px serif     | 17px serif |
| Today's lesson body               | 15px Inter      | 15px Inter |
| Pick teaser card                  | 16px           | 16px        |
| While you were away rows         | 14px Inter      | 14px Inter |
| Anticipation hook                 | 13px ink-muted | 13px        |

**Mobile-specific behavior**:
- Bottom tab bar replaces top nav: `[Briefing] [Learn] [Journal] [Track Record] [≡ More]`
- Bottom tab is sticky, safe-area-aware, 64px tall
- "Tomorrow's brief lands at 7am ET" sits above the tab bar with 24px breath
- Single-column always; no card-grid attempt at md breakpoint
- Pick teaser card is full-width minus gutters

**Mobile first-fold contract** (≤480px height visible without scroll):
- Date eyebrow
- TL;DR sentence (20px serif, 2-3 lines)
- Beginning of "The story" — at least 2 lines visible above fold

This is the user's first 4-second impression. Calm, single artifact, no chrome.

---

## 5. Desktop layout (1280×800)

- Reading column max-width 720px, centered
- Side gutters 80px+
- Single column throughout — never two-column even on wide viewports
- Top nav is the existing TodayNav style (single calm row, 48px tall, brand left, links right)
- No sidebar on desktop; no persistent sidebar chrome
- Fixed footer reading: "Tomorrow's brief lands at 7am ET" with browse links below

**Desktop first-fold contract** (≤800px visible without scroll):
- Top nav (48px)
- Date (16px)
- TL;DR sentence (24px serif, 3 lines max)
- First 2 paragraphs of "The story" visible

User can complete the briefing without scrolling if it's short, or scroll into the lesson + pick teaser sections.

---

## 6. How Learn integrates

Briefing and Learn are **two-channel literacy**: encounter then internalize.

### Cross-link contract

| From | To | Trigger |
|---|---|---|
| Briefing "Today's lesson" CTA | `/learn/term/:slug` OR `/learn/path/:slug` | Single click — opens the lesson |
| Lesson page footer | "Back to today's brief →" | One-click return to /briefing |
| Briefing "The AI is watching" Pick teaser | `/today/pick/:symbol` (PR-4 surface) | already wired |
| Pick Detail "Learn more" chips | `/learn/term/:slug` | already wired |
| Learn home page top section | "Read today's briefing →" | reciprocal link |

### Daily flow (cross-surface)

```
Day 1 morning  → /briefing → today's lesson chip → /learn/term/trim
              → read 3 min   → "Back to today's brief"
              → /briefing → "The AI is watching" → /today/pick/NVDA
              → close. User encountered "trim" in context, studied it briefly, saw a fresh signal.

Day 2 morning  → /briefing → different story; different lesson chip
              → user starts a path (multi-day commitment) instead of single term
              → path lessons reference yesterday's AMAT close
              → literacy compounds, briefing fuels it
```

### Why this works

The briefing creates curiosity. The lesson satisfies it. Without the briefing, lessons feel academic. Without the lesson, the briefing feels passive. **They need each other and only work in the briefing→lesson direction.**

---

## 7. Revised navigation

### Primary (5 slots)

```
1. Briefing      ← HOME (was Learn in prior plan)
2. Learn         (path index, glossary, lesson library)
3. Journal       (chronological AI decisions)
4. Portfolio     (state check)
5. Track Record  (lifetime + honest losses)
```

### Mobile (bottom-tab, 4 visible + More drawer)

```
[Briefing] [Learn] [Journal] [Track Record]    [≡ More]
```

Portfolio moves to More drawer on mobile. Reasoning: a beginner's daily check is briefing + lesson; portfolio state is a less-frequent need on mobile. Track Record stays primary on mobile to keep the honest-history surface accessible.

### Floating

`Ask` (Copilot) — feature button, deferred until backend ready.

### Secondary (hidden)

`Operator` — collapsed expander on desktop, More drawer item on mobile.
`Settings` — More drawer item.

---

## Routes after login summary

| Route | Page |
|---|---|
| `/`                          | redirects to `/briefing` |
| `/briefing`                  | the daily artifact home (new — replaces /today as default landing) |
| `/learn`                     | path index + glossary + featured lesson (slot 2 nav) |
| `/learn/path/:slug`          | a multi-lesson path |
| `/learn/term/:slug`          | single glossary term |
| `/learn/concept/:slug`       | broader concept page (momentum, mean reversion, etc.) |
| `/journal`                   | chronological AI decisions |
| `/portfolio`                 | state check (reuses TodayPortfolioPage from PR-2) |
| `/track-record`              | lifetime + honest losses |
| `/today/pick/:symbol`        | Pick Detail (PR-4, unchanged) — reachable from briefing's "AI is watching" + journal entries |
| `/operator/*`                | engineering surfaces, off primary nav |
| `/settings`                  | utility |

**Legacy routes** (`/today`, `/today/portfolio`, `/overview`) remain intact for backward compatibility during the transition but redirect to the new equivalents (`/briefing`, `/portfolio`, `/briefing`) once the new nav ships.

---

## What this means for shipped PRs

| Shipped | New role |
|---|---|
| PR-1 TodayPage (calm shell + tokens + TodayNav) | The shell pattern + tokens stay; the page becomes the foundation for `/briefing`. WhatChangedCard becomes the "While you were away" section. RecentMovesStrip + AITrackRecord move to `/track-record`. |
| PR-2 TodayPortfolioPage + primitives + variants | TodayPortfolioPage becomes `/portfolio` (functional, demoted in nav). Primitives stay. PickModal calm variant stays. |
| PR-3 What-changed + recent moves + track record | WhatChangedCard powers "While you were away" on Briefing. RecentMovesStrip + AITrackRecord move to `/track-record` page. |
| PR-4 PickDetailPage | Stays at `/today/pick/:symbol` URL (or could rename to `/pick/:symbol` later — separate decision). Reachable from Briefing's "AI is watching" + Journal entries. |

**No code wasted.** Components stay; slot semantics shift.

---

## Open question for separate decision

Should Briefing have a **scheduled-publish artifact** (one new briefing per weekday at 7am ET, frozen until next day) — like a true newspaper — or should it **recompute every visit** with whatever data is current?

Tradeoffs:
- **Frozen artifact**: stronger ritual; same content all day; missable. Requires a "today's briefing" job in the worker that materializes the briefing.
- **Live recompute**: always reflects latest activity; less ritual; risk of "feels like a dashboard that updates."

This is a separate research question. Not blocking PR approval.

---

## Stopping

No code. No diffs. No components.

Awaiting explicit approval on:

1. **Home = Briefing** (not Learn)
2. **Briefing homepage hierarchy** (§3)
3. **Mobile + desktop layouts** (§4, §5)
4. **Briefing↔Learn cross-link contract** (§6)
5. **Revised 5-item nav with Briefing in slot 1** (§7)
6. **`/` redirects to `/briefing` after login**
7. **Shipped PRs retain component code; only route/slot semantics shift**
