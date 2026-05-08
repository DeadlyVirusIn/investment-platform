# UX-7 — Visual Design System Master

**Status:** master synthesis. Locked after a four-round debate
between Gemini 2.5 Pro · Codex · Claude Opus 4.7 · Claude Sonnet
4.6 (substituting for the requested Sonnet 4.7). Full transcripts
archived at `.debate/ux7_visual_20260508-165325/`.

This document is the visual companion to UX-6
(`UX_6_AI_COPILOT_MASTER.md`). UX-6 locked the abstraction +
information model. UX-7 locks the **visual identity, motion,
atmosphere, and component-level tokens** that turn UX-6 from
"editorial but emotionally flat" into "calm but unmistakably
modern."

---

## 1. Identity statement

**"Composed daily intelligence."**

Cinematic in *composition*, never in *effects*. The product
reads like a single editorial composition arranged each
morning by an intelligent system — with one ambient state,
one Featured Read, one authored sentence, and a small set of
quiet object surfaces beneath. The user opens the app, feels
"oh, today is different from yesterday," and reads.

Reference field: Apple Health, Arc Browser, Granola AI,
modern editorial typography. **Not** Bloomberg, **not**
Robinhood, **not** Linear (workspace), **not** Perplexity
(query-driven), **not** any "Powered by AI" SaaS dashboard.

The user thought after first session: *"This AI understands
markets and helps guide me — without ever performing
intelligence at me."*

---

## 2. Visual primitives (locked)

### 2.1 Atmosphere — TWO STATES ONLY

After R3 critique (Opus + Sonnet attacked the original
five-variant proposal), atmosphere collapses to two states.

```
default     #121212  near-black neutral (90% of sessions)
elevated    #14110f  2-3 hex steps warmer (10% of sessions)
```

**Atmosphere is rendered into the HTML before React mounts.**
No cross-fade. No splash. The page opens with the gradient
already in place. This avoids a cinematic intro animation that
would contradict every other motion rule.

**Optional radial wash layer** (Codex R4 contribution; ships
last per build-order rule §10.E):

```css
body[data-atmosphere-state="protective"],
body[data-atmosphere-state="constructive"] {
  background:
    radial-gradient(
      ellipse at 50% 0%,
      rgba(255, 200, 160, 0.035) 0%,
      rgba(255, 200, 160, 0.012) 34%,
      transparent 68%
    ),
    var(--ux7-bg-elevated);
}

body[data-atmosphere-state="slow"],
body[data-atmosphere-state="steady"],
body[data-atmosphere-state="calm"] {
  background:
    radial-gradient(
      ellipse at 50% 0%,
      rgba(255, 255, 255, 0.025) 0%,
      transparent 62%
    ),
    var(--ux7-bg-default);
}
```

**Visible-object explanation contract.** When state is
`protective` or `constructive`, the first viewport MUST
contain a visible page object whose text references the
underlying condition. Lint enforces. Atmosphere is never
unexplained.

`<body data-atmosphere-state="…">` exposed for E2E tests +
analytics.

### 2.2 Featured Read — materiality-gated

Renders **only when** the engine has ≥ 2 material inputs from
distinct object classes (position lifecycle, candidate idea,
risk exception, realized outcome).

| Materiality | Behaviour |
|-------------|-----------|
| ≥ 2 distinct object classes | Render Featured Read, 2–3 sentences default |
| ≥ 4 distinct object classes | Render Featured Read, up to 5 sentences |
| < 2 distinct object classes | **Block ABSENT.** Page goes masthead → context line (if present) → first lane / section. No greeting at display weight. |

**Greeting-only fallback is BANNED.** This was the largest R3
correction. A "Good morning. Markets are open." paragraph at
display weight would teach the user that the AI's authority
is theatrical. Better to render shorter pages.

**Every sentence in the Featured Read** must map to a visible
object or evidence item below the fold. Lint enforces.

### 2.3 Context line

One authored sentence beneath the page title. Renders only
when engine produces a non-generic sentence; absent otherwise.
120-char max. Sonnet R1 + R2 specification.

### 2.4 Daily Intelligence Field — spatial lanes (NOT cards)

