# Phase 15 Elite UX Debate — Brief for Panelists

**Project:** AI Investing OS (paper-trading research + recommendation surface)
**Branch:** `phase-1/ledger`
**Latest commit:** `c0e18fd` (Phase 14f-F — mobile sticky relax)
**Stack:** React 18 + TypeScript + Vite + Tailwind + custom CSS tokens (`--pi-*` / `--fg-*`)
**Routing:** react-router-dom; main shell at `apps/web/src/components/shell/`
**Reviewers:** 4 — Gemini CLI, Codex CLI, Claude Sonnet (subagent), Claude Opus (moderator)

---

## Mission

Conduct a **deep product UX / IA / navigation / storytelling / cognitive-flow / mobile-first audit** intended to push the platform toward elite 10/10 quality comparable to premium AI-native products (Linear, Stripe, Perplexity, Bloomberg Terminal).

This is **NOT** a simple visual review. Review the **REAL current implementation**, not hypothetical redesigns.

## Critical discipline constraints

- No fake data
- No fabricated AI states
- No "atmospheric" visuals that reduce information clarity
- Maintain honest-data discipline (post-13k canonical source = `/api/paper/summary`)
- Preserve paper-trading disclaimers (RESEARCH_NOTE / PAPER_ONLY_NOTE)
- Preserve density modes (compact / cozy / spacious)
- Preserve light/dark parity (Phase 13j fixed TopStrip; ticker/rail/picks-* covered)
- Preserve accessibility (skip-link, focus-visible, aria-sort, aria-pressed, sr-only captions per Phase 13a/d/g)
- Preserve performance (no virtualization regression on Action Queue / PositionsTable)
- Review BOTH desktop and mobile UX equally
- Review REAL current implementation, not hypothetical redesigns

## Pages to evaluate (11)

| # | Route | Page component | Notes |
|---|---|---|---|
| 1 | `/overview` (default) | `apps/web/src/pages/PicksPage.tsx` | Phase 14b: subtitle = canonical NAV+return+posture; 4 launcher cards; Today's read; PortfolioSnapshot |
| 1b | `/overview?view=working` | `apps/web/src/pages/Overview.tsx` | Legacy preserved per Strategic lock D |
| 2 | `/events` | `apps/web/src/pages/EventsResearchPage.tsx` | Mostly delegates to `MarketEvents` component |
| 3 | `/action-queue` | `apps/web/src/pages/ActionQueuePage.tsx` | Phase 14c: decision-desk subtitle, "Why no buys?" panel, action-color rail, skeleton |
| 4 | `/signal-lab` | `apps/web/src/pages/SignalLabPage.tsx` | Phase 13h: ExpertDetails wrap; readiness composite |
| 5 | `/decisions` | `apps/web/src/pages/Decisions.tsx` | Legacy Tailwind page, Phase 13e PageChapter threaded |
| 6 | `/strategies` | `apps/web/src/pages/StrategiesPage.tsx` | Phase 14f-E: strategy-edu now in ExpertDetails; h2 fix |
| 7 | `/options/*` | `apps/web/src/pages/options/OptionsLayout.tsx` + 12 sub-pages | 12-tab nested router (overview/chain/features/trades/risk/observatory/performance/diagnostics/replay/evaluation/decision-support/decision-framing) |
| 8 | `/portfolio` | `apps/web/src/pages/copilot/PortfolioRouteSwitch.tsx` → `PortfolioTerminal.tsx` (default) / `CopilotHoldings` (?view=brief) | Reads `/api/paper/summary` via `usePaperSummary` |
| 9 | `/risk` | `apps/web/src/pages/RiskDashboard.tsx` | Legacy Tailwind, Phase 13e PageChapter threaded, Phase 13i tokenized |
| 10 | `/research` (Alpha Lab) | `apps/web/src/pages/ResearchLab.tsx` | Phase 13e PageChapter threaded; static fallback registry rows |
| 11 | `/ops` | `apps/web/src/pages/Ops.tsx` | 12 cards Live/ML/Engine/Replay; Phase 13e PageChapter threaded |

## Shell components (cross-cutting on every page)

- `apps/web/src/components/shell/Shell.tsx` — flex SideNav + main column; Phase 14f-A drawer state
- `apps/web/src/components/shell/SideNav.tsx` — `w-[220px]` desktop, mobile drawer at ≤768
- `apps/web/src/components/shell/TopStrip.tsx` — Phase 14f-B: 6 cells with data-slot, mobile hides 3
- `apps/web/src/components/shell/MarketTicker.tsx` — animated ticker; mobile gutter shrunk
- `apps/web/src/components/shell/StatusRail.tsx` — NOW/NEXT/RISK; mobile vertical stack
- `apps/web/src/components/shell/PageChapter.tsx` — narrative chapter rail (NOW/WHY/NEXT)
- `apps/web/src/components/shell/NextStepCard.tsx` — bottom-of-page next-step nudge
- `apps/web/src/components/shell/ExpertDetails.tsx` — collapsible used in Signal Lab + Strategies

