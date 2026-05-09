# Model: Sonnet 4.6
## Round: 1

## Position summary (300 words max)

The product feels like a dashboard because we built **a grid of containers on a black canvas**. That is the diagnosis. Linear, Arc, Perplexity, Autopilot do not look "premium" because their cards are prettier — they look premium because **the canvas itself is the protagonist** and components are guests on it. We inverted that: our canvas is dead (`#000` flat), our components are loud (bordered tiles, ALL CAPS labels, dense rows). Result: institutional tooling with a dark mode preset.

My position: the locks are 95% right and must NOT be reopened. The bear-case invariant, the 4 verbs, refuses-to-render schema, 13 trust safeguards — those are the spine. **What is wrong is the substrate underneath them.** UX-10/11 specified content. UX-12 must specify atmosphere, light, rhythm, and the ambient state of the canvas itself.

Specifically:

1. **Light is warm near-black `#0B0B0E`** with a single, slow page-level vertical luminance gradient (top 6% lighter) — not "atmospheric gradients" plural. One light source, like Linear or Arc.
2. **Motion budget extends to 360ms for orchestration**, holds at 220ms for components. "Cinematic" is *staggered*, not *longer*. Apple's iOS 17 modal curve `cubic-bezier(0.32, 0.72, 0, 1)`.
3. **AI presence via ambient time** — one line "as of 09:24, market 41 min in" that ticks, plus the page reflowing when conviction shifts. No orb. No chat. No theater.
4. **Tiles lose borders.** They become rows separated by light, not chrome.
5. **Type ramps to a 32px hero** — but the hero is page state ("3 to look at"), not the decision sentence. Decision sentence stays 16px and stays largest *inside* the tile. Hierarchy preserved, T5 resolved.

---

## D1. Visual philosophy (manifesto)

**The canvas is the product. Components are footprints on it.**

We've been designing tiles as if the tile were the unit of value. It is not. The unit of value is *the moment a user spends 6 seconds on this page and walks away calmer than they arrived*. That moment is atmosphere first, content second, chrome never.

UX-12 is the death of chrome. No card borders. No visible dividers. No drop shadows. The page is one warm-near-black surface (`#0B0B0E`) with content floating on it, separated by *space and luminance*, not edges.

The product is not a dashboard of recommendations. It is **a calm room that knows what time it is, what the market is doing, and what the user owns**, that quietly arranges three things in front of them. Closer to opening Arc on Sunday morning than Bloomberg on Monday. Linear's Inbox is the closest reference.

One sentence: **Calm canvas, confident type, invisible chrome, ambient time, present AI, zero theater.**

---

## D2. Emotional hierarchy

Eye moves in this order, every time, under 5 seconds:

1. **Page-level state** (top, 32px regular, `#E8E8EC` @ 70%) — "3 to look at" / "Quiet morning." Sets the room.
2. **First card's decision sentence** (16px medium, `#F4F4F7`) — first object in the room.
3. **Verb pill** (12px mono, monochrome) — inside the card, never first, never largest. Label, not flag.
4. **The why** (14px regular, `#A8A8AF`) — one line of evidence under the decision.
5. **Metadata** (11px, `#6B6B72`, tabular nums) — freshness, timestamp, tier dot.

Eye should *fall* down the page, not *scan* across it. Linear's Inbox: title carries you, metadata never grabs. **Hierarchy means most things are quiet so one thing can be loud.** Currently every tile is loud, so nothing is.

---

## D3. Light/depth strategy

The ban on glassmorphism and mood-rings stays. What survives:

**Tokens (proposed):**
- `--canvas`: `#0B0B0E` (warm near-black, ~2% red shift). Not `#000`. Black is brutal; near-black is calm.
- `--canvas-elevated`: `#101015` (drawer only).
- `--canvas-recessed`: `#08080B` (behind page header for the single luminance gradient).
- `--ink-hero`: `#F4F4F7`. `--ink-body`: `#A8A8AF`. `--ink-meta`: `#6B6B72`.
- `--hairline`: `rgba(255,255,255,0.04)` — used ONLY between major sections. NEVER as card borders.

