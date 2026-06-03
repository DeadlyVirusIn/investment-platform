// Phase G1 — options portfolio intelligence hook. Read-only aggregate of
// open options paper positions (GET /api/options/portfolio). No mutation.

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

export interface OptionsPortfolioPosition {
  trade_id: number;
  underlying: string;
  strategy: string;
  capital_at_risk: number;
  max_profit: number;
  net_delta: number | null;
  net_theta: number | null;
  net_vega: number | null;
  dte: number | null;
}

export interface OptionsConcentration {
  underlying: string;
  capital_at_risk: number;
  pct: number;       // 0..1
  high: boolean;     // > 40%
}

export interface OptionsPortfolio {
  status: 'live' | 'empty';
  open_count: number;
  capital_at_risk: number;
  max_profit: number;
  net_delta: number | null;
  net_theta: number | null;
  net_vega: number | null;
  greeks_source: 'current' | 'entry' | 'mixed' | null;
  greeks_as_of: string | null;
  concentration: OptionsConcentration[];
  positions: OptionsPortfolioPosition[];
}

export function useOptionsPortfolio() {
  return useQuery<OptionsPortfolio>({
    queryKey: ['options', 'portfolio'],
    queryFn: () => apiGet<OptionsPortfolio>('/options/portfolio'),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}
