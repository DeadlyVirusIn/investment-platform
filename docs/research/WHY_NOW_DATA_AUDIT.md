# "Why Now?" — Data Source Audit

**Date:** 2026-06-20 · Task: can a simple per-recommendation "Why now?" catalyst line be built from **existing** data? Scope: no new data providers, models, or trading infra.

## Verdict

Yes — a useful, honest "Why now?" line ships from data already on the idea page. It is **implemented** on PickPage (accent card between "As of" and "Why this idea exists"). Some of the richer catalyst types listed (earnings, analyst sentiment, market breadth) are **not** populated today; those are documented below as the minimum backend work.

## What IS available now (used by the shipped line)

| Catalyst type | Source (existing) | Status |
|---|---|---|
| Sector / trend strength improving | rec `evidence` (`trend_momentum` factors: price_vs_sma_long, sma_20_vs_50, trend_strength) — already in the `/recommendations` payload | used (dominant driver phrase) |
| Volatility creating opportunity | rec `evidence` (`volatility_risk`: atr_pct_14, max_drawdown) | available (driver when it dominates) |
| Recency / freshness | rec `generated_at` | used ("still true on today's read") |
| Fresh news catalyst | `useSymbolNews` (`/news/symbol/{symbol}`) — already fetched on PickPage | used (recent headline link when within 7 days) |

The shipped deriver (`apps/web/src/v2/lib/whyNow.ts`) composes: dominant current driver (reusing the Bull-vs-Bear factor split) + freshness + optional recent news link. Zero new fetches — every input is already loaded by the page.

## What is NOT available (documented backend work)

| Catalyst type | Why not available | Minimum backend work |
|---|---|---|
| **Earnings approaching** | `earnings_event` table is **empty** (0 rows with `event_date >= today`); `/market/events` returns `earnings: []` for every symbol checked (GE, JBHT, SIRI, CSCO, JAZZ, AAPL, MSFT, NVDA). | Populate `earnings_event` via the existing ingestion path (provider already wired, just not run/backfilled). Then add a `useSymbolEvents` hook on the existing `/market/events` endpoint and fold "earnings in N days" into `whyNow`. No new provider — only run/backfill + one read hook. |
| **Analyst sentiment improving** | Engine v1 does not compute a sentiment/analyst factor (evidence shows `sentiment` family absent; beta also "not computed in engine v1"). | Add an analyst-revision/sentiment factor to the recommendation engine (engine change — out of this sprint's scope). |
| **Market breadth improving** | No per-recommendation breadth signal stored; breadth is a market-level series, not attached to a rec. | Compute a market-breadth series (advancers/decliners or % above MA) and expose it as context; then reference it in `whyNow`. Backend + data work. |

## Recommendation

Ship the evidence + freshness + news version now (done). When earnings ingestion is backfilled (cheapest, highest-value next step — provider already exists), add the "earnings in N days" branch via one read-only hook on `/market/events`. Analyst sentiment and market breadth require engine/data work and are P2.
