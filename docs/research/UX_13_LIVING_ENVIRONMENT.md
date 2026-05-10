# UX-13 Living AI-Native Environment — Master

**Status:** locked after 3-round adversarial debate (Gemini · Codex · Claude Opus 4.7 · Claude Sonnet 4.6)
**Date:** 2026-05-10
**Pivot:** UX-12 fixed substrate; UX-13 fixes COMPOSITION. Move from "beautifully designed dashboard" to "AI-native investing operating system" via 3 named rooms chosen at session-load + verb-anchor-point + aspect-ratio taxonomy + session memory line. NO new components, NO new schemas, NO new routes.
**Debate transcripts:** `docs/research/debates/UX_13_environment/`
**Parent specs:** UX-10/11/12 masters (all invariants inherited).
**Implementation isolation:** parallel route `/overview?view=living` (same pattern as 9D / 10D / 11D / 12X). Default `/overview` and all other `?view=*` parallels remain unchanged until cutover.

---

## TL;DR

UX-12 fixed the substrate. UX-13 fixes the composition.

**Single load-bearing principle (4-way convergent):**

> **The page is one of three named rooms (Solo / Duet / Field) chosen by the AI at session-load. The composition itself is the AI's voice.**

Five universal moves: 3 named rooms · verb-anchor-point fixed across rooms · aspect-ratio taxonomy (hero/sub/watchlist/context) · "since you left" delta line · 3-zone luminance ladder (stage/shop/deep). One acceptance test (Codex): **if the user reads 4 tiles in 5 seconds, UX-13 has failed.**

Canonical justification (Gemini, locked verbatim):

> **"Equal rectangles imply the system has not decided."**

---

## Section 1 — Locked across all 4 models

| # | Decision | Attribution |
|---|----------|-------------|
| L1 | **3 named rooms (Solo / Duet / Field)** chosen at session-load by AI's editorial read. Composition name implicit in posture sentence. | 4-way convergence (Sonnet's naming wins) |
| L2 | **Verb-anchor-point fixed across rooms.** Single (x,y) where the verb-glyph lives is identical across Solo / Duet / Field. What changes is what surrounds it, not where it begins. | Sonnet R2 synthesis bridging Opus's persistent-slots concern |
| L3 | **Aspect-ratio taxonomy.** 4 categories: hero 1.65:1, sub 1.65:1, watchlist 0.5:1 narrow-tall, context band 6:1 wide-short. Different shape = different category. | Opus R1 contribution · Sonnet R2 adopted |
| L4 | **"Since you left" delta line.** Single 11px mono line below ambient timestamp. Says "Since 09:18 yesterday: NVDA conviction +0.3" or "Since you left: nothing changed." Honest absence is itself AI presence. | Opus R1 contribution · Sonnet R2 adopted |
| L5 | **3-zone luminance ladder** — stage (top 40vh, `#13161B` warm) / shop (40vh+, `#0F1115`) / deep (below-fold, `#0B0D10` coolest). Extends UX-12's two zones. | Opus R1 + 4-way adoption |
| L6 | **Layout decided once at session-load.** Never auto-shifts mid-session (UX-12 spatial-memory lock holds). Refresh recomposes. | Universal carry-forward |
| L7 | **Acceptance test (Codex):** "If user reads 4 tiles in first 5 seconds, UX-13 has failed." Measurable. | Codex R1 · Sonnet R2 + R3 adopted |
| L8 | **Canonical justification (Gemini, verbatim):** "Equal rectangles imply the system has not decided." | Gemini R1 · all R3 adopted |
| L9 | **40vh hard cut inviolable.** Verb-glyph spans the cut (Sonnet R2 synthesis); hero envelope stays above. The eye crosses the horizon, not the object. | Sonnet R2 synthesis of Codex R1 contribution |
| L10 | **Hero left-anchored** in cols 1-7 of 12. Negative well right (cols 8-12). Western F-pattern reading flow. | 3-vs-1 vs Codex (right-anchored documented) |
| L11 | **Solo-only halo at 4% amber.** Color-locked to UX-12 stage amber family (NOT pure gold). Never in Duet or Field. | Sonnet R2 narrowed · 3-vs-1 vs Codex's anti-glow |
| L12 | **Posture sentence carries mode signature.** Solo: "One thesis stands alone today." Duet: "Two theses, one challenger." Field: "Six theses forming." Subtle mode signaling. | Sonnet R1 · 4-way adoption |
| L13 | **Composition is the AI's voice, not text about the AI.** Solo = "I see one thing." Field = "I see noise." The room is the message. | 4-way convergence |

