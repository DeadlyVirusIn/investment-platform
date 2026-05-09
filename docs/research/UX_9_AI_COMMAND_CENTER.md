# UX-9 — AI Command Center Master

**Status:** master synthesis. Locked after a four-round
debate between Gemini 2.5 Pro · Codex · Claude Opus 4.7 ·
Claude Sonnet 4.6. Full transcripts archived at
`.debate/ux9_command_20260508-214023/`.

UX-9 is a complete redesign that **abandons** the editorial
direction of UX-7 / UX-8 / UX-8B. The PRESSURED proof
shipped in `fd3fd71` failed visual validation: the user
described it as *"a dramatic quote on a dark webpage."*
The whole composition model was wrong.

UX-9 picks **The Stream** — a vertical feed of intelligence
cards arranged by importance — as the visual identity.

---

## 1. Identity

**The Stream — vertical feed of intelligence cards.**

The page is composed of MULTIPLE intelligence objects with
visible motion — never a single sentence on a dark page.
Hero card sized larger than the rest. Cards in named fixed
slots; only contents update daily. Hero shape is
INVARIANT (single Portfolio Pulse type). Page contracts
gracefully when slots are empty.

Reference field: Perplexity Discover (modular intelligence
cards), Apple Stocks, modern AI copilots. NOT Bloomberg,
NOT Robinhood, NOT empty editorial pages.

The user opens the app and sees the AI **showing them
their portfolio**, not narrating it.

---

## 2. Debate convergence

Four rounds. Twelve AI Command Hero concepts in R1
(3 per model). R2 vote:

| Concept | Author | Vote |
|---------|--------|------|
| **The Stream** | Opus | **3 votes** (Gemini, Sonnet, Opus self-vote) |
| Living Portfolio Map | Codex | 1 vote (Codex with concessions to Stream) |
| All other 10 concepts | various | 0 votes |

R3 universal fixes:
* **Hero locked to ONE invariant type** (Portfolio Pulse) — Opus + Sonnet R3.
* **Weight bars are the day-1 visual proof** — 3-of-4 R3.
* **First-paint motion primitives, no live-tick dependency** — Opus R3 reality check.
* **Quiet-state two-variant repair** — Sonnet R3.
* **Per-card admin tooltip with data lineage** — Opus R3.

---

## 3. Hero card specification

### Tokens

```css
:root {
  /* Hero geometry */
  --ux9-hero-padding:        32px 40px;
  --ux9-hero-padding-mobile: 24px 20px;
  --ux9-hero-radius:         16px;
  --ux9-hero-bg:             rgba(255, 255, 255, 0.03);
  --ux9-hero-border:         1px solid rgba(255, 255, 255, 0.06);

  /* Bar geometry */
  --ux9-bar-track-height:    40px;
  --ux9-bar-fill-duration:   300ms;
  --ux9-bar-stagger-gap:     60ms;

  /* Type */
  --ux9-hero-header-size:    11px;
  --ux9-hero-header-track:   0.12em;
  --ux9-hero-header-color:   rgba(255, 255, 255, 0.55);
  --ux9-hero-delta-size:     17px;
  --ux9-hero-delta-color:    rgba(255, 255, 255, 0.92);
  --ux9-hero-read-size:      17px;
  --ux9-hero-read-leading:   1.5;
  --ux9-hero-read-color:     rgba(255, 255, 255, 0.92);

  /* Position hue palette (muted, max 0.5 saturation) */
  --ux9-pos-1: #7a8caf;   /* slate-blue */
  --ux9-pos-2: #8fa8a3;   /* sage */
  --ux9-pos-3: #b39a82;   /* tan */
  --ux9-pos-4: #9c8aa8;   /* dusty purple */
  --ux9-pos-5: #a39785;   /* warm grey */
  --ux9-pos-6: #6f8a9c;   /* steel */
  --ux9-pos-7: #b29a9a;   /* dusty rose */
  --ux9-pos-cash: rgba(255, 255, 255, 0.10);
}
```

### CSS (full)

