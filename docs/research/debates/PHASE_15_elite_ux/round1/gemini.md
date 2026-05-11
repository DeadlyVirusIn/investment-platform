# Phase 15 Elite UX Audit — Round 1 (Gemini)

**Panelist:** Gemini CLI  
**Date:** 2026-05-11  
**Scope:** 11 core pages + shell + design system  
**Baseline:** Phase 14f-F (mobile sticky relax)

---

## 1. Page-by-Page Audit

### 1.1 Overview (/overview)
**Score: 8.5/10**

*   **Biggest strengths:** The executive briefing (Phase 14b) is a masterclass in information hierarchy. The `Subtitle` (`nav · return · posture`) provides instant context before the eye even hits the page content.
*   **Biggest weaknesses:** `PortfolioSnapshot` and `LauncherCard` grid competition. Both sections are dense with metrics, creating a "data wall" effect in the upper half of the page.
*   **Desktop-specific issues:** `LauncherGrid` feels slightly over-wide on 1680px+, losing some of the "launcher" focus.
*   **Mobile-specific issues:** Excellent stacking per Phase 14f-D, but `PortfolioSnapshot` secondary metrics (ps-secondary) can feel like a list of 10+ items to scroll through before reaching the actual signals.
*   **Novice-user issues:** "Posture: Neutral" is well-explained, but the difference between "Today's Read" and "PageChapter Now" is subtle; they almost say the same thing in different fonts.
*   **Expert-user issues:** No way to jump directly to a specific symbol from here; requires navigating to Action Queue or Portfolio.
*   **Storyline / navigation issues:** Strongest page for storytelling. It sets the "Now" effectively.
*   **Recommended structural changes:** Consider making `ps-secondary` a 2-column grid on desktop to save vertical space.
*   **Recommended visual changes:** Subtle gradient backdrop behind `LauncherGrid` to group it visually and separate it from the "Read-only" snapshot above.
*   **Recommended interaction changes:** Add a "Quick View" hover or tap for `LauncherCard` metrics to show the top 3 symbols without leaving the page.
*   **Priority ranking:** P1 (ROI)
*   **Estimated implementation complexity:** Low
*   **Regression risk:** Low

### 1.2 Events & Catalysts (/events)
**Score: 6.5/10**

*   **Biggest strengths:** The `MarketEvents` card system (apps/web/src/components/portfolio/MarketEvents.tsx:131) is clean and the sentiment-tinted news items are helpful.
*   **Biggest weaknesses:** Passive feel. It's a "read-only" log that doesn't feel connected to the "Actions" the user needs to take.
*   **Desktop-specific issues:** The `me-grid` layout can leave a lot of white space if only 2-3 symbols have active events.
*   **Mobile-specific issues:** News links are small tap targets (me-news-item a). Brief 14f-D addressed 44px targets, but these inline links are still tight.
*   **Novice-user issues:** Opaque pills (E/N/F/X). While Phase 13/14 supposedly translated some, the implementation at `MarketEvents.tsx:131` still feels like an "engine dump".
*   **Expert-user issues:** No filtering by event type (e.g., "Show me only SEC filings").
*   **Storyline / navigation issues:** It's the "Why" page, but it doesn't lead back to the "What" (Action Queue) effectively.
*   **Recommended structural changes:** Add a "Linked Signals" sidebar or section to show which events are driving which active suggestions.
*   **Recommended visual changes:** Use the action-color system (buy-green, sell-red) to tint event cards where a specific symbol has a matching signal.
*   **Recommended interaction changes:** Filtering by event type and sentiment.
*   **Priority ranking:** P1 (High ROI)
*   **Estimated implementation complexity:** Medium
*   **Regression risk:** Low

### 1.3 Action Queue (/action-queue)
**Score: 9.0/10**

