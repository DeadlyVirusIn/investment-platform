// Phase 11F — Options read-only React Query hooks.
// Read-only by construction: every hook is `useQuery`, never `useMutation`.

import { useQuery } from '@tanstack/react-query';
import {
  optionsApi,
  type ChainResponse,
  type FeaturesResponse,
  type OptionsHealth,
  type PaperTradeDetail,
  type PaperTradesResponse,
  type RiskSummary,
} from './optionsApi';

const STALE = 30_000;

export function useOptionsHealth() {
  return useQuery<OptionsHealth>({
    queryKey: ['options', 'health'],
    queryFn: optionsApi.health,
    staleTime: STALE,
  });
}

export function useOptionsSymbols() {
  return useQuery<{ notice: string; symbols: string[] }>({
    queryKey: ['options', 'symbols'],
    queryFn: optionsApi.symbols,
    staleTime: 5 * 60_000,
  });
}

export function useOptionsExpiries(symbol: string | undefined) {
  return useQuery<{ notice: string; symbol: string; expiries: string[] }>({
    queryKey: ['options', 'expiries', symbol],
    queryFn: () => optionsApi.expiries(symbol!),
    enabled: !!symbol,
    staleTime: 5 * 60_000,
  });
}

export function useOptionsChain(symbol: string | undefined, expiry: string | undefined) {
  return useQuery<ChainResponse>({
    queryKey: ['options', 'chain', symbol, expiry],
    queryFn: () => optionsApi.chain(symbol!, expiry!),
    enabled: !!symbol && !!expiry,
    staleTime: STALE,
  });
}

export function useOptionsFeatures(symbol: string | undefined) {
  return useQuery<FeaturesResponse>({
    queryKey: ['options', 'features', symbol],
    queryFn: () => optionsApi.features(symbol!),
    enabled: !!symbol,
    staleTime: STALE,
  });
}

export function useOptionsPaperTrades(params: {
  status?: string; underlying?: string; limit?: number;
} = {}) {
  return useQuery<PaperTradesResponse>({
    queryKey: ['options', 'paper-trades', params],
    queryFn: () => optionsApi.paperTrades(params),
    staleTime: STALE,
  });
}

export function useOptionsPaperTradeDetail(id: number | undefined) {
  return useQuery<PaperTradeDetail>({
    queryKey: ['options', 'paper-trades', 'detail', id],
    queryFn: () => optionsApi.paperTradeDetail(id!),
    enabled: typeof id === 'number' && id > 0,
    staleTime: STALE,
  });
}

export function useOptionsRiskSummary() {
  return useQuery<RiskSummary>({
    queryKey: ['options', 'risk-summary'],
    queryFn: optionsApi.riskSummary,
    staleTime: STALE,
  });
}
