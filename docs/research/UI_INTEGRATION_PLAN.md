# Phase L UI Integration Plan

**Status**: Plan only. NO implementation yet.
**Date**: 2026-05-18 (Day 12)
**Scope**: How the validated reasoning substrate surfaces in the WebUI carefully and truthfully.

---

## 1. Current WebUI audit

### Routes that exist today

Default landing: `/` → redirects to `/overview` → `OverviewRouteSwitch`
which defaults to `PicksPage` (BUY/SELL grid + click-into-modal).

| Route | Page | Audience |
|-------|------|----------|
| `/overview` | `PicksPage` (default) | Novice — landing |
| `/overview?view=working` | `Overview.tsx` (1350 LOC, elite terminal) | Operator |
| `/action-queue` | `ActionQueuePage` | Novice |
| `/portfolio` | `PortfolioRouteSwitch` | Mixed |
| `/portfolio/intel` | `PortfolioIntelligencePage` | Mixed |
| `/decisions` | `Decisions.tsx` (1233 LOC, 3-col workstation) | Operator/Power |
| `/events` | `EventsResearchPage` | Mixed |
| `/strategies` | `StrategiesPage` | Operator |
| `/signal-lab` | `SignalLabPage` | Operator |
| `/research`, `/alpha-lab`, `/ml-lab` | Research tools | Operator |
| `/ops`, `/risk`, `/agents` | Operator-only |
| `/options/*` | 20+ options-specific pages | Operator |

### Where AI explanation already lives

- `PickModal.tsx` — currently shows engine `rationale` text (freeform engine output) under "Why" sections in the novice modal. **This is the primary surface where reasoning belongs.**
- `Decisions.tsx` — already has `live`/`replay` filter. Column 2 is "Decision Detail" with a `usePaperTrades`/`useDecision` hook. **This is the operator surface where reasoning belongs.**
- `Briefing.tsx` — has `useBriefingNarrative` (different system, separate from Phase L). Out of scope.

### Reasoning client lib

**Does not exist.** No `lib/reasoning/*` files. Backend endpoints (`/api/v2/decisions/{id}/reasoning`, `/api/v2/envelope-generation/{health,quality,gaps}`) have no TypeScript client yet.

---

## 2. Where reasoning SHOULD appear

### Primary surfaces (must integrate)

1. **`PickModal.tsx`** — novice-facing pick detail. Today shows engine `rationale` string (potentially freeform LLM prose — danger zone). Replace with Phase L `setup` / `thesis` / `uncertainty` from the deterministic renderer.

2. **`Decisions.tsx` Column 2** — operator-facing Decision Detail. The page already structures around it. Add an envelope card with rendered output. Currently shows engine `reason` strings from `paper_trade.reason` (freeform — same danger).

### Secondary surfaces (could integrate)

3. **`ActionQueuePage`** — if any pending actions are explained, use the same envelope card. Likely a short row-level snippet (1 line setup).

4. **`Ops.tsx`** — operator-only. Add an envelope-generation coverage panel sourcing `/api/v2/envelope-generation/health` and `/quality` endpoints.

### Surfaces that should STAY UNTOUCHED

| Surface | Why untouched |
|---------|---------------|
| All `/options/*` pages | Options reasoning is a separate Phase L follow-up; envelope generator supports `asset_class='options'` but options trades don't yet route through paper_trade |
| `/alpha-lab`, `/ml-lab`, `/research`, `/signal-lab` | Research surfaces; envelope is an engine artifact not a research output |
| `/agents` | Agent workflows — orthogonal |
| `/risk` | Risk dashboard — no envelope role |
| `Briefing.tsx` | Has its own narrative system (briefing_narrative router) |
| Copilot views (Stream/Conviction/Interactive/Living/Legacy) | These are visual hypotheses behind ?view= params; do not touch them in Phase UI-1 |
| `Performance.tsx`, `PortfolioTerminal.tsx` | Numeric surfaces; reasoning is per-decision, not per-portfolio |
| `Asset.tsx` | Asset deep-dive — could be a Phase UI-2 candidate |

