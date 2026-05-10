# Model: Claude Opus 4.7
## Round: 1

## Position summary (300 words max)

The user's "operating system" framing is the right metaphor and the wrong reference class. **macOS is not Bloomberg-with-better-typography; macOS is a SPATIAL persistent state.** The Finder window the user closed yesterday is in the same place tomorrow. The Dock is in the same position. Mission Control rearranges the same spaces in predictable ways. **An OS feels alive because the user has memory of it.** A dashboard feels dead because the user has no memory of it.

UX-13's thesis: **the page must persist between sessions.** Not in data — in *spatial composition*. The user's hero tile from yesterday is in the same position today, even if the underlying ticker changed. The watchlist sits in the same lower-right quadrant. The ambient timestamp is in the same upper-right corner. After a week of opens, the user has muscle memory of WHERE things live. That muscle memory IS the OS feeling.

Within that persistent spatial frame, the *content* changes daily — ONE hero tile dominates today's stage, occupying ~60% of the first viewport. Subordinates compose around it asymmetrically based on relationship to hero (sector cluster left, opposing thesis right, watchlist below). The composition is determined by content but the SLOTS are persistent.

This single inversion fixes most user complaints simultaneously:

- **Asymmetric composition** — slots have unequal sizes by design (hero is 2-col-span, sector cluster is 1-col-span at half-height, etc.)
- **Visual gravity** — hero slot's persistent position trains the eye over weeks
- **Living environment** — the page changes content daily but FEELS the same, like opening macOS
- **Habit-forming** — opening becomes ritual because the room is familiar
- **Premium** — Linear/Arc/Apple all rely on persistent spatial layouts

If the page rearranges itself daily based on data, it's a dashboard. If the page is the same room with new contents, it's an OS.

## D1. Visual philosophy evolution (UX-12 → UX-13)

UX-12: editorial cockpit. Static composition. Magazine page.

UX-13: **persistent spatial OS.** The page is a *room you walk into the same way every morning.* The room has a fixed layout — hero in the center, sector cluster to the left, watchlist to the right, ambient time top-right corner. Each surface has a persistent purpose. What changes daily is the *content* in each surface. Like macOS Finder windows: same chrome, new files.

Reference shift:
- UX-12 referenced FT.com + Linear + Apollo Mission Control (editorial flat composition)
- UX-13 references **macOS Finder + iOS Home Screen + Arc Spaces** (persistent spatial state)

**Manifesto sentence:** The page is the same room, with new contents.

## D2. Homepage recomposition

Persistent slots, asymmetric layout. Specific:

```
══════════════════════════════════════════════════════════════
                                          as of 09:24, market 41 min in   ← persistent slot: ambient time, top-right
3 to look at                                                              ← persistent slot: page state, top-left

                  The market is narrow today;                              ← persistent slot: posture sentence, center top
                  conviction is concentrated in two names.                  (36px Source Serif 4)

═════════════════════════════ stage / shop hard cut ═══════════
                                                                            
┌────────────────────────────────────────┐  ┌──────────────┐               ← LAYOUT GRID: 8 cols
│                                        │  │              │
│   HERO SLOT (cols 1-5, ~60% width)     │  │  WATCHLIST   │  ← persistent slot: watchlist, right column
│                                        │  │  (cols 7-8)  │
│   Today's content: NVDA conviction     │  │              │     content: 3-5 names
│                                        │  │  · AAPL ←   │
│   OPEN  ●●●●  Confirmed · 14h          │  │    near $172│
│   NVDA · Semis cycle continuation      │  │  · TSM     │
│   Add through $172 while data-center   │  │    warming   │
│   margin expansion holds.              │  │  · COST    │
│   Bull · capex +22% YoY                │  │    slowing   │
│   Bear · hyperscaler rollover risk     │  │              │
│   Invalid < $158 · Horizon ~6w         │  │              │
│                                        │  │              │
└────────────────────────────────────────┘  └──────────────┘
                                                                           ← 32px gap (vertical)
┌──────────────┐  ┌──────────────┐         ┌──────────────────┐
│ TRIM TSLA    │  │ HOLD MSFT    │         │ MARKET CONTEXT   │            ← persistent slot: market context, right
│ (cols 1-2)   │  │ (cols 3-4)   │         │ (cols 6-8)        │              content: regime + macro one-liner
│ ...          │  │ ...          │         │ "Risk-on tape;   │
│              │  │              │         │  semis leading"   │
└──────────────┘  └──────────────┘         └──────────────────┘
                                                                           ← scroll begins here
─────────────────────────────────────────────────────────────────  divider
DEEPER RESEARCH (below fold) — accessible via scroll
```

