# Phase 15g — Signal Freshness & Model Truth Audit

**Date:** 2026-05-11 (Monday)
**Audit window:** Live endpoints probed at ~23:37 UTC (~19:37 ET) — after the regular daily-pipeline 16:30 ET / 20:30 UTC scheduled run.
**Branch:** `phase-1/ledger`
**Latest commit at audit time:** `749488d` (Phase 15f — review flow)
**Audit type:** READ-ONLY. No code changes. No backend fixes. Data probes only.

---

## 1. TL;DR — Trust state right now

**The product currently displays Friday/Saturday data as if it were today's snapshot, with no user-visible indication that the Monday pipeline has not produced fresh state.**

Of 13 endpoints probed:
- **3 are fresh today** (market events, shadow signals, recommendations diagnostics — partial)
- **6 are 2-3 days stale** (paper summary, paper state, dashboard summary, paper equity, recommendations themselves, today's pick set)
- **4 expose no freshness timestamp at all** (options strategies / risk-summary / performance-summary / paper-trades — `as_of` is null on every options endpoint)

**The most damaging mismatch:** every individual recommendation returns `"stale_data": false` and `"enough_data": true` even though `generated_at` is `2026-05-09T02:30 UTC` (Saturday — 65+ hours old at audit time). The UI takes `pick.stale_data` at face value and renders the cards as fresh signals. Today's-read hero (Phase 15e) builds its sentence from these stale picks; subtitle says "constructive posture · 4.99% return"; PageChapter reads as a current state. The whole copilot UX of Phase 13–15 now sits on top of Saturday data without flagging it.

**Net effect:** the product is **actively misleading on freshness** as of audit time. This is the elite-product trust failure Phase 15g exists to catch.

---

## 2. Per-endpoint freshness audit (live data, 2026-05-11 23:37 UTC)

### 2.1 Paper portfolio + state (the most-load-bearing endpoints)

| Endpoint | Field | Value | Age | Status |
|---|---|---|---|---|
| `/api/paper/summary` | `as_of_date` | 2026-05-09 | 2d | **STALE** |
| `/api/paper/summary` | `last_decision_ts` | 2026-05-09T03:30:20 UTC | 65h | **STALE** |
| `/api/paper/summary` | `pipeline_status` | `"success"` | — | **MISLEADING** (last successful, not current) |
| `/api/paper/summary` | `engine_active` | `"none"` | — | conflicts with /paper/state |
| `/api/paper/state` | `as_of_date` | 2026-05-08 | 3d | **STALE** |
| `/api/paper/state` | `engine` / `fire` | `"B"` / `true` | — | **CONTRADICTS /paper/summary** (which says engine_active=none) |
| `/api/paper/state` | `reason` | "directional_regime + credit_stable + rates_calm" | — | from May 8 |
| `/api/paper/equity` | last point | `2026-05-09` | 2d | **STALE** (no Monday point) |
| `/api/dashboard/summary` | `as_of_date` | 2026-05-08 | 3d | **STALE** |
| `/api/dashboard/summary` | `regime.market_trend` | `"uptrend"` | — | from May 8 |

**Critical contradictions:**
- `paper/summary.engine_active = "none"` vs `paper/state.engine = "B" / fire = true`. Two endpoints disagree about whether the engine is firing. UI reads from both at different surfaces.
- `paper/summary.pipeline_status = "success"` is the literal last-successful-cycle marker, not a "ran today" signal — yet the field name reads as "currently healthy". Misleading by name.

### 2.2 Recommendations / picks (the entire Action Queue + Today's read hero)

| Endpoint | Field | Value | Age | Status |
|---|---|---|---|---|
| `/api/recommendations?latest=true&limit=5` | first pick `generated_at` | 2026-05-09T02:30:10 UTC | 65h | **STALE BUT NOT FLAGGED** |
| same | first pick `stale_data` | `false` | — | **LIES** (>48h old should be stale) |
| same | first pick `enough_data` | `true` | — | acceptable |
| same | total returned | 5 of `?limit=5` | — | endpoint serves data |
| `/api/recommendations/diagnostics` | `summary.total` | 100 | — | exists |
| same | `summary.buys` / `trims` / `holds` | 10 / 17 / 73 | — | composition known |
| same | `as_of` | not present | — | no top-level freshness field |

**Most damaging finding:** `pick.stale_data` is the single boolean the UI relies on (PickBox `data-fresh` attribute, Today's-read hero composition, briefing posture). It returns `false` on data 65 hours old. Phase 13b's `useFetchWithError` only catches transport failures; it does NOT catch the case where the backend returns yesterday's-yesterday's data with a "fresh" flag.

### 2.3 Market events / catalysts (the only consistently-fresh endpoint)

| Endpoint | Field | Value | Age | Status |
|---|---|---|---|---|
| `/api/market/events?symbols=SPY,QQQ` | `generated_at` | 2026-05-11T23:37:05 UTC | <1m | **FRESH** ✓ |
| same | `status` | `null` | — | weird (expected "ready"/"empty"/"not-connected") |

Events feed appears to refresh on demand per request — fresh per call. Only consistently-current surface in the product.

### 2.4 Shadow signals / anomalies

| Endpoint | Field | Value | Age | Status |
|---|---|---|---|---|
| `/api/shadow/signals` | count | 3 | — | data present |
| same | first signal `last_updated` | not in shape returned | — | **NO PER-ITEM TIMESTAMP** |
| `/api/anomalies?status=open` | count | 0 | — | could be healthy or silent fail |

Shadow signals visible (3 items), but no per-signal freshness timestamp in the API response — so the AlphaLab "Static baseline" pill (Phase 15a) protects against silent fallback substitution but not against a real-but-2-week-old signal looking current.

### 2.5 System health

| Endpoint | Field | Value | Status |
|---|---|---|---|
| `/api/system/health` | `overall` | `"healthy"` | **MISLEADING** |
| same | `as_of` | `null` | NO TIMESTAMP |
| same | `items` | `[]` (empty array, count 0) | **NO ACTUAL CHECKS** |

**This is a trust failure on the trust-reporting endpoint itself.** The system-health endpoint says "healthy" with zero actual checks behind it. Used by Ops + likely by future banner code. Currently nobody reads it, but if a 15h banner did, it would render a green "all systems operational" while the recommendation pipeline hasn't run today.

### 2.6 Options endpoints

| Endpoint | Top-level fields | `as_of` / `generated_at` | Status |
|---|---|---|---|
| `/api/options/strategies` | notice, observation_only_notice, strategies | not present | **NO FRESHNESS FIELD** |
| `/api/options/risk-summary` | n_open_trades, greeks, data_quality_flags, notice | not present | **NO FRESHNESS FIELD** |
| `/api/options/performance-summary` | n_closed_trades, by_strategy, data_quality_flags, observation_only_notice | not present | **NO FRESHNESS FIELD** |
| `/api/options/paper-trades?limit=2` | notice, count, trades | not present | **NO FRESHNESS FIELD** |
| `/api/options/observations?limit=2` | count = 0 | n/a | empty (could be intentional) |

Every options endpoint exposes data + a `notice` / `observation_only_notice` paper-trading disclaimer, but **no `as_of` or `generated_at`** on any of them. Options pages render counts and Greeks with no way for the user to know how stale the snapshot is. The `data_quality_flags` field exists but isn't surfaced in the UI.

### 2.7 Endpoints that DON'T exist

Probed but missing:
- `/api/today` — 404
- `/api/now` — 404
- `/api/freshness` — 404
- `/api/jobs` — 404
- `/api/scheduler/status` — 404
- `/api/ops/status` — 404

**There is no system-wide freshness API.** No single endpoint a UI can call to ask "when did the daily pipeline last run / what is the last-completed timestamp per channel?" Every freshness signal has to be inferred from per-endpoint `as_of_date` / `generated_at` / individual record `generated_at` — and most endpoints don't carry one.

---

## 3. What ran today (2026-05-11), per the live evidence

| Pipeline component | Today? | Evidence |
|---|---|---|
| 1. Ingestion (FRED, market data) | **No clear evidence** | No top-level "ingestion ran" signal. Equity curve has no Monday point. |
| 2. Recommendation generation | **NO** | Latest pick.generated_at = 2026-05-09T02:30 UTC (Saturday). |
| 3. Posture generation | **NO** | /paper/state.as_of_date = 2026-05-08 (Friday). |
| 4. Signal ranking | **NO** | Same source as #2; ranked output is the same May 9 batch. |
| 5. Events / catalysts ingest | **YES** | /api/market/events.generated_at = 2026-05-11T23:37 UTC (now). |
| 6. Shadow evaluation | **UNKNOWN** | /api/shadow/signals returns 3 items; no per-item timestamp visible. |
| 7. Options pipeline | **UNKNOWN** | All options endpoints return data without `as_of` — cannot tell. |
| 8. Paper portfolio refresh | **NO** | /paper/summary.as_of = 2026-05-09. /paper/equity last point = 2026-05-09. |
| 9. Scheduler / tick loop success today | **NO directly visible signal** | No /api/jobs or /api/scheduler endpoint. /system/health says "healthy" with empty items. |
| 10. Stale timestamps anywhere | **YES, multiple** | Paper summary 2d, paper state 3d, dashboard 3d, equity 2d, recommendations 65h. |

**Verdict:** The Monday daily-paper-pipeline (scheduled 16:30 ET = 20:30 UTC, ~3 hours before audit time) appears to have **not run, not completed, or not propagated**. The product is serving Friday/Saturday data on Monday evening with no surface indication.

---

## 4. Stale / degraded components (ranked by user-trust risk)

1. **`/api/recommendations` `pick.stale_data` flag is broken.** Returns `false` on 65h-old data. Every PickBox renders as `data-fresh` accordingly. Today's-read hero (Phase 15e) composes a confident sentence from this stale set. **HIGHEST trust risk.**
2. **`/api/paper/summary.pipeline_status = "success"`** reads as "ran successfully today" but actually means "last cycle that completed succeeded." Field name lies.
3. **`/api/paper/state` vs `/api/paper/summary` disagree on engine state.** State says engine=B/fire=true; summary says engine_active=none. UI reads from both depending on surface.
4. **`/api/system/health` returns `overall: "healthy"` with zero items.** Trust-reporting endpoint that itself isn't trustworthy.
5. **All options endpoints lack `as_of` / `generated_at`.** Options pages can't display "as of when" for chains, observations, or risk snapshots.
6. **No system-wide freshness API.** UI has no way to ask "when did the daily pipeline last complete" — has to infer from per-endpoint shapes that don't all expose one.
7. **`/api/dashboard/summary.as_of_date` is Friday's** while `/api/paper/summary.as_of_date` is Saturday's. Both "current" surfaces, two different days. Phase 13k canonical fix only resolved which to read for NAV/cash; it did not resolve as_of disagreement.
8. **`/api/anomalies?status=open` returns 0** — could be honestly zero anomalies, or could be silently failed evaluation. No way to tell from the endpoint alone.
9. **PortfolioSnapshot `freshAt` field on Overview** displays whichever endpoint resolved last (`paper/summary.as_of_date` or `dashboard/summary.as_of_date`). Currently shows "2026-05-09" or "2026-05-08" depending on race, with no UI annotation that this is 2-3 days old.
10. **Ops page Phase 15a "status pending" labels are now coincidentally honest** — because the JobRow `last="unknown"` change in 15a labels each row "status pending — live last-run status not wired yet". This was a defensive truth fix; turns out today is exactly the day where that defensive label saves the page from lying. ✓ already shipped.

---

## 5. Recommended freshness SLAs

Calibrated to the actual scheduler cadence (daily 16:30 ET pipeline, intra-session refresh for events). Three bands per channel: **fresh** (acceptable), **degraded** (show muted; still actionable), **stale** (show warning; copilot tone shifts to cautious).

| Channel | Fresh | Degraded | Stale |
|---|---|---|---|
| Recommendations / picks | < 16h | 16-30h | > 30h |
| Posture / market regime | < 16h | 16-36h | > 36h |
| Paper portfolio snapshot | < 30 min during market hours; < 16h overnight | 30m–4h / 16-30h | > 4h / > 30h |
| Paper equity curve | < 24h | 24-48h | > 48h |
| Market events / catalysts | < 6h | 6-24h | > 24h |
| Shadow signals | < 24h | 24-48h | > 48h |
| Anomalies | < 24h | 24-48h | > 48h |
| Options chains / Greeks | < 6h | 6-24h | > 24h |
| Options paper trades | < 1h after last trade event | 1-6h | > 6h with open trades |
| Risk dashboard | < 30 min during market hours | 30m-4h | > 4h with positions open |

**Audit-time state per the SLA:** picks STALE (65h), posture STALE (3d), paper portfolio STALE (2d), equity DEGRADED (2d), events FRESH (<1m), shadow UNKNOWN (no ts), anomalies UNKNOWN (empty), options UNKNOWN (no ts), risk UNKNOWN (no ts). 4 of 9 channels are STALE per these SLAs right now and the UI shows none of it.

---

## 6. Proposed user-facing freshness model

Calm. Subtle. Honest. Never alarmist. Inspired by Phase 14b's "executive briefing subtitle" pattern + Phase 15a's "Static baseline" pill on AlphaLab.

### 6.1 Core principle

**Every primary surface that displays time-bound data should carry a tiny `as of` annotation in the same eyebrow / meta register as Phase 15a's static-baseline pill — never a banner, never a modal, never red, never alarmist.**

When the channel's freshness drops to **degraded**, the annotation copy hardens slightly ("delayed", "awaiting refresh"). When it drops to **stale**, the copilot's tone shifts to cautious in derived sentences (briefing.headline already does this when picks.length === 0; extend to "stale ≥30h" condition).

### 6.2 Calm freshness language

| State | Annotation copy (verbatim) |
|---|---|
| Fresh — recommendations | "Signals refreshed Nm ago" / "Signals refreshed at 9:30 AM ET" |
| Fresh — posture | "Market posture updated this morning" |
| Fresh — events | "Catalysts refreshed Nm ago" |
| Fresh — portfolio snapshot | "Account valued Nm ago" |
| Degraded — recommendations | "Signals from yesterday's close — awaiting next refresh" |
| Degraded — posture | "Posture not yet refreshed today" |
| Degraded — portfolio | "Account snapshot delayed — last update 9:30 AM ET" |
| Stale — recommendations | "Recommendations based on last completed cycle (Saturday close). Today's pipeline has not yet produced new state." |
| Stale — posture | "Market posture is from Friday close — awaiting next refresh." |
| Stale — events | "Catalyst feed delayed — last update Nh ago." |
| Stale — portfolio | "Account snapshot Nh stale — last refresh did not propagate." |
| All channels stale + no recent runs | "Awaiting next market refresh — copilot is reading the last completed cycle." |

**Anti-patterns explicitly rejected** (per the brief):
- "Scheduler failure" / "job dead" / "queue timeout" / "ingestion exception" — operator vocabulary; never user-facing
- Red banners across the page header
- Modal pop-ups warning of stale data
- Animated yellow chevrons / pulsing dots
- "0 critical issues" green checkmarks (already a discipline lock — don't manufacture confidence)

### 6.3 Surface-by-surface integration

- **Today's-read hero (Overview, Phase 15e):** add tiny eyebrow line `"AS OF Sat 9 May · stale by 2 days"` (only when stale). Hero sentence wording should soften: when picks are stale, the hero opens with `"Reading the last completed cycle (Saturday close) ..."` instead of `"Cautious posture · 5 trims..."`.
- **TopStrip NAV cell:** when paper/summary is stale, NAV value renders muted with a `·` indicator and a hover/tap title `"NAV from Sat 9 May · awaiting Monday refresh"`.
- **PortfolioSnapshot:** add an `as of date` line in the same eyebrow region as the existing "Portfolio" eyebrow. Already has `data.freshAt` plumbed (Phase 13k) — just needs to be rendered.
- **Action Queue cards:** PickBox `data-fresh` attribute is currently driven by the broken `pick.stale_data` flag. Replace with a derived `isPickFresh(pick.generated_at)` function that ignores the backend's flag and computes from `generated_at` directly.
- **PageChapter:** when underlying data is stale, the NEXT cell could show a small annotation `"Next refresh expected at 9:30 AM ET"` derived from the known scheduler cadence.
- **Options pages:** every page-level header should carry a `"Chains as of —"` line. Today's-state: not available — endpoints don't expose `as_of`. Backend fix needed before UI can render this honestly.
- **`/risk`:** page header `as of` line; if portfolio snapshot is stale, the calm card opens `"Reading the last completed snapshot — fresh risk numbers will appear after the next pipeline run."`

---

## 7. Highest-risk trust gaps (ranked)

1. **`pick.stale_data = false` on 65h-old data.** Every Action Queue card, Today's-read hero, executive briefing subtitle, and TodayPanel posture line is currently derived from picks the backend incorrectly says are fresh. **The single most dangerous lie in the product right now.**
2. **`pipeline_status = "success"` reads as "ran today".** Used by future Ops banners; would render green when nothing ran today. Field rename + UI never displaying it raw.
3. **System-health endpoint returns "healthy" with zero items.** Any future UI surfacing system health would render a confident green state on what is in fact an unmonitored system.
4. **Two endpoints disagree on engine state.** Wherever the UI reads from `/paper/state` (engine=B firing) vs `/paper/summary` (engine_active=none), users see different truths on different surfaces. Could be a same-day timing window normally; on a stale day like today it's load-bearing.
5. **Options surface has zero freshness signal.** Pages render Greek aggregates and trade lists with no way for the user to know when the snapshot was taken.
6. **`/dashboard/summary.as_of` and `/paper/summary.as_of` are different dates.** UI reads from both depending on surface; user could see "Today's" data labelled with two different dates.
7. **Today's-read hero (Phase 15e) builds confident copilot prose from the stale data layer.** The phase's emotional-ROI thesis ("the copilot answers the door first") becomes a liability when the door opens onto Friday's reality narrated as Monday's.
8. **AlphaLab's `usingFallback` pill (Phase 15a) protects against silent registry substitution but not against shadow signals being technically present yet weeks old.** No per-signal `last_updated` rendered.
9. **NextStepCard rationale on `/overview`** ("N picks need a closer look — start with what changed today") makes a "today" claim — when "today" hasn't happened yet in the data layer, this is misleading.
10. **No global "last successful cycle" pill in chrome.** Every other premium investing tool surfaces a small "as of HH:MM ET" in the corner. This product has nothing.

---

## 8. Minimal implementation plan (no implementation in this commit — just the proposal)

Five tightly-scoped commits, each addressing one trust gap. All client-side (no backend changes); the existing endpoints carry enough timestamp data to derive freshness states locally.

### 15h.1 — Replace broken `pick.stale_data` flag with derived freshness (S, low risk)

- New function `isPickFresh(pick): "fresh" | "degraded" | "stale"` in `lib/picks/api.ts` — pure function on `pick.generated_at` against the SLA (16h fresh / 30h degraded / >30h stale).
- PickBox + Action Queue + briefing logic call this instead of `pick.stale_data`.
- Today's-read hero composition reads the derived freshness; when most picks are stale, hero opens with "Reading the last completed cycle..." instead of confident "constructive posture..."

### 15h.2 — Render `as of` annotation on PortfolioSnapshot + TopStrip NAV (S, low)

- PortfolioSnapshot already has `data.freshAt` plumbed (Phase 13k). Render it as `"As of Sat 9 May"` in the existing eyebrow row when present, with a degraded/stale tier shown.
- TopStrip NAV cell: when staleness derives, render the value muted (~ --fg-3 instead of --fg) with a title attr explaining.

### 15h.3 — Compose freshness sentence into Today's-read hero (S, low)

- Extend `OverviewHero` (Phase 15e) to accept a `freshness` prop computed in PicksPage from the picks set + commandBar.freshAt.
- When freshness is degraded or stale, the hero's eyebrow becomes `"AS OF Sat 9 May · stale by 2 days"` and headline opens with the cautious-tone copy from §6.2.

### 15h.4 — Add a global "last successful cycle" pill to TopStrip (S-M, low)

- Tiny right-aligned pill in TopStrip showing `"as of 9 May · 9:30 AM ET"` derived from `paper/summary.last_decision_ts`.
- When stale per SLA, pill carries a quiet warning tone (not red — `--fg-3` muted text + dotted border instead of solid).
- Click/tap opens a small overflow showing per-channel freshness.

### 15h.5 — Resolve `paper/summary.engine_active` vs `paper/state.engine` disagreement (S, low)

- Document which is canonical. Likely `/paper/state` is the live decision row; `/paper/summary` is the daily snapshot. UI should use `/paper/state` for engine display; `/paper/summary` for portfolio numerics (already canonical post-13k).
- Audit current consumers of `engine_active` field and re-source them to `/paper/state`.

### Out of scope for 15h (deferred or backend-required)

- **System-health endpoint fix** — backend would need to actually compute checks rather than return "healthy"+empty. Out of UI scope.
- **Options endpoints `as_of` field addition** — backend change. Until then, options pages cannot honestly display freshness.
- **`pipeline_status` field rename** — backend change.
- **Per-shadow-signal `last_updated` propagation** — backend change.
- **A real `/api/freshness` summary endpoint** — backend feature; would replace 15h.4's per-channel inference with a single source of truth.

---

## 9. What's NOT broken (preserve as-is)

- **Phase 15a "Static baseline" pill on AlphaLab** — exact pattern Phase 15h should use everywhere
- **Phase 15a Ops `last="unknown"` pills with "status pending" copy** — defensive label that turns out to be honest today
- **Phase 13a–j discipline locks** (no fake marks, no swallowed errors, paper-trading disclaimers, FetchError visible state)
- **Phase 15e localStorage diff line** — already honest about no-prior / stale-prior / no-change cases
- **Phase 13k canonical `/api/paper/summary` source for portfolio numerics** — correct architectural call; just doesn't propagate freshness yet
- **The existing `pick.generated_at` field on every pick** — the raw timestamp IS in the data; only the broken `stale_data` flag derived from it is wrong

---

## 10. Audit summary in one line

**The Phase 13–15 copilot UX is sitting on a freshness layer that quietly says "fresh" while serving 65-hour-old recommendations, and the lie surfaces on every premium moment we've built.** Phase 15h ships the calm freshness language above; no backend changes required for the first round; the elite-product trust ceiling cannot move higher until this layer is honest.

---

*Audit conducted 2026-05-11 ~23:37 UTC (~19:37 ET, post-scheduler-window). All endpoint probes were live HTTP calls through the local Vite proxy to the running FastAPI backend. No code modified during audit. No mocks. No fabrications.*
