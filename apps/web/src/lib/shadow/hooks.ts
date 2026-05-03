import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


export type ShadowSignal = "LONG" | "FLAT";

export interface ShadowCurrent {
  as_of_date: string;
  signal: ShadowSignal;
  regime: string | null;
  trend_score: number | null;
  engine_a_active: boolean;
  note: string | null;
}

export interface ShadowRollingWindow {
  window_days: number;
  n: number;
  sharpe: number | null;
  cumulative_pct: number;
  max_dd_pct: number;
}

export interface ShadowRegimePerf {
  regime: string;
  n_days: number;
  n_long: number;
  sharpe: number | null;
  cumulative_pct: number;
}

export interface ShadowMetrics {
  cumulative_pct: number;
  sharpe_full: number | null;
  max_dd_pct: number;
  hit_rate_on_long_pct: number | null;
  n_total: number;
  n_long: number;
  n_flat: number;
  n_filtered_stress: number;
  active_pct: number;
  filtered_stress_pct: number;
  rolling: ShadowRollingWindow[];
  by_regime: ShadowRegimePerf[];
  advisory_only: true;
  execution_changed: false;
}

export interface ShadowRecentRow {
  as_of_date: string;
  signal: ShadowSignal;
  regime: string | null;
  fwd_return_1d: number | null;
  fwd_return_5d: number | null;
  trend_score: number | null;
}

export interface ShadowEquityPoint {
  date: string;
  equity: number;
}

export interface ShadowSeriesPoint {
  date: string;
  signal: ShadowSignal;
  fwd_return_1d: number | null;
  regime: string | null;
}

export interface ShadowReport {
  strategy: string;
  n_rows: number;
  current: ShadowCurrent | null;
  recent: ShadowRecentRow[];
  metrics: ShadowMetrics | null;
  equity_curve: ShadowEquityPoint[];
  series: ShadowSeriesPoint[];
}


export interface ShadowDivergence {
  strategy: string;
  n: number;
  vs_engine_a: {
    n: number; mean_bps: number; stdev_bps: number; cumulative_pct: number;
  } | null;
  vs_engine_b: {
    n: number; mean_bps: number; stdev_bps: number; cumulative_pct: number;
  } | null;
  advisory_only: true;
}


export function useShadowReport(strategy = "tsmom_60_no_stress",
                                  days = 365) {
  return useQuery<ShadowReport>({
    queryKey: ["shadow.report", strategy, days],
    queryFn: () => apiGet<ShadowReport>(
      `/shadow/strategy/${encodeURIComponent(strategy)}?days=${days}`),
    staleTime: 60_000,
  });
}


export function useShadowDivergence(strategy = "tsmom_60_no_stress") {
  return useQuery<ShadowDivergence>({
    queryKey: ["shadow.divergence", strategy],
    queryFn: () => apiGet<ShadowDivergence>(
      `/shadow/strategy/${encodeURIComponent(strategy)}/divergence`),
    staleTime: 60_000,
  });
}