```css
.ux9-hero {
  position: relative;
  background: var(--ux9-hero-bg);
  border: var(--ux9-hero-border);
  border-radius: var(--ux9-hero-radius);
  padding: var(--ux9-hero-padding);
}

.ux9-hero-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.ux9-hero-header-label {
  font-size: var(--ux9-hero-header-size);
  letter-spacing: var(--ux9-hero-header-track);
  text-transform: uppercase;
  color: var(--ux9-hero-header-color);
  font-weight: 500;
}

.ux9-hero-delta {
  font-size: var(--ux9-hero-delta-size);
  color: var(--ux9-hero-delta-color);
  font-variant-numeric: tabular-nums;
}

.ux9-hero-bars {
  display: flex;
  width: 100%;
  height: var(--ux9-bar-track-height);
  margin-top: 24px;
  border-radius: 4px;
  overflow: hidden;
}

.ux9-hero-bar {
  height: 100%;
  background: var(--bar-color);
  width: 0;
  transition: width var(--ux9-bar-fill-duration)
              cubic-bezier(0.2, 0.7, 0.1, 1);
  transition-delay: calc(var(--bar-index) * var(--ux9-bar-stagger-gap));
}

.ux9-hero.is-revealed .ux9-hero-bar {
  width: var(--bar-target-width);
}

.ux9-hero-bar-labels {
  display: flex;
  width: 100%;
  margin-top: 8px;
  font-size: 11px;
  letter-spacing: 0.04em;
  color: rgba(255, 255, 255, 0.55);
}

.ux9-hero-read {
  margin-top: 28px;
  font-size: var(--ux9-hero-read-size);
  line-height: var(--ux9-hero-read-leading);
  color: var(--ux9-hero-read-color);
  max-width: 60ch;
}

.ux9-hero-mini-objects {
  display: flex;
  gap: 16px;
  margin-top: 24px;
}

.ux9-hero-mini-object {
  flex: 1 1 0;
  padding: 12px 16px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.74);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

@media (prefers-reduced-motion: reduce) {
  .ux9-hero-bar { transition: none; width: var(--bar-target-width); }
}
```

### React shape

```tsx
// apps/web/src/components/copilot/HeroCard.tsx
export interface PositionWeight {
  symbol: string;
  weight: number;        // 0..1, must sum to 1
  hue: 1 | 2 | 3 | 4 | 5 | 6 | 7 | "cash";
}

export interface HeroCardProps {
  todayDeltaPct: number;
  positions: PositionWeight[];
  read: string;
  miniObjects: { label: string; value: string }[];
}

export default function HeroCard(p: HeroCardProps) {
  const ref = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const t = setTimeout(() => ref.current?.classList.add("is-revealed"), 80);
    return () => clearTimeout(t);
  }, []);
  return (
    <article ref={ref} className="ux9-hero" data-test="ux9-hero">
      <header className="ux9-hero-header">
        <span className="ux9-hero-header-label">PORTFOLIO PULSE</span>
        <span className="ux9-hero-delta">
          {p.todayDeltaPct >= 0 ? "↗" : "↘"}{" "}
          {(p.todayDeltaPct * 100).toFixed(1)}% today
        </span>
      </header>
      <div className="ux9-hero-bars" role="presentation">
        {p.positions.map((pos, i) => (
          <span
            key={pos.symbol}
            className="ux9-hero-bar"
            style={{
              "--bar-color": `var(--ux9-pos-${pos.hue})`,
              "--bar-target-width": `${(pos.weight * 100).toFixed(2)}%`,
              "--bar-index": i,
            } as React.CSSProperties}
            data-symbol={pos.symbol}
          />
        ))}
      </div>
      <p className="ux9-hero-read">{p.read}</p>
      {/* mini objects */}
    </article>
  );
}
```

### ASCII (rendered)

```
┌──────────────────────────────────────────────────────────┐
│  PORTFOLIO PULSE                          ↗ +0.8% today  │
│                                                          │
│  ████████████████████████████████░░░░░░░░░░░░░░          │
│  AAPL  MSFT NVDA GOOGL TSLA META cash                    │
│                                                          │
│  Tech-heavy day. NVDA carrying the move; one position    │
│  approaching its target.                                 │
│                                                          │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐      │
│  │ ●━●━●━●─    │ │ +1.3% AAPL   │ │ Day 4 target │      │
│  │ AAPL mature │ │ approaching  │ │ near         │      │
│  └──────────────┘ └──────────────┘ └──────────────┘      │
└──────────────────────────────────────────────────────────┘
```

---

## 4. Intelligence Grid — 6 named fixed slots

```
slot-1: OPPORTUNITY      slot-2: WHAT CHANGED
slot-3: WATCHLIST        slot-4: CATALYSTS THIS WEEK
slot-5: RISK              slot-6: YOUR DAY
```

Slot positions NEVER move. Contents update daily.
Quiet-day variants per slot (observational, NOT
reassurance prose):

