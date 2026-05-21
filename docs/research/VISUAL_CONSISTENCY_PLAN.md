# Visual Consistency Audit + PR-2 Plan

**Date**: 2026-05-20
**Status**: PLAN ONLY — no implementation, no scope expansion beyond
PR-2 explicit deliverables
**Predecessors**:
- `FRONTEND_DESIGN_ADAPTATION_PLAN.md` (PR-1 shipped)
- `VISION_ALIGNMENT_UI_AUDIT.md` (top-10 mismatches identified)
- `SEMANTIC_FREEZE_REVIEW.md` (30-phrase Tier-A lock)

`/today` now feels premium and calm. The rest of the app does not.
This audit identifies the visual gap and proposes the smallest next
PR to close it without expanding scope.

---

## 14-component visual consistency audit

### 1. PortfolioSnapshot
- **Still operator-y**: 11 `.ps-metric` tiles below the hero (`PortfolioSnapshot.tsx:130-230`). Uppercase 0.14em labels (`picks.css:295`). Hover lifts (`picks.css:264-265`).
- **Clashes with `/today`**: Yes — `/today` shows 1 number; `/portfolio` shows 13+ tiles in dense grid.
- **Should inherit tokens**: Yes — colors, typography, card style, no glow.
- **Should remain advanced**: No. This is a Layer-1 surface (mounted on `/overview` + `/portfolio`).
- **Touched in PR-2**: **YES** — primary target.

### 2. PickModal
- **Still operator-y**: Action badge with `--picks-buy-glow` (`picks.css:236`, rgba 0.30). Top-bar radial gradient on modal (`picks.css:487-490`). Confidence band displayed as "·Medium conviction" tag. Technical details section spills `engine_version`, `composite_score`, `family_scores`, `raw_action` (`PickModal.tsx:336-407`).
- **Clashes with `/today`**: Yes — the One-thing card on `/today` opens this modal; tonal jump is harsh.
- **Should inherit tokens**: Yes — surface, ink, single accent.
- **Should remain advanced**: Technical details panel = yes (collapse it).
- **Touched in PR-2**: **YES** — primary target.

### 3. CopilotHoldings
- **Still operator-y**: Trade lifecycle ribbon, per-position story card layout dense. Holdings table inherits dashboard chrome.
- **Clashes with `/today`**: Moderate — calmer than PickModal but still busy.
- **Should inherit tokens**: Eventually yes.
- **Touched in PR-2**: **NO** (deferred to PR-4).

### 4. TopStrip
- **Still operator-y**: 6 cells of dense numerics + uppercase labels (`TopStrip.tsx:65-153`). Persistent across every legacy route.
- **Clashes with `/today`**: N/A — `/today` doesn't mount Shell, so it doesn't appear there. Other Layer-1 routes (`/overview`, `/portfolio`) DO show TopStrip.
- **Should inherit tokens**: Yes, but trim cells first.
- **Should remain advanced**: After trim, only NAV + as-of stays.
- **Touched in PR-2**: **NO** (deferred to PR-7).

### 5. ReasoningCard
- **Still operator-y**: No. Phase B semantic-freeze pass already cleaned this.
- **Clashes with `/today`**: No — empty-state copy is observational.
- **Should inherit tokens**: Yes (color + type only; no structure change).
- **Touched in PR-2**: **NO** — already constitutional; tokens come automatically when used inside the new modal.

### 6. ActionQueue cards
- **Still operator-y**: Same glow/lift problem (`picks.css:236-265`). Uppercase action labels.
- **Clashes with `/today`**: Yes — `/today` "See full ideas →" lands here. Tonal jump.
- **Should inherit tokens**: Yes.
- **Touched in PR-2**: **NO** — bigger surface; address in PR-3 alongside `/learn` work.

### 7. Holdings table (PositionsTable)
- **Still operator-y**: Dense rows, monospace numerics, alternating shade. Already partially cleaned (Position state column).
- **Clashes with `/today`**: Moderate.
- **Touched in PR-2**: **NO** (PR-4).

