# ArthOS — Phase 2 Product Evolution

Direction reset. Visual design is sufficient. Product behavior is the
remaining problem. This document covers the five Phase-2 tasks and
consolidates them into one roadmap.

References to current state:
- Screenshots: `docs/research/Screenshots/arth-mvp-v2-2026-05-24/*`
- Architecture spec: in conversation transcript (chapter loop +
  recommendation chain +  memory layer + adaptive recommendations)
- Current MVP: PR #14 (See → Decide → Practice → Reflect → Remember
  loop wired on Today + Journal only)

---

## 0. Executive findings

### What the MVP confirmed
1. The voice + glyph + first-person framing works. Today and Journal
   read as a copilot.
2. The decision row + skip-with-reason + reflection-on-follow loop
   captures intent and produces memory. Users get a real exchange.
3. The Journal-as-conversation-log surface earns its keep — it is the
   visible relationship.

### What the MVP exposed
1. **Arth speaks like a copilot but does not yet think like one.**
   Recommendation is a hand-picked default, not a function of user
   memory + market state.
2. **No track record visible.** Arth makes calls; the user has no proof
   any of them ever worked.
3. **No contextual learning.** Skips lead nowhere. Trade closes don't
   teach. Lessons live in a separate library.
4. **Me page is still a metrics table.** No relationship surface.
5. **Opportunities is still an analyst worksheet.** No decision-desk
   structure.

### Phase 2 thesis
The remaining gap is **product behavior**, not appearance. Five focused
workstreams close it:

| Task | Theme | What changes |
|---|---|---|
| 1 | Decision Desk | Opportunities becomes "what should I do today?" |
| 2 | Mentor Profile | Me becomes a relationship document |
| 3 | Contextual Learning | Lessons emerge from behavior, not browsing |
| 4 | Trust Engine + Arth Report Card | Arth proves itself with outcomes; new `/v2/arth` first-class surface |
| 5 | Intelligence Audit | Honest map of where Arth is dumb vs. smart |

### Three direction-reset mandates (applied throughout)

1. **Trust + Decision Quality come before the relationship layer.**
   Sequence is 2A → 2B (Trust + Report Card) → 2C (Decision Desk) →
   2D (Contextual Learning) → 2E (Mentor Profile) → 2F (Trust v2).
   Mentor Profile is deliberately late: patterns only earn user trust
   after Arth has already proven himself with outcomes.

2. **Every recommendation must explicitly answer 5 questions:**
   Why this idea? · Why not the alternatives? · Why now? ·
   What would invalidate it? · How similar ideas performed historically.
   No card ships without all five.

3. **Learning is embedded in decisions/outcomes/skips/wins/losses/
   mind-changes.** The Learn page becomes primarily an archive of
   concepts encountered elsewhere — not a discovery destination.
   A user who never opens `/v2/learn` still builds a real competence
   map through inline encounters.

---

# TASK 1 — Opportunities as Decision Desk

## 1.1 Current state (screenshot reference)

`arth-mvp-v2-2026-05-24/07-opportunities-desktop.png`

- 6 stacked sections: What's on the desk, Strongest setups today,
  Setups still forming, Names we're tracking, Risk flags, What we
  passed on.
- Stocks | Options two-column grid in every section.
- Hairline-divided list rows for tracking + passed-on.
- No Arth voice. No personalization. No ranking. No decision row.

Reads as a research dashboard. The user does not know which idea
to look at first.

## 1.2 Target state — Decision Desk

The primary question the page answers becomes:
**"What should I do today?"**

Single Arth-voiced opening. Single ranked hero. Single decision row
per card. Honest closing.

## 1.3 UX specification

### Page-level structure (top → bottom)

```
[rail above]
[topbar with Today's date + Day N]

[Arth opening line — 1-2 sentences]
[Arth's pick marker — "If I could only do one today, this is it"]

┌─────────────────────────────────────────────────────────┐
│ THE ONE                                                 │
│ [hero card — full decision-desk treatment]              │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ ALSO CONSIDER (N)                                       │
│ [ranked secondary cards — collapsed to summary form]    │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ WHAT I'M WATCHING (N)                                   │
│ [compact rows — name + waiting-on condition]            │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ WHAT I PASSED ON TODAY (N collapsed by default ▾)       │
│ [each rejection + Arth's reason + linked lesson]        │
└─────────────────────────────────────────────────────────┘

[trust footer: Arth's last 30-day track record]
```

### The Hero card (THE ONE) — required fields

Every hero card must answer seven questions structurally:

```
┌─────────────────────────────────────────────────────────┐
│ AAPL · Buy AAPL 175/180 call spread                     │
│ ★ Arth's pick                                           │
│ [low risk]  [medium confidence]  [hold ~6-12d]          │
│                                                          │
│ THESIS                                                  │
│ {actionLabel + paragraph from Recommendation}           │
│                                                          │
│ ─────────────────────────────────────────────────────── │
│ WHY THIS IDEA      WHY NOT THE         WHY NOW          │
│                    ALTERNATIVES?                        │
│                                                          │
│ - Defined-risk     - TSLA: credit     - IV in bottom    │
│   structure          too small           quartile       │
│ - Liquid spread    - SPY: 60% time    - Bullish gamma   │
│ - Tight bid/ask      decay already      flip yesterday  │
│                                       - Earnings 4w out │
│                                                          │
│ ─────────────────────────────────────────────────────── │
│ WHAT COULD INVALIDATE IT                                │
│ - AAPL daily close below $168                           │
│ - IV expansion above 30%                                │
│ - Broad SPY breakdown below 50-DMA                      │
│                                                          │
│ ─────────────────────────────────────────────────────── │
│ HOW SIMILAR IDEAS HAVE PERFORMED                        │
│ My last 7 long-call spreads at IV<25%ile:               │
│   4 wins (avg +1.6%) · 2 losses (avg -2.3%)             │
│   · 1 expired flat                                      │
│ Avg hold: 7 days. [See those calls →]                   │
│                                                          │
│ ─────────────────────────────────────────────────────── │
│ Expected hold: 6-12 days                                │
│ Confidence: medium (normal size — not a larger one)     │
│                                                          │
│ [Paper trade]  [Save]  [Skip — tell me why]             │
│                                                          │
│ ─────────────────────────────────────────────────────── │
│ Why I picked this for you: {WhyForYou.line}             │
│ Show me how I got here →   ·   Primer: IV Crush · 3 min │
└─────────────────────────────────────────────────────────┘
```

Required information density (the five non-negotiable answers,
per user mandate — every recommendation must explicitly answer):

