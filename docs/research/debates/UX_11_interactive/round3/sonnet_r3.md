# Model: Sonnet 4.6
## Round: 3

## Final position summary (200 words max)

UX-11 is a compositional re-layering of UX-10, not an architectural reset. The homepage becomes a compact AI conviction surface; the drawer becomes the structurally honest thesis surface UX-10 already locked. The single load-bearing principle, named cleanly by Codex in R1 and adopted across all four R2s in some form, is: **the click hides detail, not risk existence**. Every spec downstream traces back to it.

Final spec: **304×184 ConvictionTile** with 5 required rows including the inline Bull/Bear pair on Confirmed+ tier; **third-person AI voice in the hero, implicit voice in tile/drawer body** (mixed regime synthesizing Opus's R2 concession with my own); **modal-with-backdrop drawer** (3-of-4 consensus, Opus dock dissent documented); **UX-10 §9 sections in single scroll, invalidation moved one slot earlier** (Codex's tightening); **220ms cubic-bezier(0.32, 0.72, 0, 1)** sheet rise; **single static radial vignette** behind hero at 4% opacity; **monochrome verb pill** with text-only accent permitted; **`+18%` upside banned** on tile; **URL state via `?drawer=<TICKER>`**.

Premium remains non-permissive. UX-11 does not weaken UX-10's trust safeguards — it composes them differently.

---

## What I maintain from R1/R2

1. **5-row tile mandatory on Confirmed+ tier with inline Bull/Bear pair (my R1 contribution).** Codex R2's "miniature analyst card" critique misreads the fix: bull/bear is a two-clause line, not paragraphs. Opus conceded verbatim in R2; Gemini conceded in spirit (Invalidation distance as substitute).
2. **`+18% upside` banned on tile.** 3-of-4. Codex's "modeled upside" qualifier is cosmetic; eye behavior does not parse adverbs.
3. **Modal drawer with backdrop, not Opus's dock.** Dock fails focus-trap a11y (Codex R2 caught the `aria-modal="false"` + focus-trap contradiction); 70% scrollable-underneath fragments attention during a high-stakes risk read. Spotify is media; UX-11 is capital allocation.
4. **220ms drawer rise on `cubic-bezier(0.32, 0.72, 0, 1)`** (iOS sheet curve). Codex's 280ms too slow; Opus's 240ms `(0.16, 1, 0.3, 1)` lands hard; Gemini's 350ms theatrical.
5. **Single radial vignette at 4% opacity, fixed neutral color.** Reject Gemini's conviction-density-mapped ambient.
6. **Composer-templated AIReadHero**, not free-form prose. Slot grammar lint-enforced.
7. **Single drawer instance, content cross-fades on tile-to-tile navigation.**

---

## What I conceded across R2-R3

1. **Tile dimensions: 320×176 (R1) → 304×184 (R2/R3 final).** Codex right that 320 too wide on dense desktops; Opus wrong that 220 needed.
2. **Voice regime: third-person-everywhere (R1) → mixed (R2/R3).** Opus's R1 implicit-voice insight correct for the body of the page; third-person correct only for the hero sentence. Composer enforces boundary.
3. **Drawer section ordering: invalidation moves one slot earlier** (Codex R1). UX-10 said "invalidation before target"; Codex's tightening to "invalidation before bear case too" is a strict tightening, not a violation.
4. **URL state for drawer: `?drawer=<TICKER>`** (Codex R1). Bookmarkable, shareable. My R1 history.pushState was insufficient.
5. **Verb pill text-color accent permitted; tinted fill banned.** Codex's `OPEN: #7DDC9E text on rgba(125,220,158,0.10)` is restrained text-color, not surface fill.
6. **Refuses-to-render Counter applies only to `Confirmed`/`Conviction` tiers.** On `Forming`/`Working`, the Bull/Bear row is composer-discretion based on data availability.
7. **Quiet-day hero copy: adopt Opus's "Quiet day. Three theses unchanged. No new entries warranted."** "Warranted" more decisive than my R1 "recommended."
8. **Tile shadow (depth-2) allowed for PRIMARY layer.** Codex's `0 18px 50px rgba(0,0,0,0.28)` on near-black renders as imperceptible elevation, not Material card.
9. **Mobile horizontal-snap rail (not vertical stack).** Codex/Gemini right: vertical stack reads as feed; horizontal snap reads as guided cockpit.

---

## Open disputes I want documented in the master

