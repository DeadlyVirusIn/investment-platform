# Market Quote Provider — Architecture Recommendation

> **Phase 15h.5 (architecture-only).** Replaces the synthetic random-walk
> stub at `apps/web/src/lib/market/hooks.ts`. NOT yet implemented; this
> is the recommendation to be approved before any code lands.

---

## Use case

Local-first paper-trading research platform. Need delayed (5–15 min)
intraday quotes for ~50 symbols (5–6 macro indices + ~45 equity
holdings) to drive a Cloudflare-Access-gated "Market Tape" UI on
iPhone. REST polling on a cadence; backend caches to Postgres or
Redis. Solo developer; ceiling $50/mo, target <$30/mo.

The existing daily EOD ingest (yahoo + tiingo into `price_bar`) is
**not** disturbed by this work — that pipeline runs once/day at 22:00
ET and serves the recommendations engine. The intraday tape is a
separate, lower-stakes UI concern.

---

## 1. Provider evaluation

| Provider              | Entry tier            | $/mo  | Indices (VIX/TNX)                      | Rate limit       | WS  | Ergonomics |
|-----------------------|-----------------------|-------|----------------------------------------|------------------|-----|------------|
| Polygon Stocks Starter| 15-min delayed stocks | $29   | ETFs yes; **VIX needs Indices add-on**, TNX unverified | unlimited | yes | clean      |
| Polygon + Indices     | as above + indices    | ~$58 (est., unverified) | VIX yes, TNX unverified                | unlimited | yes | clean      |
| Tiingo Power          | IEX real-time         | $30   | **No SPX/VIX/TNX**; ETFs only          | ~500/min         | yes | clean      |
| FMP Starter           | real-time US          | $22 (annual) / ~$29 mo | partial; VIX unverified, TNX via Treasury endpoint | 300/min | no (Starter) | messy |
| Alpaca Free           | IEX delayed/RT        | $0    | **No indices**, ETFs only              | 200/min          | yes | clean      |
| yfinance              | scraped               | $0    | VIX/TNX yes (`^VIX`/`^TNX`)            | unreliable, 429-prone | no | fragile  |

(Pricing pages 2026; sources at end of this doc. Items marked
*unverified* require a one-hour validation spike before commitment.)

### Per-provider gotchas

- **Polygon Stocks Starter** ($29/mo): unlimited calls, clean docs,
  WebSocket included. Indices are a **separate subscription** — VIX
  requires the Indices add-on. Realistic landed cost ~$58/mo. Over
  the $30 target.
- **Tiingo Power** ($30/mo): IEX-limited (~2% of US tape volume),
  no true index coverage (no SPX/VIX/TNX). ETF wrappers (SPY/QQQ/DIA)
  work. Already in our EOD pipeline so the credential + code path
  exist, but coverage gap forces a second source.
- **FMP Starter** (~$22 annual / $29 monthly): real-time US equities,
  Index endpoint covers S&P/Dow/Nasdaq, separate Treasury endpoint
  covers TNX. **VIX coverage on Starter is unverified.** No WebSocket
  on Starter. Documentation is messier than Polygon. 300 req/min cap.
- **Alpaca Free**: IEX-only, no indices. Tempting for $0 but does not
  cover the macro tape, defeating the surface's purpose.
- **yfinance**: covers `^VIX`/`^TNX` natively but is unreliable as a
  primary polling source — Yahoo 429s aggressively in 2026. Acceptable
  as a thin **fallback for 1–2 symbols**, not as primary.

---

## 2. Recommendation + estimated monthly cost

### Empirical update (2026-05-12 probe with operator's free Polygon key)

The operator already holds a Polygon free-tier key. Probed against
production endpoints:

| Endpoint                                    | Free-tier result        |
|---------------------------------------------|-------------------------|
| `/v2/snapshot/.../tickers/AAPL` (equity)    | 403 NOT_AUTHORIZED      |
| `/v2/snapshot/.../tickers/SPY` (ETF)        | 403 NOT_AUTHORIZED      |
| `/v3/snapshot/indices?ticker=I:VIX`         | 403 NOT_AUTHORIZED      |
| `/v3/snapshot/indices?ticker=I:TNX`         | 403 NOT_AUTHORIZED      |
| `/v2/aggs/ticker/AAPL/prev` (EOD bar)       | OK — returned `c: 292.68` |

