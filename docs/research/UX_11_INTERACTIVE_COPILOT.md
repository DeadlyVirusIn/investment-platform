# UX-11 Interactive AI Copilot Layer — Master

**Status:** locked after 3-round adversarial debate (Gemini · Codex · Claude Opus 4.7 · Claude Sonnet 4.6)
**Date:** 2026-05-09
**Pivot:** UX-10's static research surface → compact AI conviction surface with progressive disclosure via drawer.
**Debate transcripts:** `docs/research/debates/UX_11_interactive/`
**Parent spec:** `docs/research/UX_10_CONVICTION_ENGINE.md` (every UX-10 invariant inherited; nothing re-debated).
**Implementation isolation:** parallel route `/overview?view=copilot` (same pattern as UX-9 Phase 9D and UX-10 Phase 10D). Default `/overview` and `?view=working`, `?view=stream`, `?view=conviction` all remain unchanged until cutover (Phase 11I).

---

## TL;DR

UX-11 is a compositional re-layering of UX-10. The homepage becomes a compact AI conviction surface; the drawer becomes the structurally honest thesis surface UX-10 already specced.

**Single load-bearing principle (Codex R1, adopted across 4 R2s):**

> **The click hides detail, not risk existence.**

Every spec downstream traces back to it. Bear case existence stays on every `Confirmed`+ tile (inline Bull/Bear pair). Bear case detail moves to the drawer (forced past the eye in single-scroll). UX-10 §13.9 tension resolved.

Final atom: **304×184 ConvictionTile** with 5 required rows. **Mixed AI voice regime** (third-person hero, implicit body). **Modal sheet drawer** (88vh desktop / 92vh mobile, 9 sections, 220ms iOS curve). **URL state** via `?drawer=<TICKER>`. **Single static radial vignette** 4% opacity behind hero. Hard ban on `+18% upside` on tile and on conviction-density mood-ring backgrounds.

---

## Section 1 — Locked across all 4 models (universal agreement)

| # | Decision | Attribution |
|---|----------|-------------|
| L1 | **"The click hides detail, not risk existence."** Master organizing principle. | Codex R1 phrase · Sonnet R1 implementation · Opus R2 adoption · Gemini R2 alignment |
| L2 | **No `+18% upside` on tile** in any framing including "modeled magnitude." | Sonnet R1 + Gemini R1 + Opus R1 (Codex dissents) |
| L3 | **No emoji circles on verbs.** Casino-coded saturation. Verb pill is monochrome. | All 4 R1 |
| L4 | **Drawer is single-scroll, no tabs.** Carries forward UX-10 §9 lock. | All 4 R1 |
| L5 | **AI voice mixed regime: third-person in hero, implicit elsewhere.** Composer-enforced; lint-rejected outside boundary. | Opus R1 implicit-voice insight + Sonnet/Codex R2 third-person-in-hero requirement → 4-way R3 convergence |
| L6 | **URL state `?drawer=<TICKER>`.** Shareable, bookmarkable, back-button-natural. | Codex R1 · Sonnet R2 · Opus R3 · Gemini R3 |
| L7 | **Anchor return on dismiss.** Scroll restored + brief originating-tile highlight. | All 4 R3 |
| L8 | **Quiet-day hero copy locked.** *"Quiet day. Three theses unchanged. No new entries warranted."* | Opus R1 + Sonnet R3 conceded · Codex R3 conceded · Gemini R3 conceded |
| L9 | **No mood-ring background.** No conviction-density-mapped ambient color. No state-encoded hue. | Sonnet R2 + Codex R2 + Opus R2 (Gemini dissents) |
| L10 | **No glassmorphism, no animated ambient blobs, no purple-blue AI gradients.** UX-10 §12 carryforward. | All 4 |
| L11 | **No first-person pronouns ("I", "we") outside the AIRead hero label.** Lint-enforced. | Opus R1 · Sonnet R3 · Codex R3 · Gemini R3 |
| L12 | **No staggered text fade-in inside drawer ("AI is typing" theater).** Content paints solid with the sheet. | Gemini R1 · Codex R3 · Sonnet R3 |
| L13 | **No auto-opening drawer on first-session as onboarding.** Patterns are discovered via affordances, not unsolicited motion. | Sonnet R2 critique landed; Opus R3 conceded |