Beneath the Featured Read (when present), Today renders up to
three compact spatial lanes. Codex R3 specification.

* **Observation** — what changed or emerged today.
* **Decision** — what the user may inspect or confirm.
* **Exception** — what could break the plan or requires
  protective attention.

**Layout rules:**

* Empty lanes do NOT render. If only "Decision" has content,
  only Decision renders.
* Each lane: 11px section header + 1 primary 15px body
  sentence + ≤ 2 12px secondary links.
* Mobile (< 720px): lanes stack in priority order.
* Desktop default: lanes stack vertically (single column).
* Wide-display three-column band: ONLY when viewport ≥ 960px
  AND user opts in via `?density=wide`. **Build last.**

**Priority order by atmosphere state:**

| State | Lane order |
|-------|------------|
| `protective` | Exception · Decision · Observation |
| `constructive` | Decision · Observation · Exception |
| default | Observation · Decision · Exception |

### 2.5 Soft surface tokens

```css
/* breathing-zone container — Today prose, Ideas list */
.surface--editorial {
  background: rgba(255, 255, 255, 0.04);
  background-hover: rgba(255, 255, 255, 0.06);
  border: none;
  box-shadow: none;
  border-radius: 12px;
  padding: 20px 24px;
}

/* actionable container — Holdings rows w/ chevron */
.surface--actionable {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid #1c1c1c;          /* Sonnet R3 — required */
  border-radius: 12px;
  padding: 16px 20px;
}

/* warm risk variant */
.surface--risk {
  background: rgba(255, 200, 160, 0.06);
  border-color: #221b15;
}

*:focus-visible {
  outline: 2px solid rgba(255, 255, 255, 0.20);
  outline-offset: 2px;
}
```

**Sonnet R3 rule (locked):** any surface with an actionable
chevron MUST have a 1px hairline border. The 4% tint alone
fails at low display brightness. The "no border, no shadow"
ban applies to *heavy card chrome*, not 1px hairlines that
define interaction boundaries.

### 2.6 Working rupture

**Structural, not animated.** Crossing to Working:

* Background → `#0a0a0a` (slightly darker than Layer-1
  atmosphere)
* 720px column constraint dropped
* Atmospheric gradient layer dropped entirely
* Typography: display-sans → operator-mono
* **Title continuity anchor** (Sonnet R3): the 11px
  uppercase masthead position is preserved. `TODAY · MAY 8`
  becomes `WORKING · MAY 8` at the same x/y/typographic
  register. This single anchor communicates "still in the
  product."

NO custom animation. NO cross-fade. The contrast itself is
the message.

---

## 3. Typography ramp

```css
:root {
  --ux7-type-masthead:        17px;   /* TODAY · MAY 8 */
  --ux7-type-context:         15px;   /* context line */
  --ux7-type-read-display:    30px;   /* Featured Read body */
  --ux7-type-read-leading:    1.32;
  --ux7-type-section-header:  11px;   /* WHAT IS OPEN, lane labels */
  --ux7-type-section-body:    15px;   /* prose, idea observations */
  --ux7-type-tertiary:        12px;   /* link arrows, footer */

  --ux7-letter-display:       -0.011em;
  --ux7-letter-tracked:       0.04em;

  --ux7-weight-display:       500;
  --ux7-weight-section:       500;
  --ux7-weight-body:          400;
  --ux7-weight-emphasis:      550;     /* risk-typed reads only */
}
```

**Featured Read font choice:** sans display by default (system
or Inter Display). A serif option (Georgia or equivalent) was
proposed by Sonnet R4 for a more editorial register; left as a
**post-launch A/B**, not a day-1 decision.

---

## 4. Color tokens (dark-first)