| # | Question | Field | Required? |
|---|---|---|---|
| 1 | **Why this idea?** | why_this_idea (3 bullets) | yes |
| 2 | **Why not the alternatives?** | why_not_others (per other rec) | yes |
| 3 | **Why now?** | why_now (3 bullets — timing signals) | yes |
| 4 | **What would invalidate it?** | invalidate_conditions[] | yes |
| 5 | **How similar ideas performed historically?** | historical_performance | yes |

Plus the additional decision-support fields:

| # | Question | Field | Required? |
|---|---|---|---|
| 6 | What is it? | symbol + structure + thesis | yes |
| 7 | Expected holding period? | hold_estimate_days_min/max | yes |
| 8 | How confident is Arth? | confidence_level (words, not numbers) | yes |
| 9 | What does Arth want me to pick first? | is_arth_pick | yes |

Plus the two existing copilot affordances:
- WhyForYou personalization line
- Decision row (paper trade / save / skip-with-reason)

The **historical performance** row is sourced from the same data the
Trust Engine + Arth Report Card use (Phase 2B). Each rec carries a
`historical_cohort_key` — a coarse classification of the setup
(e.g. `"long_call_spread_low_iv"`, `"short_credit_spread_high_iv"`,
`"directional_long_breakout"`) — and the resolver runs `historicalCohort(key)`
against the closed-decision archive at render time.

Empty-cohort case (early days, N < 5 closed calls of this type):
```
HOW SIMILAR IDEAS HAVE PERFORMED
I've only made 2 calls like this so far. Too early to claim a
pattern. [See those calls →]
```

### Secondary cards (ALSO CONSIDER)

```
┌─────────────────────────────────────────────────────────┐
│ TSLA — Short at $172                                    │
│ Short · high risk · low confidence · hold ~3-5d         │
│                                                          │
│ Why I have it lower: the catalyst is fuzzy. Wait for    │
│ Thursday's inventory print before sizing up.            │
│                                                          │
│ [Read more →]  [Save]                                   │
└─────────────────────────────────────────────────────────┘
```

Compact — one-line "why I have it lower" framing, less depth on the
seven questions. Expanded view opens the full decision desk.

### Watching list

```
WHAT I'M WATCHING (8)

▸ NVDA   Waiting for IV crush below 25
▸ AMD    Waiting for breakout above $180
▸ XLE    Waiting for the EIA print Thursday
▸ MSFT   Waiting for earnings to clear
... 4 more — [See all 8]
```

No decision row. Each row carries the specific condition Arth is
waiting on. Tap → expanded view showing thesis-in-waiting.

### Passed-on (collapsed by default)

```
WHAT I PASSED ON TODAY (4)  ▾

TSLA $175 calls — IV too rich today
   I'd consider this if IV drops below 28. Primer →

META — earnings in 3 days, IV crush risk
   You've skipped earnings setups 5 of 6 times. I assumed
   the same here. Tell me if I'm wrong.  Primer →

... 2 more
```

The honesty pass. Each rejection links a lesson + acknowledges
patterns observed about the user.

### Empty-day variant

If nothing passes the filter today:

```
[Arth] Nothing clean today. I'd rather show you nothing than
make something up. Read a lesson instead, or come back tomorrow.

[Suggested lesson based on what you've been working on]
[Tomorrow's watch list — what I expect to surface next]
```

## 1.4 Data requirements

### New fields on `Recommendation`

```
hold_estimate_days_min: number
hold_estimate_days_max: number
confidence_level: 'low' | 'medium' | 'high'
why_this_idea: string[]            // up to 3 bullets — qualities of the idea
why_now: string[]                  // up to 3 bullets — timing signals
why_not_others: { rec_id, reason }[]   // per alternative
invalidate_conditions: string[]    // 1-3 bullets
historical_cohort_key: string      // classifier for cohort lookup
is_arth_pick: boolean              // ★ marker
```

### New page-level state

```
arth_opening_line: string          // generated from rec + memory
ranked_recommendations: Recommendation[]   // sorted by confidence+pick
watching_list: WatchingItem[]      // existing TRACKING data, restyled
passed_on_today: PassedOnItem[]    // existing, demoted
```

### New computed: ranking algorithm

```
rank(rec) = primary: is_arth_pick desc
            then: confidence_level desc (high > med > low)
            then: hold_estimate_days_min asc
            then: composite_score desc
```

Exactly one rec gets `is_arth_pick = true` per day. Hand-coded for
MVP, derived from confidence + alignment with user patterns later.

## 1.5 Implementation plan

| Step | Item | Effort |
|---|---|---|
| 1.5.1 | Extend `Recommendation` interface with 9 new fields | 0.5d |
| 1.5.2 | Seed all 5 entries in `TODAYS_DESK` with the new fields | 0.5d |
| 1.5.3 | Build `DecisionDeskHero` component (the 7-question card) | 1d |
| 1.5.4 | Build `AlternativeRow` (collapsed secondary) | 0.5d |
| 1.5.5 | Build `WatchingRow` + `PassedOnExpander` | 0.5d |
| 1.5.6 | Replace `Opportunities.tsx` body with the new layout | 1d |
| 1.5.7 | Generate Arth opening line via templated rules over ranked set | 0.5d |
| 1.5.8 | Empty-day variant + tests | 0.5d |
| 1.5.9 | Capture screenshots | 0.5d |

**Total: ~5.5 days**

No backend changes. All data from existing `arthosData.ts` extended.

---

# TASK 2 — Me as Mentor Profile

## 2.1 Current state (screenshot reference)

`arth-mvp-v2-2026-05-24/09-me-desktop.png`

- "Day 1" + brand-pill eyebrow (from existing MePage)
- 4-row metric table (Lessons read, Reflections written, Decisions
  followed, Paper trades)
- 3-bar progress chart (Foundations, Risk literacy, Options literacy)
- "What you wrote" — last reflection visible
- "Your paper trades" — unrealized + realized
- "Where to go next" — 3 chips

Reads as an analytics dashboard with a relationship paragraph spliced
in. The relationship paragraph is the strongest part — it should be
the whole page.

## 2.2 Target state — Mentor Profile

The Me page becomes a **relationship document**. Metrics are demoted
to a quiet footer.

Structure (top → bottom):

```
1. Streak hero (Day N + longest + 30-day dot grid)
2. What Arth knows about you (declared / seen / patterns)
3. Strengths I've noticed
4. Patterns I'm watching (uncertain inferences, editable)
5. Lessons you've earned (competence map preview)
6. Mistakes I've seen you repeat
7. Last 3 things you taught me (reflection quotes)
8. What I'd recommend next (computed next ritual)
9. Track Record (demoted metrics)
```

