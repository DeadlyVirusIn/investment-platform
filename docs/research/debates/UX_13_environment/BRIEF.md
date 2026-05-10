# UX-13 Living AI-Native Environment — Debate Brief

> Shared brief read by all 4 models (Gemini · Codex · Claude Opus 4.7 · Claude Sonnet 4.6).
> 3-round adversarial debate. 2,000–3,000 words per model per round.
> **PURE EXPERIENCE DESIGN.** NOT implementation. NOT backend. NOT schemas. NOT routes.

## What we are validating

UX-12 (Aesthetic Philosophy) shipped its master. The substrate fix is right: dark two-zone canvas, serif posture sentence, page-state line, ambient timestamp, no card chrome, weight-as-confidence, schema-preserving 2-col hero, Linear-class spacing. All 4 models converged on substrate.

**User feedback after the UX-12 lock:**

> "STOP MICRO-ITERATING COMPONENTS. UX-12 finally identified the real issue correctly: 'The failure is substrate, not components.' Now we need the NEXT leap: FROM AI research dashboard TO AI investing environment."

> "The current UX still feels like pages, cards, dashboards, layouts, research software. My actual vision is AN AI-NATIVE INVESTING OPERATING SYSTEM. Emotionally guided. Visually alive. Aspirational. Cinematic. Intelligent. Adaptive. Premium. Habit-forming."

> "The user should feel: 'The AI already understands the market for me.' NOT: 'I should read these tiles.'"

> "Symmetrical grids ALWAYS feel like dashboards. We need: visual gravity, asymmetric composition, guided eye flow, focal hierarchy, dynamic composition, living intelligence."

**UX-13 is the LIVING ENVIRONMENT debate.** Not new components, not new substrate tokens — new *composition* and *atmosphere*.

## Reference emotional direction

CLOSER TO:
- Arc Browser
- Perplexity
- Linear
- Apple-level interaction design
- premium editorial systems
- cinematic product design
- modern AI-native software
- (NEW) investing operating system that the user opens *because they want to*, not *because they must*

NOT:
- Bloomberg
- TradingView
- hedge fund terminals
- crypto dashboards
- admin systems

## The 7 problems user explicitly named

1. **Break the grid.** Page should NOT feel "card card card card." Need: dominant focal object, asymmetric layouts, dynamic spacing, guided visual flow, spotlight hierarchy, intentional imbalance. ONE opportunity should visually dominate; others should support.

2. **Visual gravity.** Eye flow: AI posture → primary conviction → secondary opportunities → watchlist → market context → deep research. User should NEVER wonder "where do I look?"

3. **Living environment.** Need environmental depth, atmospheric lighting, dynamic warmth/coolness, subtle intelligence presence, spatial calmness, breathing composition. NOT flat black + tiles.

4. **Remove dashboard energy.** Too many rectangles, equal surfaces, alignment symmetry, visual rigidity, "software" feel. Need editorial composition, cinematic spacing, intentional emptiness, emotional pacing, premium restraint.

5. **AI presence (still).** AI should feel present, aware, observing, guiding. Without chat bubbles, typing, AI theater, glowing orbs, gimmicks.

6. **Premium feel.** Currently still feels prototype-level. Need stronger typography confidence, richer composition, higher-end motion, luxury software feel, cleaner rhythm, more beautiful first paint.

7. **Emotion target.** User should feel: "Damn. This feels like the future of investing." NOT: "This is a nice dashboard."

## What stays locked from UX-10/11/12 (DO NOT re-debate)

UX-13 is a COMPOSITION + ATMOSPHERE layer. It modifies the *arrangement* of locked invariants but does not change them. Locked across UX-10/11/12 (carry-forward):