1. **Drawer modality: dock (Opus) vs modal-with-backdrop (Sonnet/Codex/Gemini).** 3-vs-1. Recommend modal default; document dock as "validated alternative for future user testing." Do not ship a half-modal.
2. **Tile dimensions cluster after R2: 304×184 ± 16px width, ± 6px height.** Recommend 304×184 floor with min-width 280, max-width 320 for responsive grids. Heights must not vary across tiles.
3. **Modeled upside on tile: Codex (yes) vs everyone else (no).** Recommend ban; Codex's dissent as "monitored exception: re-evaluate post-A/B."
4. **Conviction-density ambient lighting: Gemini (yes) vs everyone else (no).** Recommend ban; Gemini's dissent as "explored and rejected."
5. **Verb pill color: monochrome only (Sonnet R1, Gemini, Opus) vs subtle text-color accent (Codex; Sonnet R2 partial concede).** Permit text-color accent; ban tinted fill on pill body. The line: color on glyph/text is direction; color on surface is mood-ring.

---

## Final answers per question

### Q1. ConvictionTile shape

**304×184 px desktop. Min-width 280, max-width 320, height fixed.** 5 required rows on Confirmed+, 4 on Forming/Working:

```
Row 1 (24px): [VERB pill]                    [●●●○ · 14h]
Row 2 (22px): NVDA · Semis cycle continuation
Row 3 (44px): Add through $172 while data-center
              margin expansion holds.           ← decision sentence, 14px, 2 lines
Row 4 (16px): Bull: capex +22% · Bear: hyperscaler rollover risk
Row 5 (16px): Invalid < $158 · Horizon ~6w
```

**Required:** verb pill, ticker+thesis-name, decision sentence, freshness chip, tier glyph, invalidation distance. **Conditional required:** Bull/Bear pair on Confirmed+. **Banned:** `+18% upside` (any framing), emoji circles, "Strong thesis" filler, sparklines, target prices, options structure, F/T/M bar, confidence percentage. **Click target:** entire tile is `<button aria-haspopup="dialog">`. **Refuses to render** if required row missing or decision sentence > 140 chars.

### Q2. AIReadHero

**Single sentence, 64–110 chars, third-person AI voice ("The AI is...").** Slot grammar:

```
[STANCE_VERB] [QUALIFIER_CLAUSE]. [CONSEQUENCE_CLAUSE].
```

Cadence: **once per session on first paint, plus on regime snapshot refresh** (fresh per visit, no mid-session jitter unless engine state genuinely changes). Label "TODAY'S AI READ" is the only AI-attribution chrome on the page. Quiet-day fallback: *"Quiet day. Three theses unchanged. No new entries warranted."* Lint rejects banned tokens. No orb, chat dock, suggested-question chips, "Powered by AI" badge.

### Q3. ReasoningDrawer experience

**Modal bottom sheet, 88vh desktop, 92vh mobile.** Backdrop `rgba(11, 13, 16, 0.6)`, no glassmorphism blur. Single instance; opening another tile cross-fades content within same drawer (120ms).

