# Full Product Page Design Map

**Date**: 2026-05-20
**Status**: PLAN ONLY — no implementation, no scope expansion
**Direction**: warm premium investing mentor; calm typography; clear
cards; learning-first; simple navigation. Uses uploaded mockup as
visual reference, NOT factual copy.

## Hard truth constraints (locked across every page below)

| Lock | Enforcement |
|---|---|
| No fake confidence % | Tier-A lint (30 phrases) |
| No fake win-rate | Design: never render a top-line "X-day winning streak" |
| No "real-time alerts" unless wired | Design: never use the phrase "real-time" |
| No options execution language until canary proves it | HONEST-BANNER lock |
| No live-trading implication | Every NAV labeled "Paper" somewhere |
| No "AI sees / AI suggests / AI is …" | Tier-A lint |
| Polygon estimates must say "delayed 15 min" | Phase 1b lock |
| Official snapshots distinct from live | Dual-display lock |
| Recommendations are "Signals" unless backed by paper_trade | UI-1 lock |
| Reasoning prose sourced from backend renderer only | Phase L lock |

---

## Page 1 — Today (`/today`)

| Attribute | Value |
|---|---|
| Purpose                            | First-30-second orientation surface |
| Target feeling                     | Calm, informed, in good hands |
| Primary user question              | "Anything I need to know today?" |
| Hierarchy (top→bottom)             | Greeting → AI Read sentence → Portfolio NAV (live + official) → One thing to look at → AI's recent moves → Learning card → Browse · Advanced |
| Components needed                  | `<TodayNav/>`, `<TodayPage/>` (shipped PR-1) + future `<AITrackRecord/>` (PR-3) + `<LearningCard/>` (PR-5) |
| Existing components to reuse       | `OverviewHero`, `EquitySparkline`, partial `PortfolioSnapshot` content (via composition not import) |
| Backend data                       | `/api/paper/summary`, `/api/paper/live-nav`, `/api/picks`, `/api/paper/executed/trades`, `/api/performance/equity-curve` |
| Copy constraints                   | observational only; no AI agency verbs; serif on greeting + AI read only |
| Hidden from novices                | engine_version, family_scores, composite_score, regime literal, P15 vocabulary |
| Mobile (390×844)                   | reading column full width; serif scales to 18px hero; section gap 24px |
| Implementation priority            | PR-1 ✅ shipped; PR-3 enriches with track record + learning |

---

## Page 2 — Portfolio (`/today/portfolio`)

| Attribute | Value |
|---|---|
| Purpose                            | "What do I own and how is each position doing?" |
| Target feeling                     | Steady journal review, not Bloomberg desktop |
| Primary user question              | "What did the AI buy for me and how is each one doing?" |
| Hierarchy                          | Hero NAV (live + official) → Holdings list (sorted by market value) → Reading-this-page learning card → Browse · Advanced |
| Components needed                  | `<TodayPortfolioPage/>` (PR-2 ✅), `<HoldingRow/>` (composed, not extracted; PR-4 may extract) |
| Existing components to reuse       | `EquitySparkline`, `Chip`, `Badge` primitives |
| Backend data                       | `/api/paper/summary`, `/api/paper/live-nav`, `/api/paper/executed/positions?is_open=true`, `/api/performance/equity-curve` |
| Copy constraints                   | "Paper portfolio" + "Live estimate" labels mandatory; return tones via dot indicator only |
| Hidden from novices                | replay_recovery flag breakdown (surfaced only on legacy operator view) |
| Mobile                              | 2-line per-row stack (symbol + qty over value + return); 14px body |
| Implementation priority            | PR-2 ✅ shipped |

---

## Page 3 — Ideas (`/ideas`)

