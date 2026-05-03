import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


export type EngineBMode =
  | "LEGACY" | "SHADOW_COMPARE"
  | "PARTIAL_B2_25" | "PARTIAL_B2_50" | "PARTIAL_B2_75"
  | "FULL_B2";


export interface PromotionGate {
  name: string;
  passed: boolean;
  actual: number | boolean | null;
  threshold: number | boolean | null;
  note: string;
}

export interface KillSwitch {
  triggered: boolean;
  reason: string;
  metrics: { sharpe_30d?: number | null; max_dd_60d_pct?: number | null };
}

export interface PromotionVerdict {
  current_state: EngineBMode;
  recommended_state: EngineBMode;
  action: "HOLD" | "ADVANCE" | "REVERT";
  gates: PromotionGate[];
  kill_switch: KillSwitch | null;
  n_observations: number;
  note: string;
  advisory_only: true;
  auto_promote: false;
}

export interface DivergenceStats {
  n_divergent_days: number;
  b2_won_days: number;
  b2_lost_days: number;
  tied_days: number;
  mean_b2_advantage_bps: number;
  cumulative_b2_advantage_pct: number;
}

export interface EngineBTransition {
  current_mode: EngineBMode;
  state_order: EngineBMode[];
  operator_approval: boolean;
  n_total_days: number;
  n_divergent_days: number;
  n_b2_routed_long_days: number;
  metrics: {
    engine_b: { n: number; cumulative_pct: number; mean_bps: number } | null;
    b2: { n: number; cumulative_pct: number; mean_bps: number } | null;
    routed: { n: number; cumulative_pct: number; mean_bps: number } | null;
  };
  divergence_stats: DivergenceStats | null;
  verdict: PromotionVerdict;
  advisory_only: true;
  auto_promote: false;
  execution_changed_under_current_mode: boolean;
}


export interface TimelineRow {
  date: string;
  engine_b_signal: "LONG" | "FLAT" | null;
  b2_signal: "LONG" | "FLAT" | null;
  routed_signal: "LONG" | "FLAT" | null;
  divergence_flag: boolean;
  regime_label: string | null;
  fwd_return_1d: number | null;
  divergence_outcome: number | null;
  mode: string | null;
}

export interface EngineBTimeline {
  strategy: string;
  n: number;
  timeline: TimelineRow[];
}


export function useEngineBTransition(days = 365) {
  return useQuery<EngineBTransition>({
    queryKey: ["engineB.transition", days],
    queryFn: () =>
      apiGet<EngineBTransition>(`/engine-b/transition?days=${days}`),
    staleTime: 60_000,
  });
}


export function useEngineBTimeline(days = 60) {
  return useQuery<EngineBTimeline>({
    queryKey: ["engineB.timeline", days],
    queryFn: () =>
      apiGet<EngineBTimeline>(`/engine-b/transition/timeline?days=${days}`),
    staleTime: 60_000,
  });
}


// -- Analytics + Decision framework --

export interface DivergenceAnalytics {
  n_divergent_days: number;
  win_rate_b2_vs_b_pct: number | null;
  avg_return_diff_bps: number | null;
  cumulative_return_diff_pct: number | null;
  avoided_loss_count: number;
  avoided_loss_avg_bps: number | null;
  missed_win_count: number;
  missed_win_avg_bps: number | null;
}

export interface TailRiskBlock {
  n: number;
  worst_5: number[];
  p95_loss_pct: number | null;
  p99_loss_pct: number | null;
}

export interface TailRisk {
  engine_b: TailRiskBlock | null;
  engine_b2: TailRiskBlock | null;
  p99_improvement_pct: number | null;
}

export interface TransitionZones {
  n_stress_entries: number;
  n_pre_stress_obs: number;
  pre_stress_b2_avg_bps: number | null;
  pre_stress_b2_loss_bps: number | null;
  pre_stress_share_of_total_loss_pct: number | null;
}