- 4 verbs (`OPEN · HOLD · TRIM · EXIT`).
- 4 confidence tiers + dot glyph.
- 4 freshness states.
- Bear-case-mandated for `Confirmed`+ tier.
- Invalidation appears before target.
- "The click hides detail, not risk existence."
- AI voice mixed regime (third-person hero, implicit body).
- Drawer modal sheet, 9 sections, 88vh, 220ms iOS curve, 5 dismiss paths, URL state `?drawer=<TICKER>`.
- ConvictionTile schema 304×184, 5 rows, refuses-to-render.
- Bear-case-glyph + Bull/Bear inline pair on Confirmed+ tile.
- 13 trust safeguards as engineering invariants.
- 58-item locked anti-pattern list (UX-10 §12 + UX-11 §13 + UX-12 §14).
- Anti-AI-theater locks: no orb, chat dock, suggested-question chips, "Powered by AI" badge, typing animation, persona name, first-person pronoun outside hero, auto-open onboarding, breathing/pulsing animations, cursor lean-in, depress-on-click, biomorphic copy.
- Refuses-to-render schemas (composer-level).
- Banned-token voice lint.
- UX-12 substrate: dark warm-near-black two-zone canvas, hard 1px cut at 40vh, 2.5% static amber stage tint (NEVER state-mapped), no card chrome, hairline `rgba(255,255,255,0.04)`, no shadows.
- UX-12 typography: 5-size ramp (36/22/16/14/11), Source Serif 4 hero + Inter body + iA Mono tabular, decision sentence weight tracks tier, no weights > 500.
- UX-12 motion: 220ms components, 340ms staggered orchestration, ZERO ambient motion, iOS curve, explicit-trigger-only reflow.
- UX-12 spacing: Linear-class scale (96/80/32/14).
- UX-12 AI presence: 5 techniques (posture sentence, page-state, serif typeface, weight-as-tier, ambient timestamp).
- UX-12 hero composition: 2-col span of 304×184 schema, 32px internal padding, warmer stage-zone placement.

## What UX-13 IS allowed to change

- **Composition** (asymmetric, dynamic, broken-grid layouts).
- **Eye-flow choreography** (visual gravity, focal hierarchy, scroll-driven emphasis).
- **Atmospheric depth** (breathing rhythms in spacing, NOT in opacity/animation; environmental warmth shifts that are STATIC; layered space).
- **Emotional pacing** (when does the user encounter what; rhythm of consumption).
- **Adaptive layout** (does the layout change based on what the page contains? e.g., quiet day vs busy day vs single high-conviction vs many low-conviction).
- **Living intelligence surfaces** (compositional moves that make the system feel attentive without violating anti-theater bans).

## Specific tensions UX-13 must resolve

### T1 — Asymmetric composition vs schema lock + accessibility

User wants asymmetric layouts. ConvictionTile schema is locked at 304×184. CSS Grid + Flexbox can produce asymmetric *placement* (one tile spans 2 cols, another tile is 1 col, gap collapses, etc.) without breaking the tile schema. **What's the asymmetric layout grammar that respects the schema lock?** Be specific.

### T2 — "Living" vs zero-ambient-motion ban

UX-12 banned all ambient motion. User wants "living environment." **What KIND of "alive" is permissible without animation?** Possibilities: layout adapts to data (more cards on busy days, fewer/larger on quiet); composition shifts at session-boundary; atmospheric warmth that is STATIC but varies by content; scroll-driven parallax (probably banned); time-of-day temperature shift (probably banned as mood-ring).

### T3 — "Visual gravity" vs equal-treatment of all theses

User wants ONE dominant focal object. UX-12 already has hero+subordinate split. **What MORE does UX-13 do beyond UX-12's hero composition?** Is the hero now 4× bigger? Does the page have ONLY the hero in viewport and force scroll for subordinates? Does the hero get unique chrome (a halo, a spotlight, a frame) that subordinates don't?

### T4 — "Adaptive layout" vs predictability + spatial memory

User wants dynamic layouts that respond to data. UX-12 locked "no auto-reflow during active read" for spatial memory. **How does layout adapt without breaking spatial memory?** Possibilities: layout decided at session-load only; user-triggered refresh re-composes; composition is determined by content type (1 high-conviction = hero+nothing, 3 mixed = hero+subs, 5 low = grid).

### T5 — "Cinematic composition" vs flat editorial

