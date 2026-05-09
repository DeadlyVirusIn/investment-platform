# UX-8B — Visual Prototype Lock (Round 5 synthesis)

**Status:** visual prototype companion to
`UX_8_VISUAL_BLUEPRINT.md`. Locked after Round 5 of the
four-way visual debate (Gemini · Codex · Opus 4.7 · Sonnet
4.6). Round 5 was visual validation — proving the Portfolio
Weather Room emotionally, not refining its philosophy.

UX-8 (architecture) + UX-7 (visual identity) + UX-6
(abstraction) all stack underneath. This doc adds: the two
**bold moves** that push the product past tasteful-but-flat
into memorable-and-confident.

---

## 1. The two locked bold moves

After R5 produced four divergent "single bold moves" — each
model proposing one structural addition — synthesis adopts
**TWO** complementary moves and rejects two:

| Model | Bold move | Verdict |
|-------|-----------|---------|
| **Sonnet R5** | Full-bleed condition-responsive radial gradient on `body` | **ADOPTED** |
| **Opus R5** | 2px vertical accent bar beside the condition sentence | **ADOPTED** |
| **Codex R5** | Barometric Halo — 920×520 blurred state-colored ring escaping the block | **REJECTED** (heavy blur; glassmorphism-adjacent; conflicts with R3 ban on backdrop-filter) |
| **Gemini R5** | Generative Weatherline — continuously-animated SVG path in the hero | **REJECTED** (continuous animation banned in R3; reintroduces "AI thinking" theater) |

The two adopted moves are complementary:
* The **body gradient** establishes the atmosphere PERSISTS
  below the fold. The Weather Room is inhabitable, not just
  a header.
* The **accent bar** makes the AI's voice STRUCTURALLY
  present — one filled element on a hairlines-and-typography
  page IS the conviction.

Together they answer the user's seven R5 questions:
*does this feel intelligent / alive / premium / AI-guided?*
**Yes** — atmosphere surrounds the prose; the accent bar
is the AI's signature.

---

## 2. The full-bleed body gradient (Sonnet contribution)

```css
:root {
  --ux8-bg-base: #0F0F0F;       /* slightly darker than UX-7 #121212
                                   to make the gradient breathe */
}

body[data-condition="STABLE"] {
  background: var(--ux8-bg-base);
}

body[data-condition="PRESSURED"] {
  background:
    radial-gradient(
      ellipse 120% 40% at 50% 0%,
      rgba(74, 38, 24, 0.22) 0%,
      transparent 70%
    ),
    var(--ux8-bg-base);
}

body[data-condition="OPPORTUNISTIC"] {
  background:
    radial-gradient(
      ellipse 120% 40% at 50% 0%,
      rgba(28, 74, 53, 0.18) 0%,
      transparent 70%
    ),
    var(--ux8-bg-base);
}

@media (prefers-reduced-motion: reduce) {
  body[data-condition] {
    background: var(--ux8-bg-base);
  }
}

@media (prefers-contrast: more) {
  body[data-condition] {
    background: #000000;
  }
}
```

**Behavior:** an ellipse anchored at top-center bleeds the
condition's color across the entire viewport at low but
visible intensity. When the user scrolls below the
Condition Block into Evidence lanes and Holdings, they are
still inside the condition's atmosphere. The page does not
revert to a neutral dark background the moment the hero
scrolls out of view.

**Performance:** single CSS gradient. Zero JS. Zero
WebGL. Zero animation. Compositor-cheap.

**Reduced-motion:** strips to flat base. The gradient is
qualitative, not load-bearing.

**The gradient is set on the rendered HTML before React
mounts** (continues UX-7 / UX-8 SSR pre-mount pattern). No
FOUC. No cross-fade.

---

## 3. The 2px sentence accent bar (Opus contribution)

