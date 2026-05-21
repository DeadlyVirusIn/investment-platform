# Model: Gemini
## Round: 1

## Position summary
The current investment platform is "structurally honest but emotionally bankrupt." We have built a high-fidelity audit workstation for a quantitative analyst, rather than a modern AI-native copilot for an investor. The UI is defined by its "boxes" — the `ConvictionTile` (UX-11) and `ActionCard` (UX-10) are rigid, flat containers that communicate data density but fail to provide the *feeling* of guidance. The 11 core pages suffer from a "Dashboard Paradox": the more data we provide to build trust, the more we alienate the user's mental model of simple, confident action.

The path forward (UX-12) is not about adding new components, but about a radical shift in **visual philosophy**. We must move from "Institutional Terminal" (Bloomberg/TradingView) to "Atmospheric OS" (Linear/Arc/Apple). This means replacing rigid borders with layered surfaces, solid blacks with atmospheric gradients, and mechanical transitions with cinematic choreography. We must solve for the "5-second feeling": the user should feel "I am in safe, intelligent hands," not "I have 48 items to audit."

---

## D1. Visual Philosophy (Manifesto)
**"The Atmospheric Copilot: From Data Wall to Guided Focus."**
The UI is no longer a terminal for querying a database; it is a lens for observing an intelligence. We prioritize *Atmosphere* over *Utility*. Every pixel must serve the story of the "Living Engine." We replace the "Boxy Dashboard" with "Floating Depth." The product should feel like a premium physical object illuminated by a soft, directional light source — a "cockpit at dawn," not a "server room at night." We trade the rigid 1px border for soft layered shadows, and terminal-monochrome for a temperature-aware palette that breathes with the market's conviction.

## D2. Emotional Hierarchy
The current hierarchy is **Data → Verb → Rationale**. This is backwards for a consumer AI.
The new hierarchy is **Conviction (Feeling) → Action (Direction) → Detail (Evidence)**.
1. **The Core Feeling:** Atmospheric background shifts (warm/cool) and soft "glow" zones tell the user the market mood before they read a single word.
2. **The Decision Hero:** Large, editorial typography (32px+) commands attention with a single, clear directive.
3. **The Evidence Layer:** Data and metrics (the "institutional" part) are demoted to a secondary depth layer, appearing as "supportive metadata" rather than the primary interface.

## D3. Light/depth strategy
We will violate the "anti-glassmorphism" lock not through blur, but through **Atmospheric Layering**.
- **The "Living Surface":** Instead of solid `#0B0D10`, we use a deep `#08090A` base with a 60% wide radial gradient at the top (e.g., `hsla(220, 30%, 15%, 0.4)` on quiet days, `hsla(30, 30%, 15%, 0.4)` on high-conviction days).
- **Depth-Mapped Tiles:** Tiles (`ConvictionTile.tsx`) lose their 1px `#222` border. Instead, they use a subtle 1px "top-light" border (`hsla(0, 0%, 100%, 0.05)`) and a multi-stage shadow: `0 4px 12px rgba(0,0,0,0.4), 0 1px 2px rgba(255,255,255,0.03)`.
- **Focus Zones:** The active page section (e.g., "Action Queue") is bathed in a soft "wash" of light that follows the cursor or the AI's current focus, making the rest of the page feel like a calm, dark background.

## D4. Motion language
We solve T2 ("Cinematic" vs 240ms) through **Choreographed Reveals**.
- **The "Paper" Slide:** When a tile opens into the drawer, the tile doesn't just "click." It has a 120ms "press-in" (scale 0.98) followed by the 220ms iOS-curve drawer slide.
- **The "Ink" Fade:** Text shouldn't "appear." Decision sentences (`ux11-tile-row3`) use a 180ms opacity + 4px Y-offset drift.
- **Micro-Momentum:** Hovering a tile causes a subtle "glow" expansion (8px spread increase) rather than a border-color flip. It should feel like the tile is "waking up."
- **Curves:** Shift from `ease-out` to a custom `cubic-bezier(0.2, 0.8, 0.2, 1)` for a "heavy but responsive" feel.

## D5. Color psychology
We enter "Warmth" (T3) through **Ambient Temperature**, not semantic accent.
- **Tier-Mapped Tinting:** The background "wash" shifts temperature based on the median conviction of the `Action Queue`. 
    - *High Conviction:* Warm amber undertones (`hsla(38, 20%, 10%, 1)`).
    - *Neutral/Hold:* Cool slate undertones (`hsla(220, 15%, 10%, 1)`).
    - *Risk/Exit:* Deep charcoal-red (`hsla(0, 15%, 8%, 1)`).
- **The Verb Pill:** Stays monochrome as per UX-10 lock, but gains a "glow" property: on hover, the pill's text emits a subtle 2px blur of its own color, making it feel "electrified" by the AI's certainty.

## D6. AI presence
We solve T4 ("AI Presence" vs "Anti-Theater") through **Observational Rhythm**.
- **The "Pulse" Marker:** A single 2px vertical bar at the left edge of the page that slowly "breaths" (opacity 0.3 to 0.6 over 4s). It represents the pipeline health (`Ops.tsx`) without being an "orb."
- **Contextual Copy shifts:** The hero text in `Overview.tsx` doesn't just say "Today." It says "The engine is currently defensive" or "The engine is tracking 4 catalysts." 
- **The "Ghost" Cursor:** In the `Decisions.tsx` timeline, a subtle highlight shows the "last reviewed" decision by the AI, making it feel like the AI is currently working through the list.

