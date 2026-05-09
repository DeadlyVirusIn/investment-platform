# Model: Claude Opus 4.7
## Round: 1

## Position summary (300 words max)

The user is right that UX-10's homepage feels static. They are wrong about WHY. It's not because the cards are too detailed; it's because the cards are too **commensurable**. Every UX-10 ActionCard is the same size, same chrome, same structural weight regardless of what it's saying. The eye has nothing to grab onto.

UX-11's fix is NOT just "make cards smaller and stuff detail into a drawer." That's a partial answer that risks regressing into the very signal-spam UX-10 was designed to resist. My position: **the homepage tile is not a smaller card; it is a different visual object — a CONVICTION READ.** A read communicates *state*, not data. State changes daily; data accumulates over weeks. The tile shows: what the AI's stance is *right now*, why-in-five-words, and how strongly. That's enough to scan; everything else is interaction.

Three load-bearing positions:

1. **AIReadHero is the product's only first-person voice.** No "AI" word appears anywhere else on the page. Below the AIRead, copy is implicit-first-person — "Becoming more selective after this rally" rather than "The AI is becoming more selective." Single voice prevents AI-attribution-spam.

2. **Tiles are 320×220 — bigger than user's 280×180 mockup.** 280×180 is mobile-Twitter-card sized and forces every tile to a single-line summary that can't carry a five-word thesis read alongside the verb + ticker + tier. 320×220 fits 3 across at 1080 page width with proper gutters; that's the locked stride.

3. **Drawer is a dock, not a modal.** Slides up from bottom, grows to ~70% viewport, but the page underneath stays scrollable so the user can scan adjacent tiles WHILE the drawer is open. This kills the "modal interrupts flow" problem and matches Spotify/Apple Music's Now Playing pattern, which is the closest cinematic-but-functional reference.

The UX-10 invariants survive intact inside the drawer.

## Q1. ConvictionTile shape

Tile spec: **320×220px on desktop, full-width on mobile**.

```
┌──────────────────────────────────────┐
│  [OPEN]   ●●●●                       │ ← row 1: verb pill + tier glyph (right-aligned)
│  NVDA                                 │ ← row 2: ticker (24px, weight 600)
│  Semis cycle continuation             │ ← row 3: thesis name (14px, weight 400, max 5 words)
│                                       │
│  ──────────────────                   │
│                                       │
│  Add through $172                     │ ← row 4: 4-word action read (14px, AI voice)
│                                       │
│  ⚖ ●○○                14h ago         │ ← row 5: bear-glyph + risk-dot + freshness
└──────────────────────────────────────┘
```

5 elements maximum:
1. Verb pill (UX-10 component, unchanged) + tier glyph
2. Ticker (the visual anchor — large, monospace numbers if applicable)
3. Thesis name (≤5 words, no punctuation)
4. **Action read** — 3–6 words in active AI voice. NOT a target, NOT a percentage, NOT a confidence number. Examples: "Add through $172" / "Trim 30%" / "Hold above $415" / "Exit at market." This is the user's "+18% upside" replacement; numbers belong in the drawer.
5. Risk dot (3 sizes, only ever amber or red — same UX-10 component used on options) + freshness ago-time

