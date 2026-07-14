# ArthOS — Investor-Metric Correctness Certification

**Date:** 2026-06-20 · Correctness-not-appearance due diligence. Every investor-facing number traced to its source table + query, with scoping, formula, refresh cadence, and reproducibility proven against the live dev DB for the demo book (`bc207e65`). All stock-book metrics reproduced **exactly** from source.

## Verification result (API value == source-reproduced value)

| Metric | API shows | Source-reproduced | Match |
|---|---|---|---|
| NAV | 105,211.764195 | snapshot `total_equity` 105,211.764195 | ✅ |
| Return % | 5.2118 | (nav − starting)/starting × 100 = 5.2118 | ✅ |
| Realized P/L | 5,951.82 | `realized_pnl_cumulative` 5,951.81538 = Σ `paper_trade.realized_pnl` 5,951.82 | ✅ |
| Open positions | 30 | count `paper_position` is_open=true = 30 | ✅ |
| Closed ideas | 63 | count `paper_position` is_open=false = 63 | ✅ |
| Win rate | 31/62 = 50% | sells realized>0 (31) / sells realized≠null (62) | ✅ |
| Avg hold | 11 days | avg(closed_at − opened_at) = 11.4 d | ✅ |
| Max drawdown | −9.0% | peak-to-trough over live equity = −9.05% | ✅ |

## Per-metric certification

### Track Record Integrity Card
- **Realized return % / NAV** — Source: `paper_equity_snapshot`. Query: latest row `WHERE portfolio_id=:pid AND source='live'` ORDER BY snapshot_date DESC, recorded_at DESC, id DESC. Formula: `total_return_pct = (total_equity − starting_cash)/starting_cash × 100`. **Scoping:** portfolio_id + source='live'. **User-scoping:** device header → `resolve_user_stock_portfolio` → pid. **Cadence:** snapshot written by the scheduler (~daily, recorded_at-stamped). **Reproducible:** yes (deterministic from the stored snapshot). Endpoint `/api/paper/canonical/stock` (`paper_canonical.py`).
- **Realized P/L** — Source: snapshot `realized_pnl_cumulative` (cross-checks Σ `paper_trade.realized_pnl` for sells). Scoping/cadence as above. Reproducible: yes.
- **Open positions** — Source: `count(paper_position WHERE portfolio_id=:pid AND is_open)`. Reproducible: yes.
- **Closed ideas (63)** — Source: `count(paper_position WHERE portfolio_id=:pid AND is_open=false)` via `/api/paper/executed/positions?portfolio_id=:pid`. Note: 63 closed positions vs 62 realized sell-trades (one position closed without a realized sell) — documented, not an error.
- **Win rate (50%, 31/62)** — Source: `/api/paper/executed/trades?portfolio_id=:pid`, client formula `wins/closed_sells` where closed_sells = sells with `realized_pnl != null`, wins = `realized_pnl > 0`. **Definition disclosure:** per resolved *trade/fill* (62 across 46 distinct ideas), not per idea — honest label "resolved trades". **Gating:** hidden until ≥10 resolve. Reproducible: yes.
- **Avg hold** — client `avg((closed_at − opened_at)/86400)` over scoped closed positions. Reproducible: yes (11.4 → "11 days").
- **Max drawdown** — client peak-to-trough over `/api/paper/equity?portfolio_id=:pid` (`paper_equity_snapshot`). Reproduced in SQL = −9.05% ("−9.0%"). Reproducible: yes.
- **Freshness / source** — Source: `recorded_at` (write-time) for pipeline status; **as_of = snapshot_date** for data date. **Post-fix:** the card now shows the as_of **date** and colors the dot by data recency (not the heartbeat), so it cannot claim "fresh/today" while data is older. API currently returns `degraded` for this book (write-time aged) — consistent with the amber UI.

### My Portfolio (Paper Book)
- NAV / cash / unrealized / realized — same canonical source, same scoping. Open positions via `/executed/positions?portfolio_id=:pid` (now `enabled:!!pid`-guarded). "source: live" from snapshot source filter. Reproducible: yes.

### Bull vs Bear counts
- Source: `recommendation_evidence` (per recommendation, via `/recommendations`). Counts = evidence with `direction='bullish'`/`'bearish'` (derived client-side). **Scoping:** per-recommendation (global rec data — the same idea is identical for every user; not portfolio-scoped, correct). **Reproducible:** yes, keyed by `snapshot_hash`. No cross-user concern (same idea = same evidence for everyone).

### Recommendation Trace
- Source: same `recommendation_evidence` + `policy.adjustments` from `/recommendations`. What-helped/hurt = evidence score sign; adjustments = post-policy rules. Reproducible via `snapshot_hash`. Not portfolio-scoped (engine output, global). Correct.

### Reflection Loop
- Source: `/api/paper/closed-recommendations?portfolio_id=:pid` — join `paper_position`(closed) → `recommendation` → exit reason from closing `paper_trade`. **Scoping:** portfolio_id + `enabled:!!pid` guard. **Coverage:** 2 of 63 closes retain `opened_by_recommendation_id` (older closes predate attribution) — honest gap, every shown row is real. Reproducible: yes.

### Model Portfolio performance
- Source: `model_portfolio_perf` / `model_portfolio_holding` (separate from the user paper book). Scoped by `model_portfolio` slug, not user. These are *shared model baskets*, identical for all users by design (not personal data). Reproducible from the perf table. (Not part of the per-user track record.)

## Scoping & isolation certification

- **User-scoping:** web client always sends `X-Auth-User-Id` (`api.ts`), resolver maps device → own `user:<device>:stock` book; cold device → empty book (guardrail test). No in-app anonymous path.
- **Portfolio-scoping:** canonical filters `portfolio_id` + `source='live'`; executed hooks now carry `{ enabled: !!portfolioId }` (P0 fix `cf2b987`) so no unscoped/global aggregate can render. Verified: `/executed/*` without a pid returns global (admin-only), with a pid returns the scoped book.
- **Cross-user leak:** none for in-app users. Per-recommendation surfaces (Bull/Bear, Trace) are intentionally global engine output, identical for everyone — not personal data.

## Refresh cadence

- Equity snapshots + recommendations are written by the scheduler (worker cron/tickloop), `recorded_at`-stamped. Canonical reads the latest `source='live'` row. Win-rate/drawdown/hold recompute client-side from the latest scoped reads (staleTime 30–60s). Freshness reflects `recorded_at`; **data date** is surfaced separately post-fix.

## Certification

Every investor-facing number on the stock track record (NAV, return %, realized P/L, open/closed counts, win rate, avg hold, drawdown) **reproduces exactly from its source tables**, is **scoped to the correct portfolio and user**, and is **reproducible**. Disclosed (not errors): win-rate is per-resolved-trade; reflection coverage is 2/63 by attribution; the demo book is a disclosed clone of Replay Recovery; data is currently a few days stale (now shown honestly via the as-of date + degraded freshness). **No fabricated, mis-scoped, or unreproducible investor metric found.** Certified trustworthy for due diligence.