*   **Biggest strengths:** The most functional "desk" in the app. The "Why no buys?" panel (ActionQueuePage.tsx:112) is a brilliant piece of AI-native UX that prevents the "empty state anxiety".
*   **Biggest weaknesses:** `FilterBar` (apps/web/src/components/picks/FilterBar.tsx) uses a non-standard tab role that breaks keyboard expectations (as flagged in Phase 12 consensus).
*   **Desktop-specific issues:** Large vertical gaps between groups (Buy vs Trim) can hide content on shorter laptop screens.
*   **Mobile-specific issues:** `ActionQueue` skeleton (Phase 14c) is excellent, but the `HealthRail` at the bottom is easy to miss.
*   **Novice-user issues:** "Posture" and "Confidence" are prominent, but "Why this symbol?" is buried in the `PickBox` body.
*   **Expert-user issues:** No "Execute All" or "Mark as Reviewed" flow; feels like a static list even though it's a "queue".
*   **Storyline / navigation issues:** Excellent. It's the "What to do" page.
*   **Recommended structural changes:** Move `HealthRail` metrics into a sticky footer or TopStrip slot on mobile.
*   **Recommended visual changes:** Stronger contrast between "Action" groups (Buy/Sell) using background color-mix.
*   **Recommended interaction changes:** Fix the `FilterBar` keyboard navigation.
*   **Priority ranking:** P0 (Critical)
*   **Estimated implementation complexity:** Low (for the P0 fix)
*   **Regression risk:** Low

### 1.4 Signal Lab (/signal-lab)
**Score: 5.0/10**

*   **Biggest strengths:** The "Readiness Score" (SignalLabPage.tsx:43) is an honest, quantitative measure of system health.
*   **Biggest weaknesses:** "Not yet wired" sections (SignalLabPage.tsx:150). It feels like a construction site.
*   **Desktop-specific issues:** Massive empty states make the page feel broken or disconnected.
*   **Mobile-specific issues:** The Readiness Score card takes up the entire first fold, hiding the fact that nothing else is on the page.
*   **Novice-user issues:** Technical jargon (freshness ratio, event coverage) without tooltips or deep-dives (though `ExpertDetails` at line 114 helps).
*   **Expert-user issues:** No ability to see the raw symbols driving the readiness score.
*   **Storyline / navigation issues:** "Dead end" page. It tells you the engine is ready, but doesn't help you *do* anything.
*   **Recommended structural changes:** Merge this into the "Ops" or "Research" page unless the backtest validation is shipped immediately.
*   **Recommended visual changes:** Use a "gauge" or "dial" visual for readiness to make it feel more "lab-like".
*   **Recommended interaction changes:** Clickable metrics that drill down into the symbol lists (e.g., "Click the 48 stale symbols to see them").
*   **Priority ranking:** P2 (Polish/Wait)
*   **Estimated implementation complexity:** High (to actually wire it)
*   **Regression risk:** Low

### 1.5 Decisions (/decisions)
**Score: 7.5/10**

*   **Biggest strengths:** The "Calm Card" (Decisions.tsx:505) is the best "AI Moderator" implementation in the project. It handles the "is this okay?" question perfectly.
*   **Biggest weaknesses:** Nested scroll regions (Decisions.tsx:237+) are a nightmare on mobile, even with Phase 14 fixes.
*   **Desktop-specific issues:** The 3-column layout is fixed-width (360px / flex / 420px), which feels cramped on 1080p.
*   **Mobile-specific issues:** High cognitive load. It's impossible to see the "Timeline" and "Detail" at once.
*   **Novice-user issues:** "Engineering snapshot" (line 424) is scary even with the "Safe to ignore" warning.
*   **Expert-user issues:** Searching for a specific symbol in the timeline is missing.
*   **Storyline / navigation issues:** Great at explaining the "Past", but doesn't link forward to "Portfolio" results well.
*   **Recommended structural changes:** Convert the 3-column layout to a "Master-Detail" view on mobile where clicking a timeline entry navigates to a sub-route.
*   **Recommended visual changes:** Use the same "Action" colors (green/red) in the timeline entries to match the rest of the app.
*   **Recommended interaction changes:** Standardized scroll containers; remove the `h-[calc(100vh-240px)]` constraint for a natural page scroll on smaller viewports.
*   **Priority ranking:** P1 (High ROI)
*   **Estimated implementation complexity:** Medium
*   **Regression risk:** Medium

### 1.6 Strategies (/strategies)
**Score: 7.0/10**

