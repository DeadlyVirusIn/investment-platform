# Creative Direction — Spine Commitment

**Status**: accepted 2026-05-15
**Phase**: K (Creative Direction)
**Authority**: load-bearing for every subsequent artifact

---

## Product category statement

> **A reading environment with financial intelligence embedded inside it.**

Supersedes prior framings: "dashboard," "copilot," "AI-native investing OS."

This is the canonical category. Every artifact, every component, every pixel inherits from this statement. When a future decision conflicts with this category, the category wins.

## The spine sentence

> **An AI-authored investing briefing environment.**

Not a dashboard. Not a chatbot. Not a magazine. A *place* the user visits to receive the day's briefing from a strategist that already did the thinking — and can be asked back when the user wants more.

## Why hybrid

Pure Publication (Stratechery, FT, NYT product pages) gets editorial voice right but loses personalization + AI-native dimension. Pure Companion (ChatGPT, Granola, Pi, Mem.ai) gets AI-presence right but loses finite + edited dimension.

Hybrid resolves both:

- *Publication discipline*: edited, finite, daily issue, masthead, intentional arrival
- *Companion presence*: the AI has voice, conviction, and is queryable — but without character or mascot
- *Environment*: not a document, not a thread — a space inhabited

## Anonymous editorial authority

The strategist has **no name**. No "Atlas." No "The Desk." No sigil. No mascot. No assistant branding.

The AI's presence is carried entirely by:

- The quality and consistency of editorial voice
- Typographic precision
- Compositional authority
- Material identity

Rejected explicitly:

- Named AI character ("Atlas," "Tide," "Ledger," etc.)
- Smallcaps attribution marks ("THE DESK")
- AI sigils, logos, sparkle marks, robot icons
- "Powered by AI" stamps
- Assistant-product branding patterns

The AI is *institutional editorial authority* — like FT's Lex column reads "Lex" as a desk without naming a person. Here, even the desk isn't named. The voice is the signature.

## Reference lineage (anchor references)

| reference | what we steal | what we explicitly reject |
|---|---|---|
| Stratechery (Ben Thompson) | Daily-issue cadence, finite reading session, single-author voice, long-form analysis treated as the product | All-text monotony; absence of personalization |
| Granola | Calm AI-native presence with typographic discipline | Transcript-first surface; conversation as primary mode |
| NYT Morning Briefing | Editorial pacing, "today's edition" framing, masthead, finite reading session | Generic, non-personalized, no AI voice |
| Bloomberg Businessweek (digital) | Dataviz as authored infographic in narrative flow, financial precision with editorial taste | Print legacy; ad-driven compromises |
| Linear (the product) | Restraint, geometric authority, motion that means something, monochrome confidence | Operational tooling vocabulary; engineer-facing |
| FT app dark mode | Material identity reference — closest existing dark-paper-with-cream | None — this is our closest material kin |

**Non-references — explicitly not inheriting from:**

- Bloomberg Terminal (engine-vocabulary tyranny; density without narrative)
- Robinhood (theater + casino energy; color confetti)
- Standard fintech SaaS (Plaid, Carta — generic navy/grey/card stacks)
- ChatGPT chat surface (open-ended, infinite scroll, no editorial structure)
- TradingView (operator surface; density without authoring)
- macOS Stocks dark mode (the mud trap)
- Notion AI (purple-highlight AI signaling)

## What the product inherits from each parent

### From Publication lineage

- **Daily issue framing**: every visit is "today's edition," not "the dashboard"
- **Masthead**: the briefing has a name + a date + an edition number
- **Edited finiteness**: the user finishes the briefing; there is a bottom to the page
- **One-author voice**: consistent across every surface
- **Byline + provenance**: every claim is sourced inline
- **Section discipline**: 3-5 sections per briefing; each earns its place
- **Atmosphere through type + composition**, not chrome

### From Companion lineage

- **The strategist has voice**: present through intelligence, not mascot
- **The strategist has confidence states**: when uncertain, says so
- **The user can ask back**: one signature interaction
- **Reasoning is visible**: source citations and rejected alternatives surface as the strategist's work

### The hybrid's own innovation

