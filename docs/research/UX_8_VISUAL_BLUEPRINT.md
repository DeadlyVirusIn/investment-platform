# UX-8 — Visual Blueprint Master

**Status:** master synthesis. Locked after a four-round
debate between Gemini 2.5 Pro · Codex · Claude Opus 4.7 ·
Claude Sonnet 4.6 (substituting for the requested Sonnet
4.7). Full transcripts archived at
`.debate/ux8_blueprint_20260508-195833/`.

UX-8 is the visual *imagination* companion to UX-6
(architecture) and UX-7 (visual identity). UX-7 produced
"composed daily intelligence" but the product remained
emotionally flat. UX-8 picks the **Portfolio Weather Room**
metaphor as the dominant visual identity and locks
component-level specs around it.

---

## 1. Identity statement

**"Portfolio Weather Room."**

A daily condition read on YOUR portfolio, expressed through
a controlled three-condition vocabulary, presented as a
dominant top surface that earns its space because the AI
has already done the analysis. The first thing the user
sees on opening is one word — `STABLE`, `PRESSURED`, or
`OPPORTUNISTIC` — followed by one editorial sentence
explaining what the AI sees.

The single biggest decision UX-8 makes that UX-7 forbade:
**the first viewport is allowed a dominant visual anchor.**
The Portfolio Condition Block IS the hero. UX-7's "no hero
panel" lock is intentionally broken.

---

## 2. Debate convergence

Four rounds. Twelve Today concepts proposed in R1 (3 per
model). R2 vote on the strongest concept:

| Concept | Author | Vote |
|---------|--------|------|
| **Portfolio Weather Room** | Codex | **3 votes** (Gemini, Codex, Sonnet) |
| Editorial Market Cover | Codex | 1 vote (Opus) |
| Pulse | Sonnet | 1 vote for Holdings (Opus) |
| All other 9 concepts | various | 0 votes |

Opus dissented and conceded. Vote stands. UX-8 adopts the
Weather Room as the visual chassis with R3-locked
refinements applied below.

---

## 3. R3 universal fixes (locked into synthesis)

* **Drop "Three Forces" hero construct** — all four models
  attacked the duplication of content between Forces inside
  the hero and Brief/Observation/Decision/Exception below.
  The BOD/E band is the SINGLE evidence layer.
* **Collapse seven conditions → three.** Final vocabulary:
  **`STABLE` · `PRESSURED` · `OPPORTUNISTIC`.** Seven was
  mood-ring territory; three is learnable in one session.
* **Drop AI-assigned Holdings role groups.** Replaced with
  deterministic lifecycle-based ordering (the lifecycle
  pill is the single property that determines order). AI
  assignment of "Core Compounder" / "Ballast" / etc. was
  recommendation engine smuggled in.
* **Pressure-band overlay = pure CSS, NOT WebGL.**
* **Source Serif 4** locked for the condition sentence
  ONLY.
* **Visible-condition-explanation contract**: PRESSURED
  condition sentence MUST contain a numeric anchor;
  OPPORTUNISTIC must name a source.

---

## 4. Visual primitives

### 4.1 Portfolio Condition Block (the hero)

Full-width container. 360px desktop, 280px mobile.
Background: graphite `#161616`. Pressure-band overlay
driven by condition state.