| Attribute | Value |
|---|---|
| Purpose                            | Full signal queue with calm filtering |
| Target feeling                     | Curated, not casino |
| Primary user question              | "What is the AI seeing today, and which one matters most?" |
| Hierarchy                          | One sentence "N signals today" → Filter chips (Buy/Sell/Trim/Hold/Watch-only) → Signal cards (largest first, calm dot + symbol + plain thesis preview + reference price) → Browse · Advanced |
| Components needed                  | new `<IdeasPage/>`, new `<SignalCard/>` (replaces the existing glow-cards) |
| Existing components to reuse       | `ReasoningCard` (for inline preview), `Chip`, `Badge` primitives |
| Backend data                       | `/api/picks` (existing) |
| Copy constraints                   | "Signal" not "Recommendation"; observation only; reasoning preview is short backend-sourced thesis OR honest absence |
| Hidden from novices                | composite_score, family_scores, engine_version, raw_action |
| Mobile                              | single-column card stack; tap to open Pick Detail |
| Implementation priority            | PR-3 |

---

## Page 4 — Pick Detail (`/ideas/:symbol` or PickModal calm variant)

| Attribute | Value |
|---|---|
| Purpose                            | One-screen deep-dive on a single signal |
| Target feeling                     | Sitting with a calm analyst |
| Primary user question              | "Why is the AI flagging this?" |
| Hierarchy                          | Symbol + signal dot → **Reasoning FIRST** (full `ReasoningCard`) → Reference price (entry/target/stop, quiet) → Catalysts (if any, no fake real-time) → "Show technical detail" expander (operator-only fields collapsed) |
| Components needed                  | new `<PickDetailPage/>` (route version) and/or existing `<PickModal shellVariant="calm">` (modal version) |
| Existing components to reuse       | `ReasoningCard`, `PickModal` (with calm shellVariant) |
| Backend data                       | `/api/picks/{id}` or pick-by-symbol; existing reasoning envelope endpoint |
| Copy constraints                   | "Signal: Buy" not "Recommendation"; no engine_version chip; no family_scores in calm view (kept in expander only) |
| Hidden from novices                | composite_score, family_scores, engine_version, raw_adjusted_action |
| Mobile                              | sticky symbol + close at top; reasoning scrolls; reference price as compact 3-line block |
| Implementation priority            | PR-4 |

---

## Page 5 — Learn Hub (`/learn`)

| Attribute | Value |
|---|---|
| Purpose                            | "What do these terms mean?" + curated learning paths |
| Target feeling                     | Tutor, not Wikipedia |
| Primary user question              | "What is 'Trim' / 'Cost basis' / 'Drawdown' …?" |
| Hierarchy                          | Search input → Featured term of the day → Glossary index (alphabetical) → Learning paths (3-4 mini courses) → Browse · Advanced |
| Components needed                  | new `<LearnIndex/>`, new `<TermPage/>` (route `/learn/:slug`) |
| Existing components to reuse       | `lib/novice/glossary` data already exists |
| Backend data                       | static (glossary is in code) |
| Copy constraints                   | plain English; observational; no theatre |
| Hidden from novices                | nothing — this IS the novice surface |
| Mobile                              | full-width term list; readable line lengths |
| Implementation priority            | PR-5 |

---

## Page 6 — Copilot Chat (`/today/chat`)

| Attribute | Value |
|---|---|
| Purpose                            | Conversational explanation surface — "ask the system about itself" |
| Target feeling                     | Inquiry session with a librarian |
| Primary user question              | "Why did the AI sell X yesterday?" / "What is my exposure to tech?" |
| Hierarchy                          | Calm input bar at bottom (no autofocus) → message history (no avatars, no chat-bubble theatre) → suggested questions chips |
| Components needed                  | new `<CopilotChatPage/>`, `<ChatMessage/>`, `<SuggestedQuestion/>` |
| Existing components to reuse       | `ReasoningCard` (when chat surfaces an envelope), `Button`, `Chip` primitives |
| Backend data                       | **MISSING** — needs a new `/api/copilot/ask` endpoint that DOES NOT FABRICATE. Must be deterministic-traceable replies sourced from existing tables (envelope, decisions, paper_trade). NO open-ended LLM until that's wired. |
| Copy constraints                   | answers must cite source rows (file:line equivalent — `paper_trade.id`, `envelope_hash`); no "I think"; never invent a reason if no envelope exists for a trade |
| Hidden from novices                | raw envelope JSON, hashes |
| Mobile                              | full-screen chat surface; back arrow to Today |
| Implementation priority            | PR-8 — gated on backend `/api/copilot/ask` design which is a Phase L+ effort, NOT included in this PR sequence |