---

## 3. Truth banners — global slot

Truth banners (8 locked causes from D2.5) must be visible globally
when their priority warrants. **Recommended slot**: top of `Shell`
component, above page content. Single banner at a time per the
"one-banner-per-surface" rule.

| Banner cause | Where it fires | When user sees it |
|--------------|---------------|---------------------|
| `engine_error` | global | P0 — every page |
| `stale_data_universe_wide` | global | P1 — every page |
| `pre_canary_options` | options surfaces only | P2 — only on `/options/*` |
| `engine_dormant` | live surfaces | P2 — Today/Decisions |
| `incomplete_lifecycle` | per surface | P3 — when a surface is incomplete |
| `stale_data_single_name` | per asset/position | P3 — Asset page, position rows |
| `operator_intervention_active` | global | P3 — every page |
| `post_loss_position` | per position | P4 — position-level only |

Backend endpoint needed: `GET /api/v2/system-state?surface=<surface>` (D2.5 truth_banners.py exists but no HTTP route yet — that's a **prerequisite endpoint** for UI work).

---

## 4. State labels — small chip slot

State labels (6 locked substates from D2.5) attach to a small chip,
probably in the Shell header next to the system status indicator.

```
[Live · data lagging]   [Observing]   [Learning]   [Experimental]
```

Surfaces map to substates per `resolver.py`:
- Today / Decisions / Portfolio → `live_fresh` / `live_stale` / `live_dormant` / `observing`
- Concepts / Playbooks → `learning`
- Options preview surfaces → `experimental`

Same backend endpoint as truth banners.

---

## 5. Envelope rendering card — the central component

The single most important new UI primitive.

```
┌─ ReasoningCard ────────────────────────────────┐
│ [Live]                                          │  ← source pill (live/replay/operator_manual)
│                                                 │
│ Continuation inside macro tailwind on 3-week    │  ← rendered.setup
│ momentum positive. Exits if the regime backdrop │
│ the trade depended on has broken.               │
│                                                 │
│ Expectation: price moves higher over the next   │  ← rendered.thesis
│ 1-3 weeks.                                      │
│                                                 │
│ ⚠ We've only seen this setup a handful of      │  ← uncertainty markers, ≤3
│   times — the track record is thin.             │
│                                                 │
│ ┌── Show structured data ─────────────────┐    │  ← collapsible operator detail
│ │ skeleton: regime_aligned_continuation     │   │     hidden in novice mode
│ │ trigger:  momentum_3w_positive             │   │
│ │ regime:   macro_tailwind                   │   │
│ │ invalid:  regime_break                     │   │
│ │ hash:     22121ef8...                       │   │
│ └────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### Rules

- **All text** comes from the deterministic renderer (`setup`, `thesis`, `uncertainty[]`). Frontend NEVER paraphrases.
- **Markers display verbatim** from the locked copy (D3.5 `MARKER_COPY` dict). No truncation.
- **Empty state**: when API returns 404, card shows:
  ```
  ┌──────────────────────────────────────────────┐
  │ Part of this is still being built            │
  │                                              │
  │ The AI didn't produce structured reasoning   │
  │ for this decision. We won't substitute one.  │
  └──────────────────────────────────────────────┘
  ```
  (Sourced from `incomplete_lifecycle` banner copy.)
- **No confidence widgets.** No percentage gauges. No "AI is X% sure" — Phase L explicitly forbids this framing.

---

## 6. Replay/live source visibility

Already partially exposed via `Decisions.tsx` filter (Live/Replay).
Per-envelope, the source pill at the top of the ReasoningCard makes
it always visible. **Color-neutral** pills (no green=live, red=replay
heuristics) — both are valid states.

Per-trade row in tables: a single-letter chip `L` / `R` / `O` /
`B` next to the timestamp (live / replay / operator_manual / backfill).

---

## 7. Operator coverage / quality dashboards

A new `Ops.tsx` panel sourcing the existing JSON endpoints:

| Endpoint | Panel section |
|----------|---------------|
| `/api/v2/envelope-generation/health` | Coverage % per day (sparkline + table) |
| `/api/v2/envelope-generation/quality` | Per-skeleton firing rate, marker rate, hash uniqueness |
| `/api/v2/envelope-generation/gaps` | List of trades with no envelope; clickable to Decisions |

Operator-only. Reuses existing `Ops.tsx` layout patterns. No new
visual primitives.

---

## 8. Minimal reasoning timeline / history

Within `Decisions.tsx`, when an asset is selected, show the last N
envelopes for that asset in chronological order. Just stacked
ReasoningCards with timestamps. No fancy timeline visualization.

Backend support: `GET /api/v2/decisions/{paper_trade_id}/reasoning`
already returns one envelope. A new endpoint
`GET /api/v2/assets/{asset_id}/reasoning?limit=N` would be needed
for the timeline — **defer to Phase UI-2**, not UI-1.

---

## 9. Calibration visibility — operator only

The `Quality` endpoint exposes:
- distinct envelope hashes per skeleton (collapse signal)
- marker firing rates
- source distribution

Surface this in `Ops.tsx` as a quality matrix. **Not on novice
surfaces.** Novice users don't benefit from seeing hash-uniqueness
counts.

---

## 10. Phase UI-1 — minimal viable visible integration

**Goal**: every visible AI explanation becomes deterministic-renderer
output. Replace engine `rationale` strings.

### What to build

1. **TypeScript client lib** `apps/web/src/lib/reasoning/` with:
   - `fetchEnvelope(paperTradeId): Promise<EnvelopeResponse | null>`
   - Types matching backend response

2. **`ReasoningCard.tsx`** component (§5 spec above), in `components/decisions/`
   - Variants: novice (no structured detail) / operator (with collapsible)
   - Empty/404 state with incomplete_lifecycle copy
   - Uses tailwind classes already present, no new design tokens

3. **Integrate into `PickModal.tsx`**:
   - Replace the "Why" section's engine `rationale` text with `<ReasoningCard variant="novice" paperTradeId={...} />`
   - If pick has no `paper_trade_id` (not yet acted on), card shows the "no explanation yet" empty state
   - **Remove engine rationale entirely** — do not show both

4. **Integrate into `Decisions.tsx` Column 2**:
   - Replace freeform reason strings with `<ReasoningCard variant="operator" paperTradeId={selected.id} />`
   - Keep the existing factor attribution mini below — it complements

5. **`SourcePill.tsx`** — small badge (Live/Replay/Backfill/Operator), used by `ReasoningCard` and in table rows

### What NOT to build in UI-1

- No truth banner global slot (needs new backend endpoint)
- No state label chips (same)
- No timeline view (needs new backend endpoint)
- No coverage dashboard (defer to UI-2 — operator surface, lower priority)
- No copilot view changes (left in their current visual-hypothesis state)
- No options page changes
- No new visual primitives, no new colors, no new typography

### Success criteria for UI-1

- Every visible AI explanation in the app sourced from the deterministic renderer (zero freeform rationale strings remaining on user-facing surfaces)
- Honest "no explanation available" state is visible somewhere by design (verifiable via D8.5 `/gaps` endpoint — those rows exist)
- Pinned snapshot suite still PASS (UI doesn't affect backend hashes)
- Forbidden-phrase lint extended to scan `apps/web/src/**/*.{ts,tsx}` for the 15 Tier-A phrases

### Effort estimate

3 focused days:
- Day A: client lib + ReasoningCard component + SourcePill + tests
- Day B: PickModal integration + remove engine rationale from PickModal
- Day C: Decisions.tsx integration + lint extension + visual review

---

## 11. Phase UI-2 — expanded insight surfaces

**Goal**: truth banners + state labels + operator dashboards.

### What to build

6. **`GET /api/v2/system-state?surface=...` endpoint** — wraps the existing `resolver.py` + `truth_banners.py` (D2.5). **Backend prereq.**

7. **`TruthBanner.tsx` + Shell integration** — single banner slot above page content, priority-resolved per resolver output

8. **`StateLabelChip.tsx` + Shell header integration** — chip showing current substate (Live / Live · data lagging / Observing / Learning / Experimental)

9. **`GET /api/v2/assets/{asset_id}/reasoning` endpoint** — last N envelopes for an asset (backend prereq for timeline)

10. **`ReasoningTimeline.tsx`** — stacked ReasoningCards by date, slotted into Decisions sidebar OR Asset page

11. **`OpsReasoningPanel.tsx`** — coverage + quality + gaps dashboard in Ops.tsx, sourcing the three existing endpoints

### What NOT to build in UI-2

- No mobile-specific reasoning surfaces
- No reasoning notifications or alerts
- No "AI confidence" indicators of any kind
- No reasoning search / filter UI
- No envelope diff view (cross-asset comparison) — premature

### Effort estimate

4-5 focused days plus backend prerequisite work.

---

## 12. Explicitly NOT to build (ever, or until much later)

| Surface | Why excluded |
|---------|---------------|
| AI "confidence score" widget | Forbidden by Phase L tonality — confidence framing is exactly the Tier-A category |
| "Why this trade is great" promotional copy | Same — Tier-A forbidden |
| Generative narration / paraphrase layer | Defeats the deterministic-renderer guarantee |
| AI chat box | Out of Phase L scope; would require a separate LLM substrate |
| Envelope editing UI | Envelopes are append-only audit artifacts; no edit semantics |
| Marker dismissal / "don't show me uncertainty" | Markers are constitutional honesty; cannot be silenced |
| Visual variety (animations, gradients, multi-color severity) | Cosmetic complexity; doesn't increase truthfulness |
| AI recommendation comparison ("vs analysts") | Distracts from the AI's own structured reasoning |
| Decision Detail sharing / export | Premature; no demand signal |
| Customizable reasoning template | Templates are constitutional; users cannot reshape them |

---

## 13. Constitutional guarantees the UI must preserve

1. **Deterministic renderer is source of truth.** Frontend never paraphrases setup/thesis/uncertainty.
2. **Honest absence respected.** 404 → "Part of this is still being built" — never fall back to engine `rationale` string or other prose.
3. **No frontend-generated prose.** All visible text is either: locked operator copy (vocabulary phrases, marker text, banner copy), structured numeric labels (price, %, dates), or pass-through DB values (asset symbol, trade ID).
4. **No fake confidence indicators.** No percentages, gauges, sliders, or stars representing AI conviction. Conviction is an internal engine concept; not user-facing.
5. **No artificial visual complexity.** Reasoning cards are typography + minimal layout. No animation. No multi-color severity coding beyond what banner priority strictly requires.
6. **Novice-friendly but truthful.** Novice variants HIDE technical structure, but never lie about the underlying data.
7. **Forbidden-phrase lint extends to web/.** Same 15 Tier-A phrases banned everywhere user-facing.
8. **Source visibility is always-on.** A user looking at a Decision Detail should always be able to see whether the envelope came from live trading, replay, backfill, or operator action.

---

## 14. Open questions for the user

- Does PickModal currently show real LLM-generated rationale, or is `rationale` a structured engine output? (Determines how delicate the swap is.)
- Is there an objection to extending the forbidden-phrase lint to `apps/web/src/**/*.tsx`? (Recommended in UI-1.)
- Phase UI-2's `/system-state` endpoint requires resolving WHICH banners apply to which surface. Is the priority list in D2.5 truth_banners.py authoritative, or does each surface need overrides?
- Should the source pill on table rows be a single-letter chip or full word? (Density vs clarity tradeoff.)