**Lock these 13 first. They survive PMs and reorgs.**

---

## Section 2 — Disputes documented

For each dispute, the master picks a default + records dissent so future PMs can re-open with provenance.

### D1 — Drawer modality

| Position | Models | Argument |
|----------|--------|----------|
| **Modal with backdrop dim**, focus-trap, page scroll locked | Sonnet, Gemini, Codex (3 of 4) — **MASTER DEFAULT** | Focus-trap a11y; "thesis needs concentration" UX; capital allocation requires commitment. Bottom sheet at 88vh desktop / 92vh mobile. |
| Dock-not-modal, 70% viewport, page underneath remains scrollable | Opus (1 of 4) | "Spotify Now Playing" pattern preserves scan flow; modal interrupts; users want to compare adjacent tiles while reading. |

**Master locks modal.** Reasoning: 3 independent models converged on focus-trap + commitment arguments. Opus's dock pattern documented as "validated alternative for future user testing — could be re-tested as a Pro-mode option after the modal version validates emotionally." Do not foreclose; do not ship.

### D2 — Verb pill semantic-color accents

| Position | Models | Mechanism |
|----------|--------|-----------|
| **Pure monochrome** (`#9CA3AF` text, transparent background, 1px `#1F2329` border) | Opus + Gemini, Sonnet R1 — **MASTER DEFAULT** | UX-10 §11.3 ban applies. Subtle casino green is still casino green. |
| Text-color accent permitted (`OPEN: #7DDC9E`, `EXIT: #F2777A`) | Codex; Sonnet partial concession in R2 | Restrained text-color reads as "direction" not "fill." Below saturation 50%. |

**Master locks monochrome.** Codex's text-color accent documented as dissent. The line: any color on the verb pill trains the user to scan color over text; verb name becomes redundant chrome. Hold UX-10 §11.3 line.

### D3 — `+18% modeled upside` on tile

| Position | Models | Mechanism |
|----------|--------|-----------|
| **Banned in any framing** | Sonnet, Gemini, Opus (3 of 4) — **MASTER DEFAULT** | Numeric anchor wins regardless of qualifier word. Eye behavior at scan speed parses "+18%" as "+18%" — "modeled" is invisible. Replaced by **Invalidation distance** (`Invalid < $158`). |
| Allowed as "modeled directional magnitude" | Codex | Magnitude is information; banning entirely is over-correction. |

**Master locks ban.** Codex dissent documented as "monitored exception: re-evaluate if A/B testing shows implicit-magnitude variant did not regress upside-anchor metrics." But ship the ban.

### D4 — Conviction-density ambient lighting

| Position | Models | Mechanism |
|----------|--------|-----------|
| **Banned — mood-ring violation** | Sonnet, Codex, Opus (3 of 4) — **MASTER DEFAULT** | Hue mapping to engine state encodes asset-conviction-density into background color. User reads color before tile. Mood-ring with a different alibi. |
| Permitted as "Ambient State Lighting" | Gemini | Maps to engine internal state, not asset performance; UX-10 ban was about asset color, not engine color. |

**Master locks ban.** Gemini dissent documented as "explored and rejected." Single static radial vignette permitted (Section 8.2 below).

### D5 — Mobile tile pattern

| Position | Models | Mechanism |
|----------|--------|-----------|
| **Horizontal scroll-snap rail** (82vw tile width, sliver of next visible) | Sonnet R3 conceded, Gemini, Codex — **MASTER DEFAULT** | Snap-rail reads as guided cockpit. Vertical stack reads as feed. |
| Vertical stack (full-width tiles) | Opus R1 | Horizontal scroll on financial app reads as ticker-feed (UX-10 anti-pattern). |

**Master locks horizontal snap-rail** with `scroll-snap-type: x mandatory; scroll-snap-align: start`. Tile width 82vw, min 280, max 320, height fixed at 184. Sliver of next tile visible affords scrolling. Opus's vertical-stack dissent documented.

---

## Section 3 — ConvictionTile spec (the homepage atom)

### 3.1 Dimensions (locked)

- **Desktop:** `304px × 184px` (master default).
- **Width range:** min `280px`, max `320px` (responsive).
- **Height:** fixed at `184px`. Heights MUST NOT vary across tiles.