**Conclusion:** Polygon free tier in 2026 paywalls the snapshot
endpoint entirely. Error redirects to `massive.com/pricing` (Polygon
rebranded as Massive). The free key only serves historical aggregates
— functionally equivalent to the existing yahoo+tiingo EOD ingest.
**Free Polygon key does NOT advance the live-tape goal.**

This eliminates the "use what you already have for free" path. The
choice is now: pay for a Starter tier on some provider, or ship the
honest disabled-tape state.

### Recommendation

**Primary: Financial Modeling Prep Starter — $22/mo (billed annually,
$264/yr) or ~$29/mo (billed monthly).**

**Fallback for VIX/TNX only (if FMP coverage incomplete on probe):
yfinance via the existing daily ingest's Python environment**, polled
at 60s (only 2 symbols, well below Yahoo's rate-limit threshold).

Total realistic ceiling: **$22–29/mo.** Under the $30 target.

Rationale: only single-tier provider under $30 that delivers
(a) real-time US equity quotes for the ~45 holdings,
(b) at least partial index quotes including S&P/Dow/Nasdaq, and
(c) Treasury yields (TNX) — all on one bill.

**Backup choice if FMP probe fails (2–3 of VIX, TNX, batch-latency
<2s come back broken):** Polygon Stocks Starter ($29) + yfinance for
VIX/TNX only — total $29/mo.

---

## 3. Backend integration architecture

```
                        ┌─────────────────────────────────────┐
                        │  apps/api  (FastAPI, compose-api-1) │
                        └─────────────────────────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        │                              │                              │
        ▼                              ▼                              ▼
┌──────────────┐            ┌──────────────────┐             ┌──────────────┐
│ Web client   │            │ /api/market/     │             │ Cron-driven  │
│ (Vite, /tape)│ ◀────────▶ │   quotes         │ ◀──reads──▶ │ poller task  │
│ React Query  │            │ (read from cache)│             │ (in-process) │
└──────────────┘            └──────────────────┘             └──────────────┘
                                       ▲                              │
                                       │                              │
                                       │ writes                        │ HTTPS
                                       │                              ▼
                              ┌──────────────────┐         ┌──────────────────┐
                              │  Postgres table  │         │  FMP REST API    │
                              │  market_quote    │         │  + yfinance fb   │
                              └──────────────────┘         └──────────────────┘
```

### Components

1. **`market_quote` Postgres table** (single source of truth for the
   cache). Holds latest snapshot per symbol. ~50 rows steady-state.
   Survives container restarts. UPSERT on each poll.
2. **In-process poller** running inside the existing API container
   (no new container). Triggered by a lightweight async task launched
   at app startup (`fastapi lifespan`). Polls FMP every N seconds for
   the active symbol set, writes to `market_quote`. Falls back to
   yfinance for VIX/TNX if FMP returns null/error for those symbols.
3. **`/api/market/quotes?symbols=SPY,QQQ,VIX,TNX,...` endpoint.**
   Reads only from the `market_quote` table. Never calls upstream
   from the request path. p95 latency <50ms.
4. **Web client** uses TanStack Query against `/api/market/quotes`.
   Stale-while-revalidate, refetch every 30s.

### Why in-process poller, not a new container

- The existing `compose-worker-tickloop-1` and `compose-worker-cron-1`
  containers exist for the recommendations pipeline, which has
  long-running scheduled jobs. The market-quote poller is a tiny
  task: 1 HTTP call every 60s, ~50 symbols. Adding a third worker
  container (and its supercronic / process supervision) is more infra
  than the workload justifies.
- `fastapi.lifespan` already runs at API startup and is the natural
  place for "start a background asyncio task." If the API container
  restarts, the poller restarts with it — same lifecycle.
- If the requirements grow (e.g. WebSocket consumer, multiple
  exchanges, separate scheduling cadences), promote to its own
  container later. **Premature is the wrong call here.**

---

## 4. Cache strategy

**Two-layer cache, both read-through:**

### Layer 1 — Postgres `market_quote` table

```
CREATE TABLE market_quote (
  symbol           VARCHAR(16)               NOT NULL PRIMARY KEY,
  price            NUMERIC(20, 6)            NOT NULL,
  prev_close       NUMERIC(20, 6),
  change_abs       NUMERIC(20, 6),
  change_pct       NUMERIC(10, 4),
  quote_ts         TIMESTAMPTZ               NOT NULL,
  fetched_at       TIMESTAMPTZ               NOT NULL DEFAULT now(),
  source           VARCHAR(16)               NOT NULL,  -- 'fmp' | 'yfinance'
  delay_minutes    SMALLINT                  NOT NULL,  -- 15 for FMP delayed, 0 for live
  symbol_type      VARCHAR(16)               NOT NULL   -- 'equity' | 'index' | 'etf' | 'rate'
);
CREATE INDEX ix_market_quote_fetched ON market_quote(fetched_at);
```

- Single row per symbol. UPSERT (`ON CONFLICT (symbol) DO UPDATE`).
- `quote_ts` is the source's last-trade timestamp (NOT the time we
  fetched). Lets the UI compute true delay.
