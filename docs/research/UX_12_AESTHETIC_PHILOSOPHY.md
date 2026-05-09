# UX-12 Aesthetic Philosophy — Master

**Status:** locked after 3-round adversarial debate (Gemini · Codex · Claude Opus 4.7 · Claude Sonnet 4.6)
**Date:** 2026-05-09
**Pivot:** UX-10 + UX-11 components are right; the substrate is wrong. Move from "dark dashboard" to "AI-native editorial cockpit" via tokens + treatments only — NO new components, NO new schemas, NO new routes.
**Debate transcripts:** `docs/research/debates/UX_12_aesthetic/`
**Parent specs:** `docs/research/UX_10_CONVICTION_ENGINE.md`, `docs/research/UX_11_INTERACTIVE_COPILOT.md` (every invariant inherited).
**Implementation isolation:** parallel route `/overview?view=cockpit` (same pattern as 9D / 10D / 11D). Default `/overview` and `?view=working`, `?view=stream`, `?view=conviction`, `?view=copilot` all unchanged until cutover (Phase 12X).

---

## TL;DR

UX-10 and UX-11 ship structurally honest research. They feel like a dark dashboard because the **substrate is uniform**, not because the components are wrong. UX-12 changes substrate only.

**Single load-bearing principle (4-way convergent):**

> **The product becomes AI-native at the moment a synthesized 36px Source Serif posture sentence appears on a warm-near-black two-zone canvas, above one hero tile, with the timestamp ticking quietly in the corner.**

Five universal moves: dark two-zone canvas (`#13161B` stage / `#0F1115` shop, hard 1px cut at 40vh) · Source Serif 4 hero posture sentence at 36px · page-state narration line · decision sentence weight tracks confidence tier · ambient timestamp ticks every 60s. **Zero ambient motion.** No card chrome.

---

## Section 1 — Locked across all 4 models (universal agreement)

These ship with no remaining dispute. Cross-model attribution.

| # | Decision | Attribution |
|---|----------|-------------|
| L1 | **Dark warm-near-black canvas with two-zone luminance.** Stage `#13161B` (top 40vh) / Shop `#0F1115` (bottom 60vh). 1px hard cut between zones. NO gradient sweep. | Opus R1 contribution · Sonnet R2 conceded · Gemini R3 conceded |
| L2 | **Synthesized posture sentence as the canonical AI hero.** Third-person, present-tense, observational. *"The market is narrow today; conviction is concentrated in two names."* 36px, max-width 760px, max 2 lines. | Codex R1 contribution · Sonnet R2 conceded · Opus R2 conceded · Gemini R3 conceded |
| L3 | **Page-state narration line.** *"3 to look at" / "Quiet morning" / "Watching 2 more"* — 11–12px Inter regular, top-left, low contrast. Sits ABOVE the hero serif. | Sonnet R1 contribution · all 3 others adopted |
| L4 | **Decision sentence weight tracks confidence tier.** Confirmed/Conviction = Inter 500. Working/Forming = Inter 400. Same color, same size, weight is the instrument. | Gemini R1 contribution · Sonnet R2 + Opus R3 + Gemini R3 conceded |
| L5 | **Editorial serif typeface for hero only.** Source Serif 4 / Charter / Tiempos at 36px / 400 / -0.012em / 1.25 leading. Inter for everything else (decision, body, page-state). Mono for tabular metadata only. | Opus R1 contribution · Sonnet R2 conceded · Gemini R3 conceded |
| L6 | **Five-size type ramp, explicitly amended from four-size lock.** Hero serif 36 / Section serif 22 / Decision Inter 16 / Body Inter 14 / Meta mono 11. | All 4 R3 — explicit amendment, not smuggled override |
| L7 | **Ambient currency line.** *"as of 09:24, market 41 min in"* at 11px tabular nums. Ticks every 60s via natural number change. Top-right of stage zone. NO animation. | Sonnet R1 contribution · 3 others adopted |
| L8 | **No card chrome.** Borders soften to `rgba(255,255,255,0.04)` hairline (visible enough to bound, invisible enough not to feel boxy). NO box-shadow on tiles. NO background fills. NO rounded corners on tile (4px radius only on verb pill). | Sonnet R1 contribution (radical "remove all" softened) · all 4 R3 converged on hairline |
| L9 | **Schema-preserving hero composition.** 304×184 ConvictionTile schema **unchanged** (UX-11 lock holds). Hero gets 2-column grid span + 32px internal padding + warmer stage-zone placement. Subordinates get 1-column + 14px padding + cooler shop-zone placement. | Sonnet R2 correction of Opus R1 480×320 schema break · 3 others adopted |
| L10 | **Motion budget: 220ms components, 340ms staggered orchestration, ZERO ambient motion.** iOS curve `cubic-bezier(0.32, 0.72, 0, 1)`. Cinematic = staggered, not longer. | Sonnet R1 + R2 · 3 others converged |
| L11 | **Reflow on conviction shift requires explicit refresh trigger.** NEVER auto-reflow during active read (preserves spatial memory). | Opus R2 critique landed · Sonnet R3 conceded |
| L12 | **Hover behavior: hovered tile 100% opacity, adjacent tiles → 0.88.** NOT 0.4 (reads as disabled). Linear's row-focus pattern. | Sonnet R2 critique of Gemini R1 · all converged |
| L13 | **Whitespace is the proof of intelligence.** Spacing scale `4, 8, 12, 16, 24, 32, 48, 64, 96, 128`. Hero top 96px. Hero-to-tile drop 80px ("magazine drop"). Section gap 96px. | Gemini R1 phrase · all adopted |

