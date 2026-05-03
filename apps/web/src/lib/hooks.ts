// TanStack Query hooks for the paper-trading + recommendations + performance
// APIs. Centralized so pages don't duplicate query keys / fetchers.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from './api';
import type {
  ActionItem,
  ActionsListResponse,
  ActionStatus,
  ActResponse,
  BriefingNarrative,
  DashboardSummary,
  EquityResponse,
  IntelligenceSummary,
  NewsMarketSummary,
  NewsSummaryBatchResponse,
  NewsSymbolResponse,
  OpsStatusResponse,
  PaperEquityCurveResponse,
  PaperPerformanceSummary,
  PerformanceReport,
  PnlByRegimeResponse,
  PnlByScoreBucketResponse,
  PnlBySymbolResponse,
  PnlSummary,
  PortfolioDetail,
  PortfolioListResponse,
  PricesResponse,
  RecommendationsResponse,
  RejectionSummaryResponse,
  StockCandidatesResponse,
  TradesResponse,
} from '../types';

// --- Paper trading ---

export function usePaperPortfolios() {
  return useQuery<PortfolioListResponse>({
    queryKey: ['paper', 'portfolios'],
    queryFn: () => apiGet<PortfolioListResponse>('/paper/portfolios'),
  });
}

export function usePaperPortfolio(id: string | null | undefined) {
  return useQuery<PortfolioDetail>({
    queryKey: ['paper', 'portfolio', id],
    queryFn: () => apiGet<PortfolioDetail>(`/paper/portfolios/${id}`),
    enabled: !!id,
  });
}

export function usePaperTrades(id: string | null | undefined, limit = 100) {
  return useQuery<TradesResponse>({
    queryKey: ['paper', 'trades', id, limit],
    queryFn: () => apiGet<TradesResponse>(`/paper/portfolios/${id}/trades?limit=${limit}`),
    enabled: !!id,
  });
}

export function usePaperEquity(id: string | null | undefined) {
  return useQuery<EquityResponse>({
    queryKey: ['paper', 'equity', id],
    queryFn: () => apiGet<EquityResponse>(`/paper/portfolios/${id}/equity`),
    enabled: !!id,
  });
}

// --- Recommendations ---

export function useRecommendations(params?: {
  latest?: boolean;
  sort_by?: 'generated_at' | 'confidence';
  order?: 'asc' | 'desc';
  limit?: number;
}) {
  const qs = new URLSearchParams();
  if (params?.latest) qs.set('latest', 'true');
  if (params?.sort_by) qs.set('sort_by', params.sort_by);
  if (params?.order) qs.set('order', params.order);
  if (params?.limit) qs.set('limit', String(params.limit));
  const query = qs.toString();
  return useQuery<RecommendationsResponse>({
    queryKey: ['recommendations', params ?? {}],
    queryFn: () =>
      apiGet<RecommendationsResponse>(`/recommendations${query ? `?${query}` : ''}`),
  });
}

// --- Performance ---

// --- Benchmark prices ---

export function useBenchmarkPrices(
  symbol: string | null,
  params?: { from?: string | null; to?: string | null },
) {
  const qs = new URLSearchParams();
  if (params?.from) qs.set('from', params.from);
  if (params?.to) qs.set('to', params.to);
  const query = qs.toString();
  return useQuery<PricesResponse>({
    queryKey: ['asset', 'prices', symbol, params?.from ?? null, params?.to ?? null],
    queryFn: () =>
      apiGet<PricesResponse>(`/asset/${symbol}/prices${query ? `?${query}` : ''}`),
    enabled: !!symbol,
    // Benchmark data is stable; let it sit longer in cache.
    staleTime: 5 * 60_000,
    retry: 0,
  });
}

export function usePerformance(window: '30d' | '90d' = '30d') {
  return useQuery<PerformanceReport>({
    queryKey: ['performance', window],
    queryFn: () => apiGet<PerformanceReport>(`/performance?window=${window}`),
  });
}