**Lock these 13. They are the composition change.**

---

## Section 2 — Disputes documented

### D1 — Verb-glyph at 36-48pt vs verb-pill 11px-only (1-vs-3)

| Position | Models | Mechanism |
|----------|--------|-----------|
| **Verb-pill 11px lock holds; verb-glyph at 36-48pt SHIPS as Phase 13C deliverable (monitored)** | Sonnet R4 + Opus R4 + Gemini R4 — **MASTER DEFAULT (updated R4)** | UX-10/11/12 verb pill is locked at 11px monochrome. The 36-48pt verb-glyph ships as a SEPARATE PAGE CHROME visual category. R4 mitigations + kill-trigger gate it against Codex's drift concern. See Section 12 D1 for details. |
| Verb-glyph 36-48pt would create "trade verb as poster" / action-pressure casino drift | Codex R4 KILL position | Production drift named. Kill-trigger documented. |

**R4 update (2026-05-10):** Master now SHIPS the verb-glyph as Phase 13C deliverable, NOT just documented experiment. Codex's drift concern → named kill-trigger at 13E acceptance gate. See Section 12 D1.

### D2 — Hero-anchor side (3-vs-1)

| Position | Models | Mechanism |
|----------|--------|-----------|
| **Left-anchored (cols 1-7), negative well right** | Opus, Sonnet, Gemini — **MASTER DEFAULT** | Western F-pattern reading flow. Magazine spread pattern (FT, NYT, Stratechery). |
| Right-anchored (upper-right optical center) | Codex R1 | Mass-on-right with reading flow left. |

**Master locks left-anchored.** ~~Codex right-anchored documented as future-experiment.~~ **R4 update:** Codex CONCEDED in R4 — "Western editorial reading patterns favor left mass with right-side negative well; less risky and more immediately legible." Right-anchored downgraded to "post-13X visual experiment after UX-13 room grammar is validated." 4-vs-0 left consensus. See Section 12 D3.

### D3 — Halo permitted (Solo-only) vs banned (3-vs-1)

| Position | Models | Mechanism |
|----------|--------|-----------|
| **Solo-only halo at 4% amber, color-locked to UX-12 amber family** | Sonnet R2 + Opus + Gemini — **MASTER DEFAULT** | Rare = restraint, daily = casino. Wes Anderson lit-from-above master shot. |
| All halos banned as casino | Codex R1 | "No glow. No halo. No gradient tiles." |

**Master locks Solo-only halo.** Codex anti-glow dissent documented.

### D4 — 40vh boundary crossing: hero (Codex) vs only verb-glyph (Sonnet R2 synthesis)

| Position | Models | Mechanism |
|----------|--------|-----------|
| **Verb-glyph crosses 40vh; hero envelope stays above** | Sonnet R2 synthesis · Opus R3 conceded · 3-vs-1 wins | Cleaner editorial. Eye crosses horizon, not object. Viewport-resilient. |
| Hero envelope crosses 40vh by 80-160px | Codex R1 | "Thesis pulls environment downward." |

**Master locks verb-glyph crosses.** Codex's full-hero-cross documented as "innovative but viewport-fragile" dissent.

### D5 — Watchlist as persistent column vs mode-conditional (synthesis)