```css
.condition-sentence {
  position: relative;
  margin: 28px 0 0;
  padding-left: 16px;
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 32px;
  font-weight: 400;
  line-height: 1.32;
  color: #F0EDE8;
  max-width: 56ch;
  letter-spacing: -0.005em;
}

.condition-sentence::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0.25em;
  bottom: 0.25em;
  width: 2px;
  background: var(--ux8-condition-accent);
  transform-origin: top center;
  transform: scaleY(0);
  transition: transform 100ms cubic-bezier(0.2, 0.7, 0.1, 1);
}

.condition-block.is-revealed .condition-sentence::before {
  transform: scaleY(1);
}
```

State-driven accent color (paired with §2 above):

```css
body[data-condition="STABLE"] {
  --ux8-condition-accent: rgba(255, 255, 255, 0.20);  /* neutral */
}
body[data-condition="PRESSURED"] {
  --ux8-condition-accent: #c47a59;  /* warm rust */
}
body[data-condition="OPPORTUNISTIC"] {
  --ux8-condition-accent: #6db89a;  /* muted sage */
}
```

**Behavior:** a 2px vertical bar appears beside the
condition sentence, color-matched to the condition state.
The bar scales in (`scaleY 0 → 1`) over 100ms, anchored top,
**after** the sentence has settled — making the bar the
final element of the first-paint sequence. The user sees
the AI's voice arrive, then it underscores itself.

**Anti-pattern guard:** the bar must NEVER pulse, NEVER
animate after the initial scale-in, NEVER appear on hover.
It is structural. The entrance animation is the only
motion.

**Accessibility:** invisible to screen readers (correctly —
the condition is already announced via the label). High
contrast mode promotes the bar to currentColor.

---

## 4. First-paint sequence (R5 motion storyboard, locked)

```
Frame 1 (0ms):
  SSR delivers the page with body[data-condition] set.
  Body radial gradient already painted.
  Condition Block flat (hero gradient and sentence not yet rendered).

Frame 2 (40ms):
  React mounts. ConditionBlock JSX renders.
  Date "MAY 8" appears at opacity 0.

Frame 3 (140ms):
  Date fades to opacity 1 (linear, 100ms).
  Condition label "PRESSURED" appears at opacity 0.

Frame 4 (240ms):
  Condition label fades to opacity 1.
  Condition sentence appears at opacity 0, translateY +4px.
  Accent bar (.condition-sentence::before) hidden (scaleY 0).

Frame 5 (340ms):
  Condition sentence opacity 0 → 1, translateY +4px → 0,
  over 100ms ease-out. The serif lands.

Frame 6 (440ms):
  is-revealed class applied to .condition-block.
  Accent bar scaleY 0 → 1 over 100ms ease-out, anchored top.
  ★ This is the moment that says "the AI committed."

Frame 7 (440-540ms):
  Hairline below the Condition Block draws left-to-right
  (clip-path inset shrinks from inset(0 100% 0 0) to
  inset(0 0 0 0)) over 100ms.

Frame 8 (540ms onward):
  Evidence lanes appear in priority order. PRESSURED day:
  Exception first. Each lane fades in over 80ms with 60ms
  stagger.

Total: ~720ms. After 720ms the page is static.
```

`prefers-reduced-motion: reduce` collapses every frame to
0ms — the page paints the final state immediately.

---

## 5. Locked Today render (R5 fidelity)

