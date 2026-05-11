## 1. Final per-page scores
| # | Page | Final score | One-line justification |
|---|---|---|---|
| 1 | `/overview` | 7.0 | The executive briefing is strong, but four competing top-level heroes create unnecessary cognitive load. |
| 2 | `/events` | 6.0 | Too passive; it acts as an RSS feed rather than synthesizing catalysts with active signal impacts, and swallows fetch errors. |
| 3 | `/action-queue` | 8.5 | Our strongest and most premium surface, anchored by the excellent "Why no buys?" explanation panel. |
| 4 | `/signal-lab` | 4.5 | The "Not yet wired" backtest tombstone dominates the page and severely undermines product credibility. |
| 5 | `/decisions` | 7.0 | The calm card and audit model are great, but the 3-column layout fails ergonomically on smaller desktop viewports and mobile. |
| 6 | `/strategies` | 6.5 | Strong educational collapse, but lacks a clear hero metric for active/blocked/eligible strategy states. |
| 7 | `/options/*` | 4.0 | The 12-tab flat hierarchy wrapping on mobile is a catastrophic navigation failure that overwhelms all users. |
| 8 | `/portfolio` | 6.0 | Defaulting to the dense, developer-heavy terminal view instead of the premium brief view hides our best storytelling. |
| 9 | `/risk` | 6.5 | Strict table wrapping is good, but tiny "Generate explanation" buttons and missing next-step routing stall the user journey. |
| 10 | `/research` (Alpha Lab) | 4.0 | Silent fallback to hardcoded static signals when the shadow registry is empty is an unacceptable truth violation. |
| 11 | `/ops` | 4.0 | Hardcoded "ok" and "skipped" statuses on job rows destroy the honest-data premise of the entire platform. |

## 2. Final elite-gap thesis
The single most important reason this isn't yet an elite 10/10 product is the pervasive erosion of "honest data" trust through silent fallbacks, hardcoded UI placeholders, and fragmented design systems. While the `page_flow` architecture and "NOW/NEXT" narrative spines are incredibly strong, users constantly stumble into legacy code, inactive "tombstones," or visually distinct sub-apps like Options that break the illusion of a singular, intelligent OS. To feel like Stripe or Perplexity, the product must ruthlessly eliminate any UI that lies about data readiness and unify its three competing visual dialects into a single, cohesive vocabulary.

## 3. Final unanimous-or-strong-consensus findings
- ✓ Options 12-tab navigation wrapping via `flex-wrap` on mobile is the single largest UX and IA failure in the product.
- ✓ Hardcoded `last="ok"` statuses on job rows in `Ops.tsx` are a P0 trust violation that must be eliminated.
- ✓ The `/portfolio` default view must flip from the dense terminal to the AI-narrative `?view=brief` (`CopilotHoldings`).
- ✓ The "Not yet wired" backtest tombstone in `SignalLabPage.tsx` must be removed or hidden.
- ✓ The product currently suffers from three jarringly different design systems (picks-root, Tailwind/legacy, Options zinc-heavy).
- ◐ The Density Toggle is over-deployed on pages where it has no visual effect (Events, Signal Lab) and needs to be scoped or globally wired.

## 4. Final disagreements that did NOT converge
- **Density Toggle (Global vs. Local):** Opus and Sonnet want to hide the toggle on pages without dense tables. **My position:** It should remain visible globally but the `--pi-space-*` CSS tokens must be fixed to actually scale text leading and card padding on non-table pages, honoring it as an app-wide state.
- **AI Presence & Typography:** I proposed introducing Source Serif 4 and subtle TopStrip motion to denote AI-generated narrative and engine thinking. Opus vehemently rejected this as "atmospheric" and gimmicky. **My position:** I concede to Opus on ambient motion, but I hold that a deliberate serif contrast for AI synthesis blocks creates a premium, editorial reading experience novices appreciate.
- **Action Queue Bulk Execution:** Opus argued the Action Queue lacks bulk "execute all" affordances. **My position:** Friction here is a feature; paper-trading evaluation requires users to read the AI's reasoning, so bulk approval bypasses the core value proposition.
- **FilterBar Keyboard Navigation:** Codex argues my tablist/keyboard critique is stale because of Phase 13d's `role="group"` changes. **My position:** While the ARIA roles updated, terminal-grade users still expect robust `J`/`K` navigation and `Enter` to expand cards, which `role="group"` alone does not solve.
- **Decisions Mobile Layout:** Opus wants a bottom-sheet for the detail view on mobile, Sonnet wants scroll-into-view. **My position:** The premium standard is a swipeable bottom sheet for detail drill-downs without polluting the router history.

## 5. Phase 15 roadmap (next phase to ship)
1. **Fix hardcoded Ops statuses**
   - `apps/web/src/pages/Ops.tsx:263-266`
   - Effort: S
   - Regression risk: low
   - Why 15 not 16: Immediate P0 truth violation; hardcoded data breaks core trust.
2. **Label Research fallback registry**
   - `apps/web/src/pages/ResearchLab.tsx:128`
   - Effort: S
   - Regression risk: low
   - Why 15 not 16: Hiding static baseline data as live signals is a P0 fakes-by-omission violation.
3. **Remove Signal Lab tombstone**
   - `apps/web/src/pages/SignalLabPage.tsx:170-183`
   - Effort: S
   - Regression risk: low
   - Why 15 not 16: Dead UI sections instantly degrade the perception of a premium product.
4. **Restore Events fetch error handling**
   - `apps/web/src/pages/EventsResearchPage.tsx:27`
   - Effort: S
   - Regression risk: low
   - Why 15 not 16: Swallowing errors to show an "empty day" lies to the user about data availability.