**9 sections, single continuous scroll** (Codex's invalidation-earlier order):

1. Recap header (NEW for UX-11) — verb + tier + freshness + 60-word thesis paragraph
2. Invalidation / what would break this *(moved earlier per Codex R1)*
3. Driver / Counter / Catalyst (UX-10 §9.2.2 verbatim)
4. Target / Horizon / Structure (loss-named-first, defined-risk)
5. What changed since last review
6. Compared candidates
7. My pattern with this AI
8. Calibration line
9. Engine version footer

**Motion:** sheet `translateY(100%)` → `translateY(0)` over `220ms cubic-bezier(0.32, 0.72, 0, 1)`. Backdrop fades over `160ms ease-out`, simultaneous. Dismiss: 200ms / 140ms reverse. **Five dismiss paths:** ESC, click backdrop, browser back, swipe-down (mobile), top-right close. **Anchor return:** scroll restored + 400ms tile highlight. **a11y:** `role="dialog" aria-modal="true"`, focus trap, reduced-motion fallback (instant + opacity-only).

### Q4. AI voice rules

**Mixed regime, composer-enforced:**

- **Hero:** third-person ("The AI is becoming more selective...")
- **Tile reads + drawer body:** implicit voice ("Add through $172", "Capex rollover risk dominates")
- **Decision log:** past-tense AI voice ("The AI promoted NVDA from Working to Confirmed on May 2 because...")

**Banned at lint:** first-person ("I think"), first-person plural ("we"), imperatives ("Trim now"), hedges ("may consider"), prediction language ("will rally"), persona/emotion verbs ("excited", "worried", "loves"), discovery hype ("found", "spotted"), sycophancy ("Hey there!"), all-caps shouting, "AI" word outside the hero label and decision-log subject.

The AI is the **narrator of the page**, not a character in it.

### Q5. Visual hierarchy ramp

| Layer | Surface | Border | Elevation | Type |
|-------|---------|--------|-----------|------|
| **PRIMARY** (hero + tile rail) | `--ux10-bg-card` over radial vignette | 1px; left-tint on Confirmed+ | depth-2 (`0 18px 50px rgba(0,0,0,0.28)`) | hero 18 / tile 14px |
| **SECONDARY** (risk shifts, opportunities) | `--ux10-bg-card` flat | 1px | depth-1 | 14px |
| **TERTIARY** (watchlists, catalysts) | `--ux10-bg-page` (no card) | bottom-border separator | none | 13px |
| **QUATERNARY** (engine status, footer) | `--ux10-bg-page` | none | none | 11px meta |

No new color tokens. Single typeface (UX-10 sans). Reject Gemini's monospace mixing in QUATERNARY.

### Q6. Subtle background depth

**Single radial vignette, fixed neutral color, 4% opacity, behind hero only:**
```
radial-gradient(ellipse 60% 40% at 50% 0%, rgba(123, 140, 255, 0.04) 0%, transparent 70%)
```
Plus three depth tokens: depth-0 (none), depth-1 (`0 8px 24px rgba(0,0,0,0.18)`), depth-2 (`0 18px 50px rgba(0,0,0,0.28)`). Plus `--ux10-bg-elev` finally used (drawer surface). Plus 1px section dividers.

**Banned across all 4 models:** asset-level color glow, animated ambient blobs, glassmorphism, purple-blue AI gradients, card-level gradients, conviction-density-mapped hue (Gemini dissent documented).

If page still reads "too flat" after these treatments, fix typography spacing first (24→32px section padding), not color.

### Q7. Tile click → drawer interaction

**240ms total open, 200ms close:**

1. Hover: 1px brighter border + 1px upward translation + cursor pointer (no scale, no glow).
2. Click (t=0): tile receives confirmation feedback (`border-color: #2A2F37`).
3. t=80ms: drawer mounts, backdrop mounts at opacity 0, URL updates to `?drawer=<TICKER>`.
4. t=80–240ms: backdrop fades to 0.6 (160ms ease-out); sheet rises 100%→0% (220ms cubic-bezier(0.32, 0.72, 0, 1)); other tiles dim to 0.6; originating tile dims to 0.4.
5. t=240ms: focus moves to drawer close button.
6. Dismiss reverses: sheet 200ms, backdrop 140ms; originating tile highlights 400ms; URL clears `?drawer`; focus returns to tile.

**Reduced motion:** instant open, opacity 0→1 only.

### Q8. Secondary surfaces structure

```
[ AIReadHero ] (persistent)
[ ConvictionTile rail — up to 5 tiles ]
─── Layer 2 ───
[ Risk shifts ]    [ Opportunity shifts ]   ← paired (Codex R2)
[ Promotions today ]
─── Layer 3 ───
[ Catalysts this week ]
[ Watchlist ] (compact table)
[ Sector rotation ] (single sentence)
─── Layer 4 ───
[ Decision Diet status ]
[ Engine version footer ]
```

**Hard rules:** no infinite scroll, page ends; no "see more →" paginators; macro is one sentence in Layer 3; risk shifts paired alongside opportunities (resists feed-of-opportunities drift).

### Q9. Mobile experience (< 720px)

- AIReadHero: 16–18px, two lines max.
- ConvictionTiles: **horizontal scroll rail** with `scroll-snap-type: x mandatory`, `scroll-snap-align: start`. Tiles 82vw wide, min 280, max 320, height 184. Sliver of next tile visible.
- Drawer: 92vh bottom sheet, drag handle (32×4px), swipe-down dismiss (only when scroll at top).
- Layer 3 surfaces: collapse to accordion, closed by default.
- Tap targets: 44px minimum on close + drawer controls.

### Q10. Biggest failure modes

1. **Tile compaction → empty billboards.** Mitigation: 304×184 floor, 5 required rows, refuses-to-render if decision sentence > 140 chars.
2. **Bear case becomes background texture.** Mitigation: inline Bull/Bear on tile (Confirmed+); drawer forces invalidation before bear case; the click hides detail, not risk existence.
3. **AI voice character drift over months** (Opus R1). Mitigation: composer lint rejects emotional verbs, persona language, first-person outside hero; PR review enforces.
4. **Drawer overuse interaction tax** (Opus R1). Mitigation: tile carries enough state (verb + tier + decision sentence + Bull/Bear) that 70% of sessions don't need to open the drawer.
5. **Sycophantic AIReadHero.** Mitigation: composer slot grammar locked, banned-token unit tests, regime-snapshot cadence.

### Q11. Final synthesis (top 5 master locks)

1. **ConvictionTile = 304×184, 5 required rows on Confirmed+ including inline Bull/Bear pair.** Refuses-to-render schema. Monochrome verb pill (text-color accent permitted, fill banned). No `+18%` upside in any framing.
2. **AI voice mixed regime: third-person in hero, implicit elsewhere.** Composer-enforced, lint-rejected outside boundary.
3. **Drawer = modal sheet at 88vh desktop / 92vh mobile**, 9 sections (UX-10 §9 + recap header, invalidation moved earlier), single continuous scroll, 220ms cubic-bezier(0.32, 0.72, 0, 1), single instance, all 5 dismiss paths, anchor return.
4. **The click hides detail, not risk existence** (Codex's R1 framing, adopted verbatim) — load-bearing principle behind inline Bull/Bear, Confirmed+ refuses-to-render, drawer's invalidation-early order.
5. **Depth = single 4% radial vignette behind hero + three tokenized elevation levels + section dividers.** No mood-ring, no glassmorphism, no animated ambient, no state-mapped hue.

---

## Master doc recommendations

When Opus writes `docs/research/UX_11_INTERACTIVE_COPILOT.md`:

1. **Open with the §13.9 resolution principle (Codex R1): "The click hides detail, not risk existence."** First paragraph. Every spec traces back to it.

2. **ConvictionTile floor: 304×184.** Document dimension dispute (Gemini→320×160, Codex→300–320×176, Sonnet→304×184, Opus→300×190 revised); recommend synthesis. Width responsive 280–320; height fixed at 184.

3. **Inline Bull/Bear pair on Confirmed+ as tile invariant.** Refuses-to-render if Counter missing on Confirmed+. Both Opus (R2 concede) and Codex (R2 partial concede via "compact risk marker") accept the principle. The 2-line/11px-tracked variant addresses Opus's R2 overflow critique.

4. **Voice regime: mixed.** Hero third-person; tile reads + drawer body implicit. Composer-enforced; lint rejects "AI" word outside hero label and decision-log subject. Synthesis of Opus R1 implicit-voice insight + Codex/Sonnet/Gemini's third-person-in-hero requirement.

5. **Drawer is modal with backdrop dim. Document Opus's dock dissent.** Recommend modal default with reasoning: focus-trap a11y, "thesis needs concentration," media-vs-capital distinction. Frame Opus's dock as "validated alternative for future user testing" — do not foreclose, do not ship.

6. **Drawer section order: 9 sections with invalidation moved one slot earlier** (after recap, before Driver/Counter). Frame as strict tightening of UX-10's "invalidation before target" lock, not a violation.

7. **Motion budget: 220ms sheet rise on `cubic-bezier(0.32, 0.72, 0, 1)`, 160ms backdrop fade.** Reject Codex's 280ms (slow), Opus's 240ms `(0.16, 1, 0.3, 1)` (lands hard), Gemini's 350ms (theatrical).

8. **`+18% upside` banned on tile across all framings.** Codex's dissent as monitored exception.

9. **Conviction-density ambient lighting banned.** Gemini's dissent as explored and rejected.

10. **URL state via `?drawer=<TICKER>`.** Bookmarkable, shareable.

11. **Implementation phasing: 11A** (tokens + composer + voice transformer + lint) → **11B** (ConvictionTile + AIReadHero) → **11C** (ReasoningDrawer + URL state + a11y) → **11D** (parallel route mount at `/overview?view=copilot`) → **11E** (secondary surfaces) → **11F** (motion polish + radial depth) → **11G** (real-data wiring + freshness decay + telemetry on drawer opens/dismissals).

12. **Anti-pattern additions to UX-10 §12 lock list:**
    - No emoji circles on verbs.
    - No tinted fill on verb pill (color on text/glyph permitted).
    - No standalone target percentage on tile.
    - No state-mapped ambient hue.
    - No dock-style sheet that leaves page scrollable underneath a thesis read.
    - No auto-opening drawer on first session (Opus's onboarding theater rejected).
    - No staggered text fade-in inside drawer ("AI is typing" theater).
    - No first-person "I" or "we" outside the AIRead hero label.
    - No vertical-stack tiles on mobile (read as feed; horizontal snap is the cockpit pattern).

The §13.9 tension is resolved across all four models in some form. The bear case is on every Confirmed+ tile (existence) and forced past the eye in the drawer (detail). UX-11 does not regress UX-10's structural honesty; it composes it differently. **Premium remains non-permissive.**
