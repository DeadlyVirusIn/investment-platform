// Phase ML-2.6 — replay training readiness hook.

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";

export interface ReadinessReport {
  status: string;
  blockers: string[];
  recommended_next_action: string;
  coverage_summary: {
    total_symbols?: number;
    total_news?: number;
    total_earnings?: number;
    pct_symbol_month_coverage?: number;
    pct_known_at_coverage?: number;
    global_quality_tier?: string;
    warnings?: string[];
  };
  validation_summary: {
    comparable_decisions?: number;
    action_agreement_rate?: number;
    engine_agreement_rate?: number;
    avg_confidence_delta?: number;
  };
  leakage_summary: { ok?: boolean; violations?: string[] };
  safe_config_recommendation: {
    ML_DATASET_INCLUDE_REPLAY: boolean;
    ML_REPLAY_WEIGHT: number;
  };
}

export function useReplayReadiness() {
  return useQuery<ReadinessReport>({
    queryKey: ["ml", "replay", "readiness"],
    queryFn: () => apiGet<ReadinessReport>("/ml/replay/training-readiness"),
    staleTime: 10 * 60_000,
    refetchInterval: 20 * 60_000,
    refetchOnWindowFocus: false,
  });
}