## 2.3 UX specification

```
┌─────────────────────────────────────────────────────────┐
│ [avatar]   YOUR ARTHOS                                   │
│                                                          │
│ Day 12 of practice                                      │
│ Longest streak: 12  ·  ●●●●●●●●●●●●○○○○○ (last 17 days) │
│                                                          │
│ Started May 13, 2026.                                   │
└─────────────────────────────────────────────────────────┘

WHAT I KNOW ABOUT YOU

YOU TOLD ME
- 3-year horizon
- OK losing half before panic
- Comfortable with credit spreads, new to long calls
- You read mostly around 8pm
[Edit what you told me →]

I'VE NOTICED
- You skip earnings setups (5 of 6 times)
- You follow credit-spread setups (4 of 5 times)
- You write a reflection same day as 7 of 8 followed trades

PATTERNS I'M WATCHING
- You may be exiting winners early (2 of 3 closes before target)
  ← Not sure yet — only 3 closes. Tell me if I'm reading
  this wrong.  [Yes, that's me]  [No, I had reasons]

STRENGTHS I'VE NOTICED
- Strong reflection habit
- Patient on entries (no Day-0 follows)
- Reads thesis before deciding (avg 47s on hero)

────────────────────────────────────────────────────────────

LESSONS YOU'VE EARNED  (4 of 23 in your competence map)
✓ What is implied volatility               (May 18)
✓ Why position sizing matters              (May 19)
✓ Price vs. value                          (May 21)
✓ When to ignore the news                  (May 23)
○ How to read a thesis        (encountered but not read)
○ The discipline of waiting   (encountered but not read)
[Open competence map →]

MISTAKES I'VE NOTICED YOU REPEAT
- Closed 2 winners ahead of target ("XLE Day 4", "SPY Day 6")
- Acknowledged in reflection on May 22 — worth re-reading.
[Read the lesson: Why investors cut winners →]

────────────────────────────────────────────────────────────

LAST THINGS YOU TAUGHT ME

May 24 — "I expect implied vol to keep falling — that's the edge."
May 23 — "Earnings risk" (when skipping AAPL)
May 22 — "I want to wait for the inventory print before sizing up."
[See all reflections →]

────────────────────────────────────────────────────────────

WHAT I'D DO NEXT

You haven't read today's briefing yet.
[Go to Today →]

────────────────────────────────────────────────────────────

TRACK RECORD (quiet metrics)
12 lessons read  ·  8 reflections  ·  4 paper trades open
My track record so far: 1 winning close, 0 losing closes,
3 still open. Too early to claim accuracy.
[Open full Track Record →]
```

### Editability — non-negotiable

Every memory item has an inline edit affordance:
- **Told me** → edit the underlying onboarding answer
- **I've noticed** → not editable (it happened)
- **Patterns I'm watching** → confirm / dispute pair
  - "Yes, that's me" → promotes to "Declared filter"
  - "No, I had reasons" → reduces confidence + Arth voices
    "Got it. I'll stop weighing this for a while."

### Tone rules

- Reflections quoted verbatim. Never paraphrased.
- Patterns use plural framing ("you've skipped X times") never
  identity framing ("you are X").
- Mistakes called "patterns I've noticed" not "mistakes" in the
  surface label, even though the section is named "Mistakes I've
  noticed you repeat" — gentle, not punishing.

## 2.4 Data model requirements

### New types

```
type PatternObservation = {
  id: string
  category: 'avoid' | 'favor' | 'strength' | 'mistake'
  text: string                    // user-facing first-person from Arth
  evidence_event_ids: string[]    // the events that produced it
  confidence: 'low' | 'medium' | 'high'   // surfaced as hedge words
  user_confirmed?: boolean
  user_disputed?: boolean
  retired?: boolean
}

type CompetenceEntry = {
  lesson_slug: string
  status: 'untaught' | 'encountered' | 'read' | 'learned' | 'recalled'
  first_encountered_at?: ISODate
  learned_at?: ISODate
  recall_count: number            // times referenced in reflections
}
```

### Pattern derivation rules (initial set)

| Pattern category | Trigger rule |
|---|---|
| avoid | ≥3 skips of same tagged setup type within 30 days |
| favor | ≥3 follows of same tagged setup type within 30 days |
| strength: reflection habit | reflection-written / followed ratio > 0.7 over 14d |
| strength: patient entry | mean time-to-decide > 30s over 7 followed trades |
| mistake: cut winners | ≥2 closes ahead of target with PnL > 0 within 60d |
| mistake: hold losers | ≥2 closes beyond invalidate with PnL < 0 within 60d |
| mistake: no reflection | followed without reflection ≥3 times in 7d |

Each rule outputs a PatternObservation with `confidence` based on
sample size (3-5 = low, 6-10 = medium, 11+ = high).

## 2.5 Implementation plan

| Step | Item | Effort |
|---|---|---|
| 2.5.1 | Build `patternEngine.ts` — runs on event change | 1d |
| 2.5.2 | Rules table (7 initial rules from §2.4) | 0.5d |
| 2.5.3 | `PatternObservation` CRUD + edit/dispute hooks | 0.5d |
| 2.5.4 | `CompetenceEntry` derivation from existing events | 0.5d |
| 2.5.5 | Rebuild `MePage` per §2.3 structure | 1d |
| 2.5.6 | Inline edit / dispute UX for patterns | 0.5d |
| 2.5.7 | Capture screenshots | 0.5d |

**Total: ~4.5 days**

No backend changes.

---

# TASK 3 — Contextual Learning

## 3.1 Current state (screenshot reference)

`arth-mvp-v2-2026-05-24/08-learn-desktop.png`

- Featured lesson hero
- "Continue your path" continuation
- 4 path tiles equal weight
- "This week" counters
- "What is ArthOS" trust footer

Reads as a content library. The user must browse to find learning.
Arth has no role.

## 3.2 Target state — Emergent Learning

**Principle: Learning is embedded directly in decisions, outcomes,
skips, wins, losses, and mind-changes. The Learn page is primarily
an archive of concepts encountered elsewhere — not a destination
for browsing.**

A user who never visits `/v2/learn` should still develop a real
competence map, because every relevant lesson surfaces inline at the
moment of encounter. The Learn page is where they go to REVIEW what
they've already met, not to discover new concepts.

Lessons are surfaced **in the moment a concept is encountered or a
mistake is made** — never as a stand-alone library destination.

Three teaching tiers (from architecture):

