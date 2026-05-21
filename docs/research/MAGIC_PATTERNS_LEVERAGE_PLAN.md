# Leverage Plan — Magic Patterns "ArthOS" Reference Design

**Date**: 2026-05-21
**Source**: `C:/Users/kunal/Downloads/ffd63d40-0b11-4a98-a9bc-5c0f1c1d12e0/`
**Brand name in mockup**: "ArthOS"
**Status**: REVIEW + DIRECTION ONLY — no implementation

The shared mockup is a complete Vite + React + Tailwind project with
9 page designs and a token system that aligns ~95% with PR-1..PR-4.
This document maps what to adopt, what to adapt, what to reject.

---

## 1. What the mockup gives us

| Asset | What it is | Compatibility |
|---|---|---|
| 5 token families (sand / ink / forest / coral / ochre) | Tailwind config | **near-identical** to our `--t-*` palette |
| Fraunces (display) + Inter (sans) + JetBrains Mono | Font stack | Fraunces is a strong editorial alternative to our Source Serif 4 |
| Soft / card / lift box-shadows | Tailwind | conflicts with our "no shadow at rest" lock |
| Framer-Motion fade-in + slide-up (8px) | Page entry animations | borderline — acceptable for entry-only |
| Navigation = Today / Portfolio / Copilot / Learn / Track Record + Operator (secondary) | AppShell | adds **Copilot** + **Track Record** to primary nav (vs our 4 |
| 9 page-shaped designs | Today / Portfolio / PickDetail / Copilot / Learn / TrackRecord / PaperTrading / Operator / Home | aligns with our PR roadmap |
| Sample copy ("Nothing here requires action today.") | Per page | tone perfect for our lint |
| Lesson data structure (slug · minutes · body[heading, paragraph]) | Learn | reusable for PR-5 |
| Drawdown chart pattern | TrackRecord | reusable for PR-6 |
| Conversational primer (Copilot mock responses) | Copilot | reference for tone, not implementation |
| Lucide icons (Sunrise · PieChart · MessageCircle · BookOpen · History) | per nav item | matches our icon library |

---

## 2. Token alignment table (their values vs ours)

| Role | Their token | Their hex | Our token | Our hex | Action |
|---|---|---|---|---|---|
| Page background | `sand-50` | `#FAFAF7` | `--t-surface-paper` | `#F7F4EC` | Adopt theirs (lighter, more premium) |
| Card background | `sand-100` | `#F4F1EA` | `--t-surface-elevated` | `#FDFBF6` | Adopt theirs |
| Sunken/secondary | `sand-200` | `#E8E6DF` | `--t-surface-sunken` | `#EFEBE0` | Adopt theirs |
| Border quiet | `sand-300` | `#D6D3C8` | `--t-border-quiet` | `#E5DFD0` | Adopt ours (lighter) |
| Ink primary | `ink-900` | `#0E0E0E` | `--t-ink-primary` | `#1B2520` | Adopt theirs (pure ink, no green tint) |
| Ink secondary | `ink-500` | `#57534E` | `--t-ink-secondary` | `#5C655F` | Adopt theirs |
| Ink muted | `ink-400` | `#78716C` | `--t-ink-muted` | `#8B928D` | Adopt theirs |
| Accent (trust) | `forest-800` | `#163225` | `--t-accent` | `#2E5043` | Adopt theirs (deeper, more premium) |
| Up tone | `forest-700` | `#1F4530` | `--t-tone-up` | `#3D6B5B` | Adopt theirs |
| Down tone | `coral-500` | `#B05E4C` | `--t-tone-down` | `#A85F4D` | near-identical; keep ours |
| Warn tone | `ochre-400` | `#C9A961` | `--t-tone-warn` | `#B8825F` | Adopt theirs (warmer amber) |

**Recommendation**: re-token our `today.css` to use the Magic Patterns
values. The shift is subtle (most are within 3-5% color delta) but the
aggregate effect upgrades the perceived premium-ness without semantic
risk. This is a PR-4.5 mini-PR (CSS-only, no logic change).

---

## 3. Typography decision

| Element | Their stack | Ours | Recommendation |
|---|---|---|---|
| Display serif | Fraunces | Source Serif 4 | **Fraunces** — has a more distinctive humanist warmth; matches "calm analyst" persona better |
| Body sans | Inter | Inter | unchanged |
| Mono | JetBrains Mono | (none specified) | adopt JetBrains Mono for technical-detail panels |

Fraunces is a Google font, free to bundle. Loading cost: ~50KB
woff2 for the weights we'd use (300/400/500). Acceptable.

**Action**: PR-4.5 swap `--t-font-display` from Source Serif 4 to
Fraunces. Single-line token change in `today.css`.

---

## 4. Brand name decision — `ArthOS` vs `paper`

Their brand mark: `ArthOS` set in serif 19px next to a 32px
forest-800 rounded square with a white Sparkle icon.

Our brand mark (in PR-1 TodayNav): `paper` set in lowercase 18px.

This is a product-strategy decision, not a design decision. Options:

| Option | Pros | Cons |
|---|---|---|
| Adopt `ArthOS` | Distinctive, marketable, brandable, matches mockup pre-built copy | Implies an "operating system" — bigger claim than "paper" |
| Keep `paper` | Honest, modest, doesn't overclaim, matches paper-only product reality | Less brandable; reads as descriptive not nominal |
| Hybrid: `ArthOS · paper` | Both; positions the product line | Verbose; nav real estate |

**Recommendation**: defer the brand decision to a separate review. Our
current `paper` lowercase mark is HONEST (the product IS paper-only)
and fits the lint posture. `ArthOS` is more brandable but is a name
commitment with marketing/domain/legal implications. NOT a PR-2/4/5
question.

---

## 5. Navigation comparison

| Slot | Mockup | Ours (PR-1) | Recommendation |
|---|---|---|---|
| 1 | Today                | Today              | ✅ keep |
| 2 | Portfolio            | Portfolio          | ✅ keep |
| 3 | **Copilot**          | Ideas              | adopt **Copilot** + keep Ideas (5-slot nav) |
| 4 | Learn                | Learn              | ✅ keep |
| 5 | **Track Record**     | (not in nav)       | promote **Track Record** to nav after PR-7 ships |
| secondary | Operator        | Advanced expander  | rename "Advanced" → "Operator"; same containment behavior |

The mockup's 5-item primary nav is better because:
- Copilot Chat is the conversational entry point (high-engagement)
- Track Record gets first-class trust surfacing
- Both align with our planned PR sequence (PR-5 Learn, PR-6 Performance/Track Record, PR-7/8 Copilot)

**Recommendation**: expand nav from 4 → 5 items at PR-5 sequence point
when Learn ships. Add Track Record at PR-6. Add Copilot Chat at PR-8.

---

## 6. Copy tone — adopt their voice

Verbatim lines from the mockup that pass our 30-phrase Tier-A lint:

| Mockup line | Use where |
|---|---|
| "Nothing here requires action today."                | Today page quiet-day footer |
| "A quiet day to think."                              | Today greeting on no-signal days |
| "Most current signals remain concentrated in large-cap technology." | What-changed row when concentration > 50% in a sector |
| "Wins and losses, shown with equal weight."           | Track Record page subtitle |
| "The point of a journal is not to feel good about it — it is to learn from it." | Track Record explainer |
| "Closing a position at a loss is not a failure. Closing a position because the thesis was wrong is a discipline." | Learn lesson on closing |
| "Cash flow is what the bank account shows."           | Learn glossary `operating-cash-flow` |
| "It is not a prediction. It is a noticing."          | Pick Detail thesis when honest absence |
| "Most underused tools in beginner portfolios."        | Learn lesson on trim |
| "Trimming means reducing the size of a position without closing it entirely. It is the in-between option." | Learn glossary `trim` |

**Recommendation**: adopt these lines verbatim where they fit. Each one
is observational, lint-clean, and tonally premium.

**Lint check needed** on Copilot mock responses — some lines like "The
models observed that…" or "the model's view" border on agency
language. Run the lint before adopting Copilot copy verbatim.

---

## 7. Patterns to reject

| Pattern | Where | Why reject |
|---|---|---|
| `shadow-soft`, `shadow-card`, `shadow-lift` | Tailwind config | our lock: no shadow at rest. Adopt their tokens without shadows |
| Framer Motion `slide-up` with `translateY(8px)` | All FadeIn wrappers | our lock: no transforms. **Exception**: entry-only fade (opacity-only) is acceptable |
| `usePaperTrading` mock context | All pages | replace with our real fetchers (already done in PR-1..PR-4) |
| `generateSparkline` mock data | TrackRecord + Today | replace with real `fetchEquityCurve` |
| `bg-coral-100 text-coral-600 border-coral-200` Badge variant for SELL | ui.tsx | OK for tone but our lock prefers dot-indicator over background pill. Compromise: use sage/coral text + thin border, drop background tint |
| `motion.div initial={{opacity: 0, y: 8}}` | every FadeIn | drop the `y: 8`; keep opacity only |

---

## 8. Page-level leverage matrix

| Mockup page | Our equivalent | Action |
|---|---|---|
| `Today.tsx` | `apps/web/src/pages/today/TodayPage.tsx` (PR-1) | **PR-4.5 polish**: adopt their 11px uppercase 0.14em date-eyebrow above greeting, their italic "single-sentence market read", their "Nothing here requires action today" footer line |
| `Portfolio.tsx` | `TodayPortfolioPage.tsx` (PR-2) | **PR-4.5 polish**: adopt their position-row layout pattern + their holdings empty state |
| `PickDetail.tsx` | `PickDetailPage.tsx` (PR-4) | **PR-5 alongside**: adopt their `Back ←` arrow with `-translate-x-0.5` hover (drop translate per our lock), their ticker monospace styling, their "Reference" inline meta |
| `Copilot.tsx` | (not yet) | **PR-8 reference**: use their suggested-prompts pattern + their sample-response style |
| `Learn.tsx` | (PR-5) | **adopt fully**: their lesson data structure (slug · minutes · body[heading, paragraph]) becomes our `lib/novice/lessons` schema |
| `TrackRecord.tsx` | (PR-6) | **adopt fully**: drawdown chart + equal-weight wins/losses + journal tone |
| `PaperTrading.tsx` | scaffold-only mockup | not needed — we have real backend |
| `Operator.tsx` | `/decisions`, `/signal-lab`, etc | reference for their "Advanced expander" copy ("intentionally hidden") |
| `Home.tsx` | (no equivalent) | landing page — out of scope until marketing site discussion |

---

## 9. What to ship in PR-4.5 (small calm polish — optional, before PR-5)

**Scope**: token + typography upgrade across the calm-shell only.
Scoped to `.today-root`, no global impact, no logic change.

| File | Change |
|---|---|
| `apps/web/src/pages/today/today.css` | update 11 token values to Magic Patterns palette; swap `--t-font-display` to Fraunces |
| `apps/web/src/pages/today/today.css` | add font @import for Fraunces 300/400/500 weights |
| `apps/web/src/pages/today/TodayPage.tsx` | adopt their 11px uppercase 0.14em date-eyebrow + "Nothing here requires action today" footer |
| `apps/web/src/pages/today/portfolio/TodayPortfolioPage.tsx` | adopt their holdings empty state copy + position-row layout pattern |
| `apps/web/src/pages/today/pick/PickDetailPage.tsx` | adopt their `Reference` inline meta + ticker monospace styling |
| `apps/web/src/styles/primitives.css` | (NO changes — primitives already aligned) |

**Effort**: 2-3 hours focused work. CSS + small copy edits only.

**Validation**: all 4 constitutional lints + reasoning snapshot + API
payload byte-identical + row counts unchanged.

**Rollback**: 6 single-file reverts. Zero residue.

**Recommendation**: **YES — ship PR-4.5 before PR-5.** The token
upgrade compounds across every subsequent PR (PR-5 Learn / PR-6 Track
Record / PR-8 Copilot all inherit). Doing it before Learn ships saves
re-styling all Learn pages later.

---

## 10. What to ship in PR-5 (Learn Hub) — informed by mockup

**Adopt verbatim from mockup**:

1. Lesson data structure:
   ```typescript
   interface Lesson {
     slug: string;
     title: string;
     description: string;
     minutes: number;
     body: { heading?: string; paragraph: string; }[];
   }
   ```
2. Two sample lessons reusable as starter content:
   - `operating-cash-flow` (3 min, 4 paragraphs)
   - `multiple-compression` (4 min, 4+ paragraphs)
3. Index page pattern: featured term + path cards
4. Per-term page: title + minutes + body paragraphs

**Add to PR-5 scope**:
- Concept slug routes (`/learn/concept/:slug`) for the 6 concept tags
  referenced by Pick Detail (momentum, mean-reversion, valuation,
  quality, defensive, growth) — currently 404 in PR-4
- Term slug routes (`/learn/term/:slug`) for the 10 chips referenced by
  Pick Detail — currently 404 in PR-4

**Keep PR-5 effort within 1 focused day**: 5 sample lessons + 6
concept pages + 10 term pages.

---

## 11. What to ship in PR-6 (Track Record) — informed by mockup

**Adopt verbatim from mockup**:
- PageHeader pattern: eyebrow + serif title + subtitle
- "An honest history." title
- "Wins and losses, shown with equal weight." subtitle
- Drawdown chart with reference line at 0%
- Wins / losses split with equal visual weight
- Transparency note block

**Reject from mockup**:
- `generateEvolution` mock data — use real `fetchEquityCurve`
- Random equity walk — use real `paper_equity_snapshot` series

---

## 12. What to ship in PR-7+ (Copilot) — informed by mockup

The mockup's Copilot is a **reference design only**. Their responses
are hardcoded `SAMPLE_RESPONSES` keyed by lowercase substring match.
Their tone is excellent — but their architecture is a UI shell that
fakes the backend.

**Use the mockup for**:
- Layout: messages timeline + suggested-prompts chips + composer
- Tone of sample responses (after lint check)
- Animation patterns (opacity-only fade, no slide)

**Do NOT use for**:
- Implementation — Copilot backend (`/api/copilot/ask`) is a separate
  Phase L+ design effort, NOT shipped as part of PR-8 UI shell

---

## 13. Constitutional lint check on adopted copy

Phrases from mockup that need lint verification before adoption:

| Phrase | Risk | Verdict |
|---|---|---|
| "the models observed that…" | "models observe" anthropomorphism | **Borderline** — softer than "AI sees", but still imputes observation. Recommend rephrase to "Microsoft's operating cash flow growth has outpaced…" (drop "models observed") |
| "It is not a prediction. It is a noticing." | "noticing" implies agency | **Borderline** — but used in mockup as an ANTI-claim ("not a prediction"). Acceptable in context |
| "the model's view" | "model's view" implies opinion | **Reject** — fails our Tier-A "AI's view" pattern |
| "The signal emerged from a fundamental pattern, not a price move." | observational | **OK** |
| "The point of a journal is not to feel good about it" | observational | **OK** |

**Recommendation**: run the forbidden-phrase lint against any
Copilot mock content BEFORE PR-8 adoption.

---

## 14. Top 5 immediate leverage actions

1. **PR-4.5 token + Fraunces upgrade** (CSS only, 2-3 hours)
2. **PR-5 Learn Hub uses their lesson data structure** + 2 starter
   lessons verbatim (`operating-cash-flow`, `multiple-compression`)
3. **PR-5 must ship `/learn/concept/:slug` + `/learn/term/:slug`** for
   the 16 chip targets currently 404ing
4. **PR-6 Track Record adopts** their PageHeader pattern + drawdown
   chart layout
5. **Brand name decision** (`ArthOS` vs `paper`) — separate review,
   NOT a code change

---

## 15. What does NOT come from the mockup

The mockup gives us:
- ✅ Token palette refinement
- ✅ Typography selection (Fraunces)
- ✅ Page-level layout patterns
- ✅ Lesson data structure
- ✅ Tone-aligned copy lines

The mockup does NOT give us:
- ❌ Real backend data (theirs is `usePaperTrading` mock)
- ❌ Phase L reasoning envelope integration (theirs is hardcoded)
- ❌ Polygon live MTM wiring (we did that ourselves)
- ❌ Constitutional locks / Tier-A lint
- ❌ Cron / job_run plumbing
- ❌ Options lifecycle / canary
- ❌ HONEST-BANNER / state-label resolver

Our backend + truth infrastructure is the moat; the mockup is the
calm surface that wraps it.

---

## 16. Recommended sequence

| PR | Scope | Effort | Risk |
|---|---|---|---|
| **PR-4.5** | Token + Fraunces upgrade, scoped to `.today-root` | S (~2h) | low |
| **PR-5**   | Learn Hub: index + 5 lessons + 6 concept routes + 10 term routes | M (~1d) | low |
| **PR-6**   | Track Record full page with real equity data | S (~3-4h) | low |
| **PR-7**   | Onboarding / Risk Profile (deferred design) | M | low |
| **PR-8**   | Copilot UI shell (backend deferred) | M | medium |
| **PR-9**   | Settings | S | low |
| **PR-10**  | Advanced area containment + rename "Advanced" → "Operator" | S | low |
| **PR-11+** | Brand name decision + global token rollout to legacy routes | M | medium |

Total: ~3-4 focused days to ship PR-4.5 through PR-10.

---

## 17. Approval requested

1. **Adopt the token palette** from Magic Patterns (sand/ink/forest/coral/ochre) into `.today-root` scope only — ship as PR-4.5 before PR-5
2. **Adopt Fraunces** as `--t-font-display` (replaces Source Serif 4)
3. **Adopt the lesson data structure** + 2 starter lessons for PR-5
4. **Adopt nav structure** Today / Portfolio / Copilot / Learn / Track Record at PR-8 (when Copilot lands); keep current 4-item nav until then
5. **Defer brand name decision** (`ArthOS` vs `paper`) — separate review
6. **Reject** their shadows, transforms-on-hover, and mock data wiring
7. **Lint-check** every adopted copy line against Tier-A before merging

No code changes. Awaiting approval on PR-4.5 scope + the 7 decisions above.
