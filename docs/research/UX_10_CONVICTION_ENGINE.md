# UX-10 Conviction Engine — Master

**Status:** locked after 3-round adversarial debate (Gemini · Codex · Claude Opus 4.7 · Claude Sonnet 4.6)
**Date:** 2026-05-09
**Pivot:** observation → conviction. Stream substrate stays; verbs become first-class.
**Debate transcripts:** `docs/research/debates/UX_10_conviction/`
**Predecessor docs:** UX-6 (AI Copilot), UX-7 (Visual Design), UX-8B (Portfolio Weather Room), UX-9 (Stream)
**Implementation isolation:** parallel route `/overview?view=conviction` (same pattern as UX-9 Phase 9D). Default `/overview` and `/overview?view=working` and `/overview?view=stream` remain unchanged until cutover (Phase 10I).

---

## TL;DR

UX-10 ships an AI investing copilot that **states recommendations clearly, attaches every recommendation to a thesis, surfaces invalidation before upside, and refuses to render any card that cannot pass a structural-honesty contract.** It is built around four verbs (`OPEN · HOLD · TRIM · EXIT`), four named confidence tiers paired with a freshness state (`Fresh · Aging · Stale · Expired`), a card atom with invalidation appearing visually before target, a hero that allows quiet days as first-class, and a Research Cockpit that carries the trust load via visible decision history and credible bear cases. Options ride a separate `STRUCTURE` namespace with loss named first. All 13 trust safeguards are code-enforced engineering invariants, not designer convention.

---

## Section 1 — Locked across all 4 models (universal agreement)

These ship with no remaining dispute. Each item carries cross-model attribution.

| # | Decision | Attribution |
|---|----------|-------------|
| L1 | **Numeric confidence (`0.82`) dies on every primary surface.** | All 4 (universal R1, locked R2) |
| L2 | **Invalidation appears visually above target on every card.** | Sonnet R1 (originator) · Opus R2 conceded · Codex R3 conceded · Gemini R2 conceded |
| L3 | **Hero must support quiet days with explicit "no new entries" copy.** | Triple convergence R1 (Codex "No new buys today" · Opus "0 new today" · Sonnet "Quiet day"); Gemini supplied the locked copy: *"Market regime: noisy. Maintaining existing positions. No new entries recommended."* |
| L4 | **Bear-case-mandated for the highest confidence tier — composer-level invariant, not designer convention.** | Opus R1 (originator) · Sonnet R2 "verbatim adoption" · Gemini R2 "ultimate safeguard" · Codex R3 conceded |
| L5 | **Options use `STRUCTURE` (or "Options structure:" prefix) as the only top-level verb. Loss named first. Defined-risk by default.** | Sonnet R1 + Opus R1 + Codex R1 (variant) + Gemini R2 conceded |
| L6 | **Decision sentence is the largest visual element on every card; verb is a small label.** | Codex R1 (originator) · Sonnet R2 conceded · Opus R3 conceded · Gemini R2 conceded ("Thesis-First") |
| L7 | **Research Cockpit is the trust center; Stream is a launcher.** | All 4 R3 — uncontested |
| L8 | **Snooze affordance per thesis; logged in decision history.** | Opus R1 · Sonnet R2 adopted · Gemini R2 adopted |
| L9 | **Action ledger per ticker (visible AI track record including misses).** | Opus R1 · Sonnet R2 adopted · Codex R3 conceded |
| L10 | **Calibration line in the reasoning drawer ("Current `Confirmed` hit rate: 60% (rolling 90d). Below 70% target.").** | Sonnet R1 (originator) · Opus R2 conceded · Codex R3 conceded |
| L11 | **Trust safeguards as engineering invariants (schema-enforced, refuses-to-render), not copy guidelines.** | Sonnet R1 · Codex R2 ("component contracts") · Gemini R3 ("12 enforceable Engineering Invariants") |
| L12 | **No countdown clocks visible anywhere — casino mechanic.** | Opus R2 (originator) · Sonnet R3 conceded · all R3 silent dissent |
| L13 | **Reasoning drawer is a single scroll surface, not tabs (tabs hide the bear case behind a click).** | Sonnet R2 · Opus R3 adopted |

**Lock these 13 first. They survive PMs and reorgs.**

---

## Section 2 — Disputes documented

For each dispute, the master picks a default + records the dissent so future PMs can re-open with provenance.

### Dispute D1 — Verb count