**The single permitted gradient:** page-level vertical luminance from `#08080B` at top → `#0B0B0E` at 12% page height → solid thereafter. *One* light source, like sunlight from a window. Not on cards. Page-level only.

**Depth = luminance, not shadow.** A card is "elevated" because its background sits against a recessed strip. No `box-shadow`. macOS Sonoma sidebar does this — depth via tonal shift, never drop shadow.

**Hover/focus depth:** 1px inset `rgba(255,255,255,0.06)` ring on focus, no shadow, no scale, no translate. Linear's row hover.

This satisfies "light, atmospheric, soft depth" without violating anti-glassmorphism: (a) one light source, not many; (b) gradient is page-level not component-level; (c) no blur, no transparency stacking, no frosted glass.

---

## D4. Motion language

I argue: extend the budget *for orchestration*, hold it *for components*.

**Motion taxonomy:**
- **Component motion**: ≤220ms. Hover, focus, drawer-open, single-element transitions. Curve: `cubic-bezier(0.32, 0.72, 0, 1)` (iOS 17 modal). Tightens the existing 240ms cap.
- **Orchestration motion**: ≤360ms total, composed of staggered 180ms component animations with 30ms offsets. Used for: page load, conviction-shift reflow, drawer close. Same curve.
- **Ambient motion**: continuous, ≤0.4 px/s drift, only on the freshness line. Not animation — *time passing*.

**"Cinematic" is staggering, not duration.** Apple's iOS app launch is 320ms total but composed of 4 staggered 180ms transitions. Arc's tab-open is 240ms with URL bar, content, and chrome each animating on 30ms offsets. That reads as cinematic. A single 600ms ease-out reads as slow and casino-like.

**Homepage load choreography:** t=0 page-state header opacity 0→1 over 220ms; t=80ms card 1 fades + translates 4px upward over 180ms; t=120ms card 2; t=160ms card 3. Total 340ms. Reads as "the page is composing itself for me," not "loading."

**Hover/focus:** 140ms opacity shift on hairline, no transform, no shadow change. Linear, Arc do this. Bloomberg uses 0ms hard hover — that is *exactly* what makes Bloomberg feel like a tool.

**Banned (carry-forward):** pulse, breathe, glow, flash, count-up, confetti, parallax, blur transitions.

---

## D5. Color psychology

Position: **warmth lives in the canvas, not in semantic color.** Verb pills stay monochrome. No mood-ring. No "cool blue when AI calm, warm orange when alert." Theater.

**Warmth:** canvas (`#0B0B0E`, 2% red-shifted, barely perceptible, accumulates over 6 seconds); hero ink (`#F4F4F7`, slight warm cast, paper-like); the single page-level gradient.

**Coolness:** drawer surfaces (`#101015`, slightly cooler — subliminal "different mode" when drawer opens); metadata text (`#6B6B72`, neutral, recedes).

**Tier-vs-mood line:** Tier = monochrome dot. `Confirmed`=`#F4F4F7`, `Strong`=`#A8A8AF`, `Notable`=`#6B6B72`, `Watching`=`#48484E`. **Same hue, different luminance.** No tinting. Mood = canvas warmth. Static. Does NOT shift with AI confidence or time-of-day in v1.

**Saturation:** tighten the ≤50% ceiling to ≤30% inside a tile. The most saturated thing in the product is the verb pill, ~25%.

**This is Linear's color logic.** Linear has essentially no color outside priority dot and avatar — everything else is luminance. That is why it feels premium, not toy-like.

---

## D6. AI presence

The hardest. Bans are correct: no orb, no chat, no chips, no badge, no typing, no first-person. What's left:

1. **Ambient time as AI heartbeat.** One line top-right: "as of 09:24, market 41 min in." Updates every 60s. *Quietly being current* IS the presence. Perplexity does this with its "Pro Search" status line. 11px, `#6B6B72`, tabular nums, no icon.

2. **Reflow on conviction shift.** When conviction changes mid-session, cards re-order with 340ms staggered transition. **The AI does not announce; it demonstrates by acting.** Like Arc reordering pinned tabs — no banner, no toast.

