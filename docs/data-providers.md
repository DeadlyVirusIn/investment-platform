# Data Providers

> **Note:** All limits below are VERIFIED against provider docs as of the
> project's debate synthesis phase. **Re-verify every limit before Phase 1**
> — free tiers change frequently.

---

## Rate-Limit Table

| Provider | Endpoint / Feed | Free Tier Limit | Auth | Notes |
|----------|----------------|-----------------|------|-------|
| **Tiingo** | EOD prices (`/tiingo/daily`) | 500 req/hr, 50 000 req/day | API key header | 5-year history on free tier. VERIFIED |
| **Tiingo** | IEX real-time (`/iex`) | 1 000 ticks/hr | API key header | Delayed ~15 min on free. VERIFIED |
| **Tiingo** | Fundamentals (`/fundamentals`) | 10 req/hr (free); 10 000 req/day Pro | API key header | Free tier very limited — use sparingly. VERIFIED |
| **CoinGecko** | `/coins/markets` | 10–30 req/min (public) | None (key optional) | Use `x-cg-api-key` to get 500 req/min on free demo key. VERIFIED |
| **CoinGecko** | `/coins/{id}/market_chart` | Same as above | None / demo key | History up to 365 days on free. VERIFIED |
| **Alpha Vantage** | Various | 25 req/day free | API key query param | Too restrictive for prod use — consider paid tier or drop. VERIFIED |
| **FRED** | Economic series | Generous (unlimited key) | API key query param | Used for macro regime signals (DFF, UNRATE, T10Y2Y). VERIFIED |
| **MoonPay** | Purchase records (webhook) | N/A — webhook push | Webhook secret | On-chain purchase records only; not a market data source. VERIFIED |

---

## Provider Usage by Job

| Job | Provider | Frequency |
|-----|----------|-----------|
| `ingest_equity_eod` | Tiingo EOD | Daily after market close |
| `ingest_equity_realtime` | Tiingo IEX | Every 15 min (market hours) |
| `ingest_fundamentals` | Tiingo Fundamentals | Weekly |
| `ingest_crypto` | CoinGecko | Every 2 h |
| `ingest_macro` | FRED | Daily |

---

## Back-fill Strategy

On first run, the worker back-fills up to 5 years of daily price history for
each symbol in the watchlist. This consumes most of the daily Tiingo quota on
day one — stagger symbol additions if you have a large watchlist.

---

## Adding a New Provider

See `docs/onboarding.md` → "Adding a new provider".

---

## Rate-Limit Implementation

A simple token-bucket class (`apps/worker/rate_limiter.py`) wraps each
provider client. Buckets are in-process (not Redis) — adequate for a single
worker process. If the worker ever scales horizontally, migrate to a Redis
token bucket.