UX-12 chose flat editorial (no shadows, no gradients on tiles). User now wants cinematic. **What's the difference between cinematic and casino?** Possible: depth via spatial separation + zone-boundary edges + serif typography + restrained color. NOT depth via shadows, blur, glow, or motion.

### T6 — "Habit-forming" vs anti-addiction safeguards

User wants daily habit. UX-10/11 added anti-addiction safeguards (decision rest at 4 cards/24h, no daily-action framing, no countdown timers, action ledger). **How do we encourage daily return without violating those safeguards?** Possibilities: morning ritual feel (page changes meaningfully overnight); visible AI memory ("welcome back, here's what changed since you left"); calm continuity (the page knows you're back).

## Round mechanics

**Round 1** — Independent position. No reading other models. Cover all 7 user-named problems + 6 tensions + 15 deliverables (below). 2,000-3,000 words.

**Round 2** — Critique + refine. Quote others' weakest claims. Defend own.

**Round 3** — Final convergence. 1,500-2,500 words. Honest concessions. Open disputes documented.

## 15 deliverables (ALL models must address all 15 in R1)

1. Visual philosophy evolution (UX-12 → UX-13 manifesto)
2. Homepage recomposition (specific asymmetric layout)
3. New hierarchy system (visual gravity + eye-flow choreography)
4. Dynamic composition system (how does layout adapt to content?)
5. Environmental design system (depth, atmosphere, warmth)
6. Asymmetric layout mockups (ASCII, specific dimensions)
7. Emotional UX map (user emotion at each surface)
8. "AI atmosphere" rules (concrete techniques)
9. First 5-second feeling analysis
10. Before/after comparisons (UX-12 vs UX-13)
11. Screen-by-screen emotional flow
12. New visual language proposals
13. "Why the current cockpit still feels dead"
14. "What finally makes it feel alive"
15. ASCII mockups with asymmetric composition

## Format per model per round

```
# Model: <name>
## Round: <1|2|3>

## Position summary (300 words max)

## D1. Visual philosophy evolution
## D2. Homepage recomposition
## D3. Hierarchy system
## D4. Dynamic composition
## D5. Environmental design
## D6. Asymmetric layout mockups
## D7. Emotional UX map
## D8. AI atmosphere rules
## D9. First 5-second analysis
## D10. Before/after
## D11. Screen-by-screen emotional flow
## D12. New visual language
## D13. Why current cockpit feels dead
## D14. What makes it feel alive
## D15. ASCII mockups
```

R2 adds: critique-of-each-other + concessions + open disputes.
R3 adds: final answers + master doc recommendations.

## Hard rules

- This is PURE EXPERIENCE DESIGN. NOT implementation. NOT backend. NOT schemas. NOT routes.
- Cite specifics: pixel values, color hex, easing curves, motion ms (within UX-12 zero-ambient-motion lock), font sizes.
- Reference real products at the pixel level: Linear, Arc, Perplexity, Apple.
- Take strong positions. The user's feedback is brutal. Match the energy.
- Asymmetric composition examples MUST be concrete — describe specific column spans, gap variations, focal point placement, scroll-triggered scenes.
- "Visual gravity" must be measurable — describe what objects pull the eye and how.
- "AI atmosphere" must be decomposed into specific techniques that don't violate the 58-item anti-pattern list.

## What success looks like

After R3, Opus synthesizes a single locked master at `docs/research/UX_13_LIVING_ENVIRONMENT.md` with:

- Visual philosophy evolution (manifesto)
- Composition grammar (asymmetric layout rules)
- Visual gravity system (focal hierarchy spec)
- Dynamic composition system (content-adaptive layout rules)
- Environmental design tokens (atmosphere + warmth + depth — all STATIC)
- AI atmosphere techniques (anti-theater compliant)
- Emotional pacing rules
- Anti-pattern additions to 58-item list
- Implementation phasing (13A → 13X) — but ONLY composition + treatments, NO new components
- Cross-reference to all UX-10/11/12 invariants that are inherited

If the 4 models cannot converge on any item, the master MUST document the dispute and recommend a default with reasoning.