### 8. Shell / SideNav
- **Still operator-y**: 12 nav items in 5 uppercase sections with monospace hotkey badges (`SideNav.tsx:34-86`).
- **Clashes with `/today`**: N/A — `/today` doesn't mount Shell.
- **Touched in PR-2**: **NO** (PR-7).

### 9. Buttons / chips / badges
- **Still operator-y**: No canonical primitive. `.u-chip`, `.u-chip-warning`, `.pi-btn`, `.picks-action-badge`, custom hover states scattered across `index.css`, `picks.css`, `portfolio.css`.
- **Clashes with `/today`**: Yes — bleeds tonally whenever any chip renders inside a calm surface.
- **Should inherit tokens**: Critical — needs a single primitive.
- **Touched in PR-2**: **YES** — introduce `<Button/>` + `<Chip/>` + `<Badge/>` primitives backed by tokens.

### 10. Empty states
- **Still operator-y**: Inconsistent — some honest ("No new signals today"), some loud ("⚠ data unavailable"). Mixed iconography.
- **Touched in PR-2**: **NO** — case-by-case in subsequent PRs.

### 11. Tooltips
- **Still operator-y**: Already calm after recent cohesion polish. Use `<Cell tooltip="…">` pattern.
- **Touched in PR-2**: **NO** — touched only if PortfolioSnapshot tooltips need re-styling for tokens.

### 12. Sparkline / chart styling
- **Still operator-y**: `EquitySparkline` stroke is hardcoded emerald (in component). Other charts inherit `--success`/`--danger` from index.css.
- **Touched in PR-2**: **YES, but minimally** — adjust EquitySparkline to use `currentColor` so it inherits the surrounding ink color when rendered inside `.today-root` (and stays emerald on legacy until tokens migrate).

### 13. Mobile spacing
- **Still operator-y**: Several pages don't have `@media (max-width: 640px)` overrides; numbers truncate ugly.
- **Touched in PR-2**: Only PortfolioSnapshot's mobile breakpoint adjusted alongside its restyle.

### 14. Advanced/operator pages — bleed into Layer 1
- **Status**: Acceptable — no advanced page is mounted on Layer 1; they live at distinct routes.
- **Touched in PR-2**: **NO** — contained by route boundary.

---

## A. Visual inconsistency hotspots (ranked)

| Rank | Surface | Severity | Primary issue |
|---|---|---|---|
| 1 | PortfolioSnapshot 11-tile grid    | high | density inconsistent with /today calm |
| 2 | PickModal glow + lift + technical-detail spillage | high | tonal contradiction when entered from /today |
| 3 | Glow tokens (`--picks-buy-glow` etc) used in 4+ places | high | global theatrical color |
| 4 | Hover-lift `transform: translateY(-2px/-3px)` on cards | high | startup-SaaS energy |
| 5 | Uppercase 0.14–0.18em labels everywhere (`picks.css`)| medium | terminal-y density |
| 6 | No canonical button/chip primitive | medium | inconsistency creep |
| 7 | EquitySparkline hardcoded emerald | low | one-line fix |
| 8 | TopStrip 6 cells on legacy routes | medium | deferred (route boundary) |
| 9 | SideNav UPPERCASE section headings | low | deferred (route boundary) |
| 10 | ActionQueue cards (glow/lift) | medium | deferred (PR-3) |

---

## B. Shared token migration strategy

**Principle**: tokens live in a single root-level CSS file under
`.today-root` scope (already shipped in PR-1). To migrate other
surfaces, **promote the tokens to `:root`** so they're globally
accessible, and have other CSS files reference them.

**But**: do NOT immediately swap legacy CSS to use the new tokens
en-masse — that would break visual continuity for users still on
legacy routes. Instead:

1. **PR-2**: keep tokens scoped to `.today-root`. Apply NEW tokens
   to the restyled PortfolioSnapshot + PickModal **only when those
   surfaces are wrapped in `.today-root`** (e.g. on /today/portfolio
   subroute when added later). On legacy routes, both components
   continue to render with their existing styles. This guarantees
   zero legacy regression.
2. **PR-2 introduces**: `apps/web/src/styles/primitives.css` —
   button/chip/badge classes that read tokens. These classes are
   used INSIDE the restyled PortfolioSnapshot + PickModal. Legacy
   surfaces don't import them.