| Tier | Trigger | Format | Time cost |
|---|---|---|---|
| Primer | concept term tapped, or skip with conceptual reason | 30s popover | 30s |
| Lesson | requested depth from primer OR Arth scheduled it | 4-min inline page | 4 min |
| Path | structured study | archive grouped by theme | 20-60 min |

## 3.3 Event triggers — what causes Arth to teach

### Skip-with-reason → lesson recommendation

| Skip reason chip | Lesson recommended |
|---|---|
| Too risky | "Understanding Risk Tolerance" |
| Don't understand the structure | structure-specific (e.g. "What is a credit spread") |
| Already too exposed here | "Diversification 101" |
| Earnings risk | "Understanding Earnings Risk" |
| Not interested in this name | "Building Your Watchlist" |
| Bad timing | "The Discipline of Waiting" |

### Paper trade closed → outcome lesson

| Outcome | Lesson recommended |
|---|---|
| Closed beyond target (winner over-held) | "Why Investors Cut Winners" — celebrate but warn |
| Closed before target (winner cut early) | "Why Investors Cut Winners Early" |
| Closed below invalidate (loser over-held) | "Why Stops Exist" |
| Closed at invalidate (correctly stopped) | "The Discipline of Stops" |
| Expired worthless (options only) | "Time Decay in Options" |

### Behavior pattern → lesson recommendation

| Pattern detected | Lesson recommended |
|---|---|
| Skips every earnings setup (≥5) | "Earnings: Risk vs. Edge" |
| Never paper-trades options | "When Options Beat Stocks" |
| Reflects ≤1 of 4 follows | "The Power of a One-Sentence Thesis" |
| Day-0 follow on 3 of 5 visits | "The 24-Hour Rule" |
| Streak hits 7 | "The Discipline of Showing Up" |
| Streak hits 30 | "What 30 Days of Practice Has Taught You" |
| Mind-change seen 3+ times | "Why Models Change Their Mind" |

### Concept-tap → primer

Every italicized concept term in any Arth voice line or thesis is
tappable. Examples: *implied volatility*, *credit spread*, *gamma*,
*position sizing*, *time decay*, *invalidate*, *catalyst*.

## 3.4 Recommendation logic

```
function recommendLesson(event, memory, competence):
  candidates = []
  rules = [...skipReasonRules, ...outcomeRules, ...patternRules]
  for rule in rules:
    if rule.matches(event):
      lesson = rule.lesson
      if competence[lesson.slug].status === 'learned':
        continue                  // don't re-teach
      score = rule.priority
             - recencyPenalty(lesson, memory)
             - redundancyPenalty(lesson, competence)
      candidates.push({ lesson, score })
  candidates.sort(byScore)
  if candidates[0].score >= 0.7:
    return candidates[0].lesson
  return null
```

Where:
- `rule.priority`: 1.0 = direct skip → primer match; 0.8 = pattern;
  0.6 = milestone
- `recencyPenalty`: -0.3 if lesson surfaced in last 7 days
- `redundancyPenalty`: -0.2 if same theme as last surfaced lesson

## 3.5 UX flows

### Flow A — Skip leads to primer

```
1. User on Today → Skip — tell me why → "Earnings risk"
2. Arth responsive line replaces decision row:
   "Got it. I'll bias against earnings setups tomorrow.
    Want a quick primer on why earnings days are tricky?"
3. Tap "Yes" → 30s primer renders inline below the responsive line
   (NOT a new page, NOT a modal)
4. Primer content:
   "Earnings days carry an IV crush — implied volatility usually
    collapses right after the print. If you bought premium expecting
    a move, you can be right on the direction and wrong on the trade
    because the option's value evaporated. {30s example.}"
5. At end: "Got it" button + "Read the full 4-min lesson →"
6. Got it → competence.earnings_risk = 'read', event logged
7. Inline primer collapses, Arth's next line surfaces:
   "Logged. Less earnings stuff in your queue."
```

### Flow B — Closed trade leads to outcome lesson

```
1. Paper trade closes overnight (-2.1%, beyond invalidate)
2. Next session, on Today, Arth's opening is:
   "AAPL closed -2.1% — beyond the invalidate. I was wrong on
    the trade. Let me show you why, briefly."
3. Outcome lesson card renders below the opening:
   "Why this trade didn't work"
   [60s primer body]
   - The IV crush we expected didn't happen
   - The earnings beat was offset by guidance cut
   - The invalidate ($168) was the right line — you exited there
4. Reflection prompt: "What part of this would you do differently?"
5. Reflection saved → memory updated → trade marked
   "lesson taken"
```

### Flow C — Pattern detected leads to scheduled lesson

```
1. Pattern engine runs after each session close
2. Detects: skips_earnings_setups confidence high (5 of 6)
3. Schedules: "Earnings: Risk vs. Edge" for next session
4. Next visit, Today's Arth opening:
   "Pattern I've noticed: you've skipped 5 of 6 earnings setups.
    There's a way to think about them I'd like to share —
    when you have 4 minutes."
5. [Read it now] [Skip for now] [Don't bring this up again]
6. Read it now → inline lesson on Today, doesn't navigate
7. Skip for now → Arth tries again in 7 days
8. Don't bring this up again → suppressed permanently
```

### Flow D — Concept tap

```
1. Reading Today's hero card. Concept term "implied volatility"
   is italicized + underlined.
2. Tap → 30s primer popover (positioned over the card)
3. "Got it" → competence.implied_volatility = 'read'
4. Popover dismisses, card unchanged
```

## 3.6 Where lessons surface

| Surface | Slot |
|---|---|
| Today | Right below the hero card — "Worth learning right now" |
| Opportunities | Inline below the skipped card on skip |
| Practice (closed trade view) | Top of the closed-trade detail page |
| Me | "What I'd recommend next" slot |
| Journal | Inline on the day's row when the lesson was learned |
| Learn (archive) | Index of all earned + queued |

## 3.7 Implementation plan

| Step | Item | Effort |
|---|---|---|
| 3.7.1 | `lessonRecommender.ts` — rules table + scorer | 1d |
| 3.7.2 | `InlineLessonCard` component (primer + 4-min variants) | 1d |
| 3.7.3 | Concept-tap registry — extend `getTerm()` for primer lookup | 0.5d |
| 3.7.4 | Wire skip-reason → inline primer in `ArthHeroCard` | 0.5d |
| 3.7.5 | Wire trade-close → outcome lesson on Today opening | 1d |
| 3.7.6 | Pattern-detected → scheduled lesson surface | 0.5d |
| 3.7.7 | `competence_map` data + Me / Learn archive integration | 0.5d |
| 3.7.8 | Author 20 primers + 10 lessons mapped to the rules table | 1d |

