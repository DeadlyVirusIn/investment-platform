import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


export type Verdict = "V2_BETTER" | "B2_BETTER" | "INCONCLUSIVE";
export type Readiness = "NOT_READY" | "REVIEW" | "STRONG_CANDIDATE";


export interface DivergenceMetrics {
  n_divergent_days: number;
  n_b2_flat_v2_long: number;
  n_b2_long_v2_flat: number;
  win_rate_v2_vs_b2_pct: number | null;
  avg_return_diff_1d_bps: number | null;
  avg_return_diff_5d_bps: number | null;
  cumulative_return_diff_pct: number | null;
  avoided_losses_count: number;
  avoided_losses_avg_bps: number | null;
  new_losses_count: number;
  new_losses_avg_bps: number | null;
  impact_weighted_edge: number | null;
}


export interface RegimeMetrics {
  stress: DivergenceMetrics;
  directional: DivergenceMetrics;
  neutral: DivergenceMetrics;
}


export interface TailStats {
  n: number;
  p95_loss_bps: number | null;
  p99_loss_bps: number | null;
  worst_5_losses_bps: number[];
}


export interface TailComparison {
  b2: TailStats;
  v2: TailStats;
  tail_delta_p95_bps: number | null;
  tail_delta_p99_bps: number | null;
}


export interface StabilitySlice {
  trend: "IMPROVING" | "DECLINING" | "STABLE" | "INSUFFICIENT";
}


export interface FirstSecondHalf extends StabilitySlice {
  first_half_edge_bps: number | null;
  second_half_edge_bps: number | null;
  n_first: number;
  n_second: number;
}


export interface Last30Prior30 extends StabilitySlice {
  last_30_edge_bps: number | null;
  prior_30_edge_bps: number | null;
  n_last: number;
  n_prior: number;
}


export interface Stability {
  first_half_vs_second_half: FirstSecondHalf;
  last_30_vs_prior_30: Last30Prior30;
}


export interface VerdictBlock {
  verdict: Verdict;
  confidence: number;
  tail_guard_triggered: boolean;
  tail_guard_reason: string | null;
  readiness: Readiness;
  base_verdict_before_guard: Verdict;
  base_confidence_before_guard: number;
}


export interface Thresholds {
  verdict_edge_bps: number;
  verdict_cum_diff_pct: number;
  verdict_p99_delta_bps: number;
  verdict_p99_delta_bps_hard: number;
  tail_guard_edge_min_bps: number;
  tail_guard_confidence_cap: number;
  stability_trend_dead_zone_bps: number;
  readiness_strong_confidence: number;
  readiness_review_confidence: number;
  readiness_strong_min_n: number;
}


export interface ComparisonBundle {
  n_input_rows: number;
  n_divergent_rows: number;
  metrics: DivergenceMetrics;
  metrics_by_regime: RegimeMetrics;
  tail: TailComparison;
  stability: Stability;
  verdict: VerdictBlock;
  thresholds: Thresholds;
  params: {
    days: number;
    instrument: string;
    cutoff: string;
    b2_source_strategy: string;
    v2_source_strategy: string;
  };
}


export function useB2vsV2Comparison(days = 365, instrument = "SPY") {
  return useQuery<ComparisonBundle>({
    queryKey: ["b2v2.comparison", days, instrument],
    queryFn: () =>
      apiGet<ComparisonBundle>(
        `/b2-v2/comparison?days=${days}&instrument=${instrument}`,
      ),
    staleTime: 60_000,
  });
}
