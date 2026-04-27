// Phase 11F — read-only Options API client.
//
// Hard rules (mirror backend test_options_api_readonly.py):
//   * NO POST/PUT/PATCH/DELETE imports — only `apiGet`.
//   * NO references to execution / strategy recommendations / ML / V2.
//   * Surfaces flag tokens used by the WebUI verbatim:
//       - ASSIGNMENT_SIMPLIFIED_EXIT
//       - PIN_RISK_UNCERTAIN_OUTCOME
//       - MISSING_SETTLEMENT
//
// Keep this file the ONLY entry point to /api/options for the frontend
// so the boundary stays greppable.

import { apiGet } from '@/lib/api';

export const PAPER_ONLY_NOTICE = 'Options are paper-trading only';

export const FLAG_ASSIGNMENT_SIMPLIFIED_EXIT = 'ASSIGNMENT_SIMPLIFIED_EXIT';
export const FLAG_PIN_RISK_UNCERTAIN_OUTCOME = 'PIN_RISK_UNCERTAIN_OUTCOME';
export const FLAG_MISSING_SETTLEMENT = 'MISSING_SETTLEMENT';

export type OptionsFlag =
  | typeof FLAG_ASSIGNMENT_SIMPLIFIED_EXIT
  | typeof FLAG_PIN_RISK_UNCERTAIN_OUTCOME
  | typeof FLAG_MISSING_SETTLEMENT
  | string; // server may add more; UI handles unknowns gracefully

// All Decimal-shaped numerics arrive as `string | null` from the
// backend. Components MUST display NULL as "Insufficient data" or
// "Unavailable" — never as 0.
export type Money = string | null;

export interface OptionsHealth {
  status: string;
  paper_only: boolean;
  ml_can_affect_trades: boolean;
  notice: string;
}

export interface ChainQuote {
  option_symbol: string;
  strike: Money;
  option_type: 'CALL' | 'PUT';
  bid: Money;
  ask: Money;
  mid: Money;
  spread: Money;
  last: Money;
  volume: number | null;
  open_interest: number | null;
  iv: Money;
  delta: Money;
  gamma: Money;
  theta: Money;
  vega: Money;
  quote_age_seconds: number | null;
  provider: string;
  data_quality_flags: string[];
}

export interface ChainResponse {
  notice: string;
  symbol: string;
  expiry: string;
  as_of_utc: string | null;
  calls: ChainQuote[];
  puts: ChainQuote[];
}

export interface FeatureRow {
  as_of_date: string;
  symbol: string;
  atm_iv: Money;
  iv_rank_252d: Money;
  iv_percentile_252d: Money;
  realized_vol_20d: Money;
  vrp_30d: Money;
  skew_25d: Money;
  term_structure_30_90: Money;
  put_call_volume_ratio: Money;
  put_call_oi_ratio: Money;
  unusual_call_volume_z: Money;
  unusual_put_volume_z: Money;
  gamma_exposure_proxy: Money;
  call_wall_strike: Money;
  put_wall_strike: Money;
  data_quality_flags: string[];
}

export interface FeaturesResponse {
  notice: string;
  symbol: string;
  features: FeatureRow | null;
  gamma_exposure_label: string;
}

export interface PaperTradeHeader {
  id: number;
  underlying: string;
  strategy_name: string;
  strategy_version: string;
  status: 'PROPOSED' | 'OPEN' | 'EXPIRING' | 'CLOSED' | 'EXPIRED' | 'ASSIGNED';
  opened_at: string | null;
  closed_at: string | null;
  entry_credit_dollars: Money;
  exit_debit_dollars: Money;
  realized_pnl_dollars: Money;
  fees_total_dollars: Money;
  max_loss_dollars: Money;
  max_profit_dollars: Money;
  breakeven_lower: Money;
  breakeven_upper: Money;
  fill_model_version: string;
  paper_only: boolean;
}

export interface PaperTradesResponse {
  notice: string;
  count: number;
  trades: PaperTradeHeader[];
}

export interface LegEntryExit {
  quote_at_utc: string | null;
  bid: Money; ask: Money; mid: Money;
  iv: Money;
  delta: Money; gamma: Money; theta: Money; vega: Money;
  fill_price: Money;
  reason?: string | null;
}

export interface PaperTradeLeg {
  leg_index: number;
  option_symbol: string;
  underlying: string;
  expiry: string;
  strike: Money;
  option_type: 'CALL' | 'PUT';
  side: 'BUY' | 'SELL';
  qty: number;
  entry: LegEntryExit;
  exit: LegEntryExit;
}

