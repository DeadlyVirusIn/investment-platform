# UX-11 Interactive AI Copilot Layer — Debate Brief

> Shared brief read by all 4 models (Gemini · Codex · Claude Opus 4.7 · Claude Sonnet 4.6).
> 3-round adversarial debate. 2,000–3,000 words per model per round.

## What we are validating

UX-11 is the interaction-layer redesign sitting on top of the locked UX-10 Conviction Engine invariants.

**UX-10 (just shipped, locked):** structurally honest research surface — full ActionCards with verb + tier + freshness + decision sentence + invalidation + Driver/Counter/Catalyst + targets + horizon, all expanded inline on the homepage.

**User feedback after viewing UX-10 implementation at `/overview?view=conviction`:**

> "Still feels too much like a research terminal. Analyst cards. Static intelligence surfaces. Instead of an AI investing copilot, an interactive conviction engine, an emotionally-guided investing system."

> "The homepage should feel alive, visually guided, fast to scan, emotionally directional, AI-assisted. The detailed thesis content should appear AFTER interaction. This is the key missing UX layer."

> "The user should NOT land and immediately read invalidation, driver/counter paragraphs, catalyst blocks. Those belong INSIDE interaction layers."

**UX-11 (this debate):** transform homepage from "expanded research notes" to "compact AI conviction surface with progressive disclosure via drawer."

## What stays locked from UX-10 (do NOT re-debate)

- **The 4 verbs** — `OPEN · HOLD · TRIM · EXIT`. Period.
- **The 4 tiers** — `Forming · Working · Confirmed · Conviction` + dot glyph.
- **The 4 freshness states** — `Fresh · Aging · Stale · Expired`.
- **Bear-case-mandated** for `Confirmed`+ tier (composer invariant).
- **Invalidation appears before target** (rendered wherever full thesis shown).
- **STRUCTURE** for options; loss-named-first; defined-risk default.
- **Refuses-to-render schema** on ActionCard data.
- **13 trust safeguards** as engineering invariants (UX-10 §10).
- **29-item anti-pattern lock list** (UX-10 §12) — including no casino motion, no countdown clocks, no "AI FOUND N MOVES", no daily-action framing, no Material Indigo, no glassmorphism, etc.

## What this debate IS about (the 11 questions)

### Q1. ConvictionTile shape

The tile that replaces the full ActionCard on the homepage. User's example mockup:

```
┌───────────────────────────────┐
│ 🟢 OPEN                       │
│ NVDA                          │
│ AI infra demand accelerating  │
│                               │
│ +18% upside                   │
│ Strong thesis                 │
└───────────────────────────────┘
```

What's the right tile spec?
- Width × height (compact target ~280×180px)?
- Required fields vs banned fields?
- Color emoji circles vs monochrome verb pills?
- Is "+18% upside" a target anchor (UX-10 banned that on cards)?
- Tier glyph or named tier?
- Freshness — visible or hidden?
- Click target — entire tile or specific affordance?

### Q2. AIReadHero

Top-of-page sentence in active AI voice.

User examples:
- BAD: "Selective, valuation-sensitive."
- GOOD: "The AI is becoming more selective after this week's rally."
- BAD: "Take 30% off Tesla..."
- GOOD: "The AI believes Tesla upside no longer compensates for growing event risk."

How long? 60-100 chars? Single sentence or two? Always present? Updated daily/per-session/real-time? Anti-AI-theater rules (no orb, no chat dock, no "Powered by AI") still apply — how to give AI "presence" without violating those locks?

### Q3. ReasoningDrawer experience

Slides up from any tile/card on click. Cinematic, premium, alive, AI-guided.

What sections? UX-10 §9 master had 7 sections (recap → Driver/Counter → what changed → compared candidates → my pattern → calibration → engine version). Does UX-11 drawer match that, extend it, or differ?

Motion — slide up duration? Easing? Backdrop? Dismiss behavior?
Mobile — slides up bottom sheet, or full-screen?
Multiple drawers — can two be open? Single only?
Anchor return — does drawer dismiss bring user back to scroll position?

### Q4. AI voice rules

Active-AI-voice composer rules. What patterns? What's banned?

User said: "The AI itself must feel present" but also (from UX-9 carryforward): "no orb, no chat dock, no 'Powered by AI', no suggested-question chips."

How does AI feel present without violating those bans? Through *language* alone? Persistent footer attribution? Tone in copy?

### Q5. Visual hierarchy ramp

Four layers of weight:
- PRIMARY: AI pulse / conviction tiles
- SECONDARY: high-priority opportunities + risk shifts
- TERTIARY: watchlists / catalysts / changes
- QUATERNARY: deep research / operational detail

How to encode visually? Surface treatment per layer? Spacing scale? Color contrast? Opacity?

### Q6. Subtle background depth

User feedback: "page still feels too dark, too flat, too muted, too equal-weighted."

