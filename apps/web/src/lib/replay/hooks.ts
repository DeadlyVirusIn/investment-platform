// Phase ML-2.5 — replay admin hooks.

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";

export interface ReplayLatestRun {
  present: boolean;
  run?: {
    id: string;
    replay_name: string;
    replay_version: string;
    created_at: string;
    start_date: string;
    end_date: string;
    status: string;
    warnings: string[] | null;
    summary: {
      n_decisions?: number;
      n_symbols?: number;
      n_dates?: number;
      warnings?: string[];
    } | null;
  };
}

export function useReplayLatestRun() {
  return useQuery<ReplayLatestRun>({
    queryKey: ["ml", "replay", "latest"],
    queryFn: () => apiGet<ReplayLatestRun>("/ml/replay/runs/latest"),
    staleTime: 5 * 60_000,
    refetchInterval: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}