- `fetched_at` is when our poller wrote the row. Lets the staleness
  guard fire if the poller hangs.
- `delay_minutes` is informational metadata for the UI's honest
  labeling.

### Layer 2 — In-process LRU (optional, deferred)

For the `/api/market/quotes` endpoint, an in-process dict keyed by
`symbols.sorted().join(",")` with a 5s TTL. Saves the Postgres round
trip when 10 clients call within the same second. **Defer until
measured contention.** YAGNI for one user.

### Cache invalidation

- Poller writes overwrite. No explicit invalidation needed.
- If the poller is down for >2 minutes (`now() - max(fetched_at) > 2m`),
  the API endpoint returns the stale rows but with a `stale: true`
  flag in the JSON. UI then renders the disabled-tape state (see §9).
- No TTL on rows. A row from yesterday for a delisted symbol is fine —
  caller can choose to ignore based on `quote_ts`.

---

## 5. Polling cadence

| Window                  | Cadence    | Reason                                       |
|-------------------------|------------|----------------------------------------------|
| Pre-market 04:00–09:30 ET | 60s     | Some users check before open. Light load.    |
| RTH 09:30–16:00 ET      | **15s**    | Active session. Tape needs to feel current.  |
| After-hours 16:00–20:00 ET | 60s     | Reduced flow.                                |
| Closed 20:00–04:00 ET   | 300s (5 min) | Symbols don't move. Maintain freshness for VIX/TNX which can update late. |
| Weekends + US holidays  | poller paused | No new data; UI shows "Market closed" tag. |

**Volume math (worst case, RTH):**
- 50 symbols, batched into FMP's bulk-quote endpoint = 1 HTTP call
  per cycle.
- 1 call / 15s = 4 calls/min.
- Daily RTH: 4 × 60 × 6.5 = **1,560 calls/day**.
- Pre/post: 60 + 240 + 60 = 360 calls/day.
- Off-hours: 12 × 7 = 84 calls/day.
- Total: **~2,000 calls/day**, well under any reasonable limit.

**FMP fallback to yfinance for VIX/TNX:** 2 separate `Ticker.info` calls
at 60s during RTH = 240 yfinance calls/day. Below the empirical
~950-pull/day Yahoo soft-ban threshold.

**US market calendar:** use `pandas_market_calendars` (already in
`pyproject.toml` if not, lightweight to add) for accurate holiday
detection. Do not hand-roll a holiday list.

---

## 6. Rate-limit analysis

### FMP Starter — 300 req/min

Worst-case usage: 4 req/min (15s RTH cycle, batched). **Headroom: 75×.**
Even if we expand to 200 symbols and drop the cycle to 5s, still
60 req/min vs the 300/min cap. Comfortable.

Bandwidth cap: 20 GB/mo per FMP Starter. A typical bulk-quote response
for 50 symbols is ~8 KB JSON. 2,000 calls/day × 30 days × 8 KB =
**~480 MB/mo**. **Headroom: 40×.**

### yfinance fallback — empirical ~950 pulls/day before soft-ban

Worst-case usage: 240 pulls/day (2 symbols × 120 cycles/day RTH at
60s). **Headroom: 4×.** Acceptable but watched. If Yahoo bans, the
2 symbols (VIX, TNX) drop to `null` in the cache and the UI labels
those slots "—" rather than render fake data.

### Failure modes + circuit-breaking

| Failure                                 | Detection                            | Response                                              |
|------------------------------------------|--------------------------------------|-------------------------------------------------------|
| FMP HTTP 5xx                             | response.status_code >= 500          | Exponential backoff (15s → 60s → 300s); cache stays   |
| FMP HTTP 429                             | response.status_code == 429          | Pause poller 5 min; log warning                       |
| FMP returns malformed/empty for symbol   | parse failure                        | Skip that symbol this cycle; keep prior row in cache  |
| yfinance 429                             | exception caught                     | Drop VIX/TNX to `null`; UI shows "—" with tooltip     |
| Both providers down >5 min               | `now() - max(fetched_at) > 5m`       | Endpoint returns `{ "stale": true, ... }`; UI hides tape (see §9) |
| Container restart                        | poller restarts with lifespan        | First poll happens within 15s of API ready            |

