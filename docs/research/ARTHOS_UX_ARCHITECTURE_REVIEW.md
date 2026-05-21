# ArthOS UX Architecture Review

**Date**: 2026-05-21
**Status**: STRATEGIC REVIEW — no implementation
**Sources of truth**:
1. Implementation (PR-1 → PR-4 shipped)
2. Magic Patterns "ArthOS" mockup
3. Original vision: "calm AI-assisted investing mentor where users learn investing while using the platform"

Synthesis of four lenses: Strategist · UX Lead · Competitive Analyst · Architecture Reviewer.

---

## 1. User Journey Map

### Persona 1 — New Visitor (no account, no context)

| Stage | Need | Current state | Gap |
|---|---|---|---|
| Entry           | "What is this?"                            | `/` redirects to `/overview` → operator console with TopStrip + StatusRail | **Critical**: no marketing landing, no value-prop surface; novice sees engineering chrome on first click |
| Orientation     | "Is this safe to try?"                    | nothing addresses "paper-only" until 2-3 scrolls in | **High**: paper-trading disclosure should be the first thing they see |
| Trust building  | "Has this AI worked?"                      | track record buried at `/portfolio?view=working` | **High**: no public-facing "AI's history" before signup |
| Learning        | "Will I understand what I see?"           | none | **High**: no "How this works" explainer for cold visitors |
| First paper trade | "Where do I start?"                       | no onboarding | **Critical** |
| Portfolio growth | n/a (not yet a user)                     | n/a | n/a |
| Long-term retention | n/a                                  | n/a | n/a |

**Gap rank**: Visitor experience is the biggest hole. Every other persona starts post-signup.

### Persona 2 — New User (just signed up, never traded)

| Stage | Need | Current state | Gap |
|---|---|---|---|
| Entry           | "Help me start"                              | dropped on `/overview` or `/today` directly | **High**: no onboarding flow |
| Orientation     | "What does each thing mean?"                 | TodayPage hero is calm but assumes vocabulary | **Medium**: glossary exists but not surfaced contextually |
| Trust building  | "Why should I trust the picks?"             | Pick Detail (PR-4) does well; Today's "What changed" + Track Record do well | low gap |
| Learning        | "How do I learn?"                            | Learn Hub doesn't exist yet | **High**: PR-5 not shipped |
| First paper trade | "Can I just try one?"                       | not currently possible — engine creates trades on the user's behalf | **Medium**: should "shadow approval" or "AI trades for you" be the model? Today it's automated only |
| Portfolio growth | "Am I doing well?"                         | TodayPortfolioPage shows live + official | low gap |
| Long-term retention | "Why come back daily?"                  | "What changed" + recent moves give reason | medium gap — needs more |

### Persona 3 — Beginner Investor (knows stocks exist, doesn't know what NAV is)

| Stage | Need | Current state | Gap |
|---|---|---|---|
| Entry           | "Reassure me this isn't real money"        | "paper" labels exist | low gap |
| Orientation     | "Translate jargon for me"                    | MetricHelpTooltip exists but rare | **High**: tooltips not on every term |
| Trust building  | "Show me losses too"                          | Track Record (PR-6 pending) will deliver | depends on PR-6 |
| Learning        | "Teach me as I go"                            | inline learn-chips on Pick Detail (PR-4) — link to non-existent /learn pages | **High**: 16 chips lead to 404 until PR-5 |
| First paper trade | "Why did the AI do that?"                  | Pick Detail "Why this appeared" answers it | low gap |
| Portfolio growth | "What should I notice?"                    | TodayPage What-changed answers it | low gap |
| Long-term retention | "Help me feel smarter"                  | Learning card on Today rotates 1 term — too thin | **High**: needs paths, retrospectives |

### Persona 4 — Intermediate Investor (already trades, wants AI second opinion)

| Stage | Need | Current state | Gap |
|---|---|---|---|
| Entry           | "Show me the engine"                       | operator surfaces survive at `/decisions`, `/signal-lab` | low gap |
| Orientation     | "Don't hide the math"                       | Technical-detail expander on Pick Detail (PR-4) | low gap |
| Trust building  | "Show methodology"                          | no methodology doc / no "how the engine works" | **High**: no documented epistemics |
| Learning        | "Skip the basics"                            | Learn Hub PR-5 not shipped | medium gap |
| First paper trade | "Let me compare to my own picks"         | not currently supported (no manual entry) | **Medium**: could be a feature post-Canary |
| Portfolio growth | "Track AI vs me"                            | not supported | **High**: a key competitor differentiator (FinChat does this) |
| Long-term retention | "Performance attribution"                | no factor breakdown of returns | **Medium**: PR-6 Track Record could include |

