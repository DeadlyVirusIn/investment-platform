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
};