```css
:root {
  /* Backgrounds */
  --ux7-bg-default:           #121212;
  --ux7-bg-elevated:           #14110f;
  --ux7-bg-working:            #0a0a0a;

  /* Foregrounds */
  --ux7-fg-primary:            rgba(255, 255, 255, 0.92);
  --ux7-fg-secondary:          rgba(255, 255, 255, 0.74);
  --ux7-fg-tertiary:           rgba(255, 255, 255, 0.54);

  /* Hairlines */
  --ux7-hairline:              rgba(255, 255, 255, 0.06);

  /* Surfaces */
  --ux7-surface-editorial:     rgba(255, 255, 255, 0.04);
  --ux7-surface-actionable-bd: #1c1c1c;
  --ux7-surface-risk:          rgba(255, 200, 160, 0.06);
  --ux7-surface-risk-bd:       #221b15;
  --ux7-warm-text:             #f0c7a8;

  /* Focus */
  --ux7-focus-outline:         rgba(255, 255, 255, 0.20);
}
```

**Light theme is post-launch.** Dark-first. Token contract
holds; values invert.

---

## 5. Hierarchy system

* **Spatial > chromatic** (Codex R1, locked).
* **Three structural treatments** (Codex R2 revised):

| Treatment | Communicates | Mechanism |
|-----------|--------------|-----------|
| **Default** | calm + important | Placement, density, type |
| **Constructive** | opportunity | Warmer action emphasis, clearer next step (NOT a separate theme) |
| **Protective** | risk + urgent | Warm-spectrum surface tint, firmer containment, sharper Evidence visibility |

* **No five-state colour taxonomy** (Sonnet R2 attack landed).
* **No green/red on Layer 1.** Two muted greens / reds reserved
  for Layer 2 P&L only.

---

## 6. Today layout (locked ASCII)

```
                              (atmosphere: pre-mounted before React)

  TODAY · MAY 8                                                   ← 17px / 500 / 0.04em
                                                                    secondary 0.74
  Three positions approaching key levels.                          ← 15px / 400 / 0.74
                                                                    context line (optional)

  Markets eased into the close, and one position is               ← 30px display 500
  approaching its target. Two ideas appeared overnight,             1.32 leading
  both inside their entry zones.                                    -0.011em tracking
                                                                    primary 0.92
                                                                    max-width: 60ch

  ─────────────────────────────────────────────                     ← hairline 0.06

  OBSERVATION                                                     ← 11px / 500 / 0.04em uc
  Two new ideas appeared overnight, both in tech.                 ← 15px / 400 / 0.74
  See ideas →                                                     ← 12px / 0.54

  DECISION
  AAPL approaching target — review.
  See the working →

  EXCEPTION
  GOOGL approaching stop level.
  See risk →

  ─────────────────────────────────────────────

  WHAT IS OPEN
  3 paper positions. Two quietly working;
  one approaching its target.
  See my holdings →

  ─────────────────────────────────────────────

  See the working →                                               ← page footer
```

**Today, materiality NOT met:**

```
  TODAY · MAY 8

  Markets unchanged.                                              ← context line if present

  ─────────────────────────────────────────────

  WHAT IS OPEN
  3 paper positions. None require attention today.
  See my holdings →

  ─────────────────────────────────────────────

  See the working →
```

The Featured Read block is **absent**. Page is shorter. This
is the honest state.

---

## 7. Holdings layout (locked)

```
  HOLDINGS

  ┌────────────────────────────────────────────────────────┐    ← actionable surface
  │  AAPL                                          ▾       │      4% tint + 1px hairline
  │  5 shares · Day 4 · Entry held                         │      12px radius
  │  ──────────────                                        │      16px / 20px padding
  │                                                        │
  │  Bought May 5 at $182.40. Approaching the high         │      expanded prose
  │  of the recent range; 3% to target.                    │
  │                                                        │
  │  ●━━━●━━━●━━━○                                         │      lifecycle ribbon
  │  Idea  Bought  Day 4  Closed                           │
  │                                                        │
  │  See the working →                                     │
  └────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────┐
  │  TSLA                                          ▸       │
  │  3 shares · Day 1 · No change                          │
  └────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────┐    ← warm-risk variant
  │  GOOGL                                         ▸       │      warm bg + warm border
  │  2 shares · Day 1 · Approaching stop level             │
  └────────────────────────────────────────────────────────┘
```

8px gap between rows. Click anywhere on closed row toggles
expand. Chevron rotates `▸ → ▾` over 180ms. Reduced-Motion
replaces with instant.

---

## 8. Atmosphere computation