*   **Biggest strengths:** Educational content (Phase 14f-E) is now properly balanced via `ExpertDetails`.
*   **Biggest weaknesses:** Passive data tables. It's a "Look at what I'm doing" page rather than "Here is how you execute".
*   **Desktop-specific issues:** The page is very vertical. It feels like a long scroll of 3-4 distinct apps.
*   **Mobile-specific issues:** Tables lack `u-table-wrap` (as flagged in Phase 12).
*   **Novice-user issues:** The "Wheel" vs "LEAPS" list is great, but it doesn't tell the user *which one* to use for a specific signal on the Action Queue.
*   **Expert-user issues:** No configuration or "Strategy Builder" features.
*   **Storyline / navigation issues:** "Next Step" link (line 100) to Options is the right logical thread.
*   **Recommended structural changes:** Group "Trade Lifecycle" and "Premium Income" into a single "Performance" section.
*   **Recommended visual changes:** Stronger visual cues for "Open" vs "Closed" trades in the lifecycle view.
*   **Recommended interaction changes:** Filtering the lifecycle table.
*   **Priority ranking:** P1 (High ROI)
*   **Estimated implementation complexity:** Low
*   **Regression risk:** Low

### 1.7 Options (/options/*)
**Score: 4.5/10**

*   **Biggest strengths:** Deep, honest data. No fake "Profit/Loss" graphs that don't track real Greeks.
*   **Biggest weaknesses:** **Cognitive Overload.** 12 tabs is too many. The navigation (OptionsLayout.tsx:36) uses a different visual style (amber borders) than the rest of the app.
*   **Desktop-specific issues:** Tabs wrap into multiple rows on narrower desktop windows, breaking the "Terminal" feel.
*   **Mobile-specific issues:** Completely broken ergonomics. 12 tabs on mobile require horizontal scrolling or a wrap that takes up half the screen.
*   **Novice-user issues:** "Decision Support" vs "Decision Framing" vs "Evaluation" — what is the difference?
*   **Expert-user issues:** The most "Developer Built" section of the app. Hard-coded Zinc/Tailwind classes everywhere.
*   **Storyline / navigation issues:** It feels like a separate app. The "FLOW" thread is lost here.
*   **Recommended structural changes:** Consolidate 12 tabs into 4: **Overview** (landing), **Trade Desk** (Chain + Trades + Risk), **Analysis** (Diagnostics + Evaluation + Support), and **Scenario** (Replay + Observatory).
*   **Recommended visual changes:** Standardize navigation to match `SideNav` or `TopStrip` aesthetics. Remove `border-amber-400`.
*   **Recommended interaction changes:** Mobile-optimized tab drawer or "Select" menu.
*   **Priority ranking:** P0 (Critical)
*   **Estimated implementation complexity:** High
*   **Regression risk:** High

### 1.8 Portfolio (/portfolio)
**Score: 7.0/10**

*   **Biggest strengths:** `CopilotHoldings` (brief view) is the most "Elite AI" part of the product. The storytelling focus is world-class.
*   **Biggest weaknesses:** The "Split Personality" between `?view=brief` and `?view=working`. They feel like two different products.
*   **Desktop-specific issues:** `PortfolioTerminal` (working view) is very dense and wastes horizontal space on 2k monitors.
*   **Mobile-specific issues:** `PortfolioTerminal` tables clip on phones (PortfolioTerminal.tsx:288+).
*   **Novice-user issues:** Switching between views is a small underline link (CopilotHoldings.tsx:103); novices might get stuck in one and miss the other.
*   **Expert-user issues:** `CopilotHoldings` is too "story-heavy" for someone who just wants to see their exit price.
*   **Storyline / navigation issues:** Good, but needs a "PageChapter" on the legacy route.
*   **Recommended structural changes:** Use a toggle switch (like the Density toggle) to flip between "Brief" and "Working" views rather than a hidden link.
*   **Recommended visual changes:** Add `PageChapter` to `PortfolioTerminal`.
*   **Recommended interaction changes:** Table overflow wrappers.
*   **Priority ranking:** P1 (High ROI)
*   **Estimated implementation complexity:** Low
*   **Regression risk:** Low