| Position | Models | Argument |
|----------|--------|----------|
| **4 verbs** | Sonnet R3, **MASTER DEFAULT** | `OPEN · HOLD · TRIM · EXIT`. WAIT ships no card (suppression). Existing-position scenarios where AI's stance is "do nothing despite movement" become a re-issued thesis card with `HOLD` verb and "do not chase" line. |
| 5 verbs | Opus R3, Gemini R3 | `OPEN · HOLD · TRIM · EXIT · WAIT` (Opus) or `INITIATE · ACCUMULATE · HOLD · TRIM · EXIT` (Gemini). Defends `WAIT` as preserving restraint signal when user is likely to want action. |
| 7 verbs | Codex R3 | `BUY · ACCUMULATE · WATCH · HOLD · REDUCE · SELL · WAIT` grouped into intent families (Entry/Observe/Maintain/Risk-off). Defends nuance preservation. |

**Master locks 4 verbs.** Reasoning: M1, Public, Composer empirically suffered verb sprawl; the smaller surface forces the decision sentence to do the work. Codex's `WATCH` semantics ("thesis forming around a trigger") are subsumed by the **lifecycle pill** (locked UX-8) which already encodes thesis state. Document Codex's 7-verb governed taxonomy as the alternate approach for usability re-test in Phase 10G+.

### Dispute D2 — Confidence representation

| Position | Models | Mechanism |
|----------|--------|-----------|
| **4 named tiers + dot glyph + freshness state + event expiry** | Sonnet R3 + Opus R3 (synthesis), **MASTER DEFAULT** | Tier names + visual glyph + explicit timestamp + named expiry condition. Auto-demotion happens silently in backend; user sees tier movement, not countdown. |
| Bands + sub-bands | Codex R3 | `High/Moderate/Low/Forming` + `Fresh/Aging/Stale/Expired` + 4 sub-scores in drawer. |
| Confluence Matrix (F/T/M) | Gemini R3 | 2×2 with three pillars lit per cell. |

**Master locks tiers + glyph + freshness + expiry.** Codex's `freshnessState` vocabulary (`Fresh · Aging · Stale · Expired`) is **adopted as the second axis** alongside the tier names. Gemini's F/T/M lives in the reasoning drawer as Evidence Pillars, not on the card.

**Final tier set:** `Forming · Working · Confirmed · Conviction`
**Final glyph set:** `●○○○ · ●●○○ · ●●●○ · ●●●●`
**Final freshness set:** `Fresh · Aging · Stale · Expired`
**Decay rule:** transition `Fresh → Aging → Stale → Expired` on evidence-update absence (windows: 24h / 72h / 6d). On `Stale`, tier auto-demotes one level. Logged in decision history.

### Dispute D3 — Cockpit beginner gating

| Position | Models | Mechanism |
|----------|--------|-----------|
| **24h consideration window** | Sonnet R3, **MASTER DEFAULT for default-mode** | Tap verb → engine logs intent → paper-trade lands next session. Friction-as-time. |
| Plan-a-trade button | Opus R1, **MASTER DEFAULT for Pro-mode** | Levels collapsed behind explicit click. Friction-as-click. |
| No gate | Codex R3 | Levels visible by default; "trust users." |

**Master locks** 24h window for default-mode users; button for Pro-mode users (toggle in settings). Document Codex's anti-paternalism dissent.

### Dispute D4 — Color saturation ceiling

| Position | Models | Value |
|----------|--------|-------|
| **≤50% saturation** | Sonnet R3, Opus R3, **MASTER DEFAULT** | Conviction-bearing color clamped. |
| Material Indigo `#3F51B5` (~70%) | Gemini R1/R2/R3 | "Quiet Luxury" / "Institutional Minimalist" interpretation. |
| Unspecified | Codex | "Calm research palette." |

**Master locks saturation ≤50%.** Reject `#3F51B5` as Material 2014 cosplay (Sonnet R2 critique landed). Accent uses `#7B8CFF` at ≤50% saturation, applied as 1px left border on `Confirmed`+ cards only.

### Dispute D5 — Decision Diet enforcement

| Position | Models | Mechanism |
|----------|--------|-----------|
| **Reflection nudge in Cockpit, not interstitial blocker** | Sonnet R3 conceded, Codex R3, **MASTER DEFAULT** | Logged + surfaced as Cockpit reflection card after 4 cards/24h opened. |
| Hard interstitial | Sonnet R1 (deprecated) | Block research surface after 8 cards. |

**Master locks reflection-nudge** for paper-trading phase. Real-money phase may add the harder interstitial. Threshold: 4 cards/24h default-mode, 8 cards/24h Pro-mode.

---

## Section 3 — Conviction language system

### 3.1 The four verbs

