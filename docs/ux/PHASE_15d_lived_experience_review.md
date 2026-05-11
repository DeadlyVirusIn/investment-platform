# Phase 15d — Lived Experience Review

**Date:** 2026-05-11
**Branch:** phase-1/ledger
**HEAD at review:** 9595ef6 (Phase 15c3)
**Mode:** Single voice, narrative prose. Not an audit. The question is what this product feels like, minute by minute, to the people actually using it.

Phase 15 (the elite audit) catalogued every defect the four panelists could find. The 15a/b/c work shipped a defensible majority of those fixes. So when I open the app today I am no longer encountering trust violations or tombstones; I am encountering a product that *almost* works, and I want to describe the gap between "almost works" and "this is mine."

I'll walk through eight flows in order, then synthesize.

---

## Flow 1 — First-time novice on `/overview`

I open the app. Before the page resolves, my eye lands on the top three centimeters of chrome: a logo + version pill on the left ("AI Investing OS · v1.0.0"), then a TopStrip with NAV, Day P&L, Total Return, Regime, Engine, Health — six tabular cells in monospaced numerals — then a thin StatusRail underneath with NOW / NEXT / RISK segments. Phase 15b3 correctly hid MarketTicker on this route, and the difference is real: the page no longer scrolls horizontally above the fold. But two of those remaining strips are answering the *same question* — "is anything wrong?" — using different vocabularies. TopStrip says "Healthy." StatusRail says "Low · no anomalies." A novice cannot tell whether these are two facts or one fact rendered twice.

Then the page proper begins. A picks-header with "Overview" title and a subtitle reading "$48.2K · −2.3% return · cautious posture" (PicksPage.tsx:122-136). Below that, PageChapter with crumb "Today's read › Overview" and the WHY/NEXT cells. Below that, PortfolioSnapshot's hero — NAV again, big this time, with sparkline and "AI posture: cautious" banner. So in roughly the first 480 vertical pixels I have been told the NAV three times and "cautious" twice. Phase 15c3 removed the explicit duplicate "Engine sees N buy · M sell" from PageChapter NOW, which helps. But the NAV repetition is still there, because TopStrip exists to be persistent and PortfolioSnapshot exists to be the hero, and nobody picked one.

Where attention naturally goes: the big NAV in PortfolioSnapshot. That is the right answer. The novice ignores TopStrip — it reads as developer chrome — which makes the dual rendering asymmetric waste, not asymmetric reinforcement.

What I find emotionally: *I am not unwelcome here, but no one greeted me.* The Decisions calm card, the Risk calm card, the why-no-buys panel — those are warm moments the product is genuinely capable of. Overview does not have one. The first sentence of human English I read is in PageChapter's WHY cell, which is generic page-flow copy from `page_flow.ts` — not derived from today. The TodayPanel.headline *is* derived from today, but it sits below PageChapter and below PortfolioSnapshot, in the third visual zone, in normal-weight type that doesn't read as a headline.

Then the four launcher cards. Good cards — eyebrow / title / metric / body / "Open →" — and the metrics are honest. But the visual treatment is identical across all four. Card #1 (today's recommendations) is more important than card #4 (portfolio review the user just scrolled past), and nothing in the visual treatment says so. The hesitation is sharpest at card #4: the novice reads the giant NAV hero, scrolls, and is offered "Review Portfolio Risk" as a destination. They were just shown the portfolio. The card sells what they were just looking at.

The Phase 11K guardrail footer is one of the most quietly correct decisions in the product — never apologetic, never alarmist, always present.

**Net feel:** Competent, honest, slightly impersonal. A novice would not bounce, but would not feel the product had thought specifically about *them* either.

---

## Flow 2 — Returning daily-check user (day 5+)

Same person, five days in. I land on `/overview`. The product remembers nothing about me — no "since you last checked" line, no diff against my last visit. The Day P&L cell in TopStrip is doing the only "what changed today" work, and it's a single number that doesn't tell me whether the *picture* changed.

