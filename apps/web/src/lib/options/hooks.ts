// Phase 11F — Options read-only React Query hooks.
// Read-only by construction: every hook is `useQuery`, never `useMutation`.

import { useQuery } from '@tanstack/react-query';
import {
  optionsApi,
  type ChainResponse,
  type DiagnosticsResponse,
  type FeaturesResponse,
  type OptionsHealth,
  type PaperTradeDetail,
  type PaperTradesResponse,
  type PerformanceSummary,
  type RiskSummary,
  type ScenarioReplayResponse,
  type StrategiesResponse,
  type StrategyObservationDetail,
  type StrategyObservationsResponse,
  type EvaluationSummary,
  type EvaluationScoresResponse,
  type EvaluationScoreDetail,
  type EvaluationDistribution,
  type EvaluationDiagnostics,
  type DecisionSupportSummary,
  type DecisionSupportReviewQueueResponse,
  type DecisionSupportReviewDetail,
  type DecisionSupportBucketsResponse,
  type DecisionSupportDiagnostics,
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

// ---------------------------------------------------------------------------
// Phase 11G — read-only observability hooks
// ---------------------------------------------------------------------------

export function useOptionsStrategies() {
  return useQuery<StrategiesResponse>({
    queryKey: ['options', 'strategies'],
    queryFn: optionsApi.strategies,
    staleTime: 5 * 60_000,
  });
}

export function useOptionsStrategyObservations(params: {
  underlying?: string;
  qualified_only?: boolean;
  rule_id?: string;
  lookback_days?: number;
  limit?: number;
} = {}) {
  return useQuery<StrategyObservationsResponse>({
    queryKey: ['options', 'strategy-observations', params],
    queryFn: () => optionsApi.strategyObservations(params),
    staleTime: STALE,
  });
}

export function useOptionsStrategyObservationDetail(id: string | undefined) {
  return useQuery<StrategyObservationDetail>({
    queryKey: ['options', 'strategy-observations', 'detail', id],
    queryFn: () => optionsApi.strategyObservationDetail(id!),
    enabled: !!id,
    staleTime: STALE,
  });
}

export function useOptionsPerformanceSummary(params: {
  underlying?: string; strategy_name?: string;
} = {}) {
  return useQuery<PerformanceSummary>({
    queryKey: ['options', 'performance-summary', params],
    queryFn: () => optionsApi.performanceSummary(params),
    staleTime: STALE,
  });
}

export function useOptionsDiagnostics(params: {
  lookback_days?: number; underlying?: string;
} = {}) {
  return useQuery<DiagnosticsResponse>({
    queryKey: ['options', 'diagnostics', params],
    queryFn: () => optionsApi.diagnostics(params),
    staleTime: STALE,
  });
}

export function useOptionsScenarioReplay(symbol: string | undefined, asOf: string | undefined) {
  return useQuery<ScenarioReplayResponse>({
    queryKey: ['options', 'scenario-replay', symbol, asOf],
    queryFn: () => optionsApi.scenarioReplay(symbol!, asOf!),
    enabled: !!symbol && !!asOf,
    staleTime: STALE,
  });
}

// ---------------------------------------------------------------------------
// Phase 11H — read-only evaluation hooks
// ---------------------------------------------------------------------------

export function useOptionsEvaluationSummary(params: {
  underlying?: string; strategy?: string; lookback_days?: number;
} = {}) {
  return useQuery<EvaluationSummary>({
    queryKey: ['options', 'evaluation', 'summary', params],
    queryFn: () => optionsApi.evaluationSummary(params),
    staleTime: STALE,
  });
}

export function useOptionsEvaluationScores(params: {
  strategy?: string;
  underlying?: string;
  min_score?: number;
  qualified_only?: boolean;
  lookback_days?: number;
  limit?: number;
} = {}) {
  return useQuery<EvaluationScoresResponse>({
    queryKey: ['options', 'evaluation', 'scores', params],
    queryFn: () => optionsApi.evaluationScores(params),
    staleTime: STALE,
  });
}

export function useOptionsEvaluationScoreDetail(id: string | undefined) {
  return useQuery<EvaluationScoreDetail>({
    queryKey: ['options', 'evaluation', 'scores', 'detail', id],
    queryFn: () => optionsApi.evaluationScoreDetail(id!),
    enabled: !!id,
    staleTime: STALE,
  });
}

export function useOptionsEvaluationDistribution(lookback_days?: number) {
  return useQuery<EvaluationDistribution>({
    queryKey: ['options', 'evaluation', 'distribution', lookback_days],
    queryFn: () => optionsApi.evaluationDistribution(lookback_days),
    staleTime: STALE,
  });
}

export function useOptionsEvaluationDiagnostics(lookback_days?: number) {
  return useQuery<EvaluationDiagnostics>({
    queryKey: ['options', 'evaluation', 'diagnostics', lookback_days],
    queryFn: () => optionsApi.evaluationDiagnostics(lookback_days),
    staleTime: STALE,
  });
}

// ---------------------------------------------------------------------------
// Phase 11I — read-only decision support hooks
// ---------------------------------------------------------------------------

export function useOptionsDecisionSupportSummary(lookback_days?: number) {
  return useQuery<DecisionSupportSummary>({
    queryKey: ['options', 'decision-support', 'summary', lookback_days],
    queryFn: () => optionsApi.decisionSupportSummary(lookback_days),
    staleTime: STALE,
  });
}

export function useOptionsDecisionSupportReviewQueue(params: {
  strategy?: string;
  underlying?: string;
  min_score?: number;
  qualified_only?: boolean;
  exclude_severe_flags?: boolean;
  bucket?: string;
  lookback_days?: number;
  limit?: number;
} = {}) {
  return useQuery<DecisionSupportReviewQueueResponse>({
    queryKey: ['options', 'decision-support', 'review-queue', params],
    queryFn: () => optionsApi.decisionSupportReviewQueue(params),
    staleTime: STALE,
  });
}

export function useOptionsDecisionSupportReviewDetail(id: string | undefined) {
  return useQuery<DecisionSupportReviewDetail>({
    queryKey: ['options', 'decision-support', 'review-queue', 'detail', id],
    queryFn: () => optionsApi.decisionSupportReviewDetail(id!),
    enabled: !!id,
    staleTime: STALE,
  });
}

export function useOptionsDecisionSupportBuckets(lookback_days?: number) {
  return useQuery<DecisionSupportBucketsResponse>({
    queryKey: ['options', 'decision-support', 'buckets', lookback_days],
    queryFn: () => optionsApi.decisionSupportBuckets(lookback_days),
    staleTime: STALE,
  });
}

export function useOptionsDecisionSupportDiagnostics(lookback_days?: number) {
  return useQuery<DecisionSupportDiagnostics>({
    queryKey: ['options', 'decision-support', 'diagnostics', lookback_days],
    queryFn: () => optionsApi.decisionSupportDiagnostics(lookback_days),
    staleTime: STALE,
  });
}