export interface RegimeConsistency {
  stress_n_days: number;
  stress_b2_long_pct: number | null;
  stress_perf: { n: number; sharpe: number | null;
                  cumulative_pct: number | null;
                  mean_bps: number | null } | null;
  nonstress_n_days: number;
  nonstress_b2_long_pct: number | null;
  nonstress_perf: { n: number; sharpe: number | null;
                     cumulative_pct: number | null;
                     mean_bps: number | null } | null;
}

export interface StabilityBlock {
  n: number;
  first_date: string | null;
  last_date: string | null;
  engine_b_sharpe: number | null;
  b2_sharpe: number | null;
  engine_b_cum_pct: number | null;
  b2_cum_pct: number | null;
  mean_b2_edge_bps: number | null;
}

export interface EdgeTrajectory {
  window_days: number;
  recent_mean_edge_bps: number | null;
  prior_mean_edge_bps: number | null;
  delta_bps: number | null;
  slope_bps_per_day: number | null;
  trend: "IMPROVING" | "STABLE" | "DECLINING" | "INSUFFICIENT";
  dead_zone_bps: number;
  n_recent: number;
  n_prior: number;
}

export interface AnalyticsBundle {
  strategy: string;
  n_rows: number;
  divergence: DivergenceAnalytics;
  tail_risk: TailRisk;
  transition_zones: TransitionZones;
  regime_consistency: RegimeConsistency;
  stability: {
    early: StabilityBlock | null;
    recent: StabilityBlock | null;
    sharpe_drift: number | null;
    edge_drift_bps: number | null;
  };
  edge_trajectory: EdgeTrajectory;
  readiness: {
    score: number;
    label: "NOT_READY" | "READY_FOR_REVIEW" | "STRONG_CANDIDATE";
    breakdown: Record<string, string>;
  };
}


export interface DecisionGate {
  name: string;
  passed: boolean;
  actual: number | boolean | null;
  threshold: number | boolean | null;
  note: string;
}


export interface StabilityWindow {
  window_days: number;
  n: number;
  sharpe: number | null;
  cumulative_pct: number | null;
  mean_edge_bps: number | null;
  pass_threshold: boolean;
}


export interface PromotionPause {
  active: boolean;
  severity: "INFO" | "WARNING" | "BLOCKING";
  triggered_by: string;
  reason: string;
  clear_condition: string;
  label_override: string | null;
  metrics: Record<string, unknown>;
}


export type DecisionLabel =
  | "NOT_READY" | "READY_FOR_REVIEW" | "STRONG_CANDIDATE"
  | "READY_FOR_REVIEW_PAUSED"
  | "PROMOTION_PAUSED_EDGE_DECAY"
  | "STRUCTURAL_REVIEW_REQUIRED";


export interface DecisionVerdict {
  strategy: string;
  current_state: EngineBMode;
  recommended_state: EngineBMode;
  action: "HOLD" | "READY_FOR_NEXT" | "ADVANCE" | "REVERT";
  label: DecisionLabel;
  score: number;
  score_breakdown: Record<string, string>;
  gates: DecisionGate[];
  failed_gates: string[];
  stability_windows: StabilityWindow[];
  kill_switch: { triggered: boolean; reason: string };
  operator_approval: boolean;
  note: string;
  n_observations: number;
  thresholds_used: Record<string, number | boolean>;
  execution_changed_under_current_mode: boolean;
  advisory_only: true;
  auto_promote: false;
  promotion_pause: PromotionPause | null;
}


export function useEngineBAnalytics(days = 365) {
  return useQuery<AnalyticsBundle>({
    queryKey: ["engineB.analytics", days],
    queryFn: () =>
      apiGet<AnalyticsBundle>(`/engine-b/analytics?days=${days}`),
    staleTime: 60_000,
  });
}


export function useEngineBDecision(days = 365) {
  return useQuery<DecisionVerdict>({
    queryKey: ["engineB.decision", days],
    queryFn: () =>
      apiGet<DecisionVerdict>(`/engine-b/decision?days=${days}&persist=true`),
    staleTime: 60_000,
  });
}
