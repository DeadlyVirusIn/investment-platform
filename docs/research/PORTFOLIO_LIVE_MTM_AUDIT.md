# Portfolio Live MTM Audit — Read-Only Forensic

**Date**: 2026-05-19
**Branch**: `phase-1/ledger`
**Scope**: Can the dashboard serve a live mark-to-market NAV (`cash + Σ open_qty × latest_price`) **without** mutating `paper_equity_snapshot` (which is the documented immutable EOD anchor)?

**Short answer**: Yes. The math already exists server-side via `compute_equity_breakdown`. The dashboard's `/api/paper/summary` reader simply bypasses it in favor of frozen snapshot rows. The only price data available is **end-of-day (`timeframe='1d'`)** — there is no intraday/15-min ingestion. "Live" here means "EOD close repriced on demand", not real-time quotes.

This is a **feature add masked as a bug**: live MTM is implemented for per-portfolio detail endpoints but is *not* aggregated for the dashboard headline.

---

## 1. Data flow (text diagram)

```
Tiingo (primary) + Yahoo (fallback)
   │   apps/api/src/domain/prices/providers/{tiingo,yahoo}.py
   ▼
ingest_prices_daily()                                 (cron: 0 22 * * 1-5 ET, name `ingest_prices_daily`)
   apps/worker/src/jobs/ingest_prices_daily.py:27
   apps/api/src/domain/prices/service.py:243           writes timeframe='1d' only
   ▼
price_bar (asset_id, timeframe='1d', ts, close, …)    apps/api/src/db/models.py:84
   ▼
compute_equity_breakdown(session, portfolio)          apps/api/src/domain/paper_trading/paper_service.py:120
   = cash + Σ(qty × latest 1d close)                  (already live-MTM by construction)
   │
   ├── ALREADY EXPOSED LIVE per-portfolio:
   │     /api/paper/portfolios           paper.py:65    list, each w/ breakdown
   │     /api/paper/portfolios/{id}      paper.py:90    detail
   │     /api/paper/portfolios/{id}/equity paper.py:164 current=breakdown
   │
   └── WRITTEN to paper_equity_snapshot via snapshot_equity_now (source='live'|'replay'|…)
                                                       paper_service.py:173
         called by:
           run_paper_trading job (03:30 UTC)           run_paper_trading.py:220
           rebalance_engine                            rebalance_engine.py:479
           pending_replay                              pending_replay.py:175
           POST /api/paper/portfolios/{id}/snapshot    paper.py:196 (operator_manual)
   ▼
/api/paper/summary (operator.py:93)                   reads paper_equity_snapshot ONLY
   apps/api/src/api/operator.py:51 _latest_active_snapshots
   ▼
Dashboard PortfolioSnapshot.tsx → fetchCommandBar     apps/web/src/components/portfolio/PortfolioSnapshot.tsx:35
                                                       apps/web/src/lib/portfolio/api.ts:135 (paperFreshAt = paper.as_of_date)
```

---

## 2. Latest price evidence (queried 2026-05-19 ~17:35 UTC)

```sql
SELECT timeframe, MAX(ts), COUNT(*) FROM price_bar GROUP BY 1;
-- 1d | 2026-05-18 00:00:00+00 | 309 516
```

- **One timeframe only**: `'1d'`. No `'15m'`, `'1h'`, or any intraday table.
- **Providers**: `tiingo`, `yahoo` — both daily-only in this codebase.
- **Freshness vs now**: yesterday's close (~41h ago when queried). On a trading day, after `ingest_prices_daily` fires at 22:00 ET (≈02:00 UTC next day), this column advances by one trading session. Mid-session prices are NOT available.

### Open positions ARE price-resolvable

54 open `paper_position` rows across 4 active portfolios (`Default Paper`, `Replay Recovery Account`, `api-test`, `eq-curve-test`). Every position has a `latest_close` for 2026-05-18 (verified by `JOIN LATERAL` on `price_bar` ORDER BY ts DESC LIMIT 1). Coverage is 100% — no missing-bar holes.

### Latest live snapshots (snapshot_date=2026-05-17, recorded_at=2026-05-19 14:26 UTC)

```
portfolio                |  cash    | positions_value | total_equity
Default Paper            |  25.76   |  10 303.72      |  10 329.48
Replay Recovery Account  |  230.15  | 103 185.52      | 103 415.67
api-test                 |  939.50  |      91.99      |   1 031.50
eq-curve-test            |  943.68  |      91.99      |   1 035.67
                                                      Σ 115 812.32
```