**Total: ~6 days**

Authoring lesson content is the bottleneck. Engineering is ~5d;
copywriting another ~1-2d that can run in parallel with eng work.

---

# TASK 4 — Trust Engine + Arth Report Card

## 4.1 Why this matters most

The biggest unproven claim is "this AI is worth listening to." Every
other feature (personalization, contextual learning, mentor profile)
assumes the user trusts Arth's calls. Without trust signals,
recommendations are noise.

Current state: zero trust surfaces. Arth makes calls; user has no
evidence any of them ever worked.

Per the direction reset, Trust + Decision Quality must be established
**before** the relationship layer is expanded. This task therefore
elevates a new first-class surface — the **Arth Report Card** —
alongside the per-card trust strips and per-Today trust banner.

## 4.2 Components of the Trust Layer

| Component | What it shows |
|---|---|
| Recommendation history | Every past call, chronological |
| Outcome tracking | Per-call: win / loss / expired / open |
| Thesis-vs-outcome | "Said X would happen — actually Y happened" |
| Rolling accuracy | 30-day, 6-month win rate |
| Confidence calibration | "When high confidence, right X%; med, Y%; low, Z%" |
| Reasoning transparency | Audit trace per rec (architecture §5.2) |
| User follow rate | "You followed 58% of my calls" |
| User outcomes when following | Their paper PnL when they did |
| Mind-change diff | When Arth flipped on a symbol, the before/after |
| Admit-wrong moments | Explicit "I was wrong" on losses, no spin |
| Filter disclosure | "What I filtered out today" |
| Sample-size honesty | "Too early to claim accuracy" when N < 10 |

## 4.3 Metrics tracked

```
trust_metrics = {
  arth_calls_total: number
  arth_calls_closed: number
  arth_wins: number
  arth_losses: number
  arth_expired: number
  arth_accuracy_30d: number              // wins / (wins+losses)
  arth_accuracy_6m: number
  arth_accuracy_by_confidence: {
    low:    { calls, wins, losses, accuracy }
    medium: { calls, wins, losses, accuracy }
    high:   { calls, wins, losses, accuracy }
  }
  arth_calibration_score: number          // distance from perfect
  user_follow_rate: number               // followed / total
  user_followed_outcomes: { wins, losses, total_pnl_pct }
  user_skipped_outcomes_hypothetical: { wins, losses, total_pnl_pct }
  longest_winning_streak: number
  longest_losing_streak: number
  current_streak: { direction, count }
  thesis_match_rate: number              // outcome aligned w/ stated reason
}
```

All computed client-side from `decisions[].outcome` + `recommendation`
audit traces.

## 4.4 UX

### 4.4.1 Today — trust banner (subtle, always visible)

Below the Arth opening, before the hero card:

```
[Arth] {opening line}
                                              Day 12 of practice
                                              ────────────────────
                                              My last 30 days:
                                              8 calls · 5 wins
                                              3 losses · accuracy 62%
                                              [See full record →]
```

When N < 10:
```
                                              Day 12 of practice
                                              ────────────────────
                                              I've made 3 calls
                                              so far — too early
                                              to claim accuracy.
```

### 4.4.2 Per-card trust strip

On every recommendation card (hero + secondary):

```
[Decision row]
─────────────────────────────────────────────────
My last 5 picks like this (credit spreads):
  3 wins · 2 losses · avg +0.8% per close
Show me how I got here →
```

### 4.4.3 Audit trace ("Show me how I got here")

Tap → renders the 7 stages of the recommendation chain in plain
English (architecture §5.1):

```
WHY I PICKED AAPL

1. What data I used
   - HY OAS, DGS10, AAPL price + IV, market regime
   - (No stale features.)

2. Macro context
   - Market regime: directional (3rd day)
   - Credit gate: stable
   - Rates gate: calm

3. Strategy gate
   - Engine B fires today.

4. Universe scoring
   - 1,008 candidates evaluated
   - 10 passed per-symbol filters
   - AAPL ranked #1 by composite score

5. Why this structure
   - Long call spread (vs naked long) because IV at 22%ile —
     premium is cheap

6. Why for you
   - You marked credit spreads as comfortable (May 13)
   - You picked semis as an interest (May 13)
   - AAPL is on your watchlist

7. Confidence
   - Medium. Not high because earnings is 4w out — I want
     to see the IV behavior into next week first.

[Close]
```

### 4.4.4 Closed-trade retrospective

When a paper trade closes, instead of a silent update:

```
[Arth] AAPL just closed.

Result: +1.4% in 8 days. Target hit.

What I said: "I expect the IV to fall and the spread to
              decay in your favor."

What happened: IV fell from 22 to 18, spread decayed from
               $3.40 to $4.50, you closed at the +1.4% rung.

I was right on the structure and the timing.
This was a medium-confidence call. Add to my track record:
  high confidence calls so far: 0/0
  medium confidence calls so far: 4/5
  low confidence calls so far: 1/2

[Reflect on this →]  [See full thesis →]
```

### 4.4.5 Mind-change card

When Arth's view on a symbol flips:

```
[Arth] I changed my view on NVDA overnight.

YESTERDAY I said: Sell premium — IV at 78%ile, decent edge.
TODAY I say:      The IV crashed to 28%ile. That trade no
                  longer pays. I'd close the position if you
                  followed me.

What flipped:
  - IV: 78%ile → 28%ile
  - VIX term structure: contango → backwardation
  - Realized vol last 5d: 0.18 → 0.31

[Take Arth's exit]  [Hold anyway — tell me why]
```

### 4.4.6 ARTH REPORT CARD — first-class surface (NEW)

Route: `/v2/arth` (sibling to /v2/today, /v2/journal, /v2/me).
Sidenav promotion: appears as **"Arth's Report Card"** above the Me tile.

This is **the primary trust surface**. It is where Arth shows the work
the user is being asked to trust. Track Record (§4.4.7) becomes a
subsection of this page rather than a separate destination.

Required sections (top → bottom):