---

## 7. API schema proposal

### `GET /api/market/quotes`

Query params:
- `symbols` (required) — comma-separated, max 100
- (optional) `since` — ISO ts; only return quotes with `quote_ts > since`

Response (200):
```json
{
  "stale": false,
  "fetched_at": "2026-05-12T14:32:18Z",
  "max_delay_minutes": 15,
  "quotes": [
    {
      "symbol": "SPY",
      "price": 739.30,
      "prev_close": 737.62,
      "change_abs": 1.68,
      "change_pct": 0.228,
      "quote_ts": "2026-05-12T14:17:03Z",
      "delay_minutes": 15,
      "source": "fmp",
      "symbol_type": "etf"
    },
    {
      "symbol": "VIX",
      "price": 14.82,
      "prev_close": 14.97,
      "change_abs": -0.15,
      "change_pct": -1.002,
      "quote_ts": "2026-05-12T14:17:00Z",
      "delay_minutes": 15,
      "source": "yfinance",
      "symbol_type": "index"
    },
    {
      "symbol": "TNX",
      "price": null,
      "prev_close": 4.284,
      "change_abs": null,
      "change_pct": null,
      "quote_ts": null,
      "delay_minutes": null,
      "source": "yfinance",
      "symbol_type": "rate",
      "error": "upstream_unavailable"
    }
  ]
}
```

Response (when poller down >5 min):
```json
{
  "stale": true,
  "fetched_at": "2026-05-12T14:18:00Z",
  "max_delay_minutes": null,
  "quotes": [],
  "error": "market_quote_poller_offline"
}
```

### `GET /api/market/health`

```json
{
  "poller_status": "ok",       // "ok" | "degraded" | "offline"
  "last_successful_poll": "2026-05-12T14:32:18Z",
  "fmp_circuit": "closed",     // "closed" | "open" | "half_open"
  "yfinance_circuit": "closed",
  "symbols_tracked": 50,
  "symbols_with_recent_data": 49
}
```

Powers the existing Ops dashboard freshness panel; no new UI required.

---

## 8. Rollout plan

**Each step gated on the previous step passing.** No fake fallbacks
during migration.

### Step 0 — FMP probe (1h)

Sign up for FMP free tier (250 calls/day). Probe with curl:
- `?symbol=^VIX` — does it return a quote?
- `?symbol=AAPL,MSFT,NVDA,SPY,QQQ,DIA` — bulk shape?
- Treasury endpoint — is TNX accessible at intraday cadence or daily-only?
- Time 50-symbol batch latency.

**If VIX coverage fails:** switch primary to Polygon Stocks Starter
($29) + yfinance for VIX/TNX. Repeat probe for Polygon.

### Step 1 — backend skeleton (2h)

- Migration `066_market_quote.sql` creating `market_quote` table.
- `apps/api/src/services/market_quote.py` — FMP client + yfinance fallback.
- `apps/api/src/api/market.py` — `/api/market/quotes` + `/api/market/health` endpoints.
- Lifespan-launched async poller writing to `market_quote`.
- Env var `FMP_API_KEY` added to `.env.example` and compose stack.
- Unit tests: cache UPSERT, fallback path, stale flag.

### Step 2 — wire frontend (1h)

- Replace `apps/web/src/lib/market/hooks.ts` body. Delete SEEDS, delete
  random walks, delete `dailyOpens`/`sparkHistory`. Keep the `Quote`
  interface and `useMarketQuotes` signature; swap `queryFn` to
  `apiGet("/api/market/quotes", { symbols: ... })`.
- MarketTicker no UI change in this step — same render, real data.
- Verify on `/portfolio` (already wired surface).

### Step 3 — route-aware modes (1h)

The previously-scoped TASK B work (compact tape, route helper in
Shell, hide on /ops/research/alpha-lab). Lands once Step 2 confirms
the data is real.

### Step 4 — observability (30 min)

- Wire `/api/market/health` to a small badge in `/ops` page.
- Alert if `poller_status = offline` for >10 min during RTH (existing
  freshness alerting infra).

### Step 5 — production-paid switchover (5 min)

Upgrade FMP to Starter annual. Update `.env`. Restart API container.
Verify cache populates within 15s.