| Position | Models | Mechanism |
|----------|--------|-----------|
| **Mode-conditional: column in Duet only, single line in Solo, absent in Field** | Sonnet R3 + Opus R3 synthesis — **MASTER DEFAULT** | Empty slots are dishonest; mode-gating preserves slot purpose. |
| Persistent right column always present | Opus R1 (conceded) | Spatial memory across visits. |
| Not a slot at all | Sonnet R1 (conceded) | Three rooms with no fixed watchlist. |

**Master locks mode-conditional watchlist.** Aspect ratio 0.5:1 narrow-tall when present.

### D6 — Field room: symmetric grid (Sonnet R1) vs staggered scan rows (Codex R2)

| Position | Models | Mechanism |
|----------|--------|-----------|
| **Staggered scan rows in Field** | Sonnet R3 conceded to Codex — **MASTER DEFAULT** | Symmetric 4-up reads as dashboard regardless of "restraint signaling" defense. |
| Symmetric 4-up in Field as restraint signal | Sonnet R1 | "Editorial honesty about absence of opinion." |

**Master locks staggered scan rows.** Maintains "equal rectangles imply the system has not decided" rule even in Field mode.

---

## Section 3 — The 3 rooms (final spec)

### Room 1: SOLO
**Trigger:** 1 Confirmed+ thesis, no others above Forming.
**Posture sentence:** "One thesis stands alone today."
**Composition:**
- Hero envelope cols 1-9 (1.5× normal width).
- Hero anchor: same fixed (x,y) as Duet/Field.
- Halo: 4% amber radial behind hero, ONLY in this room.
- Verb-glyph: 48pt serif, anchored just below 40vh cut.
- Watchlist: single line ("4 watch items unchanged"), NOT column.
- No subordinate tiles.
- Market context: full-width band below.

**Emotional target:** "AI is decisive today." Conviction.

### Room 2: DUET
**Trigger:** 1 hero + 1-2 challenger theses (default mode, ~60% of sessions).
**Posture sentence:** "Two theses, one challenger." OR "The market is narrow today; conviction is concentrated in two names."
**Composition:**
- Hero envelope cols 1-7 (480×320 effective).
- Verb-glyph: 36pt serif, anchored just below 40vh cut.
- Watchlist column: cols 10-12 (0.5:1 narrow-tall) with "since you left" delta.
- Negative well: cols 8-9 above 40vh (intentionally empty).
- Subordinates: 1-2 below 40vh, staggered (NOT symmetric grid).
- Market context: 6:1 wide-short band at bottom.

**Emotional target:** "AI sees the day with one main + one alt." Orientation.

### Room 3: FIELD
**Trigger:** 4-6 Forming theses, no Confirmed.
**Posture sentence:** "Six theses forming. None resolved."
**Composition:**
- NO hero. Posture sentence becomes focal at 22pt serif.
- Verb-anchor empty (NO verb-glyph).
- Subordinates: 4-6 in staggered scan rows (NOT symmetric grid).
- Watchlist: absent.
- Market context: persistent.

**Emotional target:** "AI is honest about uncertainty." Trust + patience.

---

## Section 4 — Composition grammar

### 4.1 Verb-anchor-point (locked)

```
Single fixed (x, y) for the 36/48pt serif verb-glyph:
  x = 50% viewport width (centered horizontally)
  y = 40vh + 32px (sits just below the stage/shop hairline)

Solo:   verb-glyph rendered at 48pt
Duet:   verb-glyph rendered at 36pt
Field:  verb-glyph absent (no anchor needed; posture sentence is focal)
```

The verb-glyph spans the 40vh cut visually — the eye crosses the horizon, not the object. Hero envelope above the cut never crosses.

### 4.2 Aspect-ratio taxonomy (locked)

| Category | Aspect ratio | Use |
|----------|--------------|-----|
| Hero tile | 1.65:1 | The dominant decision object |
| Subordinate tile | 1.65:1 | Same shape as hero (size differentiates) |
| Watchlist column | 0.5:1 narrow-tall | "List" not "decision" — refuses tile-comparison cognition |
| Market context band | 6:1 wide-short | "Horizon" not "card" |

