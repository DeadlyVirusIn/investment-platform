# System Cohesion Review

Read-only audit, branch `phase-1/ledger`, 2026-05-19. Focus: smallest
corrections only. No redesign. Cited file:line throughout.

---

## 12-surface walk

### 1. Portfolio dashboard — PortfolioSnapshot
File: `apps/web/src/components/portfolio/PortfolioSnapshot.tsx`
- User thinks: a single coherent dashboard for "my portfolio".
- Actually showing: aggregate across 4 portfolios (incl. $100K Replay
  Recovery + two $1K test rigs), labelled "Across 4 paper portfolios"
  (`PortfolioSnapshot.tsx:263`).
- Severity: **confusing**.
- Class: **scope mismatch**.
- Smallest fix: drop the two test rigs (`api-test`, `eq-curve-test`)
  from the active-aggregate query, or expose `active=true AND
  name NOT LIKE '%test%'` filter in `/api/paper/summary`. The "Scope"
  tile (`:259-267`) then reads "Across 2 paper portfolios" — honest.
- Effort: **S**. Timing: **immediate**.

### 2. AccountingStrip
File: `apps/web/src/components/portfolio/AccountingStrip.tsx`
- User thinks: canonical "Total profit" = real money the AI made.
- Actually showing: Total profit also includes the +$4,786 from a
  $100K replay-recovered account. Footnote at `:239-256` mentions
  recovered positions but does not break the dollar figure out from
  Total profit.
- Severity: **confusing**.
- Class: **accounting**.
- Smallest fix: in the "Recovered history" banner, name the dollar
  contribution to *Total profit* explicitly (not just market value):
  `Recovered positions contribute ${X} to Total profit (of ${Y} shown).`
  Source: `paper_trade.realized_pnl WHERE is_replay=true`.
- Effort: **S**. Timing: **immediate**.

### 3. TopStrip
File: `apps/web/src/components/shell/TopStrip.tsx`
- User thinks: NAV/Today/Total return reflect their account.
- Actually showing: aggregate of all 4 portfolios. NAV tooltip
  (`:72-79`) names "Aggregate across N paper portfolios" but Today
  P&L (`:82-99`) and Total return (`:100-115`) have no scope hint
  in their tooltip text.
- Severity: **confusing**.
- Class: **wording**.
- Smallest fix: add `Aggregate across N paper portfolios.` prefix to
  the existing tooltip strings at `:86` and `:104-108`. One-line each.
- Effort: **S**. Timing: **immediate**.

### 4. Picks page (Overview)
File: `apps/web/src/pages/PicksPage.tsx`
- User thinks: signals are a coherent recommendation list.
- Actually showing: `actionTitle("hold") = "No edge yet"` and
  `actionGuidance("hold") = "Not a buy yet."` — both reasonable.
  But launcher metric "buy · sell · trim · hold" (`:270`) treats
  `hold` as a category alongside actionable verbs, inflating the
  count and reading like "4 actions to take" when most are no-ops.
- Severity: **confusing**.
- Class: **wording**.
- Smallest fix: separate the launcher metric into "actionable" vs
  "watch-only": `${buyCount + sellCount + trimCount} actions ·
  ${watchlistCount} watch-only` at `:270`. Counts stay sourced from
  the same arrays.
- Effort: **S**. Timing: **immediate**.

### 5. PickModal reasoning
File: `apps/web/src/components/picks/PickModal.tsx`
- User thinks: AI is giving a specific recommendation for this name.
- Actually showing: ReasoningCard at `:222-229` is hard-coded to
  `researchPreview` mode because picks are research rows with no
  attached `paper_trade`. The user sees the honest "research-preview
  absence state" but the surrounding header says "Recommendation"
  (`:206`) with action badge + "conviction" label.
- Severity: **confusing** (header is decisive, body is observational).
- Class: **lifecycle**.
- Smallest fix: change the "Recommendation" section title at `:206`
  to "Signal" or "AI signal" when `paperTradeId == null`. Picks
  outside the paper-trading lifecycle are signals, not
  recommendations to act.
- Effort: **S**. Timing: **immediate**.