**BANNED on the tile (carrying UX-10 anti-patterns forward):**
- Color emoji circles (🟢🔴🟡) — saturation > 50%, casino tell. Verb pill + tier glyph encode the same semantic without the casino visual.
- "+18% upside" or any single-number target — anchors the eye on upside (UX-10 §3 banned).
- Decision sentence in full (that's the drawer).
- Driver/Counter excerpt — diluted thesis is worse than no thesis.
- Sparklines — adds chartjunk; tile is for state, not history.

Click target: **the entire tile**. Cursor becomes pointer on hover. No "Open drawer →" CTA — the tile IS the affordance.

## Q2. AIReadHero

**Single sentence, 60–100 chars, in implicit first-person voice.** Renders as:

```
TODAY'S AI READ
Becoming more selective after this rally; valuation now leads timing.
```

The label "TODAY'S AI READ" is the only attribution. The sentence itself does NOT say "the AI is" or "the engine believes" — implicit voice. Three good examples:

- "Becoming more selective after this rally; valuation now leads timing."
- "Quiet day. Three theses unchanged. No new entries warranted."
- "Defensive setup forming as macro tightens; one trim candidate."

Three bad examples (from the user brief or natural drift):

- ❌ "The AI is becoming more selective..." — over-attributes; AI-as-character drift.
- ❌ "🤖 AI Insight: Selective today" — emoji + label = AI-theater carnival (UX-9 ban).
- ❌ "Selective, valuation-sensitive." — analyst-note-tone; the user explicitly killed this.

Update cadence: **once per session, on first paint.** Not real-time. Not per-poll. Updating mid-session would make the hero feel jittery. The sentence is the AI's stance for THIS session of THIS user; if the engine state changes meaningfully, the next session's hero reflects it.

Quiet-day variant follows UX-10 lock copy: *"Quiet day. Three theses unchanged. No new entries warranted."* (note: "warranted" not "recommended" — slightly more decisive, less hedging-bureaucratic).

Anti-AI-theater compliance: no orb, no chat dock, no chip rail, no "Powered by [model]." The label "AI READ" is the *single* permitted instance of the word "AI" in the page chrome.

## Q3. ReasoningDrawer experience

**Drawer is a dock, not a modal.** Slides up from bottom of viewport. Grows to **70% viewport height** at full open; page underneath remains scrollable. User can drag the top edge to resize.

Sections (vertical scroll, single surface — UX-10 §9 lock preserved):

1. **AI READ FOR THIS POSITION** — single sentence in implicit AI voice (3-line cap). Always above thesis recap.
2. **Decision sentence** — UX-10's existing decision sentence, 18px, full visual weight.
3. **Driver / Counter / Catalyst** — UX-10 thesis triplet, equal visual weight.
4. **INVALIDATION** — full UX-10 invalidation block.
5. **Levels & action plan** — UX-10's collapsed-by-default block, default-expanded INSIDE the drawer (the drawer IS the user's intent to act).
6. **What changed since you last looked** — diff against the user's last drawer-open.
7. **Compared candidates / My pattern with this AI / Calibration line** — UX-10 §9 final 3 sections.
8. **Engine version + last retrain** — tiny grey footer.

**Motion:** 240ms (the UX-10 motion budget cap) cubic-bezier(0.16, 1, 0.3, 1). Slide-up with subtle backdrop dimming (page goes to 60% opacity, NOT fully obscured — preserves the "dock" feel).

**Dismiss behavior:**
- Click outside drawer → dismiss
- ESC key → dismiss
- Browser back button → dismiss + replace state (not push)
- Drag drawer edge below 30% viewport → dismiss
- Open another tile while one is open → animate-swap content within same drawer (no double-open ever)

**Anchor return:** dismissing returns scroll position to the originating tile. No jump to top.

**Mobile:** drawer becomes a true bottom sheet at 90% viewport. Drag handle visible. Same dismiss rules.

## Q4. AI voice rules

The AI voice composer transforms engine output strings → user-facing copy. Rules:

**Rule V1 — Implicit voice.** No copy except the AIRead hero label says "AI." Everywhere else, the AI is implicit through directness.

| Engine | UX-11 voice |
|--------|-------------|
| `recommend_action(NVDA, OPEN)` | "Add through $172" |
| `valuation_pressure_increasing` | "Valuation pressure mounting" |
| `regime_state=cautious` | "Becoming more selective" |

**Rule V2 — Active voice, present tense, declarative.** Banned hedges: "should consider," "may want to," "could potentially," "in our view." A copilot states; it doesn't suggest.

**Rule V3 — Subject is the market or the position, never the user.** "Valuation pressure mounting" not "Your portfolio has valuation pressure." User-direction is implicit through the verb (OPEN means *you* should open).

