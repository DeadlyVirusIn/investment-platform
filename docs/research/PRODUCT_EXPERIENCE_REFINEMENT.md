# Product Experience Refinement — Today / Pick Detail / Learn Hub

**Date**: 2026-05-20
**Status**: PLAN ONLY — refines PR-3, revises sequencing
**Predecessors**:
- `FULL_PRODUCT_PAGE_DESIGN_MAP.md`
- PR-1 + PR-2 shipped (Today shell + calm portfolio)

## Hard constraints (locked across every block below)

- **No fake AI narration**. Frontend authors no agency-attributing prose.
- **No fabricated explanations**. If a fact is unknown, render honest absence.
- **No fake real-time / win-rate / streak / "AI sees"**.
- All copy passes the 30-phrase Tier-A lint.
- Existing backend data only. No new endpoints.

---

## 1. Today page orientation — "What changed recently"

### The five questions the page must answer

| Q | Where it's answered today (PR-1) | Where it should be answered post-PR-3 |
|---|---|---|
| What changed?            | nowhere on Today | NEW "What changed recently" section |
| What matters today?      | One thing to look at | unchanged |
| Am I okay?               | Portfolio NAV + AI Read sentence | unchanged, slightly extended |
| Did the system change its view? | nowhere | NEW row inside "What changed recently" |
| What should I learn?     | Learning card | unchanged |

### "What changed recently" — observational rows

A single section, max 6 rows, each row one sentence with rendered facts. No headlines, no AI agency, no "AI thinks". Every row sources facts from existing tables.

**Row types** (deterministic; render order = newest first):

| Row | Trigger | Source | Example wording |
|---|---|---|---|
| **Closed positions**       | any `paper_position` closed in last 7d | `paper_position` WHERE `is_open=false AND closed_at > now-7d` | "Closed AMAT at +4.2% on Mon 12 May." |
| **New entries**            | any `paper_trade` side=buy in last 3d | `paper_trade` WHERE `fill_ts > now-3d AND side=buy` | "Opened NVDA on Mon 19 May." |
| **Largest realized gain**  | top `realized_pnl_dollars` in last 30d | `paper_trade.realized_pnl_dollars` MAX | "Largest gain in the past month: AMAT +$420." |
| **Largest realized loss**  | min `realized_pnl_dollars` in last 30d (negative) | `paper_trade.realized_pnl_dollars` MIN | "Largest loss in the past month: KLAC −$185." |
| **Concentration shift**    | delta in top position % of NAV vs 7d ago | `paper_position.market_value` / `paper_portfolio.nav` | "Top concentration: NVDA at 4.8% of portfolio (up from 3.9% a week ago)." |
| **Portfolio estimate gap** | live_nav − official_nav delta | `/paper/live-nav` vs `/paper/summary` | "Live estimate is $1,956 below the official close." |
| **Options dormant note**   | always (until canary proves) | constant state from `OPTIONS_ENABLED` | "Options remain dormant — equities only for now." |
| **System view change**     | engine recommendation flipped on a held position | `decision_log` action delta vs prior day | "AI now flags FDX for trim (was hold yesterday)." |

**Render rules**:
- Max 6 rows shown, ranked by recency × signal strength
- Each row standalone — no narrative connectors
- Each row carries a tiny date-tag (e.g. "2d ago") on the right
- Losses styled with terracotta dot, same size as gains
- No row uses "AI thinks/sees/expects"; system view rows use "AI now flags / AI removed / AI added"
- Honest empty state: "No notable changes since your last visit."

### Today page hierarchy (revised post-PR-3)

```
1. Greeting
2. The AI Read Today           ← unchanged
3. Your paper portfolio         ← unchanged
4. One thing to look at         ← unchanged
5. What changed recently        ← NEW (PR-3)
6. AI's recent moves            ← simpler 3-row "last 3 closed signals"
7. Learning card                ← unchanged
8. Browse · Advanced
```

The "What changed" section sits ABOVE the "AI's recent moves" because the user's question "What changed?" is more emotionally pressing than the historical journal. Recent moves becomes a 3-row strip for continuity.

---

## 2. Pick Detail experience

### Current operator-heavy experience (PickModal as it stands)

Order on screen (`PickModal.tsx:177-407`):
1. Eyebrow: "AI Research Cockpit"
2. Symbol header
3. Sub-line: `engine ${pick.engine_version} · adjusted · fresh 2h ago`
4. **Signal badge** (large, colored) — "buy / Buy NVDA · Medium conviction"
5. Reasoning section (now "Signal" header per Phase B)
6. Reference price (entry / target / stop)
7. Catalysts
8. Technical details expander — `engine_version`, `composite_score`, `raw_action`, `raw_adjusted_action`, `family_scores`