## D7. Interaction philosophy
Interaction must feel **Intentional, not Functional**.
- **The "Solid" Click:** Every button press should have a subtle haptic-like scale transform.
- **The "Editorial" Scroll:** Page transitions (e.g., moving from Overview to Decisions) use a brief 200ms "content-zoom" out-and-in, making the OS feel like a physical stack of cards.
- **Zero-Friction Detail:** Clicking a symbol shouldn't "navigate" to a new page; it should "bring the data to the user" via the Drawer, which now feels like the primary workspace, not a modal.

## D8. Homepage transformation (Overview)
**Before (Current UX-11):**
```
[ Today | May 10, 2026 ] [ Working -> ]
[ Market regime: Neutral ]
[ Active Positions (3) ] [ Promotions (2) ]
[ TILE ][ TILE ][ TILE ] [ TILE ][ TILE ]
```
**After (UX-12 Proposed):**
```
( Atmospheric Radial Glow )
   "The market is pausing. The engine suggests patience."
   [ May 10, 2026 ]

   ( Soft Section Fade )
   THE CORE CONVICTION
   [ LARGE EDITORIAL TILE: AAPL HOLD ]
   "Thesis remains intact despite earnings volatility."

   ( Horizontal Scroll Rail - Soft Depth )
   SECONDARY SIGNALS
   [ TILE ] [ TILE ] [ TILE ] [ TILE ]
```

## D9. Tile redesign philosophy
The tile is no longer a "container of 5 rows." It is a **Physical Object**.
- **Remove:** Rigid row borders, solid `#222` borders.
- **Add:** Soft depth-2 shadows, variable line-heights, and "Optical Sizing."
- **The Focus Row:** The Decision Sentence (`ux11-tile-row3`) is the "Hero" of the tile. It moves to the top. The ticker and verb pill move to a "Metadata" layer at the bottom.
- **Visual momentum:** The "Invalidation Distance" (`ux11-tile-row5`) becomes a subtle progress bar at the bottom edge of the tile, providing a "visual timer" for the trade.

## D10. Typography redesign
Move from "Terminal" to "Editorial."
- **Hero H1:** 40px/1.1 tracking -0.04em. Medium weight.
- **Section Headers:** 11px uppercase, tracking 0.2em, 50% opacity. (The "Linear" look).
- **The Decision Sentence:** 20px, light weight, tracking -0.01em.
- **Metadata:** 12px Mono, `#666` (Institutional trace).
- **Scale:** Only 4 sizes total, but with dramatic weight/spacing contrast.

## D11. Spatial rhythm
**The "Breathing" Scale:**
- **Page Padding:** Increase from 32px to 64px. Let the content float.
- **Block Gaps:** 48px between sections.
- **Tile Gaps:** 24px (from 16px). Give the "depth" room to cast shadows.
- **Internal Padding:** Tiles move to 20px padding (from 16/14).

## D12. Consumer vs dashboard comparison
At the pixel level:
- **Dashboard (Bloomberg):** 1px borders, 12px condensed type, solid background, 100% saturation semantic colors, "fit as much as possible."
- **Consumer AI (Linear/Arc):** Layered box-shadows (no borders), 14px-18px type, atmospheric backgrounds, <40% saturation colors, "fit only what matters."

## D13. Before/after ASCII
**Before (ActionQueue.tsx):**
```
| [BUY] AAPL | 98% Conf | 2h ago |
| Rationale: Thesis name...      |
| "The engine believes..."       |
```
**After (ActionQueue.tsx):**
```
   ( Soft shadow, no border )
   AAPL · BUY
   "The engine believes Apple is oversold 
    ahead of next week's catalyst."
   [ 98% Confidence ] [ Fresh ] [ Bull · Bear ]
```

## D14. Screen-by-screen emotional flow
- **Today (Overview):** *Focus & Calm.* The user feels "I know exactly what to do today."
- **Drawer (Reasoning):** *Clarity & Depth.* The user feels "I understand exactly why the AI thinks this."
- **Quiet Day:** *Security & Presence.* The user feels "The AI is watching, even if there's no action."

## D15. First 5-second analysis
**The Goal:** "Confidence through Restraint."
In the first 5 seconds, the user sees a single, large, high-confidence message. They shouldn't see a grid. They see the *result* of the engine's work. The atmospheric background tells them the market temperature. They feel "informed," not "overwhelmed."

## D16. Why current implementation feels wrong
**Diagnosis:** We are using **Atomic Components** to build a **Narrative Product**.
In `ActionQueuePage.tsx` and `SignalLabPage.tsx`, we have high-quality components (`FilterBar`, `ActionQueue`, `HealthRail`) but they are laid out in a "Control Panel" configuration. They are all fighting for the user's attention at the same z-index. The use of solid borders (`border-b1`) creates a "caged" feeling.

## D17. What finally makes it feel AI-native
**Prescription:** The UI must **Anticipate**, not just **Respond**.
An AI-native product feels like it is "presenting" the day to you. This is achieved through:
1. **Dynamic Layouts:** The homepage changes layout based on the *state* of the engine (Quiet vs. Active).
2. **Atmospheric Signaling:** Color temperature as a pre-attentive signal.
3. **Editorial Typography:** Treating AI decisions as headlines, not database rows.
4. **Cinematic Depth:** Using layers to manage the "Institutional vs. Novice" tension (T6).

---
*End of Round 1 Review*