But UX-10 banned page-level conviction tints (mood-ring) and gradients on cards.

What CAN add depth without violating bans? Radial gradient at top behind hero? Layered card elevations (3 depth levels are tokenized)? Blurred ambient light? Section dividers?

### Q7. Tile click → drawer interaction

What's the UX of clicking a tile?
- Direct drawer open (modal-style)?
- Tile expands in place?
- Tile flips?
- Background darkens?
- Other tiles dim?
- Click outside dismisses?
- ESC dismisses?
- Browser back-button dismisses?

How to make this feel "cinematic" without becoming gimmicky?

### Q8. Secondary surfaces structure

Below the primary tile strip, what surfaces show? Per user:
- Watchlist
- Catalysts
- Portfolio shifts
- Macro
- Sector rotation

How are these arranged? Horizontal strips? Grid? Accordion sections? What's the visual treatment that makes them visually subordinate to the tiles?

### Q9. Mobile experience

Tile strip on mobile — horizontal scroll, vertical stack, or both? Drawer on mobile — bottom sheet at 90% viewport? AIRead positioning?

### Q10. Biggest failure modes

Each model MUST identify how UX-11 fails. Examples:
- Tiles too compact → meaningless without expansion (drawer becomes mandatory, not optional)
- AI voice becomes overbearing or sycophantic
- Drawer motion feels gimmicky
- Hierarchy ramp creates visual chaos
- Background depth violates anti-pattern locks
- Click-to-expand interaction adds friction over UX-10 inline
- Compactness loses the trust-building (bear case hidden behind a click violates Sonnet's R2 lock that "tabs hide bear case behind a click")

### Q11. Final synthesis

ConvictionTile spec, AIReadHero spec, ReasoningDrawer spec, AI voice composer rules, hierarchy ramp tokens, depth tokens, interaction model, secondary-surface structure, mobile spec, anti-pattern additions to UX-10 lock list, implementation phasing (11A → 11G).

## Specific tension to resolve

UX-10 master Section 13 §9 said:

> "Single scroll surface (not tabs) with sections: ... Plain-language thesis recap → 3 drivers / 3 counters → ..."
> "Tabs hide the bear case behind a click. Forced past the user's eye."

UX-11 now says: hide everything (including bear case) behind a click (the drawer).

**Are these compatible?** Or does UX-11 violate Sonnet's R2 lock from UX-10? The debate must address this directly. One possible resolution: drawer is one continuous scroll inside it (Sonnet's spec) but the drawer itself is opened by user action (UX-11's spec). User ACTS to see the bear case but the bear case is then forced past the eye in a single scroll. Is that enough?

## Emotional target — locked

Same as UX-10: "an AI investment strategist helping me make better decisions." NOT: gambling app · hype machine · ticker feed · signal spam · stock-picking casino.

NEW for UX-11: must also feel **alive**, **inviting**, **fast to scan**, **emotionally directional**.

Reference emotional direction:
- Autopilot
- Perplexity
- modern AI-native products
- cinematic intelligence
- Apple-level interaction quality

NOT:
- Bloomberg terminals (Failed Extreme #1)
- static dashboards
- crypto trading apps
- analyst portals
- generic fintech dark mode

## Round mechanics

**Round 1** — Independent position covering all 11 questions. No reading other models. Adversarial. Take strong positions.

**Round 2** — Read other 3 models' R1. Find weakest claim in each. Defend own. Refine where conceded.

**Round 3** — Final convergence. 1,500-2,500 words. Honest concessions. Open disputes documented.

## Output format per model per round (matches UX-10 spec)

```
# Model: <name>
## Round: <1|2|3>

## Position summary (300 words max)
## Q1. ConvictionTile shape
## Q2. AIReadHero
## Q3. ReasoningDrawer experience
## Q4. AI voice rules
## Q5. Visual hierarchy ramp
## Q6. Subtle background depth
## Q7. Tile click → drawer interaction
## Q8. Secondary surfaces structure
## Q9. Mobile experience
## Q10. Biggest failure modes
## Q11. Final synthesis
```

R2 adds: critique-of-each-other-model + concessions + open disputes.
R3 adds: final answers per Q + master doc recommendations.

## What success looks like

After R3, Opus synthesizes a single locked master at `docs/research/UX_11_INTERACTIVE_COPILOT.md` with:
- ConvictionTile spec (props + invariants + visual)
- AIReadHero spec
- ReasoningDrawer spec (sections + motion + dismiss)
- AI voice composer rules
- Visual hierarchy ramp tokens
- Background depth tokens
- Tile click interaction model
- Secondary surfaces structure
- Mobile spec
- Anti-pattern additions to the UX-10 lock list
- Implementation phasing (11A → 11G)
- Cross-reference to UX-10 invariants that are inherited

If 4 models cannot converge on any item, master MUST document the dispute and recommend a default with reasoning.