```
─────────────────────────────────────────────────────────────────
ARTH'S REPORT CARD
Updated {timestamp} · {N} closed calls · {M} open calls
─────────────────────────────────────────────────────────────────

[Arth] {voiced summary keyed to current sample size}

  N >= 30 closed:
    "Last 30 days: 18 calls, 11 wins, 6 losses, 1 expired.
     Accuracy 65%. My medium-confidence calls run hot at 73%;
     my low-confidence calls are roughly coin-flip. I'm
     calibrated within tolerance — but read on, the losses
     are the part worth your attention."

  N >= 10 closed:
    "Small sample so far: 12 calls, 7 wins, 4 losses, 1 open.
     Accuracy reads 64% but I wouldn't trust that number until
     30 closes. Read the losses first — they're more honest
     than the wins."

  N < 10 closed:
    "Too early to claim anything. {N} closed calls so far.
     I'm publishing this anyway because you should see how
     I'm thinking — not so you can score me yet."

─────────────────────────────────────────────────────────────────
1. RECOMMENDATION HISTORY
─────────────────────────────────────────────────────────────────
Chronological log. Newest first.

May 24 · AAPL · medium · followed · open · day 1
May 23 · TSLA · low    · skipped  · still open  · would be -0.3%
May 22 · XLE  · high   · followed · CLOSED +1.2% in 6d ✓ Right
May 21 · MSFT · medium · skipped  · would have won (+2.1%)
May 20 · NVDA · medium · followed · CLOSED -2.1% in 4d ✗ Wrong
...
[Filter: All / Followed / Skipped / Wins / Losses]
[Sort: Newest / Largest win / Largest loss / By confidence]

─────────────────────────────────────────────────────────────────
2. WINS AND LOSSES
─────────────────────────────────────────────────────────────────
30-day window:
  ✓ 5 wins  ·  avg +1.4%  ·  longest hold 9d
  ✗ 3 losses ·  avg -1.8%  ·  longest hold 5d
  ○ 0 expired (no theta-bleed yet)

Win/loss ratio: 1.67 (5/3)
Expectancy per call: +0.39% (mean PnL across all closed)
Current streak: 2 wins

[Show full PnL distribution chart →]

─────────────────────────────────────────────────────────────────
3. CONFIDENCE CALIBRATION
─────────────────────────────────────────────────────────────────
              calls   closed   wins   accuracy   target
  HIGH        2       0        —      —          85%+
  MEDIUM      6       5        4      80%        65-75% ✓
  LOW         4       3        1      33%        45-55% ✗ (too
                                                       generous?)

[Arth] My medium calls are calibrated. My low-confidence calls
are running too hot — I may be marking too many calls "low"
when they're actually high-risk. I'll re-baseline after the
next 5 closes.

─────────────────────────────────────────────────────────────────
4. CONFIDENCE ACCURACY (over time, last 90 days bucketed weekly)
─────────────────────────────────────────────────────────────────
[Sparkline: accuracy %, weekly, with confidence bands]
Week of May 17: 5 closes, 3 wins (60%)
Week of May 10: 4 closes, 3 wins (75%)
Week of May 03: 2 closes, 1 win (50%)
...

─────────────────────────────────────────────────────────────────
5. BEST AND WORST CALLS
─────────────────────────────────────────────────────────────────
BEST CALL (last 30 days)
  XLE · long · high confidence · closed +1.2% in 6d
  Thesis at the time: "Crack spreads widened without equity
                       follow-through."
  What actually happened: Equity caught up on EIA print. Held
                          target, exited at +1.2%.
  Why it worked: I called both the catalyst and the timing.
  [Re-read thesis →]

WORST CALL (last 30 days)
  NVDA · long · medium confidence · closed -2.1% in 4d
  Thesis at the time: "Bullish gamma, IV bottom quartile."
  What actually happened: Earnings guide cut, IV exploded,
                          spread evaporated.
  Why it didn't work: I underweighted forward guidance risk.
  Lesson I learned: When earnings is < 6 weeks out, IV
                    quartile rank is less reliable.
  [Re-read thesis →]   [See the lesson I drew →]

─────────────────────────────────────────────────────────────────
6. LESSONS ARTH LEARNED FROM MISTAKES
─────────────────────────────────────────────────────────────────
Visible record of how Arth updated his own thinking. Pure honesty.

May 20 — After NVDA -2.1%
  I now down-weight low-IV setups when earnings is <6w out.
  Next time I see this pattern, I'll flag earnings risk
  explicitly before recommending.
  [What I changed →]

May 12 — After TSLA short stopped at +0.4% (correctly)
  I held the invalidate line. I'll keep using daily-close-above
  as the stop trigger — intraday stops are too noisy.
  [What I confirmed →]

May 03 — After XLE early-exit on partial fill
  I now show partial-fill confirmation BEFORE recommending
  "hold target" — the user thought they were full, weren't.
  [What I fixed →]

[See all process updates →]

─────────────────────────────────────────────────────────────────
7. YOUR OUTCOMES (vs hypothetical)
─────────────────────────────────────────────────────────────────
When you followed me: +3.2% paper, 4 trades
If you'd followed every call: +4.1% paper, 8 trades
When you skipped me: 3 of 4 skips were winners (so far)
  ← I'm noting this. Your skip filter may be too tight.
  [See the skips →]

─────────────────────────────────────────────────────────────────
8. PROCESS TRANSPARENCY
─────────────────────────────────────────────────────────────────
- Every recommendation carries an audit trace.  [How I think →]
- Mind changes are logged.   [Every time I flipped a view →]
- Filtered candidates are visible.   [What I left out today →]
- This page updates after every trade closes.  No edits to
  past entries.

─────────────────────────────────────────────────────────────────
```

Voice rules on the Report Card surface:
- Arth talks about himself honestly, never defensively.
- Wins are stated plainly, not celebrated.
- Losses come **first** in the Best/Worst pair where appropriate.
- "Lessons I learned" is the section that most earns trust — it
  proves Arth updates rather than just optimizing his metrics.
- Sample-size honesty modes (N<5, N<10, N<30, N>=30) gate which
  metrics surface as numbers vs. honest disclaimers.

### 4.4.7 Honesty modes (gating)

The Report Card never lies about its sample size. Per-metric gating:

| Metric | Threshold to render as number | Below threshold |
|---|---|---|
| Accuracy | N >= 10 closed | "Too early — N closed so far" |
| Calibration | N >= 5 per confidence level | Hide that confidence row entirely |
| Streak | always shown | — |
| Best/Worst calls | N >= 3 closed | Render single most-recent close instead |
| Lessons learned | N >= 1 mistake | Hide section |
| User outcomes vs hypothetical | N >= 5 closed | Hide section |

### 4.4.8 Embedded honesty samples

When inline metric panels run with insufficient sample size:

```
ACCURACY: too early to tell.
I need ~10 closed positions before this is a real
number. Currently: 3 closed.

CALIBRATION: too early to tell.
I need 5+ calls per confidence level. Currently: 0 high,
2 medium, 1 low.

YOUR FOLLOW RATE: 67% (4 of 6) — typical for week 2.
```

## 4.5 Implementation plan