| Verb | Means | Visual |
|------|-------|--------|
| **OPEN** | Initiate or scale a position. Single-day or accumulation, depending on decision-sentence context. | Pill, top-left of card. 11px uppercase. Color: `#9CA3AF` (single neutral). Tracking +0.08em. |
| **HOLD** | Position correct, no new capital favored. Thesis intact. Used for both held positions AND for "do not chase" recommendations on names where movement might prompt action. | Same chrome. |
| **TRIM** | Reduce exposure but keep core. Risk/reward weakening, target partially hit, or rebalance. | Same chrome. |
| **EXIT** | Full close. Thesis broken, target fully hit, invalidation triggered, or risk dominant. | Same chrome. |

Banned vocabulary on cards: `BUY · SELL · ACCUMULATE · WATCH · WAIT · REDUCE · NIBBLE · RIDE · PASS · DEFER · INITIATE · MAINTAIN · MONITOR`. The verb namespace is closed; PR review must reject any new verb.

### 3.2 Verb visual treatment (locked)

```css
.verb-pill {
  position: top-left of card;
  font-family: var(--ui-sans);  /* Inter or system */
  font-weight: 600;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #9CA3AF;
  background: transparent;
  border: 1px solid #1F2329;
  padding: 4px 8px;
  border-radius: 0;  /* sharp */
}
```

Verb is a **label of state**, not a button. Does not navigate. Does not trigger orders (read-only research). The Cockpit page handles all interaction.

### 3.3 The decision sentence (the actual headline)

Every card carries one decision sentence. Spec:
- **Length:** 100–140 chars. Single line at default 720px width.
- **Size:** 18px on the card.
- **Tone:** active voice, present tense, declarative. "Add through $172 while data-center margin expansion holds."
- **Banned:** "AI thinks", "we believe", "should consider", "may want to" (hedging language). State the recommendation cleanly.
- **Required:** at least one numeric anchor (price, %, level) AND at least one condition (while/if/until/given).

This sentence is what carries the intelligence. The verb is just a label. The thesis triplet (Driver/Counter/Catalyst) supports it below.

---

## Section 4 — Confidence system (final design)

### 4.1 The two-axis model

Every actionable card carries **two axes** of confidence, displayed side-by-side:

**Axis 1: Strength tier (4 named levels)**

| Tier | Glyph | Meaning | Renderability |
|------|-------|---------|---------------|
| `Forming` | `●○○○` | Thesis exists but evidence is sparse. | Hidden from hero; visible in `/ideas`. |
| `Working` | `●●○○` | Multiple supporting signals; thesis credible but not fully confirmed. | Visible in hero if no `Confirmed`+ available. |
| `Confirmed` | `●●●○` | Thesis well-supported with credible bear case present. | First-class hero. |
| `Conviction` | `●●●●` | High-evidence thesis with credible counter and active monitoring. | Hero, capped (see safeguards). |

**Axis 2: Freshness state (4 named levels)**

| State | Trigger | Visual treatment |
|-------|---------|------------------|
| `Fresh` | Evidence updated <24h | Full opacity. |
| `Aging` | 24h–72h | 0.95 opacity. |
| `Stale` | 72h–6d | 0.85 opacity + auto-demote tier one level. |
| `Expired` | >6d OR named expiry condition met | Card hides from hero; demoted to `Working` minimum. |

### 4.2 Card-level display

```
[OPEN]                                  [●●●○ Confirmed · Fresh]
NVDA · NVIDIA · Semis cycle continuation
Last reviewed 14h ago · Valid until earnings May 21 or close < $462
```

Three lines: verb pill + tier-glyph-state on first row. Ticker + thesis name on second row. Freshness timestamp + expiry condition on third row. Numeric backing scores live in the drawer for power users.

### 4.3 What is banned

- `0.82` and any other numeric probability on the card surface.
- Stars (Yelp).
- Rings with progress fills (fitness app).
- F/T/M segmented bar as the primary glyph (engineering vocabulary; lives in drawer only).
- `Forming` (or anything below) ever showing in hero.
- Confidence inflation: `Conviction` cards capped at 4% of all cards in any rolling 30-day window. Alert fires if exceeded.

---

## Section 5 — ActionCard contract (refuses-to-render)

### 5.1 Required schema

