# Creative Direction — Typographic Precision System

**Status**: accepted 2026-05-15
**Phase**: K (Creative Direction)
**Inherits**: all prior creative-direction artifacts

Prime optimization target: **reading stamina.** Not visual drama. Not editorial-theater. Not luxury-magazine cosplay. Every typographic decision below is justified by sustained calm cognition over a 4-12 minute reading session, not by how the surface looks in a static screenshot.

---

## I. The cognitive principle (load-bearing constitutional doctrine)

> **Type is the interface. Every decision is justified by reading stamina, not visual drama.**

This principle governs:

- Typography
- Spacing
- Composition
- Motion
- Interaction pacing
- Editorial copy rhythm

Reading stamina = the user's ability to read for 4-12 minutes without:

- Eye fatigue
- Loss of cadence
- Scan-recovery failure
- Cognitive effort spent on parsing typography rather than content

### The danger this artifact exists to prevent: "beautifully tiring"

A surface that screenshots well at 5 seconds but exhausts the eye at 5 minutes. Most premium editorial redesigns fall here. The phrase is locked as the named failure mode the system actively defends against.

### The single verification test

After any typographic decision, ask:

> *"Can a reader hold this surface for 8 minutes at normal reading distance without conscious effort to maintain focus?"*

If no, the decision is wrong regardless of aesthetics.

This test supersedes:

- "Is this beautiful?"
- "Is this on-trend?"
- "Is this editorial-grade?"
- "Does this look like Stratechery?"

Beauty is necessary but not sufficient. **Stamina is the constraint.**

### The inevitability principle

> **The system is strongest when it feels inevitable, not self-consciously designed.**

Typography that draws attention to itself violates stamina. Typography that disappears into reading is the goal. If a reader notices the typeface mid-paragraph, the type has failed — regardless of whether they noticed "positively" or "negatively."

---

## II. Why typography carries everything now

After chrome reduction (`CREATIVE_DIRECTION_CHROME.md`), type carries:

| function | how it carries |
|---|---|
| Hierarchy | Size + role + position, not weight |
| Navigation | Section titles set on page, not chrome tabs |
| Pacing | Vertical rhythm + measure (line length) |
| Emotion | Italic restraint + verdict scale + wash co-presence |
| Authority | Newsreader as institutional voice |
| Density | Tier 1/2/3 modulation |
| Calmness | Generous leading + restrained letter-spacing |

If type fails, the system fails. There is no fallback chrome.

---

## III. Font role mapping

Two typefaces. Strictly role-mapped. No overlap.

### Newsreader (display + italic body)

```
Family:      "Newsreader", "Source Serif Pro", "Charter", "Georgia", serif
Variable:    opsz (optical size), ital (italic)
Weights:     400 only (+ 400 italic)
Exception:   500 conditionally permitted on verdict — see §IV governance
```

**Allowed roles:**

1. Masthead title ("Today's Briefing")
2. Section titles ("Watching", "Today's strongest read", "Decisive", etc.)
3. Verdict typography ("Take the loss.", "Take the gain.")
4. Strategist sentence (italic body, inside fields)
5. Orientation line (italic, first visit)
6. Editorial transitions ("Three more we'd take alongside it.")
7. "Ask one thing back." prompt
8. Inline italic phrases (strategy bias, IV state, catalyst window)
9. Conviction signpost ("Today's strongest read")

**Forbidden roles for Newsreader:**

- Any numeric value (use Inter)
- Any UI affordance (buttons, links — use Inter)
- Any chrome (drawer headers, form labels — use Inter)
- Any captions / metadata (timestamps — use Inter)
- Any tabular data
- Any monospace context

### Inter (sans, all utility)

```
Family:   "Inter", "SF Pro Text", system-ui, sans-serif
Weights:  400, 500 only (no 600/700)
```

**Allowed roles:**

1. Masthead date + edition line
2. Symbol headers in fields (e.g., "QQQ")
3. Fit percentage values ("72%")
4. All numeric values (P&L, timestamps, edition numbers)
5. Section subtitles ("Setups expecting price to rise")
6. Captions, footnotes, footer attribution
7. Drawer chrome labels
8. Form input affordances
9. Text links (action affordances)

