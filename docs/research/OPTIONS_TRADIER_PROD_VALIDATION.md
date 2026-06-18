# Tradier Production Validation — Stock Options Unblock (2026-06-18)

## Headline finding: we are ALREADY on Tradier production

`.env` is set to the **production** endpoint, not sandbox:
```
OPTIONS_DATA_PROVIDER=tradier
TRADIER_BASE_URL=https://api.tradier.com/v1     # production (sandbox = sandbox.tradier.com)
TRADIER_ACCESS_TOKEN=<valid production token>   # returned 1378 real AAPL quotes, status=ok
```
(The in-code default is `sandbox.tradier.com`, but `.env` overrides it to prod.
The ingest log tags `provider_version=tradier-prod`.)

So "switch to Tradier production" requires **no config change** — it is the
current state. The question becomes: does prod actually yield stock candidates?

## Why the earlier AAPL test showed 0 inserts (not a provider failure)

The AAPL/MSFT ingest ran at **20:47 UTC = 16:47 ET — after the 16:00 ET close.**
After hours, market makers pull quotes → zero bids, wide spreads, stale
timestamps. The liquidity gate (production profile) is strict:
```
max_bid_ask_spread = $0.10
min_open_interest  = 500
max_quote_age      = (stale gate)
```
Result: `inserted=0`, rejects dominated by `WIDE_SPREAD` + `BID_NONPOSITIVE`
+ `STALE_QUOTE`. Expected for a closed market.

**Proof the pipeline works in-hours:** the 5 ETFs' latest snapshots are stamped
`2026-06-18 14:15:28 UTC = 10:15 ET` — mid-session — and inserted tens of
thousands of rows (SPY 56,500). The intraday cron target is `*/15 13-21 * * 1-5`
UTC (market hours). The ETF path is healthy; only the timing of the ad-hoc
stock test was wrong.

## Conclusion (so far)

- Tradier **production is already configured** and returns real chains for
  individual stocks (AAPL 1378, MSFT 1578 quotes).
- The 0-insert result is a **market-hours artifact**, not a production failure.
- **Determination PENDING a market-hours ingest run.** No Alpaca work until
  that test runs — per the brief, Alpaca plan is produced only if prod fails.

## Env / config required

| Setting | Required value | Current | Action |
|---|---|---|---|
| `OPTIONS_DATA_PROVIDER` | `tradier` | `tradier` | none |
| `TRADIER_BASE_URL` | `https://api.tradier.com/v1` | same | none |
| `TRADIER_ACCESS_TOKEN` | production token | set, valid | none |
| `OPTIONS_ENABLED` | `true` | `true` | none |
| universe | includes equities | expanded (commit 1261b3d) | redeploy done |

No env changes needed. The only requirement is to **run ingestion during US
market hours** (13:30–20:00 UTC, Mon–Fri).

## Validation checklist (run during market hours)

Run from a worker container, weekday 13:30–20:00 UTC:

1. **Ingest** — fetch + filter stock chains:
   ```
   docker compose --env-file .env -f infra/compose/docker-compose.yml exec -T worker-tickloop \
     python -c "from apps.api.src.options.data.chain_ingest import ingest_universe; \
                print(ingest_universe(universe=('AAPL','MSFT','NVDA')))"
   ```
   PASS if each shows `inserted > 0`.
2. **Candidate generation** — run the downstream shadow→candidate jobs (or the
   nightly pipeline) so `options_strategy_candidate` gets stock rows:
   ```
   select underlying, count(*) from options_strategy_candidate
   where underlying in ('AAPL','MSFT','NVDA') group by underlying;
   ```
   PASS if ≥3 stock underlyings have ≥1 candidate.
3. **Opportunities API**:
   ```
   GET /api/options/opportunities?limit=200  → contains AAPL/MSFT/NVDA items
   ```
4. **Discover Options Practice UI** — `/v2/discover` → Options Practice tab
   shows at least one individual-stock card with Name (TICKER), Ends on, and
   (when priced) Practice entry / Best case / Maximum loss.

### Success criteria
≥3 individual-stock underlyings (AAPL, MSFT, NVDA or equivalent) produce valid
option candidates visible through the API and UI.

- **If PASS:** stop. Tradier production solves the blocker. No Alpaca work.
- **If FAIL** (in-hours, still 0 inserts or 0 candidates): the blocker is real;
  produce the Alpaca integration plan (endpoints, auth, chain-ingest changes,
  candidate-gen impact, effort, migration).

---

# UX Review — strategy names on beginner cards

## Current wording
Beginner card leads with the **real strategy name** + a descriptor:
```
State Street SPDR S&P 500 ETF Trust (SPY)
Iron Condor
TIME LEFT … ENDS ON … PRACTICE ENTRY …
```
Names shown today (from `STRATEGY_META`): Iron Condor, Put Credit Spread,
Call Credit Spread, Bull Call Spread, Bear Put Spread, Long Call, Long Put,
Long Straddle, Long Strangle. (Calendar Spread not in v1 set.)

A first-time investor does not know what "Iron Condor" or "Credit Spread" means.

## Proposed wording (plain primary, real name secondary)

Lead with a plain-English label; keep the real name small beneath it so the
beginner still learns the term. Detail page keeps the real name unchanged.

| Real name | Proposed plain label | One-line meaning |
|---|---|---|
| Iron Condor | **Stays-in-range play** | profits if the stock barely moves |
| Put Credit Spread | **Mild-up income play** | profits if it holds up or rises a little |
| Call Credit Spread | **Mild-down income play** | profits if it stays weak or falls a little |
| Bull Call Spread | **Up play (capped)** | profits if it rises, limited cost + gain |
| Bear Put Spread | **Down play (capped)** | profits if it falls, limited cost + gain |
| Calendar Spread | **Timing play** | profits from time passing / a near-term lull |
| Long Call | **Up bet (capped cost)** | profits if it rises; you can only lose the premium |
| Long Put | **Down bet (capped cost)** | profits if it falls; you can only lose the premium |
| Long Straddle/Strangle | **Big-move play** | profits if it moves a lot either way |

### Mockup (card header)
```
Before:                          After:
─────────────────────────       ───────────────────────────────
Apple (AAPL)                     Apple (AAPL)
Iron Condor                      Stays-in-range play
                                 Iron Condor · defined risk
TIME LEFT  About 6 weeks left    TIME LEFT  About 6 weeks left
```

## Recommendation

**Adopt plain primary + real name secondary on beginner cards; leave the detail
page showing the real strategy name only.** Rationale: beginners get an
instantly-understandable label, but the real term stays visible (small) so they
build vocabulary — consistent with the "learn by doing" positioning. Implement
as a `strategyPlain(ruleId)` map in `optionsPresent.ts`, rendered by
`OptionsAdvancedSection`; `OptionsSetupDetail` unchanged. Low risk, no data
dependency. (Not implemented yet — awaiting go-ahead.)