5. **Options tab mobile overflow**
   - `apps/web/src/pages/options/OptionsLayout.tsx:48`
   - Effort: S
   - Regression risk: low
   - Why 15 not 16: Swapping `flex-wrap` for `overflow-x-auto` is a single-line fix that immediately unblocks mobile usability.
6. **Flip Portfolio default to Brief view**
   - `apps/web/src/pages/copilot/PortfolioRouteSwitch.tsx:20-22`
   - Effort: S
   - Regression risk: medium
   - Why 15 not 16: Exposes the best AI storytelling to standard users by default.
7. **Remove Decisions emoji and tone leaks**
   - `apps/web/src/pages/Decisions.tsx:359`
   - Effort: S
   - Regression risk: low
   - Why 15 not 16: Casual emojis undermine the authoritative financial tone required for trust.
8. **Decisions column breakpoint fix**
   - `apps/web/src/pages/Decisions.tsx:207`
   - Effort: S
   - Regression risk: low
   - Why 15 not 16: Changing `xl:` to `lg:` instantly fixes the awkward 3-column squeeze on common laptops.
9. **Remove Overview MarketTicker from above-the-fold**
   - `apps/web/src/pages/PicksPage.tsx`
   - Effort: S
   - Regression risk: low
   - Why 15 not 16: Highest leverage emotional-read fix; instantly calms the first-second impression.
10. **Kill Options amber active border**
    - `apps/web/src/pages/options/OptionsLayout.tsx:56`
    - Effort: S
    - Regression risk: low
    - Why 15 not 16: Swapping to `--accent` removes a jarring design-system collision safely.

## 6. Phase 16 roadmap (after Phase 15)
1. **Options IA 12-to-4 Tab Collapse**
   - `apps/web/src/pages/options/OptionsLayout.tsx`
   - Effort: L
   - Regression risk: high
   - Why 16 not 15: Too risky to bundle with P0 truth fixes; requires deep QA of nested routes.
2. **"What changed" Temporal Pills**
   - `apps/web/src/pages/PicksPage.tsx`
   - Effort: M
   - Regression risk: medium
   - Why 16 not 15: Additive context that requires session state; truth fixes take precedence.
3. **Decisions / Ops / Risk tokenization**
   - `apps/web/src/index.css`
   - Effort: L
   - Regression risk: high
   - Why 16 not 15: Unifying the Tailwind legacy pages with `picks-root` requires extensive cross-page visual QA.
4. **Action Queue Group Rationale**
   - `apps/web/src/pages/ActionQueuePage.tsx`
   - Effort: M
   - Regression risk: medium
   - Why 16 not 15: Action Queue is already strong; enhancements can wait until broken pages are stabilized.
5. **Group Ops Cards into Collapsible Sections**
   - `apps/web/src/pages/Ops.tsx`
   - Effort: M
   - Regression risk: low
   - Why 16 not 15: Alleviates the scroll-of-death, but secondary to fixing the hardcoded job statuses inside them.

## 7. Phase 17 roadmap (last phase)
1. **Global Keyboard OS (`J`/`K` navigation)**
   - `apps/web/src/components/shell/`
   - Effort: XL
   - Regression risk: medium
   - Why 17 not 16: Elite power-user feature that demands a stable underlying DOM structure first.
2. **Mobile Bottom-Sheet for Decisions/Details**
   - `apps/web/src/pages/Decisions.tsx`
   - Effort: L
   - Regression risk: high
   - Why 17 not 16: A native-feeling mobile gesture paradigm is the final polish step, not a core structural fix.
3. **Persistent AI Assistant Rail**
   - `apps/web/src/components/shell/Shell.tsx`
   - Effort: XL
   - Regression risk: high
   - Why 17 not 16: Highly complex state management that should only be built on a fully unified design system.

## 8. Final answer to the 12 brief questions
1. **Coherent story?** The structural spine (`page_flow`) is coherent, but broken by multiple visual dialects and hidden URL variants.
2. **Navigation linear/intelligent or fragmented?** Fragmented; strong in the SideNav but completely disjointed within local page tabs and URL parameters.
3. **Natural guided flow?** Yes, via NextStepCards, but microcopy often contradicts the destination link's actual purpose.
4. **Dead/passive pages?** Events feels like an uncurated RSS feed, and Alpha Lab reads like a disconnected static worksheet.
5. **Sections to collapse?** The 15+ Ops cards need macro-grouping, and educational Start-here cards should auto-collapse after the first visit.
6. **Sections to make sticky?** The Timeline column on Decisions should stick on desktop, but mobile should remain unpinned to maximize vertical space.
7. **Visually noisy cards?** The Overview stacked heroes and the data-dense PortfolioTerminal default view overwhelm the user.
8. **Under-emphasized cards?** The `?view=brief` Portfolio toggle is practically invisible, and Risk's "Generate explanation" button is too small.
9. **Wasted vertical space?** The Options 12-tab wrap on mobile and the Signal Lab "Not yet wired" backtest block unnecessarily steal premium viewport real estate.
10. **Too dense?** Options Chains and the 3-column Decisions layout on mid-sized laptops cramp the reading experience.
11. **Mobile fails?** Options is completely broken by `flex-wrap`, and Ops is an exhausting, unstructured vertical scroll.
12. **Developer-built?** Ops, Alpha Lab, and Options scream "developer dashboard" through raw Tailwind styling and engineering vocabulary.

## 9. The one thing you would NOT change
The "Why no buys?" explanation panel on the Action Queue must remain exactly as it is, as it represents the absolute pinnacle of trust-building AI product design in the entire codebase.