### No monospace by default

Bloomberg/terminal vocabulary. Monospace appears *only* inside the drawer when raw greeks/per-leg data demands aligned columns. Never on editorial body.

---

## IV. The weight ladder — locked

Four weights total. No others permitted.

| weight | font | usage |
|---|---|---|
| Newsreader 400 | All Newsreader roles except verdict | Masthead, section titles, strategist sentence, italic phrases |
| Newsreader 400 italic | All italic roles in Newsreader | Strategist sentence (default), orientation, transitions, signposts, ask-back prompt |
| Inter 400 | Body sans roles | Captions, footnotes, subtitles, secondary metadata |
| Inter 500 | Primary sans roles | Symbol headers, fit values, masthead date, P&L numbers |

### Newsreader 500 — emergency verdict exception

Permitted **only** on the verdict line when Newsreader 400 italic at 32-40px on the warm/cool wash reads thin. Conditional, single-purpose, never normalized.

**Governance rule (locked):**

> If Newsreader 500 verdict appears in more than ~5% of verdict moments measured across the rollout window, the system has drifted into aggression. Reset by tightening wash math or reducing verdict scale, not by accepting weight escalation as the new normal.

The exception is an **emergency optical stabilization tool**, not an emphasis mechanism.

No 600. No 700. No 800. **Bold sans is the dashboard signature.** Heavier weight creates visual aggression that breaks reading stamina.

---

## V. Optical size mapping (Newsreader)

Newsreader is a variable font with `opsz` axis. Misuse is the most common Newsreader mistake.

| role | size range | opsz value |
|---|---|---|
| Masthead title | clamp(36px, 5vw, 56px) | 72 (full display) |
| Section title | clamp(22px, 2.4vw, 32px) | 36 |
| Verdict | clamp(28px, 3.2vw, 40px) | 48 |
| Strategist sentence (Tier 1) | clamp(17px, 1.5vw, 19px) | 20 |
| Italic phrase (inline / bias / catalyst) | matches surrounding | 16-20 |
| Orientation line | clamp(15px, 1.3vw, 17px) | 18 |
| Editorial transitions | clamp(14px, 1.2vw, 16px) | 16 |
| Ask-back prompt | 14-15px fixed | 16 |
| Conviction signpost | 14-15px fixed | 16 |

Locked rule:

> **Newsreader at body scale (≤22px) uses text-optical-size (opsz 16-20). Newsreader at display scale (≥28px) uses display-optical-size (opsz 36-72).**

Mismatched opsz creates weight-anemia (body forms at display) or weight-aggression (display forms at body).

---

## VI. Inter size mapping

| role | size |
|---|---|
| Symbol header in field | 22px (fixed — symbols must scan consistently) |
| Fit value ("72%") | clamp(16px, 1.4vw, 18px) |
| P&L value | clamp(16px, 1.4vw, 18px) |
| Masthead date + edition | 13-14px |
| Caption / footnote | 12.5-13px |
| Section subtitle | clamp(13px, 1.1vw, 14px) |
| Action text link | 14-15px |
| Drawer label | 12px (uppercase, 0.04em tracking) |
| Footer attribution | 13px |

---

## VII. Line-height precision

Reading stamina depends more on line-height than on size. Tight lines fatigue; loose lines lose cadence.

| role | line-height |
|---|---|
| Masthead title | 1.05 (tight; display anchor) |
| Section title | 1.15 |
| Verdict | 1.1 (display weight; tight to land) |
| Strategist sentence (italic body) | **1.6 (load-bearing)** |
| Inline italic phrase | matches surrounding body |
| Orientation line | 1.5 |
| Editorial transitions | 1.5 |
| Ask-back prompt | 1.5 |
| Symbol header (Inter 500, 22px) | 1.2 |
| Fit value / P&L | 1.3 |
| Caption | 1.5 |
| Footer attribution | 1.5 |