```css
:root {
  /* Hero geometry */
  --ux8-hero-height-desktop:   360px;
  --ux8-hero-height-mobile:    280px;
  --ux8-hero-padding:          32px 40px;
  --ux8-hero-padding-mobile:   24px 20px;

  /* Hero typography */
  --ux8-hero-date-size:        12px;
  --ux8-hero-date-tracking:    0.06em;
  --ux8-hero-date-color:       #888;

  --ux8-hero-condition-size:     11px;
  --ux8-hero-condition-tracking: 0.12em;
  --ux8-hero-condition-color:    #315F9E;  /* cobalt accent */

  --ux8-hero-sentence-size:    28px;
  --ux8-hero-sentence-leading: 1.32;
  --ux8-hero-sentence-color:   #F0EDE8;
  --ux8-hero-sentence-family:
    "Source Serif 4", "Source Serif Pro", Georgia, serif;
  --ux8-hero-sentence-weight:  400;

  --ux8-condition-bg:          #161616;
  --ux8-condition-band-color:  transparent;
  --ux8-condition-band-alpha:  0;
}

body[data-condition="PRESSURED"] {
  --ux8-condition-band-color: #4a2618;
  --ux8-condition-band-alpha: 0.06;
}
body[data-condition="OPPORTUNISTIC"] {
  --ux8-condition-band-color: #1c4a35;
  --ux8-condition-band-alpha: 0.04;
}
body[data-condition="STABLE"] {
  --ux8-condition-band-color: transparent;
  --ux8-condition-band-alpha: 0;
}

.condition-block {
  position: relative;
  height: var(--ux8-hero-height-desktop);
  padding: var(--ux8-hero-padding);
  background: var(--ux8-condition-bg);
  overflow: hidden;
}

.condition-block::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(
    180deg,
    transparent 0%,
    transparent 60%,
    var(--ux8-condition-band-color) 100%
  );
  opacity: var(--ux8-condition-band-alpha);
}

@media (max-width: 720px) {
  .condition-block {
    height: var(--ux8-hero-height-mobile);
    padding: var(--ux8-hero-padding-mobile);
  }
  .condition-sentence { font-size: 22px; }
}
```

### 4.2 Three-condition classifier (deterministic)

```typescript
type Condition = "OPPORTUNISTIC" | "PRESSURED" | "STABLE";

interface ConditionInputs {
  drawdownFromPeak: number | null;
  stressContext: boolean;
  pausedStrategies: number;
  ideasInsideEntryZone: number;
  recentSignalVolume: "low" | "normal" | "high";
}

export function deriveCondition(inp: ConditionInputs): Condition {
  // Precedence: PRESSURED > OPPORTUNISTIC > STABLE.
  const dd = inp.drawdownFromPeak ?? 0;
  if (dd <= -0.05 || inp.stressContext || inp.pausedStrategies > 0) {
    return "PRESSURED";
  }
  if (inp.ideasInsideEntryZone >= 2 && inp.recentSignalVolume !== "low") {
    return "OPPORTUNISTIC";
  }
  return "STABLE";
}

export function conditionToBg(cond: Condition): {
  bandColor: string;
  bandAlpha: number;
} {
  switch (cond) {
    case "PRESSURED":     return { bandColor: "#4a2618", bandAlpha: 0.06 };
    case "OPPORTUNISTIC": return { bandColor: "#1c4a35", bandAlpha: 0.04 };
    default:              return { bandColor: "transparent", bandAlpha: 0 };
  }
}
```

Server-rendered. `<body data-condition="PRESSURED">` set
pre-mount. NO mid-session shifts.

### 4.3 Visible-condition-explanation contract

When `data-condition="PRESSURED"`, the Condition Sentence
MUST substring-contain at least ONE numeric anchor (e.g.,
`7%`, `2 days`, `$120`).

When `data-condition="OPPORTUNISTIC"`, the sentence MUST
name at least ONE source (sector or symbol).

When `data-condition="STABLE"`, the sentence may be
observational without required anchors.

**Lint rule** in `apps/web/scripts/lint-condition-explainer.mjs`
(new): scans `condition_copy.ts` templates and rejects
PRESSURED templates without a `{numericAnchor}` placeholder
or OPPORTUNISTIC templates without a `{sourceName}`
placeholder. Build-time enforcement.

### 4.4 Single Read · Evidence · Action band (UX-6 contract preserved)

Beneath the Condition Block: Brief / Observation / Decision /
Exception spatial lanes per UX-6. Hairline-divided, NOT
cards. Empty lanes omit. Priority by condition state
(PRESSURED → Exception · Decision · Observation · Brief).

**No "Three Forces" duplicate construct.** R3 universal lock.

---