```ts
type ActionCard = {
  verb: "OPEN" | "HOLD" | "TRIM" | "EXIT";
  ticker: string;
  thesisName: string;                 // e.g., "Semis cycle continuation"
  decisionSentence: string;           // 100–140 chars, declarative
  confidenceTier: "Forming" | "Working" | "Confirmed" | "Conviction";
  freshnessState: "Fresh" | "Aging" | "Stale" | "Expired";
  lastReviewedAt: string;             // ISO timestamp
  expiryCondition: string;            // human-readable, e.g., "earnings May 21 or close < $462"
  invalidation: string;               // structural rule, e.g., "Close below $158 on > 1.4× ADV"
  thesis: {
    driver: string;                   // ~80 words, bull case
    counter: string;                  // ~80 words, bear case (REQUIRED for Confirmed+)
    catalyst: string;                 // single line: what would change conviction
  };
  target: { entry: string; t1?: string; t2?: string; t3?: string };
  horizon: string;                    // e.g., "6-18 months"
  bearCaseGlyph: boolean;             // small ⚖ icon next to verb
  snoozeOptions: ["24h", "1w", "forever"];
  riskTags: string[];                 // e.g., ["valuation risk", "AI capex risk"]
};
```

### 5.2 Refuses-to-render conditions

The composer **MUST throw a build-time error** (not a runtime fallback) if any of:

- `verb` is missing or not in the locked 4-verb set.
- `decisionSentence` is missing, < 80 chars, or > 200 chars.
- `invalidation` is missing or contains the string "TBD" / "varies".
- `confidenceTier` is `Confirmed`+ AND `thesis.counter` is missing or < 50 chars.
- `expiryCondition` is missing.
- `lastReviewedAt` is missing or > 7 days old without re-review.
- `horizon` is missing.
- `target.t1` is shown without `target.entry` AND `invalidation` both present.

### 5.3 Visual hierarchy (top to bottom)

```
[OPEN]                              [●●●○ Confirmed · Fresh]
NVDA · NVIDIA · Semis cycle continuation
Last reviewed 14h ago · Valid until earnings May 21 or close < $462
─────────────────────────────────────────────────────────────────
Add through $172 while data-center margin expansion holds and       ← decision sentence
hyperscaler capex revisions stay above +18% YoY.

INVALIDATION                                                        ← FIRST (above target)
Close below $158 on > 1.4× ADV, or hyperscaler capex revision
below +18% YoY.

DRIVER · COUNTER · CATALYST                                         ← thesis triplet
Driver: [~80 words bull case]
Counter: [~80 words bear case, equal visual weight]
Catalyst: [single line: what would change conviction faster]

Target zone $208–$222   ·   Hold horizon ~6 weeks                   ← LAST
─────────────────────────────────────────────────────────────────
[ Reasoning ↓ ]                          [ ⚖ Bear ]   [ Snooze ]
```

Width: 720px stream / 480px compact. Background `#0F1115`. Border `1px solid #1F2329`. No gradients on the card itself. No glassmorphism. No box-shadow > 4px.

---

## Section 6 — Overview hero rules

### 6.1 Structure (3 sections, vertical)

```
Today                                                Friday May 9
─────────────────────────────────────────────────────────────────

Market regime · Selective, valuation-sensitive
Add only where earnings durability offsets valuation risk.

Your active positions                          3 holding · 1 decaying
[ ActionCard: HOLD MSFT  ]
[ ActionCard: TRIM TSLA  ]
[ ActionCard: EXIT META  ]

What the engine believes more strongly         2 promoted since Friday
[ ActionCard: OPEN NVDA ]
[ ActionCard: OPEN COST ]
```

### 6.2 Hero invariants

- **Section 1 — Regime ribbon:** one line. Market stance + one supporting clause. No chart.
- **Section 2 — Your active positions:** existing holdings outrank new ideas. Always rendered (even if empty: "No active positions today.").
- **Section 3 — What the engine believes more strongly:** new promotions since last visit, capped at 2.
- **Cap total hero cards at 5; cap thesis cards at 3.** Surplus goes to `/ideas`.
- **Quiet day state (locked copy, Gemini):** *"Market regime: noisy. Maintaining existing positions. No new entries recommended."*
- **No infinite scroll.** Hero ends.
- **Banned vocabulary:** "AI found", "moves", "today's picks", "hot", "high-confidence" used as a hero adjective, all-caps shouting.

---

## Section 7 — Research Cockpit (`/stock/:ticker`)

### 7.1 First-paint hierarchy (above fold, 1080px viewport)

| Section | Height | Content |
|---------|--------|---------|
| **S1. Header band** | 96px | Ticker · company name · neutral price (no green/red until > 5s hover) · market cap chip · sector chip |
| **S2. Conviction strip** | 64px | Verb · tier glyph · freshness state · last reviewed · invalidation distance ("Currently $20 from invalidation") |
| **S3. Thesis triplet (two-column)** | 280px | Driver (left) \| Counter (right). Equal visual weight. Catalyst as single line below. |
| **S4. Action plan** | 160px | Default-mode: collapsed behind 24h consideration window. Pro-mode: visible. Contains entry zone, T1/T2/T3 targets, stops, invalidation conditions. |

