# Frontend Design Adaptation Plan — "Calm Premium Investing Mentor"

**Date**: 2026-05-20
**Status**: PLAN ONLY — no implementation, no design tokens shipped, no
nav changes yet
**Predecessors**:
- `VISION_ALIGNMENT_UI_AUDIT.md` (10 mismatches identified)
- `SEMANTIC_FREEZE_REVIEW.md` (constitutional locks for copy)
- `SYSTEM_COHESION_REVIEW.md` (9 cohesion fixes already shipped)

## Direction in one sentence

Transform the visible default landing from "operator console with a calm
voice on top" into "calm trusted financial coach with an operator
console one click away" — **without** touching accounting, trading,
reasoning generation, options lifecycle, Phase L locks, or any
constitutional contract.

## Hard truth constraints (locked, non-negotiable)

| Lock | Enforcement |
|---|---|
| No fake confidence % | Tier-A lint (Phase L) |
| No unsupported win-rate claims | New: design system must never render a top-line win-rate |
| No "AI sees / AI suggests / AI is" | Tier-A lint (15 new patterns shipped) |
| No "real-time alerts" unless wired | Visual: never use word "real-time" |
| No "options execution" until Canary proves lifecycle | HONEST-BANNER locks |
| No live-trading implication | Every NAV labeled "Paper" somewhere |
| Polygon live estimate must say "delayed 15 min" | Phase 1b lock |
| Official snapshots distinct from live | Dual-display lock |
| Recommendations are "Signals" unless backed by paper_trade | UI-1 lock |

---

## 1. Design system proposal

### 1.1 Color tokens (warm off-white + deep ink + restrained accent)

```css
:root {
  /* Surfaces — warm paper, not sterile gray */
  --surface-paper:        #F7F4EC;   /* page background */
  --surface-elevated:     #FDFBF6;   /* card background */
  --surface-sunken:       #EFEBE0;   /* secondary container, accordion bg */
  --surface-overlay:      rgba(247, 244, 236, 0.94);  /* modal scrim */

  /* Ink — calm charcoal w/ a hint of green */
  --ink-primary:          #1B2520;
  --ink-secondary:        #5C655F;
  --ink-muted:            #8B928D;
  --ink-faint:            #B5B9B4;

  /* Single trust accent — deep sage. Not emerald. Not bright. */
  --accent-trust:         #2E5043;
  --accent-trust-soft:    #C7D7CF;
  --accent-trust-faint:   #E6EEEA;

  /* Status tones — muted, never theatrical */
  --tone-positive:        #3D6B5B;   /* up / gain (sage, not emerald) */
  --tone-negative:        #A85F4D;   /* down / loss (terracotta, not red) */
  --tone-warning:         #B8825F;   /* warm amber (not yellow) */
  --tone-neutral:         #6E7670;

  /* Borders — barely visible */
  --border-quiet:         #E5DFD0;
  --border-medium:        #D8D1BD;
  --border-strong:        #A6A299;

  /* Focus ring — keyboard accessibility, low chroma */
  --focus-ring:           rgba(46, 80, 67, 0.35);
}
```

**Tonal contract**:
- **No glow**: every existing `--*-glow` token drops to `rgba(_,_,_,0.06)` or removes
- **No hover lift**: `transform: translateY(-2px)` removed across `picks.css`, `portfolio.css`, etc.
- **No emerald/red dual**: positive/negative use sage/terracotta with ~40% saturation of current
- **Single accent**: `--accent-trust` is THE primary action color; everything else is ink

### 1.2 Typography

```css
:root {
  /* Editorial serif for hero moments only (NAV, AI voice sentence, page H1) */
  --font-display: "Source Serif 4", "Charter", Georgia, ui-serif, serif;

  /* Body sans — Inter already loaded, keep it */
  --font-body:    "Inter", system-ui, -apple-system, sans-serif;

  /* Tabular numerics for money */
  --font-numeric: "Inter", ui-monospace, monospace;
  font-variant-numeric: tabular-nums;

  /* Size scale (target: novice readable, not terminal-tight) */
  --type-display:  32px / 38px;    /* hero NAV, page title */
  --type-headline: 22px / 28px;    /* AI voice sentence */
  --type-title:    18px / 26px;    /* card titles */
  --type-body:     16px / 24px;    /* paragraph text */
  --type-meta:     13px / 18px;    /* metadata */
  --type-micro:    11px / 16px;    /* labels, rarely used */

  --tracking-display:  -0.01em;
  --tracking-body:      0em;
  --tracking-meta:      0.01em;     /* never uppercase 0.14em anymore */
}
```

