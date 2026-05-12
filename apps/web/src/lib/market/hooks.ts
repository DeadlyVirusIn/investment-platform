// Market-quote hook — provider-pending stub.
//
// Phase 15h.5 honesty rule: until a real delayed-quote provider is
// integrated (per docs/research/MARKET_QUOTE_PROVIDER_EVAL.md), this
// hook returns a permanent "no data" state. The Quote interface and
// useMarketQuotes signature are preserved so that wiring a real
// provider later is a single-file change: replace the queryFn body
// with `apiGet("/api/market/quotes", { symbols: ... })` once the
// backend `/api/market/quotes` endpoint exists.
//
// What this file used to be: a synthetic random-walk generator with
// hardcoded SEEDS for SPX/DJI/NDX/VIX/TNX/SPY/QQQ/AAPL/MSFT/etc. that
// drove the MarketTicker UI with fake prices. Removed because it
// violated the honest-data discipline — the user could not tell at a
// glance that the tape was synthetic.
//
// MarketTicker now renders an honest disabled-state strip and does
// NOT call this hook. The hook stays exported so that other future
// surfaces (and the eventual provider integration) have a stable
// import path.

import { useQuery } from "@tanstack/react-query";

export interface Quote {
  symbol: string;
  label: string;
  price: number;
  change: number;
  changePct: number;
  history?: number[];   // last ~24 points for sparkline (optional)
}

export function useMarketQuotes(_symbols: string[]) {
  // Permanent disabled state — no upstream provider configured.
  // Kept as a useQuery so consumers can rely on the standard
  // TanStack Query result shape (data, isError, isLoading, ...).
  return useQuery<Quote[]>({
    queryKey: ["market", "quotes", "disabled"],
    queryFn: async () => [],
    initialData: [],
    enabled: false,
    staleTime: Infinity,
  });
}
