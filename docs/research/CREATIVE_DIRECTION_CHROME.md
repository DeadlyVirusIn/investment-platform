# Creative Direction — Chrome + Density Philosophy

**Status**: accepted 2026-05-15 (with critical nuance — see §III)
**Phase**: K (Creative Direction)
**Inherits**: `CREATIVE_DIRECTION_SPINE.md`, `CREATIVE_DIRECTION_VOICE.md`

The operational artifact. Every subsequent artifact and every implementation PR references this as ground truth.

---

## I. The single principle

> **Chrome is the dashboard signature. Editorial products earn authority through absence, not addition.**

Every container, border, pill, fill, shadow, and radius pulls the reading back toward "dashboard." The Phase J ceiling exists because chrome ratio was too high.

**Chrome ratio target**: ≤25% of visible UI elements should have containment (border / fill / radius). The remaining 75-85% sit directly on the page as type-led editorial content.

## II. The density commitment

> **Sparse on the surface; dense inside earned moments.**

| zone | density target |
|---|---|
| Page architecture | Very sparse — wide gutters, contained measure, minimal chrome |
| Editorial body | Medium-dense — typographic density, not chromed |
| Earned dense moments (drawer detail, per-leg table) | Dense but contained — lives inside drawer or "Show working" expansion |
| Chrome ratio | ≤25% of visible UI elements |

## III. Critical nuance — "calm editorial authority," not minimalism

The chrome reduction is **aggressive philosophically** but must **never collapse into raw minimalism**.

Removed: visible chrome (chips, borders, gradients, pills, stripes).

**Retained: invisible structure.**

- Ultra-low-contrast grouping planes
- Compositional rails
- Faint sectional anchoring (luminance zones)
- Quiet spatial containment
- Alignment systems
- Editorial rhythm scaffolding

The danger overcorrected into: *"empty dark page with floating text."*

The target reads instead: **"architectural structure without visible chrome."**

The system carries authority through:

- Typographic precision
- Architectural whitespace rhythm
- Luminance variation (washes, zones)
- Alignment discipline (rails)
- Inline italic phrases (replacing chips)
- Hairlines used as publication punctuation, not containment

See `CREATIVE_DIRECTION_STUDIES.md` for concrete demonstrations.

## IV. Chrome rules — what earns chrome, what doesn't

### Earns chrome (allowed)

1. **The drawer** — a separate plane. Chrome required to communicate "this is a working surface, not the editorial page."
2. **The masthead hairline** — *one* horizontal 1px rule under the masthead, if needed. Type-led; rule optional.
3. **Tabular numeric blocks** — raw data needs visible alignment (per-leg greeks table inside drawer). Drawer-only.
4. **Action affordances on hover** — buttons that *do something destructive* (rare in this read-only product). Chrome appears on hover/focus only; never default rest state.
5. **Forms** — text inputs need chrome to communicate edit affordance. (The "ask back" input is the main case.)

### Forbidden chrome (no border / fill / radius / shadow on editorial body)

1. Section banners — gradient backgrounds removed entirely
2. Hero pulse — no gradient, no border
3. Editorial cards (Opportunity, Position, Spotlight) — see §VII (field, not card)
4. Bias chips, catalyst chips, IV chips, premium-tier chips, conviction chips, shadow watermarks, live-state chip — all become inline typographic marks; see §VI
5. Eyebrow rows on every surface header ("Today · AI strategist") — removed
6. Orientation card — becomes an inline italic line; see §X
7. Empty-state dashed-border blocks — replaced with single italic sentence on page
8. Lane/group headers — already chrome-free; keep so
9. Action pill rows by default — pills earn chrome on hover only
10. Live-state chip — migrates to single-line footer attribution

## V. Border / fill / radius / shadow policies

### Border policy

Borders allowed:

- Drawer outer edge (single 1px)
- Drawer internal section separators (single 1px)
- Masthead hairline (optional 1px)
- Tabular blocks inside drawer

Borders forbidden everywhere else.

Replacements for card borders:

- Increased architectural whitespace
- Subtle background luminance shift (rare — ~1 instance per page max)
- Single hairline at section start, not 4-sided enclosure

### Fill policy

Fills allowed:

- Page background (`--surface-base`)
- Drawer (`--surface-drawer`)
- Hover state for action affordances (subtle, single-frame appearance)
- Conviction wash / restraint washes (≤3 instances per visit — see Color artifact)

