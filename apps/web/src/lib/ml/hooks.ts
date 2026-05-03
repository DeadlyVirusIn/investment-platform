// ML research hooks — read-only admin surfaces.

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";

export interface MLLatestSnapshot {
  present: boolean;
  snapshot?: {
    id: string;
    as_of_date: string;
    created_at: string;
    row_count: number;
    labeled_row_count: number;
    symbol_count: number;
    date_start: string | null;
    date_end: string | null;
    tier: string;
    leakage_clean: boolean;
    recommendation: string | null;
    feature_health: Record<string, unknown>;
    leakage_report: Record<string, unknown>;
    baseline_results: Record<string, unknown>;
    patterns: Record<string, unknown>;
    engine_c_status: Record<string, unknown>;
    warnings: string[] | null;
  };
}

export interface EngineCReadiness {
  engine_c_ml_status: string;
  engine_c_ml_reason: string;
  engine_c_training_rows: number;
  engine_c_labeled_rows: number;
  engine_c_latest_eval_score: number | null;
  engine_c_baseline_best: number;
  engine_c_catalyst_coverage: number;
  engine_c_avg_feature_conf: number;
  engine_c_blockers: string[];
  engine_c_next_requirement: string;
  min_rows_required: number;
}

export function useMLLatestSnapshot() {
  return useQuery<MLLatestSnapshot>({
    queryKey: ["ml", "snapshot", "latest"],
    queryFn: () => apiGet<MLLatestSnapshot>("/ml/research/snapshots/latest"),
    staleTime: 10 * 60_000,
    refetchInterval: 15 * 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useEngineCReadiness() {
  return useQuery<EngineCReadiness>({
    queryKey: ["ml", "engine-c-readiness"],
    queryFn: () => apiGet<EngineCReadiness>("/ml/research/engine-c-readiness"),
    staleTime: 10 * 60_000,
    refetchInterval: 15 * 60_000,
    refetchOnWindowFocus: false,
  });
}
