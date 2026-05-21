# Creative Direction — Field vs Structure Studies

**Status**: accepted 2026-05-15
**Phase**: K (Creative Direction)
**Inherits**: all prior creative-direction artifacts

Five composition studies. Three surfaces. Each contains an ASCII wireframe, an invisible-structure overlay (alignment rails, luminance zones, rhythm), and the anti-emptiness mechanic.

These studies are wireframe-grade. Pixel proportions illustrative. Intent: validate **the grammar** before implementation.

---

## Structural grammar key (reusable across all studies)

Five tools carry composition without chrome:

| tool | what it is | how it reads |
|---|---|---|
| Rail | Vertical alignment anchor. Every editorial element snaps to one of 2-3 rails per surface. Invisible. | Eye learns the rail subconsciously after 1 visit. |
| Zone | Horizontal luminance shift on page background, 1-3% above/below baseline. No border defines the zone. | Eye reads zone boundaries as breathing room shifts. |
| Rhythm | Vertical whitespace as a rule-governed sequence (e.g., 32-32-96-32-32-96), not random. | Page reads as composed. |
| Italic phrase | Inline editorial inflection replacing every chip/pill. Newsreader italic, body weight. | Reader registers emphasis as voice. |
| Hairline | 1px rule, `--hairline`, ≤2 per surface. Reserved for structural breaks. | Earned chrome as punctuation. |

---

## Rarity rules (locked)

### Wash rarity rule

The wash is the rarest material moment. Maximum three instances per visit.

| moment | wash | location |
|---|---|---|
| Today's strongest read | warm | Today only |
| Decisive loss position | cool | Holdings only, `stop_loss` |
| Decisive gain position | warm | Holdings only, `take_profit` |

Forbidden:

- No wash on any Opportunities lane
- No wash on any setup that is not Today's #1
- No wash on Research / Approaches / Learn / Journal
- No wash on `hold` / `expiring` / `roll` / `catalyst_caution` guidance
- No wash on drawer content

### Ask-back rarity rule

The "Ask one thing back" line. Second-rarest typographic moment.

Appears on:

- Tier 1 (lead) setup in each lane
- Today's strongest read
- Decisive Holdings positions (`stop_loss`, `take_profit`)
- Per-symbol Research deep page (once, at end)
- Per-approach deep page (once, at end)

Does not appear on:

- Tier 2/3 setups
- `hold` / `expiring` / `roll` positions
- Journal entries
- Learn pages
- Empty states

**Viewport rule**: never more than one ask-back inside the same visual viewport.

### Transition language anti-template rule

Editorial transitions ("Three more we'd take alongside it.") must NEVER become formulaic. Required variability: phrasing across lanes/days, contextual tone, occasional omission, asymmetric structure.

---

## STUDY 1 — Today, quiet day

The hardest case. Empty-day Today must read calm-with-authority, not "broken."

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│   Today's Briefing                                          [serif] │
│   Friday, May 15 · Edition #142                              [sans] │
│                                                                     │
│   ─────────────────────────────────────────────────                 │  ← optional hairline
│                                                                     │
│                                                                     │
│                                                                     │
│   We use Today to summarize what actually deserves                  │  ← orientation, italic
│   attention right now.                                     [italic] │
│                                                                     │
│                                                                     │
│                                                                     │
│                                                                     │
│   Watching                                                  [serif] │  ← section title
│                                                                     │
│   We're watching twenty-five setups across five                     │  ← editorial body
│   underlyings. Premium environment is still loading.                │
│                                                                     │
│                                            As of 9:32 AM ET [sans]  │
│                                                                     │
│                                                                     │
│                                                                     │
│                                                                     │
│                                                                     │
│   Today's strongest read                                   [italic] │  ← conviction signpost
│                                                                     │
│ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ │  ← warm wash begins
│                                                                     │
│   QQQ                                                       [sans]  │
│   long call · bullish                                      [italic] │
│                                                                     │
│   The call premium is cheap relative to the last six                │
│   weeks, and the catalyst sits inside our typical hold              │
│   window.                                                  [italic] │
│                                                                     │
│   72% fit with today's market                              [sans]   │
│                                                                     │
│   Ask one thing back.                                      [italic] │
│                                                                     │
│ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ │  ← wash dissolves
│                                                                     │
│                                                                     │
│                                                                     │
│                                                                     │
│   Two more setups worth a look                              [serif] │
│                                                                     │
│   SPY                                                       [sans]  │
│   long put · bearish                                       [italic] │
│   Today's tape shows pressure into the close;                       │
│   this is our hedge read.                                  [italic] │
│   71% fit                                                  [sans]   │
│                                                                     │
│   IWM                                                       [sans]  │
│   long call · bullish                                      [italic] │
│   Small-caps lead the next leg; this captures                       │
│   the breakout cleanly.                                    [italic] │
│   71% fit                                                  [sans]   │
│                                                                     │
│                                                                     │
│                                                                     │
│                                                                     │
│   All numbers shown are paper-only, as of 9:32 AM ET.      [sans]   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Invisible structure — Study 1