**Lock these 13. They are the substrate change.**

---

## Section 2 — Disputes documented

For each dispute, master picks default + records dissent so future PMs can re-open.

### D1 — Light vs dark canvas (3-vs-1)

| Position | Models | Argument |
|----------|--------|----------|
| **Dark warm-near-black** (`#0B0B0E` / `#13161B` zones) | Sonnet, Opus, Gemini — **MASTER DEFAULT** | Capital allocation gravitas. Linear/Bloomberg/Stripe-Dashboard/Robinhood-dark/Webull all dark. Light would push toward Robinhood/Acorns/Public consumer-toy category. Burns eyes at 1am. |
| Light theme (`#F7F4EE` warm daylight) | Codex | Linear/Arc/Stripe/Perplexity/Apple-Notes default light. Premium consumer AI products = light. |

**Master locks dark.** Codex's light-theme proposal is the most thoughtful dissent in the debate; documented as **"explored alternative for future user testing."** Do not foreclose; do not ship.

### D2 — Hero typeface: serif vs sans (2-vs-2)

| Position | Models | Mechanism |
|----------|--------|-----------|
| **Source Serif 4 / Charter for the 36px hero** | Opus + Sonnet R2 — **MASTER DEFAULT, A/B candidate** | Editorial register signals *authored*. FT.com / Stratechery precedent. Single-font decision does what 100 motion ms cannot. |
| One sans family (Inter / Geist) at 36-48px with weight | Codex + Gemini (mixed) | Avoids "newsletter tone" / "identity churn." |

**Master locks serif (Source Serif 4) as 1-week A/B candidate.** Lowest-risk place to dissent — adding ONE typeface for ONE element is the cheapest, most-reversible aesthetic move available, and it's the highest-emotional-leverage move identified in any R1.

### D3 — Stage-zone amber tint percentage

| Position | Models | Value |
|----------|--------|-------|
| **2.5% static amber** (`hsla(35, 60%, 50%, 0.025)`) | Sonnet R3 + Opus R3 compromise — **MASTER DEFAULT** | Below conscious detection but supplies "lit room" feeling. Static — never state-mapped. |
| 3% amber | Opus R1 | More perceivable warmth. |
| 0% (pure luminance shift only) | Sonnet R1 | Avoid all warmth tinting. |