**Discipline**:
- No `text-transform: uppercase` with wide letter-spacing (currently widespread on labels)
- No 11-13px body text — bump to 16px
- Serif used sparingly: hero NAV, AI voice sentence, page H1 only — everywhere else stays Inter
- Numbers always `tabular-nums`

### 1.3 Spacing

```css
--space-1:  4px;
--space-2:  8px;
--space-3:  12px;
--space-4:  16px;
--space-6:  24px;
--space-8:  32px;
--space-12: 48px;
--space-16: 64px;
--space-24: 96px;
--space-32: 128px;
```

**Page gutters**: 80px on desktop (≥1024px), 24px mobile. Reading
column width capped at 720px for prose; 1080px max for data layouts.

**Vertical rhythm**: 32px between sections. 64px between page chapters.
Cards stack with 16px gaps. Lists use 12px row spacing.

### 1.4 Card style

```css
.calm-card {
  background: var(--surface-elevated);
  border: 1px solid var(--border-quiet);
  border-radius: 12px;       /* not 16; not 8 */
  padding: var(--space-6);   /* 24px */
  box-shadow: none;          /* no shadows at rest */
  transition: border-color 200ms ease-out;
}
.calm-card:focus-within { border-color: var(--accent-trust); }
.calm-card:hover { border-color: var(--border-medium); }
```

**Rules**:
- 1px border, no drop shadow at rest
- Hover changes border color only (no lift, no shadow)
- Focus uses `--accent-trust` border (no blue browser default)
- Padding 24px standard; 32px for hero cards; 16px for compact rows

### 1.5 Motion

```css
:root {
  --motion-fast:    150ms ease-out;
  --motion-default: 200ms ease-out;
  --motion-slow:    350ms ease-out;
}
```

**Discipline**:
- Opacity, color, border-color only — no transform, no scale, no
  translate, no glow pulse, no shimmer
- No spinning loaders on Layer 1 (use a calm skeleton or a static
  "Loading…" line)
- No autoplay charts, no parallax
- Reduced motion: full respect for `prefers-reduced-motion: reduce`
  (already partially honored in `index.css`)

### 1.6 Icons

- Library: Lucide (already installed)
- Stroke weight: 1.5px (currently 2px in many uses)
- Default size: 20px (currently 16-18px mixed)
- Color: inherit (`currentColor`), never hard-coded
- Allowed icons (Layer 1): TrendingUp / TrendingDown / Circle (dot) /
  Info / ArrowRight / ChevronRight / Clock / BarChart3 / BookOpen
- Forbidden on Layer 1: ChartLine animated, Sparkles, Zap, Rocket,
  Trophy, anything game-ish

---

## 2. New Layer-1 navigation

| Slot | Label | Route | Component | What it shows |
|---|---|---|---|---|
| 1 | **Today**     | `/`            | new `<TodayPage/>` shell | Calm AI read + Portfolio summary + Top action + AI track record |
| 2 | **Portfolio** | `/portfolio`   | existing `<CopilotHoldings/>` (lightly restyled) | Current positions with per-position story |
| 3 | **Ideas**     | `/ideas`       | existing `<ActionQueuePage/>` (renamed) | Full signal queue with filters |
| 4 | **Learn**     | `/learn`       | new `<LearnIndex/>` shell | Glossary + playbooks (sources from `lib/novice/glossary`) |
| — | _Advanced_    | collapsed      | section toggle | Events / Strategies / Options / Risk / Decisions |
| — | _Operator_    | hidden        | direct URL only | Signal Lab / Alpha Lab / Ops / Agents / Diagnostics |

Existing nav (`page_flow.ts:25-79`): 12 items in 5 sections → 4 visible
+ 1 collapsible + operator routes off-nav.

---