### 6. Decisions page
File: `apps/web/src/pages/Decisions.tsx`
- User thinks: timeline of trades the AI made.
- Actually showing: live + recovered + replay mixed; "Recovered"
  filter at `:40` correctly labelled, but the default "All" view
  (`:36`) blends `is_replay=true` rows with live rows in the
  timeline. New users see a busy timeline that overstates AI
  output.
- Severity: **confusing**.
- Class: **scope mismatch**.
- Smallest fix: default filter to `"live"` instead of `"all"` at
  `Decisions.tsx:50`; "Recovered" stays one click away. No UI
  redesign.
- Effort: **S**. Timing: **immediate**.

### 7. Live MTM vs Official close
File: `apps/web/src/components/portfolio/PortfolioSnapshot.tsx:151-232`
- User thinks: the big number is "my money right now".
- Actually showing: dual display is honest — Live estimate primary,
  Official close secondary. But when Polygon falls back to EOD
  (`:184-187`), the line reads "using EOD fallback (Polygon
  unavailable)" *while still being labelled "Live estimate"* (the
  header tag at `:209`) — internal contradiction.
- Severity: **confusing**.
- Class: **wording**.
- Smallest fix: when `polygonStatus !== "ok"`, drop the "Live
  estimate" prefix and lead with "Last close (Polygon unavailable)"
  at `PortfolioSnapshot.tsx:185`. Value stays identical to Official
  close; user sees them collapse honestly.
- Effort: **S**. Timing: **immediate**.

### 8. Stock paper lifecycle (positions/exits)
File: `apps/web/src/components/portfolio/PositionsTable.tsx`
- User thinks: "AI Next Step" column tells them what AI will do.
- Actually showing: `nextStep()` at `:27-49` is a frontend-derived
  heuristic on `return_pct` (>=100 → "Lock partial gains",
  -10 → "Review thesis", etc.). No engine signal involved. This
  violates the same anti-pattern Phase L UI-1 fixed in PickModal.
- Severity: **dangerous** (it looks like AI advice; it is a JS
  conditional).
- Class: **wording**.
- Smallest fix: rename column header at `:177` from "AI Next Step"
  to "Position state" or "P&L bucket" and rephrase the text values
  (`:30-49`) from imperative verbs ("Lock partial gains") to
  observational ("Up >100%"). No new engine work required.
- Effort: **S**. Timing: **immediate**.

### 9. Options dormant lifecycle
File: `apps/web/src/components/options/OptionsStatusBanner.tsx`,
`apps/web/src/components/options/OptionsCanaryStatus.tsx`
- User thinks: options section is functional.
- Actually showing: ~25 options pages in nav (`pages/options/`),
  every one renders a dormant-engine banner sentence sourced from
  `/api/options/pipeline-status`. Zero positions, zero lifecycle
  events. PRE_CANARY_OPTIONS truth banner exists
  (`truth_banners.py:76-83`) but is per-surface, not nav-level.
- Severity: **confusing** (heavy nav for paused feature).
- Class: **lifecycle**.
- Smallest fix: in the options sidebar/nav entry, append a single
  `· dormant` suffix label sourced from
  `pipeline-status.engine_state` so the user sees the state before
  clicking in. No nav rewrite, one badge.
- Effort: **S**. Timing: **post-options-canary** (will flip on
  automatically when engine wakes).

### 10. Truth banners
File: `apps/api/src/system_state/truth_banners.py`
- User thinks: banners are universal status messages.
- Actually showing: 8 banner causes with one-banner-per-surface
  priority resolution (`:131-135`). Copy is locked, tone is
  carefully honest. No mismatch found.
- Severity: **acceptable**.
- Class: n/a.
- Smallest fix: none. Locks are healthy.

### 11. Freshness labels
File: `apps/web/src/lib/picks/freshness.ts`
- User thinks: "today's portfolio refresh at 11:30 PM ET"
  (`:253`) is a precise commitment.
- Actually showing: cron container has `TZ=America/New_York` env
  but `/etc/localtime → UTC`, so the scheduler fires at 03:30 UTC
  regardless of DST. In EDT (May) that *is* 11:30 PM ET; in EST
  (Nov-Mar) it fires at 10:30 PM ET. The frontend hint
  string would lie by one hour for 4 months/year.
- Severity: **confusing**.
- Class: **freshness**.
- Smallest fix: soften the string at `freshness.ts:253` from
  "11:30 PM ET" to "tonight's refresh" (no fixed-hour claim) until
  the cron timezone is fixed. Two-word edit.