### 7.2 Below fold (sections in order)

5. **Price chart** — 1Y default, with invalidation drawn as horizontal line that moves with thesis updates.
6. **Financials & flow** — compact 6-card grid showing only the metrics the thesis references. Direction louder than number ("Margins improving" > "37.2%").
7. **News & filings** — AI-tagged feed grouped as `Supports / Pressures / Neutral` (Codex R3 framing). Includes "Counter-evidence first" toggle (Opus R1) that re-orders bear-first.
8. **Decision log per ticker** — chronological list of every recommendation change on this name, including misses. ("May 2: Working → Confirmed because Q1 hyperscaler capex came in +22% vs 18% expected. Apr 18: Confirmed → Working because [reason].")
9. **Reasoning drawer** — see Section 9.

### 7.3 What makes a user trust enough to act

Three load-bearing trust mechanisms, all required:

1. **Bear case present and credible** — composer-level invariant L4.
2. **Decision log honest about misses** — visible track record per ticker.
3. **24h consideration window for beginners** — friction-as-time.

---

## Section 8 — Options UX (`OptionsStructureCard`)

### 8.1 Verb namespace (separate from equity)

Top-level verb is **`STRUCTURE`** with sub-label naming the strategy intent:

```
STRUCTURE · Defined-risk bullish · NVDA
─────────────────────────────────────────────
Long call vertical · $175 / $190 · Jun 21
─────────────────────────────────────────────
MAX LOSS  $4.20         ← named first
Max gain  $10.80
Breakeven $179.20
IV rank   42
POP est.  38%
─────────────────────────────────────────────
Linked to NVDA equity thesis: "Semis cycle continuation"
[ Risk graph - always visible, never collapsed ]
```

Sub-label vocabulary (closed): `defined-risk bullish · defined-risk bearish · hedge · income (covered) · advanced (premium-sell) · advanced (naked directional)`.

### 8.2 Hard rules (engineering invariants)

1. **`STRUCTURE` is the only top-level options verb.** `BUY CALL`, `BUY PUT`, `SELL PREMIUM`, `ROLL` etc. exist only inside the structure plan, not as badges.
2. **Defined-risk only by default.** Naked premium-sell hidden behind explicit account-level toggle.
3. **Max loss named first** in every options card. Larger font than max gain.
4. **POP visible adjacent to reward/risk.**
5. **No 0DTE on the hero.**
6. **Risk graph always visible.** Never collapsed.
7. **Every options card linked to an underlying equity thesis.** No standalone options recommendations.
8. **Three-screen primer interrupts the first options card per user.** Acknowledgement required.
9. **Risk dot is the only color-coded element in the system.** Only ever amber or red. Never green.
10. **No "Buy now" CTA.** Only `[ See plan ]` opens the structure with the Cockpit format adapted.

---

## Section 9 — AI reasoning drawer

### 9.1 Single scroll surface (no tabs)

Tabs hide the bear case behind a click. Forced past the user's eye.

### 9.2 Sections (top to bottom)

1. **Plain-language thesis recap** — 60 words, paragraph form.
2. **Driver / Counter / Catalyst with sub-confidence per claim** — bulleted, each one sentence, with `●●●○`-style sub-glyphs.
3. **What changed since last review** — "Promoted from Working → Confirmed on May 2 because hyperscaler capex came in at +22% vs 18% expected."
4. **Compared candidates** — "AI considered AMD, TSM, MU as alternatives. Picked NVDA because [reason]." Builds trust through visible selectivity.
5. **My pattern with this AI** — user-specific reflection. "Last 6 NVDA recommendations, you acted on 3. 2 hit T1, 1 stopped out, 3 you skipped (which would have hit T1 in 2 of 3 cases)."
6. **Calibration line** — "Current `Confirmed` tier hit rate: 60% (rolling 90d). Below 70% target."
7. **Engine version + last retrain date** — tiny grey footer. "Engine v2.3.1 · last retrained Apr 28."

### 9.3 Hidden by default (require explicit "Show technical detail" tap)

Factor weights, model class, F/T/M decomposition (Gemini R3), backtest stats, IC decay curves, SHAP values, prompt scaffolding, token traces, internal routing, raw model deliberation, fake-precise probabilities to 4 decimals, "Powered by [model]" branding, marketing language.

### 9.4 Layer-3 escape hatch

Layer-3 (`?view=working`) still exists for engineers — separate concern, locked in UX-9. The reasoning drawer is the *investor* surface; Layer-3 is the *engineer* surface.

---

## Section 10 — Trust safeguards (13 engineering invariants)