export function usePaperPerformanceSummary(portfolioId?: string | null) {
  const qs = portfolioId ? `?portfolio_id=${portfolioId}` : '';
  return useQuery<PaperPerformanceSummary>({
    queryKey: ['performance', 'paper', 'summary', portfolioId ?? null],
    queryFn: () => apiGet<PaperPerformanceSummary>(`/performance/summary${qs}`),
  });
}

export function usePaperEquityCurve(portfolioId?: string | null) {
  const qs = portfolioId ? `?portfolio_id=${portfolioId}` : '';
  return useQuery<PaperEquityCurveResponse>({
    queryKey: ['performance', 'paper', 'equity-curve', portfolioId ?? null],
    queryFn: () => apiGet<PaperEquityCurveResponse>(`/performance/equity-curve${qs}`),
  });
}

// --- Dashboard + PnL (paper-truth) ---

export function useDashboardSummary(portfolioId?: string | null, asOf?: string | null) {
  const params = new URLSearchParams();
  if (portfolioId) params.set('portfolio_id', portfolioId);
  if (asOf) params.set('as_of', asOf);
  const qs = params.toString();
  return useQuery<DashboardSummary>({
    queryKey: ['dashboard', 'summary', portfolioId ?? null, asOf ?? null],
    queryFn: () => apiGet<DashboardSummary>(`/dashboard/summary${qs ? `?${qs}` : ''}`),
    refetchInterval: 30_000,
  });
}

export function usePnlSummary(portfolioId?: string | null) {
  const qs = portfolioId ? `?portfolio_id=${portfolioId}` : '';
  return useQuery<PnlSummary>({
    queryKey: ['pnl', 'summary', portfolioId ?? null],
    queryFn: () => apiGet<PnlSummary>(`/pnl/summary${qs}`),
  });
}

export function usePnlBySymbol(portfolioId?: string | null) {
  const qs = portfolioId ? `?portfolio_id=${portfolioId}` : '';
  return useQuery<PnlBySymbolResponse>({
    queryKey: ['pnl', 'by-symbol', portfolioId ?? null],
    queryFn: () => apiGet<PnlBySymbolResponse>(`/pnl/by-symbol${qs}`),
  });
}

export function usePnlByScoreBucket(portfolioId?: string | null) {
  const qs = portfolioId ? `?portfolio_id=${portfolioId}` : '';
  return useQuery<PnlByScoreBucketResponse>({
    queryKey: ['pnl', 'by-score-bucket', portfolioId ?? null],
    queryFn: () => apiGet<PnlByScoreBucketResponse>(`/pnl/by-score-bucket${qs}`),
  });
}

export function usePnlByRegime(portfolioId?: string | null) {
  const qs = portfolioId ? `?portfolio_id=${portfolioId}` : '';
  return useQuery<PnlByRegimeResponse>({
    queryKey: ['pnl', 'by-regime', portfolioId ?? null],
    queryFn: () => apiGet<PnlByRegimeResponse>(`/pnl/by-regime${qs}`),
  });
}

// --- Stock engine candidates ---

export function useStockCandidates(params?: {
  as_of?: string | null;
  status?: 'accepted' | 'rejected';
  action?: string;
  limit?: number;
}) {
  const qs = new URLSearchParams();
  if (params?.as_of) qs.set('as_of', params.as_of);
  if (params?.status) qs.set('status', params.status);
  if (params?.action) qs.set('action', params.action);
  if (params?.limit) qs.set('limit', String(params.limit));
  const q = qs.toString();
  return useQuery<StockCandidatesResponse>({
    queryKey: ['stock-engine', 'candidates', params ?? {}],
    queryFn: () =>
      apiGet<StockCandidatesResponse>(`/stock-engine/candidates${q ? `?${q}` : ''}`),
  });
}