Issues for a novice:
- "AI Research Cockpit" is operator vocabulary
- Engine version + freshness on header is engineering
- The big colored action badge feels casino-like
- Reference price is positioned ABOVE the reasoning — wrong order
- Family scores leak Layer-3 vocabulary
- No invalidation / triggers (the truth-bearing fields from the envelope)
- No timeline (how the signal evolves)
- No "is this already in my portfolio?" context

### Desired mentor experience — ordered sections

| # | Section | What it answers | Source | Notes |
|---|---|---|---|---|
| 1 | **Symbol + nature**          | "What is this?"                              | symbol + signal action + DT/timestamp | calm serif title; signal dot only, no big colored badge |
| 2 | **The reasoning**           | "Why is the AI looking at this?"            | `ReasoningCard` rendered from backend envelope | primary block, takes the most vertical space; honest-absence if no envelope |
| 3 | **What we're watching for** | "What would make us change our mind?"        | envelope `invalidation` + `triggers` (already in Phase L envelope) | renders as 2 sentences max: "We'd stop if X. We'd add if Y." |
| 4 | **Reference levels**         | "What prices anchor this signal?"             | `pick.risk.{entry,target,stop_loss}` | three small numbers in a row, no emphasis, no glow; labeled "entry · target · stop" |
| 5 | **Catalysts**                | "Any events coming up?"                      | catalyst feed (existing) | calm bulleted list with dates; if empty, omit section entirely (no "no events" filler) |
| 6 | **In your portfolio**        | "Do I already own this?"                     | `paper_position` lookup by symbol + asset_id | conditional render: "You hold 0.3 shares at avg cost $741.79 (−1.1%)" — quiet line |
| 7 | **How this signal evolves** | "Will I see when it changes?"                | `decision_log` for this symbol over time | inline mini-timeline (3-5 dots: "Buy → Hold → Trim"), each with date |
| 8 | **Learn more**               | inline learning hooks                        | glossary terms | tiny links: "What's a stop?", "What does Trim mean?" — opens drawer |
| 9 | **Show technical detail**   | operator-only spillage moved here             | `engine_version`, `composite_score`, `family_scores`, `raw_*` | collapsed by default; chevron disclosure; intentionally text-dense to signal "this is for operators" |

### Tonal rules

- **Reasoning section is the focal point** — biggest vertical block, serif heading
- **Signal action** rendered as a dot + word ("• Buy"), never a large filled badge
- **Reference levels** are utility numbers — same size as body text, ink-secondary color, no glow
- **Calm scrim**: when opened from `/today`, modal uses `data-shell="calm"` (PR-2 wired). When opened from `/overview` legacy, unchanged.
- **No "AI Research Cockpit" eyebrow**. New eyebrow: small `as of <date>`.
- **Inline learn-links** are subtle accent-colored words with hover underline; tap opens a side drawer with glossary entry, never navigates away.

### Three layered density modes (same component, conditional render)

| Mode | Triggered by | What hides |
|---|---|---|
| **Novice** (default for `/today` entry)         | `shellVariant="calm"` + no operator query param | Technical detail expander, system view rows on timeline |
| **Standard** (default for `/overview` legacy)  | `shellVariant="legacy"`                          | Nothing hidden but uses legacy chrome (current modal) |
| **Operator**                                     | `?density=operator` query param OR Advanced route | Technical detail expanded by default, timeline shows full state graph |

Density is a render-time decision — no separate component fork — and reuses the existing data path.

---

## 3. Learn Hub strategy

### Identity

Not "help center" or "FAQ". This is a retention engine that compounds trust over time. The user should feel **smarter** after each visit, not more dependent.

### Structure

```
/learn
├── Featured term of the day
├── Glossary (alphabetical, searchable)
│   └── /learn/term/:slug   (per-term page)
└── Learning paths
    ├── /learn/path/how-this-ai-thinks
    ├── /learn/path/reading-your-portfolio
    ├── /learn/path/risk-literacy
    ├── /learn/path/paper-trading-fundamentals
    ├── /learn/path/portfolio-psychology
    └── /learn/path/options-basics       ← held disabled until canary proves
```

### Glossary — 30-50 terms minimum

Sources from `apps/web/src/lib/novice/glossary` (already exists). Categories:

- **Account terms**: NAV, cost basis, P&L, realized, unrealized, equity, drawdown
- **Signal terms**: Buy / Sell / Trim / Hold, conviction band, signal age, stale signal
- **Engine terms** (Layer 2, explained in plain English): composite score, factor, regime, paper trade
- **Risk terms**: position sizing, concentration, correlation, max drawdown, stop, take-profit
- **Time terms**: fill, settlement, snapshot, EOD, delayed quote

Each term page:
1. The term (serif title)
2. One-sentence definition (sentence-case, no jargon)
3. Why it matters (one paragraph)
4. How the AI uses it (where applicable — sourced from real engine behavior, not invented)
5. "Related terms" links (cross-linked glossary entries)
6. "Where you'll see it in the product" (with screenshots or component preview — defer to PR-5+)

### Learning paths — 5 mini-courses

Each path = 4-6 short lessons (5-min read each).

**Path 1: "How this AI thinks"**
- Lesson 1: What's a signal?
- Lesson 2: Why doesn't the AI talk like a human?
- Lesson 3: What's conviction, and why isn't it a percentage?
- Lesson 4: How does the AI change its view?
- Lesson 5: When does the AI go quiet, and why?

**Path 2: "Reading your portfolio"**
- Lesson 1: NAV, cash, holdings
- Lesson 2: Realized vs unrealized
- Lesson 3: Cost basis and return %
- Lesson 4: Live estimate vs official close
- Lesson 5: Drawdown — the chart that matters most

**Path 3: "Risk literacy"**
- Lesson 1: Position sizing and why "all-in" is rare
- Lesson 2: Diversification — concentration as a number
- Lesson 3: Drawdown psychology
- Lesson 4: Stop-losses — what they protect against
- Lesson 5: Paper trading — what's real and what isn't

**Path 4: "Paper trading fundamentals"**
- Lesson 1: Why paper trading first
- Lesson 2: What the AI can and can't see
- Lesson 3: Replay vs live — why your portfolio shows both
- Lesson 4: When paper P&L matters and when it doesn't

**Path 5: "Portfolio psychology"** (highest retention value)
- Lesson 1: Anchoring on entry price
- Lesson 2: The pain of trimming a winner
- Lesson 3: The temptation to over-trade
- Lesson 4: How AI trading is different from your reflexes
- Lesson 5: Building the habit of checking before acting

**Path 6: "Options basics"** (held disabled — `data-state="locked"` until canary lifecycle proves)
- Disabled card on Learn index with copy "Available after the options preview ships."

### "Why the AI did this" lessons — tied to real trade history

For each closed paper trade in the user's portfolio, render a short retrospective lesson on `/learn/trades/:trade_id`:

- The signal that triggered the entry (envelope hash if present)
- How the position moved (sparkline)
- What triggered the exit (decision_log lookup at close time)
- A general principle the trade illustrates ("This is what a trim looks like" / "This is what a stop-loss looks like")

Sources from existing `paper_trade`, `paper_position`, `decision_log`, `reasoning_audit` rows. **No invented narrative** — only renders fields that exist.

### Weekly recap concept (designed; implementation in PR-7+)

A per-week page summarizing: which signals opened, which closed, biggest move (gain or loss), portfolio NAV at start vs end, one term to learn this week. Sourced from existing data; no new endpoint.

### Tonal rules across Learn Hub

- Lesson text is short (200-400 words per lesson)
- Code/jargon shown only when explained
- No "you should …" imperatives; observational ("Most paper traders find that …")
- Each lesson ends with one calm CTA: "Continue path" or "Back to Learn"
- No quizzes / no streak counters / no gamification

---

## Revised PR-3 scope

### What PR-3 ACTUALLY ships (revised, expanded but still single-PR)

| Component | Scope | Lines (est.) |
|---|---|---|
| `<WhatChangedRecently/>` (new) | the 6-row observational section described in §1. Sources from `/api/paper/executed/trades`, `/api/paper/executed/positions?is_open=true`, `/api/paper/summary`, `/api/paper/live-nav`, `/api/performance/equity-curve`, `decision_log` (if exposed) | ~250 |
| `<AIRecentMoves/>` (new, condensed) | 3-row track record strip (was the original PR-3 scope; reduced to make room) | ~80 |
| `TodayPage.tsx` (modified) | wire both blocks into existing layout | +30 |

**Out of scope for PR-3**:
- Pick Detail rebuild
- Learn Hub
- Onboarding
- No backend / no new endpoints
- No schema / no migrations
- No Phase L renderer touches
- No options lifecycle

**Backend access**:
- `/api/paper/executed/trades`               (existing, used in PR-1 already)
- `/api/paper/executed/positions?is_open=true` (existing)
- `/api/paper/summary`                       (existing)
- `/api/paper/live-nav`                      (existing)
- `/api/performance/equity-curve`           (existing)
- `decision_log` — accessed via existing `/api/decision-log` or `usePaperTrades` if needed