Different aspect ratio = different mental category. This is the pure-composition technique that respects every UX-12 lock.

### 4.3 Negative space rules

```
Duet hero zone:        cols 1-7 hero, cols 8-12 negative well (~40% of width)
Solo hero zone:        cols 1-9 hero, cols 10-12 single watchlist line
Field:                 no hero zone; posture centered with margin air
```

The negative well is the gravity well. Emptiness creates pull. (Sonnet R1 contribution.)

### 4.4 Mode signature in posture sentence

The opening serif sentence doubles as the mode signature. The user learns to read it as both editorial posture AND room signal:

- "One thesis stands alone today." → Solo
- "Two theses, one challenger." → Duet
- "Six theses forming." → Field

Implicit room language. No new chrome required.

---

## Section 5 — AI atmosphere techniques

Six anti-AI-theater compliant techniques (synthesis of UX-12 + UX-13):

1. **Posture sentence with mode signature** (Sonnet R1) — the room signal lives in the AI's own voice.
2. **"Since you left" delta line** (Opus R1) — implicit AI memory of user's last visit. 11px mono below ambient timestamp. Always present; says "nothing changed" when nothing did.
3. **Verb-glyph at fixed anchor across rooms** (Sonnet R2 synthesis) — verb is the constant the eye learns. Composition changes around it.
4. **Aspect-ratio taxonomy** (Opus R1) — different shape = different mental category. Pure composition.
5. **Ambient timestamp** (UX-12 carry) — "as of 09:24, market 41 min in" ticks every 60s via number change.
6. **Layout mode IS the AI's voice** — Solo = "I see one thing." Duet = "I see one main + alt." Field = "I see noise." Composition is voice, not text.

UX-12 5 techniques (carried forward) + 4 NEW (room language + verb-anchor + aspect-ratio + since-you-left) = **9 total AI-presence techniques.** Zero violate the 58-item anti-pattern lock list.

---

## Section 6 — Environmental design tokens

```css
/* === 3-zone luminance ladder (extends UX-12) === */
--ux13-zone-stage:   #13161B;   /* top 40vh, warm + 2.5% amber tint (UX-12) */
--ux13-zone-shop:    #0F1115;   /* 40vh-100vh main field */
--ux13-zone-deep:    #0B0D10;   /* below-fold, deep research, coolest */

/* === Solo-only halo === */
--ux13-halo-solo: radial-gradient(
  ellipse 60% 40% at 50% 30vh,
  hsla(35, 60%, 50%, 0.04) 0%,
  transparent 70%
);
/* Applied ONLY in .ux13-room-solo. Color matches UX-12 amber family. */

/* === Verb-glyph (separate page-chrome category from tile verb-pill) === */
--ux13-verb-glyph-duet:  36px;
--ux13-verb-glyph-solo:  48px;
--ux13-verb-glyph-color: var(--ux12-fg-secondary);
--ux13-verb-glyph-font:  "Source Serif 4", serif;
--ux13-verb-glyph-weight: 400;

/* === Aspect ratio enforcement === */
--ux13-ratio-hero:      1.65;
--ux13-ratio-sub:       1.65;
--ux13-ratio-watchlist: 0.5;
--ux13-ratio-context:   6.0;

/* === Verb-anchor-point === */
--ux13-verb-anchor-x: 50%;
--ux13-verb-anchor-y: calc(40vh + 32px);
```

NO new luminance values beyond the third zone. NO noise grain (Gemini R1 conceded). NO ambient motion. NO localized glow except Solo-mode halo.

---

## Section 7 — Anti-pattern additions (extends UX-10/11/12 lock list to 65 items)