All schema-enforced. Refuses-to-render or refuses-to-build. Not designer convention. Each carries a unit test.

| # | Invariant | Enforcement layer | Originator |
|---|-----------|-------------------|------------|
| S1 | No actionable card without `invalidation` field. | Schema | Codex + Sonnet |
| S2 | No actionable card without `horizon`. | Schema | Codex + Sonnet |
| S3 | No `Confirmed`+ tier without `thesis.counter` ≥ 50 chars (bear case). | Composer | Opus |
| S4 | `Invalidation` rendered visually before `target` on every card. | Component | Sonnet |
| S5 | Hero capped at 3 thesis cards, 5 total cards. | Page composer | Opus + Codex |
| S6 | `Conviction` tier capped at 4% of all cards in rolling 30-day window. | Server-side rate limit | Sonnet |
| S7 | Confidence half-life enforced via auto-demotion on `Stale` freshness. | Backend | Sonnet + Opus |
| S8 | Color saturation ≤ 50% on any conviction-bearing color. | Token system + lint | Sonnet (originator) + Opus |
| S9 | No motion > 240ms or > 8px translation; no flashing/pulsing/countdowns/confetti. | CSS lint + component review | Sonnet + Codex |
| S10 | Weekly Calibration card shows tier hit rates publicly to user. | Cockpit composer | Sonnet |
| S11 | Snooze affordance present on every thesis card (24h/1w/forever options). | Schema | Opus |
| S12 | Action ledger per ticker visible on Cockpit; includes misses. | Cockpit composer | Opus + Sonnet |
| S13 | Decision Diet: at 4 cards/24h opened (default-mode) / 8 (Pro-mode), Cockpit reflection card surfaces. Logged, not blocking. | Behavior layer | Sonnet + Codex |

Bonus: **L11 above** (visual dignity for HOLD/WAIT-equivalent affordances) is enforced via design-system contract on `Card` and `EmptyState` components.

---

## Section 11 — Visual conviction system

### 11.1 Tokens (locked)

```css
:root {
  /* Backgrounds (3 depth levels) */
  --ux10-bg-page:    #0B0D10;
  --ux10-bg-card:    #0F1115;
  --ux10-bg-elev:    #13161B;

  /* Text (3 levels) */
  --ux10-fg-primary:   #F4F5F7;
  --ux10-fg-secondary: #9CA3AF;
  --ux10-fg-tertiary:  #6B7280;

  /* Borders */
  --ux10-border-card:  #1F2329;
  --ux10-border-strong: #2A2F37;

  /* Conviction tint (the only "color" on conviction cards) */
  --ux10-conviction-tint: hsla(228, 50%, 70%, 0.08);  /* 8% opacity, 50% saturation */

  /* Risk red — desaturated */
  --ux10-risk:        #C24A4A;

  /* Amber — only ever for risk dot */
  --ux10-amber:       #B88A2A;

  /* Type sizes (4 only) */
  --ux10-fs-h1:       24px;
  --ux10-fs-h2:       16px;
  --ux10-fs-body:     14px;
  --ux10-fs-meta:     11px;

  /* Type families */
  --ux10-font-sans:   "Inter", system-ui, -apple-system, sans-serif;
  --ux10-font-mono:   "iA Writer Mono S", "SF Mono", Menlo, monospace;
}
```

### 11.2 Component contracts

- **Verb pill:** 11px uppercase, single neutral color `--ux10-fg-secondary`. Sharp 0px border-radius. 1px border.
- **Tier glyph:** dot row `●○○○` through `●●●●`. Single color. No animation on first paint of glyph itself (only the card reveal).
- **Confidence tint:** applied as `border-left: 1px solid var(--ux10-conviction-tint)` on `Confirmed`+ cards only. **Never as background fill.**
- **Stale card visual:** `opacity: 0.85; filter: saturate(0.6);`. Auto-applied when `freshnessState === "Stale"`.
- **Risk dot:** small filled circle. Three sizes (small=defined risk, medium=naked premium, large=naked directional). Color limited to `--ux10-amber` or `--ux10-risk`.

### 11.3 What survives, what dies

**Survives:**
- Dot glyphs (●●●○).
- Verb labels (monochrome, never color-coded).
- Single-layer cards.
- 8px grid.
- Three depth levels.
- Four-size typography lock.
- 1px left-border conviction tint at low saturation.