3. **Page-state headline as AI voice.** "3 to look at today." "Nothing to act on." "Watching 2." Third-person, present, observational. Not "I see 3 things for you" (banned). Like Linear empty states or App Store "Today."

**Additional bans:** "AI thinking..." indicators, "Updating..." spinners, sparkles icons, beam-of-light animations, gradient AI badges.

**Principle:** AI presence = *the product behaving as if someone is paying attention*, not *the product telling the user it is paying attention*. Theater is the latter; presence is the former.

---

## D7. Interaction philosophy

**Premium = consequence-rich, friction-free, undo-cheap.**

Linear feels premium because: every keystroke does something (`c` create, `g i` go inbox); hovers reveal one info; click targets 32px+ even when text is 14px; undo is one keystroke; nothing modal that doesn't deserve to be.

Applied here:
- Card click → drawer open (locked).
- Card hover → 140ms hairline appears, freshness gets ~5% more luminance. Not a tooltip.
- Drawer dismissal: `Esc`, click outside, back — all preserve URL state.
- Keyboard nav: `j`/`k` between cards, `Enter` opens, `Esc` closes.

**Premium ≠ rich.** Premium = *every interaction has exactly one obvious meaning, executes in <100ms perceived, never punishes curiosity.* Bloomberg fails because right-click menus have 40 items. Arc succeeds because its command palette has 8. **Sound: zero.** Mobile: 1 light haptic on drawer open.

---

## D8. Homepage transformation

Before: dark grid of bordered tiles, ALL CAPS labels, filter chips, density toggles, ranking metadata. Boxy. Equal-weight. "12 things competing."

After:

```
   3 to look at                       as of 09:24, market 41 min in


   OPEN  AAPL
   Earnings beat, guidance raise, conviction Confirmed
   Bear case: iPhone 16 cycle softness already priced in
                                              ●●●●  fresh  09:18


   TRIM  NVDA
   Position +34% since OPEN, conviction Strong
   Bear case: AI capex digestion risk H2 2026
                                              ●●●○  fresh  09:12


   HOLD  MSFT
   Thesis intact, conviction Notable
   Bear case: Azure deceleration
                                              ●●○○  fresh  08:54


   Watching 2 more
```

Differences: no card borders; 96px between cards; 32px page-state headline at top; verb pill small and first inside card; decision sentence loudest in-card; bear case peer-level; "Watching 2 more" quiet handoff. Reads as **a page**, not **a dashboard**. The unit is the *line*.

---

## D9. Tile redesign philosophy

Schema locked (304×184, 5 rows, refuses-to-render). Treatment changes:

- **Remove the border.** Background = canvas. Separation = 96px vertical space.
- **No rounded corners on the tile.** Only on verb pill (4px) and conviction dot.
- **Promote decision sentence.** Only 16px medium element in the tile. Else ≤14px.
- **Demote verb pill.** 12px mono, 4px padding, monochrome, sits *before* ticker on same line.
- **Bear case peer-level with evidence.** Same size, same color, prefix "Bear case:".
- **Freshness:** 4 dots + timestamp, right-aligned, `#6B6B72`. Not a green/yellow indicator.
- **Hover:** hovered tile stays 100% opacity; *adjacent* tiles drop to 88%. Linear's row-hover focus. Draws the eye without animating the hovered element.

The tile becomes a *paragraph in a column*, not a *card in a grid*.

---

## D10. Typography redesign

Stack: **Inter for UI**, **Inter Display** for the 32px page state, **JetBrains Mono** for tabular metadata only (freshness timestamps, ticker counts).

| Token | Size | Weight | Tracking | Leading | Use |
|-------|------|--------|----------|---------|-----|
| `--type-page` | 32px | 400 | -0.02em | 1.15 | Page state ("3 to look at") |
| `--type-decision` | 16px | 500 | -0.005em | 1.4 | Decision sentence |
| `--type-body` | 14px | 400 | 0 | 1.5 | Evidence, bear case |
| `--type-meta` | 11px | 400 | 0.02em | 1.4 | Freshness, time, labels |
| `--type-pill` | 12px | 500 | 0.04em | 1 | Verb pill (mono) |

