# UX-5 — Progressive Abstraction Architecture

**Status:** strategy / architecture spec. **No code in this phase.**

This document responds to the realization captured during the
2026-05-08 trust incident:

> *"The current Brief view is still a simplified trader/research
> terminal. It is NOT an investing copilot."*

UX-2 / UX-3 / UX-4 fixed copy, calmness, and visual composition.
None of those fixed the deeper problem — **the product still
exposes the wrong abstraction layer by default.** Pending fills,
signal batches, regimes, gates, replay orchestration, and ingestion
state are *engine concepts*. They should not greet a user opening
the homepage.

UX-5 defines **three layers** and the discipline for routing every
existing surface into one of them.

---

## 1. Diagnosis — what's actually wrong

A clean reading test: open every current page and ask, sentence
by sentence,

> *"Would a competent retail investor who has never read a quant
> paper understand this — and care?"*

Today, most surfaces fail this test. Examples (literal current
copy):

| Current surface | What the user sees | Problem |
|-----------------|---------------------|---------|
| Overview > Readiness Strip | "Ingest 22:00 ET · Engine pipeline · Paper daily · Alpha nightly" | Cron schedule. Internal. |
| Overview > Execution Status | "Pending fills: 10 held by next-bar guard" | Mechanic, not state. |
| Overview > Anomaly Summary | "1/4 gates passing · stress regime active" | Engineering vocabulary. |
| Decisions | "Production inputs: vol_window=20, pt_sigma=2.0" | Hyperparameters. |
| Risk Dashboard | "Net Greeks · expiry concentration · flag panel" | Quant taxonomy. |
| Ops | "Pipeline · ML · scheduler · cron config" | Pure plumbing. |
| Options chain | "Calls/Puts tables, IV30, OI, delta, gamma" | Trader interface. |

These surfaces are **not wrong**. They are valuable to the operator
maintaining the system. The mistake is putting them in the
*default* product experience.

The trust failures we have been firefighting (stale UI, scheduler
opacity, pending-fill confusion) are **symptoms** of the same root
cause: an investing copilot product wearing the clothes of a
hedge-fund terminal.

---

## 2. The three-layer model

```
┌────────────────────────────────────────────────────────────┐
│  Layer 1 — INVESTING COPILOT  (DEFAULT EXPERIENCE)         │
│  Plain language. State, not mechanism. Action over data.   │
│  Answers: what matters today, do I act, what changed.      │
└────────────────────────────────────────────────────────────┘
                          ↓ disclosure
┌────────────────────────────────────────────────────────────┐
│  Layer 2 — INVESTING DETAIL  (PER-POSITION / PER-IDEA)     │
│  Human-readable but specific. Entries, exits, targets,     │
│  lifecycle, rationale. No system vocabulary.                │
└────────────────────────────────────────────────────────────┘
                          ↓ "See the working" link
┌────────────────────────────────────────────────────────────┐
│  Layer 3 — WORKING / SYSTEM  (ENGINEERING-FACING)          │
│  Everything the platform needs to be operable.             │
│  Signal batches, replay, scheduler, ingestion, gates,      │
│  regimes, fills, hyperparameters, telemetry.               │
└────────────────────────────────────────────────────────────┘
```

### Layer 1 — Investing Copilot (DEFAULT)

The default experience for `/`, `/portfolio`, `/decisions`,
`/options`. Answers six questions and only six:

1. **What matters today?**
2. **Do I need to do anything?**
3. **What opportunities exist?**
4. **What changed?**
5. **What risks matter?**
6. **What should I watch?**

Constraints:
- **Plain English only.** No "regime", "gate", "anomaly",
  "signal", "candidate", "pipeline", "ingest", "replay", "fill",
  "guard", "scheduler", "cron", "snapshot", "advisory mode".
- **State, not mechanism.** "Markets remain unstable today" —
  not "stress regime active".
- **Action, not data.** "Two ideas are waiting for tomorrow's
  open" — not "10 pending fills".
