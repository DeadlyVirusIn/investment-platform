# UX-12 Aesthetic Philosophy — Debate Brief

> Shared brief read by all 4 models (Gemini · Codex · Claude Opus 4.7 · Claude Sonnet 4.6).
> 3-round adversarial debate. 2,000–3,000 words per model per round.
> **This debate is PURE PRODUCT EXPERIENCE DESIGN — NOT implementation.**

## What we are validating

UX-10 (Conviction Engine) and UX-11 (Interactive Copilot Layer) shipped. Both are structurally honest. Both pass every trust safeguard. Both render at `/overview?view=conviction` and `/overview?view=copilot` for visual validation.

**They both fail at the same level: emotional.** The user just said:

> "We successfully reduced research density, BUT the product STILL feels like a dark dashboard, static fintech cards, institutional tooling, analyst software — instead of a modern AI-native investing copilot, an emotionally-guided investing system, a product users WANT to open daily."

> "We are still thinking COMPONENTS. We need to think EXPERIENCE. The UI still feels boxy, dark, flat, rigid, terminal-like, text-heavy, non-emotional, low-energy, dashboard software. The user should feel curiosity, clarity, confidence, guidance, momentum, focus. NOT 'I am reading cards.'"

> "The problem is NOT missing components. The problem is **visual philosophy**."

**UX-12 is the visual philosophy debate.** No new components. No new schemas. No new routes. New *feeling*.

## Reference emotional direction

CLOSER TO:
- Autopilot
- Perplexity
- Arc Browser
- Linear
- modern Apple interaction design
- premium consumer AI products

NOT:
- Bloomberg
- TradingView
- crypto exchanges
- hedge fund terminals
- admin panels

## The 8 problems user explicitly named

1. **LIGHT.** UI too dark. Need atmospheric gradients, soft depth, layered surfaces, breathing room, subtle warm/cool transitions, visual focus zones. NOT solid black everywhere.

2. **SPACING.** Cramped. Need dramatically more whitespace, clearer section breathing, larger vertical rhythm, calmer composition.

3. **TYPOGRAPHY.** Too dashboard. Need larger hero type, cleaner hierarchy, more editorial confidence, fewer ALL CAPS labels, stronger contrast hero/action/detail/metadata.

4. **AI PRESENCE.** Hidden. Need AI pulse, confidence, guidance, urgency, mood, shifts. AI should feel present, observing, reactive, alive — without chatbot gimmicks, typing animation, AI theater.

5. **TILES.** Still feel like dashboard cards. Need emotional hierarchy, stronger OPEN/TRIM/HOLD distinction, visual momentum, directional energy, richer interaction, stronger hover/focus states, cleaner information prioritization. User should feel "THIS matters" instantly.

6. **MOTION.** Too subtle and mechanical. Need cinematic transitions, layered reveals, focus movement, depth shifts, intelligent hover, premium easing curves. Apple/Arc/Linear, NOT CSS hover effects.

7. **COLOR PSYCHOLOGY.** Need intelligent warmth/coolness, emotional emphasis, subtle conviction tinting, visual temperature changes. NOT terminal monochrome.

8. **HOMEPAGE EXPERIENCE.** Should feel like "opening an AI market cockpit." NOT "viewing recommendation tiles."

## What stays locked from UX-10 + UX-11 (DO NOT re-debate)

UX-12 is a PHILOSOPHY layer — it modifies the *expression* of locked invariants but does not change them. Locked across UX-10 + UX-11 (carry-forward):

- The 4 verbs (`OPEN · HOLD · TRIM · EXIT`).
- The 4 confidence tiers + dot glyph.
- The 4 freshness states.
- Bear-case-mandated for `Confirmed`+ tier (composer invariant).
- Invalidation appears before target.
- "The click hides detail, not risk existence" master principle.
- AI voice mixed regime (third-person hero, implicit body).
- Drawer is modal, 9 sections, 88vh, 220ms iOS curve.
- ConvictionTile schema (304×184, 5 rows, refuses-to-render).
- URL state `?drawer=<TICKER>`.
- 13 trust safeguards as engineering invariants.
- 44+ items in the anti-pattern lock list (UX-10 §12 + UX-11 Section 13).
- All anti-AI-theater bans: no orb, no chat dock, no suggested-question chips, no "Powered by AI" badge, no typing animation, no auto-open onboarding.
- Refuses-to-render schemas (composer-level).
- Banned-token voice lint.

## Specific tensions UX-12 must resolve

### T1 — "Light" vs anti-glassmorphism + anti-mood-ring locks

User wants atmospheric gradients, soft depth, warm/cool transitions. UX-10/11 banned glassmorphism, mood-ring backgrounds, conviction-density-mapped hue, animated ambient blobs, purple-blue AI gradients, all gradients on cards. **What KIND of "light" is permissible?** Be specific.

### T2 — "Cinematic motion" vs the 240ms motion budget cap + anti-casino-motion ban

User wants Apple/Arc/Linear motion. UX-10 §S9 caps motion at 240ms / 8px translation. No flashing, pulsing, countdowns, confetti, casino motion. **What does "cinematic" look like inside a 240ms budget?** Or do we extend the budget?