export function useRejectionSummary(asOf?: string | null) {
  const qs = asOf ? `?as_of=${asOf}` : '';
  return useQuery<RejectionSummaryResponse>({
    queryKey: ['stock-engine', 'rejections', asOf ?? null],
    queryFn: () => apiGet<RejectionSummaryResponse>(`/stock-engine/rejections/summary${qs}`),
  });
}

// --- Ops jobs (/api/jobs/status with counts) ---

export function useOpsStatus() {
  return useQuery<OpsStatusResponse>({
    queryKey: ['jobs', 'status'],
    queryFn: () => apiGet<OpsStatusResponse>('/jobs/status'),
    refetchInterval: 30_000,
  });
}

// --- News Intelligence ---

export function useSymbolNews(symbol: string | null, days = 7, limit = 5) {
  return useQuery<NewsSymbolResponse>({
    queryKey: ['news', 'symbol', symbol, days, limit],
    queryFn: () =>
      apiGet<NewsSymbolResponse>(
        `/news/symbol/${symbol}?days=${days}&limit=${limit}`,
      ),
    enabled: !!symbol,
    staleTime: 60_000,
  });
}

export function useNewsSummaryBatch(symbols: string[], days = 7) {
  const qs = symbols
    .map(s => `symbols=${encodeURIComponent(s)}`)
    .join('&');
  return useQuery<NewsSummaryBatchResponse>({
    queryKey: ['news', 'summary', symbols.join(','), days],
    queryFn: () =>
      apiGet<NewsSummaryBatchResponse>(
        `/news/summary?${qs}&days=${days}`,
      ),
    enabled: symbols.length > 0,
    staleTime: 60_000,
  });
}

export function useIntelligenceSummary() {
  return useQuery<IntelligenceSummary>({
    queryKey: ['intelligence', 'summary'],
    queryFn: () => apiGet<IntelligenceSummary>('/intelligence/summary'),
    refetchInterval: 60_000,
  });
}

export function useBriefingNarrative() {
  return useQuery<BriefingNarrative>({
    queryKey: ['briefing', 'narrative'],
    queryFn: () => apiGet<BriefingNarrative>('/briefing/narrative'),
    refetchInterval: 60_000,
  });
}

export function useMarketNewsSummary(days = 3, limit = 5) {
  return useQuery<NewsMarketSummary>({
    queryKey: ['news', 'market-summary', days, limit],
    queryFn: () =>
      apiGet<NewsMarketSummary>(
        `/news/market-summary?days=${days}&limit=${limit}`,
      ),
    staleTime: 60_000,
  });
}

// --- Decision UX (Actions) ---

export function useActions(status: ActionStatus = 'pending', limit = 50) {
  return useQuery<ActionsListResponse>({
    queryKey: ['actions', 'list', status, limit],
    queryFn: () => apiGet<ActionsListResponse>(`/actions?status=${status}&limit=${limit}`),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

export function useAction(actionId: string | null) {
  return useQuery<ActionItem>({
    queryKey: ['actions', 'item', actionId],
    queryFn: () => apiGet<ActionItem>(`/actions/${actionId}`),
    enabled: !!actionId,
    staleTime: 0,
  });
}

export function useAct() {
  const qc = useQueryClient();
  return useMutation<ActResponse, Error, string>({
    mutationFn: (id: string) => apiPost<ActResponse>(`/actions/${id}/act`, {}),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ['actions'] });
      qc.invalidateQueries({ queryKey: ['paper'] });
      qc.invalidateQueries({ queryKey: ['actions', 'item', id] });
    },
  });
}

export function useDismiss() {
  const qc = useQueryClient();
  return useMutation<{ action_id: string }, Error, { id: string; reason?: string }>({
    mutationFn: ({ id, reason }) =>
      apiPost<{ action_id: string }>(`/actions/${id}/dismiss`, { reason: reason ?? 'user_dismiss' }),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['actions'] });
      qc.invalidateQueries({ queryKey: ['actions', 'item', vars.id] });
    },
  });
}