## 5. Today layout (locked ASCII)

```
+--------------------------------------------------------------+
|  ┌────────────────────────────────────────────────────────┐  |
|  │                                                         │  |
|  │  MAY 8                              [12px caps #888]    │  |
|  │                                                         │  |
|  │  PRESSURED                          [11px tracked uc]   │  |
|  │                                       cobalt #315F9E    │  |
|  │  Account is 7% below its peak this week.                │  |   ← 28px serif
|  │  One holding is approaching its stop level.             │  |     #F0EDE8
|  │                                                         │  |     numeric anchor REQ
|  │                                                         │  |
|  │  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   │  |   ← pressure-band
|  │  ░░░░░░░░ overlay (linear-gradient, alpha 0.06) ░░░░░░  │  |     gradient
|  └────────────────────────────────────────────────────────┘  |
|                                                              |
|  ────────────────────────────────────────                    |   ← hairline 0.06
|                                                              |
|  EXCEPTION                                                   |   ← protective day:
|  GOOGL approaching stop level.                               |     Exception first
|  See risk →                                                  |
|                                                              |
|  DECISION                                                    |
|  AAPL approaching target — review.                           |
|  See the working →                                           |
|                                                              |
|  OBSERVATION                                                 |
|  Three positions all in tech; rate sensitivity rising.       |
|  See ideas →                                                  |
|                                                              |
|  ────────────────────────────────────────                    |
|                                                              |
|  See the working →                                           |
+--------------------------------------------------------------+
```

---

## 6. Holdings layout (lifecycle-ordered)

```
+--------------------------------------------------------------+
|  HOLDINGS                                                    |
|                                                              |
|  Five positions. Tech-heavy.                                 |   ← summary line
|                                                              |
|  ────────────────────────────────                            |
|                                                              |
|  ╭──────────────────────────────────────────────────╮       |   ← warm tint
|  │  GOOGL                                ●━━●─ ─    │       |     risk-typed
|  │  Day 1 · approaching stop level       building     │       |     floats top
|  │  See the working →                                  │       |
|  ╰──────────────────────────────────────────────────╯       |
|                                                              |
|  ╭──────────────────────────────────────────────────╮       |
|  │  AAPL                                  ●━━●━━●━━●─ │       |   ← lifecycle pill
|  │  Day 4 · approaching target           mature      │       |     5 stages
|  │  Up 1.3% since you bought it on May 5.            │       |
|  ╰──────────────────────────────────────────────────╯       |
|                                                              |
|  ╭──────────────────────────────────────────────────╮       |
|  │  MSFT                                  ●━━●━━●─    │       |
|  │  Day 28 · within range                established   │       |
|  ╰──────────────────────────────────────────────────╯       |
|                                                              |
|  ╭──────────────────────────────────────────────────╮       |
|  │  TSLA                                  ●─        │       |
|  │  Day 1 · no movement                   new         │       |
|  ╰──────────────────────────────────────────────────╯       |
|                                                              |
+--------------------------------------------------------------+
```

### Lifecycle pill (5 stages, deterministic)

```typescript
type Lifecycle = "new" | "building" | "established"
                | "mature" | "aging-watch";

// Derived deterministically from daysHeld + portfolio_state.
// NO AI involvement. Pure observable state.
function deriveLifecycle(daysHeld: number, isNearTargetOrStop: boolean): Lifecycle {
  if (isNearTargetOrStop) return "aging-watch";
  if (daysHeld >= 30) return "mature";
  if (daysHeld >= 10) return "established";
  if (daysHeld >= 3)  return "building";
  return "new";
}
```

SVG rendered (not unicode):

```html
<svg class="lifecycle-pill" width="60" height="8" viewBox="0 0 60 8">
  <!-- 5 stages: 5 circles + 4 connecting lines -->
  <!-- Active stages full opacity; future stages 0.25 -->
</svg>
```

### Position sorting