**Persistent slots (always in same position):**
- Page-state line — top-left
- Ambient timestamp — top-right
- Posture sentence — center top
- Hero — cols 1-5, top half of stage zone
- Watchlist — cols 7-8 (right column), top half
- Market context — cols 6-8, lower half
- Subordinate tiles — cols 1-4, lower half, 2 wide

The asymmetry is not random. It's a fixed grammar. Hero is always wider than subordinates. Watchlist is always tall-and-narrow. Market context is always wide-and-short. The user trains on slot positions over weeks.

## D3. Hierarchy system (visual gravity + eye flow)

Eye-flow choreography, persistent across visits:

```
1. Top-left: page-state line ("3 to look at")     ← register count
2. Top-right: ambient timestamp                    ← register currency
3. Center: posture sentence (36px serif)           ← register AI's read
4. Center-left: HERO SLOT (large)                  ← register today's main thesis
5. Right: watchlist column                         ← register what's brewing
6. Lower-left: subordinate tiles                   ← scan opposing/supporting
7. Lower-right: market context                     ← register environment
8. Below fold: deeper research                     ← optional
```

The eye moves Z-pattern (top-left → top-right → center → lower-right). Western reading order with magazine focal-point exception at center.

**Visual gravity instruments (no animation):**
- **Hero slot is 2.5× the area of any subordinate.** Mass = gravity.
- **Hero gets 32px internal padding, subordinates get 14px.** Air = importance.
- **Watchlist column has rectangular vertical proportions** (160×320). Visually distinct from horizontal hero. Different shape = different category.
- **Market context tile is 3-cols wide × ~80px tall** (wide-short). Visually distinct from everything else. The "skybox."

## D4. Dynamic composition system

Layout adapts to content TYPE, not data quantity. Three layout modes:

| Layout mode | Trigger | Composition |
|-------------|---------|-------------|
| **Standard** | 1 high-conviction + 2-3 supporting | Hero (cols 1-5) + Watchlist (cols 7-8) + 2 subs (cols 1-4 lower) + Market (cols 6-8 lower) |
| **Solo** | Only 1 thesis qualifies for hero | Hero (cols 1-6, full-width-with-margin) + Watchlist (cols 7-8) + Market (full-width below) |
| **Quiet** | No thesis qualifies | Posture sentence ("Quiet day. Watching 4.") + Watchlist column (cols 6-8) + market context full-width |

**Layout decided at session-load only.** Never auto-shifts mid-session (UX-12 lock holds). Content within slots updates on explicit refresh.

This is the key adaptive move. Not "more cards on busy days." Layout MODE shifts based on whether today has a hero. The Solo mode (quiet day with one big call) reads dramatically different from Standard mode (typical morning) without breaking spatial memory — because the Hero slot is always in the same general position; only its width changes.

## D5. Environmental design system

Persistent depth, no animation:

- **Stage zone (top 40vh)** — `#13161B` warm-near-black + 2.5% static amber tint (UX-12 lock).
- **Shop zone (bottom 60vh)** — `#0F1115` cooler.
- **Below-fold zone (NEW for UX-13)** — `#0B0D10` cooler still. Subliminal "this is reference material, not action surface."
- **Three-zone luminance ladder** — stage warmest, shop neutral, deep-research coolest. Temperature decreases as the user descends. NOT mood-mapped — fixed.
- **Hero slot edge** — 1px hairline at `rgba(255,255,255,0.07)` (slightly stronger than UX-12 default). Hero is the only object with a stronger edge. The rest of the page uses 0.04. The edge is the spotlight without using light.
- **Watchlist column edge** — 1px hairline LEFT side only (separates from hero). Cards inside have NO border (Sonnet's rows-not-tiles concept finally appropriate here, because these are scan items not decision objects).

## D6. Asymmetric layout mockups

Standard mode (8-col grid, gutter 24px):

```
COL: 1   2   3   4   5   6   7   8
─────────────────────────────────
[      HERO        ]       [WTCH]   ← hero spans 1-5; watchlist 7-8
[      HERO        ]       [WTCH]
[      HERO        ]       [WTCH]
[      HERO        ]       [WTCH]
[      HERO        ]       [WTCH]
                           [WTCH]
[SUB1] [SUB2]    [MKT CTX]         ← subs span 1-2 + 3-4; market spans 6-8
[SUB1] [SUB2]    [MKT CTX]
                          
─── divider ──────────────────────
[          DEEPER (full)        ]   ← below-fold
```

Solo mode:

```
COL: 1   2   3   4   5   6   7   8
─────────────────────────────────
[       HERO              ] [WTCH]   ← hero spans 1-6
[       HERO              ] [WTCH]
[       HERO              ] [WTCH]
[       HERO              ] [WTCH]
[       HERO              ] [WTCH]
                            [WTCH]
[          MARKET CONTEXT (full)  ] ← market spans full width
─── divider ──────────────────────
```

Quiet mode:

```
COL: 1   2   3   4   5   6   7   8
─────────────────────────────────
       Quiet day.                    ← posture sentence center, no tiles
       Three theses unchanged.
       No new entries warranted.
                            [WTCH]   ← watchlist column persists
                            [WTCH]
                            [WTCH]
[          MARKET CONTEXT (full)  ]
```

The slots are persistent. The compositions vary by mode. Spatial memory holds.

## D7. Emotional UX map

| Surface | Emotion target | How engineered |
|---------|----------------|----------------|
| Page open (Standard) | "I'm in the same room. Let's see today." | Persistent slot positions; new content in known frames |
| Page open (Solo) | "Today is unusual. The AI thinks one thing matters." | Hero widens to dominate; only-one-tile signals importance |
| Page open (Quiet) | "Today is calm. I can come back later." | Hero slot empty; honest about absence; watchlist persists |
| Hover hero | "I can go deeper here." | Edge brightens 0.07 → 0.10; subordinates dim 100% → 88% |
| Click hero | "I committed to research." | Drawer modal; UX-11 motion |
| Watchlist scan | "These are warming." | Different shape; minimal chrome; reads as "list of names" not "decisions" |
| Market context | "Here's the weather." | Wide-short tile reads as horizon line; one-sentence regime read |
| Scroll below fold | "I'm in research mode now." | Cooler zone; deeper layout density; for power users |

## D8. AI atmosphere rules (anti-theater compliant)

Eight specific techniques, all static or session-bounded:

1. **Persistent slot positions across sessions.** The user's muscle memory is the AI's continuity. (NEW for UX-13)
2. **Posture sentence rotates per session** (composer-driven, lint-validated). Each visit reads slightly different. (UX-12 carry)
3. **Layout mode shifts at session-load** (Standard / Solo / Quiet). The composition itself signals AI judgment. (NEW for UX-13)
4. **Watchlist column shows "since you left" delta.** "Since 09:18 yesterday: AAPL approached $172." Implicit AI memory of last visit. (NEW for UX-13)
5. **Hero edge brightens 0.07 → 0.10 on hover.** Hardware-precision response. Subliminal "the page noticed you." (NEW for UX-13, UX-12 cleaner)
6. **Subordinate dim 100% → 88% on hero hover.** Eye guidance via context dimming. (UX-12 carry)
7. **Below-fold zone darker.** Spatial signal of "going deeper." Static. (NEW for UX-13)
8. **Ambient timestamp + page-state.** UX-12 carry-forward.

The key NEW move: **the layout itself signals AI judgment.** Solo mode = "AI is unusually convinced." Quiet mode = "AI sees nothing today." Standard mode = "AI is operating normally." The composition is the AI's voice, not just the typography.

## D9. First 5-second analysis

```
sec 0   page paints. Three zones visible (stage/shop/below-fold).
        Pupils relax (warm near-black, not pure black).
sec 1   eye lands top-left → "3 to look at" registers count
        eye flicks top-right → ambient timestamp registers currency
sec 2   eye drops to center → posture sentence
        registers AI's read in serif (signals authored)
sec 3   eye drops to hero → registers OPEN, ticker, decision
        hero's mass (60% width) signals "this is THE thing today"
sec 4   eye scans right → watchlist column
        4 names register as "what's brewing"
sec 5   eye scans lower → subordinates (TRIM, HOLD)
        + market context wide tile registers regime
```

User feels at sec 5: **oriented in a familiar room with new contents.** Not "reading a dashboard." Not "scanning a feed." OS feeling.

## D10. Before/after

UX-12 (current):
- 3 equal tiles in row
- All tiles 304×184
- Symmetrical grid

UX-13 (proposed):
- Hero (480×320 effective via 2-col span + 32px padding)
- 2 subordinates (304×184)
- Watchlist column (160×320 narrow-tall)
- Market context (480×80 wide-short)
- 4 different shapes; persistent positions; asymmetric

The pixel difference: **3 different aspect ratios in the same viewport.** Aspect ratio = visual category. Different ratios = different mental categories. Same ratio = "another tile."

## D11. Screen-by-screen emotional flow

- **Today (Standard):** persistent room, new contents. Calm orientation in 5s.
- **Today (Solo):** unusual day. Hero widens. Eye locks. AI is unusually decisive.
- **Today (Quiet):** AI sees nothing. Watchlist still present (continuity). Market context still present (room is the same).
- **Drawer open:** UX-11 motion preserved. Backdrop dims to 60%. Drawer rises 220ms iOS curve.
- **Scrolled below fold:** zone darkens. User in research mode. Deeper density permitted.
- **Day 7 of opening:** muscle memory. User's eye finds the watchlist without reading anything else. *That* is the OS feeling.

## D12. New visual language

- **Aspect ratio as taxonomy.** Hero (wide-tall, 1.5:1). Subs (square-ish, 1.65:1). Watchlist (narrow-tall, 0.5:1). Market (wide-short, 6:1). Four ratios = four categories.
- **Persistent slot grammar.** Slots have NAMES (HERO / WATCHLIST / MARKET / SUBS). Composer renders into named slots, not into a free grid.
- **Layout modes as AI signal.** Standard / Solo / Quiet. The layout is the message.
- **Below-fold zone as third luminance.** UX-12 had two zones; UX-13 adds third for deep research.
- **Watchlist as borderless list.** Inside the watchlist column, items have NO border (this is where Sonnet's rows-not-tiles applies — scan items, not decision objects). Outside watchlist, decision tiles still bordered.

## D13. Why current cockpit feels dead

UX-12 fixed substrate but kept SYMMETRIC composition. Three-tile row at any size = dashboard. The eye reads three equal tiles as "scan all three with equal weight" which is exactly the dashboard cognition pattern. Even with serif hero + zones + spacing, the underlying layout is a grid.

Specific failures:
- Three tiles, all same size, all same chrome
- Single column of decision tiles + nothing else (no watchlist, no market context)
- Layout never changes between visits (no Solo mode for unusual days)
- No spatial slot for "what changed since I was last here" (no AI memory surface)
- Below-fold is just more of the same (not a different mode)

UX-12 is a beautifully designed PAGE. UX-13 is an environment.

## D14. What makes it feel alive

Three things:

1. **Layout adapts to content type at session load.** Solo mode IS the AI saying "today is unusual" without text. Quiet mode IS the AI saying "nothing today." Standard mode = normal. The composition is voice.

2. **Persistent slots create muscle memory.** Day 1 the user reads everything. Day 7 the user knows where the watchlist is. The page becomes habitable. macOS Finder, iOS Home, Arc Spaces all do this.

3. **Watchlist column with "since you left" deltas.** Implicit AI memory. The page knows what you saw last and what changed. This is the single most "AI-native" addition possible without violating any anti-theater lock.

## D15. ASCII mockups

(Already in D6 above — Standard / Solo / Quiet modes with column spans.)

The product becomes an OS at the moment three things ship: (a) named persistent slots in a fixed asymmetric grid; (b) layout modes that adapt at session-load to content type; (c) a watchlist column with "since you left" memory deltas. After day 7 the user has muscle memory. The page is no longer read — it is *inhabited*.
