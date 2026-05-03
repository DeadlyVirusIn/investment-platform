// TanStack Query hooks for /api/catalysts endpoints.

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { CatalystSummary } from "./types";

export function useTopCatalysts(limit = 8) {
  return useQuery<CatalystSummary[]>({
    queryKey: ["catalysts", "top", limit],
    queryFn: () => apiGet<CatalystSummary[]>(`/catalysts/top?limit=${limit}`),
    staleTime: 5 * 60_000,
    refetchInterval: 15 * 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useCatalystForSymbol(symbol: string | null) {
  return useQuery<CatalystSummary>({
    queryKey: ["catalysts", "symbol", symbol],
    queryFn: () => apiGet<CatalystSummary>(`/catalysts/${symbol}`),
    enabled: !!symbol,
    staleTime: 5 * 60_000,
  });
}
