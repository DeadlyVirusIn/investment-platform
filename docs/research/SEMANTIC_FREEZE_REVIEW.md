# Semantic Freeze Review — User-Visible Frontend Copy

**Branch**: phase-1/ledger
**Scope**: every user-visible string under `apps/web/src/` (read-only audit)
**Date**: 2026-05-19

---

## Headline (verdict)

**No.** A material slice of user-visible copy still overstates what the
system actually does. The strongest constitutional violations cluster
in three places: (1) `lib/picks/copilot.ts` attributes seeing, suggesting,
and confidence to "AI" in the very headlines that drive the Overview/Picks
hero; (2) `components/decisions/ReasoningCard.tsx` ships frontend-generated
AI-attributed prose for empty-state surfaces — directly contradicting the
Phase L lock that "every word comes from the backend renderer"; (3) the
Options Copilot hero still labels itself "Today · AI strategist" and the
position card calls its rule output "the AI's judgment" while the lifecycle
is dormant. Outside those hotspots, the surfaces are largely honest — paper-
only banners, freshness disclosures, and the canary status block all read
truthfully. With the Class C/D items in this report addressed, the answer
flips to yes.

---

## 1. Methodology

Grepped `apps/web/src/**/*.{ts,tsx}` for each pattern group described
in the audit brief (AI agency, execution overstatement, replay/live
conflation, freshness, recommendation, dormant-as-operational,
autonomy, confidence theater). Each hit was opened and read in
context to distinguish chrome (labels, eyebrows, ARIA), code comments,
fixture data, and user-visible runtime strings. Only runtime
user-visible strings are flagged below. Code comments, test fixtures,
and CSS comments are explicitly excluded.

Surfaces already audited and fixed per the brief
(PositionsTable "Position state", PickModal "Signal", AccountingStrip
replay banner, PortfolioSnapshot scope chip, TopStrip Today P&L tooltip,
freshness.ts hint, Decisions default "live", PicksPage launcher split,
PortfolioSnapshot Polygon eyebrow) are NOT re-flagged.

---

## 2. Findings by class