## 3. Today page hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│ (calm header — 1 row, ≤ 48px tall)                          │
│   logo · Today  Portfolio  Ideas  Learn      [user menu]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Good morning, Kunal.                          [t=0s]      │
│                                                             │
│   ──────────────────────────────────────────────────        │
│                                                             │
│   THE AI READ TODAY                                         │
│   "Light buy pressure on two names. Portfolio is up         │
│    1.2% on the week."                                       │
│                                              [t=5s]         │
│   ──────────────────────────────────────────────────        │
│                                                             │
│   YOUR PORTFOLIO                                            │
│   $117,314                                                  │
│   Live estimate: $115,358 · prices delayed 15 min           │
│   Official close: $117,314 · Tue, May 19                    │
│                                                             │
│                            [sparkline — small, calm]        │
│                                                             │
│   ──────────────────────────────────────────────────        │
│                                                             │
│   ONE THING TO LOOK AT                       [t=15s]        │
│   ┌────────────────────────────────────────────────┐        │
│   │ NVDA                                Signal: Buy │        │
│   │                                                 │        │
│   │ Reasoning: <plain English from backend>         │        │
│   │                                                 │        │
│   │ Reference: $X target · $Y stop                  │        │
│   │                              [ See details → ]  │        │
│   └────────────────────────────────────────────────┘        │
│                                                             │
│   ──────────────────────────────────────────────────        │
│                                                             │
│   AI'S RECENT MOVES                          [t=30s]        │
│   Up 1.2% since Mar 14 · biggest dip −3.4% on Apr 22        │
│                                                             │
│   • 2d ago   AMAT     closed +4.2%                          │
│   • 4d ago   KLAC     closed −1.8%                          │
│   • 6d ago   NVDA     opened                                │
│   • 9d ago   FDX      closed +2.1%                          │
│                                                             │
│   ──────────────────────────────────────────────────        │
│                                                             │
│   WHAT CHANGED SINCE YOU LAST VISITED                       │
│   <one-sentence diff from prior session>                    │
│                                                             │
│   ──────────────────────────────────────────────────        │
│                                                             │
│   LEARNING CARD (rotates daily, optional skip)              │
│   "What does 'Trim' mean?"                                  │
│   Trim = reduce exposure without exiting. The signal        │
│   appears when momentum weakens but the thesis is intact.   │
│                                          [ More terms → ]   │
│                                                             │
│   ──────────────────────────────────────────────────        │
│                                                             │
│   Browse: Ideas · Holdings · Learn                          │
│                              [ Advanced ▾ ]                 │
└─────────────────────────────────────────────────────────────┘
```

**Hierarchy rules**:
- One AI voice sentence — never two
- One portfolio number with live + official labeled distinctly
- One top action — never a grid
- AI track record is fourth, not buried
- Learning card is fifth (mentor identity)
- "Advanced" expander is the ONLY exit to operator surfaces

### 3.1 Above-fold contract (1280×800 default viewport)

Visible without scroll:
1. Header (48px)
2. Greeting (24px line + 32px padding)
3. The AI Read Today (3 lines max + label)
4. Portfolio NAV (display number + 2 small subtitles)

Total: roughly 480-520px. Below fold: action card, track record,
learning card, advanced.

### 3.2 Below-fold

Items 4-7 from the storyboard above. Generous spacing, no second
hero, no competing density.

---

## 4. Component migration map

### 4.1 KEEP (no visual change, just remount in TodayPage)

| Component | Current location | New role |
|---|---|---|
| `OverviewHero.tsx`              | `PicksPage.tsx:228` | Primary "AI Read Today" block (with rewritten styles via tokens) |
| `EquitySparkline.tsx`           | `PortfolioSnapshot.tsx:246` | Stays in NAV row |
| `ReasoningCard.tsx`             | `PickModal.tsx:225` | Stays; honest absence already shipped |
| `MetricHelpTooltip.tsx`         | scattered | Stays; surfaces glossary on hover |

### 4.2 RESTYLE (apply new tokens, simplify structure, no logic change)

| Component | Current | Restyle target |
|---|---|---|
| `PortfolioSnapshot.tsx` | Hero NAV + sparkline + 4 metric tiles + posture banner + 11 secondary metrics | Hero NAV + sparkline + dual-label (Live / Official) + 0 secondary metrics |
| `TopStrip.tsx`          | 6 dense cells + Ticker + StatusRail | 1 cell (NAV + as-of) on Layer 1 routes only |
| `PickModal.tsx`         | Action badge → Reference price → Catalysts → AI reasoning → Technical detail (4-deep operator panel) | AI reasoning → Action badge → Reference price → "Show technical detail" expander |
| `CopilotHoldings.tsx`   | Per-position list, no track-record section | + new `<AITrackRecord/>` block at top |

### 4.3 DEMOTE TO ADVANCED (still reachable, not Layer-1 nav)

| Page | Current nav | New location |
|---|---|---|
| Decisions       | section "SIGNALS" | Advanced → "AI activity audit" |
| Signal Lab      | section "SIGNALS" | Advanced (operator) |
| Events          | section "MARKET"  | Advanced |
| Strategies      | section "EXECUTION" | Advanced |
| Risk Dashboard  | section "PORTFOLIO" | Advanced |
| Alpha Lab       | section "SYSTEM"  | Advanced (operator) |
| Ops             | section "SYSTEM"  | Advanced (operator) |
| Agents          | top-level         | Operator only (direct URL) |

### 4.4 REMOVE FROM LAYER 1 (hide entirely from default nav)

| Element | File | Why |
|---|---|---|
| `StatusRail`                  | `Shell.tsx:113-138` | Engine vocabulary leak (UX-5 lock) |
| `MarketTicker`                | `Shell.tsx:113-138` | Persistent visual noise on every page |
| `DensityToggle`               | `PicksPage.tsx:?`   | Hide on Layer 1; expose only in Advanced |
| 27 `/options/*` routes       | `App.tsx:123-171`   | Collapse to `/options` only |
| Action color glow             | `picks.css:18-48`   | Casino theatre |
| Hover lift on cards           | `picks.css:3949-3956` | Casino theatre |

### 4.5 NEW (small, additive, sourced from existing data)

| Component | Sources | Lines (est.) |
|---|---|---|
| `<TodayPage/>` shell | Wraps existing components in new layout | ~120 |
| `<AITrackRecord/>` | `usePaperEquity` + `useExecutedTrades` | ~80 |
| `<LearningCard/>`  | `lib/novice/glossary` (already exists) | ~40 |
| `<LearnIndex/>` (route `/learn`) | `lib/novice/glossary` | ~120 |
| `<AdvancedExpander/>` (collapsible nav section) | local state | ~30 |

Total new code: ~390 lines, all view-layer composition. **Zero new
endpoints. Zero new data models. Zero backend changes.**

---

## 5. Copy principles

| Principle | Rule | Forbidden alternative |
|---|---|---|
| Observational              | "Up 1.2% since Mar 14"        | "AI is bullish today" |
| Plain English              | "Reduce exposure"             | "Trim allocation per the engine output" |
| Honest absence             | "No new signals today"        | "AI is quiet today" |
| No agency claims            | "Signal: Buy"                  | "AI recommends buying" |
| Reasoning sourced from backend | rendered by `ReasoningCard` | frontend-authored prose |
| Freshness specific          | "Prices delayed 15 min · as of HH:MM" | "Real-time" |
| Paper-only disclosed         | "Live estimate" + "Paper portfolio" labels | dropping "paper" qualifier |
| Recommendations are signals  | "Signal" header in PickModal (UI-1) | "Recommendation" when no paper_trade |

All Tier-A + Phase A/B/D forbidden phrases stay enforced by the
existing CI lint. The new design system must NEVER reintroduce them
even when copy is rewritten for the new tone.

---

## 6. First implementation slice (smallest PR)

### Scope

**ONLY**:
1. Author design tokens file (new) — color, type, spacing, motion, card
2. Author `<TodayPage/>` shell that renders **existing** components
   (`OverviewHero`, `PortfolioSnapshot`, top pick card from
   `TodayPanel`, equity sparkline) inside the new layout
3. Wire `<TodayPage/>` to route `/today` (do NOT replace `/` yet —
   keep old route alive in parallel for A/B comparison)
4. New Layer-1 nav rendered as `<TodayNav/>` (separate from
   `SideNav.tsx`) gated by a feature flag (env var
   `WEB_NEW_NAV_ENABLED`, default false)
5. NO changes to existing PicksPage, PortfolioTerminal, Decisions, etc.

### Out of scope for first PR

- No restyling of existing PickModal / PortfolioSnapshot / CopilotHoldings
- No new `<AITrackRecord/>`
- No new `<LearningCard/>`
- No removal of StatusRail / MarketTicker / DensityToggle from old routes
- No options route consolidation
- No removal of operator nav items
- No backend changes, no data model changes
- No options lifecycle work

### Files touched (estimated)

| File | Type | Purpose |
|---|---|---|
| `apps/web/src/styles/tokens.css` (new) | new | Design tokens |
| `apps/web/src/index.css` | modify | `@import` tokens.css at top |
| `apps/web/src/pages/today/TodayPage.tsx` (new) | new | New page shell |
| `apps/web/src/pages/today/today.css` (new) | new | Layout + typography for Today |
| `apps/web/src/components/today/TodayNav.tsx` (new) | new | 4-item Layer-1 nav, feature-flag gated |
| `apps/web/src/App.tsx` | modify | Mount `/today` route (`/` stays on PicksPage for now) |

Total: 5 new files, 2 modified files. ~400-500 lines.

### Acceptance criteria for first PR

- `/today` route renders the new layout against existing data
- `/` route unchanged
- TypeScript builds clean
- Forbidden-phrase lint passes (no new copy added; just composition)
- Resolver-anchor + canary-gateway lints pass
- Reasoning snapshot suite passes
- Visual diff: side-by-side screenshot of `/` (old) vs `/today` (new)
- No backend / accounting / Phase L / options lifecycle changes
  — verified by `git diff --stat`

---

## 7. Validation plan

### 7.1 CI lints (must all pass)

```
python infra/ci/constitutional_checklist/forbidden_phrases.py    # 30 phrases
python infra/ci/constitutional_checklist/resolver_anchor_lint.py
python infra/ci/constitutional_checklist/canary_gateway_lint.py
python apps/api/tests/unit/test_reasoning_envelope_snapshots.py  # 9 tests
```

### 7.2 Visual validation

- Screenshot `/` (current) at 1280×800
- Screenshot `/today` (new) at 1280×800
- Compare side-by-side; verify the calm-mentor target is visibly closer
  in the new shell
- Repeat at 375×800 (mobile)
- Repeat with reduced-motion enabled (no animations)

### 7.3 No accounting / no trading drift

```bash
# Row counts identical before/after
SELECT 'paper_trade' AS t, COUNT(*) FROM paper_trade
UNION ALL SELECT 'paper_position', COUNT(*) FROM paper_position
UNION ALL SELECT 'paper_equity_snapshot', COUNT(*) FROM paper_equity_snapshot
UNION ALL SELECT 'options_paper_position', COUNT(*) FROM options_paper_position
UNION ALL SELECT 'options_trade_lifecycle_event', COUNT(*) FROM options_trade_lifecycle_event;

# Equity unchanged
curl /api/paper/summary | jq '.equity'  # must equal pre-deploy value
```

### 7.4 TypeScript

```bash
cd apps/web && npm run typecheck
```

### 7.5 Roll-forward / roll-back

| State | Action |
|---|---|
| Flag `WEB_NEW_NAV_ENABLED=false` (default)        | Users see old `/` and old nav |
| Flag `WEB_NEW_NAV_ENABLED=true`                    | Users see `/today` + new nav (still visit `/` if they want old) |
| Roll back                                          | Revert flag → 0 user-facing changes |

---

## 8. Subsequent PRs (planning only)

After PR-1 lands and `/today` works in parallel with `/`:

| PR | Scope | Effort |
|---|---|---|
| **2** | Add `<AITrackRecord/>` to `<TodayPage/>` | S |
| **3** | Add `<LearningCard/>` + `/learn` route | S |
| **4** | Restyle `PortfolioSnapshot` to dual-label + zero secondary tiles | M |
| **5** | Reorder PickModal sections (reasoning first) + remove engineering shrapnel | S |
| **6** | Make `/today` the default `/` route; demote old PicksPage to `/legacy/overview` | S |
| **7** | Collapse SideNav → `<TodayNav/>` only on Layer-1 routes | M |
| **8** | Drop StatusRail + MarketTicker from Layer-1 routes | S |
| **9** | Drop color theatre (glow, lift) from picks.css globally | S |
| **10** | Consolidate `/options/*` 27 routes → 1 + Advanced subnav | M |
| **11** | Hide Signal Lab / Alpha Lab / Ops / Agents from default nav | S |

Each PR is independently revertable. Total effort: ~3-4 focused days
wall-clock.

---

## 9. What this plan deliberately does NOT change

- ✅ No accounting math
- ✅ No trading logic (paper_execution, paper_service)
- ✅ No options lifecycle (still Gate 5 paused)
- ✅ No reasoning envelope generation (Phase L renderer untouched)
- ✅ No new endpoints, no new DB tables, no new migrations
- ✅ No new ML, no new providers
- ✅ No websockets, no streaming
- ✅ No social features, no gamification
- ✅ No fake real-time
- ✅ No copy that would fail the existing 30-phrase Tier-A lint

---

## 10. Approval requested

Approve **PR-1 scope only** (design tokens + `/today` shell + 4-item
nav behind feature flag). Subsequent PRs reviewed individually as
they're proposed.

The smallest first slice does NOT remove anything. It ADDS a parallel
route to validate the new direction. Existing operator surfaces remain
fully intact.

After PR-1 ships and is verified visually, the next gating decision
is: keep `/today` parallel, or promote it to `/`.