### 3.2 Required rows (5 on `Confirmed`+, 4 on `Forming`/`Working`)

```
Row 1 (24px):  [VERB pill]                        [●●●○ · 14h]
Row 2 (22px):  NVDA · Semis cycle continuation
Row 3 (44px):  Add through $172 while data-center
               margin expansion holds.                ← decision sentence, 14px, 2 lines
Row 4 (16px):  Bull: capex +22% · Bear: hyperscaler rollover risk    ← Confirmed+ only
Row 5 (16px):  Invalid < $158 · Horizon ~6w
```

Total: 184px (5 rows × ~22px content + 26px padding).

### 3.3 Field contract

```ts
interface ConvictionTileData {
  verb: "OPEN" | "HOLD" | "TRIM" | "EXIT";
  ticker: string;
  thesisName: string;                   // ≤ 5 words
  decisionSentence: string;             // 80-140 chars, declarative
  confidenceTier: "Forming" | "Working" | "Confirmed" | "Conviction";
  freshnessState: "Fresh" | "Aging" | "Stale" | "Expired";
  lastReviewedAt: string;               // ISO timestamp
  invalidationDistance: string;         // e.g., "Invalid < $158"
  horizon: string;                      // e.g., "~6w" / "6-18mo"
  bullClause?: string;                  // ≤ 32 chars; REQUIRED on Confirmed+
  bearClause?: string;                  // ≤ 32 chars; REQUIRED on Confirmed+
}
```

### 3.4 Refuses-to-render conditions

Composer throws `TileSchemaError` if any of:
- `verb` not in locked set.
- `decisionSentence` missing, < 80 chars, or > 140 chars.
- `invalidationDistance` missing or stub.
- `confidenceTier` is `Confirmed`+ AND `bearClause` missing or < 8 chars.
- `confidenceTier` is `Confirmed`+ AND `bullClause` missing or < 8 chars.
- `lastReviewedAt` missing or `freshnessState` mismatched with timestamp age.
- `thesisName` > 5 words.

### 3.5 Banned fields

`+18% upside` (any framing including "modeled magnitude"). Color emoji circles. "Strong thesis" filler text. Sparklines. Target prices (T1/T2/T3). Options structure. F/T/M segmented bar. Confidence percentage. Star ratings. Progress rings. AI score widget. Countdown timers. Trending/social indicators.

### 3.6 Visual treatment

- **Background:** `--ux10-bg-card` (`#0F1115`).
- **Border:** 1px solid `--ux10-border-card` (`#1F2329`). `Confirmed`+ adds `border-left: 1px solid var(--ux10-conviction-strong)`.
- **Border radius:** 4px (sharp).
- **Shadow:** `0 18px 50px rgba(0,0,0,0.28)` (depth-2; Codex R1 contribution; Sonnet R2 conceded). Renders as imperceptible elevation on near-black, not Material card.
- **Verb pill:** 11px uppercase `#9CA3AF` monochrome, 1px `#1F2329` border, sharp 2px radius, no fill, no semantic color.
- **Tier glyph:** dot row `●●●○` (per UX-10 §4.1 component, reused).
- **Click target:** entire tile is `<button aria-haspopup="dialog">`.

### 3.7 Hover state

```css
.ux11-tile {
  transition: border-color 120ms ease-out, transform 120ms ease-out;
}
.ux11-tile:hover {
  border-color: var(--ux10-border-strong);
  transform: translateY(-1px);
}
```

No scale, no glow, no shimmer. Inside UX-10 S9 motion budget.

---

## Section 4 — AIReadHero spec

### 4.1 Visual + content

- **Single sentence**, 64–110 chars, third-person AI voice ("The AI is becoming more selective...").
- **Label:** "TODAY'S AI READ" (11px tracked uppercase, `--ux10-fg-tertiary`). Only persistent surface where "AI" appears as page chrome.
- **Hero text:** 18px `--ux10-fg-primary`, line-height 1.5, max-width 780px.
- **Cadence:** once per session on first paint, plus on regime snapshot refresh (~6h backend cadence). NOT real-time. NOT per-poll.
- **Quiet-day fallback (locked):** *"Quiet day. Three theses unchanged. No new entries warranted."*