```
+──────────────────────────────────────────────────────────────────────+
│  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │  ← body radial
│  ░░░░░░░ radial gradient ellipse 120% × 40% at 50% 0% ░░░░░░░░░░░░░  │     bleeds across
│  ░░░░░░ alpha 0.22 PRESSURED · alpha 0.18 OPPORTUNISTIC ░░░░░░░░░░░  │     entire viewport
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  CONDITION BLOCK — full-bleed h:380px desktop, 280px mobile     │  │
│  │  ════════════════════════════════════════════════════════════   │  │
│  │                                                                │  │
│  │  ┌────────────────────────────────┐                            │  │
│  │  │ Editorial column max 720px     │                            │  │
│  │  │                                 │                            │  │
│  │  │  MAY 8                          │  12px / 0.06em / #888      │  │
│  │  │                                 │                            │  │
│  │  │  PRESSURED                      │  11px / 0.12em / #c47a59   │  │
│  │  │                                 │  warm rust                  │  │
│  │  │                                 │                            │  │
│  │  │  ┃ Account is 7% below          │  32px Source Serif 4       │  │
│  │  │  ┃ its peak this week.          │  weight 400, leading 1.32  │  │
│  │  │  ┃ One holding is approaching   │  color #F0EDE8             │  │
│  │  │  ┃ its stop level.              │  ┃ = 2px accent bar        │  │
│  │  │                                 │     warm rust, scaleY in   │  │
│  │  └────────────────────────────────┘                            │  │
│  │                                                                │  │
│  │  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │  │
│  │  ░░░░░░ pressure-band overlay alpha 0.08 (lifted from R4) ░░░  │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ──────────────────────────────────────────────────────              │  hairline
│                                                                      │
│        EXCEPTION                                                     │
│        GOOGL approaching stop level.                                 │
│        See risk →                                                    │
│                                                                      │
│        DECISION                                                      │
│        AAPL approaching target — review.                             │
│        See the working →                                             │
│                                                                      │
│        OBSERVATION                                                   │
│        Three positions all in tech; rate sensitivity rising.         │
│        See ideas →                                                   │
│                                                                      │
│  ──────────────────────────────────────────────────────              │
│                                                                      │
│        See the working →                                             │
│                                                                      │
│  (atmosphere from body radial continues to bleed faintly             │
│   even down here at the page footer — Sonnet R5 contribution)        │
+──────────────────────────────────────────────────────────────────────+
```

---

## 6. React component shape (production-ready)

```tsx
// apps/web/src/pages/today/TodayPage.tsx
import { useEffect, useRef } from "react";
import { ConditionBlock } from "@/components/copilot/ConditionBlock";
import { EvidenceLane } from "@/components/copilot/EvidenceLane";
import { TodayFooter } from "@/components/copilot/TodayFooter";
import type { Condition } from "@/lib/copilot/condition";

interface TodayPageProps {
  condition: Condition;
  date: string;
  conditionSentence: string;
  exception?: string;
  decision?: string;
  observation?: string;
}

export default function TodayPage(props: TodayPageProps) {
  // Set the body data-condition on mount; SSR may have set it
  // already; this keeps client-side reactive when data updates.
  useEffect(() => {
    document.body.dataset.condition = props.condition;
    return () => { delete document.body.dataset.condition; };
  }, [props.condition]);

  return (
    <article className="today-page" data-test="today-page">
      <ConditionBlock
        date={props.date}
        condition={props.condition}
        sentence={props.conditionSentence}
      />
      <div className="today-evidence-column">
        <hr className="page-hairline" aria-hidden="true" />
        <EvidenceLane lanes={[
          props.exception   && {
            kind: "Exception",   text: props.exception,
            link: "/risk", linkText: "See risk",
          },
          props.decision    && {
            kind: "Decision",    text: props.decision,
            link: "/overview?view=working",
            linkText: "See the working",
          },
          props.observation && {
            kind: "Observation", text: props.observation,
            link: "/ideas", linkText: "See ideas",
          },
        ].filter(Boolean) as LaneItem[]} />
        <hr className="page-hairline" aria-hidden="true" />
        <TodayFooter />
      </div>
    </article>
  );
}

// apps/web/src/components/copilot/ConditionBlock.tsx
import { useEffect, useRef } from "react";

export function ConditionBlock({ date, condition, sentence }: ConditionBlockProps) {
  const ref = useRef<HTMLElement>(null);
  // Trigger the accent-bar scaleY animation ~440ms after mount.
  useEffect(() => {
    if (!ref.current) return;
    const t = setTimeout(() => ref.current?.classList.add("is-revealed"), 440);
    return () => clearTimeout(t);
  }, []);

  return (
    <header
      ref={ref}
      className="condition-block"
      data-test="condition-block"
      data-source={`condition:${condition},date:${date}`}
    >
      <div className="condition-column">
        <p className="condition-date">{date}</p>
        <p className="condition-label">{condition}</p>
        <h1 className="condition-sentence">{sentence}</h1>
      </div>
    </header>
  );
}
```