**Dies:**
- Confidence rings (fitness-app vocabulary; Codex critique landed).
- Conviction bars (read as "loading" or "battery low").
- Page-level conviction tint backgrounds (mood-ring failure).
- Score glyphs as decoration.
- Gradients on cards.
- Glassmorphism.
- Material Indigo `#3F51B5` (Material 2014 cosplay).
- Casino green/red (high saturation).
- Pure green (`#00FF00`), neon pink, electric blue.
- All-caps shouting headlines.
- Confetti, fireworks, haptics on profitable trades.

---

## Section 12 — Anti-pattern lock list

These are banned. PR review must reject. Lint rules where automatable.

| Anti-pattern | Reason | Banned by |
|--------------|--------|-----------|
| Numeric confidence on primary surface (`0.82`) | Fake precision. | All 4, R1+ |
| BUY/SELL verbs on cards | Order-ticket vocabulary on read-only research; bait-and-switch. | Sonnet R1 |
| `WATCH` / `WAIT` as standalone verbs | No-action verbs are signal padding. | Sonnet R3, Master |
| "AI FOUND N MOVES TODAY" hero framing | Casino-coded across 4 axes. | Opus R1, locked |
| Daily-action framing ("Today's picks", "Hot", "Found") | Conditions daily-check addiction. | All 4 |
| Hero with > 3 thesis cards | Selectivity prevents picks-app drift. | Sonnet R3 + Codex R3 |
| Target on collapsed card without paired downside + invalidation | Upside anchoring. | Sonnet, Codex, master |
| Verb without invalidation | Actionability without falsifiability = casino. | Codex S1 |
| Verb without horizon | Tweet-energy. | Codex S2 |
| Confidence with no decay | Stale claims look fresh. | Sonnet R1 |
| Visible countdown clocks | Casino mechanic. | Opus R2, locked |
| F/T/M segmented bar as primary glyph | Engineering vocabulary on user surface. | Opus R2 |
| Confidence rings (progress fills) | Fitness-app vocabulary. | Codex R2 |
| Glassmorphism, gradient washes on cards | Decorative — distracts from data. | Sonnet R3, master |
| Material Indigo `#3F51B5` | Material 2014 cosplay. | Sonnet R2 |
| Conviction tint as background fill | Mood-ring effect, confuses signal. | Opus R2 |
| Color saturation > 50% on conviction-bearing color | Casino tell. | Sonnet R3 |
| Motion > 240ms or > 8px translation | Casino motion. | Sonnet R1 |
| Flashing, pulsing, confetti, haptics on profit | Reinforces dopamine loop. | All 4 |
| Trending ticker rail / "what's hot" | Hype contagion. | Opus R1 |
| Suggested-question chips, chat dock, AI orb | UX-9 lock, still in force. | UX-9 carry-forward |
| "Powered by [GPT/Claude/etc]" badges | Wrong trust frame. | Opus R1 |
| Marketing language in reasoning drawer | Drawer is committee-memo, not pitch deck. | Codex R3 |
| Tab-hidden bear case in drawer | Hides counter behind a click. | Sonnet R2, Master |
| Standalone `BUY CALL` / `SELL PUT` options badges | WSB UI. | All 4 |
| Naked options on default surfaces | Beginner protection. | Opus R1 |
| 0DTE on hero | Banned product surface. | Opus R1 |
| Confidence inflation > 4% Conviction in 30d | Tier devaluation. | Sonnet R1 |
| Adding new verbs without master doc revision | Verb gravity defense. | Sonnet R3 |

---

## Section 13 — Implementation phasing

Same parallel-route validation pattern as UX-9 Phase 9D. Default `/overview` does not change until 10I.

| Phase | Scope | Files | Risk |
|-------|-------|-------|------|
| **10A** | Tokens + verb pill component + tier glyph + freshness chip + bear-case-mandated composer rejection (build-time error) | `apps/web/src/lib/copilot/ux10_tokens.css`, `VerbPill.tsx`, `TierGlyph.tsx`, `FreshnessChip.tsx`, `apps/api/src/composers/conviction_card.py` | Low |
| **10B** | `ActionCard` component (refuses-to-render schema validation) + `OptionsStructureCard` | `ActionCard.tsx`, `OptionsStructureCard.tsx` + composer fixtures | Low |
| **10C** | Hero refactor — 3-section structure, Active Positions + Promotions blocks | `ConvictionHero.tsx`, `compose_hero_conviction.ts` | Low |
| **10D** | Mount at `/overview?view=conviction` (parallel route, isolated) | `OverviewRouteSwitch.tsx` (additive branch) | Low — additive |
| **10E** | Reasoning drawer — single-scroll, all 7 sections, with calibration + compared candidates + my pattern | `ReasoningDrawer.tsx` + 7 section primitives | Medium |
| **10F** | Research Cockpit page (`/stock/:ticker?view=conviction`) — 5 above-fold sections + 4 below-fold | `CockpitPage.tsx`, `CockpitConvictionStrip.tsx`, `ThesisTriplet.tsx`, `DecisionLog.tsx` | Medium |
| **10G** | Wire engine — replace fixtures with composers reading `paper_position`, `recommendation`, `regime_snapshot`, `paper_summary`, `factor_snapshot` | composer rewrites + API contract additions | High — backend contract |
| **10H** | Trust safeguard enforcement layer — schema validators with build-time errors; lint rules for tokens; weekly Calibration card composer | `composers/safeguards/`, `lints/conviction_lint.ts` | Medium |
| **10I** | Cutover — default `/overview` → conviction view. Stream becomes `?view=stream` archive. Default UX-8B PRESSURED proof archived as `?view=condition`. | `OverviewRouteSwitch.tsx` default branch swap | High — visible default change |