### 4.2 Composer slot grammar (lint-enforced)

```
[STANCE_VERB] [QUALIFIER_CLAUSE]. [CONSEQUENCE_CLAUSE].
```

Where:
- `STANCE_VERB` ∈ {"is becoming more selective", "is leaning into", "is reducing exposure to", "is holding pattern on", "sees no new entries warranted in"}
- `QUALIFIER_CLAUSE` describes regime evidence ("after this week's rally", "as macro data softens")
- `CONSEQUENCE_CLAUSE` makes the implication ("Add only where earnings durability offsets valuation risk")

### 4.3 Banned tokens (lint rejects)

`AI found`, `AI-powered`, `Powered by AI`, `Ask me anything`, `Here's what you should do`, `Don't miss`, `Before it's too late`, `Guaranteed`, `crush`, `moon`, `explode`, `rip`, `Based on my proprietary algorithm`, `discover`, `today's picks`, `smart`, `hot`, ALL-CAPS shouting headlines, emoji.

### 4.4 Anti-AI-theater compliance

No orb. No chat dock. No suggested-question chips. No "Powered by [GPT/Claude]" badge. No first-person pronoun. The label "TODAY'S AI READ" is the *single* permitted instance of "AI" in page chrome. AI presence comes from **language alone** — third-person framing in the hero, implicit voice everywhere else.

---

## Section 5 — AI voice composer rules (mixed regime)

| Surface | Voice | Example |
|---------|-------|---------|
| **AIReadHero** | Third-person AI | "The AI is becoming more selective after this week's rally." |
| **Tile decision sentence** | Implicit | "Add through $172 while data-center margin expansion holds." |
| **Tile Bull/Bear clause** | Implicit | "Bull: capex +22% · Bear: hyperscaler rollover risk" |
| **Drawer thesis recap** | Implicit | "Capex rollover risk dominates; valuation pressure rising." |
| **Decision log entries** | Past-tense AI | "The AI promoted NVDA from Working to Confirmed on May 2 because hyperscaler capex came in +22% vs 18% expected." |

### 5.1 Composer rules (lint-enforced at build)

| Rule | Banned | Permitted |
|------|--------|-----------|
| V1 — Mixed-regime attribution | First-person ("I", "we") anywhere; "AI" word anywhere outside the hero label and decision-log subject | "The AI is..." in hero only; implicit voice elsewhere |
| V2 — Active voice present tense | Hedges ("may consider", "could potentially"), prediction ("will rally", "expected to") | Declarative ("Add through $172"; "Capex rollover risk dominates") |
| V3 — Subject is market or position | "You should...", "Your portfolio..." | "Valuation pressure mounting"; "The AI is..." |
| V4 — No persona/emotion | "excited", "worried", "loves", "hates", "thinks" | Direct observations ("Cloud margins continue expanding") |
| V5 — No discovery hype | "Found", "spotted", "discovered", "AI found N moves" | "The AI is leaning into..." |
| V6 — Length constraints | Two sentences in hero; >140 chars in decision sentence | One sentence hero; 80–140 char decision sentence |
| V7 — No persona name | The AI does not have a name. No "Cleo says..." or similar | "The AI is..." (third-person attribution only) |

PR review enforces. Lint runs on every composer-touching commit.

---

## Section 6 — ReasoningDrawer spec

### 6.1 Modality + dimensions

- **Modal sheet** (Section 2 D1 default).
- **Desktop:** 88vh height. `aria-modal="true"`. Backdrop `rgba(11, 13, 16, 0.6)`. NO `backdrop-filter: blur` (glassmorphism banned).
- **Mobile:** 92vh bottom sheet. Drag handle 32×4px. Swipe-down dismiss only when scroll at top.
- **Page scroll locked** while open.
- **Single instance.** Opening another tile cross-fades content (120ms) within same drawer; never stacks.

### 6.2 Sections (9, single continuous scroll)