| Slot | Active | Quiet variant |
|------|--------|---------------|
| OPPORTUNITY | "3 ideas worth watching" | "No new ideas today" |
| WHAT CHANGED | "Tech rotation accelerated" | "Today looks like yesterday" |
| WATCHLIST | "META warming since Tue" | "Watchlist quiet" |
| CATALYSTS THIS WEEK | "AAPL Thu, Fed Wed" | "No catalysts this week" |
| RISK | "Concentration: 64% tech" | "No new exposures" |
| YOUR DAY | "2 new ideas, 1 near target" | "Nothing pressing today" |

### Card CSS

```css
.ux9-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-top: 24px;
}

@media (max-width: 720px) {
  .ux9-grid { grid-template-columns: 1fr; }
}

.ux9-card {
  position: relative;
  padding: 20px 24px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 120px;
}

.ux9-card-header {
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.55);
  font-weight: 500;
}

.ux9-card-primary {
  font-size: 15px;
  color: rgba(255, 255, 255, 0.92);
  line-height: 1.4;
}

.ux9-card[data-quiet="true"] .ux9-card-primary {
  opacity: 0.55;
}

.ux9-card-sparkline {
  height: 32px;
  width: 80px;
  align-self: flex-start;
  opacity: 0.74;
}

/* State-change emphasis — left-edge bar fires once on
 * first paint when card content has changed since
 * lastSeenAt (stored localStorage) */
.ux9-card[data-changed="true"]::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0.5em;
  bottom: 0.5em;
  width: 2px;
  background: rgba(255, 200, 160, 0.74);
  animation: ux9-emphasis 300ms cubic-bezier(0.2, 0.7, 0.1, 1) both;
}

@keyframes ux9-emphasis {
  from { opacity: 0; transform: scaleY(0); }
  to   { opacity: 1; transform: scaleY(1); }
}

@media (prefers-reduced-motion: reduce) {
  .ux9-card[data-changed="true"]::before {
    animation: none; opacity: 1; transform: scaleY(1);
  }
}
```

### React shape

```tsx
type SlotName = "OPPORTUNITY" | "WHAT CHANGED" | "WATCHLIST"
              | "CATALYSTS THIS WEEK" | "RISK" | "YOUR DAY";

interface SlotData {
  primary: string;
  ai?: string;
  sparkline?: number[];
  isQuiet: boolean;
  isChanged: boolean;
}

const SLOT_ORDER: SlotName[] = [
  "OPPORTUNITY", "WHAT CHANGED",
  "WATCHLIST", "CATALYSTS THIS WEEK",
  "RISK", "YOUR DAY",
];

export default function IntelligenceGrid(
  { slots }: { slots: Record<SlotName, SlotData> },
) {
  return (
    <section className="ux9-grid" data-test="ux9-grid">
      {SLOT_ORDER.map((name) => {
        const d = slots[name];
        return (
          <article
            key={name}
            className="ux9-card"
            data-slot={name}
            data-quiet={d.isQuiet}
            data-changed={d.isChanged}
          >
            <header className="ux9-card-header">{name}</header>
            <p className="ux9-card-primary">{d.primary}</p>
            {d.sparkline && (
              <Sparkline points={d.sparkline} className="ux9-card-sparkline" />
            )}
            {d.ai && <p className="ux9-card-ai">{d.ai}</p>}
          </article>
        );
      })}
    </section>
  );
}
```

---

## 5. First-paint motion contract (5 motions, NO live-tick dependency)

| # | Motion | Timing | Trigger |
|---|--------|--------|---------|
| 1 | **Weight bars staggered fill** | 300ms ease-out, 60ms stagger per bar | First paint, ONCE |
| 2 | **Delta count-up** | 800ms ease-out, tabular nums | First paint, ONCE |
| 3 | **Sparkline draw-in** | 200ms left-to-right line draw | First paint, ONCE |
| 4 | **State-change emphasis** | 300ms scaleY entrance on left-edge bar | When card changed since `lastSeenAt`, ONCE |
| 5 | **Reduced-motion fallback** | 0ms — bars snap to width, delta jumps, sparkline complete, no emphasis | When `prefers-reduced-motion: reduce` |

NO mid-session motion. NO pulsing on idle. NO continuous
animation. NO live-WebSocket tick dependency.

**Frame-by-frame timeline:**

```
0ms     React hydration. DOM rendered. Bars at width 0.
80ms    .is-revealed added to .ux9-hero. CSS bar transitions fire.
        Bar 0 (no delay): fills 80ms-380ms.
        Bar 1: 140ms-440ms. ... Bar 6: 440ms-740ms.
200ms   Bar labels (AAPL/MSFT/...) fade in matching widths.
300ms   Delta count-up begins (JS rAF loop, 800ms ease-out).
740ms   All bars finished. Hero stable.
760ms   AI READ paragraph fades in (200ms).
960ms   Mini-objects fade in staggered 60ms each.
1100ms  Intelligence Grid cards fade in top-to-bottom 80ms each.
1500ms+ Page static. No further motion until interaction.
```