export interface LifecycleEvent {
  id: number;
  event_type: string;
  event_at_utc: string | null;
  triggered_by: string;
  payload: Record<string, unknown>;
}

export interface ExpirationEvent {
  leg_index: number;
  expiry_date: string;
  underlying_settlement: Money;
  classification: 'OTM' | 'ITM' | 'PIN_RISK' | 'MISSING_DATA';
  intrinsic_value_dollars: Money;
  realized_pnl_dollars: Money;
  event_at_utc: string | null;
}

export interface AssignmentEvent {
  leg_index: number;
  event_type: string;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | null;
  ex_div_date: string | null;
  ex_div_amount: Money;
  intrinsic_value_dollars: Money;
  realized_pnl_dollars: Money;
  event_at_utc: string | null;
  notes: string | null;
}

export interface PaperTradeDetail extends PaperTradeHeader {
  notice: string;
  data_quality_flags: string[];
  legs: PaperTradeLeg[];
  lifecycle_events: LifecycleEvent[];
  expiration_events: ExpirationEvent[];
  assignment_events: AssignmentEvent[];
}

export interface ExpiryConcentration {
  expiry: string;
  n_trades: number;
  max_loss_at_expiry_dollars: Money;
}

export interface RiskSummary {
  notice: string;
  n_open_trades: number;
  max_loss_exposure_dollars: Money;
  net_delta: Money;
  net_gamma: Money;
  net_theta: Money;
  net_vega: Money;
  expiry_concentration: ExpiryConcentration[];
  n_assignment_events: number;
  n_pin_risk_events: number;
  n_missing_settlement_events: number;
  data_quality_flags: string[];
  greeks_source_label: string;
}

// ---------------------------------------------------------------------------
// Read-only fetchers (used by hooks)
// ---------------------------------------------------------------------------