This is the moment I most want the product to have an opinion. By day five I no longer need to read the page; I need to be told *what's different*. The Decisions calm card has this exactly right — five branches of state-of-the-world in plain English. Overview doesn't. Overview is basically the same view as day 1 with different numbers in it.

The "Today's read" line (PicksPage.tsx:192-197) is the closest thing, but it sits as the fifth element on the page, after the NAV hero, the posture banner, the AI summary in TodayPanel, and the top-action card. The headline is buried under its own context.

The keyboard-shortcut `kbd` glyphs in SideNav (SideNav.tsx:75-78) are a love letter to the returning operator. But they are silent — I could not trace an actual global keydown handler in the shell. If `n.hot` is decorative metadata, this is a fakes-by-UI moment on the most premium-feeling element of the navigation — and it survived the audit because it looks like documentation.

**Net feel:** The product treats day 5 the same as day 1. The surfaces that *would* recognize a returning user are either silent or absent. The product doesn't yet know me.

---

## Flow 3 — Active portfolio manager

I open the app to actually do work — scan, decide, drill in, decide again. Path: `/overview` → `/action-queue` → click into a pick → close modal → `/decisions` → `/risk`.

`/action-queue` is the strongest surface in the entire product, and it is strong in the way a real working tool is strong. The skeleton loader (ActionQueuePage.tsx:114-128) gives a layout-stable wait. The FilterBar chips have correct `aria-pressed` semantics. The "Why no buys?" panel (ActionQueuePage.tsx:146-170) is the one moment in the product where the AI speaks like an analyst — "No buy setups passed the engine's thresholds today. The strongest live signals are 5 trims · 2 sells · 10 watches. Buys reappear when momentum, trend, and breadth filters align." That paragraph is the product I thought I bought. Everything else is trying to be that paragraph.

PickBox (PickBox.tsx) delivers the working unit of investing as an experience. Action color along the left edge, fresh-pulse dot, plain-English explain line, tags, confidence meter, relative timestamp. Tap target generous (Phase 14f-D). Action color semantic and consistent.

Where the active manager hesitates: the click-into-modal interaction. I tap a card, modal opens, I read, I close. There is no "next pick" affordance inside the modal — I close, I find my place in the list (the card I just tapped is no longer visually distinguished as "I just looked at this"), I tap the next one. Compared to Linear's keyboard model or Gmail j/k traversal, this is real friction. Three picks in, I'm hunting for my place each time. The cards do not remember my visit.

`/decisions`: the timeline / detail / outcome 3-col layout is correct. Phase 15b3 fixed the breakpoint so 1024-1280 laptops actually get 3 columns. The calm card at the top, the timeline, then per-row detail with `humanReasoning()` in plain English (Decisions.tsx:506-516, 722-759) — second-best surface in the product after Action Queue. The engine literally explains itself.

But six clicks in, I run into the design-system seam. PageChapter at top is rendered through the `picks-root picks-root-inline` bridge (Decisions.tsx:87-89), then the rest of the page is `max-w-[1680px] mx-auto px-8 py-8` Tailwind `u-card`s. Action Queue and Decisions look like two different products — both good, but two — and the manager moving between them re-learns the typography scale. The `picks-title` `clamp()` versus Decisions's `u-title-lg` 24px is the same product in different letterforms.

**Net feel:** The active session is rewarding in the moment of each action and unrewarding in the moments between. Where I do work (Action Queue) is excellent. Moving through the app is tax.

---

## Flow 4 — Investigating a catalyst from `/events`

I want to understand why TSLA is on the trim list. I navigate to `/events`. PageChapter NOW reads "Tracking N symbols · filings update through the day" (microcopy fixed in 15b3 — reads correctly). Then MarketEvents.

What I hoped for: synthesis. Top three catalysts of the day, the symbols they touch, the active signals that derive from them. What I get: a per-symbol grid of earnings / news / filings / expirations counts, sortable but not synthesized. Correct data, well-formatted, emotionally inert.