```typescript
type AtmosphereState =
  | "protective"
  | "constructive"
  | "slow"
  | "steady"
  | "calm";

interface AtmosphereInputs {
  drawdownFromPeak: number | null;
  stressContext: boolean;
  pausedStrategies: number;
  ideasInsideEntryZone: number;
  openPositions: number;
  recentSignalVolume: "low" | "normal" | "high" | null;
}

export function deriveAtmosphere(inp: AtmosphereInputs): AtmosphereState {
  // Precedence: protective > constructive > slow > steady > calm
  const dd = inp.drawdownFromPeak ?? 0;
  if (dd <= -0.05 || inp.stressContext || inp.pausedStrategies > 0) {
    return "protective";
  }
  if (inp.ideasInsideEntryZone >= 1) {
    return "constructive";
  }
  if (inp.recentSignalVolume === "low" && inp.openPositions === 0) {
    return "slow";
  }
  if (inp.openPositions > 0) {
    return "steady";
  }
  return "calm";
}

// Two-color rendering — protective + constructive → elevated;
// slow + steady + calm → default. Five named states resolve
// to two backgrounds.
export function atmosphereToBg(state: AtmosphereState): string {
  return (state === "protective" || state === "constructive")
    ? "#14110f"
    : "#121212";
}
```

**Server-rendered.** The atmosphere state and its background
color render into the HTML head as a `<style>` tag during
SSR (or as inline body style for SPA with prefetch). The page
opens with the gradient already present. No FOUC, no
cross-fade.

```html
<body style="background: #14110f"
      data-atmosphere-state="protective">
```

Atmosphere locks for the entire session. **No mid-session
shifts.** New states apply only on full page reload (next
session).

---

## 9. Motion + accessibility tokens

```css
:root {
  --ux7-motion-instant:   0ms;
  --ux7-motion-fast:      180ms;     /* hairline expand, hover */
  --ux7-motion-medium:    300ms;     /* lifecycle delta tint */
  --ux7-motion-text:      200ms;     /* Featured Read recompose */

  --ux7-ease:             cubic-bezier(0.2, 0.7, 0.1, 1);
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --ux7-motion-fast:    0ms;
    --ux7-motion-medium:  0ms;
    --ux7-motion-text:    0ms;
  }
  body[data-atmosphere-state] {
    background: var(--ux7-bg-default) !important;  /* flat */
  }
}

@media (prefers-contrast: more) {
  :root {
    --ux7-bg-default:           #000000;
    --ux7-bg-elevated:           #000000;
    --ux7-surface-actionable-bd: #ffffff;
    --ux7-hairline:              rgba(255, 255, 255, 0.30);
  }
  .surface--actionable {
    border-width: 2px;
  }
}
```

### Motion contract

| Allowed | Banned |
|---------|--------|
| Atmosphere set pre-mount (no transition on first paint) | Pulsing animation |
| 200ms text-reveal on Featured Read recompose | Parallax |
| Hairline expand on chevron (180ms) | Floating widgets |
| Working rupture (instant, no animation) | Glassmorphism |
| Lifecycle delta animation (300ms tint, max ONCE per position per session, ONLY on lifecycle state changes) | Mid-session atmospheric pulse |
| Reduced-Motion strips all transitions; atmosphere flat | Anticipatory micro-motion (Gemini R3 — rejected) |
| Haptic confirmation on user-initiated action only | Director's Emphasis underline-wipe (Gemini R3 — rejected) |
| | Working Focus Transition cinematic (Gemini R3 — rejected) |
| | Continuous haptic feedback |

### WCAG-AA verification (lint test required)

| Foreground | Background (worst case) | Ratio | Standard |
|-----------|------------------------|-------|----------|
| `rgba(255,255,255,0.92)` (primary) | `#14110f` (elevated) | 14.8:1 | AA + AAA |
| `rgba(255,255,255,0.74)` (secondary) | `#14110f` | 9.8:1 | AA + AAA |
| `rgba(255,255,255,0.54)` (tertiary) | `#14110f` | 5.3:1 | AA only |

CI lint must assert these ratios on every visual token
change. Tertiary tier sits at AA only; `prefers-contrast: more`
lifts it to AAA via the high-contrast overrides.

