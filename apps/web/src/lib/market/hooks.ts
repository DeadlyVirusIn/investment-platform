// Market-tape hook — Phase 15h.5.
//
// Reads /api/market/tape, which is served from the backend's
// in-process Polygon poller (90s cadence, 15-min delayed quotes,
// SPY/QQQ/DIA scope). The frontend NEVER calls Polygon directly.
//
// Honest discipline: the response carries `stale`, `delay_minutes`
// per quote, and a top-level `source` so the UI can label freshness
// truthfully. When `stale: true`, MarketTicker hides its quote row
// and renders the calm disabled strip instead.

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";


export interface TapeQuote {
  symbol: string;
  price: number | null;
  prev_close: number | null;
  change_abs: number | null;
  change_pct: number | null;
  quote_ts: string | null;       // ISO; source-reported timestamp (delayed)
  source: string;                // "polygon"
  delay_minutes: number;         // 15
  history?: number[];            // intraday 1-min closes (chronological)
}


export interface TapeSnapshot {
  stale: boolean;
  fetched_at: string | null;
  max_delay_minutes: number | null;
  source: string | null;
  symbols_tracked: string[];
  quotes: TapeQuote[];
  error: string | null;
}


export type TapeScope = "macro" | "holdings";


// Generalized tape hook. `scope="macro"` (default) hits /market/tape
// (SPY/QQQ/DIA). `scope="holdings"` hits /market/holdings-tape (open
// paper positions). Identical response shape; `holdings` adds a
// `scope: "holdings"` field and omits the `history` field per quote.
export function useTape(scope: TapeScope = "macro") {
  const path = scope === "holdings" ? "/market/holdings-tape" : "/market/tape";
  return useQuery<TapeSnapshot>({
    queryKey: ["market", "tape", scope],
    queryFn: () => apiGet<TapeSnapshot>(path),
    refetchInterval: 60_000,        // refetch from cache every 60s
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}


// Back-compat alias — existing call sites (Shell.tsx) keep working.
export function useMarketTape() {
  return useTape("macro");
}


// ---------------------------------------------------------------------------
// Legacy stub — kept exported as a no-op so any straggler import still
// type-checks. The real surface is useMarketTape() above. Remove this
// once a grep confirms zero callers.
// ---------------------------------------------------------------------------
export interface Quote {
  symbol: string;
  label: string;
  price: number;
  change: number;
  changePct: number;
  history?: number[];
}

export function useMarketQuotes(_symbols: string[]) {
  return useQuery<Quote[]>({
    queryKey: ["market", "quotes", "deprecated"],
    queryFn: async () => [],
    initialData: [],
    enabled: false,
    staleTime: Infinity,
  });
}