```typescript
function sortHoldings(positions: Position[]): Position[] {
  return positions.sort((a, b) => {
    // 1. Risk-typed always first.
    if (a.isRiskTyped !== b.isRiskTyped) return a.isRiskTyped ? -1 : 1;
    // 2. Lifecycle order: aging-watch > mature > established > building > new.
    const order: Record<Lifecycle, number> = {
      "aging-watch": 5, mature: 4, established: 3, building: 2, new: 1,
    };
    if (order[a.lifecycle] !== order[b.lifecycle]) {
      return order[b.lifecycle] - order[a.lifecycle];
    }
    // 3. Tie-break by daysHeld descending.
    return b.daysHeld - a.daysHeld;
  });
}
```

NO AI involvement in ordering. Deterministic from
observable state.

### Risk-typed warm-tint variant (extends UX-7)

```css
.holding-row {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid #1c1c1c;
  border-radius: 12px;
  padding: 16px 20px;
  margin-bottom: 8px;
}

.holding-row[data-risk-typed="true"] {
  background: rgba(255, 200, 160, 0.06);
  border-color: #221b15;
}
```

---

## 7. Ideas layout (Watch Landscape)

```
+--------------------------------------------------------------+
|  IDEAS                                                       |
|                                                              |
|  Three ideas worth watching. Two are in the same theme.      |
|                                                              |
|  TOO EARLY        FORMING        NEAR        COOLING         |   ← zone axis labels
|  ───────────────────────────────────────────────────────     |     11px tracked
|                       ●          ●  ●                        |   ← idea dots
|                       NVDA       AAPL MSFT                   |     8px circles
|                                                              |
|  ─────────────────────────                                   |
|                                                              |
|  NEAR (2)                                                    |   ← zone header
|                                                              |
|  ╭──────────────────────────────────────────────────╮       |   ← full card
|  │  AAPL · Today                                     │       |
|  │  Entry zone reached. Reports earnings Thursday.   │       |
|  │  Decision window: through Wednesday close.         │       |
|  ╰──────────────────────────────────────────────────╯       |
|                                                              |
|  ╭──────────────────────────────────────────────────╮       |
|  │  MSFT · Today                                     │       |
|  │  Building a base near 50-day. Reports Wednesday.  │       |
|  ╰──────────────────────────────────────────────────╯       |
|                                                              |
|  FORMING (1)                                                 |   ← single line
|  NVDA — momentum easing into earnings.                       |     13px / 0.74
|                                                              |
|  TOO EARLY (3 ideas)                                          |   ← collapsed count
|                                                              |
|  ─────────────────────────                                   |
|                                                              |
|  The best new idea reduces your tech exposure.               |   ← AI footer
+--------------------------------------------------------------+
```

### Zone axis CSS

```css
.zone-axis {
  position: relative;
  margin: 24px 0;
  padding: 32px 0 24px;
  border-bottom: 1px solid var(--ux7-hairline);
}

.zone-axis-track {
  position: relative;
  height: 1px;
  background: var(--ux7-hairline);
}

.zone-dot {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ux7-fg-primary);
  transition: left 500ms cubic-bezier(0.2, 0.7, 0.1, 1);
}
```

### Dot positioning

```typescript
type Zone = "TOO_EARLY" | "FORMING" | "NEAR" | "COOLING";

function zonePositionPct(zone: Zone, intraZone: number): number {
  // Each zone occupies 25% of axis. intraZone in [0, 1].
  const base = { TOO_EARLY: 0, FORMING: 25, NEAR: 50, COOLING: 75 }[zone];
  return base + intraZone * 25;
}
```

| Zone | Treatment |
|------|-----------|
| **NEAR** | Full paragraph card (4% tint, 20/24 padding) |
| **FORMING** | Single line: `SYMBOL — observation.` 13px / 0.74 |
| **TOO EARLY** | Collapsed count: `TOO EARLY (N ideas)` 11px tracked |
| **COOLING** | Collapsed + dimmed 0.5 |

### AI footer note

