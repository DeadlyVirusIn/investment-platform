# Creative Direction — Color + Material Philosophy

**Status**: accepted 2026-05-15 — values locked precisely
**Phase**: K (Creative Direction)
**Inherits**: all prior creative-direction artifacts

The highest-stakes artifact. Wash luminance math, baseline color, material identity. Everything color downstream inherits from here.

---

## I. The defining risk — "tasteful mud"

Most editorial-restrained dark products fail in the same way: cool slate (#0E1117 family) + white text + muted greys → restrained, tasteful, **emotionally inert**.

That's mud. The most generic premium-fintech aesthetic in existence — every B2B SaaS dark mode since 2019.

The product cannot land here. This artifact's central design problem is **carrying warmth, depth, and emotional temperature with extreme restraint** — without sliding into either chrome or mud.

### Failed reference products (the mud bench)

- macOS Stocks dark mode
- Robinhood's calm theme
- Most Tailwind `slate-900` + `zinc-200` starter palettes
- Plaid's dashboard
- Most fintech onboarding flows
- VSCode "Dark+"

---

## II. Material identity commitment

> **Ink on warm paper, inverted.**

The product's material is **warm-dark surface with cream text** — the inversion of late-night newsprint. Metaphor: *a reader's desk lamp on a single sheet of paper at 11pm*: warm, calm, atmospheric, hand-touched.

**Not:**

- Slate (cold, generic)
- Glass (Apple, too theatrical)
- Linen (Stripe, too brand-y)
- Carbon (Bloomberg, too operator)
- OLED black (TikTok / Twitter dark, too clinical)

**Yes:**

- Nightstand newsprint
- FT app dark mode (closest existing reference)
- Kindle "Sepia" mode (warm paper)
- Substack reader mode at midnight
- The light a vinyl reissue's gatefold sleeve reflects

The material is *the product's signature*. A returning user recognizes the warm-dark surface immediately — it's not the typeface, not the layout; it's the *temperature of the page itself*.

---

## III. Anti-brown-UI guard (locked)

The warmth must remain **atmospheric and almost imperceptible**.

Verification test: if a fresh viewer describes the surface as "warm," they're noticing correctly. If they describe it as "brown" or "themed," the warmth has overshot.

The locked value `#0F0D0A` sits *below the perception threshold for color* and *above the threshold for atmosphere*. Future tuning must preserve this balance.

---

## IV. Complete token table — single source of truth

```css
/* ==== Substrate ==== */
--surface-base:        #0F0D0A;
--surface-drawer:      #18140E;

/* ==== Ink ==== */
--ink-primary:         #ECE6D8;
--ink-muted:           #B5AC9B;
--ink-fainter:         #7C7568;

/* ==== Verdict typography ==== */
--verdict-on-warm:     #F2E9D4;
--verdict-on-cool:     #DEE3E8;

/* ==== Material hairline ==== */
--hairline:            rgba(236, 230, 216, 0.06);
--hairline-drawer:     rgba(236, 230, 216, 0.08);

/* ==== Warm wash (conviction + take-profit) ==== */
--wash-warm-gradient:
  linear-gradient(
    93deg,
    rgba(83, 64, 47, 0.058) 0%,
    rgba(83, 64, 47, 0.042) 35%,
    rgba(83, 64, 47, 0.020) 72%,
    rgba(83, 64, 47, 0.000) 100%
  );

/* ==== Cool wash (decisive loss) ==== */
--wash-cool-gradient:
  linear-gradient(
    93deg,
    rgba(59, 80, 99, 0.048) 0%,
    rgba(59, 80, 99, 0.035) 35%,
    rgba(59, 80, 99, 0.018) 72%,
    rgba(59, 80, 99, 0.000) 100%
  );

/* ==== Drawer elevation ==== */
--drawer-shadow:
  0 16px 48px rgba(0, 0, 0, 0.32),
  0 4px 12px rgba(0, 0, 0, 0.24);

/* ==== Phase J tokens retired ==== */
/* DELETED: --opt-color-conviction-gold      (replaced by wash) */
/* DELETED: --opt-color-conviction-gold-soft (replaced by wash) */
/* DELETED: --opt-paper-noise                (material identity now
                                              carried by ink+warm-dark
                                              pair, not by texture) */
```

---

## V. The baseline — `#0F0D0A` rationale

| variable | value |
|---|---|
| Hue (HSL) | ~30° (warm amber territory, near-zero saturation) |
| Saturation | 4.5% (very low — warm character without color cast) |
| Lightness | 4.9% (deep but not pitch) |

Reads as "warm-dark" in side-by-side with cool-slate `#0E1117`. Without comparison, the eye reads it as *dark* — warmth registers subconsciously.

### Alternatives rejected

| candidate | reason |
|---|---|
| `#000000` | OLED-marketing connotation; no warmth |
| `#0E1117` | Mud trap |
| `#1A1814` | Too light — reads as elevated drawer |
| `#0A0807` | Too dark for italic body type |
| `#181410` | Too brown; reads as themed |

---

## VI. Ink colors — three-step cream ramp

```
--ink-primary:    #ECE6D8     (paper cream, 14.8:1 contrast on baseline)
--ink-muted:      #B5AC9B     (faded cream, 7.4:1 contrast)
--ink-fainter:    #7C7568     (dim cream, 3.7:1 contrast — AA only)
```

| role | color |
|---|---|
| Body type, italic phrases, section titles, masthead | `--ink-primary` |
| Captions, timestamps, "Ask one thing back", footer attribution, overflow disclosures, italic transitions | `--ink-muted` |
| Tertiary metadata (edition number tail), drawer chrome details | `--ink-fainter` |

Pure white rejected — reads clinical. Cool grey-white rejected — mud. Warm off-white = paper-on-warm-dark.

Three-step cream ramp gives typography enough range to create hierarchy *through luminance alone* — section titles and body type are the same color; type size + role does the hierarchy work.

---

## VII. Wash temperatures — exact spec

The rarest material moments. Three instances maximum per visit.

### Conviction wash (warm)

Applied as gradient layer over `--surface-base`, NOT as solid fill.

```
background-image: linear-gradient(
  93deg,
  rgba(83, 64, 47, 0.058) 0%,
  rgba(83, 64, 47, 0.042) 35%,
  rgba(83, 64, 47, 0.020) 72%,
  rgba(83, 64, 47, 0.000) 100%
);
```

Why these stops:

- 93° (slightly off-horizontal) — deliberate asymmetric direction so wash reads "lit from upper-left" not "card-shaped highlight"
- 0.058 → 0.042 in first 35% — wash *body* sits where verdict/content sit
- 0.042 → 0.020 between 35-72% — slow tapering
- 0.020 → 0 between 72-100% — final fade; **wash never has a hard right edge**

### Cool restraint wash (decisive loss)

```
background-image: linear-gradient(
  93deg,
  rgba(59, 80, 99, 0.048) 0%,
  rgba(59, 80, 99, 0.035) 35%,
  rgba(59, 80, 99, 0.018) 72%,
  rgba(59, 80, 99, 0.000) 100%
);
```

Slightly lower alpha than warm wash because cool hues read more luminous on dark at identical alpha.

### Take-profit wash (decisive gain)

**Reuses the warm conviction gradient.** Same values. Warmth = positive in this product. Two different warm gradients would dilute meaning.

### What the wash is NOT

- Not a color block
- Not a card background
- Not a highlight
- Not a status color
- Not visible at right edge (no boundary)
- Not animated by default (Motion artifact decides)
- Not present without accompanying italic signpost line

Wash always co-occurs with typographic moment. Wash + verdict = one material moment.

---

## VIII. Verdict typography colors

```
--verdict-on-warm:  #F2E9D4    (warm cream, +6% brighter than --ink-primary)
--verdict-on-cool:  #DEE3E8    (cool cream, same luminance, cool-tinted)
```

| moment | color | reading |
|---|---|---|
| "Take the gain." / "Today's strongest read" | `--verdict-on-warm` on warm wash | Radiates — warmth + brightness |
| "Take the loss." | `--verdict-on-cool` on cool wash | Sobering — cool tint registers gravity. Not red. Not alarming. *Composed.* |

Both verdict colors are full ink luminance — the brightest type on the page when they appear.

---

## IX. Hairline color

```
--hairline:    rgba(236, 230, 216, 0.06)
```

Same hue as `--ink-primary`, 6% opacity. Reads as *slight separation in the paper material* — not a drawn line. Optically dissolves at viewing distance.

---

## X. Drawer surface

```
--surface-drawer:  #18140E    (lightness +3.5% from baseline, same hue)
```

Reads as *paper lifted from the desk* — same material, different elevation.

Drawer chrome:

- Outer border: `1px solid rgba(236, 230, 216, 0.08)` — slightly more visible than page hairline
- Internal separators: `--hairline` (6%)
- Drop shadow: `0 16px 48px rgba(0, 0, 0, 0.32), 0 4px 12px rgba(0, 0, 0, 0.24)`

---

## XI. Accent color policy — the locks

> **The product has no accent colors.**

Not red. Not green. Not yellow. Not blue. Not purple. Not gold (gold is retired). No status dots. No alert tints. No AI-purple. No success greens. No warning ambers.

**Status / emotion communicated by temperature**, not by symbol:

- Conviction / gain = warm wash + warm-cream verdict
- Loss = cool wash + cool-cream verdict
- Neutral = baseline (no wash)
- Uncertainty = italic + `--ink-muted`

This is the hardest single discipline lock. Every product instinct will pull toward "just a small red dot for the loss" or "a green check for the gain." **No.** The wash + verb (*take the loss / take the gain*) carry it. Adding accent color collapses the editorial discipline.

### What's permitted that looks like color but isn't

- Wash gradients (≤6% alpha) — material, not accent
- Verdict crème shifts (warm vs cool cream) — temperature, not accent
- Muted ink ramp — luminance, not accent

---

## XII. Restrained-clarity guard

The no-accent policy must NOT collapse into illegibility or directional ambiguity. The reader must always know:

- Which moment matters most on this page
- Which decisions are decisive vs holding
- Which direction the strategist leans

Clarity is preserved by:

- Typography weight (verdict at editorial scale)
- Position-on-page (Tier 1 above Tier 2)
- Wash temperature (warm vs cool emotional polarity)
- Verdict line (decisive verbs: "take the loss", "take the gain")

Never by status colors.

If a future iteration loses directional readability, the recovery path is **not** accent colors — it's stronger typographic hierarchy and clearer verdict phrasing.

---

## XIII. Light mode commitment

**Dark mode is the defining surface.** Light mode is not specified in Phase K.

Reasoning:

- Editorial reading happens at all hours; dark mode is the *atmospheric* mode
- Material identity (*warm paper, inverted*) inverts naturally to light if needed later (cream baseline `#F5EFE0`, ink-warm text `#1A1612`, washes invert to ~7-9% alpha)
- Defining light mode now would dilute Phase K's identity work

Future iterations may add light mode; not done now.

---

## XIV. Failure mode catalog — the "mud" list

If a future PR introduces any of these, reject:

| trap | why it fails |
|---|---|
| Cool slate baseline (`#0E1117` family) | Generic SaaS mud |
| Pure white body text on dark | Clinical, no material |
| Cool grey body text on dark | Mud trap |
| Status dots (red/green/amber) | Reverts to dashboard vocabulary |
| Linear gradient backgrounds (Stripe-style) | Brand-y, theatrical |
| Glass / blur backdrop | Apple aesthetic, wrong identity |
| Color-coded bias chips (bullish-green, bearish-red) | Pure chrome regression |
| Theatrical AI-purple highlights | Generic AI-product cliché |
| Yellow / amber warning tints | Dashboard alert vocabulary |
| Multiple wash temperatures beyond warm + cool | Vocabulary inflation |
| Wash visible right-edge | Reads as card |
| Wash on more than 3 elements per visit | Vocabulary dilution |
| High-saturation accent on hover | Hover breaks editorial calm |
| Borders defined in any color other than ink-opacity-6% | Color-noise leak |
| Raw monospace greeks columns on editorial surface | Operator-vocabulary leak; drawer-only |
| Surface that reads "brown" or "themed" | Anti-brown-UI guard tripped |

---

## XV. Verification tests

When rollout begins, every page must pass:

1. **Mud test**: side-by-side with macOS Stocks dark + Robinhood dark + generic Tailwind `slate-900`. Page must read *distinct*.
2. **5-second warmth test**: unfamiliar viewer describes temperature in one word. If "cool" or "grey," fail.
3. **Wash visibility test**: user registers *temperature shift* in wash zone but cannot identify wash boundary without close inspection.
4. **Verdict gravity test**: "Take the loss." on cool wash reads *sobering* — not alarming, not neutral.
5. **Hairline dissolve test**: visible at 14" reading distance but optically dissolves when eye relaxes.
6. **Ink-on-warm test**: italic body type on baseline reads like *paper italics inverted* — soft, paper-textured. If "italic text on dark background" (generic), cream undertone is off.
7. **Brown-UI test**: viewer describes surface as "warm," not "brown."

---

## XVI. Re-stated commitments

- No accent colors
- Three wash instances maximum per visit
- Material is "ink on warm paper, inverted"
- Wash boundaries always dissolve — no hard edges
- Verdict typography carries gravity; temperature carries polarity
- Paper noise (Phase J) retired
- Gold accent (Phase J) retired
- Dark mode is the defining surface; light mode not specified
- Warmth is atmospheric, not thematic (anti-brown-UI guard)
- No-accent policy preserves directional readability through type + position + temperature

---

## Linked artifacts

- `CREATIVE_DIRECTION_SPINE.md`
- `CREATIVE_DIRECTION_VOICE.md`
- `CREATIVE_DIRECTION_CHROME.md`
- `CREATIVE_DIRECTION_STUDIES.md`
- `CREATIVE_DIRECTION_TYPOGRAPHY.md` *(next artifact)*