**Rule V4 — No prediction language.** Banned: "will rally," "likely to," "expected to outperform." AI states observed conditions; market does what market does. "Earnings durability holds" is fine; "earnings will beat" is banned.

**Rule V5 — Five-word constraint on tile reads.** Forces the composer to pick one word that's load-bearing. "Add through $172" — the load-bearing word is "through." "Trim 30%" — load is "30." Constraint produces precision.

**Rule V6 — One-sentence constraint on AIRead hero.** Two sentences split the eye; one sentence forces a single point of view per session.

**Rule V7 — No persona, no name, no "I."** The AI does not have a name. It does not say "I think." It speaks *through* its observations. This is what differentiates a copilot from a chatbot.

## Q5. Visual hierarchy ramp

Four layers. Each layer has a different chrome:

| Layer | Surface | Border | Spacing | Where |
|-------|---------|--------|---------|-------|
| **PRIMARY** — AIRead + tile strip | `--ux10-bg-card` (raised) on subtle radial gradient backdrop | 1px `--ux10-border-card` | 32px around, 24px between tiles | Top viewport |
| **SECONDARY** — Risk shifts + Opportunities | `--ux10-bg-card` flat | 1px `--ux10-border-card` | 24px around, 16px between | Below tile strip |
| **TERTIARY** — Watchlist / Catalysts | `--ux10-bg-page` (no card) | bottom-border separator only | 16px around | Mid-page |
| **QUATERNARY** — Footnote / Engine status / Settings link | `--ux10-bg-page` | none | 12px around | Footer |

This is a real ramp — each layer LOOKS different. The eye instantly knows where to look.

## Q6. Subtle background depth

The UX-10 ban was "page-level conviction tint backgrounds (mood-ring failure)." A static, non-conviction-bearing depth treatment is allowed.

What survives:

1. **Single radial gradient at top of viewport**, behind AIRead + tile strip. `radial-gradient(ellipse at 50% -20%, hsla(228, 30%, 22%, 0.4) 0%, transparent 70%)`. Static; never changes color or intensity. This is visual depth, not signal.

2. **Three elevation levels** (already tokenized: `--ux10-bg-page` `--ux10-bg-card` `--ux10-bg-elev`). Use them. PRIMARY tiles sit on `--ux10-bg-card` over the radial-tinted page; SECONDARY blocks sit on `--ux10-bg-card` over plain page; QUATERNARY items have no card at all.

3. **A 1px highlight at the top edge of every PRIMARY-layer card** (`box-shadow: inset 0 1px 0 rgba(255,255,255,0.04)`). Subtle physical-light cue.

What dies (UX-10 carryforward):
- All gradients on cards themselves
- Glassmorphism
- Page-level conviction tints
- Animated backgrounds
- Conviction-tied background colors

## Q7. Tile click → drawer interaction

Step-by-step:

1. **Hover state** (200ms): tile gets a 1px brighter border + subtle 2px upward translation. No color change.
2. **Click**: tile briefly scales to 0.98 (60ms haptic-like compression). Drawer begins slide-up (240ms cubic-bezier).
3. **During slide-up** (240ms): page background dims to 60% opacity (NOT 0%; preserves dock feel). Tile that was clicked gets a faint highlight border so user can re-find it on dismiss.
4. **Drawer fully open**: focus traps in drawer (a11y). ESC dismisses. Click outside drawer dismisses. Drag drawer edge below 30% viewport dismisses.
5. **Open another tile**: drawer content animates-swap (160ms fade-out / 160ms fade-in of content), drawer stays open. No double-open.
6. **Dismiss**: 200ms slide-down. Page restores opacity. Scroll returns to anchor tile.