| Step | Item | Effort |
|---|---|---|
| 4.5.1 | Extend `Decision` with full outcome tracking | 0.5d |
| 4.5.2 | `trustMetrics.ts` — pure compute over decisions[] | 1d |
| 4.5.3 | `TrustBanner` component (Today + per-card) | 0.5d |
| 4.5.4 | `AuditTrace` component renders 7-stage trace | 1d |
| 4.5.5 | Persist audit trace per recommendation (mock for now, real later) | 0.5d |
| 4.5.6 | `ClosedTradeRetrospective` — fires on close | 1d |
| 4.5.7 | `MindChangeCard` — detect + render flips | 1d |
| 4.5.8 | **`/v2/arth` Report Card page (first-class surface)** — sections 1-8 per §4.4.6 | 2d |
| 4.5.9 | `historicalCohort()` resolver — feeds recommendation cards (Task 1) AND Report Card best/worst | 0.5d |
| 4.5.10 | "Lessons Arth learned" data type + manual seed of 3-5 examples | 0.5d |
| 4.5.11 | Honesty-mode rendering for small N (per metric gating table) | 0.5d |
| 4.5.12 | Sidenav promotion — add Arth Report Card tab | 0.25d |

**Total: ~9.25 days**

Two backend requests (deferred, mocked for now):
- `/recommendations/audit-trace/{id}` — returns the recorded trace
  for past calls
- `/recommendations/mind-changes` — diff detection over briefings

Mock both client-side for Phase 2; promote to backend in Phase 3.

---

# TASK 5 — Arth Intelligence Audit

Honest evaluation. Visual design ignored. Focus: does Arth genuinely
behave like an investing copilot?

## 5.1 Evaluation matrix

| Dimension | Current state | Target state | Gap size |
|---|---|---|---|
| **Intelligence** | Picks first placeable from a static list; hand-templated copy | Picks based on memory + market + history; reasoning earns each line | LARGE |
| **Usefulness** | Surfaces 1 hero + 3-button decision row on Today | Surfaces situationally; teaches in context; closes the loop | MODERATE |
| **Coaching ability** | Says "I picked this for you" with 5 rule-based reasons; fallback fires 80% of time | Acknowledges last decision; ties to lesson; frames next ritual | MODERATE |
| **Personalization** | Why-for-you resolver has 5 hardcoded rules over watchlist + level + topics | Adapts from skip-reasons, follow patterns, reflections, trade outcomes | LARGE |
| **Memory value** | Captures observations; surfaces in Journal | Surfaces back contextually; cited in next recommendation; visible in Me as patterns | MODERATE |
| **Novice friendliness** | Voice is plain; decision row is 3 buttons; reflection capture is one sentence | Empty-day honesty; contextual lessons fire; mistakes are taught not punished | MODERATE |
| **Trustworthiness** | Thesis snapshot kept; no track record visible; no calibration | Track record + calibration + audit trace + admit-wrong + mind-change all visible | LARGE |

## 5.2 Direct answer

**Does Arth genuinely behave like an investing copilot?**

**Partially. Arth speaks like one but does not yet think like one.**

The voice + decision capture + memory write are real. The
intelligence underneath is hand-picked. The relationship's surface
exists; the substance of the relationship — track record, adapted
reasoning, contextual teaching — is still missing.

## 5.3 Gaps ranked by user impact

| Rank | Gap | Why it matters most | Resolved by |
|---|---|---|---|
| 1 | **No track record** | User has zero evidence Arth's calls work. Trust gate. | Task 4 |
| 2 | **No real personalization** | Why-for-you fallback fires 80% of the time. Recs feel generic. | Task 2 + Task 4 |
| 3 | **No contextual learning** | Skips lead nowhere. Trade closes don't teach. Lessons are siloed. | Task 3 |
| 4 | **No mind-change visibility** | Arth seems static. Real reasoning shifts daily but invisible to user. | Task 4 (mind-change card) |
| 5 | **No outcome closure** | Followed trades sit forever. No celebration of wins, no honesty on losses. | Task 4 (closed-trade retro) |
| 6 | **No empty-day intelligence** | When nothing's clean Arth has nothing to say. Worst possible time to go silent. | Task 1 (empty-day variant) |
| 7 | **Pattern engine missing** | Me page can't show "what I've noticed about you" without it. | Task 2 |
| 8 | **No competence map** | Learning has no progress signal. | Task 3 |
| 9 | **Audit trace unbuilt** | Can't say "show me how you got here" yet. | Task 4 |
| 10 | **No conflicting-view honesty** | Arth never says "I'm uncertain" — uniform confidence reads false. | Task 4 (confidence levels) |

## 5.4 Proposed solutions, in priority order

1. **Build the Trust MVP (Task 4 basic — banner + per-card + audit trace + closed-trade retro).** This alone moves trust from 0 → 5. Without it nothing else matters.
2. **Build the pattern engine (Task 2 dependency).** Unlocks Me as relationship + real personalization on Today/Opportunities.
3. **Build the Decision Desk (Task 1).** Opportunities goes from analyst worksheet → primary daily decision surface.
4. **Build contextual learning (Task 3).** Closes the loop between mistakes and lessons.
5. **Build mind-change detection (Task 4 advanced).** Makes Arth's reasoning visibly alive.
6. **Build empty-day variant (Task 1).** Most honest moment in the product.
7. **Build calibration tracking (Task 4 long tail).** Pays off after ~30 closed positions.

---

# CONSOLIDATED ROADMAP

## Phase 2 sequence