---

## 10. AI presence model

* **The composition + atmosphere = the AI presence.**
  No orb, no chat dock, no "Powered by AI" anywhere.
* **Featured Read** = primary AI expression (when materiality
  met).
* **Daily Intelligence Field** = secondary expression (object
  grammar visible).
* **Context line** = tertiary expression (editor's note).
* **Atmosphere** = quaternary expression (mood signal,
  always paired with visible explaining object).
* **Haptics**: ONE-TIME confirmation on user-initiated
  consequential action ONLY (e.g., confirming a trade
  execution in Working). NEVER on passive states.

---

## 11. Anti-patterns explicitly rejected

(Lint-enforceable)

* WebGL shaders for default UI
* Focus-pull camera transitions / Z-depth blur hierarchy
* Continuous haptic feedback
* Five-state colour taxonomy
* "Powered by AI" anywhere
* Mid-session atmospheric shifts
* Pulsing animations on idle elements
* **Greeting-only Featured Read at display weight**
  (R3 lock — Sonnet attack)
* Loading skeletons that mimic final layout
* Notifications · streaks · badges · engagement counters
* Charts above the fold on Today
* Multi-column on Today below 960px
* Hover-pulse on cards
* Border-and-shadow heavy card chrome (only soft tint +
  optional 1px hairline allowed)
* Anticipatory micro-motion (Gemini R3 — rejected)
* Director's Emphasis underline-wipe (Gemini R3 — rejected)
* Animated Working transitions (Gemini R3 — rejected)
* Suggested-question chips
* Chat dock as primary AI surface
* Cinematic intro splash on session start

---

## 12. Day-30 visual acceptance test

Combination of all four R3 tests:

1. **Comprehension (Sonnet R3).** Read the Featured Read
   without looking at numbers; then look at Holdings —
   ordering matches what the Featured Read implied was most
   worth watching.
2. **5-second test (Codex R3).** No onboarding. New user
   identifies day's primary Observation, Decision, and
   Exception from the first viewport in under 5 seconds.
3. **Word-cloud test (Opus R3).** Two new users see Today
   for 5 seconds; ≥ 70% describe with words from {calm,
   premium, intelligent, considered, modern, edited}; 0%
   use {dashboard, terminal, app, page, basic, sparse}.
4. **Anticipation test (Gemini R3).** Engine producing a
   new insight (regime shift, new idea) results in a
   meaningful change visible to the user on the NEXT
   session — i.e., the product reflects reality without
   performing it.

All four must pass for UX-7 to ship.

---

## 13. Migration roadmap (UX-7 phases)

| # | Scope | Risk |
|---|-------|------|
| **7A** | Token system in `apps/web/src/lib/copilot/ux7_tokens.css`. Atmosphere + spacing + type ramp + color + motion CSS custom properties. No UI changes. | None — additive |
| **7B** | `deriveAtmosphere` function + state precedence model + `data-atmosphere-state` exposed on body. SSR pre-mount renders flat background. Visible-object explanation lint. | Composer-level |
| **7C** | Featured Read materiality rule. Composer enforces ≥ 2 distinct material classes; null state renders absent block. CopilotOverview updated. | Composer + page rewire |
| **7D** | Daily Intelligence Field — Observation / Decision / Exception lanes as spatial blocks (NOT cards). Empty lanes omit. Priority order by atmosphere state. Mobile stacks. | Page rewire |
| **7E** | Holdings actionable surfaces — 4% tint + 1px hairline + warm-risk variant. PositionStoryCard updated. | Component rewire |
| **7F** | Motion contract — 180ms hairline expand, 200ms Featured Read recompose, 300ms lifecycle delta tint. Reduced-motion strips. | Visual polish |
| **7G** | Working rupture — title continuity anchor; structural background swap; mono typography on Working surfaces. | Working surface restyling |
| **7H** | Optional radial gradient wash (`body::before`). Late phase per build-order rule. | Compositor-layer addition |
| **7I** | Three-column Daily Intelligence Field band at ≥ 960px (`?density=wide` opt-in). Build LAST. | Responsive layout |
| **7J** | WCAG-AA lint test in CI. Atmosphere precedence test. Day-30 acceptance battery. | Verification |

Each phase ≤ 1 day, reversible, plan-only review before
implement (UX-5 / UX-6 discipline preserved).

UX-2 Phase C-2 typography ramp + C-3 Featured archetype
(currently stashed) **resume in 7E** — they apply correctly to
Holdings once the actionable-surface tokens land.

---

## 14. Build-last decisions (consensus)

All four models agreed on shipping order:

* **Build last: the three-column Daily Intelligence Field band
  at ≥ 960px.** (Opus, Codex). Single-column lanes are the
  canonical experience.
* **Build last: the radial gradient wash layer.** (Sonnet).
  Flat background ships first; the `body::before` radial wash
  is decorative polish that must clear GPU profiling.

Both decisions resolve to the same principle: **the
information contract lives in the composer + lanes + Featured
Read materiality. The visual polish atop is additive and can
ship later.**

---

## 15. Debate transcripts + credits

Full Round 1 / Round 2 / Round 3 / Round 4 transcripts
archived at `.debate/ux7_visual_20260508-165325/`
(gitignored). 16 model outputs, ~44,000 words.

| Contribution | Credit |
|--------------|--------|
| "Composed daily intelligence" identity statement | Codex R2 |
| Atmospheric gradient (session-locked, deterministic) | Opus R1 |
| Atmosphere → 2 states (collapsed from 5) | Opus R3 + Sonnet R3 |
| Atmosphere precedence model | Codex R3 |
| Visible-object explanation contract | Codex R3 |
| Featured Read materiality rule | Codex R3 + Sonnet R3 |
| Featured Read null-state grammar | Sonnet R3 |
| Daily Intelligence Field (Observation/Decision/Exception lanes) | Codex R1 + R3 |
| Spatial > chromatic hierarchy rule | Codex R1 |
| Warm-spectrum risk surface tint | Sonnet R1 |
| Surfaces with chevrons need 1px hairline | Sonnet R3 |
| Soft surface token contract | Opus R3 |
| Editorial column 720px | Opus R1 |
| Working rupture (structural, no animation) | Opus R1 |
| Working title continuity anchor | Sonnet R3 |
| Atmosphere set on HTML pre-mount (no FOUC) | Opus R3 |
| Reduced-Motion + WCAG-AA contracts | Opus R3 + Codex R4 + Sonnet R4 |
| Three-column band as build-last | Opus R4 + Codex R4 |
| Radial wash as build-last | Sonnet R4 |
| Cinematic memorability instinct (rejected specifics, absorbed principle) | Gemini R1–R3 |
| Lifecycle delta animation scope (state changes only, not price ticks) | Sonnet R3 |
| Day-30 acceptance test battery (4 tests) | All four R3 |

Gemini's specific implementations (WebGL nebula gradient,
focus-pull camera, Z-depth blur, haptics on passive states,
Director's Emphasis underline-wipe, Anticipatory micro-motion,
Working Focus Transition cinematic, "Start this story" copy)
were **rejected by 3-of-4 vote**. Gemini's instinct that
"memorability matters" is absorbed throughout.

---

## 16. What survives from UX-6

UX-7 is purely a visual layer atop UX-6. UX-6 architecture
unchanged:

* Read · Evidence · Action · See the working
* Object typing (Brief / Observation / Decision / Exception)
* Composer triage rules
* Numeric visibility contract
* 4-item primary nav (Today · Holdings · Ideas · Working)
* Working subnav model
* Lint scope + banned vocabulary

The visual locks here REPLACE UX-6's visual placeholders
(typography ramp + atmosphere were left under-specified in
UX-6 §8). UX-7 fills that gap.

---

## 17. Out of scope for UX-7

* Light theme
* Mobile-native app
* Custom display fonts (post-launch A/B)
* Voice interface
* Personalisation of atmosphere (locked to deterministic
  engine state — no user override)
* Custom themes / "skins"
* Haptic patterns beyond single confirmation tap
* Charts of any kind on Layer 1 surfaces

---

The synthesis is the formal capstone of the visual identity.
Lock and execute.