| # | Anti-pattern | Reason |
|---|--------------|--------|
| 59 | Halo opacity > 4% | Casino glow threshold |
| 60 | Halo color outside UX-12 amber family | Mood-ring violation (e.g., pure gold #FFD700, blue, purple) |
| 61 | Halo present in Duet or Field | Spotlight is Solo-only restraint |
| 62 | Verb-glyph at 36pt+ outside hero zone (in nav/footer/chrome) | Verb-as-headline drift |
| 63 | Symmetric 4-up grid in Field room | "Equal rectangles imply system has not decided" |
| 64 | Hero envelope crosses 40vh hard cut | Viewport-fragile; horizon must stay clean |
| 65 | Layout shift during active read | UX-12 lock carry-forward; Sonnet R3 reaffirmed |
| 66 | Watchlist as empty slot when no content | Mode-gating > always-present |
| 67 | "Since you left" line absent when something changed | Honest memory required |
| 68 | Mode count > 3 | Cognitive load (Codex R1 5-mode taxonomy reduced) |
| 69 | 1% noise grain texture on stage zone | Decoration ban extension (Gemini R1 conceded) |
| 70 | Editorial-gutter verb anchor as branding watermark | TradingView left-rail energy |

Combined: UX-10 §12 (29) + UX-11 §13 (15) + UX-12 §14 (15) + UX-13 (12) = **71-item locked anti-pattern list.**

---

## Section 8 — Implementation phasing (13A → 13X)

Composition + treatments only. NO new components. NO new schemas. NO new routes (until 13X).

| Phase | Scope | Files | Risk |
|-------|-------|-------|------|
| **13A** | UX-13 tokens (scoped `.ux13-living`) — 3-zone ladder + Solo halo + verb-glyph + aspect-ratio enforcement + verb-anchor variables | `apps/web/src/lib/copilot/ux13_tokens.css` | Low |
| **13B** | Composer mode-selector — chooses Solo / Duet / Field at session-load based on AI conviction state | `copilot_compose.ts` extension (no new schema) | Low |
| **13C** | Page wrapper component — applies room class (`ux13-room-solo` / `ux13-room-duet` / `ux13-room-field`) to root, renders verb-glyph at anchor, renders watchlist column when in Duet | `CopilotLivingView.tsx` (single new page; no new components below it) | Low |
| **13D** | "Since you left" line composer — reads last visit timestamp from local storage + computes delta against current state | `voice_composer.ts` extension | Low |
| **13E** | Mount `CopilotLivingView` at `/overview?view=living` (parallel route, additive branch) | `OverviewRouteSwitch.tsx` (additive only) | Low |
| **13F** | Posture sentence mode-signature templates — composer slot grammar for each room type | `voice_composer.ts` extension | Low |
| **13G** | Aspect-ratio enforcement — CSS aspect-ratio rules for hero/sub/watchlist/context categories | CSS-only | Low |
| **13H** | Field-mode staggered scan rows — composer renders subordinates in non-symmetric layout | `CopilotLivingView.tsx` extension | Low |
| **13X** | Cutover — default `/overview` → living view. UX-12 cockpit archived as `?view=cockpit`. UX-11 copilot archived as `?view=copilot`. UX-10 conviction archived as `?view=conviction`. UX-9 stream archived as `?view=stream`. | `OverviewRouteSwitch.tsx` default branch swap | High |

**Validation gates:**
- After 13E: user emotional validation at `/overview?view=living` with PROOF fixtures across all 3 rooms (force Solo/Duet/Field via query string for testing). Apply Codex's 5-second test.
- Before 13X: 1-week staging window with both `?view=cockpit` (UX-12) and `?view=living` (UX-13) available.

---

## Section 9 — UX-10/11/12 invariants inherited (no changes)

UX-13 is a COMPOSITION layer. Every UX-10/11/12 invariant survives intact:

- 4 verbs (`OPEN · HOLD · TRIM · EXIT`)
- 4 confidence tiers + dot glyph
- 4 freshness states
- Bear-case-mandated for `Confirmed`+ tier (composer invariant)
- Invalidation appears before target
- "The click hides detail, not risk existence."
- AI voice mixed regime — third-person hero, implicit body
- ConvictionTile schema 304×184, 5 rows, refuses-to-render
- Drawer modal sheet, 9 sections, 88vh, 220ms iOS curve, 5 dismiss paths, URL state `?drawer=<TICKER>`
- Dark warm-near-black two-zone canvas + UX-13's third zone
- 5-size type ramp + Source Serif 4 hero
- Decision sentence weight tracks confidence tier
- ZERO ambient motion · 220ms components · 340ms staggered orchestration
- 13 trust safeguards as engineering invariants
- 71-item locked anti-pattern list (with UX-13 additions)
- Verb-pill 11px lock (UX-13 verb-glyph at 36-48pt is SEPARATE category, not modification of pill)

---

## Section 10 — Debate provenance

3-round adversarial debate held 2026-05-09→05-10 between four models per `/octo:debate` skill.

| Model | R1 words | R2 words | R3 words |
|-------|----------|----------|----------|
| Gemini | 2,261 | 1,711 | 1,373 |
| Codex (gpt-5.5) | ~5,200 (post-prompt-echo) | ~5,000 (post-echo) | ~3,500 (post-echo) |
| Sonnet 4.6 (Agent) | ~3,820 (with ASCII) | 2,978 | 2,421 |
| Claude Opus 4.7 (moderator) | 2,564 | 2,507 | 2,162 |

**Total ~32,000 words of independent argumentation.**

Source files:
- Brief: `docs/research/debates/UX_13_environment/BRIEF.md`
- R1: `docs/research/debates/UX_13_environment/round1/{gemini,codex,sonnet,opus}_r1.md`
- R2: `docs/research/debates/UX_13_environment/round2/{gemini,codex,sonnet,opus}_r2.md`
- R3: `docs/research/debates/UX_13_environment/round3/{gemini,codex,sonnet,opus}_r3.md`

**Convergence pattern:** Strong 4-way convergence on adaptive-room model (Sonnet's Solo/Duet/Field naming wins; Codex/Opus/Gemini's modes all reduce to 3 rooms). Two architectural disputes documented with majority defaults (verb-glyph 36-48pt minority position; halo Solo-only majority position). Sonnet's R2 synthesis of "verb-anchor-point fixed across rooms" was the most important single move — it bridged Opus's persistent-slot concern with Sonnet's room-changing model. The 4-way agreement that "the composition itself is the AI's voice" is itself the most important consensus.

**Single most cited line across rounds:** Gemini R1's *"Equal rectangles imply the system has not decided."* Adopted as canonical justification for asymmetric composition.

**Single most load-bearing decision:** Verb-anchor-point fixed across rooms (Sonnet R2). Without it, room-changing breaks muscle memory at the moment muscle memory matters most.

---

## Section 11 — What this master deliberately does NOT lock

- Specific posture sentence copy beyond format constraints (composer template, A/B testable).
- Specific Source Serif 4 verb-glyph load strategy (already specced in UX-12 12B).
- Specific local-storage schema for "since you left" delta (deferred to 13D).
- Mobile breakpoint specifics for room compositions (Phase 13G+ refinement; mobile may flatten to single-column regardless of room).
- Real-time mid-session re-room-selection (banned per L6; future user-research could re-evaluate).

---

## Section 12 — Round 4 Resolutions (focused dispute round)

R4 added 2026-05-10 to resolve 3 disputes carrying minority dissent. Each model wrote a tight 800-1500 word focused position. Resolutions:

### R4 Resolution D1 — Verb-glyph at 36-48pt: SHIPPED as monitored Phase 13C deliverable

| Model | R4 position |
|-------|-------------|
| Sonnet | HOLD — promote from "future-experiment" to "locked Phase 13C deliverable" |
| Opus | SPLIT — ship as page chrome separate from tile pill, A/B in 13E |
| Gemini | SPLIT — ship as opt-in "Living View" experiment |
| Codex | KILL — "trade verb as poster" risk; preserve verb-anchor as abstract anchor only |

**Resolution:** Lock the verb-glyph as **Phase 13C deliverable** with the following constraints:
- **Solo:** 48pt Source Serif 4, weight 400, color `--ux12-fg-secondary`.
- **Duet:** 36pt same family, same weight, same color.
- **Field:** absent (no anchor needed).
- **Anchor:** fixed (x, y) at 50% viewport width, 40vh + 32px (just below stage/shop hairline).
- **Visual category:** PAGE CHROME (separate object from tile schema verb-pill at 11px). Pill stays unchanged.
- **Mitigations against Codex's "trade verb as poster" drift:**
  - Color matches body text (NOT red/green/amber/saturated).
  - Serif typeface (NOT block sans).
  - Solo (rare ~15%) uses 48pt; Duet (default ~60%) uses smaller 36pt.
  - Anti-pattern #62 prohibits any verb-glyph appearance outside hero zone (no nav/footer/chrome use).
- **Acceptance gate at 13E:** if Codex-test ("user reads 4 tiles in 5s") fails OR user qualitative testing shows action-pressure vibe, KILL the verb-glyph and revert to abstract anchor only. Codex's drift concern is the kill-trigger.

Codex's R4 dissent strengthens the existing dissent documentation: production drift is the named failure mode the kill-trigger guards against.

### R4 Resolution D2 — Halo Solo-only at 4% amber: HELD

| Model | R4 position |
|-------|-------------|
| Sonnet | HOLD lock as written |
| Opus | HOLD Solo-only at 4% |
| Gemini | HOLD majority position |
| Codex | KILL entirely — production drift to "easiest knob to turn" |

**Resolution:** Lock holds. 3-vs-1 toward keeping Solo-only halo at 4% amber. Codex's R4 dissent is sharper than R3 — names the **production drift mechanism** ("4% amber halo will become the easiest knob to turn when the page feels insufficiently alive"). Strengthens dissent documentation as a deployment-time guard. If 13A staging shows the halo being applied to Duet or Field by drift, kill the halo entirely. Anti-pattern #61 ("halo present in Duet or Field") is the explicit guard.

### R4 Resolution D3 — Hero anchor: LEFT confirmed (4-vs-0, Codex conceded)

| Model | R4 position |
|-------|-------------|
| Sonnet | HOLD LEFT, no experiment |
| Opus | HOLD LEFT default, allow RIGHT in Solo-only experiment |
| Gemini | HOLD LEFT, no experiment |
| Codex | HOLD LEFT — **CONCEDED** in R4 |

**Resolution:** 4-vs-0 LEFT. Codex's R4 conceded the right-anchor argument: *"I concede the other three are right that Western editorial reading patterns, especially premium magazine spreads, favor left mass with a right-side negative well; it is less risky and more immediately legible."* Right-anchored hero is **downgraded from "documented dissent" to "post-13X future experiment after UX-13 room grammar is validated."** No in-staging A/B. Master's Section 2 D2 dissent text updated.

### R4 Convergence statistic

R4 produced 1 strengthened lock (D1 verb-glyph with mitigations + kill-trigger), 1 unchanged lock (D2 halo, dissent sharpened), 1 dissent removal (D3 hero anchor → 4-way agreement).

The verb-glyph going to Phase 13C as monitored deliverable is the single most consequential R4 outcome — it ships Sonnet's R1 contribution into the implementation roadmap with Codex's drift concern as the explicit guard. If implementation drift produces the casino energy Codex predicts, the kill-trigger reverts the master to "no page-chrome verb." The composition still works without the glyph (room asymmetry + verb-anchor as abstract composition rule); the glyph is added value, not load-bearing.

R4 source files: `docs/research/debates/UX_13_environment/round4/{gemini,codex,sonnet,opus}_r4.md`. Word counts: Gemini 390, Codex ~720 (post-echo), Sonnet 1,061, Opus 586. ~3,000 words total of focused dispute resolution.

---

**End of master. Lock as `docs/research/UX_13_LIVING_ENVIRONMENT.md`. Do not rewrite without re-running the 4-way debate.**
