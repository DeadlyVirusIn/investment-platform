// Phase EXEC-VISIBILITY — clear "signals ready vs next-bar pending" status.
//
// Wires the three new endpoints:
//   /api/performance/paper/pending-fills
//   /api/performance/paper/daily-suggestions
//   /api/performance/options/strategy-suggestions
//
// All read-only. Hooks consumed by ExecutionStatusCard for the
// dashboard banner.

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";


// --------------------------------------------------------------------
// /api/performance/paper/pending-fills
// --------------------------------------------------------------------

export interface PendingFillItem {
  symbol: string;
  asset_id?: string | null;
  action?: string | null;
  submitted_at?: string | null;
  as_of_date?: string | null;
  expected_fill_rule?: string | null;
  current_status?: string | null;
  reason?: string | null;
  latest_price_bar_ts?: string | null;
  next_expected_bar_date?: string | null;
}

export interface PendingFillsResponse {
  as_of_date: string | null;
  next_expected_bar_date?: string | null;
  count: number;
  items: PendingFillItem[];
  notice?: string;
}

export function usePendingFills() {
  return useQuery<PendingFillsResponse>({
    queryKey: ["performance", "paper", "pending-fills"],
    queryFn: () => apiGet<PendingFillsResponse>(
      "/performance/paper/pending-fills",
    ),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}


// --------------------------------------------------------------------
// /api/performance/paper/daily-suggestions
// --------------------------------------------------------------------

export interface DailySuggestionItem {
  symbol: string;
  score?: number | null;
  status?: string | null;
}

export interface DailySuggestionsResponse {
  as_of_date: string | null;
  count: number;
  items: DailySuggestionItem[];
  notice?: string;
}

export function useDailySuggestions() {
  return useQuery<DailySuggestionsResponse>({
    queryKey: ["performance", "paper", "daily-suggestions"],
    queryFn: () => apiGet<DailySuggestionsResponse>(
      "/performance/paper/daily-suggestions",
    ),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}


// --------------------------------------------------------------------
// /api/performance/options/strategy-suggestions
// --------------------------------------------------------------------

export interface OptionsStrategySuggestionsResponse {
  as_of_date: string | null;
  count: number;
  contracts_reviewed?: number;
  contracts_passed_liquidity?: number;
  items: unknown[];
  notice?: string;
}

export function useOptionsStrategySuggestions() {
  return useQuery<OptionsStrategySuggestionsResponse>({
    queryKey: ["performance", "options", "strategy-suggestions"],
    queryFn: () => apiGet<OptionsStrategySuggestionsResponse>(
      "/performance/options/strategy-suggestions?limit=50",
    ),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}


// --------------------------------------------------------------------
// Derive next-bar date from a submitted_at ISO string.
// Strict next-trading-day (Mon-Fri only) — the runner uses
// `snapshot_at_utc::date > submitted_at::date`, so this matches.
// --------------------------------------------------------------------

export function nextTradingDate(after: Date): Date {
  const d = new Date(after.getFullYear(), after.getMonth(), after.getDate());
  d.setDate(d.getDate() + 1);
  while (d.getDay() === 0 || d.getDay() === 6) {
    d.setDate(d.getDate() + 1);
  }
  return d;
}

export function fmtMMDD(d: Date | string | null | undefined): string {
  if (!d) return "—";
  const date = typeof d === "string" ? new Date(d) : d;
  if (Number.isNaN(date.getTime())) return "—";
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${mm}/${dd}`;
}