- Effort: **S**. Timing: **immediate**.

### 12. Operational observability (Jobs Health)
File: `apps/web/src/pages/JobsHealth.tsx`
- User thinks: a single place to confirm "the AI is running".
- Actually showing: page renders job counts + last-run timestamps
  honestly. `scheduler_alive` boolean at `:42-43` is surfaced. No
  mismatch found.
- Severity: **acceptable**.
- Class: n/a.
- Smallest fix: none.

---

## TOP 10 COHESION GAPS (ranked by user-trust impact)

| # | Surface | 1-line truth gap | Severity | Class | Fix | Effort | Timing |
|---|---|---|---|---|---|---|---|
| 1 | PositionsTable "AI Next Step" column | A JS conditional on return_pct is presented as AI advice (`PositionsTable.tsx:27-49,177`) | dangerous | wording | Rename column to "Position state"; rephrase imperatives ("Lock partial gains") to observations ("Up >100%") | S | immediate |
| 2 | AccountingStrip "Total profit" | $4,786 from $100K replay-recovered account inflates the headline; banner names market value, not profit contribution (`AccountingStrip.tsx:239-256`) | confusing | accounting | Banner copy: "Recovered positions contribute $X to Total profit (of $Y shown)" | S | immediate |
| 3 | PortfolioSnapshot scope | "Across 4 paper portfolios" silently includes two $1K test rigs (`PortfolioSnapshot.tsx:263`) | confusing | scope mismatch | Filter test portfolios from active-aggregate; honest count becomes 2 | S | immediate |
| 4 | Live MTM label during Polygon failure | "Live estimate" tag stays while body says "Polygon unavailable" (`PortfolioSnapshot.tsx:184-187,209`) | confusing | wording | When polygonStatus≠"ok", drop "Live estimate" prefix; lead with "Last close" | S | immediate |
| 5 | Decisions default filter | "All" view blends live + replay-recovered timelines, overstating AI output (`Decisions.tsx:36,50`) | confusing | scope mismatch | Default initial filter to "live"; "Recovered" remains one click away | S | immediate |
| 6 | PickModal "Recommendation" header | Decisive header sits above an honest research-preview absence state (`PickModal.tsx:206,222-229`) | confusing | lifecycle | Rename "Recommendation" → "Signal" when paperTradeId is null | S | immediate |
| 7 | Freshness hint string | "11:30 PM ET" is wrong 4 months/year because cron container is UTC (`freshness.ts:253`) | confusing | freshness | Soften to "tonight's refresh" until cron TZ is fixed | S | immediate |
| 8 | TopStrip Today P&L / Total return tooltips | No scope hint; user assumes per-account when it's aggregate (`TopStrip.tsx:86,104-108`) | confusing | wording | Prepend "Aggregate across N paper portfolios." to existing tooltip strings | S | immediate |
| 9 | PicksPage launcher metric | "buy · sell · trim · hold" treats hold as actionable, inflates apparent workload (`PicksPage.tsx:270`) | confusing | wording | Recompose as "${actionable} actions · ${watchlistCount} watch-only" | S | immediate |
| 10 | Options nav (dormant) | ~25 options sub-pages with no engine activity; per-surface dormant banner only inside the page (`OptionsStatusBanner.tsx`) | confusing | lifecycle | Append "· dormant" suffix to options nav root sourced from pipeline-status; reverts automatically when engine wakes | S | post-options-canary |

---

## Pattern summary

Five gaps (#1, #4, #6, #8, #9) are pure **wording** — none touch
canonical accounting, lints, or UX-5 architecture. Three (#2, #3, #5)
are **scope mismatch**: the aggregate worldview is honest but novice
users read it as per-account. One (#7) is a **freshness** string that
will silently lie when DST flips. One (#10) is the **dormant
lifecycle** of options nav, which auto-resolves when canary lights up.

All fixes are S-effort, single-file, immediate except #10 which sits
behind the paused Gate 5. No fix proposed here adds features,
endpoints, or ML. The most trust-load-bearing single change is #1
(PositionsTable "AI Next Step") because it has the same shape as the
anti-pattern Phase L UI-1 already fixed in PickModal and currently
violates that lock.