---

## Page 7 — Onboarding / Risk Profile (`/onboard`)

| Attribute | Value |
|---|---|
| Purpose                            | Capture initial risk profile + connect a paper portfolio |
| Target feeling                     | Calm first-day-at-a-private-bank |
| Primary user question              | "How does this product fit me?" |
| Hierarchy                          | Welcome sentence → 3-question risk profile (time horizon / loss comfort / experience) → "Your starting paper portfolio: $10,000" → "Continue to Today" |
| Components needed                  | new `<OnboardingPage/>`, new `<RiskQuestionCard/>` |
| Existing components to reuse       | `Button`, `Chip`, `Card` primitives |
| Backend data                       | new `paper_portfolio` row created at end (operator approval) OR mapping to an existing `Default Paper` for now |
| Copy constraints                   | No promise of returns; no scoring of "aggressive vs conservative" hype; observational |
| Hidden from novices                | strategy selection (engine picks deterministically) |
| Mobile                              | one question per screen; large tap targets; progress dots |
| Implementation priority            | PR-6 — gated on a design review of risk-profile question set; backend impact is minimal (new column on `paper_portfolio` for `risk_profile: text`); could ship without DB if persisted in localStorage initially |

---

## Page 8 — Performance / Track Record (`/today/performance`)

| Attribute | Value |
|---|---|
| Purpose                            | "How has the AI done over time?" — honest journal |
| Target feeling                     | Annual report from a calm advisor |
| Primary user question              | "Is this thing any good?" |
| Hierarchy                          | One-line summary ("Up X% since Mar 14; biggest decline −Y%") → equity curve (neutral sparkline larger) → realized P&L table (paginated, losses rendered equally) → drawdown periods → closed signals breakdown by action type |
| Components needed                  | new `<TrackRecordPage/>`, expanded `<AITrackRecord/>` (built in PR-3 as Today block) |
| Existing components to reuse       | `EquitySparkline` with `theme="neutral"`, `Chip`, `Badge` |
| Backend data                       | `/api/performance/equity-curve`, `/api/paper/executed/trades`, `/api/paper/executed/summary` |
| Copy constraints                   | losses styled same weight as gains; NO "win streak"; NO percentage larger than the portfolio number itself; no "alpha" word |
| Hidden from novices                | sharpe ratio, sortino, ulcer index (these go on operator Risk page) |
| Mobile                              | sparkline scales to width; table collapses to "symbol · outcome" rows |
| Implementation priority            | PR-7 |

---

## Page 9 — Settings (`/today/settings`)

| Attribute | Value |
|---|---|
| Purpose                            | Profile, preferences, paper portfolio choice, theme |
| Target feeling                     | Quiet utility |
| Primary user question              | "Where do I change my paper account or theme?" |
| Hierarchy                          | Account (paper portfolio name, starting cash, created date) → Display (theme: warm/dark) → Notifications (email digest cadence) → Data export → About / legal |
| Components needed                  | new `<SettingsPage/>` + form primitives (`<Input/>`, `<Toggle/>`) |
| Existing components to reuse       | `Button` (primary/quiet) |
| Backend data                       | `/api/paper/portfolios` (existing), new `/api/settings/preferences` (if wired); fallback to localStorage |
| Copy constraints                   | no marketing copy; no "premium plan upsell" |
| Hidden from novices                | engine flags, options flags, advanced toggles |
| Mobile                              | single-column form |
| Implementation priority            | PR-9 |

---

## Page 10 — Advanced / Operator Area (`/advanced/*`)

| Attribute | Value |
|---|---|
| Purpose                            | Container for operator surfaces (Decisions, Signal Lab, Alpha Lab, Ops, Risk, Agents, Diagnostics, Options operator) |
| Target feeling                     | "I asked for this; here are the controls" — utilitarian, not advertised |
| Primary user question              | "I'm an operator; show me the working." |
| Hierarchy                          | Sectioned list: Signals lab / Decisions audit / Risk / Ops / Agents / Diagnostics / Options operator. Each item is a quiet link, no badges, no glow, no metrics. |
| Components needed                  | new `<AdvancedIndexPage/>` (acts as a router gate, NOT a redesign of the operator pages themselves) |
| Existing components to reuse       | All existing operator pages mounted as-is under `<Shell/>` (legacy chrome stays for operator surfaces) |
| Backend data                       | none (links only) |
| Copy constraints                   | "Advanced" wording is intentional — operator pages keep their existing copy/tone (Bloomberg-density is acceptable here) |
| Hidden from novices                | The whole area; reachable only via `<details className="today-advanced">` from any Layer-1 page, or via direct URL |
| Mobile                              | same as desktop — operator users are unusual on mobile, accept legacy chrome |
| Implementation priority            | PR-10 — last item, mostly a routing/nav containment patch |