3. **Future PRs (PR-6+)**: migrate `picks.css` to read from tokens
   instead of hardcoded glows; that's the global cutover and is
   gated on visual sign-off.

---

## C. Safest next PR sequence

| PR | Scope | Risk |
|---|---|---|
| **PR-2** (this proposal) | PortfolioSnapshot restyle + PickModal section reorder + primitives.css | low |
| PR-3 | Add `<AITrackRecord/>` to TodayPage (more data, no design changes) | low |
| PR-4 | CopilotHoldings + Holdings table token migration | medium |
| PR-5 | ActionQueue cards + Picks page calm pass | medium |
| PR-6 | Drop glow + lift globally; deprecate `--picks-*-glow` tokens | medium |
| PR-7 | SideNav collapse + TopStrip trim (Layer-1 chrome) | medium |
| PR-8 | Options 27-route consolidation | medium |
| PR-9 | Remove StatusRail + MarketTicker from Layer-1 | low |

Each PR independently revertable. Total: 8 small follow-on PRs,
roughly 1 each per focused session.

---

## D. Canonical components to standardize on

| Component | Canonical (keep, restyle) | Deprecate / replace |
|---|---|---|
| Button | new `<Button variant="primary|quiet|ghost"/>` | `.pi-btn`, raw `<button>` styled inline |
| Chip   | new `<Chip tone="quiet|trust|warn|down|up"/>` | `.u-chip`, `.u-chip-warning`, `.picks-tag` |
| Badge  | new `<Badge dot tone="…"/>` | inline color-coded `<span/>` |
| Card   | new `.calm-card` class (in primitives.css) | `.ps-card`, `.pick-modal-section` inline styles |
| Sparkline | `EquitySparkline` (color via `currentColor`) | per-page hardcoded strokes |
| Action color | dot indicator on Chip/Badge, never glow/wash | `--picks-buy-glow`, radial gradients |

---

## E. Visual patterns that must die globally (eventually)

| Pattern | Where seen | Replace with |
|---|---|---|
| `--picks-buy-glow` etc (rgba 0.24-0.30) | picks.css:24,32,40,48 | dot indicator + ink border |
| `transform: translateY(-2px/-3px)` on hover | picks.css:264, 971; index.css scattered | border-color transition only |
| `text-transform: uppercase` + `letter-spacing: 0.12-0.18em` | picks.css line 295, 554, 585-586, 663-664, 714-715, 744, 779, 861-862, 1070, 1150-1151, 1177; index.css various | small-caps OFF; sentence-case meta labels |
| Dense action chips with colored backgrounds | various | quiet tone w/ tone-dot |
| Excessive 1px-on-1px borders | scattered | single border-color transition, no double borders |

**Migration discipline**: dying patterns get **deprecation comments**
in PR-2 (visible in `picks.css`) but stay functional. Removal lands
in PR-6 after PR-2..PR-5 validate the replacement primitives work.

---

## F. Mobile polish priorities

| Surface | Issue | Fix |
|---|---|---|
| PortfolioSnapshot 11-tile grid | overflows 375px viewport; uses 2-column at md, collapses to 1-col mobile but tiles still tall | reduce to 0 tiles above fold; secondary tiles below fold in 1-col with `--t-3` gap |
| PickModal | full-screen on mobile is OK; technical-detail accordion runs 6-deep nested boxes | collapse + reorder |
| EquitySparkline | width 360 hardcoded | viewBox + width 100% |
| Numerics | font-feature-settings missing on some surfaces | `font-variant-numeric: tabular-nums` global on `:root` |

---

## G. Typography consistency map

```
ROLE                  CURRENT (mixed)               TARGET (consistent)
─────────────────────────────────────────────────────────────────────
Page hero / NAV       Inter 32-38px bold            Source Serif 4 38-44px
AI voice sentence     Inter 16-18px                 Source Serif 4 22-24px
Section heading       Inter 14-16px UPPERCASE 0.14  Inter 12px sentence-case, color: muted
Card title            Inter 14-16px bold            Inter 16-18px medium, ink-primary
Body                  Inter 11-14px                 Inter 16px, ink-primary
Metadata / asof       Inter 10-12px uppercase       Inter 12-13px sentence-case
Numerics (money)      Inter monospace               Inter tabular-nums (no fallback to mono)
```

