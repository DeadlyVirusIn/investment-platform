// Phase SYSTEM-ALPHA-7 — context calibration hooks.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "@/lib/api";

export interface ContextRec {
  context: { engine: string; regime: string; mode: string };
  context_key: string;
  current_multiplier: number;
  proposed_multiplier: number;
  stats: {
    sample_size: number;
    win_rate: number;
    avg_return: number;
    sharpe: number;
  };
  reason: string;
  confidence: number;
  risk_reducing: boolean;
  auto_applicable: boolean;
}

export function useContextRecs() {
  return useQuery<{ count: number; recommendations: ContextRec[] }>({
    queryKey: ["alpha", "context", "recs"],
    queryFn: () => apiGet("/alpha/context/recommendations"),
    staleTime: 5 * 60_000,
  });
}

export function useActiveContexts() {
  return useQuery<{ count: number; rows: any[] }>({
    queryKey: ["alpha", "context", "active"],
    queryFn: () => apiGet("/alpha/context/active"),
    staleTime: 5 * 60_000,
  });
}

export function useApplyContext() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (r: ContextRec) => apiPost("/alpha/context/apply", r),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alpha", "context"] });
    },
  });
}

export function useRevertContext() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (context_key: string) =>
      apiPost("/alpha/context/revert", { context_key }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alpha", "context"] });
    },
  });
}