### The 1.6 strategist body leading — load-bearing

Most reading-fatigue from "elegant editorial" products comes from line-height ≤1.4. The product errs toward looser leading to extend stamina.

> **Dark surfaces + serif italics + long-session reading require more breathing room than conventional editorial systems.**

Verification: a 5-line italic paragraph must read without the eye fighting to find the next line.

---

## VIII. Letter-spacing (tracking) precision

| role | tracking |
|---|---|
| Masthead title (Newsreader 36-56px) | -0.015em |
| Section title (Newsreader 22-32px) | -0.005em |
| Verdict (Newsreader 28-40px italic) | -0.01em |
| Strategist sentence (Newsreader italic body) | 0 (default — Newsreader's natural fit) |
| Inline italic phrase | 0 |
| Symbol header (Inter 500, 22px) | -0.005em |
| Fit value (Inter 500, 16-18px) | 0 |
| Masthead date (Inter, 13-14px) | 0.04em |
| Caption (Inter, 13px) | 0.01em |
| Section subtitle (Inter, 13-14px) | 0.02em |
| Drawer label (Inter 12px uppercase) | 0.04em |
| Footer attribution | 0.02em |

**Newsreader's italic body must not be tightened.** Tracking ≤-0.01em on italic body type causes character overlap at reading distance. The product accepts Newsreader's natural italic fit — that looseness is reading stamina.

---

## IX. Measure (line length) rules — load-bearing for stamina

The single most-tested variable for reading fatigue.

| role | measure (max-width in ch) |
|---|---|
| Strategist sentence (Tier 1) | 56ch |
| Strategist sentence (Tier 2) | 48ch |
| Strategist sentence (Tier 3) | inline, no measure limit |
| Orientation line | 60ch |
| Editorial transitions | 56ch |
| Verdict line | 32ch |
| Masthead title | no limit (always fits at any viewport) |
| Section title | 40ch (rarely approached) |
| Caption / footnote | 64ch |
| Drawer body content | 56ch |

**56ch maximum for body italic is the single most important reading-stamina constraint.** Wider causes line-return failure; narrower causes cadence-fragmentation. 56ch is editorial-optimal for serif italic body at 17-19px.

Verification: print the page at reading distance. Words per line on a typical strategist sentence should land in 9-13 word range.

---

## X. Vertical baseline grid

```
Baseline:  4px sub-grid, 8px primary grid
```

All vertical rhythm decisions snap to the 4px sub-grid. Major rhythm elements snap to 8px primary grid.

### Standard rhythm sequence

| gap | value |
|---|---|
| Masthead → hairline (optional) | 24px |
| Hairline → orientation | 96px |
| Orientation → first section | 144px |
| Section title → first paragraph | 32px |
| Inside a field (header → strategy → sentence → metric → ask) | 16/24/24/24/32 |
| Field → next field | 80px |
| Section → next section | 144px |
| Tier 2 setup → Tier 2 setup | 56px |
| Tier 3 setup → Tier 3 setup | 40px |
| Last field → footer attribution | 144px |

### Responsive rhythm

| viewport | scaling |
|---|---|
| ≥1024px | Values as specified |
| 768-1023px | Reduce 144→112, 96→80, 80→64; keep 32/24/16 |
| <768px | Reduce 144→96, 96→64, 80→56, 56→40; keep 32→24, 24→16 |

Reduction preserves *ratio* of rhythm gaps.

---

## XI. Responsive type scaling — clamp formulas (locked)

```css
/* ==== Newsreader ==== */
--type-masthead-title:    clamp(36px, 5vw, 56px);
--type-section-title:     clamp(22px, 2.4vw, 32px);
--type-verdict:           clamp(28px, 3.2vw, 40px);
--type-strategist-body:   clamp(17px, 1.5vw, 19px);
--type-orientation:       clamp(15px, 1.3vw, 17px);
--type-transition:        clamp(14px, 1.2vw, 16px);
--type-italic-phrase:     inherit;  /* matches surrounding body */
--type-ask-back:          14px;     /* fixed */
--type-signpost:          14px;     /* fixed */

/* ==== Inter ==== */
--type-symbol-header:     22px;     /* fixed — scan consistency */
--type-fit-value:         clamp(16px, 1.4vw, 18px);
--type-pnl-value:         clamp(16px, 1.4vw, 18px);
--type-masthead-date:     14px;     /* fixed */
--type-caption:           13px;     /* fixed */
--type-section-subtitle:  clamp(13px, 1.1vw, 14px);
--type-action-link:       14px;     /* fixed */
--type-drawer-label:      12px;     /* fixed */
--type-footer-attr:       13px;     /* fixed */
```

**Fixed values are deliberate.** Some roles must not scale — symbol headers, captions, action affordances must be predictable at every width. Scaling them breaks scan-recovery.

---

## XII. Optical alignment — italic-to-upright

1. Italic phrase inside a sentence: no adjustment.
2. Italic block-quote-style line followed by upright body: indent italic line +6px to compensate for the lean.
3. Italic ask-back prompt after upright metric: italic prompt aligns to text rail without shift.
4. Verdict italic followed by upright reason body: align both to text rail; rhythm gap (32px) absorbs optical drift.

---

## XIII. Punctuation conventions (locked)

| convention | rule |
|---|---|
| Sentence-end period | always; no exceptions |
| Em-dash `—` | sparingly for inline elaboration; max 1 per paragraph |
| En-dash `–` | ranges only ("3-5 days") |
| Hyphen `-` | compounds only ("ask-back") |
| Ellipsis `…` | single character; only for genuine elision |
| Exclamation mark | forbidden |
| Question mark | only in user-facing input prompts |
| Quote marks | curly `" "`; straight forbidden |
| Apostrophe | curly `'`; straight forbidden |
| Numbers in body prose | spelled out below ten; digits at ten and above; financial values always digits |
| Currency | `$` symbol; never "USD" or "dollars" |
| Percentages | `%` symbol; no spaces ("72%") |

---

## XIV. Italic phrase rules

| use italic for | do NOT use italic for |
|---|---|
| Strategist sentence (Newsreader italic body) | Visual decoration |
| Inline bias / IV / catalyst phrases | Emphasis-only emphasis |
| Editorial transitions | Tooltip text |
| Orientation line | Section subtitles |
| Ask-back prompt | Captions |
| Conviction signpost | UI labels |

**Italic frequency cap (locked):** at most ~40% of a typical viewport should be italic. Beyond, italic loses inflection meaning and reads as decorative monotone.

---

## XV. Number formatting

| value type | format |
|---|---|
| Dollar amount | `$1,840` (no decimals when integer); `$1,840.50` (two decimals when fractional) |
| Negative dollar | `−$610` (true minus `−`) |
| Percentage | `72%`; `72.4%` (one decimal max) |
| Ratio | `38% of max` |
| Time | `9:32 AM ET` (with timezone always) |
| Date | `Friday, May 15` |
| Edition number | `#142` |
| Days | `23 days out` |
| Numbers below ten | spelled out ("forty-one"); digits at ten and above |

**No flourish formatting:**

- No `+` prefix on positive returns
- No "k"/"m"/"bn" abbreviations in editorial body
- No scientific notation
- Proportional-nums in italic body; tabular-nums only in P&L columns when drawer-tabulated

---

## XVI. Forbidden typographic patterns (the ornamentation veto)

| ❌ pattern | why forbidden |
|---|---|
| Drop caps | Magazine cliché |
| All-caps headlines | Visual aggression; not scannable |
| Smallcaps everywhere | Magazine-cosplay; retired with "THE DESK" |
| Swash characters / decorative ligatures | Ornamental sophistication |
| Inline italic-bold | Double-emphasis = no emphasis |
| Centered body type | Line-return failure |
| Justified body type | Word-spacing variability fatigues the eye |
| Underlined body type | Confused with action affordance |
| Strikethrough in body prose | Visual noise |
| Hanging indents on body | Magazine cosplay |
| Multi-column body type | Reading-stamina hostile |
| Text-shadow on body | Breaks paper-on-dark material identity |
| Letter-spacing on italic body (≥0.01em) | Breaks Newsreader's natural italic fit |
| Letter-spacing on body sans (≥0.02em) | Reads as branding |
| Pull-quotes set in oversized italic | Magazine cosplay |
| Decorative em-dashes | Visual noise |
| Bullet-list with custom-glyph bullets | Chrome leak |
| Numbered lists in editorial body | Engine-output reading; drawer-only |

---

## XVII. Reading-stamina verification tests

1. **8-minute hold test**: full briefing read for 8 continuous minutes; no eye strain reported.
2. **Line-return test**: eye finds next line's start without conscious search.
3. **Cadence test**: read Tier 1 setup aloud — natural sentence rhythm aligns to line breaks.
4. **Scan-recovery test**: user reads paragraph, looks away, returns. Eye finds where it left off within ~2 seconds.
5. **5-second / 5-minute parity test**: surface that screenshots well at 5 seconds must also feel good at 5 minutes.
6. **Mobile stamina test**: same tests at 360-400px viewport.

---

## XVIII. Microscopic precision territory

Acknowledged: tiny deviations in measure, line-height, optical size, italic density, spacing rhythm, or responsive scaling can materially damage the emotional effect.

That sensitivity is the price of low-chrome typography-led design.

Implementation discipline: every value in this artifact is **a precise commitment**, not a rough guide. Drift of ≥1px in measure, ≥0.05 in line-height, ≥0.005em in tracking is enough to compromise stamina.

---

## XIX. What this artifact commits to NOT being

- An editorial-theater system (magazine cosplay)
- A luxury-magazine cosplay (drop caps, gold accents, ornamental serifs)
- A literary-performance UI (typography as spectacle)
- A "beautifully tiring" system
- A typeface showcase (Newsreader used because stamina-grade, not prestige-grade)

## XX. What this artifact commits to being

- A reading-stamina system first, aesthetic system second
- A system where every typographic decision has stamina justification
- A system where Newsreader and Inter cooperate, strict role separation
- A system that holds up at 8-minute reading sessions
- A system that scales gracefully 360-1920px without scan-recovery failure
- A system that feels inevitable, not self-consciously designed

---

## XXI. Complete token table — single source of truth

```css
/* ==== Font families ==== */
--font-serif:  "Newsreader", "Source Serif Pro", "Charter", "Georgia", serif;
--font-sans:   "Inter", "SF Pro Text", system-ui, sans-serif;

/* ==== Weight ladder (locked) ==== */
--weight-serif:           400;
--weight-serif-verdict:   500;  /* emergency exception only — ≤5% governance */
--weight-sans-body:       400;
--weight-sans-primary:    500;

/* ==== Line-height tokens ==== */
--lh-display-tight:       1.05;
--lh-display:             1.1;
--lh-section:             1.15;
--lh-symbol:              1.2;
--lh-numeric:             1.3;
--lh-body:                1.5;
--lh-strategist:          1.6;   /* load-bearing */

/* ==== Tracking tokens ==== */
--track-masthead:         -0.015em;
--track-verdict:          -0.01em;
--track-section:          -0.005em;
--track-symbol:           -0.005em;
--track-body:             0;
--track-meta:             0.02em;
--track-date:             0.04em;

/* ==== Measure tokens ==== */
--measure-tier1:          56ch;
--measure-tier2:          48ch;
--measure-orientation:    60ch;
--measure-transition:     56ch;
--measure-verdict:        32ch;
--measure-drawer:         56ch;
--measure-caption:        64ch;
```

---

## Linked artifacts

- `CREATIVE_DIRECTION_SPINE.md`
- `CREATIVE_DIRECTION_VOICE.md`
- `CREATIVE_DIRECTION_CHROME.md`
- `CREATIVE_DIRECTION_STUDIES.md`
- `CREATIVE_DIRECTION_COLOR_MATERIAL.md`
- `CREATIVE_DIRECTION_COMPOSITION.md` *(next artifact — scan-recovery elevated to core principle)*