The `is-revealed` className is the single trigger for the
2px accent bar's scale-in. Reduced-motion CSS overrides
`transition` to `0ms` so the bar appears instantly.

---

## 7. Three-state CSS lock (locked, complete)

```css
:root {
  /* Geometry */
  --ux8-hero-height-desktop: 380px;
  --ux8-hero-height-mobile:  280px;
  --ux8-hero-padding:        32px 40px;
  --ux8-hero-padding-mobile: 24px 20px;

  /* Base */
  --ux8-bg-base:             #0F0F0F;

  /* Type */
  --ux8-hero-date-size:        12px;
  --ux8-hero-date-tracking:    0.06em;
  --ux8-hero-date-color:       #888;
  --ux8-hero-condition-size:     11px;
  --ux8-hero-condition-tracking: 0.12em;
  --ux8-hero-sentence-size:    32px;
  --ux8-hero-sentence-leading: 1.32;
  --ux8-hero-sentence-color:   #F0EDE8;
  --ux8-hero-sentence-family:  "Source Serif 4", Georgia, serif;
  --ux8-hero-sentence-weight:  400;
  --ux8-hero-sentence-tracking: -0.005em;
}

/* STABLE — zero atmosphere shift */
body[data-condition="STABLE"] {
  background: var(--ux8-bg-base);
  --ux8-condition-accent:        rgba(255, 255, 255, 0.20);
  --ux8-condition-band-color:    transparent;
  --ux8-condition-band-alpha:    0;
  --ux8-hero-sentence-weight-state: 400;
}

/* PRESSURED — warm rust, body bleeds */
body[data-condition="PRESSURED"] {
  background:
    radial-gradient(
      ellipse 120% 40% at 50% 0%,
      rgba(74, 38, 24, 0.22) 0%,
      transparent 70%
    ),
    var(--ux8-bg-base);
  --ux8-condition-accent:        #c47a59;
  --ux8-condition-band-color:    #4a2618;
  --ux8-condition-band-alpha:    0.08;
  --ux8-hero-sentence-weight-state: 450;  /* half-step heavier */
}

/* OPPORTUNISTIC — sage, body bleeds */
body[data-condition="OPPORTUNISTIC"] {
  background:
    radial-gradient(
      ellipse 120% 40% at 50% 0%,
      rgba(28, 74, 53, 0.18) 0%,
      transparent 70%
    ),
    var(--ux8-bg-base);
  --ux8-condition-accent:        #6db89a;
  --ux8-condition-band-color:    #1c4a35;
  --ux8-condition-band-alpha:    0.05;
  --ux8-hero-sentence-weight-state: 400;
}

/* Reduced motion strips atmosphere + animations */
@media (prefers-reduced-motion: reduce) {
  body[data-condition] {
    background: var(--ux8-bg-base) !important;
  }
  .condition-block::after { display: none; }
  .condition-sentence::before { transform: scaleY(1) !important; transition: none !important; }
}

/* High contrast — maximum readability */
@media (prefers-contrast: more) {
  body[data-condition] {
    background: #000000 !important;
  }
  .condition-sentence::before {
    background: currentColor;
    width: 3px;
  }
}
```

---

## 8. Implementation phasing (R5-locked)

8 hours is the user's R5 phrasing — the single visual
moment to prototype FIRST.

### Phase 8B-1 — the 8-hour proof (PRESSURED hero only)

Goal: prove the visual identity is real before any other
component is built.

* Add `condition.ts` with 3-state classifier.
* Add `<body data-condition>` SSR pre-mount.
* Build `<ConditionBlock>` with the 2px accent bar +
  scaleY entrance.
* Self-host Source Serif 4 with Georgia fallback.
* Render Today with ONLY the Condition Block (no Evidence
  lanes yet, no footer, no Holdings, no Ideas).
* Test the PRESSURED state with sample content: *"Account
  is 7% below its peak this week. One holding is
  approaching its stop level."*

