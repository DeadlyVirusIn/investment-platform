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

## Is Alpaca needed? NO (optional complement only)

Alpaca Market Data (alpaca.markets/data) does offer OPRA options:
- **Free tier:** *indicative* options quotes, 200 calls/min, 30 WS symbols.
- **Algo Trader Plus ($99/mo):** real-time OPRA, unlimited.
- Covers stocks + ETFs.

Verdict: **not required** — Tradier already delivers stock + ETF chains.
Alpaca would only be worth adding later if (a) Tradier sandbox data quality
is insufficient for production, or (b) the universe grows large enough that
Tradier's 1 qps rate limit becomes the bottleneck. A user-provided Alpaca
token exists but is **not wired** — deferred until a real blocker appears.

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

- New equity candidates require api+worker redeploy (new constant) **and** a
  nightly options pipeline cycle to appear as cards. Expansion is additive +
  safe; visibility is deferred to that cycle.
- The advanced **detail page** (`/v2/today/options/:id`, "ENGINE SETUP",
  reached only via an explicit "View option idea" after the warning) keeps
  trader vocabulary (DTE, POP, breakeven, Greeks) by design — it is the
  deep-dive, not the default beginner card.