### T3 — "Color psychology / warmth" vs monochrome verb pill + ≤50% saturation ceiling

User wants warmth. UX-10/11 lock pure monochrome verb pills, ≤50% color saturation, no semantic color accents. **Where does color enter?** Is it a temperature-shift (warm/cool background) without violating verb-pill monochrome? Is it tier-mapped tint?

### T4 — "AI presence" vs anti-AI-theater bans

User wants AI to feel present, alive, observing. UX-9/10/11 banned: orbs, chat docks, suggested-question chips, "Powered by AI" badges, typing animation, AI persona names, first-person pronouns outside hero. **How do you make AI feel present without ANY of these?** Through copy alone? Motion? Composition? Real-time updates? Rhythm?

### T5 — "Larger hero typography" vs decision-sentence-as-headline (UX-11 L6)

User wants editorial typography. UX-11 locks decision sentence as the largest visual element on every card at 14-18px. **Is the hero now larger than the decision sentence?** What's the new type ramp?

### T6 — "Premium feel" vs all the bans

User wants premium consumer AI product. UX-10/11 ban gradients, glassmorphism, casino motion, mood-rings, color saturation > 50%, typography > 4 sizes. **What's left to make it feel premium?** Restraint vs richness — where's the line?

## Round mechanics

**Round 1** — Independent position. No reading other models. Cover all 8 user-named problems + all 6 tensions + 17 deliverables (below). 2,000-3,000 words.

**Round 2** — Critique + refine. Quote other models' weakest claims. Defend own.

**Round 3** — Final convergence. 1,500-2,500 words. Honest concessions. Open disputes documented.

## 17 deliverables (ALL models must address all 17 in R1)

1. New visual philosophy (one paragraph manifesto)
2. Emotional hierarchy system (how the eye moves through the page)
3. Light/depth strategy (specific tokens — what survives the anti-glass ban)
4. Motion language (specific easing curves, durations, choreography)
5. Color psychology system (where warmth lives; where coolness lives; tier-vs-mood line)
6. AI presence system (concrete techniques that DON'T violate anti-AI-theater)
7. Interaction philosophy (what makes interaction feel premium vs functional)
8. Homepage transformation (before → after, ASCII or specific layout deltas)
9. Tile redesign philosophy (NOT new schema — new visual treatment)
10. Typography redesign (specific type ramp + weights + tracking + leading)
11. Spatial rhythm redesign (specific spacing scale + section padding + breathing rules)
12. Consumer-product vs dashboard comparison (what differentiates Linear from Bloomberg at the pixel level)
13. Before/after ASCII mockups (current UX-11 → proposed UX-12)
14. Screen-by-screen emotional flow (Today / Drawer / Quiet day — what does the user feel at each)
15. First 5-second user feeling analysis (what should they feel in the first 5 seconds? how do we engineer that?)
16. "Why current implementation still feels wrong" (concrete diagnosis)
17. "What finally makes it feel AI-native" (concrete prescription)

## Format per model per round

```
# Model: <name>
## Round: <1|2|3>

## Position summary (300 words max)

## D1. Visual philosophy (manifesto)
## D2. Emotional hierarchy
## D3. Light/depth strategy
## D4. Motion language
## D5. Color psychology
## D6. AI presence
## D7. Interaction philosophy
## D8. Homepage transformation
## D9. Tile redesign philosophy
## D10. Typography redesign
## D11. Spatial rhythm
## D12. Consumer vs dashboard comparison
## D13. Before/after ASCII
## D14. Screen-by-screen emotional flow
## D15. First 5-second analysis
## D16. Why current implementation feels wrong
## D17. What makes it feel AI-native
```

R2 adds: critique-of-each-other + concessions + open disputes.
R3 adds: final answers + master doc recommendations.

## Hard rules

- This is NOT about backend, schemas, lint, routes, drawers, validators, or implementation details.
- This is PURE PRODUCT EXPERIENCE DESIGN.
- Cite specifics: pixel values, color values, easing curves, motion ms, font sizes, weights, line-heights, tracking.
- Reference specific products: Linear, Arc, Perplexity, Autopilot, Apple — at the pixel level.
- Take strong positions. The user's feedback is brutal — your response should be brutal too.
- If your view is "the previous direction was right, just polish it" — say so and defend it. Don't perform-disagree.
- If your view is "the previous direction was fundamentally wrong" — say so and defend it.

## What success looks like

After R3, Opus synthesizes a single locked master at `docs/research/UX_12_AESTHETIC_PHILOSOPHY.md` with:

- Visual philosophy manifesto
- Emotional hierarchy spec
- Light/depth tokens
- Motion language (curves, durations, choreography)
- Color psychology system
- AI presence techniques (anti-AI-theater compliant)
- Interaction philosophy
- Homepage transformation spec
- Tile visual redesign
- Typography ramp + weights
- Spatial rhythm scale
- Anti-pattern additions to existing locked list
- Implementation phasing (12A → 12X) — but ONLY tokens + treatments, NO new components

If the 4 models cannot converge on any item, the master MUST document the dispute and recommend a default with reasoning.
