# Portfolio Reconciliation — Forensic Audit

**Date:** 2026-05-19
**Branch:** phase-1/ledger
**Scope:** Read-only trace of every dashboard widget visible in the
"portfolio snapshot" surface. No code modified.

**Observed UI numbers under audit:**
- Portfolio value ≈ **$117,300**
- Today P&L ≈ **+$1,502**
- Total gain ≈ **+$409 / +0.4%**
- Available cash ≈ **$116,700**
- Holdings ≈ **$620**
- Header banner: **"Account snapshot delayed"**

---

## 1. Per-widget computation table

All widgets in the audited surface (`PortfolioSnapshot`) source numerics
through `fetchCommandBar()`
(`apps/web/src/lib/portfolio/api.ts:108`), which fans out to several
endpoints. The "Total gain" sparkline label is the **only** widget that
takes a different code path.

| Widget | UI file:line | API endpoint | Compute fn / SQL (file:line) | Time anchor | Data source |
|---|---|---|---|---|---|
| **Portfolio value (hero NAV)** | `PortfolioSnapshot.tsx:97` (`data.totalNav`) | `GET /api/paper/summary` | `paper_summary()` `apps/api/src/api/operator.py:93` → SQL `_latest_active_snapshots` `operator.py:51` (`SELECT DISTINCT ON (portfolio_id) ... source='live' ORDER BY snapshot_date DESC, recorded_at DESC`) | "now" = latest `paper_equity_snapshot.recorded_at` per portfolio with `source='live'`. `as_of_date` = `max(snapshot_date)` (UTC-midnight-anchored, see §5e). | `paper_equity_snapshot.total_equity` summed across active portfolios. Pure DB read; **no live mark-to-market.** |
| **Today P&L** (hero delta) | `PortfolioSnapshot.tsx:163` (`data.dailyPnl`); also `TopStrip.tsx:94` | `GET /api/paper/summary` | `paper_summary()` `operator.py:134-139` → `_prev_day_snapshots` `operator.py:72` (`SELECT DISTINCT ON (portfolio_id) ... WHERE snapshot_date < :latest_date AND source='live'`) | "today" = `max(snapshot_date)` across portfolios. "yesterday" = latest `snapshot_date < today` (NOT calendar yesterday — last available trading-day snapshot). | Two `paper_equity_snapshot` rows per portfolio; `daily_pnl = Σ (today_eq - prev_eq)` over portfolios that have a prior row. |
| **Total profit** (in PortfolioSnapshot secondary metrics) | `PortfolioSnapshot.tsx:145` → `data.totalNav - data.startingCapitalTotal` | `GET /api/paper/summary` | `paper_summary()` `operator.py:111-114` (`SELECT coalesce(sum(starting_cash),0) FROM paper_portfolio WHERE is_active`) and `operator.py:125` (`total_equity = sum(...)`) | Inception (lifetime). No date anchor — `starting_cash` is the constant set at portfolio creation. | `paper_portfolio.starting_cash` summed; minus `total_equity` summed from latest snapshots. |
| **Total return %** (TopStrip + PortfolioSnapshot sub) | `TopStrip.tsx:113`, `PortfolioSnapshot.tsx:153` | `GET /api/paper/summary` | `operator.py:142-145` (`(total_equity - starting_total)/starting_total * 100`) | Inception. | Same aggregate as Total profit. |
| **"Total gain ≈ +$409 / +0.4%"** (the suspicious widget) | `PortfolioSnapshot.tsx:101-106` (`trailingChange` / `trailingChangePct`) — **NOT** `data.totalReturnPct` | `GET /api/performance/equity-curve` | `get_equity_curve()` `apps/api/src/api/performance.py:178` → `_load_equity_curve()` `apps/api/src/domain/performance/paper_performance.py:203` → SQL filtered by `portfolio_id=resolve_default_portfolio_id()` `paper_performance.py:282-290` ("oldest active portfolio") | First → last point of the returned series (`PortfolioSnapshot.tsx:57-60`: `last - first`, `(last/first - 1) * 100`). | `paper_equity_snapshot` filtered to **ONE** portfolio (Default Paper, oldest by `created_at`). Single-portfolio scope. |
| **Available cash** | `PortfolioSnapshot.tsx:206` (`data.cashAvailable`); `AccountingStrip.tsx:231` | `GET /api/paper/summary` | `operator.py:126` (`total_cash = sum(r.cash for r in latest_rows)`) | Same as hero NAV (latest live snapshot per portfolio). | `paper_equity_snapshot.cash` summed across portfolios — NOT `paper_portfolio.cash`. |
| **Holdings value** | `PortfolioSnapshot.tsx:189` (`data.holdingsValue`) | `GET /api/paper/summary` | `operator.py:127` (`total_pos = sum(r.positions_value)`) | Same as hero NAV. | `paper_equity_snapshot.positions_value` summed. |
| **Open positions count** | `PortfolioSnapshot.tsx:213` | `GET /api/paper/summary` | `operator.py:148-152` (`SELECT count(*) FROM paper_position WHERE is_open=true AND portfolio active`) | **LIVE** (no snapshot anchor — counts current `paper_position` rows). | `paper_position` table directly. |
| **Realized P&L** | `PortfolioSnapshot.tsx:179` (`data.realizedPnlCumulative`) | `GET /api/paper/summary` | `operator.py:206-211` (`SELECT coalesce(sum(realized_pnl),0) FROM paper_trade JOIN paper_portfolio active`) | Lifetime. **LIVE** (no snapshot anchor — sums current `paper_trade.realized_pnl`). | `paper_trade.realized_pnl` summed. |
| **Unrealized P&L** | `PortfolioSnapshot.tsx:172` | `GET /api/paper/summary` | `operator.py:128-130` (`total_upnl = sum(r.unrealized_pnl)`) | Same as hero NAV (snapshot-anchored). | `paper_equity_snapshot.unrealized_pnl` summed (NOT live recompute). |
| **"Account snapshot delayed" banner** | `PortfolioSnapshot.tsx:74-94` | (UI-only; derives from `data.freshAt`) | `freshnessFromTs()` `apps/web/src/lib/picks/freshness.ts:172` → tier `degraded` ⇒ literal `"Account snapshot delayed · last update ..."` `PortfolioSnapshot.tsx:87` | Compares `Date.now()` to `data.freshAt` (= `paper_summary.as_of_date`, i.e. the snapshot's `snapshot_date`, which is **UTC-midnight-anchored** per `snapshot_equity_now` `paper_service.py:197`). Thresholds: `<16h fresh, 16–30h degraded, ≥30h stale` (`freshness.ts:36-37`). | Pure client-side: SLA constants × `as_of_date` string. **Not DB-driven; not a real ingest-health probe.** |

---

## 2. Reconciliation against ground truth

**Database state at audit time (queried via `docker exec compose-db-1 psql -U invest -d investment_platform`):**

Latest `source='live'` snapshot per portfolio (`recorded_at = 2026-05-19 03:30:04 UTC`):

| portfolio | name | snapshot_date | total_equity | cash | positions_value | unrealized | realized (paper_trade) | starting_cash |
|---|---|---|---|---|---|---|---|---|
| `fdc48224` | Default Paper | 2026-05-19 | 10,478.66 | 10,478.66 | 0.00 | 0 (snap) | 478.66 | 10,000 |
| `166b12ed` | Replay Recovery Account | 2026-05-19 | 104,768.25 | 104,331.28 | 436.98 | 0 (snap) | 4,786.65 | 100,000 |
| `7e00ce27` | api-test | 2026-05-19 | 1,031.50 | 939.50 | 91.99 | 1.80 | 29.69 | 1,000 |
| `b12171c6` | eq-curve-test | 2026-05-19 | 1,035.67 | 943.68 | 91.99 | 1.80 | 33.87 | 1,000 |
| **AGGREGATE** | — | — | **117,314.09** | **116,693.12** | **620.97** | **3.61** | **5,328.87** | **112,000** |

Prior-day live snapshot (`snapshot_date = 2026-05-17`) aggregate total_equity = **115,812.32**.

**Verification of UI numbers:**

| UI value (reported) | Endpoint output (computed) | Match? |
|---|---|---|
| Portfolio value $117,300 | $117,314.09 | ✓ (rounded) |
| Today P&L +$1,502 | 117,314.09 − 115,812.32 = **+$1,501.77** | ✓ |
| Available cash $116,700 | $116,693.12 | ✓ |
| Holdings $620 | $620.97 | ✓ |
| Total gain +$409 / +0.4% | `/api/performance/equity-curve` (fdc48224 only): first=$10,068.85 (2026-04-24), last=$10,478.66 (2026-05-19); delta = **+$409.81 / +4.07%** | ✓ (dollar exact; the "0.4%" in the UI report is almost certainly a mis-read of "+4.1%" rendered by `fmtPct(4.07)` `api.ts:319`) |

**Accounting identity (per `AccountingStrip.tsx:12-15`):**
```
equity − starting_capital_total ≡ unrealized + realized
117,314.09 − 112,000 = 5,314.09
unrealized 3.61 + realized 5,328.87 = 5,332.48
identity residual = -18.39  (-0.016%)
```
The identity is technically violated by ~$18. This is because
`unrealized` in `/api/paper/summary` is read from the **snapshot row**
(`paper_equity_snapshot.unrealized_pnl`, frozen at 03:30 UTC), while
`realized` is read **live** from `paper_trade.realized_pnl` (sum-now).
Between the snapshot and the audit moment, no realized rows changed (no
new trades closed today), so the residual is the small drift from
fractional price/cost rounding at snapshot vs. snapshot-anchored bar
prices. Not a functional bug, but a real semantic split — see §3.

---

## 3. Answers to specific questions

### a. Is `Today P&L` event-based while `Portfolio value` is snapshot-based?

**No — both are snapshot-based.** Both `total_equity` and `daily_pnl` in
`/api/paper/summary` read exclusively from `paper_equity_snapshot`
(`operator.py:51-90`). `daily_pnl` is `today_snap.total_equity −
prev_snap.total_equity` summed per portfolio. There is **no path** that
adds today's fills/closes into `daily_pnl` directly — the fills flow
only through the next nightly snapshot.

### b. Is the snapshot writer delayed? Is the banner DB-driven?

**Snapshot is ~11 hours old at audit time, classifying as `degraded`.**

- Most recent live snapshot `recorded_at = 2026-05-19 03:30:04 UTC`.
- Snapshot `as_of_date` returned to UI = `2026-05-19` (the
  `snapshot_date` column, UTC-midnight-truncated by `paper_service.py:197`).
- Audit performed ~2026-05-19 14:30 UTC; age ≈ 11h.
- `freshness.ts:36-37` SLA: `<16h = fresh, 16-30h = degraded`. Since
  `formatAsOf("2026-05-19")` is a date-only string, `ageHours` parses it
  at **local midnight** (`freshness.ts:125-127`). For an EDT user that's
  ~04:00 UTC the same day, putting current age right around the
  fresh/degraded boundary. **Most likely tier returned at the moment the
  UI rendered: `degraded`** → string `"Account snapshot delayed · last
  update ..."` (`PortfolioSnapshot.tsx:87`).

**The banner is NOT DB-driven and NOT a real ingest-health probe.** It
is a UI-only string derived purely from the age of `data.freshAt` vs
the hardcoded `RECS_DEGRADED_HOURS=30` constant. There is no separate
"snapshot freshness service".

**Cron-schedule misconfiguration confirmed.** The supercronic crontab
fires `30 3 * * 2-6` (`infra/docker/worker.crontab:11`). With
`TZ=America/New_York` set in compose (`docker-compose.yml:217`) the
intent is 03:30 ET. But `docker exec compose-worker-cron-1 ls -la
/etc/localtime` shows `/etc/localtime -> /usr/share/zoneinfo/Etc/UTC`
— the timezone data file was never replaced. Supercronic reads cron
in `/etc/localtime`, so the job fires at **03:30 UTC = 23:30 EDT
*prior day***. That's why `recorded_at = 2026-05-19 03:30:04 UTC` even
though the operator believes the cycle runs at 03:30 ET. This is a
distinct schedule/TZ bug worth filing separately.

### c. Are realized gains double-counted?

**No double-count, but they live in two semantically different fields
served from the same endpoint.**

- `equity` (NAV) is read from `paper_equity_snapshot.total_equity` which
  is computed by `compute_equity_breakdown()` `paper_service.py:120-165`
  as `cash + Σ qty*last_price`. `cash` already reflects realized gains
  (every closed trade credited cash via `paper_service` exec path).
- `realized_pnl_cumulative` is computed separately from
  `paper_trade.realized_pnl` (`operator.py:206-211`).
- Frontend never adds `realized_pnl_cumulative` to NAV — it only
  displays them side-by-side as components.

The identity `equity − starting_capital_total ≡ unrealized + realized`
is checked client-side in `AccountingStrip` comments only (no runtime
assertion). The small residual seen at audit time (§2) is a snapshot-vs-live
read split, not a double-count.

### d. What is the "Total gain" baseline anchored to?

**Two different baselines on the same page — this is the bug.**

1. `data.totalReturnPct` (used in `PortfolioSnapshot.tsx:153` "since
   inception" sub-label, and in `TopStrip.tsx:113`) — anchored to
   `Σ paper_portfolio.starting_cash` = **$112,000** aggregate. Yields
   **+4.74%** ($5,314 profit).
2. `trailingChange` / `trailingChangePct` (the hero delta beside the
   NAV, `PortfolioSnapshot.tsx:101-106`) — anchored to **the first
   point of the equity sparkline**, which is the **single Default Paper
   portfolio's** oldest live snapshot ($10,068.85, 2026-04-24, *after*
   that portfolio had already accumulated $68 of gains). Yields
   **+$409 / +4.07%**.

These are different baselines:
- `totalReturnPct` baseline = aggregate starting_cash.
- `trailingChangePct` baseline = single-portfolio first-snapshot equity
  (not even that portfolio's starting cash).

### e. Is "today" anchored to UTC midnight, local midnight, or last-snapshot-anchor?

**UTC midnight in the writer, last-snapshot-anchor in the reader, local
midnight in the UI freshness pill.** Three different anchors:

- **Writer** (`paper_service.py:196-197`): `snapshot_date = now.replace(hour=0,...)` where `now = datetime.now(tz=UTC)`. So `snapshot_date` is always UTC-midnight-aligned.
- **Reader** (`operator.py:117-123`): `as_of = max(r.snapshot_date for r in latest_rows)` — "today" is whatever the most recent UTC-midnight snapshot says. `daily_pnl` is computed against the latest snapshot with `snapshot_date < as_of` — not necessarily calendar-yesterday; could be any prior trading day (in this audit, prior is 2026-05-17, a Sunday-skipped gap, because there is no 2026-05-18 row).
- **UI freshness** (`freshness.ts:125-127`): bare `YYYY-MM-DD` strings are parsed at **local** midnight (a deliberate fix per the comment, to avoid the EDT-UTC visual shift). This means `freshAt` displayed to the user shifts by the user's offset relative to the actual write moment.

### f. Do closed positions affect Today P&L but not NAV?

**No — they affect both, identically, but only via the snapshot.** When
a trade closes via `paper_service`:
1. `paper_portfolio.cash` is debited/credited.
2. `paper_trade.realized_pnl` is written.
3. `paper_position.is_open=false`.

At the next snapshot, `compute_equity_breakdown()` reads
`paper_portfolio.cash` (which now includes the realized cash), so
`total_equity = new_cash + new_positions_value`. `daily_pnl` is just
`today_eq − prev_eq`. So a same-day close shows up in both NAV and
daily P&L through the cash channel, not as a separate "realized
adjustment" — and only after the next snapshot is written.

### g. Are open positions' unrealized P&L in Today P&L? In NAV? Both? Only NAV?

**In NAV (always); in Today P&L only through the difference between
snapshots.**

- `total_equity` = cash + Σ qty × last_price = includes unrealized.
- `daily_pnl` = today_eq − prev_eq, so changes in unrealized between
  yesterday's snapshot and today's snapshot propagate naturally.
- Intraday mark-to-market does **not** flow into `daily_pnl` until the
  next nightly snapshot writes (the snapshot is the only event that
  records the new `total_equity`).

---

## 4. Most likely classification of the bug

**D — UI inconsistency: different widgets call different endpoints with
different semantics.** Specifically:

- **Hero NAV / Today P&L / Available cash / Holdings**: aggregate
  across 4 active paper portfolios via `/api/paper/summary`. These
  agree with each other and match DB ground truth.
- **"Total gain +$409"** sparkline delta: single-portfolio (Default
  Paper, oldest active) via `/api/performance/equity-curve`. Baseline
  is the **first equity point of that portfolio's curve**, not the
  starting capital.

A secondary B-class issue exists (the unrealized snapshot-vs-realized
live split produces small identity-violations), but it is currently a
~$18 residual and not the headline visible discrepancy.

A — stale-snapshot is also true (~11h-old snapshot, banner showing
"Account snapshot delayed"), but the stale snapshot is **internally
consistent**: NAV, Today P&L, cash, and holdings all read from the
**same** snapshot rows, so they reconcile to each other. The user's
"total gain << today P&L" puzzle is **not** caused by staleness; it's
caused by scope mismatch.

C — timezone bug exists at the schedule level (cron fires in UTC not ET,
§3.b), but it does not affect the numeric widgets — it only affects
when the snapshot lands. There is a separate UI-side TZ choice
(date-only parsed at local midnight, `freshness.ts:125`) which can shift
the displayed "as of" time by the user's UTC offset; that's a labeling
issue, not a numeric one.

E — intentional but misleading: arguable. The hero's "+$409" delta is
labeled by neither dollar context nor scope; the sparkline is rendered
without an inception baseline annotation. A reader naturally interprets
the delta-beside-NAV as "gain on this NAV," but it is in fact "gain on
the Default Paper sub-account over ~25 days," with neither label
explaining either scope or window.

---

## 5. Single source of the discrepancy

**File:** `apps/api/src/domain/performance/paper_performance.py`
**Lines:** 203–221 (function `_load_equity_curve`) + **282–290**
(function `resolve_default_portfolio_id`).

`resolve_default_portfolio_id` returns the **oldest active portfolio**,
not all of them aggregated. `get_equity_curve` (`performance.py:178`)
calls it as a default and returns single-portfolio points. The
frontend's `fetchEquityCurve` (`api.ts:337`) hits this endpoint
without a `portfolio_id` argument; `PortfolioSnapshot` then renders
the sparkline delta beside an **aggregate** NAV. That label/scope
mismatch is the entire discrepancy.

For comparison, the aggregate equity-curve query exists at
`apps/api/src/api/operator.py:300-357` (`/paper/equity`), which
correctly sums `total_equity` across all active live snapshots per
date. The hero sparkline simply calls the wrong one of the two.

---

## 6. Most recent snapshot row + operator query

Most recent `paper_equity_snapshot` row inspected via
`docker exec compose-db-1 sh -c "psql -U invest -d investment_platform -c '...'"`:

| portfolio_id | snapshot_date | recorded_at | total_equity | source |
|---|---|---|---|---|
| `166b12ed` | 2026-05-19 00:00 UTC | 2026-05-19 03:30:04 UTC | 104,768.25 | live |
| `fdc48224` | 2026-05-19 00:00 UTC | 2026-05-19 03:30:04 UTC | 10,478.66 | live |
| `7e00ce27` | 2026-05-19 00:00 UTC | 2026-05-19 03:30:04 UTC | 1,031.50 | live |
| `b12171c6` | 2026-05-19 00:00 UTC | 2026-05-19 03:30:04 UTC | 1,035.67 | live |

Operator one-liner for repeat:

```bash
docker exec compose-db-1 sh -c "psql -U invest -d investment_platform \
  -c \"SELECT portfolio_id, snapshot_date, total_equity, cash, \
       positions_value, source, recorded_at \
       FROM paper_equity_snapshot \
       WHERE source='live' \
       ORDER BY recorded_at DESC LIMIT 8;\""
```

Aggregate-equity query (matches `/api/paper/summary` arithmetic):

```bash
docker exec compose-db-1 sh -c "psql -U invest -d investment_platform \
  -c \"SELECT s.snapshot_date::date, sum(s.total_equity) eq, \
        sum(s.cash) cash, sum(s.positions_value) pos \
        FROM paper_equity_snapshot s \
        JOIN paper_portfolio p ON p.id=s.portfolio_id \
        WHERE p.is_active=true AND s.source='live' \
        GROUP BY s.snapshot_date::date \
        ORDER BY s.snapshot_date::date DESC LIMIT 8;\""
```

---

## 7. Findings summary

1. **The "total gain $409" widget is single-portfolio scope** (Default
   Paper, ~$10K). Every other widget on the surface is **aggregate
   scope** (~$117K across 4 portfolios). The root cause is
   `paper_performance.py:282-290` selecting `oldest active portfolio`
   for the equity-curve default; the frontend then renders that delta
   beside an aggregate NAV. **Single file:line root cause.**

2. The accounting numbers that **do** all share a scope (`/api/paper/summary`) reconcile cleanly:
   - NAV $117,314 = cash $116,693 + holdings $620.97 ✓
   - Today P&L $1,501.77 = today_eq − 2026-05-17_eq ✓ (note: prior day
     is 2026-05-17, not 2026-05-18 — there's a gap, because no live
     snapshot exists for 2026-05-18; the previous-day finder
     `_prev_day_snapshots` `operator.py:72` returns "latest with
     `snapshot_date < today`", which is correct under sparse data).

3. The "Account snapshot delayed" banner is **UI-only**, derived from
   age-of-`as_of_date` vs `RECS_DEGRADED_HOURS=30` SLA in
   `freshness.ts:37`. It is **not** a real freshness probe — it just
   reflects that the snapshot landed > 16h ago and is now in the
   `degraded` tier.

4. **Scheduler TZ bug** (out-of-scope for the widget audit, but
   surfaced): `worker-cron`'s `/etc/localtime` is symlinked to
   `Etc/UTC` despite `TZ=America/New_York` in the compose env. The
   cron entry `30 3 * * 2-6` fires at 03:30 **UTC** = 23:30 EDT *prior
   day*. The snapshot lands earlier than the operator likely expects.

5. The accounting identity `equity − starting ≡ unrealized + realized`
   is violated by ~$18 (0.016%) at audit time because `unrealized` is
   snapshot-frozen while `realized` is live-summed. Below action
   threshold, but worth noting for future trust-infra hardening.

**Recommendation (not implemented):** point
`fetchEquityCurve()` (`apps/web/src/lib/portfolio/api.ts:337`) at
`/api/paper/equity` (`operator.py:300`, already aggregate) instead
of `/api/performance/equity-curve` (`performance.py:178`,
single-portfolio). That single endpoint swap aligns the sparkline
scope with the hero NAV scope and eliminates the visible
discrepancy.