Rails:

- Primary text rail — left page padding (clamp 20-64px). Every editorial element snaps here.
- Right text-end rail — right page padding (clamp 20-40px). Timestamps, metric values, footer attribution.
- No third rail. Composition lives on 2 rails.

Zones:

- Page baseline: `--surface-base` (`#0F0D0A`)
- Conviction wash zone: warm gradient over "Today's strongest read" field. Tapers across right ~30% of measure — no hard edge.
- Footer zone: optional -1% luminance shift in bottom ~80px

Rhythm:

- Masthead → optional hairline: 24px
- Hairline → orientation: 96px
- Orientation → first section: 144px
- Section title → first paragraph: 32px
- Body paragraph → timestamp: 56px
- Section → next section: 144px
- Inside a field (header → strategy → sentence → metric → ask): 16-24-24-24-32
- Field → next field: 80px
- Last field → footer: 144px

Anti-emptiness mechanics:

1. Italic orientation line introduces voice immediately on first visit
2. Conviction wash gives the eye a focal anchor without a border
3. Rhythm sequence (144 → 32 → 56 → 144) reads as publication section breaks
4. Footer attribution closes the page

---

## STUDY 2 — Today, high-conviction day

Shows how the conviction wash + section progression scale when the day has more to say. Introduces the **two density tiers** mechanic.

```
┌─────────────────────────────────────────────────────────────────────┐
│   Today's Briefing                                          [serif] │
│   Tuesday, May 19 · Edition #146                             [sans] │
│   ─────────────────────────────────────────────────                 │
│                                                                     │
│   Watching                                                  [serif] │
│   We're watching forty-one setups across nine                       │
│   underlyings. Premium is rich; we'd lean toward                    │
│   selling rather than buying convexity today.              [italic] │  ← editorial inflection
│                                            As of 9:32 AM ET [sans]  │
│                                                                     │
│   Today's strongest read                                   [italic] │
│ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ │
│   AAPL                                                      [sans]  │
│   iron condor · neutral / income                           [italic] │
│   With premium this rich and earnings five weeks out,               │
│   we'd collect time decay through expiry. This is the               │
│   strongest setup we've seen this week.                    [italic] │
│   81% fit with today's market                              [sans]   │
│   Ask one thing back.                                      [italic] │
│ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ │
│                                                                     │
│   Five more setups worth a look                             [serif] │
│   QQQ      long call · bullish                                      │  ← Tier 2 — compact
│   We'd capture the next leg up through May expiry.        [italic] │
│   76% fit                                                  [sans]   │
│                                                                     │
│   SPY      iron butterfly · neutral                                 │
│   Premium environment supports this; range is narrow.     [italic] │
│   74% fit                                                  [sans]   │
│                                                                     │
│   [etc. for GLD, IWM, TLT — all Tier 2 compact]                    │
│                                                                     │
│   All numbers shown are paper-only, as of 9:32 AM ET.      [sans]   │
└─────────────────────────────────────────────────────────────────────┘
```

### Density tiers (key insight)

| tier | composition | role |
|---|---|---|
| Tier 1 (conviction field) | Spacious, wash-anchored, each line own row | Attention is held |
| Tier 2 (secondary setups) | Denser, multi-element rows, less whitespace per setup | Attention scans |

Density variation IS the anti-emptiness tool. Uniform Tier 1 would feel sparse. Tier 2 returns content gravity without returning chrome.