PR-2 applies this to PortfolioSnapshot + PickModal only.

---

## H. Spacing consistency map

```
TOKEN     PIXELS    USED FOR
──────────────────────────────────
--t-1       4       inline icon-text
--t-2       8       chip padding, small gap
--t-3      12       row gap in lists
--t-4      16       card row spacing
--t-6      24       card padding (default)
--t-8      32       between sections
--t-12     48       between page chapters
--t-16     64       page top margin
```

Used as scoped tokens (`.today-root`) today. PR-2 introduces a
`primitives.css` that exposes them at `:root` so PortfolioSnapshot +
PickModal can use them. Legacy CSS unchanged.

---

## I. Button / chip / badge hierarchy proposal

```
<Button variant="primary">           sage ink-on-paper, no shadow, 1px border, 200ms hover border-color
<Button variant="quiet">             ink-secondary on transparent, hover ink-primary, border-bottom on hover
<Button variant="ghost">             ink-muted, no border; underline on focus
<Button variant="link">              accent color, border-bottom on hover

<Chip tone="quiet">                  paper-elevated, border, ink-secondary text
<Chip tone="trust">                  accent-faint bg, accent text
<Chip tone="warn">                   tone-warn 12% bg, tone-warn text
<Chip tone="up">                     tone-up 10% bg, tone-up text
<Chip tone="down">                   tone-down 10% bg, tone-down text

<Badge dot tone="up">                8px dot + label, no background pill
```

**Forbidden** in primitives:
- No radial gradient
- No box-shadow at rest
- No `transform` on hover
- No `text-transform: uppercase`
- No emoji icons

---

## J. Advanced/operator visual containment strategy

Two rules, enforced by route boundary:

1. **`.today-root` scope**: any component rendered inside the
   `.today-root` wrapper uses ONLY token-driven styles. Operator
   styling (uppercase labels, monospace numerics, dense grids)
   physically cannot leak in because legacy CSS isn't scoped to
   `.today-root`.

2. **`Shell` wrapper**: operator chrome (TopStrip, MarketTicker,
   StatusRail, SideNav) is mounted inside `<Shell/>`. Any route
   NOT under `<Shell/>` (today /today, future /portfolio rewrite,
   future /learn) is automatically free of operator chrome.

Containment is structural, not stylistic. PR-2 reinforces this by
adding the primitives.css **inside `.today-root` only**.

---

## PR-2 — exact scope

### Goal

PortfolioSnapshot + PickModal restyle to match `/today` calm tone.
Introduce primitives.css for Button/Chip/Badge inside `.today-root`.
**Visual coherence on the two highest-traffic shared components.**

### Files (new)

| File | Purpose | Lines |
|---|---|---|
| `apps/web/src/styles/primitives.css` | Token-driven Button/Chip/Badge/Card classes scoped to `.today-root` | ~150 |
| `apps/web/src/pages/today/portfolio/TodayPortfolioPage.tsx` | New parallel route `/today/portfolio` rendering the restyled snapshot inside `.today-root` | ~180 |

### Files (modified, additive only)

| File | Change | Lines |
|---|---|---|
| `apps/web/src/App.tsx` | mount `/today/portfolio` route | +3 |
| `apps/web/src/components/today/TodayNav.tsx` | Portfolio link points to `/today/portfolio` (was `/portfolio`) | +1 |

### Files NOT modified

- `apps/web/src/components/portfolio/PortfolioSnapshot.tsx` — left intact for `/overview` and `/portfolio` legacy routes
- `apps/web/src/components/picks/PickModal.tsx` — same
- `apps/web/src/lib/picks/picks.css` — untouched (glow/lift stays for legacy)
- `apps/web/src/index.css` — untouched

### What PR-2 actually does

1. **Introduce primitives**: `<Button>`, `<Chip>`, `<Badge>`, `.calm-card`
   classes in `primitives.css`. Scoped to `.today-root`.