| # | Section | Purpose |
|---|---------|---------|
| 1 | **Recap header** (NEW for UX-11) | verb + tier + freshness + 60-word thesis paragraph |
| 2 | **Invalidation / what would break this** *(moved earlier per Codex R1)* | falsification conditions before any thesis |
| 3 | **Driver / Counter / Catalyst** | UX-10 §9.2.2 thesis triplet, equal visual weight |
| 4 | **Target / Horizon / Structure** | loss-named-first; defined-risk default |
| 5 | **What changed since last review** | diff against user's last drawer-open of this ticker |
| 6 | **Compared candidates** | "AI considered AMD, TSM, MU; picked NVDA because..." (UX-10 §9.2.4) |
| 7 | **My pattern with this AI** | user-specific reflection (UX-10 §9.2.5) |
| 8 | **Calibration line** | "Current `Confirmed` hit rate: 60% (rolling 90d). Below 70% target." (UX-10 §9.2.6) |
| 9 | **Engine version footer** | tiny grey "Engine v2.3.1 · last retrained Apr 28" |

### 6.3 Motion (locked)

- **Open:** sheet `translateY(100%)` → `translateY(0)` over 220ms `cubic-bezier(0.32, 0.72, 0, 1)` (iOS sheet curve). Backdrop fades 0→0.6 over 160ms ease-out, simultaneous.
- **Close:** sheet 200ms reverse. Backdrop fades 140ms.
- **Tile-to-tile cross-fade:** 120ms content opacity swap within same drawer.
- **Reduced motion:** instant open + opacity 0→1 only, no translate.

Total motion budget: 240ms in, 200ms out. Inside UX-10 S9 240ms cap.

### 6.4 Dismiss paths (5)

1. ESC key
2. Click backdrop
3. Browser back-button (URL state `?drawer=` clears)
4. Swipe down (mobile only, when scroll at top)
5. Top-right close button (32×32 hit target)

### 6.5 Anchor return

On dismiss: scroll position restored to originating tile + 400ms tile highlight (`border-color: var(--ux10-border-strong)` then fade). Resolves "where was I" disorientation.

### 6.6 a11y contract

```ts
<dialog
  role="dialog"
  aria-modal="true"
  aria-labelledby="drawer-title"
>
```

Focus trap inside drawer when open. Focus returns to originating tile on dismiss. ESC always dismisses.

---

## Section 7 — Tile click → drawer interaction (timeline)

```
t=0ms       User clicks tile (pointerdown).
t=0–80ms    Tile receives confirmation feedback
            (border-color shift, 80ms).
t=80ms      Drawer mounts. Backdrop mounts at opacity 0.
            URL pushes ?drawer=<TICKER> state.
t=80–240ms  Backdrop fades to 0.6 (160ms ease-out).
            Sheet rises 100%→0% (220ms iOS curve).
            Other tiles dim to 60% opacity.
            Originating tile dims to 40% opacity.
t=240ms     Settled. Focus moves to drawer close button.
            Body scroll locked.

DISMISS
t=0ms       User triggers dismiss (any of 5 paths).
t=0–200ms   Sheet translates to 100% (200ms reverse).
            Backdrop fades to 0 (140ms).
            URL state clears.
t=200ms     Originating tile receives 400ms highlight then fades.
            Focus returns to tile.
            Scroll position preserved.
```

---

## Section 8 — Visual hierarchy ramp

### 8.1 Four layers (each visually distinguishable)

| Layer | Background | Border | Elevation | Type |
|-------|-----------|--------|-----------|------|
| **PRIMARY** (AIRead + tile rail) | `--ux10-bg-card` over radial vignette | 1px `--ux10-border-card`; left-tint on Confirmed+ | depth-2 (`0 18px 50px rgba(0,0,0,0.28)`) | hero 18 / tile 14px |
| **SECONDARY** (risk shifts, opportunities) | `--ux10-bg-card` flat | 1px `--ux10-border-card` | depth-1 (`0 8px 24px rgba(0,0,0,0.18)`) | 14px |
| **TERTIARY** (watchlist, catalysts) | `--ux10-bg-page` (no card) | bottom-border separator only | none | 13px |
| **QUATERNARY** (engine status, footer) | `--ux10-bg-page` | none | none | 11px meta |

Type opacity ramp via existing `--ux10-fg-*` tokens. Single typeface (UX-10 sans). Reject Gemini's monospace mixing in QUATERNARY (visual noise).

### 8.2 Background depth (single radial vignette)