The `2026-05-19` snapshot (the freshest 03:30 UTC run today) is also present with `total_equity=10 329.48` for Default Paper but uses 2026-05-17 close prices because the 2026-05-18 price_bar hadn't landed yet at 03:30 UTC. **Note: `ingest_prices_daily.last_run_at = 2026-05-19 02:06 UTC` ≪ `run_paper_trading.last_run_at = 2026-05-19 03:30 UTC`, so the snapshot writer actually had 2026-05-18 prices available** — the 03:30 run wrote 2026-05-17 anyway because `snapshot_date = now.replace(hour=0,…)` and the prior audit's stale snapshot is from yesterday's run, not today's.

---

## 3. Does `/api/paper/summary` use live prices?

**No.** `operator.py:51-69 _latest_active_snapshots` reads `paper_equity_snapshot.{total_equity,cash,positions_value,unrealized_pnl}` filtered to `source='live'`. The endpoint never joins `price_bar`.

Exception: `operator.py:180-196` joins `price_bar` to compute `replay_positions_mv` — but it's an *informational sub-metric* (how much of headline equity is rebuilt from the 2026-05-02 wipe), not the headline.

---

## 4. Existing live-MTM endpoints

| Endpoint | Source | Aggregated? |
|---|---|---|
| `/api/paper/portfolios` (paper.py:65) | `compute_equity_breakdown` → live | No (array of per-portfolio) |
| `/api/paper/portfolios/{id}` (paper.py:90) | live | No (single) |
| `/api/paper/portfolios/{id}/equity` (paper.py:164) → `current` | live | No (single) |
| `/api/paper/summary` (operator.py:93) | `paper_equity_snapshot` rows | **Yes — but stale** |
| `/api/dashboard/summary` | (downstream of operator) | same |

The live math already runs; the dashboard just doesn't ask for it.

---

## 5. paper_equity_snapshot semantics

From the model docstring (`db/models.py:498-506`):

> Phase L M079 — immutable + source-tagged equity snapshots.
> Truth contract (see `docs/research/M083_CANONICAL_SEMANTIC.md`):
>   - `source='live'` is canonical truth for user-facing reads
>   - replay/backfill/operator_manual are audit-only
>   - storage immutability: existing rows are never modified by replay
>   - presentation immutability: user-facing readers MUST filter `source='live'`

`snapshot_equity_now` docstring (`paper_service.py:180-194`) reinforces: *"appends a new row with the current `recorded_at`. … Existing historical rows are never modified."*

**Verdict**: documented as the immutable historical/EOD anchor. Adding live MTM must **not** write new rows to this table.

---

## 6. Cash mutation on intraday close

`paper_portfolio.cash` is the live cash anchor (column name `cash`, not `cash_current`). It is mutated on every fill:

- `paper_execution.py:312` `portfolio.cash = cash - cost` on buy
- `paper_execution.py:345` `portfolio.cash = cash + proceeds` on sell

So a close that fires intraday (between snapshots) **does** move `cash` immediately. `compute_equity_breakdown` reads this column live, so a live-NAV endpoint will reflect closes the moment they commit.

---

## 7. UI freshness handling today

`PortfolioSnapshot.tsx:75-87` derives a freshness tier from `data.freshAt` using `freshnessFromTs` (`freshness.ts:172`). Thresholds:
- `< 16h` → "fresh"
- `16–30h` → "degraded"
- `> 30h` → "stale"

`data.freshAt` = `paper.as_of_date` (a *date*, not a write timestamp). The UI shows e.g. `"Account snapshot delayed · last update Sat 9 May"`. There is no "Live estimate" vs "Official snapshot" distinction anywhere in the web layer.

---

## 8. Cron TZ misconfiguration impact