---

## Phased roadmap

| PR | Scope | Effort | Risk |
|---|---|---|---|
| **PR-1** ✅ shipped | TodayPage shell + design tokens + TodayNav | S | low |
| **PR-2** ✅ shipped | TodayPortfolioPage + primitives.css + PickModal calm-variant prop + EquitySparkline theme prop | S | low |
| **PR-3** | Add `<AITrackRecord/>` block to TodayPage + 4-row recent moves; uses existing endpoints only | S | low |
| **PR-4** | Build `<IdeasPage/>` with calm `<SignalCard/>` list (replaces operator picks grid on `/ideas` only — legacy `/action-queue` unchanged) | M | medium |
| **PR-5** | Build `<LearnIndex/>` + `<TermPage/>` (sources existing `lib/novice/glossary`) | S | low |
| **PR-6** | Onboarding/Risk Profile route (`/onboard`), localStorage-only first, optional `paper_portfolio.risk_profile` column later | M | low (no schema in PR-6) |
| **PR-7** | Performance/Track Record route (`/today/performance`); composes `EquitySparkline neutral` + closed-trade list | S | low |
| **PR-8** | Copilot Chat shell — UI ONLY in PR-8; backend `/api/copilot/ask` is a SEPARATE phase, gated on Phase L extensibility design | M | medium (chat without backend = empty surface) |
| **PR-9** | Settings page minimal | S | low |
| **PR-10** | Advanced area containment — `/advanced/*` route shell + nav-link audit; existing operator pages remain mounted under `<Shell/>` | S | low |

Each PR is independently revertable, follows the "additive parallel
route" pattern established in PR-1+PR-2, and touches NO backend
except the optional risk_profile column in PR-6 (deferred unless
required).

## Sequencing rationale

1. PR-3 (track record) compounds trust on the page users see first.
2. PR-4 (Ideas) needs the calm signal-card primitive; we already
   have the chip/badge/card primitives from PR-2 so it's a UI-only PR.
3. PR-5 (Learn) is small but strategically central — the product
   identity ("mentor") needs a Learn surface visible from PR-4 onward.
4. PR-6 (Onboarding) gates the first-time experience.
5. PR-7 (Performance) extends PR-3's track record into a full page.
6. PR-8 (Copilot Chat) is shell-only because the backend is not yet
   designed; we defer the backend to a separate research phase.
7. PR-9 (Settings) is utility.
8. PR-10 (Advanced) is the final containment that hides operator
   surfaces from Layer-1 nav.

## What this design map deliberately does NOT do

- ✅ No backend changes proposed except optional `risk_profile` column in PR-6 (and it's optional, localStorage-first)
- ✅ No new ML / new providers / new endpoints (Copilot Chat backend is OUT OF SCOPE for PR-8 — only the UI shell)
- ✅ No fake AI / fake real-time / fake winners-only — Track Record and Ideas pages render losses with equal visual weight
- ✅ No premium-plan / paywall / social / gamification
- ✅ No copy that would fail the 30-phrase Tier-A lint
- ✅ No options-execution implication beyond the existing HONEST-BANNER copy
- ✅ No deletion of operator surfaces — they survive under `/advanced/*` with their legacy chrome intact
- ✅ No promotion of `/today` to `/` (legacy `/` continues to redirect to `/overview`) — happens only when PRs 1-7 are validated end-to-end

## Approval requested

Approve the design map and confirm PR-3 as the next implementation
target (or redirect to a different PR). Subsequent PRs gated
individually based on operator review of the live `/today` and
`/today/portfolio` surfaces.