- **Briefing-as-environment**: not a document (you can interact), not an app (you don't use it for an hour). A place you visit, read, ask one thing, close.
- **Generative composition**: layout responds to the day's character. Quiet days look visually quiet. High-conviction days look visually different.

## The single visual philosophy sentence

> **Authored restraint with an institutional voice.**

Every visual decision passes this test. If a UI element doesn't read *authored* (someone with taste made it on purpose), doesn't carry *restraint* (it earns its space), and doesn't relate to the *voice* (consistent with the editorial register), it doesn't belong.

## The single gesture (interaction signature)

> **Ask one thing back.**

After reading any section the user can ask one follow-up. Not a chat window. Not a thread. A single-question slot opens inline beneath whatever the user clicked. The strategist answers in the same voice as the briefing.

No chat tab. No prompts library. No persistent history. Read → ask one thing → answer → close.

Specific rarity rules (see `CREATIVE_DIRECTION_STUDIES.md`):

- Maximum 1-3 ask-back instances per briefing
- Never two within the same viewport
- Reserved for Tier 1 setups, decisive Holdings, conviction moments, deep pages

## The signature visual moment

> **The daily masthead.**

Editorial-grade typographic mark at the top of today's edition. Not a logo. Not a nav. A masthead. Date. Edition number. Set in Newsreader at editorial scale.

This is the visual moment the user remembers.

## The day-cycle feel

| time | feel |
|---|---|
| 6 AM | Pre-market quiet. Yesterday's edition fading. "In preparation" mark on masthead. |
| 9:30 AM | Today's edition lands. First reveal of the day. Cinematic moment. |
| Midday | Stable. Quote refreshes happen quietly under the surface. |
| 4 PM ET | Close. Edition gets "today's outcome" coda. |
| Evening / midnight | Today's edition stays available, reads as yesterday's record with slight tonal shift. |

The product *has a day*. It is not stateless.

## The imagined designer

Composite taste fingerprint:

- **Mark Porter** (former NYT/Guardian creative director — editorial typography with calm authority)
- **Karri Saarinen** (Linear — restraint + motion + geometric confidence)
- **Robin Rendle** (writer-designer — type-as-system, gentle materiality)
- **Massimo Vignelli** (NYC subway, American Airlines — restraint as ideology)

Not:

- David Carson (too expressive)
- Stefan Sagmeister (too theatrical)
- Generic SaaS design teams (defaulted)

The product should feel made by *one person with strong opinions about typography and silence*.

## The one rule that, if broken, kills the product

> **The engine's vocabulary may never appear in the user-facing layer.**

Words like *composite confidence, would_trade_count, shadow run, rule_id, promotion_gate, thresholds_met* — engine words. Never visible. Not in copy. Not in tooltips. Not in drawer footers. Not in URL slugs the user sees.

The strategist talks like a strategist. The engine talks to itself.

This is the load-bearing wall of the spine.

## What this commits us to NOT being

- A dashboard with editorial polish
- A chat product
- A magazine (we're not just text)
- A terminal (we're not engineer-facing)
- An app a power user lives in for hours
- A product that competes on feature breadth
- A generic fintech aesthetic

## What this commits us to being

- A daily briefing the user *visits*
- A finite reading session with optional follow-up
- A product that has a *day*
- A product with anonymous institutional voice
- A product that feels *authored* by someone with taste
- A product where AI-nativeness is visible without being theatrical

## Phase J retirements committed by this spine

- Gold accent token (`--opt-color-conviction-gold`) — retired
- Paper noise SVG texture — retired
- Strategist-naming patterns — retired before introduction
- AI sigil / mark concepts — retired before introduction

## Linked artifacts

- `CREATIVE_DIRECTION_VOICE.md` — Editorial Authority + Voice System
- `CREATIVE_DIRECTION_CHROME.md` — Chrome + Density Philosophy
- `CREATIVE_DIRECTION_STUDIES.md` — Field vs Structure Studies
- `CREATIVE_DIRECTION_COLOR_MATERIAL.md` — Color + Material Philosophy
- `CREATIVE_DIRECTION_TYPOGRAPHY.md` — Typographic Precision System *(in progress)*