Fills forbidden:

- Card backgrounds
- Section gradient backgrounds
- Hero pulse gradient
- Banner gradients
- Orientation card gradient
- Pill fills

### Radius policy — three values only

| value | usage |
|---|---|
| `0px` | Page background, hairlines, type, marks (default) |
| `8px` | Inputs, action affordances on hover, small inline chrome moments |
| `12px` | Drawer outer + masthead-area treatments + conviction wash bounding (optical only — wash has no visible edge) |

Forbidden: 6px, 10px, 14px, 16px, 18px radius values. The current 7-value spread is itself a chrome leak.

### Shadow policy

Allowed:

- Drawer (single elevation shadow — see Color artifact)
- Hover lift inside drawer only

Forbidden everywhere on editorial body. Depth comes from typography weight + negative space + luminance washes, not z-axis elevation.

## VI. Pills + chips migration table

| current chip | reduction |
|---|---|
| Bias chip (BULLISH, BEARISH, NEUTRAL) | Removed. Bias communicated by strategy name + editorial sentence. Where explicit, inline italic mark: *long call · bullish* |
| Catalyst chip (NFP · 23d) | Inline italic phrase within sentence: "...inside the NFP window (23 days out)." |
| Guidance pill (Take loss, Hold, Roll) | Typographic mark — italic smallcaps adjacent to position header, no fill, no border, color shifts by tone |
| Action pills (Explain, Open in Research, Paper trade) | Text links by default. No border, fill, radius. Underline on hover. Chrome only on focus (accessibility). |
| IV pill (cheap/average/elevated/rich) | Inline editorial phrase. "Premium is rich." Not a chip. |
| Premium tier chip | Merged into IV phrase. |
| Conviction chip / score chip | Removed. Position on page + single non-chip emphasis carries it. |
| Shadow watermark pill | Removed from card-level. Migrates to single page-footer attribution. |
| Live-state chip (Shadow only, read-only) | Removed from every surface header. Single page-footer line. |
| Lane name chip (Bullish, Bearish, etc) | Section header in italic Newsreader; no chrome. |

Net effect: average Opportunity card today renders 6-8 chips. Post-policy: 0 chips. Information identical; chrome eliminated.

## VII. The "field, not card" principle

> **Default unit of editorial content is a *field*, not a *card*.**

| concept | definition |
|---|---|
| Card | Bounded rectangle. Border, fill, radius, padding. Communicates *thing*. |
| Field | Typographic block set directly on the page. Whitespace boundaries only. Communicates *paragraph*. |

A field has:

- A title (typographic)
- A body (typographic)
- Optional inline marks (italic phrases)
- Optional links (underlined text affordances)
- Generous architectural whitespace above and below

A field does *not* have:

- Border
- Background fill
- Radius
- Shadow
- Hover state (other than text-link underline on inline affordances)

Cards survive only in earned contexts:

- The drawer
- Tabular numeric blocks inside the drawer
- Form inputs (the ask-back input)

Everything on the editorial surface becomes fields. **The product loses ~95% of its cards.**

## VIII. Per-surface chrome reduction targets

| surface | current (J-rev1) chromed elements | target |
|---|---|---|
| Today | ~12 (orientation card, hero pulse gradient, spotlight cards × 2-3, chips per card × 4-6) | ≤3 (masthead hairline if needed; drawer when invoked; conviction wash on one field) |
| Opportunities | ~30-50 (regime banner + 6 lanes × 1-6 cards × ~5 chips each) | ≤2 (drawer; possibly one hairline) |
| Holdings | ~12 per position (card + 5-6 chips + 2-3 action pills + guidance pill) | ≤2 (drawer; one section divider) |
| Research (per-symbol) | ~15-25 | ≤4 (drawer; tabular blocks within sections) |
| Approaches | ~20+ | ≤2 |
| Journal | ~15+ | ≤1 (drawer when opened) |
| Learn | ~20+ | ≤2 |

Drawer remains the single workhorse of "dense detail."

## IX. Conviction emphasis without chrome

Phase J introduced gold border-left stripe + soft wash on conviction-grade cards. Under this policy:

- **Stripe removed** (it's a border).
- **Wash retained**, redefined as a faint warm-toned background gradient with no visible edge.
- **One italic line above the field**: *"Today's strongest read."* (in Newsreader italic).

No stripe. No border. No badge. The italic line + faint wash. Single accent moment per page maximum.

Specific wash math: see `CREATIVE_DIRECTION_COLOR_MATERIAL.md` §V.

## X. Eyebrows + section labels

Eyebrows ("Today · AI strategist", "Opportunities · today's read") removed everywhere except the masthead.

Replacement: each surface has a **single editorial section title** in Newsreader at editorial scale, set directly on the page, no container. The section title carries the identity.

Example:

```
Today's Briefing               ← masthead (Today only)
Friday, May 15 · Edition #142

Watching                       ← section title (Newsreader, set on page)

We're watching twenty-five     ← editorial paragraph (field)
setups across five underlyings.
```

No `.opt-narrative-eyebrow`. No "Today · AI strategist". No live-state chip. Type only.

## XI. The orientation card — final treatment

Current: bordered card with gradient and left-stripe sitting above the hero on first visit.

**Final**: italic single-line first-visit phrase set directly on the page, between the masthead and the first section. No card. No border. No fill. No dismiss button (line removes itself on second visit via localStorage).

```
Today's Briefing
Friday, May 15 · Edition #142

We use Today to summarize what actually deserves attention right now.   ← orientation, italic, muted

Watching
We're watching twenty-five setups...
```

## XII. Forbidden chrome patterns — master list

After rollout, these do not exist on the editorial surface:

1. Any card with border on editorial body
2. Any card with fill/background on editorial body
3. Any chip (bias, catalyst, IV, premium, conviction, lane, status)
4. Any pill (guidance, action)
5. Any eyebrow row repeating product identity
6. Any section-banner gradient
7. Any hero gradient
8. Any border-left stripe used as decoration
9. Any dashed-border empty state block
10. Any radius value other than 0 / 8 / 12
11. Any shadow on editorial body
12. Any "Powered by AI" / robot-icon mark
13. Any live-state chip on individual surfaces

Drawer keeps chrome. Forms keep chrome. Hover affordances earn chrome temporarily.

## XIII. Per-element migration map (for future implementation)

| current component | becomes |
|---|---|
| `OptionsOpportunityCard` | `<Field>` containing typography only; links instead of action pills; chips inlined |
| `OptionsPositionCard` | `<Field>` with typographic guidance mark, no pill |
| `OptionsHeroPulse` | Type-only `<header>` directly on page; gradient + border + paper noise removed |
| `OptionsOrientationCard` | Italic single-line phrase, no component |
| `OptionsLiveStateChip` | Removed; replaced with single page-footer line |
| `OptionsBiasChip` | Removed; inline italic phrase |
| `OptionsCatalystChip` | Removed; inline italic phrase |
| `OptionsActionPills` | Text links, no chrome |
| Section banners (regime, positions, research) | Type-only section headers, no container |

## XIV. The CI success test

Code change evaluated against this artifact:

> *"Does this change add chrome? If yes — does the chrome appear on the editorial body? If yes — reject."*

Subsidiary tests:

- Did this PR introduce a new chip? → reject
- Did this PR introduce a new border on the editorial surface? → reject
- Did this PR introduce a new radius value? → reject
- Did this PR introduce a new gradient? → reject
- Did this PR introduce a new shadow on the editorial body? → reject
- Did this PR introduce a new pill row? → reject
- Did this PR keep chrome ratio ≤25% on the affected surface? → check

## XV. Risk acknowledged

This is the most aggressive reduction in the project. Approximately 80% of current Options Copilot visible chrome disappears.

Risk: post-reduction, surfaces could read *bare* / under-built.

Mitigation: **type carries the surface** + **invisible structure carries the architecture**. Newsreader at editorial scale + first-person plural voice + generous architectural whitespace + alignment rails + luminance zones must do the work cards used to do.

If post-rollout the surface reads bare, the recovery is **not** to add chrome back — it's to **strengthen the type + tighten the invisible structure**.

## Linked artifacts

- `CREATIVE_DIRECTION_SPINE.md`
- `CREATIVE_DIRECTION_VOICE.md`
- `CREATIVE_DIRECTION_STUDIES.md`
- `CREATIVE_DIRECTION_COLOR_MATERIAL.md`