Tier 2 rhythm: 56px between setups (tighter than Tier 1's field-to-field 80px).

---

## STUDY 3 — Opportunities lane (REVISED with 3-tier modulation)

Original concern: single-tier lanes read repetitive. Revised: three-tier hierarchy + editorial transitions resolve repetition.

```
┌─────────────────────────────────────────────────────────────────────┐
│   Bullish                                                   [serif] │
│   Setups expecting price to rise                            [sans]  │
│                                                                     │
│   QQQ                                                       [sans]  │
│   long call · bullish                                      [italic] │
│   We'd capture the next leg up through May expiry.                  │
│   The call premium is cheap relative to the last six                │
│   weeks, and breadth is broadening as small-caps                    │
│   catch up. We'd structure the entry inside the May                 │
│   expiry window to keep theta contained.                   [italic] │  ← Tier 1 — full editorial
│   76% fit with today's market                              [sans]   │
│   Ask one thing back.                                      [italic] │  ← only ask-back in lane
│                                                                     │
│   Three more we'd take alongside it.                       [italic] │  ← editorial transition
│                                                                     │
│   IWM    long call                                          [sans]  │
│   71% fit                                                  [sans]   │
│   Small-caps converging with breadth; the same                      │  ← Tier 2 — compact
│   theme as QQQ at a different beta.                        [italic] │
│                                                                     │
│   AAPL   call debit spread                                  [sans]  │
│   68% fit                                                  [sans]   │
│   Defined-risk version, earnings five weeks out.           [italic] │
│                                                                     │
│   SOXL   long call                                          [sans]  │
│   67% fit                                                  [sans]   │
│   Semis showing structural momentum into the next                   │
│   FOMC.                                                    [italic] │
│                                                                     │
│   And two further down our list, lower conviction.         [italic] │  ← second transition
│                                                                     │
│   NVDA   diagonal call spread       64% fit                         │  ← Tier 3 — single-line
│   Compressed setup; the better expression of this                   │
│   theme is QQQ.                                            [italic] │
│                                                                     │
│   TSLA   long call                  62% fit                         │
│   Speculative; we wouldn't size into this alone.           [italic] │
└─────────────────────────────────────────────────────────────────────┘
```

### Three tiers inside the lane

| tier | setups | composition | ask-back |
|---|---|---|---|
| Tier 1 | 1 (lead) | Full prose, ~5 lines italic body, spacious rhythm | yes |
| Tier 2 | 2-4 | Symbol/strategy/fit inline, 1-2 line sentence | no |
| Tier 3 | 0-3 | Symbol/strategy/fit on one row + 1-line caveat | no |

Two editorial transitions connect tiers. Not buttons. Not section titles. Inline italic continuation prose. Subject to anti-template rule.

---

## STUDY 4 — Holdings, single position (stop-loss)

The hardest emotional case. Position broken; guidance decisive. Communicates urgency through type + voice, not alarm chrome.

```
┌─────────────────────────────────────────────────────────────────────┐
│   Holdings                                                  [serif] │
│   One position open.                                        [sans]  │
│                                                                     │
│   Decisive                                                  [serif] │
│                                                                     │
│   AMZN                                                      [sans]  │
│   bull call spread · bullish                               [italic] │
│ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ │  ← cool restraint wash
│   Take the loss.                                            [serif] │  ← verdict typography
│   The thesis is materially impaired. Unrealized P&L         [italic] │
│   is down the full max-loss; theta and IV are no                    │
│   longer favorable. Close to preserve remaining                     │
│   capital for setups we believe in.                                 │
│   Awaiting quote refresh                                   [sans]   │  ← honest waiting state
│   Ask one thing back.                                      [italic] │
│ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ │
│                                                                     │
│   Three more guidance groups are quiet today.              [italic] │  ← group overflow
│                                                                     │
│   All numbers shown are paper-only, as of 9:32 AM ET.      [sans]   │
└─────────────────────────────────────────────────────────────────────┘
```

### Verdict-as-typography (key move)

"Take the loss." set in Newsreader at editorial scale (the same scale as a section title). Not a guidance pill. **The verdict IS the typography.** Chrome-free replacement for red guidance pill.

Rhythm contrast: 96/64 above breathes; 32-32-24 around verdict pulls tight. Contrast is the emotional pacing.

---

## STUDY 5 — Holdings, multiple positions

How guidance groups compose when multiple positions occupy multiple buckets.

```
┌─────────────────────────────────────────────────────────────────────┐
│   Holdings                                                  [serif] │
│   Four positions open.                                      [sans]  │
│                                                                     │
│   Decisive                                                  [serif] │
│                                                                     │
│   AMZN  ·  bull call spread                                         │
│ ~ cool wash ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ │
│   Take the loss. Thesis is broken.                          [serif] │
│   Awaiting quote refresh                                   [sans]   │
│   Ask one thing back.                                      [italic] │
│ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ │
│                                                                     │
│   NVDA  ·  long call                                                │
│ ~ warm wash ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ │
│   Take the gain.                                            [serif] │
│   We're at our target; theta accelerates against us                 │
│   from here.                                               [italic] │
│   +$1,840 unrealized · 71% of max                          [sans]   │
│   Ask one thing back.                                      [italic] │
│ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ │
│                                                                     │
│   Time-sensitive                                            [serif] │
│   SPY  ·  iron condor                                               │
│   Expiring in three days. We'd close into the gain                  │
│   rather than ride into pin risk.                          [italic] │
│   +$420 unrealized · 38% of max                            [sans]   │
│                                                                     │
│   Holding                                                   [serif] │
│   GLD  ·  long put                                                  │
│   Thesis intact; theta favorable through next Friday.     [italic] │
│   +$180 unrealized · 14% of max                            [sans]   │
│                                                                     │
│   One guidance group is quiet today.                       [italic] │
│                                                                     │
│   All numbers shown are paper-only, as of 9:32 AM ET.      [sans]   │
└─────────────────────────────────────────────────────────────────────┘
```

### Two wash temperatures coexist

- Cool wash on `stop_loss` — sobering
- Warm wash on `take_profit` — affirming
- Both at ~3% saturation
- Temperature alone carries emotional polarity
- Verdict typography carries decision weight

The wash boundary brackets the entire decisive position field (header + verdict + reason + metric + ask) so the wash reads as material containment without visible edge.

---

## Cross-study observations — what makes these surfaces work without chrome

| mechanic | how it carries the surface |
|---|---|
| Typographic verdict | Important moments set in editorial-scale Newsreader. Type IS the visual weight cards used to provide. |
| Wash temperatures | One emotional anchor per page as background luminance shift, never as stripe/border. Material without chrome. |
| Italic inline phrases | Every chip becomes Newsreader italic phrase. Strategy bias, IV state, catalyst window — voice, not UI. |
| Density tiers | Tier 1 spacious; Tier 2 denser scannable; Tier 3 compressed. Variation prevents flatness. |
| Architectural rhythm | Vertical gaps follow numeric sequence (32 / 64 / 80 / 96 / 144). Eye learns rhythm subconsciously. |
| Rails | 1-2 vertical alignment anchors per surface. Everything snaps. |
| Hairlines as punctuation | One or two horizontal rules per surface as publication punctuation. Never containment. |
| Earned signposts | Section titles ("Watching", "Today's strongest read") do the work eyebrows + chips used to do. |
| Footer attribution | Single page-bottom line closes each surface. Pages have a bottom. |

## What's deliberately NOT in these studies

- No chips of any kind
- No cards with visible borders/fills
- No gradient backgrounds on banners or heroes
- No "AI ✦" / "Powered by" marks
- No eyebrow rows
- No guidance pills
- No action pill rows with chrome
- No "Compare" / "Watchlist" / "Add to" affordances
- No nav chrome inside editorial body
- No infinite-scroll signals — pages have explicit bottoms

## Risks flagged for downstream artifacts

1. **Wash math is highest-failure-risk variable** — defined precisely in `CREATIVE_DIRECTION_COLOR_MATERIAL.md`
2. **Verdict typography on dark depends on Newsreader weight** — addressed in `CREATIVE_DIRECTION_TYPOGRAPHY.md`
3. **Rhythm sequence must hold across viewport sizes** — addressed in Composition artifact (deferred)
4. **Loss of at-a-glance scanning** — deliberate trade; drawer carries chip-grade scan affordances when invoked

## Linked artifacts

- `CREATIVE_DIRECTION_SPINE.md`
- `CREATIVE_DIRECTION_VOICE.md`
- `CREATIVE_DIRECTION_CHROME.md`
- `CREATIVE_DIRECTION_COLOR_MATERIAL.md`
