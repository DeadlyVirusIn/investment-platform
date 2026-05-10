# Model: Sonnet 4.6
## Round: 1

## Position summary (300 words max)

The cockpit feels dead because UX-12 fixed substrate but kept the room empty. A serif sentence and a 2-col hero on a black canvas isn't an environment — it's a slide. **Living = composition that proves the AI looked at *today* before it laid out the page.** Not animation. Not warmth gradients. Not parallax. *Layout itself as evidence of attention.*

My single load-bearing claim: **the homepage must be one of three named compositions** chosen at session-load by the AI's read of the day — `Solo` (one Confirmed thesis dominates), `Duet` (hero + one challenger), `Field` (4–6 soft theses). Each has a fixed asymmetric grammar. The user learns three rooms, not infinite arrangements. Spatial memory survives because the room *type* is announced in the posture sentence ("One thesis stands alone today"), not discovered by scroll.

Visual gravity is delivered by **one technique repeated brutally**: the hero occupies a 7-of-12 column span with a 5-col negative-space well to its right containing only the page-state line and a single secondary metric. The 5-col well is the gravity well — emptiness creates pull. Subordinates appear *below the fold* (40vh+1px), spanning 4 cols each with a 96px gap above them. The fold becomes a horizon, not a slot.

Cinematic without casino: depth via **three static atmospheric layers** — base canvas (#0A0908), stage zone (#0D0B09 + 2.5% amber), and a *thesis halo* (radial gradient at 4% opacity, 800px radius, behind hero only). No shadows. No glow. No motion. The halo is a static lighting cue, like a spotlight in a Wes Anderson frame.

AI presence: the *composition itself* is the AI. When the page chooses `Solo`, that is the AI saying "I only see one thing today." When it chooses `Field`, that is "I see noise."

Habit-forming via **session-diff**: posture sentence reads "Since you left, conviction shifted on NVDA." Continuity, not gamification.

---

## D1. Visual philosophy evolution (UX-12 → UX-13 manifesto)

UX-12 said: *the substrate should disappear.* It did. The result is a beautiful empty room.

UX-13 says: **the room must show that someone has been arranging it.** Not by moving the furniture while you watch (motion ban), but by *what is and isn't there when you walk in.*

The manifesto in five lines:

1. **Composition is content.** The shape of the page is a sentence the AI writes about today.
2. **Emptiness is a brushstroke.** A 5-col well is louder than 5 cols of tiles.
3. **Three rooms, not infinite layouts.** `Solo / Duet / Field`. Spatial memory survives because the user learns three named rooms.
4. **The fold is a horizon.** Above-fold is conviction. Below-fold is context. The 1px cut at 40vh is a literal horizon line.
5. **Living = chosen.** The page was *chosen* for today. Not animated, not adaptive-while-you-watch — chosen at the door.

This is closer to Apple's keynote stage (one object, vast negative space, focused light) than to Linear's grid. Linear is the grammar of efficiency. Apple-keynote is the grammar of conviction. We need conviction.

Reference: Arc Browser's "Spaces" — entering a Space *changes the entire chrome*, not just the content. We borrow that mechanic for `Solo / Duet / Field`. Reference: Apple's macOS Sonoma desktop picker — three wallpaper "moods" that shift atmosphere without any animation. The user *names* the mood by choosing it; we let the AI name the mood by choosing it for the user.

---

## D2. Homepage recomposition (specific asymmetric layout)

**Grid:** 12-col, 1440px max width, 80px outer margin, 32px gutter (UX-12 spacing scale).

**The `Duet` composition (default for typical days, ~60% of sessions):**

```
[80px margin][col 1 ────────── col 7][32px gap][col 8 ──── col 12][80px margin]
              HERO (304×184 schema       NEGATIVE WELL
              centered in span,           - posture sentence (22pt serif)
              scaled to 480×290)          - page-state line (11pt mono)
                                          - ambient timestamp
              [stage-zone tint            - one secondary metric
               with thesis halo]          [no card, no chrome]

────────────────── 1px hairline at 40vh ──────────────────

[col 1 ─ col 4][gap][col 5 ─ col 8][gap][col 9 ─ col 12]
   SUB tile        SUB tile           SUB tile
   (304×184)       (304×184)          (304×184)
   below-fold zone (#0A0908, no tint)
```

The hero is **not centered.** It sits left-of-center, in cols 1–7. The cols 8–12 well is the gravity well. This breaks symmetry decisively. The eye lands on the hero (mass), then drifts right into emptiness (release), then down (curiosity).

The hero ConvictionTile schema (304×184) is preserved by *centering* it inside its 7-col span (which is ~720px wide). The tile renders at its native 304×184 in the *upper-left* of that span, with the lower-right of the span occupied by the *thesis halo* gradient and a single 36pt serif "verb glyph" (OPEN / HOLD / TRIM / EXIT). This is the only place the verb appears at 36pt anywhere in the system. It is the focal point.

This satisfies T1: the schema is locked, but its *placement and scale of surrounding atmosphere* is asymmetric.

---

## D3. Hierarchy system (visual gravity + eye-flow choreography)

Five-step eye flow, measured in saccades:

1. **Saccade 1 (0–400ms): posture sentence** in cols 8–10, top of viewport. 22pt Source Serif 4, weight 400. It's the first thing read because it's the only sentence.
2. **Saccade 2 (400–800ms): hero verb glyph.** 36pt serif, in lower-right of the 7-col hero span. Mass pulls the eye left.
3. **Saccade 3 (800–1200ms): hero schema rows.** The 5-row ConvictionTile content reads top-to-bottom inside the hero.
4. **Saccade 4 (1200–1800ms): negative well drift.** The eye finds the 11pt mono page-state line, then the timestamp. This is the *exhale.*
5. **Saccade 5 (1800ms+): scroll.** The 1px hairline at 40vh signals horizon. Subordinates exist below.

Visual gravity is **measurable**: it's the ratio of pixel mass (hero halo + verb glyph + tile) to negative space (5-col well). Target ratio 1.4:1, weighted toward hero. Compare to Apple's iPhone 15 Pro product page hero: ratio ~1.6:1, image-left, copy-right with massive air. Compare to Perplexity's home: ratio ~1.0:1 (centered logo + search). We are closer to Apple than Perplexity — Perplexity is a *tool entry*, we are a *briefing*.

Subordinate tiles use **equal mass intentionally** below the fold. The hierarchy is one-vs-many, not graded-many. This is a Linear pattern: Linear's issue list has flat hierarchy *because* the inbox header has dominant hierarchy.

T3 resolved: the hero gets the halo (unique chrome), the verb glyph (unique scale), and the negative well (unique adjacency). Subordinates get none of the three. They are explicitly subordinate, and they know it.

---

## D4. Dynamic composition (how does layout adapt to content?)

Three named compositions, AI-chosen at session-load. **Choice is locked for the session** (T4: spatial memory). Refresh recomputes.

**`Solo`** — One thesis at Confirmed+ tier, no other thesis above Forming. Used when the AI sees a singular call.

```
[80px margin][col 1 ─────────────────── col 9][32px gap][col 10 ─ 12]
              HERO at 720×440 scale         vertical
              (1.5× normal hero)            posture stack
              thesis halo at 1200px         + timestamp
              radius, 6% opacity            (no metrics)
                                            
── 1px hairline at 60vh (lowered horizon) ──

[col 1 ─ col 12]
   "Other 4 watch-list items have no thesis change today."
   single line, 14pt, dim text
   no tiles
```

`Solo` is the most cinematic. It is the equivalent of Apple's iPad Pro launch page where the device fills 80% of viewport with one phrase. **The page itself says "today is about one thing."**

**`Duet`** — Hero + one challenger thesis. Default. (See D2.)

**`Field`** — 4–6 Forming or Tracking theses, no Confirmed. Used on noisy days.

```
[80px margin][col 1 ─ col 12][80px margin]
              POSTURE: "Six theses forming. None resolved."
              22pt serif, full width

────── 1px hairline at 30vh (raised horizon — more room for field) ──────

[col 1-3][col 4-6][col 7-9][col 10-12]
  TILE     TILE     TILE     TILE       (row 1)
[col 1-3][col 4-6][col 7-9][col 10-12]
  TILE     TILE     TILE     TILE       (row 2)
```

`Field` looks more "dashboard-y" *intentionally* — the AI is signaling "I see noise, I am not pretending to have a hero." The user reads the room as honesty, not failure.

T4 resolved: layout is chosen at the door, not while reading. Composition name appears in posture sentence (subtly: "One thesis stands alone today" / "Two theses, one challenger" / "Six theses forming"). The user learns to read the *opening line* as the room signature.

T2 partially resolved: "alive" = the AI re-chose the room since last visit. Static page, dynamic *room selection.*

---

## D5. Environmental design (depth, atmosphere, warmth)

Three static atmospheric layers. All static. All composition-time, not runtime.

**Layer 1 — Base canvas:** `#0A0908`. Warm-near-black. UX-12 lock.

**Layer 2 — Stage zone:** `#0D0B09` with 2.5% amber tint (UX-12 lock). Occupies cols 1–9 above 40vh in `Duet`, full width above 60vh in `Solo`, top 30vh in `Field`. **The stage zone shape changes per composition.** This is a major UX-13 contribution: the zone is no longer a fixed top stripe — it is a *room-shaped* lit area.

**Layer 3 — Thesis halo:** A radial gradient centered behind the hero. Color: `rgba(232, 184, 109, 0.04)` (warm amber, near-invisible). Radius: 800px (`Duet`), 1200px (`Solo`), N/A (`Field`). **Static.** This is the cinematic spotlight. It is the *only* "glow" in the system and it is so faint it reads as ambient warmth, not as a treatment on the hero. Compare to Apple's macOS Sequoia desktop wallpapers — the warm gradient under the menu bar is ~3% saturated and reads as "atmosphere," not "decoration."

**Depth via spatial separation, not blur:**
- 96px vertical gap between hero zone and subordinate zone (UX-12 spacing scale's largest value).
- 1px hairline at 40vh in `Duet` (was UX-12 lock; UX-13 *moves* it: 40vh `Duet`, 60vh `Solo`, 30vh `Field`).
- Negative well in cols 10–12 of hero zone is the *third dimension* — it is depth-by-absence.

**Warmth shift, STATIC, by composition (not by time of day, not by mood):**
- `Solo`: thesis halo 6% opacity → most "lit" room. Reads as confidence.
- `Duet`: thesis halo 4% opacity → balanced. Reads as deliberation.
- `Field`: no halo, stage zone tint reduced to 1.5% → coolest room. Reads as observational.

T5 resolved: cinematic = composition + spatial separation + serif typography + restrained warmth via halo. **Casino = motion + saturation + glow on demand.** We have none of the latter. The halo is so faint it *reads* atmospheric, not interactive.

T2 fully resolved: "alive" = (1) composition was chosen by AI, (2) atmospheric warmth follows that choice statically, (3) session-diff appears in posture. No animation.

---

## D6. Asymmetric layout mockups (ASCII, specific dimensions)

Already partially in D2/D4. Adding the **scroll-state mockups** (below 40vh in `Duet`):

```
═══════════════════════════════════════════════════════════
  Above 40vh (Hero Zone, stage-tinted #0D0B09)
═══════════════════════════════════════════════════════════
80│col 1 ────────── col 7              │32│col 8 ─ col 12│80
  │                                    │  │              │
  │   ┌──── halo radius 800px ────┐    │  │  Two theses, │
  │   │                           │    │  │  one         │
  │   │   ┌─ConvictionTile────┐   │    │  │  challenger. │
  │   │   │ NVDA · OPEN       │   │    │  │              │
  │   │   │ 5-row schema      │   │    │  │  Day 12      │
  │   │   │ 304×184           │   │    │  │  09:14 EDT   │
  │   │   └───────────────────┘   │    │  │              │
  │   │                  OPEN     │    │  │  Memory:     │
  │   │              (36pt serif) │    │  │  +0.3 since  │
  │   └───────────────────────────┘    │  │  yesterday   │
  │                                    │  │              │
═══════════════════════════════════════════════════════════
              ── 1px hairline at 40vh ──
═══════════════════════════════════════════════════════════
  Below 40vh (Subordinate Zone, base #0A0908, NO halo)
═══════════════════════════════════════════════════════════
  96px gap before first row
  
80│col 1-4   │32│col 5-8   │32│col 9-12  │80
  │┌────────┐│  │┌────────┐│  │┌────────┐│
  ││ AMD    ││  ││ TSM    ││  ││ ASML   ││
  ││ HOLD   ││  ││ HOLD   ││  ││ TRIM   ││
  ││ 304×184││  ││ 304×184││  ││ 304×184││
  │└────────┘│  │└────────┘│  │└────────┘│
═══════════════════════════════════════════════════════════
```

**Solo composition mockup:**

```
═══════════════════════════════════════════════════════════
  Above 60vh — full-width stage zone, halo at 1200px
═══════════════════════════════════════════════════════════
80│col 1 ─────────────────── col 9      │32│col 10-12│80
  │                                     │  │         │
  │   ┌──────── halo r=1200px ────┐     │  │ One     │
  │   │                           │     │  │ thesis  │
  │   │  ┌─ConvictionTile─────┐   │     │  │ stands  │
  │   │  │ scaled 1.5×        │   │     │  │ alone   │
  │   │  │ 456×276            │   │     │  │ today.  │
  │   │  │ NVDA · OPEN        │   │     │  │         │
  │   │  └────────────────────┘   │     │  │ Day 12  │
  │   │                  OPEN     │     │  │         │
  │   │             (48pt serif!) │     │  │         │
  │   └───────────────────────────┘     │  │         │
═══════════════════════════════════════════════════════════
                ── 1px hairline at 60vh ──
═══════════════════════════════════════════════════════════
  Below 60vh — almost empty
  
  Other 4 watch-list items show no thesis change today.
  (14pt, dim text, full-width, single line, no tiles)
═══════════════════════════════════════════════════════════
```

In `Solo`, the verb glyph escalates from 36pt to 48pt — the only place this scale appears. It is reserved for `Solo` mornings. The user learns: when the verb is huge, the AI is sure.

**Field composition mockup:** (See D4.) Symmetric grid, intentionally — symmetry signals *I have nothing to spotlight.*

---

## D7. Emotional UX map (user emotion at each surface)

| Surface | Composition | Emotion | Mechanism |
|---|---|---|---|
| First paint (0–500ms) | any | "Someone is here." | Posture sentence loads first, in serif, full-weight. |
| Hero zone, `Solo` | `Solo` | "Today matters." | One verb at 48pt + 1200px halo + 60vh of room. |
| Hero zone, `Duet` | `Duet` | "There's a call and a counter." | Asymmetric 7-col + 5-col with negative well. |
| Hero zone, `Field` | `Field` | "Lots brewing, nothing decided." | Symmetric grid + raised horizon. |
| Negative well | `Duet` | Calm pause. | 5-col emptiness with 11pt mono only. |
| Hairline horizon | all | "There's more, when you want it." | 1px line, no arrow, no chevron. |
| Subordinate zone | `Duet`/`Field` | Curiosity, not obligation. | 96px above-gap; cooler atmosphere (no halo). |
| Drawer open | any | Focused investigation. | UX-11 lock; modal sheet. |
| Drawer close | any | Returned to room. | Same composition still there, unchanged (T4). |

Compare to Arc Browser's "Boost" reveal: the page transforms when you "Boost" it, but the chrome stays still. That stillness is the calm. We do the same — drawer overlay, room beneath unchanged.

---

## D8. AI atmosphere rules (concrete techniques, anti-theater compliant)

Six techniques. All static. None violate the 58-item anti-pattern list.

1. **Composition-as-AI-voice.** The room name *is* the AI's read. `Solo` = "I see one." `Duet` = "I see two." `Field` = "I see many." The user feels the AI's perspective without any AI character or persona.

2. **Posture-sentence room signature.** First three words of the posture sentence carry the room ("One thesis stands…" / "Two theses, one…" / "Six theses forming…"). Same banned-token lint as UX-12.

3. **Session-diff line.** After ambient timestamp, optional 11pt mono line: `Since you left: NVDA conviction +0.3, AMD verb HOLD→TRIM`. Only appears if something changed. Static. No animation. This is the "AI memory" without any persona. Reference: Linear's "Updates since you were away" inbox state.

4. **Halo-as-confidence.** Halo opacity tracks composition (6% Solo, 4% Duet, 0% Field). The user reads "warm room = AI is sure" subliminally. Static.

5. **Negative well as "AI is thinking with you."** The 5-col empty space is where a human collaborator would have a notepad. Leaving it empty *invites* the user; filling it would *perform* for the user.

6. **Verb-glyph scale.** 36pt `Duet`, 48pt `Solo`, none on `Field`. The serif verb is the loudest typographic gesture in the system, and it's reserved for AI conviction.

**What we DO NOT do (anti-theater compliance check):** no orb, no chat dock, no suggested-question chips, no "Powered by AI", no typing animation, no persona, no first-person hero, no breathing/pulsing, no cursor lean-in, no depress-on-click, no biomorphic copy. All six techniques above are layout / typography / static color decisions.

---

## D9. First 5-second feeling analysis

**Second 0:** Page paints. Posture sentence renders first (it's the lightest weight; serif loads fast). User reads "Two theses, one challenger." User does not yet know what they mean — but the *cadence* of the sentence (subject-comma-clause) tells them an editor wrote this.

**Second 1:** Eye drops to hero zone. The thesis halo is so faint it is felt before seen. The verb glyph (`OPEN`, 36pt serif) lands. Mass.

**Second 2:** Eye reads the ConvictionTile schema rows. Tier dot, ticker, decision, invalidation, target. 5 rows. Familiar.

**Second 3:** Eye drifts to negative well. 11pt mono `Day 12 · 09:14 EDT`. Calm.

**Second 4:** Session-diff line: `Since you left: NVDA conviction +0.3`. *The AI noticed I left.*

**Second 5:** Eye finds the hairline horizon. There is more. Not now.

Target emotion at 5s: **"Someone arranged this for me today."** Not: "I should read these tiles."

Compare to Linear's first 5s on the Inbox: ~3s to read the count, ~2s to scan top item. Ours is heavier, more editorial. We are closer to a Sunday morning newspaper opening than a notification queue. That's the right reference for an investing OS — newspapers are habit-forming because they *changed since yesterday* and *the editor took a stance.*

---

## D10. Before/after (UX-12 vs UX-13)

| Aspect | UX-12 | UX-13 |
|---|---|---|
| Hero placement | 2-col span, centered | 7-col span, left-of-center, with 5-col negative well right |
| Layout choice | one fixed grid | three named compositions (`Solo / Duet / Field`), AI-chosen |
| Verb prominence | inside ConvictionTile only | 36pt serif glyph (Duet) / 48pt (Solo) outside tile |
| Atmospheric warmth | 2.5% amber stage tint, full-width top stripe | stage zone reshapes per composition; thesis halo behind hero |
| Horizon line | 1px at 40vh, fixed | 1px at 30vh / 40vh / 60vh per composition |
| Subordinate zone | tile grid | tile grid below horizon + 96px above-gap + cooler atmosphere |
| AI presence | 5 techniques (posture, page-state, serif, weight, timestamp) | 5 + composition-as-voice + session-diff + halo-as-confidence + verb-glyph-scale |
| First sentence | "Today's posture" (generic) | "Two theses, one challenger." (room-signature) |
| Negative space | uniform spacing | 5-col gravity well right of hero |
| Eye flow | predictable left-right scan | choreographed: posture → verb → tile → well → horizon |

The substrate is unchanged. The *room* is new.

---

## D11. Screen-by-screen emotional flow

**Today (default landing) → `Duet`:** "There's a call and a counter. The AI has a position. I want to know it."

**Today → `Solo` (rare, ~15% of sessions):** "Damn. This is a real day. The AI thinks one thing matters."

**Today → `Field` (~25% of sessions):** "Quiet day. The AI is honest about it."

**Holdings:** Inherits `Field`-style symmetric grid by default, because holdings are not theses. The grid here is *correct* — equal-treatment is what holdings deserve. **Important:** holdings page should *never* render in `Solo`/`Duet` — those are reserved for theses. This protects the language of the hero.

**Ideas:** Renders as a vertical column of `Field` tiles, 1-col-wide (304×184 stacked), max-width 720px, centered. Reads like a curated reading list — Perplexity's discover feed is the reference. Negative space on both sides is the message: "these are ideas, not actions."

**Working:** Renders as a system status sheet. NOT a hero composition. Uses symmetric mono-typography for telemetry. The room is intentionally workshop-feeling, not gallery-feeling.

**Drawer open (UX-11 lock):** Modal sheet over any composition. Room beneath does not reflow.

The cross-page rule: **only `Today` uses Solo/Duet/Field.** Other surfaces use their own grammar. This protects the hero language from inflation.

---

## D12. New visual language proposals

Three additions to the UX-12 token system. All composition-level, no new components.

1. **Composition tokens:** `room.solo`, `room.duet`, `room.field` — each defines hero col-span, hero scale, halo radius, halo opacity, horizon vh, posture-sentence prefix pattern, stage-zone shape.

2. **Negative-well token:** `well.cols = 3-5`, `well.contents = posture+pageState+timestamp+sessionDiff` — a named region, not a component.

3. **Verb-glyph treatment:** `verb.glyph.font = Source Serif 4`, `verb.glyph.size.duet = 36pt`, `verb.glyph.size.solo = 48pt`, `verb.glyph.weight = 400`, `verb.glyph.tracking = -0.02em`. This is the *only* element above 22pt in the system. It is reserved for AI conviction.

Plus one **anti-pattern addition** to the 58-item list: *"Halo opacity must never exceed 6%. Never animate halo opacity. Never state-map halo color."* Halo is atmosphere, not feedback.

---

## D13. Why current cockpit feels dead

UX-12 fixed substrate but kept four dead-room patterns:

1. **Symmetric hero placement.** The 2-col hero centered in the grid is still grid-shaped. Symmetry reads as "no one chose this." Every dashboard since 1998 has centered the hero. We need *off-center.*

2. **No negative-space allocation.** UX-12 spacing is generous in *gaps* but never *allocates* a region as empty. A 5-col empty well is a different beast from a 32px gap. Apple's keynote stage has *80% empty stage* — that's the difference between casino and cinema.

3. **No room signature.** The posture sentence is the same shape every day. The user cannot read the *room* — only the content. A room with no signature is a generic conference room.

4. **Single composition for all days.** A quiet day and a high-conviction day look the same. The page has no opinion about the day. The user has to extract the opinion from the tiles. That is the *dashboard mindset.*

These four patterns make the cockpit feel like inventory rather than briefing. The fix is not new components. It is **room language.**

---

## D14. What finally makes it feel alive

Five concrete moves that, taken together, cross the threshold:

1. **The room was chosen.** AI-selected `Solo / Duet / Field` at session-load. The shape of the page *is* the AI's read.

2. **The first three words name the room.** "One thesis stands…" / "Two theses, one…" / "Six theses forming…". The reader picks up the room from the cadence.

3. **The negative well is allocated, not residual.** Cols 8–12 in `Duet` are *given to* emptiness. This is the Apple keynote move. Emptiness on purpose ≠ emptiness by accident.

4. **The verb-glyph is the loudest typographic mark.** 36pt Source Serif 4 verb (`OPEN`, `HOLD`, `TRIM`, `EXIT`) outside the tile, in the lower-right of the hero span. The reader's eye finds it second, after the posture. This is the AI's verdict, in the editor's voice.

5. **Session-diff line, when relevant.** "Since you left: NVDA conviction +0.3." Static. Optional. Honest. Continuity without gamification.

Together these mean: when you open the page, **someone has been here.** The arrangement is evidence. That is what "living" means without animation.

T6 resolved: habit forms via *continuity* (session-diff, room re-selection), not via *retention mechanics* (no streaks, no countdowns, no "today's pick" framing).

---

## D15. ASCII mockups with asymmetric composition

**Final consolidated mockup, `Duet` composition, 1440×900 viewport:**

```
┌─────────────────────────────────────────────────────────────────────┐
│ 80px outer margin                                                   │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ col 1 ────────── col 7    32   col 8 ─── col 12             │    │
│  │ ▲ stage zone (#0D0B09 + 2.5% amber)                         │    │
│  │ │                                                           │    │
│  │ │  ╭ halo r=800px (rgba(232,184,109,0.04)) ╮                │    │
│  │ │  │                                       │                │    │
│  │ │  │   ┌ConvictionTile 304×184─────────┐   │  Two theses,   │    │
│  │ │  │   │ ● NVDA · OPEN                  │   │  one           │    │
│  │ │  │   │ tier dot · ticker · verb       │   │  challenger.   │    │
│  │ │  │   │ ─────────────────────────────  │   │                │    │
│  │ │  │   │ Bear: rev miss < $30B          │   │  ─────────     │    │
│  │ │  │   │ Bull: rev > $35B               │   │  Day 12        │    │
│  │ │  │   │ Invalidation: $850             │   │  09:14 EDT     │    │
│  │ │  │   │ Target: $1100                  │   │                │    │
│  │ │  │   └────────────────────────────────┘   │  ─────────     │    │
│  │ │  │                                        │  Since you     │    │
│  │ │  │                       ┌──────────┐     │  left: NVDA    │    │
│  │ │  │                       │   OPEN   │     │  conviction    │    │
│  │ │  │                       │ 36pt serif│    │  +0.3          │    │
│  │ │  │                       └──────────┘     │                │    │
│  │ │  ╰────────────────────────────────────╯   │                │    │
│  │ ▼                                                            │    │
│  ├──────────────── 1px hairline #1A1716 at 40vh ────────────────┤    │
│  │                                                              │    │
│  │            96px gap (UX-12 largest spacing)                  │    │
│  │                                                              │    │
│  │ col 1-4         32  col 5-8          32  col 9-12            │    │
│  │ ┌────────────┐     ┌────────────┐       ┌────────────┐       │    │
│  │ │● AMD       │     │● TSM       │       │● ASML      │       │    │
│  │ │ HOLD       │     │ HOLD       │       │ TRIM       │       │    │
│  │ │ 304×184    │     │ 304×184    │       │ 304×184    │       │    │
│  │ │ schema...  │     │ schema...  │       │ schema...  │       │    │
│  │ └────────────┘     └────────────┘       └────────────┘       │    │
│  │   (no halo, base canvas #0A0908, cooler atmosphere)          │    │
│  └─────────────────────────────────────────────────────────────┘    │
│ 80px outer margin                                                   │
└─────────────────────────────────────────────────────────────────────┘
```

**Key dimensions recap:**
- Outer margin: 80px
- Grid: 12-col, 32px gutter
- Hero span: cols 1–7 (~720px wide)
- Negative well: cols 8–12 (~520px wide)
- Hero tile: 304×184 (schema lock), placed top-left of span
- Verb glyph: 36pt Source Serif 4, lower-right of hero span
- Halo: radial, 800px radius, 4% amber opacity, behind hero
- Horizon: 1px hairline at 40vh
- Subordinate gap above: 96px
- Subordinate tiles: 304×184 each, in cols 1–4 / 5–8 / 9–12

This is the room. Three named versions. AI chooses. User walks in. Reads the room. Reads the verb. Drifts into the well. Crosses the horizon when ready.

That is the operating system, not the dashboard.