If a viewer at this stage thinks "this looks like the
future of investing," UX-8B is validated and the rest of
the components ship. Otherwise, hold and revisit.

### Phase 8B-2 — extend to STABLE + OPPORTUNISTIC

Add the other two condition variants. Verify each renders
correctly and the body gradient + accent bar swap with the
condition-state attribute.

### Phase 8B-3 — Evidence lane + footer

Below the Condition Block, render the BOD/E lanes + footer
per UX-8 §5.

### Phase 8B-4 — Holdings + Ideas

Build out the lifecycle pill + sortHoldings + Watch
Landscape per UX-8 §6 + §7.

### Phase 8B-5 — Motion polish

The 5 motions from UX-8 §8 + the new accent-bar entrance
from §3 above.

### Phase 8B-6 — Reduced-motion + WCAG-AA

Verify accessibility contracts. Lint test for
condition-explanation contract.

---

## 9. Day-1 acceptance test (extends UX-8)

Show the PRESSURED hero (alone) for 5 seconds to two
viewers. Pass criteria:

1. Both viewers identify the condition without prompting
   ("the system is telling me my portfolio is under
   pressure").
2. Both viewers can name the **specific reason** ("because
   it said I'm 7% below peak").
3. Neither viewer uses the words "dashboard," "chart," or
   "graph."
4. **NEW (UX-8B):** at least one viewer mentions a visual
   element specifically — the bar, the warmth, the serif,
   the bleed. This proves the visual identity registered
   beyond the copy.

If criterion 4 fails, the visual moves were too quiet. Lift
the body gradient alpha (0.22 → 0.28) and the
pressure-band alpha (0.08 → 0.10) and re-test.

---

## 10. What was rejected from R5

* **Gemini's Generative Weatherline** — animated SVG path
  driven by market volatility. Continuously animates in the
  hero. Reintroduces the "AI thinking" pulse banned in R3.
  REJECTED.
* **Codex's Barometric Halo** — 920×520 blurred ring with
  42px blur escaping the Condition Block. Glassmorphism-
  adjacent; backdrop-filter explicitly banned in R3. Heavy
  compositor cost. REJECTED.

The user's "premium ≠ faint" warning was honored without
crossing into theatrical territory. The two adopted moves
are the maximum boldness the synthesis can absorb without
breaking R3 locks.

---

## 11. Debate transcripts + credits

`.debate/ux8_blueprint_20260508-195833/round5/` — 4 model
outputs, ~2,750 lines.

| Contribution | Credit |
|--------------|--------|
| Full-bleed body radial gradient | Sonnet R5 |
| 2px sentence accent bar | Opus R5 |
| Frame-by-frame motion storyboard | Opus R5 + Sonnet R5 |
| Three-state CSS lock | Opus R5 + Sonnet R5 |
| Half-step sentence weight on PRESSURED | Opus R5 |
| Day-1 acceptance test criterion 4 | Opus R5 |
| 8-hour first-prototype priority | Opus R5 |
| Generative Weatherline (rejected) | Gemini R5 |
| Barometric Halo (rejected) | Codex R5 |

Total UX-8 debate: 5 rounds × 4 models = 20 model outputs,
~75,000 words. The heaviest visual debate of any UX phase.

---

## 12. Master plan stack (current state)

* **UX-2 / UX-3 / UX-4 / UX-5** — implementation phases
  (Brief view, copilot primitives, Today scaffolding).
  Shipped to `phase-1/ledger`.
* **UX-6** — abstraction architecture. Locked.
* **UX-7** — visual identity (atmosphere, motion, soft
  surfaces). Locked.
* **UX-8** — Portfolio Weather Room visual blueprint.
  Locked.
* **UX-8B** (this doc) — visual prototype lock with the
  two bold moves. Locked.

Each subsequent phase is reversible, plan-only review
before implement, ≤ 1 day per commit.

The product visual identity is now fully specified.
Engineering can begin Phase 8B-1 (the 8-hour proof) on
your signal.
