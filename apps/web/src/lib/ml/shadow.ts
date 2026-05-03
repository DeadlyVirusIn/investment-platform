// Phase ML-3 — shadow ML admin hooks.

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";

export interface ShadowLatestReport {
  present: boolean;
  latest_model_run?: {
    id: string;
    created_at: string;
    model_type: string;
    dataset_source: string;
    status: string;
    row_count: number;
    labeled_row_count: number;
    blockers: string[] | null;
    baseline_comparison?: {
      winner?: string;
      delta_sharpe?: number;
      shadow?: { n_accepted?: number; sharpe_proxy?: number };
      baselines_best?: { name?: string; sharpe_proxy?: number };
    } | null;
    calibration?: {
      ece?: number;
      brier?: number;
      poor_calibration?: boolean;
    } | null;
    feature_health?: Record<string, unknown>;
    metrics?: Record<string, unknown>;
  };
  prediction_counts?: {
    n?: number;
    n_accept?: number;
    n_avoid?: number;
    n_reduce?: number;
    n_needs?: number;
  } | null;
}

export function useShadowLatestReport() {
  return useQuery<ShadowLatestReport>({
    queryKey: ["ml", "shadow", "latest-report"],
    queryFn: () => apiGet<ShadowLatestReport>("/ml/shadow/latest-report"),
    staleTime: 10 * 60_000,
    refetchInterval: 15 * 60_000,
    refetchOnWindowFocus: false,
  });
}


// ------------------------------------------------------------------
// ML-5 — Hybrid Advisor
// ------------------------------------------------------------------

export interface HybridActivity {
  trade_id: string;
  entry_date: string;
  instrument: string | null;
  engine: string | null;
  multiplier: number;
  action: string | null;
  available: boolean;
  reason: string | null;
}

export interface HybridStatus {
  config: {
    enabled: boolean;
    mode: "advisory" | "paper_reduce" | string;
    min_confidence: number;
    require_calibration: boolean;
    require_baseline_beat: boolean;
    max_stale_days: number;
    min_data_confidence: number;
    allow_block: boolean;
    min_multiplier: number;
  };
  ml_can_affect_trades: boolean;
  latest_model_run: {
    id: string;
    status: string;
    created_at: string;
    calibration?: { ece?: number; poor_calibration?: boolean } | null;
    baseline_comparison?: {
      winner?: string; delta_sharpe?: number;
    } | null;
  } | null;
  recent_activity: HybridActivity[];
}

export function useHybridStatus() {
  return useQuery<HybridStatus>({
    queryKey: ["ml", "hybrid", "status"],
    queryFn: () => apiGet<HybridStatus>("/ml/hybrid/status"),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}


// ------------------------------------------------------------------
// ML-6 — Performance + Promotion
// ------------------------------------------------------------------

export interface HybridWindow {
  window_days: number;
  as_of_date: string;
  mode: string;
  ml_advice_count: number;
  ml_reduce_count: number;
  ml_avoid_count: number;
  ml_eligible_count: number;
  ml_gated_count: number;
  deterministic_trades: number;
  ml_agreement_count: number;
  ml_disagreement_count: number;
  avoided_loss_estimate: number | null;
  missed_winner_estimate: number | null;
  false_avoid_rate: number | null;
  missed_winner_rate: number | null;
  good_warning_rate: number | null;
  avg_return_when_ml_agreed: number | null;
  avg_return_when_ml_warned: number | null;
  avg_return_when_ml_unavailable: number | null;
  delta_sharpe_vs_deterministic: number | null;
  calibration_ece: number | null;
  brier_score: number | null;
  model_status: string | null;
  blockers: string[];
  recommendation: string;
  metrics: Record<string, unknown>;
}

export interface PromotionDecisionDTO {
  state: string;
  current_mode: string;
  blockers: string[];
  reasons: string[];
  recommendation: string;
  operator_approval_required: boolean;
  healthy_day_count: number | null;
}

export interface PromotionStatus {
  as_of: string;
  current_mode: string;
  promotion: PromotionDecisionDTO;
  windows: Record<string, HybridWindow>;
  thresholds: {
    min_advice: number;
    min_outcomes: number;
    max_ece: number;
    min_delta_sharpe: number;
    max_false_avoid_rate: number;
    required_healthy_days: number;
  };
}

export function usePromotionStatus() {
  return useQuery<PromotionStatus>({
    queryKey: ["ml", "hybrid", "promotion-status"],
    queryFn: () => apiGet<PromotionStatus>("/ml/hybrid/promotion-status"),
    staleTime: 5 * 60_000,
    refetchInterval: 10 * 60_000,
    refetchOnWindowFocus: false,
  });
}