**Tracking:** negative on display (Apple SF), neutral on body, slightly positive on caps/meta.
**Weight:** 400 default, 500 emphasis. **No 600+ anywhere.** Bold is loud and dashboard-like.
**ALL CAPS banned** except the verb pill (4 chars max, reads as glyph).

**T5 resolution:** The decision sentence is **not** the largest element on the *page* — the page-state headline is. But the decision sentence **remains the largest element on the tile** (UX-11 L6 preserved). The new 32px hero lives at page level, not tile level. No conflict.

---

## D11. Spatial rhythm

**Scale (4px base):** `4, 8, 12, 16, 24, 32, 48, 64, 96, 128`.

**Page-level:** top padding 96px (was ~32px); side padding `clamp(24px, 6vw, 128px)`; section spacing 128px; between cards 96px (was ~16px).

**In-tile:** rows 12px apart; decision → evidence 16px; evidence → bear case 12px; bear case → metadata 24px.

**Why:** Linear's Inbox uses 24px between rows, ~96px between sections. Arc's sidebar 12px / 48px. Bloomberg 4px / 8px. The spacing scale *is* the difference between "tool" and "product." Currently we are at Bloomberg spacing on a Linear color palette. That is the precise diagnosis.

---

## D12. Consumer vs dashboard comparison (pixel level)

| Dimension | Bloomberg / current | Linear / Arc / proposed |
|-----------|---------------------|-------------------------|
| Canvas | `#000` flat | `#0B0B0E` warm, single luminance gradient |
| Component edges | Visible 1px borders | None — separation by 96px space |
| Type sizes | 8-14px, 6+ sizes | 11-32px, 5 sizes |
| Type weight range | 400-700, frequent bold | 400-500 only |
| Capitalization | ALL CAPS labels everywhere | None except 4-char pill |
| Color | Saturated red/green semantic | Monochrome ink, 4 luminance steps |
| Spacing scale | 4-16px | 12-128px |
| Hover | Instant border highlight | 140ms hairline + adjacent dim |
| Motion | None or hard | iOS 17 curve, staggered |
| Density | 12+ items competing | 3-5 items at human scale |
| Time presence | Static timestamp | Quietly ticking metadata |
| Empty state | Empty grid | "Nothing to act on" hero |

Pixel-level differentiator: **Linear has 5x our whitespace, half our type sizes, no semantic color, no borders, one light source.** Match those five and "premium consumer" appears automatically.

---

## D13. Before/after ASCII

**Before (`/overview?view=conviction`):**

```
┌─CONVICTION──────────────┬─FRESHNESS────────┬─FILTER───┐
│ ┌─────────┐┌─────────┐ │ ALL · NEW · ... │ OPEN · ...│
│ │ OPEN    ││ TRIM    │ │                  │           │
│ │ AAPL    ││ NVDA    │ │                  │           │
│ │ ████░ 4 ││ ███░░ 3 │ │                  │           │
│ │ +12.3%  ││ +34.1%  │ │                  │           │
│ │ EARNINGS││ +34% RUN│ │                  │           │
│ │ DETAILS ││ DETAILS │ │                  │           │
│ └─────────┘└─────────┘ │                  │           │
└─────────────────────────┴──────────────────┴───────────┘
```

**After (proposed UX-12):**

```


   3 to look at                       as of 09:24, market 41 min in



   OPEN  AAPL
   Earnings beat, guidance raise, conviction Confirmed
   Bear case: iPhone 16 cycle softness already priced in
                                              ●●●● fresh  09:18



   TRIM  NVDA
   Position +34% since OPEN, conviction Strong
   Bear case: AI capex digestion risk H2 2026
                                              ●●●○ fresh  09:12



   Watching 2 more


```

The "after" is mostly **air**. That is the entire point.

---

## D14. Screen-by-screen emotional flow

