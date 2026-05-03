// Phase DAILY-VISIBILITY — paper-run hooks.

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";

export interface PaperRunSummary {
  present: boolean;
  id?: string;
  run_date?: string;
  started_at?: string;
  finished_at?: string;
  status?: string;
  decisions_evaluated?: number;
  trades_opened?: number;
  trades_closed?: number;
  trades_skipped?: number;
  exploratory_trades?: number;
  strict_trades?: number;
  blocked_by_gates?: number;
  blocked_by_anomaly?: number;
  blocked_by_data_quality?: number;
  net_pnl_today?: number;
  nav_start?: number;
  nav_end?: number;
  summary?: string;
  warnings?: string[] | null;
  details?: Record<string, unknown> | null;
}

export function useLatestPaperRun() {
  return useQuery<PaperRunSummary>({
    queryKey: ["paper", "runs", "latest"],
    queryFn: () => apiGet<PaperRunSummary>("/paper/runs/latest"),
    staleTime: 2 * 60_000,
    refetchInterval: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}

export interface PaperRunEvent {
  ts?: string;
  symbol?: string;
  engine?: string;
  action?: string;
  event_type?: string;
  gate_mode?: string;
  exploratory_paper?: boolean;
  alpha_rule_size_multiplier?: number | null;
  position_size_pct?: number | null;
  gross_ret_pct?: number | null;
  net_ret_pct?: number | null;
  gates_passed?: number | null;
  gates_total?: number | null;
  reason?: string | null;
  status?: string | null;
  // ALPHA-8 similarity annotation (present on trade events only)
  sim_matched?: string | null;
  sim_mult?: string | null;
  sim_reason?: string | null;
  sim_n?: string | null;
  sim_avg?: string | null;
  sim_wr?: string | null;
  // ML-5 hybrid advisor annotation (present on trade events only)
  ml_avail?: string | null;
  ml_mult?: string | null;
  ml_action?: string | null;
  ml_reason?: string | null;
  ml_status?: string | null;
}

export interface PaperRunEvents {
  run_date: string | null;
  count: number;
  decisions: PaperRunEvent[];
  trades: PaperRunEvent[];
}

export function useLatestPaperRunEvents() {
  return useQuery<PaperRunEvents>({
    queryKey: ["paper", "runs", "latest", "events"],
    queryFn: () => apiGet<PaperRunEvents>("/paper/runs/latest/events"),
    staleTime: 2 * 60_000,
    refetchInterval: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}