`prefers-reduced-motion: reduce` collapses all frames to
0ms — page paints final state immediately.

---

## 6. Per-page Stream variants

| Page | Variant |
|------|---------|
| **Today** (`/overview`) | Hero + 6-slot Intelligence Grid |
| **Holdings** (`/portfolio?view=brief`) | Position Pulse Stream — row card per position with sparkline + lifecycle pill (UX-8) + delta. Sorted by lifecycle. |
| **Ideas** (`/ideas`) | Opportunity Stream — top idea hero + secondary cards by zone (NEAR / FORMING) |
| **Options** (`/options`) | Strategy Stream — top option idea + payoff inline + position cards w/ theta/delta/DTE |
| **Risk** (`/risks`) | Threat Stream — risk vector hero + 4 secondary cards including Sonnet's Thermal-Map card showing 18 position bands |
| **Watchlist** | Watch Pulse Stream — most-warming hero + compact pulse cards |
| **Working** (`/overview?view=working`) | Preserved verbatim — Layer-3 escape hatch |

Working remains the inspectable engine room. The Stream
identity does NOT extend to Working.

---

## 7. Per-card admin tooltip

Activation: `Ctrl+Shift+A` toggles admin mode (stored in
sessionStorage, never persisted). When admin mode active,
hovering any card displays a tooltip anchored to the
card's right edge, ~360px wide.

```
┌─────────────────────────────────────┐
│  CARD: Hero Portfolio Pulse          │
│                                      │
│  RENDERED FROM:                      │
│    paper_position (5 rows)           │
│    paper_summary.daily_pnl           │
│                                      │
│  AI READ COMPOSED VIA:               │
│    overview_derive.deriveTodayLine() │
│    template: tech-heavy-day          │
│    triggers: 3-of-5 in tech sector   │
│                                      │
│  LAST UPDATE:                        │
│    paper_position: 02:30 UTC         │
│    summary: 14:26 UTC                │
│                                      │
│  See raw data →                      │
└─────────────────────────────────────┘
```

Card lineage shape:

```typescript
interface CardLineage {
  slot: string;
  renderedFrom: string[];
  composerTrigger?: string;
  template?: string;
  lastUpdate: Record<string, string>;  // sourceName → ISO
  rawDataLink: string;                  // /overview?view=working&focus=…
}
```

---

## 8. AI Presence mechanism

Three signals — none an orb, chat, or "Powered by AI":

* **Composed prose inside cards** (observational only;
  never first-person; never "AI says").
* **State-change emphasis** (the 2px left-edge bar fires
  on cards changed since `lastSeenAt` — the AI noticed).
* **Quiet-day collapse** (page is honest about silence;
  slot quiet variants use observational language).

NO orb. NO chat dock. NO "Powered by AI." NO suggested
questions. NO chat-trojan-horse "Ask" affordance.

---

## 9. Atmosphere — UX-8B failure correction

* DROP the editorial-column 720px constraint on Today.
* DROP Source Serif 4.
* DROP the heavy radial body gradient (UX-8B failure mode).
* Background = flat `#0F0F0F`. A subtle 0.04-alpha tint
  at the top is allowed for depth, but if removed the
  page reads identically.
* **The visual conviction lives in CARD COMPOSITION**, not
  in background atmosphere.

---

## 10. Breaks from UX-6 / UX-7 / UX-8 / UX-8B

* Editorial column 720px on Today — abandoned.
* "No charts above the fold" — abandoned (sparklines +
  weight bars return).
* Source Serif 4 — abandoned (sans throughout).
* Single-condition Hero — abandoned.
* Heavy radial gradient — abandoned (UX-8B failure).
* Editorial-page identity — abandoned for Stream.
* "No chips, badges, counters" — partially abandoned;
  numerical deltas with arrows allowed. Conviction
  percentages still banned.

---

## 11. Keeps from UX-6 / UX-7 / UX-8

* Working preserved verbatim.
* "See the working" link as Layer-3 escape.
* Banned-vocab list (signal, batch, regime, etc.).
* No chat / orb / "Powered by AI."
* Object typing inside cards.
* Reduced-Motion + WCAG-AA contracts.
* Holdings lifecycle pill (UX-8) preserved.

---

## 12. Anti-patterns explicitly REJECTED