export const optionsApi = {
  health:    () => apiGet<OptionsHealth>('/options/health'),
  symbols:   () => apiGet<{ notice: string; symbols: string[] }>('/options/symbols'),
  expiries:  (symbol: string) =>
    apiGet<{ notice: string; symbol: string; expiries: string[] }>(
      `/options/expiries?symbol=${encodeURIComponent(symbol)}`,
    ),
  chain:     (symbol: string, expiry: string) =>
    apiGet<ChainResponse>(
      `/options/chain?symbol=${encodeURIComponent(symbol)}&expiry=${encodeURIComponent(expiry)}`,
    ),
  features:  (symbol: string) =>
    apiGet<FeaturesResponse>(
      `/options/features?symbol=${encodeURIComponent(symbol)}`,
    ),
  paperTrades: (params: { status?: string; underlying?: string; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.status)     q.set('status', params.status);
    if (params.underlying) q.set('underlying', params.underlying);
    if (params.limit)      q.set('limit', String(params.limit));
    const qs = q.toString();
    return apiGet<PaperTradesResponse>(
      `/options/paper-trades${qs ? `?${qs}` : ''}`,
    );
  },
  paperTradeDetail: (id: number) =>
    apiGet<PaperTradeDetail>(`/options/paper-trades/${id}`),
  riskSummary: () => apiGet<RiskSummary>('/options/risk-summary'),

  // Phase 11G — Strategy Observatory (read-only)
  strategies: () => apiGet<StrategiesResponse>('/options/strategies'),
  strategyObservations: (params: {
    underlying?: string;
    qualified_only?: boolean;
    rule_id?: string;
    lookback_days?: number;
    limit?: number;
  } = {}) => {
    const q = new URLSearchParams();
    if (params.underlying)     q.set('underlying', params.underlying);
    if (params.qualified_only) q.set('qualified_only', 'true');
    if (params.rule_id)        q.set('rule_id', params.rule_id);
    if (params.lookback_days)  q.set('lookback_days', String(params.lookback_days));
    if (params.limit)          q.set('limit', String(params.limit));
    const qs = q.toString();
    return apiGet<StrategyObservationsResponse>(
      `/options/strategy-observations${qs ? `?${qs}` : ''}`,
    );
  },
  strategyObservationDetail: (id: string) =>
    apiGet<StrategyObservationDetail>(
      `/options/strategy-observations/${encodeURIComponent(id)}`,
    ),
  performanceSummary: (params: { underlying?: string; strategy_name?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.underlying)    q.set('underlying', params.underlying);
    if (params.strategy_name) q.set('strategy_name', params.strategy_name);
    const qs = q.toString();
    return apiGet<PerformanceSummary>(
      `/options/performance-summary${qs ? `?${qs}` : ''}`,
    );
  },
  diagnostics: (params: { lookback_days?: number; underlying?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.lookback_days) q.set('lookback_days', String(params.lookback_days));
    if (params.underlying)    q.set('underlying', params.underlying);
    const qs = q.toString();
    return apiGet<DiagnosticsResponse>(
      `/options/diagnostics${qs ? `?${qs}` : ''}`,
    );
  },
  scenarioReplay: (symbol: string, asOf: string) =>
    apiGet<ScenarioReplayResponse>(
      `/options/scenario-replay?symbol=${encodeURIComponent(symbol)}&as_of=${encodeURIComponent(asOf)}`,
    ),

  // Phase 11H — Controlled Strategy Evaluation Layer (read-only)
  evaluationSummary: (params: {
    underlying?: string; strategy?: string; lookback_days?: number;
  } = {}) => {
    const q = new URLSearchParams();
    if (params.underlying)    q.set('underlying', params.underlying);
    if (params.strategy)      q.set('strategy', params.strategy);
    if (params.lookback_days) q.set('lookback_days', String(params.lookback_days));
    const qs = q.toString();
    return apiGet<EvaluationSummary>(
      `/options/evaluation/summary${qs ? `?${qs}` : ''}`,
    );
  },
  evaluationScores: (params: {
    strategy?: string;
    underlying?: string;
    min_score?: number;
    qualified_only?: boolean;
    lookback_days?: number;
    limit?: number;
  } = {}) => {
    const q = new URLSearchParams();
    if (params.strategy)       q.set('strategy', params.strategy);
    if (params.underlying)     q.set('underlying', params.underlying);
    if (params.min_score !== undefined)
      q.set('min_score', String(params.min_score));
    if (params.qualified_only) q.set('qualified_only', 'true');
    if (params.lookback_days)  q.set('lookback_days', String(params.lookback_days));
    if (params.limit)          q.set('limit', String(params.limit));
    const qs = q.toString();
    return apiGet<EvaluationScoresResponse>(
      `/options/evaluation/scores${qs ? `?${qs}` : ''}`,
    );
  },
  evaluationScoreDetail: (id: string) =>
    apiGet<EvaluationScoreDetail>(
      `/options/evaluation/scores/${encodeURIComponent(id)}`,
    ),
  evaluationDistribution: (lookback_days?: number) => {
    const qs = lookback_days ? `?lookback_days=${lookback_days}` : '';
    return apiGet<EvaluationDistribution>(
      `/options/evaluation/distribution${qs}`,
    );
  },
  evaluationDiagnostics: (lookback_days?: number) => {
    const qs = lookback_days ? `?lookback_days=${lookback_days}` : '';
    return apiGet<EvaluationDiagnostics>(
      `/options/evaluation/diagnostics${qs}`,
    );
  },
};

// ---------------------------------------------------------------------------
// Phase 11H types
// ---------------------------------------------------------------------------

export interface ScoreComponent {
  component: string;
  weight_max: number;
  score: number;
  explanation: string;
}

export interface ScorePenalty {
  code: string;
  label: string;
  points: number;        // negative
  reason: string;
}

export interface EvaluationScoreItem {
  id: string;
  rule_id: string;
  underlying: string;
  as_of_date: string;
  qualified: boolean;
  total_score: number;
  components: ScoreComponent[];
  penalties: ScorePenalty[];
  flags: string[];
  inputs: Record<string, unknown>;
  model_version: string;
}

export interface EvaluationScoresResponse {
  notice: string;
  observation_only_notice: string;
  evaluation_disclaimer: string;
  count: number;
  excluded_count: number;
  scores: EvaluationScoreItem[];
  model_version: string;
}

export interface EvaluationScoreDetail extends EvaluationScoreItem {
  notice: string;
  observation_only_notice: string;
  evaluation_disclaimer: string;
}

export interface EvaluationSummary {
  notice: string;
  observation_only_notice: string;
  evaluation_disclaimer: string;
  n_observations_scored: number;
  n_included_by_filter: number;
  n_excluded_by_filter: number;
  average_score: string | null;
  median_score: string | null;
  score_distribution_buckets: { lo: number; hi: number; count: number }[];
  threshold: number;
  n_at_or_above_threshold: number;
  n_below_threshold: number;
  model_version: string;
}

export interface EvaluationDistribution {
  notice: string;
  observation_only_notice: string;
  evaluation_disclaimer: string;
  by_strategy: {
    strategy: string;
    n: number;
    mean_score: string | null;
    buckets: { lo: number; hi: number; count: number }[];
  }[];
  by_underlying: {
    underlying: string;
    n: number;
    mean_score: string | null;
    buckets: { lo: number; hi: number; count: number }[];
  }[];
  buckets_definition: { lo: number; hi: number }[];
  model_version: string;
}