The narrative break is sharp here. PageChapter NEXT promised me "Map these catalysts to the live signals." The page below it does not perform that mapping. There is no "TSLA: trim signal driven by 8-K filed yesterday" line anywhere. I have to do the join in my head between this feed and what I just read on `/action-queue`. Perplexity ships synthesis-first; this page ships sources-first. The reader is doing the AI's job.

The fetch-error fix from 15a is correct — I trust the empty state now, because if there were an error I'd see it. That's a quiet trust win the user only feels in the negative.

**Net feel:** A library, not a brief. The product has the data; it has not yet earned its name on this page.

---

## Flow 5 — "Why no buys today?"

I land on `/overview`, see "0 buy · 5 sell · 10 trim · 8 hold" on launcher card #1, click in to `/action-queue`, and the panel from Flow 3 appears. The "Why no buys?" panel is the entire reason this scenario doesn't fail. Without it, the user concludes "the product has nothing for me today" and bounces. With it, the user concludes "the AI is reasoning, just not in my favor right now," which is the exact emotional outcome a research tool should produce on a quiet day.

This is the surface I would point at to argue this product is a real AI-native investing OS rather than a polished dashboard. The reasoning is honest, specific, and forward-looking. There are about four such sentences in the entire product, and three of them are on this single panel.

Now I want the same instinct elsewhere. The novice on `/overview` who sees "0 buy" on launcher card #1 has *no* "why no buys" affordance there. If they don't click through, they never read the explanation. The pattern exists; it isn't being replicated.

**Net feel:** The product can do this. It chose to do it once. The "do it everywhere" cost is small and the leverage enormous.

---

## Flow 6 — Reviewing portfolio risk on `/risk`

PageChapter at the top through the bridge. PageGuide eyebrow / title / subtitle. A "Focus today" 1-2-3 list. A collapsible "Where this data comes from." A controls row with replay toggle and a "Why?" button (Phase 15b3 microcopy fix, correctly bumped to text-sm). Then the calm card derives a one-sentence interpretation: "Account risk looks normal. Exposure and drawdown are both within their usual range..." Exactly the right shape.

This page is the clearest articulation of the product's "calm interpretation" philosophy. The Risk calm card, the Decisions calm card, the why-no-buys panel — same family. Honest derivation, plain English, no alarmism, no false reassurance. When the panel says "Drawdown is larger than usual. The account has fallen more than 10% from a previous high. Temporary declines are normal, but a deeper drop is worth a closer look at the largest holdings below" — that is the voice the product should always have.

The headline strip is well-labelled in plain English ("Profit/loss if you closed now" instead of "Unrealized P&L"). The `mark_unavailable` honesty is preserved. The page suffers from one structural problem the audit named correctly: **five framing layers before any number** (PageChapter, PageGuide, Focus-today, AdvancedDetails source, controls row). For a returning operator this feels protective in the wrong direction. For a novice it feels right. The page does not know which audience it is talking to.

**Net feel:** Doing its job for a novice and over-talking to an expert. The "Why?" button is the single most premium affordance on the page — a question, not a verb — and it lives at the edge of the controls row where I almost don't see it.

---

## Flow 7 — Strategies and Options

`/strategies` is calm. The educational "When each strategy fits" list is collapsed by default behind ExpertDetails (Phase 14f-E), the strategies-sections rhythm has explicit 32px gaps (Phase 15c3), three components stack with breathing room. NextStepCard at the bottom links to Options with derived rationale.

What's missing: a hero metric. The page does not tell me, at a glance, how many strategies are active, blocked, or eligible. I read three component cards to assemble the picture. Compared to `/action-queue`, where FilterBar gives an immediate count breakdown, `/strategies` feels listful where it should feel summarized.