**Today, 09:24, 3 cards:** *Calm. Composed. The page knows what time it is.* Eye lands on "3 to look at," falls to AAPL, registers OPEN, reads the why, notes bear case, sees freshness. ~6 seconds. User feels: *oriented.*

**Drawer open on AAPL:** Canvas dims to 88%, drawer slides from right at 220ms iOS curve, lands at 88vh. Drawer is `#101015` — slightly cooler than canvas. User feels: *zoomed in, not interrupted.* Esc closes; URL preserves.

**Quiet day (no cards above threshold):** Page state reads "Nothing to act on. Watching 4." Below: 4 quiet rows in `#6B6B72`, no verb pills, no decision sentences — ticker + one-line context. User feels: *trust.* The product did not invent action to fill space.

**Conviction shift mid-session:** AAPL drops Confirmed → Strong. Dot glyph quietly animates `#F4F4F7` → `#A8A8AF` over 180ms. Card may reflow position with 340ms staggered orchestration. No banner. No toast. User feels: *the page is alive without being noisy.*

---

## D15. First 5-second analysis

**Sec 0:** Page paints. Warm near-black canvas, subtle vertical gradient. Pupils relax (warm vs. pure black). Eye lands top-left.

**Sec 1:** Reads "3 to look at." 32px regular Inter Display, low contrast. Registers *page state* + *count*. Tension: low (3, not 27).

**Sec 2:** Eye drops to first card. Sees "OPEN" pill, then "AAPL," then decision sentence. Registers *action* + *subject*.

**Sec 3:** Reads decision sentence. Registers *why*.

**Sec 4:** Catches "Bear case:" — registers *the system has self-doubt baked in*. Trust accrues.

**Sec 5:** Glances right, sees freshness + 09:18. Registers *currency*. Loop closes.

User feels: **oriented, calm, in control, slightly curious about card 2.**

Engineered with: low density (3 not 12), top whitespace (96px), page-state headline before any tile, bear case peer-level, ambient time top-right.

---

## D16. Why current implementation feels wrong

1. **Canvas is `#000` solid.** Pure black is brutal — same neural response as a TV that's off. Premium consumer apps use `#0B0B0E`–`#111114` warm near-black. Apple, Linear, Arc all do this.
2. **Tiles have visible borders.** Borders create "a grid of separate things." Removing borders and using whitespace as separator is the single biggest Linear-vs-Bloomberg pixel difference.
3. **ALL CAPS labels everywhere.** "EARNINGS BEAT," "DETAILS," "CONVICTION." ALL CAPS = enterprise dashboard. Sentence case = product.
4. **Type ramp too narrow.** Everything 11-14px. No editorial hero. Eye has nowhere to land first.
5. **Spacing is 8-16px.** Linear uses 24-96px. We are 5x too dense.
6. **No page-level state.** Product opens and immediately throws tiles. No "page is talking to you" moment.
7. **No ambient time.** Everything static. AI presence invisible.
8. **Hover states are CSS hard transitions.** Linear, Arc use 140ms easing on opacity. We use 0ms or 250ms scale. Both wrong.
9. **Verb pills compete with decision sentence.** Should be small and first; are large and demanding.
10. **No light source.** Pure black canvas with same-luminance components reads as flat. One subtle page-level gradient creates a sense of *room*.

All *substrate* issues, not *component* issues. Which is why adding more components won't fix it.

---

## D17. What makes it feel AI-native

Three things:

1. **Ambient currency.** An 11px `as of 09:24, market 41 min in` line that quietly updates. Not animated. Just *current*. That is presence.
2. **Page-state narration.** "3 to look at." "Nothing to act on." "Watching 2." The page narrates its own state in third-person, present-tense, observational voice. The AI without the AI badge.
3. **Reflow as proof.** When conviction shifts, cards re-order in 340ms staggered orchestration. The user sees the AI *act*, not the AI *announce*. The most powerful AI-native gesture available — at zero new components.

Combined with the warm-near-black canvas, removed borders, generous whitespace, 32px page hero, and iOS 17 motion curve, the product crosses from "dark dashboard" to "calm, attentive, AI-native morning room."

The locks all hold. The substrate changes. The feeling appears.
