# Model: Sonnet 4.6
## Round: 1

## Position summary (300 words max)

UX-11 is not a redesign. It is a **layered re-composition** of UX-10 that adds two surfaces (the AI Pulse hero and the Reasoning Drawer) and one interaction primitive (tile click → drawer slide), without deleting a single trust safeguard from the locked master. The user's diagnosis is correct — UX-10 reads as a research terminal because the hero is rendering full ActionCards that were specced for the Cockpit. UX-10 §6.1 caps hero at 5 cards; it never said those cards must be the full 720px atom. **The fix is compositional, not architectural.**

My core position across Q1–Q11:

1. **ConvictionTile is 320×176px, not the user's 280×180px.** The mockup is 4 lines too thin to carry a 100-char decision sentence. UX-10 L6 says the decision sentence is the largest element on every card — that invariant must survive the compaction. I will not let a tile show only "AI infra demand accelerating" (a thesis name) without the decision sentence ("Add through $172 while data-center margin expansion holds"). One degrades; the other commits.
2. **AIReadHero is composer-generated from the regime ribbon UX-10 already specced**, not a free-form AI sentence. Composer rules, not improv.
3. **The drawer is UX-10 §9 verbatim plus a recap-paragraph header.** I refuse to redesign 7 sections that 4 models already converged on.
4. **The bear-case-behind-a-click problem is real and I do not dismiss it.** Resolution: tile renders Driver AND Counter inline as a 2×1 micro-grid (`Strong thesis · Bear: capex rollover risk`), so the click reveals depth, not the existence of the bear case.
5. **Failure mode #1: tile compaction creates "newsfeed scrolling"**. Mitigation: hero hard-cap stays at 5, no infinite scroll, drawer is the only depth path.

The phrase "AI investing copilot" must not become an excuse to weaken structural honesty. Premium ≠ permissive.

---

## Q1. ConvictionTile shape

**Locked spec:**