`ingest_prices_daily` runs at `0 22 * * 1-5` (ET). The worker container has `TZ=America/New_York` env but `/etc/localtime` symlinks to UTC, so supercronic fires it at **22:00 UTC ≈ 18:00 ET** — *during* market hours. The 2026-05-18 close it ingested at 22:00 UTC on 2026-05-18 is therefore *partial day data* (Tiingo returns latest available bar, which on a Sunday is Friday's). On Mon–Fri ingest at 22:00 UTC = 18:00 ET, this fetches today's close (regular market closes 16:00 ET) — that's actually fine for the price ingest, but means the EOD anchor is computed before official daily settlement (after-hours moves not yet locked).

For the live-MTM proposal: the price freshness ceiling is "latest 1d close", which is at-best yesterday's close, never an intraday quote.

---

## 9. Proposed minimal patch surface

### New endpoint

```python
# apps/api/src/api/operator.py (additive — no edits to existing handlers)

@router.get("/paper/live-nav")
def paper_live_nav(db: Session = Depends(get_session)) -> dict[str, Any]:
    """Live mark-to-market NAV across active portfolios.

    Computes NAV on-the-fly from paper_portfolio.cash + Σ(qty × latest 1d close).
    Does NOT read or write paper_equity_snapshot. The snapshot table remains
    the immutable EOD anchor; this endpoint is a freshness companion.
    """
```

Single SQL (one round-trip; portable across portfolios):

```sql
WITH latest_close AS (
  SELECT DISTINCT ON (asset_id) asset_id, ts AS price_ts, close
  FROM price_bar WHERE timeframe = '1d'
  ORDER BY asset_id, ts DESC
)
SELECT pp.id          AS portfolio_id,
       pp.name,
       pp.starting_cash::numeric,
       pp.cash::numeric                                                AS cash,
       COALESCE(SUM(pos.quantity * lc.close), 0)::numeric              AS live_positions_value,
       COALESCE(SUM(pos.quantity * (lc.close - pos.avg_cost)), 0)::numeric AS live_unrealized_pnl,
       MAX(lc.price_ts)                                                AS price_as_of
FROM paper_portfolio pp
LEFT JOIN paper_position pos ON pos.portfolio_id = pp.id AND pos.is_open = TRUE
LEFT JOIN latest_close lc    ON lc.asset_id = pos.asset_id
WHERE pp.is_active = TRUE
GROUP BY pp.id, pp.name, pp.starting_cash, pp.cash;
```

Returns:

```jsonc
{
  "live_total_equity": 115812.32,
  "live_cash": 2139.10,
  "live_positions_value": 113673.22,
  "live_unrealized_pnl": -1426.81,
  "price_as_of": "2026-05-18T00:00:00Z",   // freshest price_bar.ts used
  "computed_at": "2026-05-19T18:00:00Z",
  "portfolios": [ /* per-portfolio breakdown */ ],
  "snapshot_anchor": { "as_of_date": "2026-05-17", "total_equity": 115812.32 }  // from existing /paper/summary path
}
```

### Frontend wiring

`apps/web/src/lib/portfolio/api.ts:135` already builds `CommandBarData` from `/paper/summary`. Add a parallel `fetchLiveNav()` and extend `PortfolioSnapshot.tsx:35` to `Promise.all([fetchCommandBar(), fetchEquityCurve(), fetchLiveNav()])`. Render `liveNav` as the primary headline; demote the snapshot to a secondary "Official close: 2026-05-17 · $115,812.32" line.

**Do not** modify `fetchCommandBar`, `_latest_active_snapshots`, or any equity-curve reader. The snapshot table's role as immutable EOD anchor is preserved.

---

## 10. Reconciliation equation

```
live_cash             = paper_portfolio.cash                          (mutated on every fill)
live_holdings_value   = Σ_open(qty × latest_close)                    (latest_close from price_bar 1d)
live_estimated_nav    = live_cash + live_holdings_value
live_unrealized_pnl   = Σ_open(qty × (latest_close − avg_cost))
realized_pnl_cum      = Σ(paper_trade.realized_pnl)                   (unchanged from current path)

Identity (must hold):
  live_estimated_nav − Σ(paper_portfolio.starting_cash) ≡
  live_unrealized_pnl + realized_pnl_cum
```

On the EOD snapshot anchor (post-`run_paper_trading`):
```
paper_equity_snapshot[source='live', latest].total_equity ≡ live_estimated_nav
  evaluated at the moment the cron fired
```

Once the next trading day's 1d close lands, `live_estimated_nav` will drift from the latest snapshot — that drift IS the value of this endpoint.

---

## 11. UI label recommendation

Two distinct labels (Phase 15h freshness vocabulary):

| Surface | Label | Source |
|---|---|---|
| Hero NAV (primary) | **Live estimate · prices as of Mon 18 May** | `/paper/live-nav` |
| Secondary line | **Official close · Sat 17 May $115,812.32** | `/paper/summary` (unchanged) |

Freshness pill on the live line uses `price_as_of` (not `computed_at`) — the meaningful staleness is the price feed, not the request handler. With current 1d-only data, the pill will show "degraded" or "stale" outside of the ~16h window after each daily ingest. That's honest; the system genuinely has no fresher prices.

Phase 15h.4 pending-window logic (`freshness.ts:178+`) remains relevant: between 22:00 ET (ingest) and 23:30 ET (paper run), the live endpoint already reflects today's close while the snapshot still shows yesterday's. The UI copy should acknowledge this gap rather than hide it.

---

## 12. Risks of using daily (not 15-min) prices

The original brief assumed "15-min delayed". Reality is worse — **EOD only**:

1. **No intraday repricing**: a 5% mid-session move on a position is invisible until tomorrow's close ingests.
2. **Halted symbols**: a halt freezes the bar at the prior close; live endpoint reports stale price as if it were current.
3. **Dividend ex-dates**: `corporate_action` table exists (models.py:113) but `compute_equity_breakdown` does NOT apply ex-date adjustments. A position that went ex-div between snapshot and now will misreport unrealized P&L by the dividend amount.
4. **Splits**: same as dividends — `corporate_action.action_type='split'` rows exist but the live MTM math does not adjust historical `avg_cost` against splits. Mostly cosmetic if ingest_prices_daily uses adjusted_close (it stores both `close` and `adjusted_close`).
5. **Thinly-traded / delisted symbols**: `JOIN LATERAL ... LIMIT 1` returns the last bar regardless of age. A symbol last priced 30 days ago will appear "live" at the stale close.
6. **Provider divergence**: tiingo and yahoo rows coexist in `price_bar` (unique on `provider`); the `LATEST DISTINCT ON (asset_id) ORDER BY ts DESC` picks whichever provider wrote most recently, which is non-deterministic across symbols. Recommend filtering to a single provider preference in the SQL.
7. **Pre-market / after-hours fills**: `paper_execution` writes `fill_ts` and mutates `cash` immediately. If a paper fill clears at 04:00 ET, `live_cash` shows the new cash but `live_positions_value` still uses yesterday's close — the unrealized line will be off by today's open-vs-yesterday-close gap until the next ingest.

Mitigation: surface `price_as_of` prominently and gate "live" tone on it being within the same trading session.

---

## 13. Classification

**Feature add.** Live MTM is fully implemented in `compute_equity_breakdown` and exposed per-portfolio (paper.py:65), but the dashboard's aggregated `/paper/summary` endpoint was deliberately wired to read from `paper_equity_snapshot` (per its M079 truth-contract: snapshots are the user-facing canonical source). The proposal adds a *parallel* endpoint, leaving the M079 contract intact.

If treated as a bug, the fix would be to change `_latest_active_snapshots` to compute live — that would violate the documented M083 canonical semantic ("user-facing readers MUST filter source='live'" in `paper_equity_snapshot`). **Do not do that.** Add the new endpoint instead.

---

## Cited files

- `apps/api/src/db/models.py:55-106` (Asset, PriceBar)
- `apps/api/src/db/models.py:401-530` (PaperPortfolio, PaperPosition, PaperEquitySnapshot)
- `apps/api/src/api/operator.py:51-69, 80-90, 93-249` (paper/summary)
- `apps/api/src/api/paper.py:65, 90, 164, 187` (per-portfolio endpoints w/ live breakdown)
- `apps/api/src/domain/paper_trading/paper_service.py:120-165, 173-214` (compute_equity_breakdown, snapshot_equity_now)
- `apps/api/src/domain/paper_trading/paper_execution.py:312, 345` (cash mutation on fill)
- `apps/api/src/domain/prices/service.py:243` (timeframe='1d' upsert)
- `apps/worker/src/jobs/ingest_prices_daily.py:27-54`
- `apps/worker/src/jobs/run_paper_trading.py:220` (snapshot writer)
- `apps/web/src/components/portfolio/PortfolioSnapshot.tsx:35-87`
- `apps/web/src/lib/portfolio/api.ts:135-220`
- `apps/web/src/lib/picks/freshness.ts:36-44, 172-174`
- `infra/docker/worker.crontab` (single supercronic entry)
- DB `job_schedule` rows (queried 2026-05-19): no intraday price job exists.