### 1.9 Risk (/risk)
**Score: 6.0/10**

*   **Biggest strengths:** The `deriveRiskCalmState` (RiskDashboard.tsx:142) logic is mathematically sound and provides genuine reassurance.
*   **Biggest weaknesses:** "Generate Explanation" (RiskDashboard.tsx:88) button is hidden in a corner; should be a primary action.
*   **Desktop-specific issues:** Tables in "Concentration" are tiny compared to the "Account Value" cards above.
*   **Mobile-specific issues:** Data tables clip. "Focus Today" list is long.
*   **Novice-user issues:** "Notional" and "Unrealized" are technical terms that need better labels in the tables.
*   **Expert-user issues:** No "Stress Test" or "What-if" tools.
*   **Storyline / navigation issues:** It's the "End" of the funnel, but it should lead back to "Overview" for the next day's prep.
*   **Recommended structural changes:** Make the "Narrative/Explanation" the hero of the page once it's generated.
*   **Recommended visual changes:** Tokenize the zinc Tailwind classes.
*   **Recommended interaction changes:** Table overflow.
*   **Priority ranking:** P1 (High ROI)
*   **Estimated implementation complexity:** Low
*   **Regression risk:** Low

### 1.10 Alpha Lab (/research)
**Score: 5.5/10**

*   **Biggest strengths:** The "Shadow Signal Registry" (ResearchLab.tsx:116) is a great transparency feature.
*   **Biggest weaknesses:** "Patterns" tab is very dry. It's just a few big numbers.
*   **Desktop-specific issues:** The "Wins" and "Losses" lists are very narrow.
*   **Mobile-specific issues:** Tab navigation is custom and doesn't match the shell.
*   **Novice-user issues:** It's labelled "Experimental" (line 42) but still contains a lot of numbers that a novice might misinterpret as "Live".
*   **Expert-user issues:** No way to export this data.
*   **Storyline / navigation issues:** Fragmented.
*   **Recommended structural changes:** Move "Patterns" to the "Signal Lab" as that's where "Readiness" is discussed.
*   **Recommended visual changes:** Use the same "Action Queue" colors for wins (green) and losses (red).
*   **Recommended interaction changes:** Clickable pattern cards to see the trades within them.
*   **Priority ranking:** P2 (Polish)
*   **Estimated implementation complexity:** Medium
*   **Regression risk:** Low

### 1.11 Ops (/ops)
**Score: 5.5/10**

*   **Biggest strengths:** `SystemHealthCard` and `DailyLoopHealthCard` provide great operational transparency.
*   **Biggest weaknesses:** Total information overload. 15+ cards on one page.
*   **Desktop-specific issues:** The "Anchor Nav" (line 220) is helpful but the page is still too long.
*   **Mobile-specific issues:** It's a "Scroll of Death".
*   **Novice-user issues:** "FRED Ingest" and "Anomaly Scan" (line 257) are meaningless to anyone but a developer.
*   **Expert-user issues:** No "Trigger Manual Run" button.
*   **Storyline / navigation issues:** It's "Pro View" but it's part of the main nav.
*   **Recommended structural changes:** Group cards into 3 collapsible sections per the Phase 12 consensus (Live / ML / Engine).
*   **Recommended visual changes:** Dim or recede the engineering-heavy cards.
*   **Recommended interaction changes:** Collapsible sections.
*   **Priority ranking:** P1 (High ROI)
*   **Estimated implementation complexity:** Low
*   **Regression risk:** Low

---

## 2. Cross-Product Findings

### A. Navigation Inconsistencies
*   **The "Three Navs" Problem:** We have `SideNav` (primary), `Options` tabs (amber border), and `Alpha Lab` tabs (custom underline). They all look and feel different.
*   **Route Logic:** Some pages use `?view=` (Overview/Portfolio) while others use nested routes (Options). This makes the browser "Back" button behavior unpredictable.

### B. Typography & Density
*   **Inter Overload:** We use Inter for everything. While it's a great font, the "Elite" feel would benefit from a Serif (Source Serif 4) for AI-narrative blocks (PageChapter, Calm Cards, Copilot Stories).
*   **Density Toggle:** It's only truly implemented on Phase 11/14 pages. Legacy pages (Decisions, Risk, Ops) ignore it, creating a jarring "jump" in scale when navigating.