- **Dimensions:** `320px × 176px` desktop. `min-width: 280px; max-width: 360px`. Reject the user's 280×180 mockup target. 280px cannot fit a 100–140 char decision sentence at 14px/1.4 line-height without truncating to ellipsis on line 3, and ellipsing the decision sentence violates UX-10 L6 ("decision sentence is the largest visual element").
- **Internal padding:** `16px 16px 14px 16px` (8px grid).
- **Background:** `var(--ux10-bg-card)` = `#0F1115`. No gradient. No glassmorphism. No tinted background fill (that would violate Opus's R2 "no mood-ring" lock).
- **Border:** `1px solid var(--ux10-border-card)` = `#1F2329`. `Confirmed`+ tier adds `border-left: 1px solid var(--ux10-conviction-tint)` per UX-10 §11.2.
- **Border-radius:** `4px`. Sharp enough to read as instrument, not soft enough to read as iOS widget.

**Required fields (in render order, top to bottom):**

```
Row 1 (24px):  [VERB pill]                          [●●●○ · 14h]
Row 2 (22px):  NVDA · Semis cycle continuation
Row 3 (44px):  Add through $172 while data-center
               margin expansion holds.                ← decision sentence, 14px, 2 lines
Row 4 (16px):  Bull: capex +22% · Bear: hyperscaler rollover risk
Row 5 (16px):  Invalid < $158  ·  Horizon ~6w
```

That is **5 rows**, all required, total `~150px` content + 26px padding = 176px. Not negotiable.

**Banned fields on the tile:**

- `+18% upside` — this is the user's mockup but it violates UX-10 §12 anti-pattern "Target on collapsed card without paired downside + invalidation." Upside without paired downside is hero-anchoring. Ship the **invalidation distance** instead (`Invalid < $158`), which UX-10 already specced for the Cockpit conviction strip.
- "Strong thesis" as a free-floating phrase — vacuous. Replace with the named driver clause (`Bull: capex +22%`).
- Numeric probability (`0.82`).
- F/T/M segmented bar.
- Star rating, ring, progress bar.
- Target price, T1/T2/T3 — those live in the drawer's "Action plan" section per UX-10 §7.2.

**Verb treatment:** UX-10 §3.2 verb pill, unchanged. Monochrome `#9CA3AF`, 11px uppercase, sharp 0px border-radius, 1px border. **No green emoji circle.** The user's `🟢 OPEN` mockup violates UX-10 §11.3 "casino green/red (high saturation) dies." A green emoji = uncontrolled saturation in user font stack = casino tell. Reject.

**Tier:** Glyph form (`●●●○`). Named tier is redundant on the tile — the drawer carries the named form. Saves 6 chars per tile.

**Freshness:** Visible as relative timestamp (`14h` = "fresh, last reviewed 14h ago"). Promotes UX-10 §4.1 freshness to first-class on the tile because UX-10 says fresh ≠ stale matters most when scanning a strip of 5.

**Click target:** Entire tile is the affordance. No "See plan" button on the tile. Reasoning: a button-inside-tile produces dual click targets and forces the user to aim. The whole tile clicks → drawer opens. Cursor: `pointer` on hover. Keyboard: tile is `<button role="button">`, focus ring `2px outline #7B8CFF` per UX-10 §11.1 accent.

**Hover state:** `transform: translateY(-1px); border-color: #2A2F37; transition: 120ms ease-out;`. No scale, no glow, no shimmer. UX-10 S9 caps motion at 240ms / 8px translation; I'm well inside.

---

## Q2. AIReadHero

**Position:** AIReadHero is **not free-form AI prose.** It is a composer-templated single sentence with strict slot grammar. UX-10 §6.1 already specced "Market regime · Selective, valuation-sensitive" as the regime ribbon. UX-11 promotes that ribbon to a 2-line hero block but **inherits the composer**.

**Spec:**

- **Length:** 64–110 chars total. Two lines maximum at 18px size.
- **Voice:** active third-person AI voice. "The AI is becoming more selective" not "We are becoming more selective" (false consensus) and not "AI thinks selectively" (broken grammar) and not "Be selective" (imperative addressed at user → coach voice, banned).
- **Update cadence:** **once per regime snapshot refresh** (existing backend cadence, ~6h). Not real-time. Not per-session. Real-time AI prose creates the Bloomberg-ticker feel UX-10 was built to escape.
- **Slot grammar:**

```
[STANCE_VERB] [QUALIFIER_CLAUSE].
[CONSEQUENCE_CLAUSE].
```

Where:
- `STANCE_VERB` ∈ {"is becoming more selective", "is leaning into", "is reducing exposure to", "is holding pattern on", "sees no new entries warranted in"}
- `QUALIFIER_CLAUSE` describes the regime evidence ("after this week's rally", "as macro data softens")
- `CONSEQUENCE_CLAUSE` makes the actionable implication ("Add only where earnings durability offsets valuation risk", "Maintaining existing positions today")

**Three GOOD examples:**

```
The AI is becoming more selective after this week's rally.
Add only where earnings durability offsets valuation risk.
```

```
The AI is reducing exposure to long-duration semis as guide cuts mount.
Three trims posted today; no new entries.
```

```
The AI sees no new entries warranted in this regime.
Holding 3 positions; reviewing on Friday close.
```

**Three BAD examples (rejected):**

- ❌ "Selective, valuation-sensitive." → UX-10 §6.1 ribbon, but it's static label voice. Promotes well to ribbon, fails as Hero.
- ❌ "Hey there! Today the AI is feeling cautious 😊" → sycophantic, emoji, anthropomorphized. Violates UX-10 anti-pattern "AI feels alive" ≠ "AI has feelings".
- ❌ "AI THINKS YOU SHOULD TRIM TSLA NOW." → all-caps shouting (banned UX-10 §11.3), imperative, time-pressure, target-singling.

**Anti-AI-theater compliance:** No orb, chat dock, "Powered by Claude" badge, or suggested-question chips. Presence comes from **language alone** — third-person framing gives presence without ornament.

**Quiet day path:** Hero swaps to UX-10 L3 locked copy verbatim: *"Market regime: noisy. Maintaining existing positions. No new entries recommended."*

---

## Q3. ReasoningDrawer experience

**Position:** Drawer sections are **UX-10 §9 verbatim**, plus one new top-section recap. I refuse to redesign 7 sections that 4 models already locked. UX-11 added the *opening interaction*, not the *content model*.

**Section order (8 sections, single scroll):**

1. **Recap header (NEW for UX-11)** — 60-word plain-language thesis paragraph + verb pill + tier glyph + freshness chip. This is the section the drawer-open animation lands on. Replicates the tile's identifying chrome so user knows context.
2. Driver / Counter / Catalyst — UX-10 §9.2.2, sub-glyph per claim.
3. What changed since last review — UX-10 §9.2.3.
4. Compared candidates — UX-10 §9.2.4.
5. My pattern with this AI — UX-10 §9.2.5.
6. Calibration line — UX-10 §9.2.6.
7. Action plan (collapsed by default in default-mode per D3) — UX-10 §7.1 S4.
8. Engine version footer — UX-10 §9.2.7.

**Motion:**

- **Slide-up duration:** `220ms`. Inside UX-10 S9 240ms cap.
- **Easing:** `cubic-bezier(0.32, 0.72, 0, 1)` — same as iOS sheet presentation. NOT linear, NOT ease-in-out. The 0.72 second control point gives the "settle" that reads cinematic without being theatrical.
- **Translation:** `translateY(100%)` → `translateY(0)`. 8px in CSS terms? No — sheet is 88vh. The 8px cap in S9 was about *idle/hover micro-motion*, not user-initiated sheet presentations. Distinction matters. (Defending preemptively: if Codex argues this violates S9, I reply that S9's intent was anti-distraction-motion, not anti-sheet.)
- **Backdrop:** `rgba(11, 13, 16, 0.6)` (page bg @ 60%). Backdrop fade `160ms ease-out`, starts simultaneously with sheet rise. NO `backdrop-filter: blur` — that's glassmorphism, banned by UX-10 §11.3.
- **Originating tile:** stays in DOM, dims to `opacity: 0.4`. Other tiles dim to `opacity: 0.6`. Reasoning: anchoring the source tile prevents the "where did I come from" disorientation.

**Dismiss behavior (all four supported):**

- Click backdrop → dismiss.
- ESC key → dismiss.
- Browser back button → dismiss (push state on open, pop on close).
- Swipe down on mobile → dismiss.
- Drawer close button (`×`, top-right, 32×32 hit target).

**Anchor return:** On dismiss, scroll position is restored AND the originating tile briefly highlights (`border-color: #2A2F37` for 400ms then fades). Resolves the "where was I" disorientation.

**Multiple drawers:** **Single drawer, period.** Opening a second tile during an open drawer cross-fades content (`120ms`) but does not stack. Stacked drawers create a back-button trap.

**Mobile:** Bottom sheet, `92vh`. Drag handle at top (`32×4px rounded`). Same content order. Same dismiss paths.

---

## Q4. AI voice rules

**Composer rules (transformation patterns):**

- **First-person plural ("we", "our") → banned.** False team voice.
- **First-person singular ("I think") → banned.** AI does not have an "I" worthy of self-claim.
- **Third-person AI ("The AI is becoming...") → preferred.** Non-anthropomorphic, attributable, falsifiable.
- **Imperatives ("Trim Tesla now") → banned.** Coach voice. UX-10 verb pill carries the action label; copy should describe rationale, not command.
- **Hedging ("may want to consider", "perhaps look at") → banned.** UX-10 §3.3 already locked this for decision sentence; extend to drawer copy.
- **"AI found N moves" → banned (UX-10 §12).**
- **"Powered by Claude/GPT" → banned (UX-10 §12).**
- **Suggested-question chips → banned (UX-9 carry-forward).**
- **AI orb / chat dock → banned (UX-9 carry-forward).**

**Tone calibration scale (composer parameter):**

```
voiceMode: "report" | "brief" | "annotated"
```

- `report` — cards, decision sentences. Curt, declarative.
- `brief` — drawer recap header. 60-word paragraph, conversational but third-person.
- `annotated` — drawer Driver/Counter/Catalyst. Bulleted, evidence-cited.

**Presence-without-ornament rules:**
1. The AIReadHero line **always renders at the same top position**. Persistent location = presence.
2. The recap header uses third-person AI voice (`The AI promoted NVDA from Working to Confirmed on May 2 because...`). Persistent voice = presence.
3. The decision log uses past-tense AI voice (`The AI demoted MSFT from Confirmed to Working on Apr 18 because earnings revisions weakened.`). Persistent narrator = presence.

That is enough. No avatar, no chat, no chips. The AI is the **narrator of the page**, not a character in it.

---

## Q5. Visual hierarchy ramp

**Four layers, concrete tokens:**

| Layer | Surface | Background | Border | Type scale | Spacing |
|-------|---------|------------|--------|------------|---------|
| **PRIMARY** | AIReadHero + ConvictionTile strip | `--ux10-bg-page` `#0B0D10` (hero) / `--ux10-bg-card` `#0F1115` (tiles) | hero=none, tile=`1px #1F2329` | hero=18px, tile=14px | 24px section padding |
| **SECONDARY** | High-priority opportunities, risk shifts | `--ux10-bg-card` `#0F1115` | `1px #1F2329` | 14px | 16px row gap |
| **TERTIARY** | Watchlists, catalysts, changes | `--ux10-bg-page` `#0B0D10` (no card surface) | bottom border `1px #1F2329` between rows | 13px | 12px row gap |
| **QUATERNARY** | Deep research / operational detail | `--ux10-bg-page` `#0B0D10` | none | 11px (`--ux10-fs-meta`) | 8px row gap, secondary text color |

**Type opacity ramp (NOT a new color, just opacity on `--ux10-fg-primary`):**

- Primary: `100%` → `#F4F5F7`
- Secondary: `60%` → `#9CA3AF` (already tokenized as `fg-secondary`)
- Tertiary: `42%` → `#6B7280` (already tokenized as `fg-tertiary`)

**Section dividers:** `1px solid #1F2329` between layer transitions, with `48px` vertical padding. The divider is the only "decoration" between layers.

**No new colors. No gradients. No elevation shadows beyond what UX-10 §11 tokenized.**

---

## Q6. Subtle background depth

**Position:** Almost nothing. The user said "too dark, too flat" — but UX-10 banned mood-ring page tints, gradient washes, glassmorphism. The legal surface area for "depth" is small.

**What survives:**

1. **Radial vignette behind AIReadHero only.** `radial-gradient(ellipse 60% 40% at 50% 0%, rgba(123, 140, 255, 0.04) 0%, transparent 70%)`. 4% opacity. Single tint. Localized to top 240px. NOT page-wide, NOT card-level. This survives because it does not encode conviction (which would violate the mood-ring ban) and does not appear on cards (which would violate §11.3).
2. **Three tokenized depth levels already exist** — `--ux10-bg-page` `#0B0D10`, `--ux10-bg-card` `#0F1115`, `--ux10-bg-elev` `#13161B`. Use the elev token for the drawer surface specifically. That's the third level finally getting used.
3. **Section dividers** at `1px #1F2329` create rhythm without color.
4. **Tile shadow:** zero. The `1px border` does the job. UX-10 §11.3 capped `box-shadow: > 4px` because anything bigger reads as Material Design.

**What does NOT survive:**
- Conviction-colored page tint (mood-ring).
- Animated gradient ("aurora").
- `backdrop-filter: blur` (glassmorphism).
- Conviction tint on tile background (per Opus R2 lock).
- Vignettes that encode user mood / portfolio P&L.

If after 11C the page still reads "too flat," the answer is **typography spacing, not color.** Increase section padding from 24px → 32px before adding any decoration.

---

## Q7. Tile click → drawer interaction

**Step-by-step:**

1. **t=0ms** — User clicks tile. `pointerdown` event.
2. **t=0–80ms** — Tile receives `border-color: #2A2F37` confirmation feedback. No depress, no scale.
3. **t=80ms** — Drawer mounts. Backdrop element mounts at `opacity: 0`.
4. **t=80–240ms** — Backdrop fades to `0.6` (`160ms ease-out`). Sheet translates from `100%` to `0%` (`220ms cubic-bezier(0.32, 0.72, 0, 1)`). Other tiles dim to `0.6`. Originating tile dims to `0.4`.
5. **t=240ms** — Settled. Focus moves to drawer close button.
6. **Dismiss** — reverse: sheet `translateY(100%)` over `200ms`, backdrop fades over `140ms`. Originating tile highlights for 400ms post-dismiss. Focus returns to tile.

**Total motion budget:** 240ms open, 200ms close. Inside S9 240ms cap (intent-of-rule, see Q3).

**Accessibility:**
- `<dialog>` element with `aria-modal="true"`.
- Focus trapped inside drawer.
- ESC dismisses.
- Backdrop click dismisses.
- Browser back-button dismisses (history API push on open).
- Reduced motion: `@media (prefers-reduced-motion: reduce)` → instant open, no translate, just opacity 0→1 at 80ms.

**Why click-to-drawer not tile-expand:**

Tile-in-place expansion creates layout shift, breaks scroll position, prevents "compare two recommendations" workflow. The drawer model means scroll position never moves. **Sticky context.**

---

## Q8. Secondary surfaces structure

**Below the primary tile strip, in render order:**

```
[ Layer 1: AIReadHero        ] ← persistent
[ Layer 1: ConvictionTile strip — up to 5 tiles, horizontal scroll on overflow ]
─────────────────────────────────────────────
[ Layer 2: Risk shifts       ] ← max 3 rows, condensed list
[ Layer 2: Promotions today  ] ← what changed in tiers
─────────────────────────────────────────────
[ Layer 3: Catalysts this week ] ← bullet list, ticker · event · date
[ Layer 3: Watchlist          ] ← compact table, ticker · tier · last reviewed
[ Layer 3: Sector rotation    ] ← single sentence
─────────────────────────────────────────────
[ Layer 4: Decision Diet status ]
[ Layer 4: Engine version footer ]
```

**Treatment differences:**
- Layer 2 = card surface, 14px type, 16px row gap.
- Layer 3 = no card surface (rows on page background), 13px type, 12px row gap, bottom border separators.
- Layer 4 = 11px meta type, secondary text color.

**Hard rules:**
- No infinite scroll. The page ends.
- No "see more →" paginators that could re-introduce the picks-app feel.
- Macro is **one sentence in Layer 3**, not a section. Resists Bloomberg drift.

---

## Q9. Mobile experience

**Breakpoint: < 720px.**

- AIReadHero: stays at top, type drops to 16px.
- ConvictionTiles: **vertical stack**, full-width (`calc(100vw - 32px)`), height same `176px`. No horizontal scroll on mobile (forces hidden cards out of sight).
- Cap visible at 5; scroll-to-end is the only path to additional.
- Drawer: 92vh bottom sheet.
- Layer 3 surfaces: collapse to accordion. Closed by default.

---

## Q10. Biggest failure modes

**1. Tile compaction reduces decision sentence to ellipsis → kills UX-10 L6.**
The user mockup showed only "AI infra demand accelerating" (a thesis name fragment). If we ship that, we have demoted the *largest visual element* invariant. Mitigation: 320×176px floor, decision sentence rendered at 14px / 2 lines, refuses-to-render if > 140 chars.

**2. Drawer click introduces friction the inline UX-10 layout did not have.**
The user got their bear case for free in UX-10. Now they must click. Mitigation: tile **always renders both Driver and Counter inline** as a single line each (`Bull: capex +22% · Bear: hyperscaler rollover risk`). The bear case existence is visible at scan time; the depth is behind the click. This is the resolution to the explicit tension: drawer-clicking is fine if **bear case visibility ≠ bear case detail**.

**3. AIReadHero composer outputs sycophantic or marketing prose.**
"Discover today's smart picks!" Mitigation: composer slot grammar locked (Q2), unit tests reject any sentence containing banned tokens ("today's picks", "smart", "hot", "discover", "moves").

---

## Q11. Final synthesis (top 5 master locks)

1. **ConvictionTile = 320×176, 5 required rows including Driver/Counter inline pair.** No green emoji, no upside-only anchor, no thesis-name-only mode. Refuses-to-render if any row missing.
2. **AIReadHero = composer-templated slot grammar.** Third-person AI voice. 64–110 chars. Updates on regime snapshot refresh, not per-session. Unit tests reject banned tokens.
3. **Drawer = UX-10 §9 verbatim + recap header.** Single scroll, 8 sections, single instance, 220ms sheet rise on `cubic-bezier(0.32, 0.72, 0, 1)`. Bear case forced past the user's eye on open.
4. **Bear-case-visible-on-tile resolves the §13.9 tension.** Bear case existence is a tile invariant; bear case detail is a drawer reveal. Both conditions satisfied.
5. **Depth is one radial vignette behind the hero at 4% opacity, plus the third tokenized bg level finally used (drawer surface).** No mood-ring, no glassmorphism, no aurora. If page still feels flat, fix typography spacing first.