**Master locks 2.5%.** Inside the stage zone only. Single fixed neutral color. NEVER state-mapped (rejecting Gemini's R1 conviction-density hue).

### D4 — Per-verb temperature shifts (3-vs-1)

| Position | Models | Mechanism |
|----------|--------|-----------|
| **Banned — mood-ring violation** | Sonnet, Opus, Gemini — **MASTER DEFAULT** | "OPEN context: warm amber-peach 22% / TRIM context: cooler silver-blue" is mood-ring scoped to verb-context. Either mood-ring is on or off; "off, except by verb" is incoherent. |
| Permitted as "temperature, not semantics" | Codex R1 | Warmth = guidance, coolness = analysis. |

**Master locks ban.** Temperature lives in the canvas (static), not in per-verb backgrounds. Codex dissent documented.

### D5 — Reflow on conviction shift mid-session

| Position | Models | Mechanism |
|----------|--------|-----------|
| **Explicit refresh trigger only** | Opus, Sonnet R3 conceded — **MASTER DEFAULT** | Spatial memory beats AI-action-by-stealth. User reads tile, looks away, looks back, tile must NOT have moved. |
| Auto-reflow with 340ms staggered animation | Sonnet R1 (conceded) | "AI demonstrates by acting." |

**Master locks explicit-trigger only.** Conviction shift surfaces as a single 11px contextual label (`REGIME SHIFTED 6H AGO`); reflow happens on cmd-R / refresh action / session-boundary, never invisibly mid-read.

---

## Section 3 — Visual philosophy manifesto

**Editorial Cockpit, not Consumer Toy.**

The page is dark because financial decisions are serious. The page has a single bright focal point (the stage zone with the serif hero) because magazines have headlines. The page narrates its own state because intelligence is a process, not an artifact. The page never performs "AI-ness" because no one wants their investing strategist to be theatrical — they want it to be **right**.

References: Linear's editorial whitespace + FT.com's serif gravitas + Apollo Mission Control focal lighting + Stripe Dashboard restraint + Arc/Perplexity composition. NOT: Bloomberg density · Robinhood casino · Apple consumer airiness · Material Design.

One sentence: **Calm canvas, two-zone luminance, editorial serif posture, page-state narration, invisible chrome, ambient currency, present AI without theater, zero ambient motion.**

---

## Section 4 — Emotional hierarchy (six-stop ride)

| Stop | Element | Time | Visual |
|------|---------|------|--------|
| 1 | **Page atmosphere** — stage warmer than shop | 0-200ms | registered without reading |
| 2 | **Page-state line** — "3 to look at" | 0.5-1s | 11-12px Inter regular, top-left |
| 3 | **Hero posture sentence** — "The market is narrow today..." | 1-2.5s | 36px Source Serif 4, max 2 lines |
| 4 | **Hero tile decision sentence** | 2.5-4s | 16px Inter, weight tracks tier |
| 5 | **Subordinate tiles decisions** | 4-5s+ | 14px Inter, shop zone, 1-col each |
| 6 | **Metadata + ambient timestamp** | always | 11px tabular, low contrast |

The eye must FALL down the page, never SCAN across. Linear's Inbox does this; Bloomberg does the opposite.

---

## Section 5 — Light/depth tokens (locked)

```css
:root, .ux12-cockpit {
  /* === Two-zone canvas === */
  --ux12-canvas-stage:    #13161B;   /* top 40vh, hero region, slightly warmer */
  --ux12-canvas-shop:     #0F1115;   /* bottom 60vh, working region */
  --ux12-canvas-deep:     #0B0D10;   /* page chrome, footer */
  --ux12-canvas-elev:     #131319;   /* drawer surface, slightly cooler */

  /* === Hairline === */
  --ux12-hairline:        rgba(255, 255, 255, 0.04);   /* tile borders, zone divider */
  --ux12-hairline-strong: rgba(255, 255, 255, 0.08);   /* hover/focus only */

  /* === Stage tint (2.5% static, NOT state-mapped) === */
  --ux12-stage-tint: radial-gradient(
    ellipse 80% 50% at 50% 0%,
    hsla(35, 60%, 50%, 0.025) 0%,
    transparent 70%
  );

  /* === Ink levels === */
  --ux12-ink-hero:        #F4F4F7;   /* hero, decision, ticker */
  --ux12-ink-body:        #A8A8AF;   /* body, evidence */
  --ux12-ink-meta:        #6B6B72;   /* metadata, timestamp */
  --ux12-ink-recede:      #48484E;   /* dimmed/inactive */
}
```

**Hard 1px cut between stage and shop at 40vh.** No gradient sweep. No box-shadow on tiles. Depth = luminance + spatial separation only.

**Banned:** glassmorphism (`backdrop-filter: blur`), animated ambient blobs, conviction-density-mapped hue, purple-blue AI gradients, card-level gradients, drop-shadow theater (`0 18px 50px rgba(0,0,0,0.28)` REMOVED — Sonnet correctly noted Linear has none).

---

## Section 6 — Motion language (locked)

| Motion | Duration | Curve | Trigger |
|--------|----------|-------|---------|
| Hover | 140ms | `cubic-bezier(0.2, 0.6, 0.2, 1)` | mouse over |
| Drawer open | 220ms | `cubic-bezier(0.32, 0.72, 0, 1)` (iOS) | tile click |
| First-paint orchestration | 340ms total (180ms each, 30ms stagger) | iOS curve | mount |
| Reflow on conviction change | 340ms staggered | iOS curve | **explicit refresh / session boundary only** |
| Timestamp tick | 0ms (number change only) | n/a | every 60s |

**Cinematic = staggered orchestration, never longer single curves.** Apple's iOS app launch is 320ms total composed of 4 staggered 180ms transitions.

**Banned (all 4-way agreement):**
- Breathing/pulsing on AIRead opacity (Opus R1 conceded)
- Cursor lean-in / proximity magnification (Opus R1 conceded — broken on touch + CLS)
- Depress-on-click compression on tile-as-trigger (Gemini R1 banned — theater dressed as tactility)
- Glowing dots, pulsing borders, shimmer
- Auto-reflow during active read

Reduced-motion `@media (prefers-reduced-motion: reduce)`: all transitions instant, opacity-only fades. No translation.

---

## Section 7 — Color psychology (locked)

| Where | Color |
|-------|-------|
| **Warmth** lives in canvas | `#0B0B0E` 2% red-shifted, plus 2.5% static amber stage tint |
| **Coolness** lives in drawer | `--ux12-canvas-elev` `#131319` slightly cooler hue |
| **Tier color** | monochrome dot, four luminance steps (`#F4F4F7` → `#A8A8AF` → `#6B6B72` → `#48484E`). Same hue, different luminance. NO hue shift across tiers. |
| **Decision sentence weight** | confidence tier instrument. Confirmed/Conviction = Inter 500, Working/Forming = Inter 400. (Gemini R1 contribution.) |
| **Verb pill** | monochrome `#9CA3AF`, ≤25% saturation, NEVER colored, NEVER tinted fill |
| **Saturation ceiling** | ≤30% inside any tile (Sonnet's tighter cap). UX-10's ≤50% on accent unchanged. |

**Banned:** per-verb temperature tints, tier-mapped card backgrounds (Gemini R1 conceded), `#C24A4A` semantic red on tile (Opus R1 conceded — luminance contrast only for invalidation distance).

---

## Section 8 — AI presence (5 anti-AI-theater compliant techniques)

1. **Synthesized posture sentence** (Codex) — "The market is narrow today; conviction is concentrated in two names." 36px Source Serif 4, third-person, present-tense.
2. **Page-state narration** (Sonnet) — "3 to look at" / "Quiet morning" / "Watching 2 more." 11-12px Inter, top-left.
3. **Editorial serif typeface on hero** (Opus) — Source Serif 4 signals *authored intelligence*.
4. **Decision sentence weight tracks tier** (Gemini) — typographic instrument. Same color, same size, weight is presence.
5. **Ambient currency line** (Sonnet) — "as of 09:24, market 41 min in" — ticks every 60s via natural number change. The page is alive because the *content is current*, not because pixels oscillate.

**Reflow on conviction shift** (Sonnet R1, defanged per Opus R2) — explicit refresh trigger only. AI demonstrates by acting, but never under the user's eyes mid-read.

**Banned (4-way agreement):** breathing labels, cursor lean-in, glowing dots, pulsing borders, color-coded verb temperature, biomorphic copy ("AI heartbeat"), depress-on-click, AI orb, chat dock, suggested-question chips, persona name, first-person pronoun outside hero.

---

## Section 9 — Interaction philosophy

**Premium = consequence-rich, friction-free, undo-cheap.** Linear/Arc grammar.

- Every keystroke does something (`j`/`k` between tiles, `Enter` opens drawer, `Esc` closes).
- Hovers reveal one fact (freshness gains +5% luminance), never a tooltip.
- Click does ONE thing immediately. Never depresses-then-acts.
- Hover at 120ms primes drawer DOM (mount as display:none → block) so click feels instantaneous.
- Drawer dismissed → originating tile receives 400ms highlight (anchor return).
- No double-confirms. Destructive actions get 4-second toast undo.
- Sound: zero. Mobile: one light haptic on drawer open.

---

## Section 10 — Homepage transformation (before / after)

### Before (current `/overview?view=copilot`)

```
TODAY'S AI READ
The AI is becoming more selective after this rally.
Add only where earnings durability offsets valuation risk.

[Tile NVDA 304×184] [Tile TSLA 304×184] [Tile MSFT 304×184]
   ← three equal tiles, equal weight, dark uniform canvas
```

### After (UX-12)

```
                                          as of 09:24, market 41 min in   ← 11px mono ambient

3 to look at                                                              ← 12px Inter regular, page-state

The market is narrow today;                                               ← 36px Source Serif 4, hero posture
conviction is concentrated in two names.                                   ← line 2 of hero, max width 760px

══════════ stage / shop hard cut at 40vh ══════════════════════════════

┌─────────────────────────────────────────────────────────────┐
│ HERO TILE (304×184 schema, 2-col span, 32px padding)         │  ← rotates daily
│  OPEN  ●●●●  Confirmed · 14h                                 │
│  NVDA · Semis cycle continuation                              │
│  Add through $172 while data-center margin expansion holds.  │  ← 16px / 500 (tier-tracked)
│  Bull · capex +22% YoY                                       │
│  Bear · hyperscaler rollover risk                            │
│  Invalid < $158 · Horizon ~6w                                │
└─────────────────────────────────────────────────────────────┘
                                                                  ← 32px gap
┌──────────────┐  ┌──────────────┐                                ← 304×184 each, 1-col
│ TRIM TSLA    │  │ HOLD MSFT    │                                ← 14px padding
│ ...          │  │ ...          │                                ← 14px / 400 decision
└──────────────┘  └──────────────┘

  Watching 2 more
```

The "after" is mostly **air**. That is the entire point.

---

## Section 11 — Tile redesign

**Schema preserved (304×184).** Treatment changes only.

- **Borders:** subtle `rgba(255,255,255,0.04)` hairline (concession from Sonnet R1 "remove entirely").
- **Background:** matches zone (stage for hero, shop for subordinates). NO fills.
- **Shadow:** ZERO (Sonnet correctly noted Linear has zero).
- **Border radius:** 4px on verb pill only. Sharp on tile.
- **Hero:** 2-col grid span + 32px internal padding. Decision sentence stays 16px (preserves UX-11 L6 card-local).
- **Subordinate:** 1-col + 14px internal padding. Decision sentence 14px.
- **Hover:** hovered tile 100% opacity, adjacent → 0.88 (NOT 0.4 — that reads as disabled).
- **Decision sentence weight = confidence tier** (Gemini's contribution).

---

## Section 12 — Typography (5-size, explicitly amended)

| Token | Size | Weight | Tracking | Leading | Family |
|-------|------|--------|----------|---------|--------|
| `--ux12-type-hero` | 36px | 400 | -0.012em | 1.25 | Source Serif 4 |
| `--ux12-type-page-state` | 12px | 400 | 0 | 1.4 | Inter |
| `--ux12-type-section` | 22px | 400 | -0.005em | 1.4 | Source Serif 4 |
| `--ux12-type-decision` | 16px | 400 / 500 | -0.005em | 1.45 | Inter (weight tracks tier) |
| `--ux12-type-body` | 14px | 400 | 0 | 1.5 | Inter |
| `--ux12-type-meta` | 11px | 400 | 0.02em | 1.4 | iA Writer Mono S / JetBrains Mono |

**Two faces:** Source Serif 4 (hero + section) + Inter (decision + body + page-state). Mono only for tabular metadata (timestamps, ambient currency).

**Verb pill** is a *glyph*, not a type size: 12px / 500 / 0.04em / Inter / uppercase / 4-char max.

**ALL CAPS budget:** 4-char verb pill + max ONE contextual regime label per page (`REGIME SHIFTED 6H AGO`). Everything else mixed case.

**No weight > 500** anywhere. Reject Codex's R1 620-weight hero as marketing-page energy.

---

## Section 13 — Spatial rhythm

```
Spacing scale: 4, 8, 12, 16, 24, 32, 48, 64, 96, 128

Page top padding:                  96px
Stage zone height:                 ~40vh
Page-state → hero serif gap:       24px
Hero serif → first tile gap:       80px (the "magazine drop")
Hero tile internal padding:        32px
Subordinate tile internal padding: 14px
Tile gap (horizontal):             32px
Tile gap (vertical):               24px
Section gap:                       96px
Side padding:                      clamp(24px, 6vw, 128px)
```

Linear's ratios. UX-11 was at Bloomberg spacing on a near-Linear color palette — that was the precise diagnosis.

---

## Section 14 — Anti-pattern additions (extends UX-10/11 lock list)

| Anti-pattern | Reason | Banned by |
|--------------|--------|-----------|
| Page-tied background-hue mapping | Extends mood-ring ban to per-tier card tints | Sonnet R3 |
| Persistent ambient motion loops | Extends anti-pulse to "breathing" rebrand | Sonnet R2 critique landed; Opus R3 conceded |
| Cursor-proximity scale or position changes | Anthropomorphic Narcissism (Gemini's phrase) | Sonnet R2 + Codex R3 + Gemini R3; Opus R3 conceded |
| Depress-on-click compression on tile-as-trigger | Theater dressed as tactility | Sonnet R2 + Codex R3 |
| Equal-weight first viewport | One item MUST have spatial privilege (Codex R1) | All 4 |
| First-load animation > 360ms total | Casino motion budget | Sonnet R3 |
| Semantic red on invalidation distance text | Smuggled semantic red — luminance contrast only | Sonnet R2 critique landed; Opus R3 conceded |
| Drop-shadow stack on tiles | Linear has zero shadows; we have zero | Sonnet R3 |
| Light-theme canvas | Wrong polarity for capital allocation | Sonnet, Opus, Gemini (Codex dissents) |
| Per-verb temperature shifts | Mood-ring scoped to verb-context | Sonnet, Opus, Gemini (Codex dissents) |
| Auto-reflow during active read | Breaks spatial memory | Opus R2 critique; Sonnet R3 conceded |
| Hero typeface > 500 weight | Marketing-page energy | Sonnet R3 |
| Mid-tile background gradient | UX-10 §11.3 carry-forward | All |
| Tinted card surface fills | Mood-ring | All |
| 4-size lock as smuggled override | Frame as explicit amendment | Sonnet R2 |

Combined with UX-10 §12 (29 items) + UX-11 §13 (15 items) + UX-12 (above 14 items) = **58-item locked anti-pattern list.**

---

## Section 15 — Implementation phasing (12A → 12X)

**Tokens + treatments only. NO new components. NO new schemas. NO new routes (until 12X cutover).**

| Phase | Scope | Files | Risk |
|-------|-------|-------|------|
| **12A** | UX-12 tokens (scoped `.ux12-cockpit`) — canvas zones + hairlines + ink levels + stage-tint + amended type ramp + spacing scale | `apps/web/src/lib/copilot/ux12_tokens.css` | Low |
| **12B** | Source Serif 4 typeface load (Google Fonts or self-host); Inter weight 500 added | `apps/web/index.html` + tokens | Low |
| **12C** | New surface treatment: `.ux12-cockpit` wrapper applies dark two-zone canvas + stage-zone amber tint + page-state line + hero serif + ambient timestamp | New page wrapper component (single file) | Low |
| **12D** | ConvictionTile treatment: subtle hairline borders, no shadows, no fills, hero gets 2-col span + 32px padding, decision sentence weight tracks tier | CSS-only modifications to existing `ConvictionTile.tsx` (no new schema) | Low |
| **12E** | Mount `CopilotCockpitView` page at `/overview?view=cockpit` (parallel route, additive branch) | `OverviewRouteSwitch.tsx` (additive only) | Low |
| **12F** | Composer additions: `pageStateText` ("3 to look at"), `posturesentenceText` (synthesized posture), `ambientTimestamp` (recomputed every 60s) | `copilot_compose.ts` extension | Low |
| **12G** | Motion polish: 30ms-staggered first-paint orchestration; hover dimming on adjacent tiles to 0.88 | CSS only | Low |
| **12H** | Voice composer additions: posture-sentence slot grammar (`stance + qualifier + consequence`), banned-token list extended | `voice_composer.ts` extension | Low |
| **12X** | Cutover — default `/overview` → cockpit view. UX-11 copilot view archived as `?view=copilot`. UX-10 conviction archived as `?view=conviction`. UX-9 stream archived as `?view=stream`. UX-8B PRESSURED archived as `?view=condition`. | `OverviewRouteSwitch.tsx` default branch swap | High — visible default change |

**Validation gates:**
- After 12E: user emotional validation at `/overview?view=cockpit` with PROOF fixtures. Compare emotional response vs `?view=copilot`. If UX-12 doesn't read as "AI-native editorial cockpit" within 5 seconds, diagnose before continuing.
- After 12G: full motion polish review.
- Before 12X: 1-week staging window with both `?view=copilot` and `?view=cockpit` available; user toggles default.

**Total scope:** ~9 phases, mostly CSS + composer additions. NO new schemas. NO new components. Existing `ConvictionTile`, `AIReadHero`, `ReasoningDrawer` all reused with treatment overrides via `.ux12-cockpit` parent class.

---

## Section 16 — UX-10 + UX-11 invariants inherited (no changes)

UX-12 is a SUBSTRATE layer. Every UX-10 + UX-11 invariant survives intact:

- **The 4 verbs** (`OPEN · HOLD · TRIM · EXIT`)
- **The 4 confidence tiers** + dot glyph
- **The 4 freshness states**
- **Bear-case-mandated** for `Confirmed`+ tier (composer invariant)
- **Invalidation appears before target** (rendered wherever full thesis shown)
- **STRUCTURE for options**; loss-named-first; defined-risk default
- **ConvictionTile schema 304×184 + 5 rows + refuses-to-render**
- **Drawer modal sheet, 9 sections, single scroll, 220ms iOS curve**
- **URL state `?drawer=<TICKER>`**
- **Mixed AI voice regime** — third-person hero, implicit body
- **13 trust safeguards** as engineering invariants
- **Anti-AI-theater bans:** no orb, chat dock, suggested-question chips, "Powered by AI" badge, typing animation, persona name, first-person pronoun outside hero, auto-open onboarding
- **Composer-level refuses-to-render schemas**
- **Banned-token voice lint**

**The single change UX-12 makes to a UX-11 lock:** explicit amendment of the four-size type ramp to **five sizes** (frame openly as deliberate amendment, not smuggled override).

---

## Section 17 — Debate provenance

3-round adversarial debate held 2026-05-09 between four models per `/octo:debate` skill. **Pure product experience design — NOT implementation.**

| Model | R1 words | R2 words | R3 words |
|-------|----------|----------|----------|
| Gemini | 2,202 | 1,437 | 1,214 |
| Codex (gpt-5.5) | ~5,200 (post-prompt-echo) | ~5,000 (post-echo) | ~3,200 (post-echo) |
| Sonnet 4.6 (Agent) | 3,820 | 2,924 | 2,371 |
| Claude Opus 4.7 (moderator) | 3,131 | 2,448 | 2,142 |

**Total ~33,000 words of independent argumentation.**

Source files:
- Brief: `docs/research/debates/UX_12_aesthetic/BRIEF.md`
- R1: `docs/research/debates/UX_12_aesthetic/round1/{gemini,codex,sonnet,opus}_r1.md`
- R2: `docs/research/debates/UX_12_aesthetic/round2/{gemini,codex,sonnet,opus}_r2.md`
- R3: `docs/research/debates/UX_12_aesthetic/round3/{gemini,codex,sonnet,opus}_r3.md`

**Convergence pattern:** Strong 4-way convergence on substrate (dark canvas, two zones, serif hero, page-state, ambient timestamp, no card chrome, zero ambient motion). Two real disputes documented (light theme, ambient breathing). Two minor disputes documented (per-verb temperature, cursor lean-in — both 3-vs-1 bans). The 4-way agreement on "the failure is substrate, not components" is itself the most important consensus — it means UX-12 ships as tokens + treatments, not new components.

**Single most cited contribution across rounds:** Codex's R1 hero posture sentence ("The market is narrow today; conviction is concentrated in two names") — adopted by all 4 in R3 as the canonical AI hero. Combined with Opus's R1 serif typeface contribution, it produces the master organizing principle:

> **The product becomes AI-native at the moment a synthesized 36px Source Serif posture sentence appears on a warm-near-black two-zone canvas, above one hero tile, with the timestamp ticking quietly in the corner.**

---

## Section 18 — What this master deliberately does NOT lock

- Specific copy for posture-sentence examples beyond format constraints (composer template, A/B testable).
- Specific Source Serif 4 self-host strategy (Google Fonts CDN vs self-host — performance decision, deferred to 12B).
- Mobile breakpoint specifics below 480px (Phase 12G+ refinement).
- Specific telemetry on user emotional response to substrate change.
- Migration story for users in flight on the previous view (will be designed at 12X cutover).

---

**End of master. Lock as `docs/research/UX_12_AESTHETIC_PHILOSOPHY.md`. Do not rewrite without re-running the 4-way debate.**