**Total dev time: ~5h spread across 2 sessions.** No downtime; the
fake tape stays disabled (returns `stale: true` from honest endpoint)
until Step 5 lands.

---

## 9. Honest UX labeling strategy

**Hard rule: the user must be able to tell, at a glance, that the
tape is delayed and not live.**

### Visible labels

- A small `[DELAYED 15M]` chip pinned to the right edge of the tape,
  same row as the macro/focus toggle. Always visible. `var(--fg-3)`
  color, `9px`, `letter-spacing: 0.18em`. Never animates.
- Tooltip on hover: "Quotes delayed 15 minutes by upstream provider
  (Financial Modeling Prep). Last update: 2:17 PM ET."
- For symbols with `delay_minutes != 15` (e.g. yfinance `^VIX` may be
  effectively real-time on some Yahoo paths), the chip text becomes
  `[DELAYED ≤15M]` to be conservative. Never overstate live-ness.

### Empty + degraded states

- `stale: true` → tape rendered as a 24px disabled strip with the
  text **"Market tape unavailable — awaiting upstream feed"** in
  `var(--fg-3)`. No symbols. No motion. Tooltip with `last_successful_poll`.
- Per-symbol failure (e.g. TNX returns null) → that slot renders
  `TNX —` (em-dash) instead of a number. Tooltip: "Quote unavailable;
  last successful at HH:MM ET."
- Pre-market / after-hours → same delay chip; if symbol's
  `quote_ts` is from prior session close, append `[CLOSE]` next to
  the price. Distinguishes "no movement because closed" from "no
  data at all."
- Weekend / holiday → tape replaced with a single line: **"Market
  closed — next session opens Mon 9:30 AM ET"**. Computed from
  `pandas_market_calendars`.

### What we will NOT show

- No fake tick movement.
- No interpolated prices between poll cycles.
- No "live" word anywhere in the UI.
- No green/red flash animations on price updates (suggests real-time).
- No simulated sparklines from random walks. Sparklines either come
  from real intraday history (Step 6 future work, requires storing
  ~30 minutes of recent quotes) or are omitted.

---

## Validation gates before approval

1. FMP probe (Step 0) passes: VIX returns a quote, bulk latency <2s.
2. yfinance fallback path tested: rate-limit not tripped on 2 symbols
   at 60s for a full RTH session.
3. Cost confirmed: FMP Starter at $22/mo annual is the actual landed
   number when you sign up (pricing page subject to change).
4. Approval to add one new dependency (`fmp-python` or direct httpx)
   + one new migration + two new endpoints.

---

## Sources

- [Polygon.io Pricing](https://polygon.io/pricing)
- [Polygon.io Indices API](https://polygon.io/indices)
- [Polygon Knowledge Base — Indices subscription scope](https://polygon.io/knowledge-base/article/are-all-indices-available-through-the-basic-subscription-tier)
- [Yolo Trading — Polygon.io Complete Review (2026)](https://medium.com/@yolotrading/a-complete-review-of-the-polygon-io-api-everything-you-wanted-to-know-c79e992a74ff)
- [Tiingo Pricing](https://www.tiingo.com/about/pricing)
- [Tiingo IEX API Documentation](https://www.tiingo.com/documentation/iex)
- [findmymoat.com — Tiingo Review 2026](https://www.findmymoat.com/tools/tiingo)
- [Financial Modeling Prep Pricing Plans](https://site.financialmodelingprep.com/pricing-plans)
- [FMP Index Market Data APIs](https://site.financialmodelingprep.com/datasets/indexes)
- [FMP Economics / Treasury APIs](https://site.financialmodelingprep.com/datasets/economics)
- [Alpaca Market Data FAQ](https://docs.alpaca.markets/docs/market-data-faq)
- [Alpaca Snapshot API guide](https://alpaca.markets/learn/snapshot-api)
- [Trading Dude — Why yfinance keeps getting blocked (2026)](https://medium.com/@trading.dude/why-yfinance-keeps-getting-blocked-and-what-to-use-instead-92d84bb2cc01)
- [yfinance Issue #2422 — rate limit errors](https://github.com/ranaroussi/yfinance/issues/2422)
- [yfinance Issue #2128 — new rate-limiting](https://github.com/ranaroussi/yfinance/issues/2128)

---

*Document originated 2026-05-12 ~07:30 ET as Phase 15h.5 architecture
recommendation. NOT yet implemented. Requires user approval +
validation-gate completion before any code lands.*
