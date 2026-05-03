// Phase SYSTEM-ALPHA — read-only admin hooks.

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";

export interface SystemHealthResp {
  present: boolean;
  overall?: number;
  components?: {
    data_quality?: number;
    signal_quality?: number;
    catalyst_coverage?: number;
    execution_quality?: number;
    risk_control?: number;
    ml_readiness?: number;
    paper_feedback?: number;
  };
  recommendation?: string;
  warnings?: string[];
  computed?: any;
  created_at?: string;
}

export function useSystemHealthScore() {
  return useQuery<SystemHealthResp>({
    queryKey: ["system", "health-score"],
    queryFn: () => apiGet<SystemHealthResp>("/system/health-score"),
    staleTime: 10 * 60_000,
    refetchInterval: 15 * 60_000,
    refetchOnWindowFocus: false,
  });
}