**Validation gates between phases:**
- After 10D: user emotional validation at `/overview?view=conviction` with PROOF fixtures (ETA review with Kunal).
- After 10F: full Cockpit usability validation against 3 representative tickers (NVDA, AAPL, KO).
- After 10G: real-data validation at full cycle (overnight ingest → conviction surfaces refresh).
- Before 10I: 1-week staging window with both views available; user toggles default.

---

## Section 14 — Engineering API contract additions (10G)

The composer must produce ActionCard data shaped to the schema in §5.1. Backend additions required:

- `paper_position` — extend with `current_thesis_id`, `current_verb`, `last_recommendation_changed_at`.
- `recommendation` (existing) — extend with `confidence_tier`, `freshness_state`, `expiry_condition`, `bear_case_text`, `decision_sentence`.
- `decision_log` (NEW table) — `(id, ticker, recommendation_id, change_reason, changed_at, prev_tier, next_tier, prev_verb, next_verb, evidence_ref)`.
- `tier_calibration` (NEW table) — `(tier, hit_rate_90d, target_rate, last_computed_at)` recomputed daily.
- `compared_candidates` (NEW table) — `(recommendation_id, alternate_ticker, reason_not_picked)`.
- `user_pattern` (NEW or virtual table) — per-user view of `recommendation` + acted/skipped + outcome.

These fit into the existing FastAPI/SQLAlchemy schema; migrations land in 10G.

---

## Section 15 — Debate provenance

This master is the synthesis of a 3-round adversarial debate held 2026-05-09 between four models per `/octo:debate` skill:

| Model | R1 words | R2 words | R3 words |
|-------|----------|----------|----------|
| Gemini | 1,782 | 1,976 | 1,654 |
| Codex (gpt-5.5) | ~5,200 (post-prompt-echo) | ~3,300 (post-echo) | ~2,500 (post-echo) |
| Sonnet 4.6 (Agent) | 2,955 | 2,996 | 2,244 |
| Claude Opus 4.7 (moderator) | 3,112 | 2,404 | 2,047 |

**Total ~32,000 words of independent argumentation.**

Source files:
- Brief: `docs/research/debates/UX_10_conviction/BRIEF.md`
- R1: `docs/research/debates/UX_10_conviction/round1/{gemini,codex,sonnet,opus}_r1.md`
- R2: `docs/research/debates/UX_10_conviction/round2/{gemini,codex,sonnet,opus}_r2.md`
- R3: `docs/research/debates/UX_10_conviction/round3/{gemini,codex,sonnet,opus}_r3.md`

Key cross-model concessions tracked above in Section 1 (universal locks) and Section 2 (documented disputes with master defaults).

**Single most load-bearing decision in the entire master:** the **bear-case-mandated composer-level invariant (L4 / S3)**. One confidently-wrong call on a high-profile ticker would otherwise destroy the "AI investment strategist" framing. With the bear case shown before the user acted, the loss reads as normal variance. Without it, the product is dead.

---

## Section 16 — What this master deliberately does NOT lock

- Specific copy for AI READ sentences beyond format constraints (composer template, A/B testable).
- Specific behavior of the live-data subscription layer (post-10G, post-launch).
- Mobile breakpoint specifics below 480px (Phase 10G+ refinement).
- Onboarding flow / first-run education for the 4-verb / 4-tier vocabulary (Phase 10E surface, deferred design).
- Real-money execution UX (currently paper trading only — separate future phase).
- Crypto / forex / commodities surfaces (roadmap; UX-10 vocabulary should extend cleanly but no specific design here).

These are deliberate omissions, not oversights. Future PMs may extend.

---

**End of master. Lock as `docs/research/UX_10_CONVICTION_ENGINE.md`. Do not rewrite without re-running the 4-way debate.**