```css
/* Static — fixed neutral color, never state-mapped */
background-image: radial-gradient(
  ellipse 60% 40% at 50% 0%,
  hsla(228, 30%, 22%, 0.05) 0%,
  transparent 70%
);
```

Behind hero only. Not page-wide. Not card-level. NO color shift based on engine state (Gemini's "Ambient State Lighting" rejected).

Plus three depth tokens: depth-0 (none), depth-1 (`0 8px 24px rgba(0,0,0,0.18)`), depth-2 (`0 18px 50px rgba(0,0,0,0.28)`). Plus `--ux10-bg-elev` finally used (drawer surface). Plus 1px section dividers between layers.

If page reads "too flat" after these treatments, fix typography spacing first (24px → 32px section padding), not color.

### 8.3 Banned depth treatments

Asset-level color glow. Animated ambient blobs. Glassmorphism (`backdrop-filter: blur`). Purple-blue AI gradients. Card-level gradients (UX-10 §11.3 carry-forward). Conviction-density-mapped hue. Material Indigo `#3F51B5`.

---

## Section 9 — Secondary surfaces structure

```
[ AIReadHero ]                                    ← persistent, PRIMARY
[ ConvictionTile rail — up to 5 tiles ]           ← PRIMARY

────── Layer 2 divider ──────

[ Risk shifts ]      [ Opportunity shifts ]       ← SECONDARY (paired, side-by-side)
[ Promotions today ]                              ← SECONDARY

────── Layer 3 divider ──────

[ Catalysts this week ]                           ← TERTIARY
[ Watchlist (compact table) ]
[ Sector rotation (single sentence) ]

────── Layer 4 divider ──────

[ Decision Diet status · Engine version ]         ← QUATERNARY footer
```

### 9.1 Hard rules
- **No infinite scroll.** Page ends.
- **No "see more →" paginators.** No daily-pick framing reintroduction.
- **Macro is one sentence in Layer 3**, not a section. Resists Bloomberg drift.
- **Risk shifts paired alongside opportunities** in Layer 2. Resists feed-of-opportunities drift.
- **Secondary surfaces lose bounding boxes** beyond Layer 1. PRIMARY tiles are the only high-elevation card set on first viewport.

---

## Section 10 — Mobile experience (< 720px)

- **AIReadHero:** drops to 16px, two lines max (50ch line-height 1.5).
- **ConvictionTile rail:** **horizontal scroll-snap** (`scroll-snap-type: x mandatory; scroll-snap-align: start`). Tiles 82vw width, min 280, max 320, height 184. Sliver of next tile visible.
- **Drawer:** 92vh bottom sheet with drag handle (32×4px). Swipe-down dismiss only when scroll at top.
- **Layer 3 surfaces:** collapse to accordion. Closed by default.
- **Tap targets:** 44px minimum on close + drawer controls. Tile click target +12px padding internal.
- **Below 480px:** tiles stay full-width horizontal-snap; thesis name truncates with "..."; decision sentence drops to 4-line max.

---

## Section 11 — URL state contract

`/overview?view=copilot[&drawer=<TICKER>]`

- `view=copilot` is the parallel-route flag (Section 12 D below).
- `drawer=<TICKER>` opens the ReasoningDrawer for that ticker on first paint. Bookmarkable. Shareable. Browser-back closes the drawer before leaving the page.
- Dismissing the drawer clears `drawer=` param via `history.replaceState`.
- Opening a different drawer replaces `drawer=` param via `history.pushState` (so back navigates ticker-by-ticker through opened drawers within session).

---

## Section 12 — Implementation phasing (11A → 11I)

Same parallel-route validation pattern as UX-9 Phase 9D and UX-10 Phase 10D. Default `/overview` does not change until 11I cutover.

| Phase | Scope | Files | Risk |
|-------|-------|-------|------|
| **11A** | UX-11 tokens (scoped `.ux11-copilot`) + AI voice composer + lint rules + ConvictionTile schema validator | `apps/web/src/lib/copilot/ux11_tokens.css`, `voice_composer.ts`, `tile_schema.ts`, `lints/voice_lint.ts` | Low |
| **11B** | `ConvictionTile` + `AIReadHero` primitives | `ConvictionTile.tsx`, `AIReadHero.tsx` + composer fixtures | Low |
| **11C** | `ReasoningDrawer` (modal, 9 sections, motion, a11y, URL state, dismiss paths) | `ReasoningDrawer.tsx`, `useDrawerUrlState.ts` | Medium |
| **11D** | `CopilotInteractiveView` page + mount at `/overview?view=copilot` (additive route) | `CopilotInteractiveView.tsx`, `OverviewRouteSwitch.tsx` (additive branch) | Low |
| **11E** | Secondary surfaces: Risk shifts + Opportunities + Watchlist + Catalysts + Sector rotation | secondary surface components | Medium |
| **11F** | Motion polish + radial vignette + depth tokens + section dividers | CSS additions; no new components | Low |
| **11G** | Real engine wiring — replace fixtures with composer reading `paper_position` + `recommendation` + `regime_snapshot` + `factor_snapshot` | composer rewrites + API additions (overlap with UX-10 Phase 10G) | High |
| **11H** | Telemetry on drawer opens / dismiss times / Bull-Bear-row reads / lint enforcement | telemetry events + dashboard | Medium |
| **11I** | Cutover — default `/overview` → copilot view. UX-10 conviction view archived as `?view=conviction`. UX-9 Stream archived as `?view=stream`. UX-8B PRESSURED archived as `?view=condition`. | `OverviewRouteSwitch.tsx` default branch swap | High |

**Validation gates between phases:**
- After 11D: user emotional validation at `/overview?view=copilot` with PROOF fixtures. Compare emotional response vs `?view=conviction` (UX-10) at the same data. If UX-11 doesn't feel materially more "alive," diagnose before continuing.
- After 11F: full visual polish review before 11G touches backend.
- After 11G: real-data validation at full cycle (overnight ingest → copilot surfaces refresh). Latency budget: drawer open < 100ms with cached data.
- Before 11I: 1-week staging window with both `?view=conviction` and `?view=copilot` available; user toggles default.

---

## Section 13 — Anti-pattern additions to UX-10 §12 lock list

| Anti-pattern | Reason | Banned by |
|--------------|--------|-----------|
| Emoji circles on verb pills (🟢🔴🟡) | Casino saturation; user font-stack uncontrollable | All 4 R1 |
| Tinted fill on verb pill (`background: rgba(...)` as direction encoding) | Text-color permitted (Codex dissent doc'd); fill banned | Sonnet R3 partial concede + Opus R3 |
| `+18% upside` on tile (any framing) | Eye behavior parses numeric as target regardless of qualifier | Sonnet, Gemini, Opus (Codex dissent) |
| State-mapped ambient hue | Mood-ring with different alibi | Sonnet, Codex, Opus (Gemini dissent) |
| Dock-style sheet with page scrollable underneath | Attention fragmentation during high-stakes risk read | Sonnet, Gemini, Codex (Opus dissent) |
| Auto-opening drawer on first session ("onboarding") | Theater; patterns must be discoverable via affordance | Sonnet R2 critique landed; Opus R3 conceded |
| Staggered text fade-in inside drawer ("AI is typing") | Theater; content paints solid with sheet | Gemini R1 + Codex R3 + Sonnet R3 |
| First-person "I" or "we" outside AIRead hero label | Persona drift; chatbot pattern | Opus R1 + 3-way concede |
| Vertical-stack tiles on mobile | Reads as feed; horizontal snap is the cockpit pattern | Codex/Gemini/Sonnet (Opus dissent) |
| Standalone target percentage on any homepage surface | Upside anchoring | All 4 |
| Conviction-density background colors | Mood-ring | Sonnet, Codex, Opus |
| Two-sentence AIReadHero | Splits the eye; one-sentence forces single point of view | Opus R1 + Sonnet R2 |
| AI persona name (e.g., "Cleo") | The AI does not have a character | All 4 R3 |
| Suggested-question chips below hero | UX-9 carry-forward | UX-9 lock |
| Chat dock | UX-9 carry-forward | UX-9 lock |
| AI orb | UX-9 carry-forward | UX-9 lock |

---

## Section 14 — UX-10 invariants inherited (no changes)

UX-11 must respect every UX-10 invariant. List for traceability:

- **Verbs (locked 4):** `OPEN · HOLD · TRIM · EXIT`. Same set, same banned alternatives.
- **Tiers (locked 4):** `Forming · Working · Confirmed · Conviction` + dot glyph.
- **Freshness (locked 4):** `Fresh · Aging · Stale · Expired`.
- **Bear-case-mandated** for `Confirmed`+ tier — composer-level invariant. UX-11 strengthens this by surfacing bear-case existence on the tile (Bull/Bear inline pair).
- **Invalidation appears before target** — UX-11 surfaces invalidation distance on tile; in drawer, moves invalidation one slot earlier (between recap and Driver/Counter).
- **STRUCTURE for options** — loss-named-first; defined-risk default. UX-11 inherits `OptionsStructureCard` (UX-10 §8) into drawer Section 4.
- **Refuses-to-render schema** on ActionCard — UX-11 adds parallel `TileSchemaError` for `ConvictionTile`.
- **13 trust safeguards** (UX-10 §10) — all carry forward.
- **29-item anti-pattern lock list** (UX-10 §12) — UX-11 extends with Section 13 above.

---

## Section 15 — Engineering API contract additions (11G)

The composer must produce ConvictionTileData shaped to Section 3.3. Backend additions:

- `recommendation` (existing) — extend with `bull_clause` (≤32 chars) and `bear_clause` (≤32 chars). Composer-required on `Confirmed`+ tier; refuses to produce a recommendation otherwise.
- `recommendation` — extend with `invalidation_distance_str` (human-readable e.g. "Invalid < $158" or "−4.2% to invalidation").
- `regime_snapshot` (existing) — extend with `ai_read_sentence` (composed via slot grammar; lint-validated at write time).
- `drawer_telemetry` (NEW table) — `(user_id, ticker, opened_at, dismissed_at, dismiss_method, read_count_bull_bear, scrolled_to_section)` for Phase 11H.

Migrations land in 11G. Lint enforcement of voice rules runs at composer-level (Python side) AND at frontend composer-test level (TS side). Build-time error if voice composer outputs banned tokens.

---

## Section 16 — Debate provenance

3-round adversarial debate held 2026-05-09 between four models per `/octo:debate` skill:

| Model | R1 words | R2 words | R3 words |
|-------|----------|----------|----------|
| Gemini | 2,512 | 1,702 | 1,227 |
| Codex (gpt-5.5) | ~5,200 (post-prompt-echo) | ~3,800 (post-echo) | ~2,500 (post-echo) |
| Sonnet 4.6 (Agent) | 2,989 | 2,892 | 2,371 |
| Claude Opus 4.7 (moderator) | 2,398 | 2,352 | 1,992 |

**Total ~28,000 words of independent argumentation.**

Source files:
- Brief: `docs/research/debates/UX_11_interactive/BRIEF.md`
- R1: `docs/research/debates/UX_11_interactive/round1/{gemini,codex,sonnet,opus}_r1.md`
- R2: `docs/research/debates/UX_11_interactive/round2/{gemini,codex,sonnet,opus}_r2.md`
- R3: `docs/research/debates/UX_11_interactive/round3/{gemini,codex,sonnet,opus}_r3.md`

**Convergence pattern:** UX-11 converged faster than UX-10 because it inherits UX-10's locks. The debate effectively narrowed to: tile dimensions (settled at 304×184), modality (modal won 3-1), magnitude allowance (banned 3-1), and ambient color (banned 3-1). The single most cited contribution across rounds was Codex's R1 phrase **"the click hides detail, not risk existence"** — adopted as the master organizing principle.

---

## Section 17 — What this master deliberately does NOT lock

- Specific copy for AIReadHero examples beyond format constraints (composer template, A/B testable).
- Specific behavior of the live-data subscription layer (post-11G, post-launch).
- Specific copy for `bullClause` / `bearClause` per-ticker — composer template, lint-validated only.
- Real-money execution UX (paper trading only currently).
- Crypto / forex / commodities surfaces (roadmap).
- Drawer telemetry dashboards (Phase 11H spec, deferred design).

These are deliberate omissions, not oversights.

---

**End of master. Lock as `docs/research/UX_11_INTERACTIVE_COPILOT.md`. Do not rewrite without re-running the 4-way debate.**
