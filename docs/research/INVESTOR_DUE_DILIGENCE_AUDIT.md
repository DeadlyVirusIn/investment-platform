# Investor Technical Due-Diligence Audit

**Date:** 2026-06-20 · Lens: skeptical investor verifying every investor-facing number can be defended. Traced all surfaces to source (endpoint → SQL/ORM → table) and verified scoping, reproducibility, and cross-user isolation against the live dev DB.

## Per-metric defensibility

| Metric | Where from | Real? | Reproducible? | Can be wrong? | Show another user's data? | Challenge? |
|---|---|---|---|---|---|---|
| NAV / realized return / realized P/L | `/paper/canonical/stock` → `paper_equity_snapshot` WHERE `portfolio_id=:pid AND source='live'` | Yes (stored snapshot) | Yes (deterministic from snapshot) | Only if snapshot stale (see P0-2) | No — scoped to resolved pid | "Is NAV current?" — see freshness |
| Open positions count | canonical → `count(paper_position WHERE pid AND is_open)` | Yes | Yes | No | No | None |
| Closed ideas / win-rate / hit-rate / expectancy | `/paper/executed/trades?portfolio_id=:pid` (sells w/ realized_pnl), computed client-side | Yes | Yes | **Was: global flash during load (P0-1, fixed)**; win-rate counts fills not ideas (P1) | **Was yes during load (P0-1, fixed)** → now No | "Per-idea or per-fill?" (P1) |
| Avg hold time | client-side `(closed_at-opened_at)` over scoped closed positions | Yes | Yes | No | No (fixed w/ P0-1) | None |
| Max drawdown | client-side peak-to-trough over `/paper/equity?portfolio_id=:pid` | Yes | Yes | No | No | None |
| Freshness / source | canonical `freshness` from `recorded_at`; `source='live'` filter | Yes | Yes | Label semantics (P0-2) | No | "Fresh but as-of 3 days ago?" (P0-2) |
| Recommendation / Bull-vs-Bear / Trace / Why-now | `/recommendations` → `recommendation` + `recommendation_evidence` (+ `snapshot_hash`) | Yes | Yes (snapshot_hash) | No | No (global, not per-user — same for everyone) | None |
| Reflection Loop | `/paper/closed-recommendations?portfolio_id=:pid` join `paper_position`+`recommendation` | Yes | Yes | No | No (scoped + `enabled` guard) | "62 closed but 2 reflections?" (P1) |
| TrustBanner "N calls live" | `/recommendations` global count (engine metadata, intentional) | Yes | Yes | No | No (engine-wide, not personal) | None |
| TrustBanner "X/10 accuracy" | `/paper/executed/trades?portfolio_id=:pid` (scoped) | Yes | Yes | Was global flash (P0-1, fixed) | No (fixed) | None |

## Verified safe (cannot leak / cannot be wrong)

- **Identity / resolver:** authenticated device → own `user:<device>:stock` book; cold device → empty book (guardrail test). Web client **always** sends `X-Auth-User-Id` (`api.ts:34`, auto-generated device id) → no anonymous path in-app.
- **Canonical endpoint:** every read filters by resolved `portfolio_id` AND `source='live'`; cannot return another portfolio's snapshot.
- **Persistence:** DB-backed; survives server restart + API rebuild (verified a prior sprint).
- **Math:** total-return, realized, drawdown, avg-hold, expectancy formulas all correct.

## P0 — credibility risks

- **P0-1 (GENUINE BUG — FIXED `cf2b987`):** `useExecutedTrades` / `useExecutedPositions` had no `enabled` guard, so investor surfaces (Integrity Card, Track Record, Trust Banner, Paper Book) fired an **unscoped** `/paper/executed/*` request while `portfolio_id` was resolving — returning aggregates across **all 58 portfolios** — and briefly rendered global win-rate / closed-count / positions before correcting. Fixed by gating the hooks with `{ enabled: !!portfolioId }` (global operator/admin callers preserved via default-true). This is the only genuine code bug found.
- **P0-2 (DESIGN / DATA — not a code bug, not implemented):** the Integrity Card shows **"Fresh · Live"** while `as_of` is **Jun 17** (today Jun 20). Freshness is measured from `recorded_at` (last write, 15.7h ago) by design (RC3), not from `snapshot_date` (the equity date). Defensible as "pipeline is alive", but a skeptic will read "Fresh" as "today's value". **Mitigation (no code change):** demo on a freshly-run pipeline so `as_of` is current; product decision (future) to surface data-date staleness distinctly. Not fixed here — it is not a bug, and the brief forbids UI changes.

## P1 — demo risks

- **Stale dev data:** latest recommendation `generated_at` = Jun 19; latest live snapshot `snapshot_date` = Jun 17. "Today's top idea" / "as of" read a day or more old. Run the ingestion + recommendation + snapshot pipeline immediately before any demo.
- **Win-rate is per resolved trade, not per idea:** denominator = 62 sell-trades across **46 distinct ideas** (scale-outs counted separately). Honest ("resolved trades") but a skeptic may expect per-idea. Disclose, or offer a per-idea variant (P2).
- **Reflection coverage:** only **2 of 62** closed positions retain `opened_by_recommendation_id`, so the loop reflects on 2 while the card shows 62 resolved. Explain: older closes (replay/execution) predate rec-attribution; coverage grows going forward.
- **Demo book provenance:** the demo device book (`bc207e65`) is a **clone of Replay Recovery** (`166b12ed`); the anonymous API fallback returns identical numbers. The figures are real paper-engine outcomes, but disclose the clone provenance if asked ("a seeded demo book of real paper results").
- **Count nuance:** 63 closed positions vs 62 realized sell-trades (1 position closed without a realized sell).

## P2 — future improvements

- Offer a **per-idea** win-rate alongside per-trade.
- Backfill `opened_by_recommendation_id` on historical closes to widen Reflection coverage.
- Anonymous (header-less) API calls return the shared demo book — not reachable in-app, but consider requiring auth or admin-gating the unscoped `/paper/executed/*` queries.
- Surface a **data-date** indicator distinct from pipeline freshness so "Fresh" can never be misread.

## Verdict

After fixing P0-1, every investor-facing number is sourced from real, scoped, reproducible data with no cross-user leak. The remaining risks are **demo-data freshness** and **disclosure** (clone provenance, win-rate definition, reflection coverage) — defensible with a one-line explanation, not bugs. Run the pipeline fresh before the meeting and the numbers hold under diligence.
