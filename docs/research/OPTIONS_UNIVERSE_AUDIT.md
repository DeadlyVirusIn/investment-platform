# Options Pipeline Audit + Universe Expansion (2026-06-18)

## Why only SPY / GLD / IWM / QQQ appeared

**Root cause: a hardcoded universe, NOT a provider limit.**

Pipeline end-to-end:
`chain_ingest.DEFAULT_UNIVERSE` → `options_chain_snapshot` job → shadow
eval → `options_strategy_candidate` → `GET /options/opportunities`
(`opportunities/service.py`) → `useOptionsLanes` → Options Practice cards.

`apps/api/src/options/data/chain_ingest.py` defined:
```
DEFAULT_UNIVERSE = ("SPY", "QQQ", "IWM", "GLD", "TLT")
```
Only these 5 ETFs were ever ingested, so candidates only ever existed for
them (DB confirmed: `options_strategy_candidate` had exactly SPY/QQQ/IWM/
GLD/TLT, run_date = today). The UI showed 4 because TLT lacked displayed
setups. Provider, selector, persistence all work — the input list was the cap.

## Can the current provider do individual-stock options? YES

Dev provider = **Tradier** (`OPTIONS_DATA_PROVIDER=tradier`,
`OPTIONS_ENABLED=true`, sandbox token set). Verified live:
- `get_chain_snapshot(symbol="AAPL")` → **1378 quotes**
- `get_chain_snapshot(symbol="SPY")`  → **5744 quotes**

Tradier returns full chains for any optionable equity. The provider was
never the blocker.

## The REAL blocker for stock cards: sandbox quote quality

Capability ≠ usable data. After expanding the universe, a targeted ingest of
AAPL + MSFT through the live pipeline showed:

```
AAPL: provider_quotes=1378 inserted=0
      rejects={BID_NONPOSITIVE:381, WIDE_SPREAD:787, STALE_QUOTE:130, LOW_OPEN_INTEREST:80}
MSFT: provider_quotes=1578 inserted=0
      rejects={BID_NONPOSITIVE:298, WIDE_SPREAD:1094, STALE_QUOTE:147, LOW_OPEN_INTEREST:39}
```

The **Tradier sandbox** returns chains but with synthetic/stale quotes
(non-positive bids, wide spreads, stale timestamps) that fail the liquidity
gate (`liquidity_filter`). Result: **0 snapshot rows → 0 stock candidates**,
even with the universe expanded. The ETF candidates that exist today scrape
through the same gates only marginally.

So the universe expansion is correct and additive, but stock cards will NOT
appear until a **real-quality options quote source** is wired.

## Is Alpaca needed? Now YES — for real quotes (or Tradier production)

To populate single-name option candidates we need real bid/ask/OI, which the
sandbox does not provide. Two paths:

1. **Tradier production token** — same adapter, just real quotes. Cheapest
   change (swap `TRADIER_ACCESS_TOKEN` + base URL to production). No new code.
2. **Alpaca options** (user has a token) — new adapter:
   - Free tier = *indicative* OPRA quotes (200 calls/min, 30 WS symbols);
     Algo Trader Plus ($99/mo) = real-time OPRA. Covers stocks + ETFs.
   - Plan: add `apps/api/src/options/data_provider/alpaca_adapter.py`
     implementing `BaseOptionsAdapter.get_chain_snapshot()` (REST
     `/v1beta1/options/snapshots/{underlying}`), wire into
     `chain_ingest._build_adapter('alpaca')`, add `ALPACA_API_KEY_ID` /
     `ALPACA_API_SECRET_KEY` env, set `OPTIONS_DATA_PROVIDER=alpaca`.
   - Validate indicative-quote quality against the liquidity gate before
     committing (indicative quotes may still trip WIDE_SPREAD).

**Recommendation:** try the Tradier production token first (zero new code);
fall back to the Alpaca adapter if production access isn't available. Do NOT
relax the liquidity filter to admit sandbox junk.

## What was implemented now

1. **Universe expansion** (`chain_ingest.py`): added 10 deeply-liquid
   single-name equities (AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, AMD,
   NFLX, JPM) to the 5 ETFs. New names surface in the UI only after the
   nightly `chain→shadow→candidate` pipeline processes them.
2. **Card enrichment** (UI, using fields the API already returns — no
   provider change, no fabrication):
   - Company name via `CompanyTitle` (e.g. "State Street SPDR S&P 500 ETF
     Trust (SPY)").
   - **Ends on `<expiry>`** (real `expiry`).
   - **Practice entry**: "You receive $X now (a credit)" / "You pay $X
     (a debit)" — real `economics.net_credit/net_debit`.
   - **Best case**: real `economics.max_profit`.
   - **Maximum loss**: real `economics.max_risk` (capped fallback otherwise).
   - All economics rows are conditional — shown only when priced legs exist;
     never fabricated. `expiry` is near-always present; economics is
     intermittent (depends on fresh priced legs).
   - Explainer: "These are advanced practice setups. They use capped-risk
     option structures and should be practiced before real money."

## Remaining / operational

- New equity candidates require api+worker redeploy (done) **and** a
  real-quality quote source (Tradier production OR Alpaca). Under the current
  sandbox token they ingest 0 rows, so no stock cards appear yet — this is
  the open blocker, not a code gap. ETFs remain fully functional.
- The advanced **detail page** (`/v2/today/options/:id`, "ENGINE SETUP",
  reached only via an explicit "View option idea" after the warning) keeps
  trader vocabulary (DTE, POP, breakeven, Greeks) by design — it is the
  deep-dive, not the default beginner card.