`/options/*` is the surface that breaks the spell. I tap the Options nav item and land in a separate product. The header is "Options paper trading" (15b3 microcopy correct). The GuardrailsToggleButton at the right edge — I cannot tell if it does anything (audit P0 #4, still open). The 12-tab nav is now a single horizontal scroll row (Phase 15b1 fixed the wrap). Active tab uses `border-accent` (Phase 15b1 killed the amber).

Below that, an Outlet. The Options sub-pages still use `zinc-*` Tailwind hardcodes in places, which means type sizes and surface treatment differ from every other page. Even the Options Overview page (UX-1 Commit F's calm landing) reads in a different visual language than `/strategies` two clicks earlier. The bridge to picks-root stops at the OptionsLayout boundary. This is the "different product" sensation the audit named, and the clearest place where I notice the product was assembled by a team rather than authored by a voice.

**Net feel:** Strategies feels like a calmer cousin of Overview. Options feels like a different application that shares a sidebar.

---

## Flow 8 — Mobile-only (iPhone Safari, full session)

The Phase 14f shell work is real and I can feel it. Hamburger toggle (Shell.tsx:53-64) opens a slide-in SideNav drawer with body-scroll lock and Esc handler. TopStrip relaxed its sticky behavior (14f-F: only TopStrip pinned). MarketTicker compresses. Tap targets on PickBox 44px (14f-D). All invisible-when-correct work.

But page interiors remain desktop ports.

`/overview` on mobile: I scroll past the executive subtitle, PageChapter, PortfolioSnapshot, and the launcher grid stacks correctly to one column. Below the four launcher cards I'm at roughly 2400px scroll depth on a 667pt iPhone. The page is long. The "Today's read" sentence is buried mid-scroll. No "jump to the answer" affordance.

`/action-queue` on mobile: FilterBar chips swipe horizontally (14f-C). PickBoxes stack to one column. Where mobile fatigues: the action queue is long, no mobile-native section anchor, no floating "back to top." After scrolling 12 cards I scroll all the way back to switch filters.

`/decisions` on mobile: the 3-column desktop grid collapses to 1-column linear stack (Decisions.tsx:213). Filter chips swipe horizontally (15c1). Selecting a row scrolls past the timeline into the detail card — but the timeline is *above* the detail card in mobile order, so I scroll up to pick another row. No in-page sheet. This is the single roughest mobile flow in the product (and bottom-sheet treatment is Phase 17 work).

`/options` on mobile: tabs swipe horizontally (15b1), active tab tokenized correctly. But each sub-page interior is desktop-shaped; the chain table requires horizontal scroll. The sub-pages haven't been re-IA'd for mobile.

The mobile lived experience: foundation solid (hamburger, sticky relax, tap targets, drawer). Interiors responsive but not native. No "thumb zone" thinking — the most-used controls (filter chips, density toggle, hamburger) sit at the *top* of the viewport, the worst zone for one-handed thumb reach. There is no bottom nav, no FAB, no thumb-shelf control.

**Net feel:** A desktop product that responds correctly to a phone, not a phone product. Every flow is completable; none feel made for the thumb.

---

## SPECIFIC IDENTIFICATION

### 1. Dead interactions

DensityToggle on inert pages was hidden in 15b3 — good — but where it remains visible (Overview, ActionQueue) it's not obvious which mode is active. **GuardrailsToggleButton** in OptionsLayout.tsx:48 is still unverified. **ThemeToggle / UIModeToggle** in TopStrip use operator vocabulary ("guided / expert") with unclear effect. The **kbd shortcut hints in SideNav** (SideNav.tsx:75-78) appear to be decorative — I could not trace a global keydown handler — which would make them fakes-by-UI on the most premium-feeling element of the navigation. **PickModal closure** loses my place in the list — no "next pick," no scroll-position memory, no visited-card distinction.

### 2. Narrative breaks

`/events` does not join catalysts to live signals despite PageChapter NEXT promising exactly that mapping. The Options surface boundary is a hard visual break — type scale, button treatment, card padding all change at OptionsLayout. PageChapter's WHY/NEXT cells are page-flow-defined rather than data-derived, so they read identically on a quiet day and a loud day; NextStepCard derives rationale on some pages (PicksPage.tsx:268-274) and falls through to generic copy on others.

### 3. Emotional flatness

`/events` is entirely competent and entirely cold. No "we noticed this for you," no editorial. The launcher grid on `/overview` treats four unequal things as four equal cards. TopStrip itself is six cells of monospaced numerals — Bloomberg vocabulary the product hasn't yet earned the right to use.

### 4. Over-information (still, after 15c3)

NAV is rendered three times in the upper viewport on `/overview`: TopStrip cell, executive subtitle, PortfolioSnapshot hero. Posture is rendered twice (executive subtitle, PortfolioSnapshot banner) — was three times before 15c3. Health/system status is rendered twice (TopStrip Health pill, StatusRail RISK segment). The launcher card metric line duplicates the action distribution visible on TodayPanel above it. `/risk` has five framing layers before the first number.

### 5. Under-information

The returning user has no "what changed since last visit" surface. Options sub-pages (chain, features, diagnostics) drop the user into raw data with minimal framing. `/events` does not answer "why does this catalyst matter to the signals I just looked at?" PickModal does not show "the last 12 times the engine flagged a setup like this, here's how they resolved" — Decisions does this for closed trades, live picks deserve the same.

### 6. Mobile lived experience

Thumb fatigue: most-used controls cluster at the top of the viewport, the worst zone for one-handed reach. Excessive scrolling: Overview ~2400px deep, Decisions timeline-above-detail vertical stack. Weak section transitions: section anchors exist as `u-caption-2` text rather than visual chapter dividers. Sticky fatigue: reduced by 14f-F (only TopStrip pinned), but TopStrip itself is the densest element on screen — six cells of monospaced numerals on a 375pt viewport.

### 7. Product identity verdict

**This is a polished quant dashboard wearing the costume of a premium AI-native investing copilot.**

The bones are AI-native: PageChapter narrative spine, page_flow.ts FLOW chain, calm cards on Decisions and Risk, the why-no-buys panel, humanReasoning() on Decisions, the Brief view on Portfolio. These prove the product *can* be that thing.

But the surfaces driving the emotional read — TopStrip, MarketTicker, StatusRail, Ops, Options, the dense KV tables — are quant-dashboard surfaces. They speak ticker / regime / engine / health / gates_passed / decision_version. A novice opening this product for the first time would describe it as "a trading dashboard with some explanations," not as "an AI that helps me invest."

The product currently *contains* the copilot. It is not yet *led by* the copilot. The path from "dashboard with copilot moments" to "copilot with dashboard depth" is not a bigger feature — it's a tilt of visual hierarchy and copy register so the AI's voice is the first voice the user hears on every page, and the dashboard is what they reveal when they dig in.

---

## A. Moments of delight

1. **The "Why no buys?" panel** (`ActionQueuePage.tsx:146-170`) — single most premium moment in the product; honest derivation, analyst's voice, forward-looking.
2. **The Decisions calm card** (`Decisions.tsx:1129-1232`) — five-branch state derivation in warm sentence form is exactly how a copilot should narrate a system to its operator.
3. **The Risk calm card** (`RiskDashboard.tsx:183-250`) — drawdown-aware branches read as a portfolio manager friend, not a dashboard.
4. **The PickBox composition** (`PickBox.tsx`) — entire reasoning of one signal in ~250 vertical pixels; the working unit of the product.
5. **CopilotHoldings (Brief) view** (`CopilotHoldings.tsx`) — most consistent application of "AI as narrator" anywhere in the product.
6. **page_flow.ts + PageChapter + NextStepCard** — the architectural decision to thread a narrative spine through every page; execution incomplete, architecture correct.
7. **The shell footer disclaimer** (`Shell.tsx:94-100`) — always present, never apologetic, never alarmist.
8. **The skeleton loader on `/action-queue`** — layout-stable, shape-matched, the premium way to load.

---

## B. Moments of friction

1. `/events` is a feed, not a brief — promises "the why behind signal changes" and delivers a counts grid.
2. Three sticky chrome strips above every page — TopStrip + MarketTicker + StatusRail; two answer "is anything wrong" using different vocabularies.
3. NAV rendered three times in `/overview`'s upper viewport.
4. PickModal closure costs my place in the list — no traversal, no scroll-position memory, no visited-card distinction.
5. The Options surface is a different product — type scale, card treatment, color tokens diverge at the OptionsLayout boundary.
6. The kbd shortcut hints in SideNav may be decorative — fakes-by-UI on the most premium-feeling element of the nav.
7. The launcher grid on `/overview` treats four unequal things as four equal cards.
8. Decisions on mobile is timeline-above-detail-stack — picking a second row requires scrolling back up.
9. The product remembers nothing between visits — no "since you last checked," no session memory.
10. `/risk` has five framing layers before the first number.

---

## C. What should NEVER change now

1. **PageChapter / NextStepCard / page_flow.ts narrative spine** — the architectural decision that makes the product a flow rather than a collection of pages.
2. **The "honest data" discipline** — no fake marks, no swallowed errors, no fabricated AI states, no static-fallback substitutions, no hardcoded "ok" pills. Spine of trust.
3. **The calm-card pattern** (Decisions, Risk) — state-of-the-world in plain English before the numbers.
4. **The "Why no buys?" microcopy register** — analyst's voice, honest, forward-looking, derived from real counts.
5. **The picks-root design world for the FLOW pages** — Overview, Action Queue, Events, Signal Lab, Strategies share coherent visual language; this is the product's authored half.

---

## D. What should be removed

1. **MarketTicker on every page that isn't a market context page** — already hidden on `/overview` (15b3); same logic for `/decisions`, `/risk`, `/portfolio?view=brief`, `/signal-lab`. Motion competing with reasoning.
2. **The kbd shortcut hints in SideNav, unless they are wired** — either implement the global keydown handler or strip the metadata.
3. **GuardrailsToggleButton in OptionsLayout, unless verified** — audit P0 #4, still open.
4. **Duplicate posture rendering** between executive subtitle and PortfolioSnapshot banner — pick one.
5. **The "guided / expert" mode toggle in TopStrip** — operator vocabulary, unclear effect, competes for chrome space.

---

## E. What should become more prominent

1. **The "Today's read" headline on `/overview`** — currently the fifth thing on the page; should be the first. The sentence the user came for.
2. **The "Why?" button on `/risk`** — most premium affordance on the page, currently at the edge of the controls row.
3. **The CopilotHoldings (Brief) view as Portfolio default** — already flipped in 15b2; the toggle remains subtle, the brief view's narrative quality could be more strongly signaled.
4. **The pattern-context panel from Decisions, applied to live picks** — Decisions does this for closed trades; live picks deserve the same.
5. **The "Why no buys?" pattern on every empty/quiet state** — Strategies, Signal Lab, Options Overview, Risk's healthy branch all deserve the same analyst-voice treatment.

---

## F. What should become calmer

1. **TopStrip** — six cells of monospaced numerals on every page; three cells (NAV / Day / Health) would carry the same value with half the chrome cost.
2. **The `/risk` framing stack** — five framing layers before any number; compress or absorb into the calm card.
3. **The Options 12-tab nav** — single-row scroll fix made it usable; the four-group collapse (Phase 16) is the right destination.
4. **The launcher grid on `/overview`** — four equal cards is loud equality; an asymmetric 2-column-with-hero layout would calm it.
5. **The shell footer disclaimer paragraph** — could compress to one line and reclaim the bottom edge.

---

## G. Top 5 highest-leverage improvements (ranked by emotional ROI)

### 1. Promote the "Today's read" headline to the page hero on `/overview`

- **Where:** `apps/web/src/pages/PicksPage.tsx:192-197` (currently rendered after TodayPanel)
- **Change:** The first sentence on `/overview` is a derived, plain-English read of what today's signals mean — appearing *before* NAV, sparkline, and launcher grid.
- **Why high emotional ROI:** Right now the user opens the app and is greeted by chrome and numbers. A sentence — "Cautious posture · 5 trims driven by weak earnings revisions" — written as the first thing they read is the difference between "dashboard" and "copilot." No new data, no new endpoint. Removes the moment of "where do I look first?"
- **Risk it doesn't land:** The headline depends on `briefing.headline` having something interesting to say. On a quiet day it could read flat. Mitigation: branch the empty state to a calm-card-style "Quiet day — engine reviewed N candidates, none cleared the threshold."

### 2. Replicate the "Why no buys?" pattern on every quiet/empty state

- **Where:** Pattern source `apps/web/src/pages/ActionQueuePage.tsx:146-170`. Targets: `StrategiesPage.tsx`, `SignalLabPage.tsx`, `RiskDashboard.tsx` (calm "healthy" branch), `apps/web/src/pages/options/OptionsOverviewPage.tsx`.
- **Change:** Every page with a quiet state speaks in the analyst's voice the way Action Queue does, not as "no data" or "all clear" administratively.
- **Why high emotional ROI:** The product's emotional ceiling is the why-no-buys panel. Replicating that register everywhere quiet states exist makes the product feel unified in voice rather than "well-written in one place." Cheapest path to "the AI is the product" feeling.
- **Risk it doesn't land:** The pattern is honest because it derives from real data. Forcing it where derivation is thin could make the analyst voice sound like filler. Mitigation: only render when there is at least one data-derived sentence to say.

### 3. Add a single "What changed since your last visit" line to `/overview`

- **Where:** New surface on `apps/web/src/pages/PicksPage.tsx`, derived from session/localStorage compared to current `commandBar` snapshot.
- **Change:** Returning users see a one-line diff at the top — "Since you last checked: 2 new picks · TSLA flipped to trim · NAV +$320."
- **Why high emotional ROI:** Day 5 currently feels like day 1 with different numbers. A returning-user diff is the strongest single signal that the product knows you. Highest-leverage AI-native moment available without any new model work.
- **Risk it doesn't land:** localStorage memory is fragile (clearing cookies erases it). The line could feel hollow when nothing changed. Mitigation: branch to "Same picture as your last visit" rather than hide — itself a kind of presence.

### 4. Demote the upper-third chrome on every page

- **Where:** `apps/web/src/components/shell/Shell.tsx:78-89` — the three sticky strips (TopStrip + MarketTicker + StatusRail).
- **Change:** Above-the-fold chrome shrinks from three strips (~95-115px) to one strip with smarter route-aware compression — TopStrip slimmer, MarketTicker only on market-context pages (already partly done), StatusRail folded into TopStrip on calm interpretive pages.
- **Why high emotional ROI:** The first 100px of every page is dense ribbon. The user's eye spends those pixels parsing chrome rather than meeting the page. Reclaiming that space is the difference between "professional terminal" and "premium product." Extends Opus's highest-leverage emotional-read change beyond `/overview`.
- **Risk it doesn't land:** Operators may want the persistent NAV/health strip during active sessions. Mitigation: keep the strip on `/action-queue`, `/decisions`, `/portfolio?view=working`, `/ops` — pages where operating state matters in the moment — and shed it on interpretive pages (`/overview`, `/portfolio?view=brief`, `/risk`, `/events`, `/strategies`) where the page itself answers the same questions.

### 5. Make the PickModal traversable

- **Where:** `apps/web/src/components/picks/PickModal.tsx` (and the PickBox click-through in `ActionQueue.tsx`).
- **Change:** Inside the modal, j/k or arrow-key navigation moves to the previous/next pick in the current filtered queue, and closure returns the user to the card they last opened — visually marked as visited.
- **Why high emotional ROI:** The biggest friction in the active manager's flow. Each modal closure currently restarts the scan. A traversable modal turns six clicks into one continuous review session and turns the queue into a real working surface. The difference between Gmail j/k and a CRUD list.
- **Risk it doesn't land:** Keyboard navigation is invisible until discovered. If the discoverability cue is too subtle, only power users benefit. Mitigation: pair the keyboard handler with a small "← → · prev/next pick" affordance inside the modal footer.

---

**Closing observation:** The product is no longer a quant dashboard with a copilot bolted on; it is a quant dashboard with a copilot living inside it. The Phase 15d work that matters most is the work that lets the copilot answer the door first.