export interface EvaluationDiagnostics {
  notice: string;
  observation_only_notice: string;
  evaluation_disclaimer: string;
  n_total_scored: number;
  threshold: number;
  n_at_or_above_threshold: number;
  n_below_threshold: number;
  common_penalty_drivers: { code: string; count: number }[];
  common_missing_data_drivers: { code: string; count: number }[];
  model_version: string;
}

// ---------------------------------------------------------------------------
// Phase 11G types
// ---------------------------------------------------------------------------

export interface StrategyCriterion {
  code: string;
  label: string;
  description: string;
}

export interface StrategyDef {
  rule_id: string;
  name: string;
  summary: string;
  criteria: StrategyCriterion[];
}

export interface StrategiesResponse {
  notice: string;
  observation_only_notice: string;
  strategies: StrategyDef[];
}

export interface StrategyObservationListItem {
  id: string;
  underlying: string;
  as_of_date: string;
  rule_id: string;
  rule_name: string;
  qualified: boolean;
  n_passed: number;
  n_criteria: number;
  n_chain_accepted: number;
}

export interface StrategyObservationsResponse {
  notice: string;
  observation_only_notice: string;
  count: number;
  observations: StrategyObservationListItem[];
}

export interface StrategyCheck {
  code: string;
  passed: boolean;
  reason: string;
}

export interface StrategyEvaluation {
  rule_id: string;
  name: string;
  qualified: boolean;
  n_passed: number;
  n_criteria: number;
  checks: StrategyCheck[];
  candidate: Record<string, unknown> | null;
  notes: string[];
}

export interface StrategyObservationDetail {
  notice: string;
  observation_only_notice: string;
  id: string;
  underlying: string;
  as_of_date: string;
  n_chain_accepted: number;
  evaluation: StrategyEvaluation;
}

export interface StrategyPerfRow {
  strategy_name: string;
  n: number;
  n_assigned: number;
  n_wins: number;
  win_rate: string | null;
  total_pnl_dollars: string | null;
  total_fees_dollars: string | null;
}

export interface UnderlyingPerfRow {
  underlying: string;
  n: number;
  n_wins: number;
  win_rate: string | null;
  total_pnl_dollars: string | null;
}

export interface PerformanceSummary {
  notice: string;
  observation_only_notice: string;
  n_closed_trades: number;
  n_wins: number;
  n_losses: number;
  n_max_loss_hits: number;
  n_assigned: number;
  n_expired_otm: number;
  n_closed_pre_expiry: number;
  win_rate: string | null;
  max_loss_hit_rate: string | null;
  assignment_rate: string | null;
  pin_risk_frequency_per_expiration_event: string | null;
  missing_settlement_per_expiration_event: string | null;
  total_realized_pnl_dollars: string | null;
  total_fees_dollars: string | null;
  fee_drag_ratio_of_abs_pnl: string | null;
  by_strategy: StrategyPerfRow[];
  by_underlying: UnderlyingPerfRow[];
  data_quality_flags: string[];
}

export interface DiagnosticsResponse {
  notice: string;
  observation_only_notice: string;
  lookback_days: number;
  lookback_cutoff: string;
  chain: {
    n_rows: number;
    n_missing_iv: number;
    n_missing_greeks: number;
  };
  features: {
    n_rows: number;
    flag_counts: Record<string, number>;
    n_naive_gex_warnings: number;
    n_insufficient_iv_history: number;
    n_no_price_history: number;
    n_insufficient_volume_history: number;
  };
  expirations: {
    by_classification: { classification: string; n: number }[];
    n_pin_risk: number;
    n_missing_settlement: number;
  };
  assignments: { n_events: number };
  naive_gex_label: string;
}

export interface ScenarioReplayResponse {
  notice: string;
  observation_only_notice: string;
  symbol: string;
  as_of_date: string;
  chain_summary: {
    n_raw: number;
    n_accepted: number;
    n_calls_accepted: number;
    n_puts_accepted: number;
    expiries_accepted: string[];
  };
  feature_row: FeatureRow | null;
  rule_evaluations: StrategyEvaluation[];
  nearby_trades: {
    id: number;
    strategy_name: string;
    status: string;
    opened_at: string | null;
    closed_at: string | null;
    realized_pnl_dollars: string | null;
  }[];
  data_quality_flags: string[];
}