- **Calm, not telemetry.** No counters, no chips, no badges.
- **Truthful fallbacks.** Silence > placeholder.

### Layer 2 — Investing Detail

Reachable from Layer 1 by clicking a story card. Shows position-
specific or idea-specific specifics: entry date, entry price,
current move, target zone, stop zone, lifecycle stage, "what
changed since you last looked." Still human-readable. Still
no engine vocabulary.

The Phase B Brief view is mostly Layer 2 today (with leakage —
"recovered" chip, "Day N" cue are Layer 2 OK, but the page also
inherits Layer 3 noise from sibling pages).

### Layer 3 — Working / System

Where every current page should *eventually* live. Engineering-
facing. Operator-facing. Not retail-facing. Reachable from any
Layer 1/2 surface via a single, consistently-named link:

> **See the working →**

This is the Working view that already exists at
`/portfolio?view=working`. Generalize the same routing pattern
across other pages.

---

## 3. Translation glossary (Layer 3 → Layer 1 vocabulary)

Every Layer 3 concept maps to one Layer 1 phrase. The mapping is
**deterministic** (the same input always renders the same Layer 1
sentence) and **observed** (we report state, not narrate).

| Layer 3 (engine) | Layer 1 (copilot) |
|------------------|---------------------|
| "Signal batch 2026-05-08 generated" | "The system reviewed today's market activity." |
| "Regime: stress" | "Markets remain unstable today." |
| "Regime: normal" | "Markets are calm today." |
| "Regime: trending" | "Markets are moving with direction today." |
| "1/4 gates passing" | "Most safety checks are cautious today." |
| "4/4 gates passing" | "All safety checks are clear today." |
| "Pending fills: 10" | "Two ideas are waiting for the next market session." |
| "Critical anomaly: 1" | "One thing needs your attention today." |
| "Pipeline failed" | "System status changed today. Open *System status* below." |
| "Engine A vs Engine B" | "Buy-the-dip strategy vs Defensive strategy" |
| "max_drawdown_pct: -7.2%" | "The account is 7% below its peak this week." |
| "ingest_prices_daily success at 22:02" | (silent — internal, never surfaced) |
| "candidate_idea written=1008 buys=10" | "Today's review shaped 10 possible ideas." |
| "factor_snapshot 1008/1008" | (silent) |
| "next-bar guard" | (silent — replace with "Two ideas are waiting for tomorrow's open") |
| "replay completed" | (silent — replace with "Recovered earlier activity") |
| "ML advisory mode" | (silent — strategies should never name themselves) |

Banned in Layer 1 (extends UX-3D + UX-4 anti-AI-theater list):
`signal`, `batch`, `regime`, `gate`, `anomaly`, `pipeline`,
`ingest`, `replay`, `fill`, `guard`, `scheduler`, `cron`,
`snapshot`, `advisory`, `engine`, `pending`, `cycle`, `trigger`,
`runner`, `stage`, `module`, `as_of`, `submitted_at`.

---

## 4. Page-by-page audit

For each existing page: **left column = what it currently
exposes**, **right column = where it belongs**.

### `/overview` (homepage today)

| Current surface | Belongs in |
|-----------------|------------|
| ReadinessStrip (cron names) | L3 |
| ExecutionStatusCard ("pending fills, next-bar guard") | L1 (translated) |
| CalmStateLine | L1 (already aligned; keep) |
| DailyActivityCard | L1 (translate "Trades 0" → "Two ideas are waiting…") |
| Performance attribution | L1 (translate "alpha decay" → "results vs target this week") |
| RegimeHeatmap | L3 |
| TopCatalysts | L1 (rename to "What might move things this week") |
| WhatChanged | L1 (already aligned; keep) |
| TradeBlotter | L2 / L3 split |
| GuidancePanel ("anomaly summary, gate counts") | L3 |
| AlphaCoreStatus ("ML readiness, signal stability") | L3 |
| RecentEventsFeed (cron logs) | L3 |
| ExploratoryBanner | L3 |

