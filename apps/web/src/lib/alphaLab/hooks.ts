// Alpha Lab data hook — backed by /api/performance/paper/alpha-lab.

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";


export interface AlphaLabPosition {
  position_id: number;
  portfolio_id: string;
  portfolio_name: string;
  symbol: string;
  asset_id: string;
  quantity: number;
  entry_price: number;
  last_price: number | null;
  last_price_date: string | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  held_days: number | null;
  age_bucket: string | null;
}


export interface AlphaLabClosedTrade {
  trade_id: string;
  portfolio_id: string;
  portfolio_name: string;
  symbol: string;
  quantity: number;
  exit_price: number;
  exit_ts: string | null;
  realized_pnl: number;
  reason: string | null;
  is_replay: boolean;
}


export interface AlphaLabSummary {
  as_of_date: string;
  open_positions: number;
  closed_positions: number;
  open_unrealized_pnl: number;
  closed_realized_pnl: number;
  pending_fills: number;
  live_trades: number;
  replay_trades: number;
  open_winners_count: number;
  open_losers_count: number;
}


export interface AlphaLabResponse {
  as_of_date: string;
  summary: AlphaLabSummary;
  open_winners: AlphaLabPosition[];
  open_losers: AlphaLabPosition[];
  closed_winners: AlphaLabClosedTrade[];
  closed_losers: AlphaLabClosedTrade[];
  patterns: {
    by_age_bucket: Array<{
      bucket: string;
      n: number;
      avg_upnl_pct: number;
    }>;
    by_portfolio: Array<{
      portfolio: string;
      n_open: number;
      sum_unrealized: number;
    }>;
    concentration: Array<{
      symbol: string;
      n_open: number;
      total_notional: number;
    }>;
  };
  notice?: string;
}


export function useAlphaLab(limit: number = 20) {
  return useQuery<AlphaLabResponse>({
    queryKey: ["alpha-lab", limit],
    queryFn: () => apiGet<AlphaLabResponse>(
      `/performance/paper/alpha-lab?limit=${limit}`,
    ),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}


// ---------------------------------------------------------------
// Trade Quality (Phase B — pre-ML diagnostic). Read-only.
// ---------------------------------------------------------------

export type TradeQualityGrade = "A" | "B" | "C" | "D" | "F";

export type TradeQualityThesis =
  | "open_positive" | "open_negative"
  | "stopped_out" | "take_profit" | "max_hold" | "closed_other"
  | "pending_next_bar" | "insufficient_data";

export type TradeQualityCompleteness = "full" | "partial" | "low";

export interface TradeQualityItem {
  trade_id: string;
  symbol: string;
  portfolio_id: string;
  portfolio_name: string;
  side: "buy" | "sell";
  is_open: boolean;
  fill_ts: string | null;
  entry_price: number;
  qty: number;
  held_days: number | null;
  current_price: number | null;
  realized_pnl: number | null;
  exit_reason: string | null;
  score: number;
  grade: TradeQualityGrade;
  thesis: TradeQualityThesis;
  completeness: TradeQualityCompleteness;
  components: {
    entry: number;
    return: number;
    hold: number;
    exit_or_status: number;
    completeness: number;
  };
  reasons: string[];
}

export interface TradeQualityResponse {
  notice: string;
  as_of_date: string;
  include_replay: boolean;
  n_items: number;
  n_open: number;
  n_closed: number;
  average_score: number | null;
  grade_distribution: Partial<Record<TradeQualityGrade, number>>;
  thesis_distribution: Partial<Record<TradeQualityThesis, number>>;
  completeness_distribution: Partial<
    Record<TradeQualityCompleteness, number>
  >;
  items: TradeQualityItem[];
}

// ---------------------------------------------------------------
// Exit Analytics (Phase D — read-only).
// ---------------------------------------------------------------

export type ExitCategory =
  | "take_profit" | "stop_loss" | "max_hold" | "other";

export interface ExitTrade {
  trade_id: string;
  symbol: string;
  exit_ts: string | null;
  exit_price: number;
  realized_pnl: number;
  reason: string | null;
  category: ExitCategory;
  held_days: number | null;
}

export interface ExitCategoryRow {
  category: ExitCategory;
  n: number;
  win_rate: number | null;
  total_pnl: number;
  avg_pnl: number | null;
}

export interface ExitAnalyticsResponse {
  notice: string;
  include_replay: boolean;
  n_closed: number;
  n_winners: number;
  n_losers: number;
  win_rate: number | null;
  note?: string;
  realized_pnl_total: number;
  avg_win_dollars: number | null;
  avg_loss_dollars: number | null;
  avg_hold_days: number | null;
  best_exit: ExitTrade | null;
  worst_exit: ExitTrade | null;
  by_category: ExitCategoryRow[];
  exit_reason_raw_breakdown: Array<{ reason: string; n: number }>;
  tp_sl_effectiveness: {
    tp_count: number;
    tp_total_pnl: number;
    tp_avg_pnl: number | null;
    tp_win_rate: number | null;
    sl_count: number;
    sl_total_pnl: number;
    sl_avg_pnl: number | null;
    sl_win_rate: number | null;
  };
  small_sample_warning: string | null;
  small_sample_threshold: number;
  trades: ExitTrade[];
}

export function useExitAnalytics(includeReplay = false) {
  const qs = includeReplay ? "?include_replay=true" : "";
  return useQuery<ExitAnalyticsResponse>({
    queryKey: ["exit-analytics", includeReplay],
    queryFn: () => apiGet<ExitAnalyticsResponse>(
      `/performance/paper/exit-analytics${qs}`,
    ),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
  });
}


export function useTradeQuality(limit: number = 50) {
  return useQuery<TradeQualityResponse>({
    queryKey: ["trade-quality", limit],
    queryFn: () => apiGet<TradeQualityResponse>(
      `/performance/paper/trade-quality?limit=${limit}`,
    ),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}