If `decision_log` action-flip data isn't readily available client-side, the "System view change" row is omitted (honest absence) and we add it after a small read-only endpoint exposes it in a future PR.

---

## Sequencing recommendation

### Recommended next order: PR-4 BEFORE PR-5

**Reasoning**:

After PR-3 ships, the Today page has 6 calm sections. The user's #1 emotional action is clicking the "One thing to look at" card. That click currently lands them in the legacy operator PickModal (or whatever Ideas page renders). Even with the calm `shellVariant="calm"` infrastructure shipped in PR-2, the modal still has its operator-heavy section order.

**The trust break**: calm Today → tap → operator-density Pick Detail. The user notices the tonal jump immediately. **This breaks the mentor narrative.**

Order:

| PR | Goal | User-trust impact | Risk |
|---|---|---|---|
| **PR-3** | Today "What changed" + recent moves | answers the 5 questions calmly | low |
| **PR-4** | Pick Detail calm rebuild | **highest single-PR trust impact** — closes the trust loop from Today → click → Pick | medium |
| **PR-5** | Learn Hub (glossary + 2 starter paths) | compounding retention; complements PR-4 (inline learn-links inside Pick Detail need glossary entries) | low |
| **PR-6** | Performance / Track Record full page | extends PR-3's recent moves into a full historical page | low |
| **PR-7** | Onboarding / Risk Profile | gates new-user experience; needs PR-4 + PR-5 so the journey is complete | medium |
| **PR-8** | Settings | utility; safe anywhere | low |
| **PR-9** | Copilot Chat UI shell | gated on backend `/api/copilot/ask` design (not in this sequence) | medium |
| **PR-10** | Advanced area containment | last; pulls the rug on operator surfaces from default nav | low |

### Why this differs from the original Design Map order

| Old | New | Why |
|---|---|---|
| PR-4 = Ideas | PR-4 = **Pick Detail** | Pick Detail is the single highest-trust surface after Today; Ideas page is just a list and can wait |
| PR-5 = Learn | PR-5 = Learn | unchanged (after Pick Detail, learn-links from PR-4 need glossary entries to point at) |
| PR-6 = Onboarding | PR-6 = **Performance** | Onboarding without a strong Pick Detail experience misrepresents the product; Performance extends PR-3's recent-moves into a fuller history |
| PR-7 = Performance | PR-7 = **Onboarding** | Onboarding lands once the core loop (Today → Pick → Learn → Performance) is complete |
| PR-8 = Copilot Chat | PR-8 = **Settings** | trivially safe, defer Copilot Chat until backend design lands |
| PR-9 = Settings | PR-9 = Copilot Chat shell (deferred until backend ready) | — |
| PR-10 = Advanced | PR-10 = Advanced | unchanged |

### Ideas page (was PR-3 in original map) is deferred to PR-11

The `/action-queue` route already shows ideas in operator form. With PR-3's "What changed" + recent moves on Today, the user can usually find what they need. A dedicated calm Ideas page is valuable but lower-leverage than Pick Detail or Learn. Ship as PR-11 after the core mentor loop is in place.

---

## Locks honored across this refinement

| Lock | Status |
|---|---|
| No fake AI narration                          | ✅ — every row in "What changed" is observation only |
| No fabricated explanations                    | ✅ — honest absence on every section |
| No new endpoints                              | ✅ — uses existing /api/paper/executed/*, /paper/summary, /paper/live-nav, /performance/equity-curve |
| No schema changes                             | ✅ |
| No accounting touches                         | ✅ |
| No trading touches                            | ✅ |
| No Phase L renderer touches                   | ✅ |
| No options lifecycle touches                  | ✅ |
| No fake confidence / win-rate / streak        | ✅ — Pick Detail signal is a dot, not a colored badge |
| No "real-time" claim                          | ✅ |
| No "AI sees / AI suggests"                    | ✅ — Tier-A lint enforces |
| No copy that fails 30-phrase lint             | ✅ |
| Legacy `/overview`, `/portfolio`, `/action-queue` untouched | ✅ |
| Operator surfaces survive at `/advanced/*`    | ✅ |

---

## Approval requested

1. Accept revised PR-3 scope (What changed + recent moves both ship)
2. Accept revised sequencing: PR-4 = Pick Detail rebuild (highest trust impact)
3. Confirm Ideas page deferral to PR-11

On approval, implement PR-3 next under the same discipline as PR-1/PR-2 (additive parallel, all validations pass, full rollback).