**Verdict:** ~70% Layer 3. Overview today is a thinly translated
operator dashboard. Needs a full architectural redesign, not a
typography pass.

### `/portfolio` (current default = PortfolioTerminal; brief opt-in)

| Current surface | Belongs in |
|-----------------|------------|
| Brief view (CopilotHoldings) | L1 / L2 (already aligned, mid-flight UX-2/3/4) |
| Working view (PortfolioTerminal): exposure tables, exec audit | L3 |
| Risk Dashboard card embedded | L3 |
| Exit Analytics card embedded | L3 |

**Verdict:** Portfolio is the closest to right. Phase F flip
(brief becomes default) is correct. Working view stays L3.

### `/decisions`

Three-column "audit workstation." Every column is L3:
- Timeline filters
- Decision detail (production inputs, hyperparameters)
- Outcome + pattern context

**Verdict:** Pure L3. Should be reachable only via *See the
working* from a Layer 2 position card. Not in primary nav.

### `/alpha-lab`

"Open + closed trade intelligence dashboard." Concentration,
exit-reason breakdowns, P&L by holding-age bucket. L3 by content,
but the *idea* of "how is this trade going" is L2.

**Verdict:** Split. Per-trade narrative ("How is this position
evolving?") moves to L2. Concentration / breakdown / hold-age
analytics stay L3.

### `/risk`

Net Greeks, max-loss exposure, expiry concentration, flag panel.

**Verdict:** Pure L3. The L1 surface is *one sentence* on the
homepage: "What risks matter today?" Everything else is *See the
working*.

### `/options/*` (13 sub-pages)

Chain, features, paper trades, risk dashboard, observatory,
performance, diagnostics, replay, evaluation, decision support,
decision framing, overview, layout.

**Verdict:** Almost entirely L3. The L1 surface is one path:
"Today's option ideas (paper)" with at most 3 ideas, each rendered
as a story card. Every diagnostic / observatory / replay / chain
table moves under *See the working*.

UX-1 Commit F's `OptionsOverviewPage` is closer to L1 than the
chain table — it's the right precedent, but the rest of the
sub-pages need to recede behind a single `/options?view=working`
gate.

### `/ops`

Pipeline status, ML pipeline, scheduler config, cron jobs.

**Verdict:** Pure L3. **Should never be linked from Layer 1 nav.**
Operator-only.

### `/research`, `/ml-lab`, `/agents`

Research observatory, ML validation console, agent workflows.

**Verdict:** Pure L3. Operator/research-only.

### Aggregate verdict

| Page | L1 share | L2 share | L3 share |
|------|----------|----------|----------|
| Overview | ~10% | ~5% | ~85% |
| Portfolio (brief) | ~70% | ~30% | 0% |
| Portfolio (working) | 0% | 0% | 100% |
| Decisions | 0% | ~20% | ~80% |
| Alpha Lab | 0% | ~30% | ~70% |
| Risk | 0% | 0% | 100% |
| Options/* | ~5% | ~5% | ~90% |
| Ops | 0% | 0% | 100% |

**The Layer 1 surface area is currently ~5% of what users see by
default.** UX-5's job is to invert that ratio.

---

## 5. Hidden / translated / under-the-working classification

For every concept exposed today:

| Concept | Treatment in Layer 1 |
|---------|----------------------|
| Cron names, schedules, pipeline stages | **Hidden.** Never surfaced in L1. |
| Engine identifiers (A, B), engine names | **Translated.** "Buy-the-dip" / "Defensive". |
| Hyperparameters (vol_window, sigma, thresholds) | **Hidden.** Reachable only via L3. |
| Signal scores, confidence floats | **Translated** to 3-band labels. |
| Regime label | **Translated** to one calm sentence. |
| Gate counts | **Translated** to "all clear" / "most cautious" / "needs attention." |
| Anomaly counts | **Translated** to "one thing needs your attention today" or absent. |
| Replay metadata, source flags | **Hidden** in L1. Surfaces as "recovered" chip in L2. |
| Pending fills, next-bar guards | **Translated.** "Two ideas are waiting for tomorrow's open." |
| Trade execution mechanics (slippage, commissions, fill_ts) | **Hidden** in L1. Visible in L2 "lifecycle" without naming the mechanism. |
| ML mode, advisory state | **Hidden** entirely from L1/L2. |
| Daily-loop status | **Translated.** "Today's review is ready." or "We're catching up — open *System status* below." |
| Performance attribution detail | **Translated.** "Up X% this week" with no "alpha decay" / "factor exposure." |
| Drawdown | **Translated.** "Account is N% below its peak this week." |
| Position-level Greeks (options) | **Hidden** in L1. Surfaces in L2 as "this idea's risk shape" without numbers. |

Default rule: **if a concept requires a glossary, it does not
belong in Layer 1.**

---

## 6. New Overview design (Layer 1 default)

The new Overview answers the six questions in order. Every block
is one sentence or one short list. No charts above the fold. No
chips. No counters.

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   Good morning.                                              │   ← time-of-day greeting only
│                                                              │
│   {The system reviewed today's market activity.            } │   ← 1-line "what matters today"
│   {Markets are calm today.                                 } │     (deterministically composed
│                                                              │      from regime + pipeline state)
│                                                              │
│   ─────────────────────────────────────────────              │
│                                                              │
│   What's open                                                │   ← question 2
│   {3 paper positions. Two are quietly working;              }│     (one sentence; the actual
│   {one is approaching its target.                           }│      cards live on /portfolio)
│                                                              │
│   See my holdings →                                          │
│                                                              │
│   ─────────────────────────────────────────────              │
│                                                              │
│   Today's ideas                                              │   ← question 3
│                                                              │
│   • {AAPL — entry zone reached, signal still early}          │   ← max 3 cards (Phase C territory)
│   • {NVDA — pulling back into support}                       │     each = one observational sentence
│   • {MSFT — building a base}                                 │     no scores, no confidence numbers
│                                                              │
│   See all ideas →                                            │
│                                                              │
│   ─────────────────────────────────────────────              │
│                                                              │
│   What changed                                               │   ← question 4
│   {Two new ideas appeared overnight.                        }│
│   {One position is approaching its target.                  }│
│                                                              │
│   ─────────────────────────────────────────────              │
│                                                              │
│   What to watch this week                                    │   ← question 6
│   • Earnings: AAPL Thu, MSFT Wed                             │
│   • Fed minutes Wed                                          │
│                                                              │
│   ─────────────────────────────────────────────              │
│                                                              │
│   Read-only research — paper trading only.                   │   ← footer (existing)
│                                                              │
│   See the working →                                          │   ← single Layer-3 escape hatch
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

What is **not** on the new Overview:
- Readiness strip (cron names)
- Equity drawdown chart
- Regime heatmap
- Daily activity card with counters
- Anomaly summary
- Alpha core status
- Recent events feed
- Trade blotter
- Catalyst lists with raw scores
- Performance attribution panel
- Anything from `usePerformance`, `useAnomalies`, `useSystemHealth`,
  `usePaperEquity` — these become *See the working* surfaces

Question **5 ("What risks matter?")** intentionally absent
from the default homepage — it surfaces only when an actual risk
condition triggers (e.g., drawdown ≥ 5%, stress regime, paused
strategy). Otherwise silence.

---

## 7. New Portfolio design (Layer 1 + 2)

Portfolio is already mid-flight (Phase B Brief view). UX-5
finishes the abstraction by:

1. Flipping default to brief (Phase F as already planned).
2. Removing Layer 3 leakage from brief: Risk Dashboard card +
   Exit Analytics card stay only in Working view.
3. Preserving the per-position story format from UX-4 (Featured
   + Standard) but rejecting any Layer 3 vocabulary on the cards
   themselves.

```
┌──────────────────────────────────────────────────────────────┐
│   My Holdings                                                │
│   {3 positions are open. One is approaching its target.   }  │
│                                                              │
│   ─────────────────────────────────────────────              │
│                                                              │
│   AAPL          (Featured: most recent or biggest move)       │
│   {Up 1.3% since you bought it on May 2.                  }  │
│   {Approaching target zone.                                } │
│   ●─●─●─○   Idea  Bought  Day 4  Closed                     │
│                                                              │
│   ─────────────────────────────────────────────              │
│                                                              │
│   TSLA           +0.4% ↑   Day 1                             │
│   ▸ click to expand                                          │
│                                                              │
│   GOOGL         −0.2% ↓   Day 1                             │
│   ▸                                                          │
│                                                              │
│   ─────────────────────────────────────────────              │
│                                                              │
│   See the working →                                          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

Banned in Layer 1/2 Portfolio cards: `engine`, `strategy`,
`signal`, `confidence`, `band`, `gate`, `regime`, `replay`,
`source`, "advisory", "next-bar", "pending fill". The temporal
cue ("Day 4", "Opened today") is allowed because it is a
human-meaningful position fact.

---

## 8. Layer routing

The same `?view=brief|working` pattern that Phase A introduced
generalizes:

| URL | Layer | Notes |
|-----|-------|-------|
| `/` | L1 | New homepage redesign |
| `/portfolio` | L1 default (after Phase F) | brief = L1+L2; working = L3 |
| `/portfolio?view=working` | L3 | Existing PortfolioTerminal |
| `/options` | L1 default | Today's ideas only |
| `/options?view=working` | L3 | Chain, observatory, decisions |
| `/risks` | L1 (new, optional) | One sentence + watch list |
| `/risks?view=working` | L3 | Existing /risk page |
| `/decisions`, `/alpha-lab`, `/ml-lab`, `/agents`, `/ops`, `/research` | L3 | Removed from primary nav. Reachable via *See the working*. |

Primary nav retracts to four items: **Today**, **Holdings**,
**Ideas**, **Watch**. (The *Working* link sits in the page footer,
not the nav.)

---

## 9. What stays in Layer 3 (operator continuity)

Nothing in this proposal *deletes* any existing surface. Every
operator-facing diagnostic remains accessible. Specifically:

- `/portfolio?view=working` — full PortfolioTerminal preserved
- `/decisions` — full audit workstation preserved
- `/alpha-lab` — concentration / breakdowns preserved
- `/risk` — risk dashboard preserved
- `/options/*` — every options sub-page preserved
- `/ops` — pipeline / ML / scheduler / cron preserved
- `/research`, `/ml-lab`, `/agents` — preserved

The change is *navigation prominence + default route*, not
deletion. Operators bookmark Working URLs directly; the *See the
working* link is the formal escape hatch from any Layer 1/2 page.

---

## 10. Truthful fallbacks (Layer 1 specific)

When data isn't available, **say nothing** rather than say "—".
Specific rules:

| Data missing | Layer 1 behavior |
|--------------|------------------|
| Mark prices unavailable | The "Approaching target" line vanishes; card stays. |
| No new ideas today | "Today's ideas" section absent. |
| No open positions | "What's open" section becomes "Cash only today." |
| Quiet regime + nothing happening | Page collapses to greeting + "Quiet day. Nothing pressing." + footer. |
| Pipeline failed | Single banner "We're catching up — open *System status* below." Everything below banner suppressed until pipeline resolves. |
| Drawdown ≥ 5% | "What's open" subtitle adds "Account is N% below its peak this week." Optional risk question 5 surfaces. |

The page *contracts* when nothing happens — it does not pad with
chips.

---

## 11. Implementation phasing

**No code in UX-5 itself.** UX-5 is the architecture that
*subsequent* phases implement. Sequencing recommendation:

| Phase | Scope | Ships |
|-------|-------|-------|
| **UX-5A** | Translation glossary + lint expansion | Phase A copilot lint extends with the 25 new banned tokens |
| **UX-5B** | Overview redesign | Replace `/overview` with the 6-question structure; old Overview moves to `/overview?view=working` |
| **UX-5C** | Portfolio Phase F flip + Working leakage purge | Brief becomes default; Risk + Exit cards exit brief view |
| **UX-5D** | Options L1 surface | `/options` default = "Today's ideas (paper)"; chain + diagnostics under `?view=working` |
| **UX-5E** | Nav retraction | Primary nav becomes 4 items; legacy links move to footer |
| **UX-5F** | Risks Layer-1 page (optional) | One-sentence + watch list |
| **UX-5G** | Cross-page consistency audit | Lint pass on all L1/L2 surfaces against the translation glossary |

Each phase is a separate plan-only review (per the discipline that
worked through UX-3 and UX-4) before any code lands. **UX-5B is
the highest-leverage phase** — fixing the homepage moves the
greatest share of users onto the new abstraction.

UX-2 Phase C-2 (typography ramp) and Phase C-3 (Featured
archetype) **stay stashed**. They are still correct — but they
target the wrong layer first. Resume them inside UX-5C, after the
abstraction direction is locked, so the ramp + Featured land on a
page that has the right *content*, not just the right *typography*.

---

## 12. Open questions for the human

1. **Nav retraction** — is "Today / Holdings / Ideas / Watch" the
   right 4? Should "Watch" be its own page or absorbed into
   "Today"?
2. **`/risks` Layer-1 page** — does this exist? Or is risk a
   contextual line that surfaces only when triggered, with no
   dedicated route?
3. **Options L1** — should options ideas live on the Today page
   alongside stock ideas (one combined "Today's ideas" list) or
   on their own `/options` page?
4. **Operator handoff** — should we ship a separate operator login
   that pins to `/ops` by default, so retail users never *reach*
   the Working layer except via *See the working* clicks?
5. **Featured selection rule (UX-4 leftover)** — does Featured
   exist on quiet days when no position has notable movement?
6. **Holding period framing** — is "Day 4" the right temporal cue
   for retail, or is "4 days held" / "4 days in" warmer?
7. **Layer 3 attribution** — every Working link reads "See the
   working → ". Should there be any descriptive variant
   ("See the working: position math →") or is consistency
   absolute?
8. **Anti-AI-theater extension** — the lint script currently
   scopes to `lib/copilot/` + `components/copilot/`. UX-5 needs
   it to scope to *every* L1/L2 surface. Is the current isolation
   between copilot/ and the rest of `apps/web/src/` worth
   maintaining, or do we collapse it once UX-5 lands?

These are the architectural decisions the human owns. UX-5 cannot
proceed past UX-5A without answers to (1), (2), (3).

---

## 13. Success criteria

UX-5 succeeds when:

- A retail user opening `/` sees no engineering vocabulary.
- The default homepage answers six questions in plain English.
- Every operator surface remains reachable via *See the working*.
- The lint script catches Layer 3 vocabulary leaking into Layer 1
  files.
- Removing one Layer 3 surface doesn't break any Layer 1
  experience.
- The product feels like an investing copilot.

UX-5 fails if:

- Any "regime" / "gate" / "signal batch" / "pending fill" /
  "next-bar guard" / "advisory" / "engine pipeline" string reaches
  a default-route surface.
- The homepage has more than 6 sections.
- Any chart or table appears above the fold on `/`.
- We polish typography or atmosphere before the abstraction is
  locked.

The proof is conceptual readability, not visual quality.

---

## Appendix A — Cross-reference

| External doc | Relationship |
|--------------|--------------|
| `docs/research/UX_4_COMPOSITION.md` | Visual composition principles. Still apply *inside* Layer 1. |
| `docs/ops/HARDENING_BACKLOG.md` H10 | Orchestration-state enum that makes Layer 3 → Layer 1 translation deterministic |
| `feedback_ux4_locks.md` | "See the working" lock — generalized in §8 of this doc |
| `feedback_observe_before_polish.md` | Why C-2 stays stashed until UX-5 abstraction lands |