### Persona 5 — Returning User (logs in weekly+)

| Stage | Need | Current state | Gap |
|---|---|---|---|
| Entry           | "What happened since last visit?"          | TodayPage What-changed (PR-3) answers this directly | **low gap** ✓ |
| Orientation     | "Anything urgent?"                           | One thing to look at + Defensive posture row | low gap |
| Trust building  | "Has the AI been honest?"                  | Track Record pending PR-6 | depends |
| Learning        | "Help me deepen"                            | Learn Hub pending PR-5 | depends |
| First paper trade | n/a                                          | n/a | n/a |
| Portfolio growth | "How is my account doing?"                 | TodayPortfolioPage + live MTM | low gap |
| Long-term retention | "Compounding habit"                      | weekly recap concept designed; not built | **Medium**: PR-6 can include |

### Synthesis

The product is strongest for **returning users** (PR-1+2+3 already shipped). Weakest for **new visitors** (no marketing surface) and **intermediate investors** (no methodology doc, no AI-vs-me comparison). Biggest immediate ROI: PR-5 Learn Hub closes the 404 chips and serves all four post-signup personas.

---

## 2. Information Architecture

| Page | Purpose | Primary question answered | Trust role | Educational role | Business role |
|---|---|---|---|---|---|
| **Today**        | First-30s orientation                 | "Anything I need to know?" | high — AI's current view + recent moves | medium — rotating glossary term | core daily entry; retention driver |
| **Portfolio**    | "What do I own?"                       | "What's in my account?"   | medium — live + official duality | low — "Reading this page" card | account-state surface |
| **Pick Detail**  | "Why this signal?"                    | "Why is the AI flagging X?" | **highest** — load-bearing trust | high — concept tag + 10 learn chips | conversion driver from idle to engaged |
| **Learn Hub**    | Compounding literacy                  | "What does X mean?"        | medium — methodology lives here | **highest** — core identity | retention loop |
| **Track Record** | Honest AI history                     | "Has this been any good?" | **highest** — honest losses surface | medium — interpretation of drawdown | trust-conversion-to-loyalty |
| **Copilot**      | Conversational query                  | "Ask anything"              | medium — sources citations | medium — explains terms inline | engagement spike; needs backend |
| **Onboarding**   | Calibrate risk + start                | "How does this fit me?"   | medium — sets expectations | high — first lesson | conversion: signup → first paper trade |
| **Settings**     | Account preferences                   | "Where do I change X?"    | low | low | utility |
| **Operator** (advanced) | Engineering escape         | "Show me the working"     | low (engineers don't need trust here) | low | retention for power users |

### Overlaps + redundancies

| Overlap | Decision |
|---|---|
| Today's "What changed" + Track Record's "Recent moves"  | distinct — Today = 24h; Track Record = lifetime. Keep both. |
| Today's "AI's recent moves" 4-row strip + Track Record full history | distinct — Today is teaser; Track Record is detailed. Keep both. |
| Pick Detail's "Risk awareness" + Track Record's drawdown chart | distinct — Pick Detail = per-position; Track Record = portfolio. Keep both. |
| Pick Detail's "Learn more" chips + Learn Hub glossary | one-way link; chips lead to Learn entries. Not redundant. |
| Copilot's "Why did the AI do X?" + Pick Detail's "Why this appeared" | **risk of overlap** — Copilot answers historical questions, Pick Detail answers current state. Cross-link rather than duplicate. |
| Onboarding's risk profile + Settings' preferences | distinct — Onboarding = one-time gate; Settings = ongoing changes |
| Today's Learning card + Learn Hub featured term | redundant if same content shown twice. Decision: Today shows TODAY's term; Learn Hub featured = rotating wider catalog. |

No structural redundancies. Each page has a defended purpose.

---

## 3. Navigation Architecture

### Current (PR-1)

```
Today  ·  Portfolio  ·  Ideas  ·  Learn
                                        › Advanced
```

### Magic Patterns proposal

```
Today  ·  Portfolio  ·  Copilot  ·  Learn  ·  Track Record
                                        › Operator
```

### Tradeoff analysis

| Slot | Current option | Mockup option | Final pick |
|---|---|---|---|
| 1 | Today                | Today              | Today |
| 2 | Portfolio            | Portfolio          | Portfolio |
| 3 | Ideas                | Copilot            | **Copilot** (more emotionally distinctive; Ideas overlap with Today's One Thing) |
| 4 | Learn                | Learn              | Learn |
| 5 | (none)               | Track Record       | **Track Record** (honest history is core product identity) |

Demoted to Advanced: Ideas (live at `/action-queue` or `/ideas`, but not in primary nav)

### Final navigation recommendation

**Desktop** — left sidebar (240px) on `>=1024px`:
```
[ArthOS logo]
─────────
Today               (active = sage dot left)
Portfolio
Copilot
Learn
Track Record
─────────
› Operator          (collapsed by default, click to expand)
─────────
[user menu — bottom]
```

**Mobile** — bottom tab bar (4 items, 64px tall, safe-area aware):
```
[Today] [Portfolio] [Copilot] [Learn]
                                   [≡ More]
```

`More` opens drawer with Track Record + Operator + Settings.

Track Record demoted on mobile because tab bar = 4 items max; the 5th lives in the More drawer.

**Why bottom tab bar on mobile**: novice-friendly, thumb-reachable, persistent orientation. iOS/Android native pattern.

### Operator containment

`Operator` link sits as a **collapsed secondary section** on desktop, accessed via "More" drawer on mobile. Engineers reach it by direct URL or via the expander. Never primary nav.

---

## 4. Design System Lock

**Locked as of PR-4.5 (token + Fraunces upgrade)**. After this PR ships, changes require an explicit design review.

### 4a. Color tokens (LOCKED)

```
--surface-paper:      #FAFAF7   (sand-50)
--surface-elevated:   #F4F1EA   (sand-100)
--surface-sunken:     #E8E6DF   (sand-200)
--ink-primary:        #0E0E0E   (ink-900)
--ink-secondary:      #57534E   (ink-500)
--ink-muted:          #78716C   (ink-400)
--ink-faint:          #A8A29E   (ink-300)
--accent-trust:       #163225   (forest-800)
--accent-trust-soft:  #B8D2BE   (forest-200)
--tone-up:            #1F4530   (forest-700)
--tone-down:          #B05E4C   (coral-500)
--tone-warn:          #C9A961   (ochre-400)
--border-quiet:       #E8E6DF
```

**Lock**: no new color tokens without design review. No bright/saturated colors. No glow tokens.

### 4b. Typography (LOCKED)

```
--font-display:  Fraunces  (300 / 400 / 500)
--font-body:     Inter
--font-mono:     JetBrains Mono
```

Scale:
- Display 38px (NAV) · 28px (page H1) · 24px (Today AI read) · 22px (Pick Detail thesis)
- Body 16px (read), 14px (meta), 13px (secondary), 12px (eyebrow)
- All numerics: `tabular-nums`

**Lock**: no new font families. No display below 22px. No body below 14px.

### 4c. Spacing (LOCKED)

```
--space-1: 4px · --space-2: 8px · --space-3: 12px · --space-4: 16px
--space-6: 24px · --space-8: 32px · --space-12: 48px · --space-16: 64px
```

Reading column max-width: 720px desktop. Page gutters: 80px desktop, 24px mobile. Section gap: 32px (24px mobile). Card padding: 24px (hero) or 16px (stack).

**Lock**: no spacing outside this scale.

### 4d. Card system (LOCKED)

Two canonical variants:
- `.calm-card` (24px padding) — hero cards, One-thing, Reading-page
- `.calm-card-stack` (16px padding) — evidence cards, risk cards, holdings rows

Both: 1px border `--border-quiet`, 12px border-radius, no box-shadow at rest, hover changes border-color only.

**Lock**: no third card variant without design review. No shadows. No background tints beyond surface tokens.

### 4e. Motion system (LOCKED)

```
--motion-fast: 150ms ease-out
--motion-default: 200ms ease-out
--motion-slow: 350ms ease-out
```

Allowed: opacity, color, border-color, background-color.
**Forbidden**: transform (translate/scale/rotate/skew), filter (blur/glow), animation loops (pulse/shimmer).

Page entry: opacity 0→1 over 350ms. No slide-up. No stagger.

`prefers-reduced-motion: reduce` → all transitions instant.

**Lock**: motion vocabulary cannot grow without design review.

### 4f. Iconography (LOCKED)

Library: Lucide. Stroke: 1.5px. Size: 20px default (16px small, 24px large). Color: `currentColor`.

Approved Layer-1 icons: TrendingUp · TrendingDown · ArrowRight · ChevronRight · ChevronDown · Clock · BookOpen · Info · Circle (dot) · BarChart3.

**Forbidden**: Sparkles · Zap · Rocket · Trophy · Flame · animated icons · emoji icons.

**Lock**: new icons require review against the calm-mentor persona.

### 4g. Chip system (LOCKED)

Two canonical chips:
- `.calm-chip` (passive tone variants) — `quiet · trust · up · down · warn`
- `.calm-chip-action` (clickable, links) — primary text + ChevronRight

Padding: 2-8px vertical, 8-12px horizontal. Radius: 6-8px. No background gradient. No badge variant with filled bright color.

**Lock**: no new chip variants.

### 4h. Chart styling (LOCKED)

- Equity / sparkline: 1.5px stroke, `currentColor` default, sand-50 area fill at 8% alpha
- Drawdown: 1.5px stroke `--tone-down`, dotted reference line at 0% in `--ink-faint`
- Histograms: bar stroke `currentColor`, fill `--surface-sunken`
- No 3D effects, no gradient fills beyond 8% alpha, no animated draws

**Lock**: only Recharts (already in mockup). No D3 custom charts. No interactive scrubbing on Layer 1 charts.

### 4i. Educational callout styling (LOCKED)

`.today-learn` style for inline learning blocks:
- Background `--surface-sunken`
- Padding 24px, radius 12px
- Title: Fraunces 18px
- Body: Inter 15px ink-secondary
- CTA: small accent link with → arrow

Glossary side drawer: slides from right at 320px width on desktop, full-screen modal on mobile. Single-purpose drawer; no multi-step nav.

**Lock**: educational components share this style. No standalone tutorial overlays. No tooltips longer than 80 characters.

---

## 5. Trust Model Audit

For each surface — how does it build trust, educate, reduce anxiety, avoid trading-dashboard feel? Identified weaknesses listed.

### Today
- **Trust**: AI read sentence + What-changed observational rows + Recent moves
- **Education**: rotating Learning card
- **Anxiety reduction**: NAV first; calm typography; honest absence states
- **Dashboard avoidance**: serif typography; no glow; no badges
- **Weakness**: "Track record" label may read as operator vocabulary; learning card looks like heading not CTA

### Portfolio
- **Trust**: live + official duality; both labeled clearly
- **Education**: "Reading this page" inline note
- **Anxiety reduction**: muted tone dots for return state (sage/terracotta, not green/red)
- **Dashboard avoidance**: row layout vs grid
- **Weakness**: 40+ rows can overwhelm; no top-5 grouping; no risk overview block

### Pick Detail
- **Trust**: thesis first; evidence and risk at IDENTICAL visual weight (load-bearing claim)
- **Education**: concept tag + 10 inline learn-chips
- **Anxiety reduction**: "What could go wrong" rendered same size/color as evidence
- **Dashboard avoidance**: technical detail collapsed; no big colored action badge
- **Weakness**: long mobile scroll without ToC; concept tag disappears mid-page

### Learn Hub (pending PR-5)
- **Trust**: methodology lives here
- **Education**: PRIMARY purpose
- **Anxiety reduction**: short lessons (~3 min); plain English
- **Dashboard avoidance**: editorial reading layout
- **Weakness**: not yet built; 16 chip links currently 404

### Track Record (pending PR-6)
- **Trust**: PRIMARY purpose — honest history with losses
- **Education**: explains drawdown psychology
- **Anxiety reduction**: framed as journal not leaderboard
- **Dashboard avoidance**: no win-rate counters, no streaks
- **Weakness**: not built; risk of becoming a chart-first surface if mishandled

### Copilot (pending PR-8)
- **Trust**: answers cite source rows
- **Education**: explains terms inline
- **Anxiety reduction**: friction-low (just ask)
- **Dashboard avoidance**: conversational, not tabular
- **Weakness**: backend doesn't exist; risk of hallucinated answers; HIGH constitutional risk

### Onboarding (pending PR-7)
- **Trust**: sets expectations (paper-only, AI is rule-driven, not magic)
- **Education**: first lesson
- **Anxiety reduction**: 3-question profile is gentle
- **Dashboard avoidance**: no dashboards at all
- **Weakness**: risk profile UI hasn't been designed yet

### Settings (pending PR-9)
- **Trust**: shows account state honestly
- **Education**: low
- **Anxiety reduction**: utility surface
- **Dashboard avoidance**: form layout
- **Weakness**: low priority; can be minimal

### Operator (kept hidden)
- **Trust**: shows real engine internals to those who ask
- **Education**: none (operator vocabulary)
- **Anxiety reduction**: none (not for novices)
- **Dashboard avoidance**: intentionally engineering-flavored
- **Weakness**: by design — this is the escape valve

### Overall weakness pattern

The **biggest trust weakness across the product**: 16 chip links on Pick Detail point to `/learn/term/:slug` and `/learn/concept/:slug` routes that 404. **PR-5 must fix this or the calm Pick Detail experience breaks at the moment a user clicks Learn**.

---

## 6. Competitive Benchmark

| Competitor | What they do better | ArthOS should COPY | ArthOS should AVOID |
|---|---|---|---|
| **Wealthfront** | passive index + tax-loss harvesting story; calm tone | calm onboarding; clear paper-only labels; honest risk framing | "set and forget" passivity (we want users to learn, not delegate) |
| **Betterment** | goals-first framing; risk profile flow; segmented portfolios | risk-profile question pattern (3-question gate); separate portfolios per goal | aggressive upselling; nudge marketing |
| **Magnifi** | natural-language pick discovery ("show me ETFs with low fees in healthcare") | conversational input pattern (relevant to Copilot PR-8) | broad search bar UX (we have focused signals, not search) |
| **Composer** | strategy-builder visual blocks; backtest transparency | backtest transparency framing (helps Track Record) | DIY strategy authoring (too operator-heavy for our novice persona) |
| **Public** | community + social proof; "see what others are buying" | NONE — social proof contradicts our "honest losses" identity | social feed; copy-trading; emoji reactions |
| **Robinhood** | onboarding speed; default-friendly; option education | speed of onboarding to first interaction | confetti; gamification; option-trading nudges; price ticker theatre |
| **FinChat** | per-company AI Q&A with source citations | source-cited Copilot answers (relevant to PR-8) | breadth of company coverage (we have a focused universe) |
| **Koyfin** | dense data terminal | NONE — opposite end of the spectrum | grid-heavy dashboards; chart-first |

### What ArthOS uniquely does

1. **Honest losses with equal visual weight** — no competitor renders losses without de-emphasis
2. **Deterministic reasoning envelopes** (Phase L) — no competitor exposes the reasoning skeleton structurally
3. **Paper-only with serious infrastructure** — most paper-trading products are toys; we have real cron, real telemetry, real audit
4. **Calm-mentor positioning** — most AI investing products are either casinos (Robinhood) or black boxes (Wealthfront). We are neither.

---

## 7. Product Differentiation

### "After 5 minutes inside ArthOS, what makes them remember it?"

| Memory hook | Surface | Strength |
|---|---|---|
| Editorial typography (Fraunces serif on warm sand) | Today | high |
| "Why this appeared today" with falsifiable bullets | Pick Detail | high |
| Risk surfaced at identical weight to evidence | Pick Detail | **highest — load-bearing differentiator** |
| Honest absence states ("No notable changes since your last visit") | Today + Pick Detail | medium |
| Inline learn-chips that open a drawer (not a new page) | Pick Detail | medium |
| Live + official portfolio NAV dual label | Today + Portfolio | medium |
| No glow / no streak counter / no winners-only | All | medium |
| Calm color palette (warm sand, deep sage) | All | medium |
| Single CTA per surface, never urgency | All | low-medium |

### Moat beyond quant models

1. **Constitutional locks** (Tier-A lint, resolver-anchor, Phase L envelopes) — competitors cannot copy this without rebuilding their truth infrastructure
2. **Calm-mentor voice enforced by CI** — no other product in this category has lint-enforced copy discipline
3. **Honest absence as a design primitive** — every surface has a defined "we don't know" state
4. **Reasoning that's deterministic and traceable** — every envelope is sourced; no LLM hallucination surface

### What cannot be easily copied

- The 30-phrase Tier-A forbidden-phrase lint (30 specific patterns enforced in CI)
- The Phase L deterministic renderer (engine signals → skeleton selection → slot fills → uncertainty markers → invalidation → triggers, all hash-stable)
- The wrapper-RC honesty contract (jobs return `{skipped, reason}` not `None`)
- The single-trust accent + single-warning tone + dot-not-pill chip system (small individual choices, hard-to-copy aggregate)

The moat is **truth infrastructure + calm-voice discipline**, not features.

---

## 8. Final Recommended Roadmap

Re-ranked by maximum product value (highest impact first).

| Rank | PR | Scope | Why this rank |
|---|---|---|---|
| 1 | **PR-4.5**  | Token + Fraunces upgrade (CSS only) | unblocks every subsequent PR; compounds |
| 2 | **PR-5**    | Learn Hub: index + 5 lessons + 6 concepts + 10 terms | **fixes 16 dead chip links on Pick Detail**; serves 4 of 5 personas |
| 3 | **PR-6**    | Track Record full page | **load-bearing trust surface**; biggest single trust upgrade |
| 4 | **PR-7**    | Onboarding / Risk Profile | gates new-user experience; conversion driver; localStorage-first |
| 5 | **PR-10**   | Advanced area containment + rename "Advanced" → "Operator" | structural cleanup before Copilot lands; quick win |
| 6 | **PR-9**    | Settings minimal | utility; small effort; no urgency |
| 7 | **PR-8**    | Copilot UI shell | UI-only since backend deferred; high risk of hallucination if backend forced |
| (NEW) | PR-12 | Mobile bottom-tab nav | mobile UX upgrade; high-impact on mobile-first novice persona |
| (NEW) | PR-13 | Marketing landing page | visitor persona has zero entry today |

### Rationale for reordering vs the prior sequence

- **PR-5 moves above PR-6**: 16 chips currently 404. PR-5 is a dependency-fix; PR-6 is additive.
- **PR-10 (Advanced containment) moves up**: tiny effort, large cleanup. Should happen before Copilot.
- **PR-8 (Copilot) moves DOWN**: backend is undesigned; shipping a UI shell with no backend is risky. Defer until Phase L+ extensibility plan lands.
- **NEW PR-12 mobile nav**: returning users on mobile is a high-retention persona; bottom-tab pattern is industry standard.
- **NEW PR-13 marketing landing**: visitor persona has zero coverage today.

### Sequencing principle

Trust-building before new-feature surfaces. Education before tools. Cleanup before expansion.

---

## Locks declared by this review

The following are locked and should not change without an explicit design review document:

| Domain | Lock |
|---|---|
| Color tokens                                   | §4a — 13 named tokens, no new ones |
| Font stack                                     | §4b — Fraunces / Inter / JetBrains Mono only |
| Spacing scale                                  | §4c — 8 named tokens, no new ones |
| Card system                                    | §4d — 2 canonical variants |
| Motion vocabulary                              | §4e — opacity + color + border only |
| Icon library                                   | §4f — Lucide 1.5px stroke, approved set |
| Chip system                                    | §4g — 2 canonical chips |
| Chart styling                                  | §4h — Recharts, 1.5px stroke, no 3D, no gradients |
| Educational callout styling                    | §4i — `.today-learn` pattern |
| Primary navigation                             | §3 — Today / Portfolio / Copilot / Learn / Track Record |
| Operator containment                           | §3 — collapsed secondary on desktop, More drawer on mobile |
| Truth infrastructure                           | unchanged — Phase L, Tier-A lint, wrapper-RC, HONEST-BANNER |
| Reasoning prose source                         | unchanged — backend renderer only |

---

## Single synthesized recommendation

ArthOS has the truth infrastructure of a serious financial product and the visual restraint of a calm mentor. The remaining gap is **education depth + new-visitor onboarding**.

**Ship in this order**:
1. **PR-4.5** — lock the design system (1 day)
2. **PR-5** — Learn Hub closes the 16-chip dead-links (1 day)
3. **PR-6** — Track Record completes the trust narrative (3-4h)
4. **PR-7** — Onboarding adds risk-profile gate (1 day)
5. **PR-10** — Advanced containment + rename (3h)
6. **PR-12** — Mobile bottom-tab nav (4-6h)
7. **PR-9** — Settings (3-4h)
8. **PR-8** — Copilot UI shell (backend deferred)
9. **PR-13** — Marketing landing (separate scope)

Total to ship PR-4.5 → PR-12: roughly **3-4 focused days of wall-clock**.

After PR-12, the product becomes promotable to its visitor persona for the first time. Until then, ArthOS is for users who already know the product exists.

---

## Stop

No code in this review. No diffs. No components. Awaiting decision on:

1. Approve the design system lock (§4)
2. Approve the 5-item nav decision (§3)
3. Approve the re-ranked roadmap (§8)
4. Approve PR-4.5 as the next implementation target