* Cinematic editorial quote heroes (UX-8B failure).
* Static single-sentence heroes.
* Hero shape changing between sessions.
* Live mid-session card reorder.
* Pulsing animations on idle elements.
* Continuous looping animation.
* Glassmorphism / heavy backdrop-filter.
* WebGL pressure-fields.
* Live-WebSocket-tick dependency for day-1 alive feeling.
* "Powered by AI" copy anywhere.
* Suggested-question chips.
* Chat dock as primary AI surface.
* "Quiet" reassurance prose (Sonnet R3 — replaced with
  observational variants).

---

## 13. Day-1 visual proof

The hero card's position weight bars filling staggered on
first paint, with non-equal weight distribution showing
actual portfolio composition, paired with one
source-backed AI READ sentence below.

If a viewer at this stage sees the bars compose and
thinks *"the AI is showing me my portfolio,"* the Stream
identity is real — even without a single real-time tick.

---

## 14. Migration roadmap (UX-9 phases)

| # | Scope | Risk |
|---|-------|------|
| **9A** | `apps/web/src/lib/copilot/ux9_tokens.css` — base CSS variables + position-hue palette. `apps/web/src/components/copilot/HeroCard.tsx` — Hero card with weight bars + count-up + AI READ. | Token-only |
| **9B** | `IntelligenceGrid.tsx` — 6-slot grid with quiet/changed states. `Sparkline.tsx` — minimal SVG with line-draw entrance. | Component-level |
| **9C** | `hero_compose.ts` — pure composer that returns HeroCardProps from engine state. `grid_compose.ts` — same for IntelligenceGridProps. | Composer logic |
| **9D** | `CopilotOverview.tsx` — REPLACE existing render. Drop ConditionBlock + 6 prior overview blocks; add HeroCard + IntelligenceGrid. Revert UX-8B atmosphere CSS. | Visible cutover |
| **9E** | Per-card admin tooltip + `Ctrl+Shift+A` activation. | Admin overlay |
| **9F** | Per-page Stream variants — Holdings / Ideas / Options / Risk / Watchlist. | Per-page rebuild |
| **9G** | First-paint motion polish — lifecycle pill stagger, sparkline draw-in, state-change emphasis. | Visual polish |
| **9H** | Live-tick polish (post-launch) — WebSocket subscription for real-time bar tween. NOT day-1. | Future |

Each phase ≤ 1 day, reversible, plan-only review before
implement.

**9A + 9B + 9C + 9D = the day-1 ship.** Visible cutover
in 9D returns the page to a single coherent visual
identity. UX-8B's ConditionBlock is removed in the same
commit.

---

## 15. Debate transcripts + credits

`.debate/ux9_command_20260508-214023/` — 16 model outputs,
~80,000 words.

| Contribution | Credit |
|--------------|--------|
| **The Stream** chassis | Opus R1 |
| Weight bars on hero (live-data motion) | Opus R1 |
| Frozen-named-slot grid (R2 critical fix) | Sonnet R2 |
| First-paint motion primitives without live-tick | Opus R3 (reality check) |
| Quiet-state observational variants | Sonnet R3 |
| Hero locked to ONE invariant type | Opus R3 + Sonnet R3 |
| Per-card admin tooltip with data lineage | Opus R3 |
| Position hue palette (muted, max 0.5 saturation) | Opus R4 |
| Sonnet Thermal-Map as Risk-page secondary card | Opus R2 (concession) |
| Day-1 weight-bar test | All 4 R3 |
| Living Portfolio Map (rejected; arguments absorbed) | Codex R1 |
| Market Stream / Synthesis tag pattern (rejected) | Gemini R1 |
| Strategic Lens / Instrument cockpit (rejected) | Gemini R1 + Codex R1 |
| Cinematic editorial quote (8B-1 failure) | Opus R5 of UX-8 — superseded |

---

## 16. What survives from UX-6 / UX-7 / UX-8

* All UX-6 architecture (Layer 1/2/3, Read · Evidence ·
  Action · See the working, object typing, banned vocab).
* UX-7 motion contract base (data-bound only, no
  decoration).
* UX-7 reduced-motion + WCAG-AA contracts.
* UX-8 lifecycle pill on Holdings.
* The `data-condition` body attribute (kept for admin
  signal use only; no longer drives visible atmosphere).

---

## 17. Out of scope for UX-9

* Live-WebSocket price ticks (Phase 9H, post-launch).
* Light theme.
* Mobile-native app.
* Voice interface.
* Personalisation of slot order (locked frozen).
* Custom sparkline interaction (tap-to-zoom, etc.).
* Animated card transitions on data updates.

---

The synthesis is the formal capstone of the visual
imagination work. The Stream identity replaces every
prior visual direction. Engineering can begin Phase 9A
(tokens + Hero card component) on user signal.
