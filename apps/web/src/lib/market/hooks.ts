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


export type TapeScope = "macro" | "holdings" | "combined";


// Generalized tape hook.
//   scope="macro"      → /market/tape          (SPY/QQQ/DIA)
//   scope="holdings"   → /market/holdings-tape (open paper positions)
//   scope="combined"   → /market/combined-tape (macro + holdings, single scroll)
// Identical response shape across scopes (combined adds segment per quote
// + segment_breakdown summary).
export function useTape(scope: TapeScope = "macro") {
  const path =
    scope === "holdings" ? "/market/holdings-tape"
    : scope === "combined" ? "/market/combined-tape"
    : "/market/tape";
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


// Per-symbol news + catalysts (Sprint I). Real data from /news/symbol/{symbol};
// empty when none (no fabrication).
export interface SymbolNewsItem {
  id: string;
  source: string;
  url: string | null;
  title: string;
  summary: string | null;
  published_at: string;
  category: string | null;
  sentiment: string | null;
  impact_level: string | null;
}

export interface SymbolNews {
  symbol: string;
  count: number;
  items: SymbolNewsItem[];
  summary: {
    article_count: number;
    sentiment_label: string | null;
    dominant_category: string | null;
  } | null;
}

export function useSymbolNews(symbol: string | undefined) {
  return useQuery<SymbolNews>({
    queryKey: ["news", "symbol", symbol],
    queryFn: () => apiGet<SymbolNews>(`/news/symbol/${symbol}?days=14&limit=6`),
    enabled: !!symbol,
    staleTime: 300_000,
    retry: false,            // missing/empty news -> show nothing, don't spin
  });
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
