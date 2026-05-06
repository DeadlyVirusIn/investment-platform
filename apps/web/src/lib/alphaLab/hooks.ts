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