| Phase | Name | Tasks delivered | Cumulative score |
|---|---|---|---|
| Today | Arth MVP (PR #14) | See/Decide/Practice/Reflect/Remember loop on Today + Journal | 7.0 |
| **2A** | **Pattern Foundation** | Pattern engine + competence map data + historical-cohort indexing | 7.2 |
| **2B** | **Trust MVP + Report Card** | Trust banner, audit trace, closed-trade retro, mind-change card, `/v2/arth` first-class Report Card surface | 8.2 |
| **2C** | **Decision Desk (Opportunities)** | Task 1 full — every rec answers all 5 mandated questions (incl. historical performance) | 8.7 |
| **2D** | **Contextual Learning** | Task 3 full — lessons embedded in decisions/outcomes/skips/wins/losses/mind-changes. Learn page = archive. | 9.1 |
| **2E** | **Mentor Profile (Me)** | Task 2 full — patterns + strengths + repeated mistakes + competence + relationship voice | 9.4 |
| **2F** | **Trust v2** | Confidence-cohort calibration + user-outcomes-vs-hypothetical + reflective retros across closed positions | 9.6 |

**Reorder rationale (per user direction reset):**
- Trust + Decision Quality must be established **before** the
  relationship layer is expanded.
- Mentor Profile (formerly 2C) is moved to 2E because patterns surface
  meaningfully only after recommendation history + outcomes accumulate
  in 2B + 2C.
- Decision Desk (formerly 2D) is moved up to 2C because every recommendation
  now must answer 5 mandated questions including historical performance —
  that data dependency lives in 2B's outcome tracking.

## Effort estimates

| Phase | Effort | Critical dependencies |
|---|---|---|
| 2A | 2 days | (none) |
| 2B | 9.25 days | 2A |
| 2C | 5.5 days | 2B (uses historical-cohort resolver from §4.5.9) |
| 2D | 6 days | 2B (audit trace + outcome data) + 2C (decision desk structure) |
| 2E | 4.5 days | 2A + 2B (Mentor Profile cites Report Card data) |
| 2F | 4 days | ~30 closed positions accumulated |

**Total Phase 2: ~31.25 working days** (~6.5 calendar weeks, single-track).

Parallelization:
- 2A is critical path — must ship first.
- 2B is critical path — must ship before 2C/2D/2E.
- 2D depends on 2C (skip → lesson + outcome → lesson uses Decision Desk skip-reason chips).
- 2E can run in parallel with 2D once 2B has landed.
- 2F waits for accumulated closed-position data — runs later.

Compressed schedule: ~5 calendar weeks with two parallel tracks
once 2B lands.

## Priority ranking (single-track sequence)

1. **2A Pattern Foundation** — invisible plumbing, unblocks 2B/2C/2E
2. **2B Trust MVP + Report Card** — Arth earns trust before expanding the relationship layer
3. **2C Decision Desk** — every rec answers the 5 mandated questions
4. **2D Contextual Learning** — lessons embedded in decisions and outcomes
5. **2E Mentor Profile** — relationship layer built on top of established trust + decisions + learning
6. **2F Trust v2** — calibration earns its place after data exists

## Out of scope for Phase 2

These wait for Phase 3:
- LLM-powered Arth voice (`/arth/voice` backend) — Phase H per architecture
- Multi-device sync — Phase H per architecture
- Real-time signal-driven mind-change (currently briefing-cache diff)
- Cross-user social proof
- Real-money integration

## Acceptance per phase

| Phase | Acceptance criteria |
|---|---|
| 2A | Pattern observations surface in dev console after 5 events; competence entries populate from event log; historical-cohort key resolves per recommendation |
| 2B | Trust banner visible on Today; tap audit trace renders 7 stages; closed paper trade triggers retrospective; mind-change card appears when briefing diff detected; **`/v2/arth` Report Card route ships with sections 1-8, sample-size honesty modes, and "Lessons Arth learned" subsection** |
| 2C | Opportunities page has THE ONE + ALSO CONSIDER + WATCHING + PASSED ON; hero card explicitly answers all 5 mandated questions (Why this idea / Why not alternatives / Why now / What invalidates / Historical performance); historical-cohort row renders honest "too early" mode when N<5 |
| 2D | Skip-with-reason "earnings risk" triggers inline primer; closed paper trade fires outcome lesson on next session; concept tap shows 30s popover; Learn page is reframed as competence archive (earned vs queued) — no longer a content discovery surface |
| 2E | Me page shows 6 of 9 mentor profile sections fully populated after 14 days of synthetic use; pattern observations editable; reflections quoted verbatim; Report Card data cited inline |
| 2F | Calibration shows per-confidence accuracy; user outcomes-vs-hypothetical visible on Report Card; >=10 past calls in Report Card history |

## What ships after Phase 2

A product that:
- Walks novice through 6-chapter daily loop on every surface (not just Today)
- Surfaces Arth's track record with honest sample-size caveats
- Adapts recommendations to observed skip / follow patterns
- Teaches concepts the moment a user encounters them
- Owns its losses and changes its mind in public
- Has a Me page that reads like a mentor's notes, not a dashboard

Expected product score: **9.5 / 10**.

What it still won't have: a LLM behind Arth's voice (templated hand-
authored copy), sync across devices, real-money trading, social proof.
Those are Phase 3 or later.

---

## Document index

- §0 Executive findings
- §1 (Task 1) Opportunities as Decision Desk
- §2 (Task 2) Me as Mentor Profile
- §3 (Task 3) Contextual Learning
- §4 (Task 4) Trust Engine
- §5 (Task 5) Arth Intelligence Audit
- Consolidated roadmap

## Screenshot references

| Reference | Path |
|---|---|
| Current Today | `docs/research/Screenshots/arth-mvp-v2-2026-05-24/01-today-fresh-day1-desktop.png` |
| Current Today after Follow | `…/02-today-after-follow-desktop.png` |
| Current Today after Skip | `…/03-today-after-skip-desktop.png` |
| Current reflection capture | `…/05-reflection-capture-desktop.png` |
| Current Journal populated | `…/06-journal-populated-desktop.png` |
| Current Opportunities | `…/07-opportunities-desktop.png` |
| Current Learn | `…/08-learn-desktop.png` |
| Current Me | `…/09-me-desktop.png` |
| Current Today mobile | `…/10-today-mobile.png` |
| Current reflection mobile | `…/11-reflection-capture-mobile.png` |
| Current Journal mobile | `…/12-journal-mobile.png` |

## Decision request

Before any 2A code starts, confirm (REVISED per direction reset):

1. **The reordered six-task sequence is approved**:
   2A Pattern Foundation → 2B Trust MVP + Arth Report Card →
   2C Decision Desk → 2D Contextual Learning → 2E Mentor Profile →
   2F Trust v2.
2. **Critical path** is **2A → 2B → 2C**. 2D + 2E can run in
   parallel after 2C. 2F waits for accumulated outcome data.
3. **Every recommendation card must answer all 5 mandated questions**
   (Why this idea / Why not alternatives / Why now / What invalidates /
   Historical performance). No card ships without all five.
4. **Arth Report Card** lands as a first-class `/v2/arth` route in 2B
   (sidenav promoted above Me tile).
5. **Learn is reframed as an archive** in 2D. Lessons surface inline
   in Today/Opportunities/Practice/Journal at the moment of encounter.
6. Backend changes are limited to two future endpoints
   (`/arth/voice`, `/arth/sync`) — neither in Phase 2 scope.
7. LLM-powered voice deferred to Phase 3 (continue with hand-templated
   copy + variable substitution).
8. Authoring 20 primers + 10 lessons + 3-5 "lessons Arth learned"
   examples queued as a content workstream parallel to engineering.

Once confirmed: open Phase 2A implementation worktree.