The footer line links Ideas to Holdings ("the best new
idea reduces your current tech exposure"). Codex
contribution. Renders ONLY when the Ideas list contains at
least one idea outside the user's current sector
concentration.

---

## 8. Motion contract (5 motions only)

| Motion | Trigger | Timing | Notes |
|--------|---------|--------|-------|
| **Condition Block settle** | Page arrival (Today) | 200ms ease-out | Hero descends y-8 → y0; sentence fades 80ms after block settles |
| **Holdings row expand** | Click on row | 180ms ease-out | Adjacent rows dim slightly |
| **Lifecycle pill fill** | First landing per session | 150ms per stage | Pills fill left-to-right in order of position age. No further animation that session |
| **Idea zone-dot migration** | Idea moves between zones (between sessions) | 500ms ease-in-out | Dot slides along axis on first paint. No pulse, no flash |
| **Working rupture** | Navigate to Working | Instant | Per UX-7. Title continuity anchor preserved |

NO mid-session motion. NO pulsing on idle. NO ambient
animation on the hero.

`@media (prefers-reduced-motion: reduce)` strips all
transitions to 0ms.

---

## 9. Breaks from UX-7 (intentional)

| UX-7 lock | UX-8 break | Reason |
|-----------|-----------|--------|
| 2-state atmosphere on body | 3-condition vocabulary on hero | Body stays flat; condition lives on the hero block |
| "No dominant visual anchor" | Portfolio Condition Block IS the hero | The flat editorial format failed; needs a focal anchor |
| "No ambient color signal beyond gradient alpha shift" | Pressure-band overlay (CSS gradient on hero) | Concrete visual signal vs. invisible alpha shift |
| "No serif typography" | Source Serif 4 for condition sentence ONLY | Serif IS the AI's editorial voice for the hero sentence; sans everywhere else |

---

## 10. Keeps from UX-7

* All UX-6 architecture (R · E · A, object typing, banned
  vocab, materiality rule).
* No orb, no chat dock, no "Powered by AI."
* No green/red on Layer 1 (P/L only on expand).
* Working rupture as structural threshold.
* WCAG-AA + Reduced-Motion contracts.
* Soft surface tokens (4% tint, 12px radius, 1px hairline
  for actionable).
* The lint banned-vocab list.
* Visible-object explanation rule (extended to condition
  explanation contract).

---

## 11. Anti-patterns (extends UX-7)

* WebGL pressure-field rendering — banned.
* Glassmorphism / `backdrop-filter` on hero — banned.
* Continuous looping animation on the condition surface
  — banned.
* Mid-session live cross-fading prose — banned.
* Sound-matched micro-interactions — banned.
* Drag-and-drop holdings onto market factors — banned.
* AI-assigned position roles ("Core Compounder") —
  banned (R3 lock).
* Seven-state condition vocabulary — banned (R3 lock).
* Three Forces inside the hero — banned (R3 lock).
* All UX-7 anti-patterns inherited.

---

## 12. Migration roadmap (UX-8 phases)

| # | Scope | Risk |
|---|-------|------|
| **8A** | `condition.ts` deriveCondition + `condition_copy.ts` templates with `{numericAnchor}` and `{sourceName}` placeholders. Lint script for explanation contract. No UI. | None — additive |
| **8B** | `<body data-condition>` SSR pre-mount. CSS variables for pressure-band overlay. | Tokens-only |
| **8C** | `condition_block.tsx` component + Source Serif 4 self-hosted webfont + fallback chain. Today page rebuild around it. | Hero-level UI change |
| **8D** | Drop UX-7's "Three Forces" composer construct. BOD/E band remains the single object layer. | Composer change |
| **8E** | Holdings — `deriveLifecycle` + lifecycle SVG component + `sortHoldings` algorithm + risk-typed variant. | Holdings rewire |
| **8F** | Ideas — Watch Landscape with zone axis + dot positioning + per-zone typographic treatment + AI footer. | Ideas rewire |
| **8G** | Motion contract — 5 motions implemented. Reduced-motion stripping. | Visual polish |
| **8H** | Visible-condition-explanation lint test in CI. | Verification |

Each phase ≤ 1 day, reversible, plan-only review before
implement (UX-5 / UX-6 / UX-7 discipline preserved).

UX-2 Phase C-2 typography ramp + C-3 Featured archetype
(currently stashed) **resume in 8E** — they apply correctly
to Holdings once the lifecycle pill + actionable surface
tokens land.

---

## 13. Day-1 acceptance test

**Show two new users (one investing-experienced, one not)
the default `/overview` for 5 seconds with three different
fixtures (PRESSURED / STABLE / OPPORTUNISTIC). Hide the
screen. Ask: *"What do you think the system is telling you
right now?"***

Pass criteria:
* ≥ 70% of answers paraphrase the condition correctly
  ("your portfolio is under pressure," "things are calm,"
  "there's an opportunity").
* 0% use the words "dashboard," "graph," "chart," or
  "wireframe."
* The user can name the **specific reason** the condition is
  what it is (e.g., "because it said you're 7% below
  peak"). This proves the visible-condition-explanation
  contract is working.

If those three pass, the Portfolio Weather Room identity
is live.

---

## 14. Debate transcripts + credits

`.debate/ux8_blueprint_20260508-195833/` — 16 model outputs,
~70,000 words of visual design debate (heaviest of any UX
phase to date).

| Contribution | Credit |
|--------------|--------|
| **Portfolio Weather Room** chassis | Codex R1 + R2 |
| Three-condition vocabulary (collapsed from 7) | Opus R3 |
| Pressure-band overlay CSS spec | Opus R3 + R4 |
| Visible-condition-explanation contract | Opus R3 |
| Source Serif 4 for condition sentence | Sonnet R2 |
| Holdings lifecycle pill (5 stages) | Sonnet R1 |
| Drop AI-assigned role groups | Opus R3 + Codex R3 + Gemini R3 |
| Drop "Three Forces" duplication | All 4 R3 |
| Watch Landscape zone axis (Ideas) | Codex R2 + Sonnet R2 |
| AI footer note linking Ideas to Holdings | Codex R2 |
| Condition Block settle motion | Sonnet R2 |
| Zone-dot migration motion | Sonnet R2 |
| Cobalt accent `#315F9E` | Sonnet R2 |
| Mobile breakpoint hero shrink (360 → 280px) | Opus R4 |
| Sort-by-lifecycle algorithm | Opus R4 |
| Editorial Market Cover (alternate identity) | Codex R1, Opus R2 — **dissented direction** |
| Pulse Holdings (Sonnet R1) | adopted via lifecycle pill, full visualization deferred |

Gemini's R1 proposals (Instrument cockpit + Dialogue + Living
Brief mid-session rewrites + WebGL pressure field +
backdrop-filter glassmorphism + sound-matched
micro-interactions + drag-drop holdings) all rejected by
3-of-4 vote across rounds. Gemini's instinct that "the
product needs memorability" is absorbed throughout; specific
theatrical implementations rejected.

---

## 15. What survives from UX-6 + UX-7

* All UX-6 architecture (Layer 1/2/3, R · E · A · See the
  working, object typing, banned vocab, materiality rule).
* All UX-7 visual primitives (soft surfaces, hairline
  borders, motion contract base, WCAG-AA + Reduced-Motion
  contracts, Working rupture).
* The `data-condition` body attribute extends UX-7's
  `data-atmosphere-state`. The two attribute systems
  coexist; UX-8 takes precedence on Today, UX-7 governs
  Holdings/Ideas.

---

## 16. Out of scope for UX-8

* Crypto / forex / commodities visual treatment.
* Light-mode design.
* Mobile-native app.
* Voice interface.
* Custom display fonts beyond Source Serif 4 + Inter.
* Personalisation of condition vocabulary (locked to
  three states — no user override).
* Live cross-fading mid-session prose.
* Cinematic camera transitions.

---

The synthesis is the formal capstone of the visual
imagination work. Lock and execute.
