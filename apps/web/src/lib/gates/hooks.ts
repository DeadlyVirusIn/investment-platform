// Phase GATE-DIAGNOSTIC — read /api/gates/status.

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";

export interface GateRow {
  gate_id: string;
  name: string;
  status: "pass" | "fail" | "unknown" | "stale";
  current_value: unknown;
  required: string;
  source: string;
  last_updated: string | null;
  reason: string;
  plain_english: string;
  what_would_make_it_pass: string;
}

export interface EngineArming {
  engine: string;
  status: "armed" | "not_armed" | "disabled";
  missing_gates: string[];
  plain_english: string;
}

export interface GateStatus {
  as_of: string | null;
  last_updated: string | null;
  summary: {
    passing: number;
    failing: number;
    total: number;
    engine_state: string;
    next_action: string;
  };
  gates: GateRow[];
  engine_arming: EngineArming[];
}

export function useGateStatus() {
  return useQuery<GateStatus>({
    queryKey: ["gates", "status"],
    queryFn: () => apiGet<GateStatus>("/gates/status"),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}