### C. Interaction Debt
*   **Hover states:** Many cards (`LauncherCard`, `PickBox`) have beautiful hover effects, but the "older" cards in Ops/Risk are static.
*   **Loading:** Some pages use skeletons (Action Queue), others use "Loading..." text (Signal Lab, Portfolio).

---

## 3. Elite-Gap Analysis: Why this isn't 10/10 yet

The product currently feels like a **high-end developer tool** rather than a **world-class AI-native product**. 

1.  **The "Wall of Cards" syndrome:** Every page is a grid of cards. World-class products (Linear, Stripe) use varied layouts to direct focus.
2.  **Missing "AI Presence":** The AI is behind the scenes (the "Engines"), but it doesn't feel "present" in the UI. The "Calm Cards" are a great start, but we need more ambient signal (e.g., subtle motion in TopStrip when the engine is thinking).
3.  **Data Isolation:** I can't click a symbol in "Risk" and see its "Catalysts" or its "Strategy" instantly. The silos are too thick.
4.  **Mobile Polish:** The mobile experience is "responsive" (functional) but not "optimized" (designed for thumbs).

---

## 4. Phase 15/16/17 Roadmap

### Phase 15: The Consolidation (UX Impact + Implementation Safety)
1.  **Consolidate Options Navigation:** Reduce 12 tabs to 4 top-level sections; move to a mobile-friendly switcher.
2.  **Universal Density:** Apply the `data-density` tokens to the remaining 5 legacy pages (Decisions, Risk, Research, Ops, Options).
3.  **Table Safety:** Wrap all remaining tables in `u-table-wrap`.

### Phase 16: The Narrative Lift (Novice Clarity + Trustworthiness)
1.  **The Serif Spike:** Introduce `Source Serif 4` for all AI-generated narrative blocks (`PageChapter`, `Calm Cards`, `Copilot stories`).
2.  **Interactive Calm Cards:** Make the "Calm Cards" actionable (e.g., "Drawdown is high" -> click to filter Risk table to outliers).
3.  **Action Queue "Execute" Loop:** Add a "Reviewed" state to signals to help users track their work.

### Phase 17: The "Elite" Feel (Mobile Quality + Visuals)
1.  **SideNav Redesign:** Convert the mobile drawer into a more gestural "Bottom Sheet" or modern drawer with better thumb targets.
2.  **Ambient AI Signal:** Add subtle, non-distracting motion to `TopStrip` and `StatusRail` to indicate background pipeline activity.
3.  **Cross-Link Registry:** Implement a "Global Symbol Navigator" to break the silos between Risk/Portfolio/Catalysts.

---

## 5. Answers to the 12 Specific Questions

1.  **Coherent Story?** 80% there. Overview → Action Queue is strong. Options and Ops feel like footnotes.
2.  **Linear/Intelligent Nav?** Fragmented. Navigating from a Portfolio risk to a Strategy to fix it is 4+ clicks.
3.  **Natural Guidance?** Yes, the `NextStepCard` and `PageChapter` NEXT cells are the unsung heroes here.
4.  **Dead Pages?** `SignalLab` and the middle 6 tabs of `Options`.
5.  **Collapsible Sections?** `Ops` (all of it), `SignalLab` formulas, `Decisions` engineering snapshot.
6.  **Sticky Sections?** `ActionQueue` FilterBar, `Options` Chain headers.
7.  **Visually Noisy?** `PortfolioTerminal` (the "Working" view) and `Ops`.
8.  **Under-emphasized?** "Generate Explanation" buttons and "Risk Flags" in small tables.
9.  **Wasted Vertical Space?** `Overview` ps-secondary (on mobile), `SignalLab` empty states.
10. **Too Dense?** `Options` chain and `Risk` full breakdown.
11. **Mobile Ergonomics Fail?** `Options` tabs and `Decisions` nested scroll.
12. **Developer-built?** `Options`, `Alpha Lab`, and `Ops`.

---

DONE: docs/research/debates/PHASE_15_elite_ux/round1/gemini.md