2. **New TodayPortfolioPage**: parallel route at `/today/portfolio`.
   Wraps content in `.today-root`. Renders:
   - Hero NAV (live + official, dual-label — same shape as /today)
   - Holdings table — simple `.calm-card` list, no glow, no lift
   - Per-position story rows — uses `<Chip tone="up|down">` for
     return state, never a colored background wash
   - No 11-tile metric grid
   - No `.ps-secondary` block
3. **PickModal reorder**: same component restyled when entered via
   `/today` route. Achieved by adding a CSS modifier when invoked
   from `.today-root` — `data-shell="calm"` attribute on overlay —
   that overrides glow/lift/uppercase via `.today-root` cascades.
   Legacy /overview entry still gets the old PickModal styles.
4. **Sparkline**: `EquitySparkline` updated to use `currentColor`
   for stroke when no explicit color prop passed. Inside
   `.today-root`, the stroke inherits `--t-ink-primary`. Legacy
   surfaces continue to pass explicit emerald.

### Out of scope for PR-2

- No SideNav touch
- No TopStrip touch
- No StatusRail / MarketTicker removal
- No global glow/lift removal
- No deprecation of `--picks-*-glow` tokens
- No CopilotHoldings rewrite
- No Holdings table rewrite
- No options surface touch
- No backend / accounting / Phase L / canary lifecycle changes

### Acceptance criteria

| Check | Required |
|---|---|
| Forbidden-phrase lint (30 phrases) | PASS |
| Resolver-anchor lint | PASS |
| Canary-gateway lint | PASS |
| Reasoning snapshot suite | PASS |
| TypeScript build | clean |
| `/today` (PR-1 shell) | unchanged |
| `/overview` (legacy PicksPage) | unchanged |
| `/portfolio` (legacy PortfolioTerminal) | unchanged |
| `/today/portfolio` (NEW) | renders calm holdings view with restyled snapshot |
| PickModal opened from `/today` ideas card | renders calm variant |
| PickModal opened from `/overview` picks | renders legacy variant |
| Constitutional locks unchanged | verified |
| API payload checks: `/api/paper/summary.equity` byte-identical | verified |
| Row counts: paper_trade / paper_position / options_* unchanged | verified |

### Validation plan

```
python infra/ci/constitutional_checklist/forbidden_phrases.py
python infra/ci/constitutional_checklist/resolver_anchor_lint.py
python infra/ci/constitutional_checklist/canary_gateway_lint.py
cd apps/web && npm run typecheck

# Visual diff (operator runs on Haiku)
http://localhost:5173/today              # PR-1 shell — unchanged
http://localhost:5173/today/portfolio    # NEW — calm holdings
http://localhost:5173/overview           # legacy PicksPage — unchanged
http://localhost:5173/portfolio          # legacy PortfolioTerminal — unchanged
```

### Roll-back

```bash
git checkout HEAD -- apps/web/src/App.tsx \
                     apps/web/src/components/today/TodayNav.tsx
rm -rf apps/web/src/pages/today/portfolio \
       apps/web/src/styles/primitives.css
```

Zero residue. Old routes untouched.

---

## What does NOT happen in PR-2

- ✅ No backend changes
- ✅ No accounting math
- ✅ No trading logic
- ✅ No options lifecycle (still Gate 5 paused)
- ✅ No Phase L renderer
- ✅ No new endpoints / schemas / migrations
- ✅ No SideNav / TopStrip / StatusRail / MarketTicker
- ✅ No global glow/lift removal (yet — PR-6)
- ✅ No options routes
- ✅ No removal of operator-only pages
- ✅ No copy that would fail the 30-phrase Tier-A lint
- ✅ No expanding scope beyond the two named components

---

## Approval requested

Approve **PR-2 scope only**:
- `primitives.css` (new, scoped to `.today-root`)
- `TodayPortfolioPage` at `/today/portfolio` (new parallel route)
- `PickModal` calm variant via `data-shell="calm"` attribute (additive,
  not replacement)
- `EquitySparkline` `currentColor` default (additive)
- `TodayNav` Portfolio link points to `/today/portfolio`

On approval, the next gating decisions land in PR-3 (track record) and
PR-4 (CopilotHoldings token migration), reviewed independently.