**Motion budget compliance:** all transitions ≤ 240ms. No translation > 8px (the 0.98 scale is fine — that's compression, not translation).

**Accessibility:** `role="dialog"` on drawer with `aria-modal="false"` (semi-modal — page underneath remains operable). Focus trap inside drawer when open. ESC key bound. Tile has `aria-haspopup="dialog"` and updates `aria-expanded` while drawer is open for that tile.

## Q8. Secondary surfaces structure

Below the AIRead + 3-tile primary strip, in order:

```
PRIMARY STRIP (3 tiles)

────────── thin section divider ──────────

OPPORTUNITY SHIFTS  (2-3 horizontal tiles, smaller — 240×140)
  → "OPEN COST became Confirmed since Friday"
  → "Watching: PLTR moved to Working tier"

RISK SHIFTS  (1-2 horizontal tiles, smaller)
  → "TSLA freshness moved to Aging — review"

────────── thin section divider ──────────

WATCHLIST  (4-column horizontal grid of 60×60 chips with ticker only)
CATALYSTS THIS WEEK  (vertical list, 1 line per event)
PORTFOLIO SHIFTS  (vertical list)
SECTOR ROTATION  (single sentence summary + tiny sparkline)

────────── thin section divider ──────────

QUATERNARY: engine version, last retrain, link to /overview?view=working
```

Each section title is 11px uppercase tracked. Sections have `id` attributes for deep-linking.

## Q9. Mobile experience

Below 720px:

- AIRead becomes 2-line max (50ch line-height 1.5).
- Tile strip becomes vertical stack (full-width tiles, max 3 visible without scroll).
- Drawer becomes true bottom sheet at 90% viewport with drag handle.
- Section dividers become slightly thicker for tap-zone clarity.
- Click target padding increased to 12px.
- Below 480px: tiles still full-width; thesis name truncates with "..."; 4-word read max instead of 5.

NO horizontal-scroll tile carousel on mobile. Horizontal scroll on a financial app reads as ticker-feed (banned).

## Q10. Biggest failure modes

**Top 3:**

1. **Drawer overuse.** User clicks tile → drawer → reads → dismisses → clicks next tile → drawer → reads → dismisses. The interaction tax destroys the "fast scan" promise. *Mitigation:* tile must carry enough state (verb + tier + 5-word read + freshness) that 70% of sessions dismiss in <3 seconds because the tile already answered the user's question. The drawer is for the 30% who need depth.

2. **AI voice becomes character drift.** "The AI" / "I" / persona-creep. First user reads "I'm becoming more selective" and treats the AI as a person. Within months, copy drifts toward chat-bot patterns and the anti-AI-theater locks erode. *Mitigation:* Rule V7 is engineering-enforced. Lint catches first-person pronouns + "AI" outside the AIRead hero label. Composer rejects strings containing "I think" / "I believe" / personality language.

3. **Background depth + radial gradient + 3 elevations + tile chrome differences = visual noise.** What looks "alive" in mockup looks chaotic in browser. *Mitigation:* ship 11A with depth treatments BEHIND a feature flag; visually validate at full data load before the flag flips on.

**Honorable mention:** the click-to-open friction may make existing UX-10 ActionCard users feel they LOST functionality (they used to see it all without clicking). Onboarding: first-session, the first tile auto-opens its drawer for 3 seconds then closes — teaches the pattern without explanation.

## Q11. Final synthesis (top 5 master locks)

1. **ConvictionTile is 320×220, 5 elements max, click-anywhere → drawer.** Not a smaller ActionCard.
2. **AIReadHero is one sentence, implicit first-person voice, "AI READ" is the only AI attribution on the page.**
3. **Drawer is a dock not a modal — 70% viewport, page underneath remains scrollable.**
4. **Visual hierarchy ramp = 4 distinct chrome treatments per layer.** Eye-distinguishable at first paint.
5. **AI voice composer rules V1-V7 are lint-enforced.** Persona drift gets rejected at PR review.

Implementation phasing: 11A tokens + composer + voice transformer; 11B ConvictionTile + AIReadHero; 11C ReasoningDrawer; 11D parallel route mount at `/overview?view=copilot`; 11E secondary surfaces; 11F motion polish + radial depth; 11G real-data wiring.

If forced to ship one: **the drawer-as-dock pattern**. Modal-drawer would feel like 2018 fintech; dock-drawer is the visual signature that makes UX-11 feel cinematic without violating any UX-10 lock.