## Recent change history (Phase 13 + 14)

```
Phase 13a → 13j  Tier 1/2/3/4/5/6/7 from prior octo-debate (skip-link, focus-visible,
                  useFetchWithError, density lift, mobile table wrap, FilterBar a11y,
                  PageChapter threading on 4 legacy pages, microcopy translation,
                  aria-sort + captions + press-scale, ExpertDetails on Signal Lab,
                  zinc tokenization, TopStrip light-mode parity)
13k                 Canonical /api/paper/summary on Overview snapshot (data-truth fix)
14a                 Premium visual foundation (--ax-* tokens, launcher hover glow,
                    .picks-empty-state, .picks-cta-*, .picks-badge, mobile padding,
                    .picks-action-rail)
14b                 Overview executive briefing (NAV/return/posture subtitle, 4-card
                    launcher grid, Today's read, dropped Signal Lab from Overview)
14c                 Action Queue decision desk ("Why no buys?" panel, action-color rail,
                    skeleton, decision-desk subtitle)
14f-A               Mobile shell drawer + viewport-fit + safe-area + touch global
14f-B               TopStrip cell hide + ticker gutter compress + StatusRail vertical
14f-C               picks-header stack + FilterBar overflow-x + ps-secondary 2-col mobile
14f-D               PickBox 1-col mobile + 44px tap targets
14f-E               Strategies edu collapsed + h2 hierarchy fix
14f-F               Mobile sticky relax (only TopStrip pinned)
```

## Prior octo-debate reference

`docs/ux/octo_phase_12_review.md` — full 4-panelist debate output, Phase 12 (one cycle ago).
Median page scores: Overview 7.5 / Action Queue 7.0 / Events 6.0 / Strategies 6.5 / Portfolio 6.5 / Signal Lab 5.5 / Decisions 6.0 / Risk 6.0 / Options 5.0 / Alpha Lab 5.5 / Ops 5.5. Overall median 6.0/10.

## Mobile preview URL (for reviewers who can browse)

`https://mobile-preview.packhunter.xyz` (Cloudflare Tunnel + Cloudflare Access; email-gate; not publicly browsable).

## Output format expected from each panelist (every round)

For EACH of the 11 pages:
1. Current UX score `/10`
2. Biggest strengths
3. Biggest weaknesses
4. Desktop-specific issues
5. Mobile-specific issues
6. Novice-user issues
7. Expert-user issues
8. Storyline / navigation issues
9. Recommended structural changes
10. Recommended visual changes
11. Recommended interaction changes
12. Priority ranking: P0 critical / P1 high ROI / P2 polish
13. Estimated implementation complexity
14. Regression risk

Then:
- A. Cross-product findings (design-system inconsistencies, navigation inconsistencies, typography inconsistencies, density inconsistencies, interaction inconsistencies)
- B. "Elite-gap" analysis — exactly why this still does or does not feel like a world-class AI-native investing product
- C. Final ranked roadmap — Phase 15 / Phase 16 / Phase 17 prioritized strictly by:
  1. UX impact
  2. Novice clarity
  3. Mobile quality
  4. Trustworthiness
  5. Implementation safety

## Specifically analyze (the 12 questions)

1. Is the app telling a coherent story page-to-page?
2. Does navigation feel linear/intelligent or fragmented?
3. Are users guided naturally from Overview → Catalysts → Decisions → Execution → Portfolio → Risk?
4. Which pages feel "dead" or passive?
5. Which sections should become collapsible?
6. Which sections should become sticky?
7. Which cards are visually noisy?
8. Which cards are under-emphasized?
9. Which sections waste vertical space?
10. Which sections are too dense?
11. Which pages fail on mobile ergonomics?
12. Which pages still feel "developer-built" instead of "premium product"?

## For mobile specifically

- iPhone 14/15 Pro
- Android Pixel 8
- tablet widths
- portrait + landscape
- notch / safe-area handling
- sidebar collapse (now drawer per 14f-A)
- tap target sizing (44px set 14f-D)
- horizontal overflow
- thumb reach
- sticky behavior (only TopStrip pinned per 14f-F)
- ticker usability
- scroll smoothness
- density modes
- card stacking
- readability at arm's length

## Repo entry points (open in your shell to read)

- Source root: `apps/web/src/`
- Pages: `apps/web/src/pages/`
- Shell: `apps/web/src/components/shell/`
- Picks/portfolio components: `apps/web/src/components/picks/`, `components/portfolio/`
- Options components: `apps/web/src/components/options/` (~50 files)
- Token CSS: `apps/web/src/index.css` (1789 lines), `apps/web/src/lib/picks/picks.css` (5178 lines)
- Vite dev server: `localhost:5173` (running)
- Worker / API: `apps/worker/`, `services/`

---

## Word-limit guidance

Per panelist per round: ~3000-5000 words is acceptable given the 11-page scope. Don't pad. Use file:line citations where you make a claim about the implementation. Honest data only — don't invent feature details you haven't verified.