| # | Class | file:line | Current wording | Why it overstates | Smallest safe replacement | Timing |
|---|---|---|---|---|---|---|
| 1 | **D** | `apps/web/src/components/decisions/ReasoningCard.tsx:31-33` | "Some trades have a clean structural pattern the AI can describe. This one doesn't. The trade is in your portfolio; we don't have a story to tell about it." | Phase L lock: every word in ReasoningCard "comes from the backend renderer; no frontend-generated prose." This is frontend prose attributing description-capacity to "the AI". | "No structured reasoning is available for this trade." | immediate |
| 2 | **D** | `apps/web/src/components/decisions/ReasoningCard.tsx:36-37` | "The AI is considering this name but hasn't acted on it yet. When it does, we'll show how it read the setup." | Same Phase L lock. Also attributes intent ("considering", "acted") to a deterministic ranker. | "No paper trade has been opened on this name yet." | immediate |
| 3 | **D** | `apps/web/src/lib/picks/copilot.ts:81` | `headline = "AI engine has no fresh suggestions";` | "Suggestions" is a Tier-A semantic neighbor of "recommendations" (which is already forbidden in research-stage copy). | `"No fresh signals from the engine"` | immediate |
| 4 | **D** | `apps/web/src/lib/picks/copilot.ts:85` | `headline = "AI is cautious today";` | Attributes emotion/stance ("cautious") to a rule-based ranker. Pattern: `AI is`. | `"No buy signals passed the threshold today"` | immediate |
| 5 | **D** | `apps/web/src/lib/picks/copilot.ts:92` | `"AI sees ${counts.buy === 1 ? "an entry opportunity" : "entry opportunities"} with favorable risk/reward. Review the highest-confidence pick first."` | "AI sees… with favorable risk/reward" is exactly the kind of editorial conviction theater the Tier-A list bans. Pattern: `AI sees`. | `"${counts.buy} symbol${...} crossed the buy threshold. Review the highest-confidence row first."` | immediate |
| 6 | **D** | `apps/web/src/lib/picks/copilot.ts:96` | `"AI sees risk increasing on these names. Consider exiting before further deterioration."` | "Consider exiting" is direct trade advice; "AI sees risk" is agency overstatement. | `"Sell signals fired on these names. Review before next session."` | immediate |
| 7 | **D** | `apps/web/src/lib/picks/copilot.ts:100` | `"Mixed market — AI sees both entry and exit signals. Address Sell signals first, then evaluate Buy opportunities."` | "AI sees" + "Mixed market" editorial framing. | `"Both buy and sell signals fired. Sell signals appear first in the queue."` | immediate |
| 8 | **D** | `apps/web/src/lib/picks/copilot.ts:207-209` | `case "buy": return "AI sees improving momentum and favorable risk/reward."; case "sell": return "Risk is too high or trend is broken. AI suggests avoiding or exiting."; case "trim": return "Momentum is weak and risk is rising. AI suggests reducing exposure instead of adding more.";` | Three back-to-back violations: "AI sees… favorable risk/reward", "AI suggests avoiding or exiting", "AI suggests reducing exposure". All three are direct trade advice attributed to AI. | `buy: "Trend and momentum both crossed the buy threshold."; sell: "Trend or risk thresholds breached."; trim: "Momentum weakened relative to entry."` | immediate |
| 9 | **D** | `apps/web/src/lib/picks/copilot.ts:279` | `"Risk is elevated and AI sees no remaining upside. Address this before reviewing other ideas."` | "AI sees no remaining upside" is exactly the conviction theater the forbidden-list blocks ("risk/reward is attractive", inverted). | `"Risk is elevated and the upside trigger no longer holds. Review first."` | immediate |
| 10 | **C** | `apps/web/src/components/portfolio/PositionsTable.tsx:155-156` | "real-time P&L, return %, premium income (where applicable), and AI-suggested next steps for each name." | "real-time P&L" is unsupported (Polygon is 15-min delayed). "AI-suggested next steps" — the column is deterministic threshold logic, not AI. Empty-state copy that promises something the live state doesn't deliver. | "open P&L, return %, premium income (where applicable), and position state for each name." | immediate |
| 11 | **C** | `apps/web/src/components/portfolio/CommandBar.tsx:117-121` | "Your AI Investing OS is ready / Connect a paper portfolio or run the recommendation engine to start tracking NAV, P&L, premium income, and AI posture in real time." | "real time" — false (15-min delay + EOD bars). "AI Investing OS" is product branding but appears in the empty-state body. "AI posture" is fine elsewhere as a label, but the "in real time" promise contradicts the data layer. | "Your paper-trading workspace is ready / Connect a paper portfolio or run the engine to start tracking NAV, P&L, premium income, and posture as it refreshes." | immediate |
| 12 | **C** | `apps/web/src/components/portfolio/StrategyModules.tsx:109` | "Track trades for this strategy to activate win rate, premium, and AI next-action." | Same "AI next-action" framing as PositionsTable (already fixed). The deterministic next-step is not AI. | "Track trades for this strategy to activate win rate, premium, and position state." | immediate |
| 13 | **C** | `apps/web/src/components/copilot/VerbPill.tsx:25` | `aria-label={`AI recommendation: ${verb}`}` | The verb is a state label, not a recommendation. The comment on line 5-9 explicitly says "The verb is a label of state, NOT a button." The ARIA label contradicts the comment. | `aria-label={`Signal: ${verb}`}` | immediate |
| 14 | **C** | `apps/web/src/components/portfolio/PortfolioSnapshot.tsx:239` | `AI posture: <strong>{data.posture}</strong>` | "Posture" is fine; "AI posture" attributes the posture computation to AI when it's derived from rule-based regime classification. Inline label, hero-adjacent. | `Posture: <strong>{data.posture}</strong>` | immediate |
| 15 | **C** | `apps/web/src/components/options/copilot/OptionsHeroPulse.tsx:159` | `<div className="opt-narrative-eyebrow">Today · AI strategist</div>` | Options lifecycle is dormant (OPTIONS_ENABLED=false). Labeling the hero eyebrow "AI strategist" while there are zero options trades, no fills, no closes is dormant-as-operational. | `<div className="opt-narrative-eyebrow">Today · options engine</div>` | immediate |
| 16 | **C** | `apps/web/src/components/options/copilot/OptionsResearchUnderlyingCard.tsx:55` | `<span className="opt-research-posture-eyebrow">AI posture</span>` | Same as #14 — eyebrow on a research card while options is dormant. | `<span ...>Engine posture</span>` | immediate |
| 17 | **C** | `apps/web/src/components/options/copilot/EducationalDrawer.tsx:95` | `<div className="opt-edu-eyebrow">AI Strategist · explanation</div>` | "AI Strategist" branding on an explanation drawer when the strategist is rule-based and options lifecycle is dormant. | `<div ...>Strategy explanation</div>` | post-options-canary |
| 18 | **C** | `apps/web/src/components/options/copilot/OptionsThesisEvolutionDrawer.tsx:105,148` | "AI Strategist · thesis evolution" + "Why the AI proposed this ({n})" | Two hits in one drawer. "AI Strategist" branding, and "Why the AI proposed this" attributes proposal to AI. | "Thesis evolution" + "Why this strategy was proposed ({n})" | post-options-canary |
| 19 | **C** | `apps/web/src/components/options/copilot/OptionsPositionCard.tsx:156` (rendered string sourced from `item.guidance.reason`, but the comment locks the intent) | "guidance.reason (the AI's judgment, one line)" — backend field; the user-visible text is whatever `guidance.reason` returns. | The COMMENT documents this as "the AI's judgment" — if backend renderers follow that label, the user-visible string is mislabeled. Needs verification but likely a propagating issue. | Worth a follow-up audit of `guidance.reason` content. The card itself does not have visible "AI" chrome but the upstream contract may. | post-options-canary |
| 20 | **C** | `apps/web/src/components/picks/Briefing.tsx:43` | `<span className="picks-briefing-eyebrow">Today's AI briefing</span>` | Eyebrow that pairs with Briefing headlines (already flagged in #3-#9). "Today's AI briefing" frames the whole panel as AI-authored when the body strings are deterministic templates. | `<span ...>Today's read</span>` | immediate |
| 21 | **C** | `apps/web/src/components/picks/PickModal.tsx:180,185,226` | "AI Research Cockpit" / "AI suggestion" fallback / `<h4>AI's reasoning</h4>` | Three hits. The modal already (per brief) renamed "Recommendation" → "Signal" for research-stage rows. But the eyebrow still says "AI Research Cockpit", the engine-version fallback says "AI suggestion", and the reasoning section header is "AI's reasoning" — none of which is sourced from a backend renderer for research-stage rows. | "Research Cockpit" / "Signal" / `<h4>Reasoning</h4>` | immediate |
| 22 | **C** | `apps/web/src/components/copilot/AIReadHero.tsx:21` | `Today's AI Read` | Persistent hero label. The brief notes (line 7-8) "the only persistent surface where 'AI' appears as page chrome" — locked by design. Class C downgraded to A on grounds of explicit design carve-out. Listed here only for completeness; no change recommended. | (no change) | — |
| 23 | **B** | `apps/web/src/components/portfolio/TodayPanel.tsx:63` | `<span className="today-eyebrow">AI summary</span>` | "AI summary" eyebrow for a panel that just shows posture + body. Mild — but the body text is template-derived, not AI-generated. | `<span ...>Today's summary</span>` | post-options-canary |
| 24 | **C** | `apps/web/src/lib/copilot/conviction_compose.ts:46,48,55,89,91,100,102` | PROOF fixture data containing "AI capex absorption", "AI capex risk", "AI infrastructure", "AI ROI" etc. inside `decisionSentence`/`thesis.driver` fields. | These are FIXTURES (line 7 comment: "Phase 10G replaces fixtures with composer reading paper_position + recommendation"). They render TODAY in `ConvictionHero` until 10G ships. The phrases themselves are fine ("AI capex" referring to NVDA/MSFT data-center spend is editorially valid) but they read as the system attributing market commentary to itself. | Hold — these are fixtures and the file is marked for replacement. Flag only if fixtures persist past 10G ship. | deferred |
| 25 | **C** | `apps/web/src/lib/picks/copilot.ts:82` | `"The recommendation engine has not produced any results recently. Check engine health or try again shortly."` | "recommendation engine" — the backend is a ranker producing signals; the system has explicitly moved away from calling research-stage rows "recommendations" (PickModal lock). | `"The signal engine has not produced results recently. Check engine health."` | immediate |
| 26 | **B** | `apps/web/src/components/options/OptionsLearningGate.tsx:98` | `<span className="opt-card-meta is-pos">active</span>` | Labels the learning desk as "active" when it has only met thresholds; the surrounding body text (lines 100-104) clarifies "Aggregate insights are computed at runtime in a later phase. For now the page acknowledges activation without displaying placeholder numbers." Adequate context — but the standalone "active" chip overstates. | `<span ...>thresholds met</span>` | post-options-canary |
| 27 | **B** | `apps/web/src/components/options/OptionsHealthTriage.tsx:80` | `observed: i.shadow_persistence_active ? "active" : "paused"` | Renders "active" for the shadow persistence health check. Correct in isolation but pairs with #15-18 to give a misleading impression that options is operational. Adequate context elsewhere (paper-only banner). | (no change required if banner remains) | deferred |
| 28 | **B** | `apps/web/src/components/options/OptionsCanaryStatus.tsx:111` | `"active · accepting promotions"` | When `OPTIONS_CANARY_ENABLED=false` and Gate 5 is paused, no canary portfolio should report "active · accepting promotions". The conditional is on `p.active` (DB row flag), not on the global gate. | Either tie the chip to the global canary gate OR change copy to `"declared · gate pending"`. | post-options-canary |
| 29 | **A** | `apps/web/src/components/options/OptionsStatusBanner.tsx:7-13` | "Options engine is active — N shadow decisions, M paper trades…" (backend-sourced sentence) | The backend renders this for an "active" engine_state; today engine_state is "dormant" so this branch is unreachable. Listed for completeness. | (no change) | — |
| 30 | **A** | `apps/web/src/components/options/OptionsPaperOnlyBanner.tsx:28-36` | "Options lifecycle is currently dormant / No simulated options trades are running…" | Exemplary honest banner. Calls out the truth directly. | (no change) | — |
| 31 | **A** | `apps/web/src/components/options/copilot/OptionsLiveStateChip.tsx:30-33` | "Shadow only · Engine observes; no paper or live execution" / "Canary armed · Single-portfolio paper canary active" / "Broad execution · Full paper-execution gate is on" | "Broad execution" while still inside paper-only land is mildly imprecise — but the parent state-machine guards keep it unreachable under current flags. Adequate. | (consider "Broad paper execution" for the live branch when it becomes reachable) | deferred |
| 32 | **C** | `apps/web/src/components/copilot/ActivityStream.tsx:64,66` | `aria-label="AI activity since your last visit"` + `<h4 className="ux13-activity-label">AI activity</h4>` | Labels a stream of system actions (rotations, promotions, fills) as "AI activity" when each row is a deterministic state transition. Hero-adjacent (UX-13 living env). | `aria-label="System activity since your last visit"` + `<h4>System activity</h4>` | post-options-canary |
| 33 | **C** | `apps/web/src/lib/ui/page_flow.ts:29,38,46` | `what: "Snapshot, AI posture, top action, launchers…"` / `why: "All AI recommendations, grouped by what to do."` / `why: "Audit how the AI reached a recommendation."` | Three hits inside the FLOW step descriptions that surface in nav tooltips / page-flow hints. "All AI recommendations" — research-stage rows are signals, not recommendations. "Audit how the AI reached a recommendation" — the chain is deterministic; "reached" implies inference. | "All current signals, grouped by action." / "Audit how each signal was scored." | immediate |
| 34 | **B** | `apps/web/src/pages/PicksPage.tsx:238,268` | `title="Could not load AI recommendations"` + `eyebrow="Review AI Signals"` | "AI recommendations" in an error toast title. "Review AI Signals" eyebrow on a launcher. Mild — both are chrome that pair with the cleanup elsewhere. | `title="Could not load signals"` + `eyebrow="Review signals"` | post-options-canary |
| 35 | **B** | `apps/web/src/components/shell/SideNav.tsx:28` | `<div className="u-caption text-fg font-semibold">AI Investing OS</div>` | Product branding in the sidebar. Acceptable as branding if the rest of the UI matches the truth; flagged because "AI Investing OS" sets an expectation that everything inside is AI-driven (it isn't — most of it is rules + ranking). | (no change required if treated as branding; consider "Paper Investing OS" or just "Investing OS" to align with paper-only reality) | deferred |
| 36 | **A** | `apps/web/src/lib/ui/disclaimers.ts:14-26` | "This system provides AI-generated research, signals, and …" / "AI-generated research signal · paper trading only · educational use only · not financial advice." | Disclaimer text — explicit framing as research, paper-only, not advice. Truthful. | (no change) | — |
| 37 | **A** | `apps/web/src/components/personal/OpenPositionsPnLCard.tsx:69-70` | "All open positions are recovered replay rows — NOT live trading activity. Live unrealized headline below will read zero until live trades open." | Exemplary disclosure of replay vs live conflation. Truthful. | (no change) | — |
| 38 | **B** | `apps/web/src/lib/copilot/copy.ts:53` | "Stop-losses and take-profits are deterministic — the strategy closes the trade automatically when one triggers." | "Automatically" is correct (cron-driven); but a novice could read "automatically" as "instantly". Pairs with the 03:30 UTC TZ misconfig — closes happen once per day. | "Stop-losses and take-profits are deterministic — the strategy closes the trade at the next daily cycle when one triggers." | post-options-canary |
| 39 | **C** | `apps/web/src/components/copilot/IntradayContextLine.tsx:108,110,114` | `Today aligned · ${symbol} ${pct} vs morning thesis` / `Today drifting · ${symbol} ${pct}, watching` / `Today under stress · ${symbol} ${pct} vs entry${driftClause}` | "vs morning thesis" — no morning-thesis artifact exists in the data layer; the comparison is intraday vs entry. "watching" is calm but "Today under stress" is mild editorial overstatement. | `Aligned with entry · ${symbol} ${pct}` / `Drifting from entry · ${symbol} ${pct}` / `Below entry · ${symbol} ${pct}${driftClause}` | post-options-canary |
| 40 | **A** | `apps/web/src/components/portfolio/TodayPanel.tsx` body composition | `Today's read` derived from briefing — pairs with #20. | (no separate flag) | — |
| 41 | **C** | `apps/web/src/lib/picks/copilot.ts:148` (rendered text — see lines 234) | `"high-confidence": "≥70% confidence"` (filter label) | The percentage is shown in the filter label; the system has elsewhere removed numeric confidence (PickModal). Inconsistent: filter shows ≥70% while modal shows conviction band. | `"high-confidence": "Higher conviction"` | post-options-canary |

Total flagged: **41**. By class:
- **D** (constitutional violations): 9 (items 1-9)
- **C** (trust-breaking): 18
- **B** (confusing but defensible): 8
- **A** (already honest / by-design / fixture): 6

---

## 3. Hot zones

The density of issues clusters in three folders. By far the highest is
`apps/web/src/lib/picks/copilot.ts` — a single file that produces the
Briefing headlines and per-pick explanations consumed by the
Overview hero, Picks page, and PickModal. Nine of the nine Class D
items live in this one file (items 3-9, plus the sentence templates
at 208-209 and 279). This file is the engine of conviction theater
in the current build and is the highest-leverage cleanup target.
Second-densest is `apps/web/src/components/options/copilot/` — five
hits (items 15, 16, 17, 18, plus the upstream contract noted in 19),
all involving "AI Strategist"/"AI posture" framing while the options
lifecycle is dormant. Third is `apps/web/src/components/decisions/ReasoningCard.tsx`
(items 1-2), which is small in surface area but high in constitutional
weight — it literally violates the Phase L "every word from the backend"
lock for two empty-state branches.

---

## 4. CI-lintable patterns (forbidden_phrases_tier_a additions)

These are the Class D items from this sweep that should become
constitutional locks. Each is a phrase, regex, or token combination
that, if reintroduced, would substantively overstate system capability.

Recommended additions to `forbidden_phrases_tier_a.json`:

1. **`AI sees`** — agency overstatement; the ranker doesn't "see". Hits
   in copilot.ts lines 92, 96, 100, 207, 279. Pattern: `/\bAI\s+sees\b/i`.
2. **`AI suggests`** — recommendation overstatement attributed to AI.
   Hits in copilot.ts lines 208, 209. Pattern: `/\bAI\s+suggests?\b/i`.
3. **`AI is cautious`** / **`AI is confident`** / **`AI is considering`**
   — emotional/intent attribution to a rule-based ranker. Hits in
   copilot.ts line 85 and ReasoningCard.tsx line 36. Pattern:
   `/\bAI\s+is\s+(cautious|confident|considering|worried|optimistic|bullish|bearish)\b/i`.
4. **`AI engine has no fresh suggestions`** — "suggestions" is a
   semantic neighbor of forbidden "recommendations" in research-stage
   copy. Hit in copilot.ts line 81. Narrower pattern:
   `/\bAI\s+(engine|model)\s+has\s+/i` paired with "suggestions|recommendations".
5. **`the AI can describe`** / **`the AI proposed`** / **`how the AI reached`**
   — capability/agency attribution in non-hero, non-decision-log surfaces
   (voice_composer already restricts "AI" to those two surfaces; these
   are leaks into ReasoningCard and page_flow). Hits in ReasoningCard.tsx
   lines 31, 36; OptionsThesisEvolutionDrawer.tsx line 148; page_flow.ts
   line 46. Pattern: `/\bthe\s+AI\s+(can|will|has|proposed|reached|chose|decided|saw|sees)\b/i`.
6. **`AI's reasoning`** / **`AI's judgment`** — possessive framing of
   deterministic outputs. Hits in PickModal.tsx line 226;
   OptionsPositionCard.tsx comment line 156 (upstream contract).
   Pattern: `/\bAI'?s\s+(reasoning|judgment|view|opinion|read)\b/i`.

**Carve-outs to preserve** (do not block):
- `AIReadHero.tsx` line 21 — the "Today's AI Read" hero label is a
  declared constitutional carve-out (line 7-8 comment).
- `voice_composer.ts` surfaces tagged `hero` and `decision-log` are
  explicitly allowed to attribute. The new patterns should fire on
  the OTHER surfaces only — same as the existing AI-word rule there.
- `lib/ui/disclaimers.ts` — uses of "AI-generated research" are
  explicit truth-statements, not overstatements.

Recommend adding these six patterns to the Tier-A list and running a
post-add lint sweep to surface any incidental hits.

---

## 5. Timing distribution

- **immediate** (block before broader user exposure): items 1-16, 20, 21, 25, 33. These are Class D + the highest-leverage Class C strings on the most-trafficked surfaces (Overview hero, Picks, PositionsTable empty state, CommandBar empty state, Options hero eyebrow).
- **post-options-canary** (clean up before options engine is reactivated): items 17, 18, 23, 26, 28, 32, 34, 38, 39, 41. These mostly involve options-copilot "AI Strategist" branding and a few non-critical chrome strings.
- **deferred** (track in backlog; no urgency under current flags): items 24 (10G replaces fixtures), 27, 31, 35. Fixtures that ship until composer replacement, branding decisions, and unreachable state-machine branches.

---

## Appendix — files inspected (top-level)

`pages/`: Overview, PicksPage, PaperPortfolio, PaperOperator, Portfolio,
PortfolioTerminal, PortfolioSetup, PortfolioIntelligencePage, Decisions,
SignalLabPage, ResearchLab, ActionQueuePage, Briefing, Ops, Settings,
StrategiesPage, RiskDashboard, Research, Recommendations, plus all
27 files under `pages/options/`.

`components/`: copilot/ (incl. ReasoningCard, ConvictionHero, AIReadHero,
ActivityStream, VerbPill, ConditionBlock, IntradayContextLine, PositionStoryCard,
TodayPanel, LifecycleRibbon), decisions/ReasoningCard.tsx, picks/
(PickModal, Briefing, OverviewHero, ActionQueue, OverviewHero),
portfolio/ (PositionsTable, CommandBar, PortfolioSnapshot, StrategyModules,
HealthRail, TodayPanel), personal/ (OpenPositionsPnLCard, OpenPositionsTable,
TradeLifecycleCard, PerformanceVisibilityCard, MLReadinessPanel), novice/
PageGuide, ops/ (IntradayShadowHealthCard, HybridReadinessCard), shell/
(SideNav, Shell, MarketTicker), plus all 70+ files under `components/options/`.

`lib/`: copilot/copy.ts, copilot/conviction_compose.ts,
copilot/voice_composer.ts, picks/copilot.ts, picks/freshness.ts,
picks/api.ts, ui/disclaimers.ts, ui/page_flow.ts, ui/guidance.ts,
novice/glossary.ts, market/hooks.ts, insights/types.ts,
replay/readiness.ts, alpha/context.ts, alpha/calibration.ts,
options/setupQuality.ts.

`__tests__/`: scanned for forbidden-token assertions (research/researchTokenGuard.test.ts,
research/researchPhaseFUi.test.tsx); these confirm `recommend`/`buy`/`sell`
are already blocked in the research surface and validate that
`forbiddenTokens.ts` is the right place to extend.
