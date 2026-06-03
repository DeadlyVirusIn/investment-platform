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

// ── Phase H1 — lifecycle advisory (read-only) ──────────────────────────────

export interface AdvisorySignal { level: string; reason: string }

export interface AdvisoryPosition {
  trade_id: number;
  underlying: string;
  strategy: string;
  dte: number | null;
  pct_max_profit: number | null;
  profit_so_far: number | null;
  take_profit: AdvisorySignal | null;
  dte_management: AdvisorySignal | null;
  loss_risk: AdvisorySignal | null;
  assignment_risk: { level: string; reason: string } | null;
  potential_roll_preview: {
    to_expiry: string; short_strike: number; short_mid: number | null; note: string;
  } | null;
  value_source: 'mtm_event' | 'chain' | 'mixed' | null;
  value_as_of: string | null;
}

export interface OptionsAdvisory {
  status: 'live' | 'empty';
  open_count: number;
  positions: AdvisoryPosition[];
}

export function useOptionsAdvisory() {
  return useQuery<OptionsAdvisory>({
    queryKey: ['options', 'portfolio', 'advisory'],
    queryFn: () => apiGet<OptionsAdvisory>('/options/portfolio/advisory'),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}
